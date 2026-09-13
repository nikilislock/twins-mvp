"""Append-only experiment records, with bounded snapshots for replay."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class RunStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created TEXT, metadata TEXT);
          CREATE TABLE IF NOT EXISTS snapshots(run_id TEXT, tick INTEGER, state TEXT,
            PRIMARY KEY(run_id,tick));
          CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY, run_id TEXT,
            tick INTEGER, payload TEXT);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, run_id TEXT,
            tick INTEGER, payload TEXT);
          CREATE TABLE IF NOT EXISTS trials(id INTEGER PRIMARY KEY, run_id TEXT,
            tick INTEGER, payload TEXT);
        """)
        self.db.commit()

    def create(self, metadata):
        run_id = uuid.uuid4().hex[:16]
        with self.lock, self.db:
            self.db.execute("INSERT INTO runs VALUES(?,?,?)", (
                run_id, datetime.now(timezone.utc).isoformat(), encode(metadata)))
        return run_id

    def record(self, run_id, state):
        # History is reconstructed from these snapshots, not duplicated at every tick.
        trimmed = {k: v for k, v in state.items() if k not in ("history", "events")}
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)",
                            (run_id, state["tick"], encode(trimmed)))

    def action(self, run_id, tick, payload):
        with self.lock, self.db:
            self.db.execute("INSERT INTO actions(run_id,tick,payload) VALUES(?,?,?)",
                            (run_id, tick, encode(payload)))

    def event(self, run_id, event):
        with self.lock, self.db:
            self.db.execute("INSERT INTO events(run_id,tick,payload) VALUES(?,?,?)",
                            (run_id, event.get("tick", 0), encode(event)))

    def trials(self, run_id, trials):
        if not trials:
            return
        with self.lock, self.db:
            self.db.executemany("INSERT INTO trials(run_id,tick,payload) VALUES(?,?,?)",
                                [(run_id, item.get("tick", 0), encode(item)) for item in trials])

    def list(self):
        with self.lock:
            return [{"id": row[0], "created": row[1], "metadata": json.loads(row[2]),
                     "last_tick": row[3] or 0, "frames": row[4]}
                    for row in self.db.execute("""SELECT r.id,r.created,r.metadata,
                      MAX(s.tick),COUNT(s.tick) FROM runs r LEFT JOIN snapshots s
                      ON r.id=s.run_id GROUP BY r.id ORDER BY r.created DESC""")]

    def export(self, run_id):
        with self.lock:
            row = self.db.execute("SELECT created,metadata FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return {"schema_version": 1, "run_id": run_id, "created": row[0],
                    "metadata": json.loads(row[1]), "snapshot_interval_ticks": 5,
                    "snapshots": [json.loads(x[0]) for x in self.db.execute(
                        "SELECT state FROM snapshots WHERE run_id=? ORDER BY tick", (run_id,))],
                    "actions": [{"tick": x[0], **json.loads(x[1])} for x in self.db.execute(
                        "SELECT tick,payload FROM actions WHERE run_id=? ORDER BY id", (run_id,))],
                    "events": [json.loads(x[0]) for x in self.db.execute(
                        "SELECT payload FROM events WHERE run_id=? ORDER BY id", (run_id,))],
                    "trials": [json.loads(x[0]) for x in self.db.execute(
                        "SELECT payload FROM trials WHERE run_id=? ORDER BY id", (run_id,))]}

    def frame(self, run_id, tick):
        with self.lock:
            row = self.db.execute("SELECT state FROM snapshots WHERE run_id=? AND tick<=? ORDER BY tick DESC LIMIT 1",
                                  (run_id, tick)).fetchone()
            if row is None:
                raise KeyError(run_id)
            state = json.loads(row[0])
            state["replay"] = True
            state["run_id"] = run_id
            state["running"] = False
            state["history"] = []
            frames = self.db.execute("SELECT state FROM snapshots WHERE run_id=? AND tick<=? ORDER BY tick DESC LIMIT 360",
                                     (run_id, state["tick"])).fetchall()
            for frame in reversed(frames):
                saved = json.loads(frame[0])
                metrics = saved.get("metrics", {})
                twins = saved.get("twins", [{}, {}])
                state["history"].append({"tick": saved["tick"], "phase": saved.get("phase"),
                    **metrics, "spike_rate_a": twins[0].get("spike_rate"),
                    "spike_rate_b": twins[1].get("spike_rate")})
            state["events"] = [json.loads(event[0]) for event in reversed(self.db.execute(
                "SELECT payload FROM events WHERE run_id=? AND tick<=? ORDER BY id DESC LIMIT 80",
                (run_id, state["tick"])).fetchall())]
            return state

    def close(self):
        with self.lock:
            self.db.close()
