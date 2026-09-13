import json
from fastapi.testclient import TestClient
from twins.server import create_app
from twins.storage import RunStore


class Instrument:
    """An isolated instrument stub: API tests never download scientific data."""
    def __init__(self, seed=42):
        self.seed, self.tick = seed, 0
        self.phase = "baseline"
        self.plasticity = True

    def snapshot(self):
        return {"seed": self.seed, "tick": self.tick, "phase": self.phase,
                "topology": {"source": "test fixture"}, "history": [],
                "events": [{"tick": 0, "type": "created", "message": "initial state"}]}

    def step(self, n=1):
        self.tick += n
        return self.snapshot()

    def command(self, action, value=None):
        if action == "phase":
            self.phase = value
        elif action == "plasticity":
            self.plasticity = value

    def inspect_neuron(self, index):
        if index != 0:
            raise IndexError(index)
        return {"index": 0, "voltage": [0, 0]}


def client(tmp_path):
    return TestClient(create_app(factory=Instrument, directory=tmp_path, worker=False))


def test_control_export_and_replay_survive_restart(tmp_path):
    with client(tmp_path) as api:
        state = api.get("/api/state").json()
        run_id = state["run_id"]
        assert state["running"] is False
        for _ in range(7):
            assert api.post("/api/control", json={"action": "step"}).status_code == 200
        export = api.get("/api/export").json()
        assert export["run_id"] == run_id
        assert export["snapshots"][-1]["tick"] == 7
        assert len(export["events"]) == 1  # bounded event window cannot duplicate records
        assert len(export["actions"]) == 7
        assert api.get(f"/api/runs/{run_id}/state?tick=6").json()["tick"] == 6
        reset = api.post("/api/control", json={"action": "reset", "seed": 99}).json()
        assert reset["seed"] == 99 and reset["run_id"] != run_id
        assert len(api.get("/api/runs").json()) == 2
    with client(tmp_path) as api:
        old = api.get(f"/api/runs/{run_id}/export").json()
        assert old["snapshots"][-1]["tick"] == 7


def test_input_validation_and_origin_boundary(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/api/control", json={"action": "shell", "value": "echo bad"}).status_code == 422
        assert api.post("/api/control", json={"action": "plasticity", "value": "false"}).status_code == 422
        assert api.post("/api/control", json={"action": "speed", "value": 9999}).status_code == 422
        assert api.post("/api/control", json={"action": "reset", "seed": -1}).status_code == 422
        assert api.post("/api/control", json={"action": "phase", "value": "anything"}).status_code == 422
        assert api.post("/api/control", json={"action": "run"},
                        headers={"Origin": "https://unrelated.example"}).status_code == 403
        assert api.get("/api/state", headers={"Host": "unrelated.example"}).status_code == 403
        assert api.get("/api/neurons/0").status_code == 200
        assert api.get("/api/neurons/-1").status_code == 404
        assert api.get("/api/runs/unknown/export").status_code == 404
        assert api.get("/api/runs/unknown/state").status_code == 404


def test_sql_storage_uses_bound_parameters(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3")
    run_id = store.create({"seed": 1})
    store.record(run_id, {"tick": 0, "value": "' DROP TABLE runs; --"})
    assert len(store.list()) == 1
    assert store.frame(run_id, 100)["value"].startswith("'")
    json.dumps(store.export(run_id), allow_nan=False)
    store.close()


def test_trial_archive_and_replay_history(tmp_path):
    store = RunStore(tmp_path / "trial-archive.sqlite3")
    run_id = store.create({"seed": 5})
    for tick in (0, 5, 10):
        store.record(run_id, {"tick": tick, "phase": "communication",
            "metrics": {"divergence": tick / 10}, "twins": [{"spike_rate": tick}, {"spike_rate": tick + 1}]})
    store.trials(run_id, [{"tick": 3, "context": 0, "symbol": 2, "reward": 1}])
    store.event(run_id, {"tick": 5, "message": "visible"})
    store.event(run_id, {"tick": 10, "message": "future"})
    replay = store.frame(run_id, 7)
    assert replay["tick"] == 5
    assert [item["tick"] for item in replay["history"]] == [0, 5]
    assert [item["message"] for item in replay["events"]] == ["visible"]
    assert replay["running"] is False
    assert len(store.export(run_id)["trials"]) == 1
    store.close()
