"""Exercise the full real dataset through the same runtime used by the console.

All frames/trials remain in the local run archive; a compact report is written
for review. This does not replace the independently scoped unit tests.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twins.connectome import load_connectome
from twins.engine import Experiment, PHASE_LENGTHS
from twins.server import Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/full-run.json"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    start = time.perf_counter()
    graph = load_connectome()
    runtime = Runtime(lambda seed: Experiment(seed=args.seed, graph=graph), Path("data/runs"), worker=False)
    initial = runtime.state()
    report = {"scope": "Full real graph, six-phase protocol, same Runtime/storage as the console",
              "seed": args.seed, "run_id": runtime.run_id,
              "neurons": graph.n_neurons, "edges": graph.n_edges,
              "graph_hash": graph.fingerprint,
              "initial_equal": initial["topology"]["initial_states_identical"],
              "initial_divergence": initial["metrics"]["divergence"], "checkpoints": []}
    try:
        for _ in range(sum(PHASE_LENGTHS.values())):
            runtime.step()
            tick = runtime.engine.tick
            if tick % 50 == 0:
                state = runtime.state()
                checkpoint = {"tick": tick, "phase": state["phase"], "metrics": state["metrics"],
                    "spike_rates": [agent["spike_rate"] for agent in state["twins"]],
                    "recognition": [agent["recognition"] for agent in state["twins"]],
                    "wall_ms": state["tick_wall_ms"]}
                report["checkpoints"].append(checkpoint)
                print(json.dumps({"tick": tick, "phase": state["phase"],
                    "accuracy": state["metrics"]["communication_accuracy"],
                    "divergence": state["metrics"]["divergence"]}), flush=True)
        final = runtime.state()
        report.update({"completed": final["protocol"]["completed"],
                       "neural_ms": final["neural_ms"], "final_metrics": final["metrics"],
                       "elapsed_seconds": round(time.perf_counter() - start, 3)})
        runtime.persist(runtime.engine.snapshot(), force=True)
        bundle = runtime.store.export(runtime.run_id)
        report["recorded_trials"] = len(bundle["trials"])
        report["recorded_frames"] = len(bundle["snapshots"])
        report["recorded_events"] = len(bundle["events"])
        assert report["initial_equal"] and report["initial_divergence"] == 0
        assert report["checkpoints"][0]["metrics"]["state_distance"] == 0
        assert report["completed"]
        assert final["metrics"]["trial_count"] > 0
        assert report["recorded_trials"] >= final["metrics"]["trial_count"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Verified full protocol. Archive: {runtime.run_id}. Report: {args.output}", flush=True)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
