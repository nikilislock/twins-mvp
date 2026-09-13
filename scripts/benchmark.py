"""Small paired control experiment; explicitly uses synthetic neural fixtures."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twins.engine import benchmark_learning

if __name__ == "__main__":
    report = benchmark_learning(seeds=(11, 42, 73), ticks=600)
    target = Path("docs/benchmark.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"scope": report["scope"], "means": report["means"]}, indent=2))
