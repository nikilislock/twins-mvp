"""Download fixed public research assets; never execute upstream repository code."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twins.connectome import ASSETS, DEFAULT_DATA_DIR, EON_COMMIT, ANNOTATIONS_COMMIT, verify_asset


def fetch(directory: Path, include_annotations: bool = True) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"source_commit": EON_COMMIT, "annotation_commit": ANNOTATIONS_COMMIT,
                "data_license": "CC-BY-NC-4.0", "assets": {}}
    for filename, asset in ASSETS.items():
        if not asset["required"] and not include_annotations:
            continue
        destination = directory / filename
        if destination.exists():
            digest = verify_asset(destination, asset)
            print(f"Verified {filename}", flush=True)
        else:
            temporary = destination.with_name(destination.name + ".part")
            print(f"Downloading {filename} ({asset['bytes'] / 1_000_000:.1f} MB)", flush=True)
            request = urllib.request.Request(asset["url"], headers={"User-Agent": "The-Twins-research-data-fetch/1.0"})
            digest_state = hashlib.sha256()
            size = 0
            try:
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as handle:
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        handle.write(chunk)
                        digest_state.update(chunk)
                        size += len(chunk)
                        if size > asset["bytes"]:
                            raise ValueError(f"{filename} exceeds its pinned byte size.")
                digest = digest_state.hexdigest()
                if size != asset["bytes"] or digest != asset["sha256"]:
                    raise ValueError(f"Integrity check failed for {filename}; final cache was not changed.")
                temporary.replace(destination)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            print(f"Verified {filename}: {digest}", flush=True)
        manifest["assets"][filename] = {"url": asset["url"], "bytes": asset["bytes"], "sha256": digest}
    manifest_path = directory / "provenance.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch the pinned real FlyWire-derived graph and anatomical annotations.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--without-annotations", action="store_true", help="Download only connectivity; anatomical positions will be unavailable.")
    args = parser.parse_args()
    fetch(args.data_dir, include_annotations=not args.without_annotations)
    print("Ready. FlyWire research data retains CC BY-NC 4.0; see docs/SOURCES.md.")


if __name__ == "__main__":
    main()
