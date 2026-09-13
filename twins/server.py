"""One authoritative local simulation; the browser only observes and controls it."""
import logging
import io
import hashlib
import platform
import os
import csv
import asyncio
from importlib.metadata import version as package_version
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .storage import RunStore, encode

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["run", "pause", "step", "reset", "phase", "plasticity", "shuffle", "speed", "silence", "experiment", "mouse"]
    value: Any = None
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class Runtime:
    def __init__(self, factory, directory, worker=True):
        self.factory = factory
        self.lock = threading.RLock()
        self.store = RunStore(Path(directory) / "experiments.sqlite3")
        self.running = False
        self.speed = 1
        self.error = None
        self.tick_ms = 0.0
        self.stop = threading.Event()
        self.seen_events = set()
        self.engine = factory(seed=42)
        self.checkpoints = None
        self.atlas = None
        self.restored = None
        if hasattr(self.engine, "world"):
            from .checkpoints import Checkpoints
            from .atlas import Atlas
            self.checkpoints = Checkpoints(Path(directory) / "checkpoints")
            if (self.checkpoints.path / "autosave.twins").exists():
                try:
                    self.engine, self.restored = self.checkpoints.restore("autosave", factory)
                except (ValueError, OSError) as exc:
                    self.error = "Saved state could not be restored: " + str(exc)
            self.atlas = Atlas(self.engine)
        self.start_run()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="twins-experiment")
        if worker:
            self.thread.start()

    def start_run(self):
        state = self.engine.snapshot()
        self.seen_events.clear()
        self.run_id = self.store.create({"version": __version__, "seed": state.get("seed", 42),
            "topology": state.get("topology"), "initial_state": state.get("initial_state"),
            "python": platform.python_version(), "platform": platform.system(),
            "packages": {name: package_version(name) for name in ("numpy", "scipy", "pyarrow", "fastapi", "uvicorn")},
            "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                            for name in ("twins/engine.py", "twins/connectome.py", "twins/server.py", "twins/storage.py", "requirements.lock")
                            if (ROOT / name).is_file()},
            "model": "Custom LIF dynamics and engineered learning/readouts; see METHODS.md"})
        self.persist(state, force=True)

    def persist(self, state, force=False):
        if hasattr(self.engine, "drain_trials"):
            self.store.trials(self.run_id, self.engine.drain_trials())
        for event in state.get("events", []):
            key = encode(event)
            if key not in self.seen_events:
                self.store.event(self.run_id, event)
                self.seen_events.add(key)
        if force or state["tick"] % 5 == 0:
            self.store.record(self.run_id, state)

    def state(self):
        with self.lock:
            result = self.engine.snapshot()
            result.update({"run_id": self.run_id, "running": self.running,
                "speed": self.speed, "error": self.error, "tick_wall_ms": round(self.tick_ms, 2),
                "snapshot_interval_ticks": 5, "version": __version__, "restored": self.restored})
            return result

    def step(self):
        start = time.perf_counter()
        state = self.engine.step(1)
        if state is None:
            state = self.engine.snapshot()
        self.tick_ms = (time.perf_counter() - start) * 1000
        self.persist(state)
        if self.checkpoints and state["tick"] % 25 == 0:
            self.checkpoints.save(self.engine, self.run_id, "Automatic recovery", autosave=True)
        if state["tick"] >= 20000 or state.get("protocol", {}).get("completed"):
            self.running = False
            self.persist(state, force=True)

    def loop(self):
        while not self.stop.is_set():
            started = time.perf_counter()
            with self.lock:
                if self.running:
                    try:
                        self.step()
                    except Exception as exc:
                        logging.exception("Simulation paused after an error")
                        self.running = False
                        self.error = f"{type(exc).__name__}: {exc}"
            self.stop.wait(max(0.002, 0.12 / self.speed - (time.perf_counter() - started)))

    def control(self, command):
        with self.lock:
            action, value = command.action, command.value
            if action in ("plasticity", "shuffle", "silence", "mouse") and type(value) is not bool:
                raise ValueError("value must be a boolean")
            if action == "speed" and (type(value) is not int or value not in (1, 4, 12)):
                raise ValueError("speed must be 1, 4 or 12")
            if action == "phase" and value not in (
                "baseline", "familiarization", "recognition", "communication", "separation", "reunion"):
                raise ValueError("Unknown experiment phase")
            if action == "experiment":
                if not hasattr(self.engine, "configure") or not isinstance(value, dict):
                    raise ValueError("Experiment requires a protocol object")
                from .protocols import protocol_spec
                spec = {**protocol_spec(value.get("id")), **{k: value[k] for k in ("onset","offset","duration","intensity") if k in value}}
                if any(type(spec[k]) is not int for k in ("onset","offset","duration")):
                    raise ValueError("Protocol times must be integer ticks")
                if not 0 <= spec["onset"] < spec["offset"] <= spec["duration"] <= 20000:
                    raise ValueError("Require onset < offset <= duration")
                if type(spec["intensity"]) not in (int,float) or not 0 <= spec["intensity"] <= 1:
                    raise ValueError("Intensity must be between 0 and 1")
            self.store.action(self.run_id, self.engine.snapshot()["tick"], command.model_dump())
            if action == "run":
                if self.error:
                    raise ValueError("Reset the experiment after resolving the reported error")
                if self.engine.snapshot().get("protocol", {}).get("completed"):
                    raise ValueError("Protocol complete. Select a phase or start a new experiment.")
                self.running = True
            elif action == "pause":
                self.running = False
            elif action == "speed":
                self.speed = value
            elif action == "step":
                self.running = False
                self.step()
            elif action == "reset":
                self.running = False
                self.persist(self.engine.snapshot(), force=True)
                self.engine = self.factory(seed=command.seed if command.seed is not None else 42)
                self.error = None
                self.start_run()
            else:
                self.engine.command(action, value=value)
            self.persist(self.engine.snapshot(), force=True)
            return self.state()

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=30)
        with self.lock:
            self.persist(self.engine.snapshot(), force=True)
            if self.checkpoints:
                self.checkpoints.save(self.engine, self.run_id, "Automatic recovery", autosave=True)
            self.store.close()


