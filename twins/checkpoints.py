"""Versioned, checksummed, atomic checkpoints. Never loads pickle or executable data."""
from __future__ import annotations
from collections import deque
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import uuid
import zipfile
import numpy as np

EXCLUDED = {"graph","matrix","agents","rng","world","_outgoing","_id_lookup","_regions",
            "ports","background","sample_indices","_sample_xy","_sample_edges"}

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()

def pack(experiment):
    arrays={}
    def encode(value):
        if isinstance(value,np.ndarray):
            key=f"a{len(arrays)}"; arrays[key]=value.copy()
            return {"__array__":key}
        if isinstance(value,np.generic): return value.item()
        if isinstance(value,deque): return {"__deque__":[encode(x) for x in value],"maxlen":value.maxlen}
        if isinstance(value,dict): return {str(k):encode(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)): return [encode(x) for x in value]
        if value is None or isinstance(value,(str,bool,int,float)): return value
        raise TypeError(f"Unsupported checkpoint type: {type(value).__name__}")
    state={"engine":encode({k:v for k,v in vars(experiment).items() if k not in EXCLUDED}),
           "agents":[encode({k:v for k,v in vars(a).items() if k!="rng"}) for a in experiment.agents],
           "rng":encode(experiment.rng.bit_generator.state),
           "agent_rng":[encode(a.rng.bit_generator.state) for a in experiment.agents],
           "world":encode({k:v for k,v in vars(experiment.world).items() if k!="rng"}) if hasattr(experiment,"world") else None,
           "world_rng":encode(experiment.world.rng.bit_generator.state) if hasattr(experiment,"world") else None}
    return state,arrays

def state_hash(experiment):
    state,arrays=pack(experiment)
    digest=hashlib.sha256(canonical(state))
    for key,array in sorted(arrays.items()):
        digest.update(key.encode());digest.update(str(array.dtype).encode())
        digest.update(canonical(array.shape));digest.update(array.tobytes())
    return digest.hexdigest()

class Checkpoints:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)

    def save(self,experiment,run_id,label="Manual checkpoint",autosave=False):
        state,arrays=pack(experiment)
        stream=io.BytesIO();np.savez_compressed(stream,**arrays)
        blob=stream.getvalue();meta=canonical(state)
        identifier="autosave" if autosave else uuid.uuid4().hex[:16]
        manifest={"schema":1,"id":identifier,"label":label,"run_id":run_id,
                  "seed":experiment.seed,"tick":experiment.tick,"created":datetime.now(timezone.utc).isoformat(),
                  "graph_hash":experiment._graph_hash,"state_hash":state_hash(experiment),
                  "state_sha256":hashlib.sha256(meta).hexdigest(),
                  "arrays_sha256":hashlib.sha256(blob).hexdigest()}
        target=self.path/(identifier+".twins")
        partial=target.with_suffix(".partial")
        with partial.open("wb") as handle:
            with zipfile.ZipFile(handle,"w",compression=zipfile.ZIP_STORED) as bundle:
                bundle.writestr("manifest.json",canonical(manifest))
                bundle.writestr("state.json",meta)
                bundle.writestr("arrays.npz",blob)
            handle.flush();os.fsync(handle.fileno())
        self.read_file(partial) # Validate all checksums before replacing.
        os.replace(partial,target)
        return manifest

    @staticmethod
    def read_file(path):
        with zipfile.ZipFile(path) as bundle:
            if set(bundle.namelist())!={"manifest.json","state.json","arrays.npz"}:
                raise ValueError("Invalid checkpoint members")
            manifest=json.loads(bundle.read("manifest.json"))
            meta,blob=bundle.read("state.json"),bundle.read("arrays.npz")
            if manifest.get("schema")!=1: raise ValueError("Unsupported checkpoint schema")
            if hashlib.sha256(meta).hexdigest()!=manifest["state_sha256"] or hashlib.sha256(blob).hexdigest()!=manifest["arrays_sha256"]:
                raise ValueError("Checkpoint checksum mismatch")
            with np.load(io.BytesIO(blob),allow_pickle=False) as archive:
                arrays={key:archive[key].copy() for key in archive.files}
            return manifest,json.loads(meta),arrays

    def file(self,identifier):
        if not re.fullmatch(r"(autosave|[a-f0-9]{16})",identifier): raise ValueError("Invalid checkpoint ID")
        path=self.path/(identifier+".twins")
        if not path.is_file(): raise ValueError("Checkpoint not found")
        return path

    def restore(self,identifier,factory):
        manifest,state,arrays=self.read_file(self.file(identifier))
        experiment=factory(seed=manifest["seed"])
        if experiment._graph_hash!=manifest["graph_hash"]: raise ValueError("Checkpoint dataset does not match")
        def decode(value):
            if isinstance(value,list): return [decode(x) for x in value]
            if isinstance(value,dict):
                if "__array__" in value: return arrays[value["__array__"]].copy()
                if "__deque__" in value: return deque((decode(x) for x in value["__deque__"]),maxlen=value["maxlen"])
                return {k:decode(v) for k,v in value.items()}
            return value
        engine=decode(state["engine"])
        if set(engine)&EXCLUDED: raise ValueError("Checkpoint contains protected engine fields")
        for key,value in engine.items(): setattr(experiment,key,value)
        for a,saved,rng in zip(experiment.agents,state["agents"],state["agent_rng"]):
            values=decode(saved)
            for name in ("voltage","spikes","trace","refractory"):
                if values[name].shape!=(experiment.n,): raise ValueError("Neural array shape mismatch")
            for key,value in values.items(): setattr(a,key,value)
            a.rng.bit_generator.state=decode(rng)
        experiment.rng.bit_generator.state=decode(state["rng"])
        if state["world"] is not None:
            for key,value in decode(state["world"]).items(): setattr(experiment.world,key,value)
            experiment.world.rng.bit_generator.state=decode(state["world_rng"])
        if state_hash(experiment)!=manifest["state_hash"]: raise ValueError("Restored state hash mismatch")
        return experiment,manifest

    def list(self):
        result=[]
        for path in self.path.glob("*.twins"):
            try:
                with zipfile.ZipFile(path) as z: result.append(json.loads(z.read("manifest.json")))
            except (OSError,ValueError,zipfile.BadZipFile): continue
        return sorted(result,key=lambda x:x["created"],reverse=True)
