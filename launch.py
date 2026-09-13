"""Portable first-run setup and local launch: python launch.py."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="The Twins — local research console")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required.")
    url = f"http://127.0.0.1:{args.port}"
    try:
        with urllib.request.urlopen(url + "/api/meta", timeout=2) as response:
            active = json.load(response)
        if active.get("local_only") and active.get("model") == "Custom LIF + engineered associative readouts":
            print(f"The Twins is already running: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return 0
    except (OSError, ValueError):
        pass
    interpreter = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.exists():
        print("Preparing the isolated Python environment...", flush=True)
        venv.create(ROOT / ".venv", with_pip=True)
    verify_environment = """from importlib.metadata import version
from pathlib import Path
import sys
import numpy,scipy,pyarrow,fastapi,uvicorn
for line in Path(sys.argv[1]).read_text().splitlines():
    if line.strip() and not line.startswith('#'):
        name, pinned = line.split('==')
        if version(name) != pinned:
            raise SystemExit(1)
"""
    check = subprocess.run([str(interpreter), "-c", verify_environment, str(ROOT / "requirements.lock")],
                           cwd=ROOT, capture_output=True)
    if check.returncode:
        subprocess.check_call([str(interpreter), "-m", "pip", "install", "-r", "requirements.lock"], cwd=ROOT)
    subprocess.check_call([str(interpreter), "scripts/fetch_data.py"], cwd=ROOT)
    print(f"\nTHE TWINS\n{url}\nKeep this window open. Ctrl+C stops the application.\n", flush=True)

    def open_when_ready():
        for _ in range(120):
            try:
                with urllib.request.urlopen(url + "/api/meta", timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except OSError:
                time.sleep(1)

    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        return subprocess.call([str(interpreter), "-m", "twins", "--port", str(args.port)], cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