def create_app(factory=None, directory=None, worker=True):
    @asynccontextmanager
    async def lifespan(app):
        if factory is None:
            from .connectome import load_connectome
            from .laboratory import Laboratory
            if os.environ.get("TWINS_DEMO") == "1":
                from .engine import synthetic_graph
                graph = synthetic_graph(256)
            else:
                graph = load_connectome(os.environ.get("TWINS_DATA_DIR"))
            make = lambda seed: Laboratory(seed=seed, graph=graph)
        else:
            make = factory
        app.state.runtime = Runtime(make, directory or os.environ.get("TWINS_RUN_DIR") or ROOT / "data" / "runs", worker)
        yield
        app.state.runtime.close()

    app = FastAPI(title="The Twins", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.url.hostname
        if host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return JSONResponse({"detail": "Local console only"}, status_code=403)
        origin = request.headers.get("origin")
        session_token = os.environ.get("TWINS_SESSION_TOKEN")
        if session_token and request.url.path.startswith("/api/") and request.cookies.get("twins_session") != session_token:
            if request.headers.get("authorization") != "Bearer " + session_token:
                return JSONResponse({"detail":"Launch this console from TWINS desktop."},status_code=401)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin control is disabled"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site control is disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/state")
    def state(request: Request):
        return request.app.state.runtime.state()

    @app.get("/api/meta")
    def meta(request: Request):
        state = request.app.state.runtime.state()
        return {"version": __version__, "topology": state.get("topology"),
            "model": "Custom LIF + engineered associative readouts", "local_only": True,
            "data_license": "Separate FlyWire data terms; see /docs/SOURCES.md",
            "phases": ["baseline", "familiarization", "recognition", "communication", "separation", "reunion"]}

    @app.get("/health")
    def health():
        return {"ok": True, "application": "TWINS", "version": __version__}

    @app.get("/api/atlas")
    def atlas(request: Request):
        runtime=request.app.state.runtime
        if runtime.atlas is None: return {"available":False,"nodes":[],"edges":[]}
        return runtime.atlas.data

    @app.get("/api/atlas/activity")
    def atlas_activity(request: Request):
        runtime=request.app.state.runtime
        with runtime.lock:
            return runtime.atlas.activity(runtime.engine) if runtime.atlas else {"indices":[],"a":[],"b":[]}

    @app.get("/api/experiments")
    def experiments():
        from .protocols import templates
        return templates()

    @app.get("/api/checkpoints")
    def checkpoint_list(request: Request):
        cp=request.app.state.runtime.checkpoints
        return cp.list() if cp else []

    @app.post("/api/checkpoints")
    def checkpoint_save(request: Request):
        runtime=request.app.state.runtime
        with runtime.lock:
            if not runtime.checkpoints: raise HTTPException(409,"Checkpoint support unavailable")
            runtime.persist(runtime.engine.snapshot(),force=True)
            manifest=runtime.checkpoints.save(runtime.engine,runtime.run_id)
            runtime.engine._event("checkpoint","Checkpoint saved",checkpoint=manifest["id"])
            return manifest

    @app.post("/api/checkpoints/{identifier}/restore")
    def checkpoint_restore(identifier: str, request: Request):
        runtime=request.app.state.runtime
        with runtime.lock:
            if not runtime.checkpoints: raise HTTPException(409,"Checkpoint support unavailable")
            try: restored,manifest=runtime.checkpoints.restore(identifier,runtime.factory)
            except (ValueError,OSError) as exc: raise HTTPException(422,str(exc)) from exc
            runtime.running=False
            runtime.persist(runtime.engine.snapshot(),force=True)
            runtime.engine=restored
            runtime.restored=manifest
            runtime.error=None
            runtime.start_run()
            return runtime.state()

    @app.get("/api/checkpoints/{identifier}/download")
    def checkpoint_download(identifier: str, request: Request):
        cp=request.app.state.runtime.checkpoints
        if cp is None: raise HTTPException(409,"Checkpoint support unavailable")
        try: path=cp.file(identifier)
        except ValueError as exc: raise HTTPException(404,str(exc)) from exc
        return FileResponse(path,filename=path.name)

    @app.get("/api/export/table")
    def export_table(request: Request, format: Literal["csv","parquet"]="csv"):
        runtime=request.app.state.runtime
        with runtime.lock:
            records=list(getattr(runtime.engine,"world_history",[]))
        flat=[]
        for r in records:
            row={k:v for k,v in r.items() if k not in ("a","b")}
            for side in ("a","b"):
                row.update({side+"_"+k:v for k,v in r[side].items()})
            flat.append(row)
        if format=="parquet":
            import pyarrow as pa
            import pyarrow.parquet as pq
            stream=io.BytesIO();pq.write_table(pa.Table.from_pylist(flat),stream)
            return Response(stream.getvalue(),media_type="application/octet-stream",
                            headers={"Content-Disposition":'attachment; filename="twins-telemetry.parquet"'})
        stream=io.StringIO()
        if flat:
            writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
        return Response(stream.getvalue(),media_type="text/csv",
                        headers={"Content-Disposition":'attachment; filename="twins-telemetry.csv"'})

    @app.websocket("/api/stream")
    async def stream(ws: WebSocket):
        host=ws.headers.get("host","")
        origin=ws.headers.get("origin")
        token=os.environ.get("TWINS_SESSION_TOKEN")
        if ws.url.hostname not in ("127.0.0.1","localhost","::1","testserver") or (
            origin and urlsplit(origin).netloc != host) or (token and ws.cookies.get("twins_session")!=token):
            await ws.close(code=1008);return
        await ws.accept()
        try:
            while True:
                state=await asyncio.to_thread(ws.app.state.runtime.state)
                await ws.send_json(state)
                await asyncio.sleep(.3)
        except WebSocketDisconnect: pass

    @app.post("/api/control")
    def control(command: Control, request: Request):
        try:
            return request.app.state.runtime.control(command)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/neurons/{index}")
    def neuron(index: str, request: Request):
        runtime = request.app.state.runtime
        with runtime.lock:
            try:
                return runtime.engine.inspect_neuron(int(index) if len(index) < 12 and index.lstrip("-").isdigit() else index)
            except (ValueError, IndexError, KeyError) as exc:
                raise HTTPException(404, "Neuron not found") from exc

    @app.get("/api/runs")
    def runs(request: Request):
        return request.app.state.runtime.store.list()

    def export_response(runtime, run_id):
        try:
            payload = runtime.store.export(run_id)
        except KeyError as exc:
            raise HTTPException(404, "Run not found") from exc
        return Response(encode(payload), media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="the-twins-{run_id}.json"'})

    @app.get("/api/export")
    def export(request: Request):
        runtime = request.app.state.runtime
        with runtime.lock:
            runtime.persist(runtime.engine.snapshot(), force=True)
            return export_response(runtime, runtime.run_id)

    @app.get("/api/arrays")
    def arrays(request: Request):
        import numpy as np
        runtime = request.app.state.runtime
        with runtime.lock:
            payload = runtime.engine.checkpoint_arrays()
            run_id = runtime.run_id
        stream = io.BytesIO()
        np.savez_compressed(stream, **payload)
        return Response(stream.getvalue(), media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="the-twins-{run_id}-arrays.npz"'})

    @app.get("/api/runs/{run_id}/export")
    def export_run(run_id: str, request: Request):
        return export_response(request.app.state.runtime, run_id)

    @app.get("/api/runs/{run_id}/state")
    def replay(run_id: str, request: Request, tick: int = 0):
        try:
            return request.app.state.runtime.store.frame(run_id, tick)
        except KeyError as exc:
            raise HTTPException(404, "Recorded frame not found") from exc

    @app.get("/")
    def index(request: Request):
        path=STATIC / "dist" / "index.html"
        response=FileResponse(path if path.exists() else STATIC / "index.html")
        token=os.environ.get("TWINS_SESSION_TOKEN")
        if token and request.query_params.get("launch")==token:
            response.set_cookie("twins_session",token,httponly=True,samesite="strict")
        return response

    app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
    app.mount("/docs", StaticFiles(directory=ROOT / "docs", check_dir=False), name="methods")
    return app


app = create_app()
