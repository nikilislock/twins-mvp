"""Load the pinned FlyWire-derived Eon graph without downloading or executing code.

Matrix convention is postsynaptic row, presynaptic column; values are mV.
The optional annotation table supplies real anchor positions, not neuron meshes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from scipy import sparse


EON_COMMIT = "a3db62f9436074e485c0278290c2164ed6150808"
ANNOTATIONS_COMMIT = "8587524c1748ce5ef2080822a2fc890fc03bf597"
DATA_LICENSE = "CC-BY-NC-4.0"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "flywire"
SYNAPSE_SCALE_MV = 0.275

ASSETS: dict[str, dict[str, Any]] = {
    "2025_Completeness_783.csv": {
        "url": f"https://raw.githubusercontent.com/eonsystemspbc/fly-brain/{EON_COMMIT}/data/2025_Completeness_783.csv",
        "bytes": 3465987,
        "sha256": "52b0ac6094cd32c546f8d4c341e094376f48f4e791f8db9b166de5dff8199ea4",
        "required": True,
    },
    "2025_Connectivity_783.parquet": {
        "url": f"https://raw.githubusercontent.com/eonsystemspbc/fly-brain/{EON_COMMIT}/data/2025_Connectivity_783.parquet",
        "bytes": 100804642,
        "sha256": "efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347",
        "required": True,
    },
    "Supplemental_file1_neuron_annotations.tsv": {
        "url": f"https://raw.githubusercontent.com/flyconnectome/flywire_annotations/{ANNOTATIONS_COMMIT}/supplemental_files/Supplemental_file1_neuron_annotations.tsv",
        "bytes": 31718505,
        "sha256": "9a4f8b2f843196074431ebd7cd883536afa1be86c8a4ce90970441e8be81d1be",
        "required": False,
    },
}


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_asset(path: str | Path, asset: dict[str, Any]) -> str:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path.name}. Run: python scripts/fetch_data.py")
    if path.stat().st_size != asset["bytes"]:
        raise ValueError(f"Size mismatch for {path.name}; expected {asset['bytes']} bytes.")
    digest = file_sha256(path)
    if digest != asset["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {path.name}; cached data is not the pinned release.")
    return digest


@dataclass
class Graph:
    ids: np.ndarray
    matrix: sparse.csr_matrix
    labels: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    positions: np.ndarray | None = None
    classes: list[str] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    neurotransmitters: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ids = np.asarray(self.ids, dtype=str)
        self.matrix = sparse.csr_matrix(self.matrix, dtype=np.float32)
        self.matrix.sum_duplicates()
        self.matrix.eliminate_zeros()
        self.matrix.sort_indices()
        n = len(self.ids)
        if self.matrix.shape != (n, n):
            raise ValueError("The connectivity matrix dimensions must match neuron IDs.")
        if len(set(self.ids)) != n:
            raise ValueError("Neuron IDs must be unique.")
        if not np.isfinite(self.matrix.data).all():
            raise ValueError("Connection weights must be finite.")
        for name, default in (("labels", ""), ("regions", "unannotated"), ("classes", "unannotated"), ("flows", "unknown"), ("neurotransmitters", "unknown")):
            value = getattr(self, name)
            if not value:
                setattr(self, name, list(self.ids) if name == "labels" else [default] * n)
            elif len(value) != n:
                raise ValueError(f"{name} must contain one value per neuron.")
        if self.positions is None:
            self.positions = np.full((n, 3), np.nan, dtype=np.float32)
        self.positions = np.asarray(self.positions, dtype=np.float32)
        if self.positions.shape != (n, 3):
            raise ValueError("Positions must have shape (neuron count, 3).")

    @property
    def n_neurons(self) -> int:
        return len(self.ids)

    @property
    def n_edges(self) -> int:
        return self.matrix.nnz

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update("\n".join(self.ids).encode("ascii"))
        for values, dtype in ((self.matrix.indptr, "<i8"), (self.matrix.indices, "<i8"), (self.matrix.data, "<f4")):
            digest.update(values.astype(dtype, copy=False).tobytes())
        return digest.hexdigest()


def _read_ids(path: Path) -> np.ndarray:
    # Root IDs exceed JavaScript's exact integer range; keep decimal strings.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader)
        ids = [row[0] for row in reader if row]
    if not ids or any(not root_id.isdecimal() for root_id in ids):
        raise ValueError("Completeness CSV must have decimal FlyWire IDs in its first column.")
    return np.asarray(ids, dtype=str)


def _annotations(path: Path, ids: np.ndarray) -> dict[str, Any]:
    n = len(ids)
    index = {root_id: i for i, root_id in enumerate(ids)}
    result: dict[str, Any] = {
        "labels": list(ids), "regions": ["unannotated"] * n,
        "classes": ["unannotated"] * n, "flows": ["unknown"] * n,
        "neurotransmitters": ["unknown"] * n,
        "positions": np.full((n, 3), np.nan, dtype=np.float32),
    }
    matched = 0
    if path.is_file():
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                i = index.get(row.get("root_id", ""))
                if i is None:
                    continue
                matched += 1
                result["labels"][i] = row.get("cell_type") or row.get("hemibrain_type") or row.get("cell_class") or str(ids[i])
                result["regions"][i] = row.get("super_class") or "unannotated"
                result["classes"][i] = row.get("cell_class") or "unannotated"
                result["flows"][i] = row.get("flow") or "unknown"
                result["neurotransmitters"][i] = row.get("top_nt") or "unknown"
                try:
                    # Source anchor voxels: 4 x 4 x 40 nm. Output: micrometres.
                    position = [float(row[f"pos_{axis}"]) for axis in "xyz"]
                    result["positions"][i] = np.asarray(position) * [0.004, 0.004, 0.04]
                except (KeyError, TypeError, ValueError):
                    pass
    result["matched"] = matched
    return result


def load_connectome(data_dir: str | Path | None = None, max_neurons: int | None = None, *, verify: bool = True) -> Graph:
    """Read the full real graph; optional crop is explicit and recorded in metadata.

    ``verify=False`` exists for externally supplied research fixtures and tests.
    The production server should retain the default checksum verification.
    The reduced mode selects neurons with greatest total absolute incident weight
    and retains only their actual induced edges; it cannot emulate the whole brain.
    """
    directory = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    asset_hashes = {}
    for filename, asset in ASSETS.items():
        path = directory / filename
        if asset["required"] or path.exists():
            if verify:
                asset_hashes[filename] = verify_asset(path, asset)
            elif not path.is_file():
                raise FileNotFoundError(f"Missing {filename}. Run: python scripts/fetch_data.py")
    ids = _read_ids(directory / "2025_Completeness_783.csv")
    n = len(ids)
    columns = ["Presynaptic_Index", "Postsynaptic_Index", "Excitatory x Connectivity"]
    table = pq.read_table(directory / "2025_Connectivity_783.parquet", columns=columns)
    pre = table[columns[0]].to_numpy().astype(np.int64, copy=False)
    post = table[columns[1]].to_numpy().astype(np.int64, copy=False)
    counts = table[columns[2]].to_numpy().astype(np.float32, copy=False)
    if np.any(pre < 0) or np.any(post < 0) or np.any(pre >= n) or np.any(post >= n):
        raise ValueError("Connectivity indices are outside the completeness ID table.")
    if not np.isfinite(counts).all():
        raise ValueError("Signed connectivity contains non-finite values.")
    raw_rows = len(pre)
    raw_count_sum = float(np.abs(counts).sum(dtype=np.float64))
    matrix = sparse.coo_matrix((counts * SYNAPSE_SCALE_MV, (post, pre)), shape=(n, n), dtype=np.float32).tocsr()
    matrix.sum_duplicates()
    matrix.eliminate_zeros()
    annotation = _annotations(directory / "Supplemental_file1_neuron_annotations.tsv", ids)
    matched = annotation.pop("matched")
    metadata = {
        "source": "FlyWire FAFB v783, Eon Systems 2025 model export",
        "source_url": "https://github.com/eonsystemspbc/fly-brain",
        "source_commit": EON_COMMIT,
        "annotation_commit": ANNOTATIONS_COMMIT if matched else None,
        "data_license": DATA_LICENSE,
        "license_url": "https://flywire.ai/guidelines",
        "original_neurons": n, "source_connection_rows": raw_rows,
        "signed_count_absolute_sum": raw_count_sum,
        "full_graph_edges": int(matrix.nnz), "synapse_scale_mv": SYNAPSE_SCALE_MV,
        "matrix_orientation": "postsynaptic rows, presynaptic columns",
        "position_units": "micrometres", "position_kind": "annotated anchor; not mesh, soma, or measured activity",
        "annotated_neurons": matched, "graph_mode": "full", "synthetic": False,
        "asset_sha256": asset_hashes,
        "limitations": "Static reconstructed connectivity; predicted signs; engineered sensory and readout interface.",
    }
    if max_neurons is not None:
        if not isinstance(max_neurons, int) or isinstance(max_neurons, bool) or max_neurons < 2:
            raise ValueError("max_neurons must be an integer of at least 2, or None.")
        if max_neurons < n:
            strength = np.asarray(abs(matrix).sum(axis=0)).ravel() + np.asarray(abs(matrix).sum(axis=1)).ravel()
            selected = np.sort(np.lexsort((np.arange(n), -strength))[:max_neurons])
            matrix = matrix[selected][:, selected].tocsr()
            ids = ids[selected]
            for key, values in annotation.items():
                annotation[key] = values[selected] if isinstance(values, np.ndarray) else [values[i] for i in selected]
            metadata["graph_mode"] = "explicit strongest-neuron induced subgraph"
            metadata["selection"] = "stable descending absolute incident weight; no invented edges"
    graph = Graph(ids=ids, matrix=matrix, metadata=metadata, **annotation)
    graph.metadata["neurons"] = graph.n_neurons
    graph.metadata["edges"] = graph.n_edges
    graph.metadata["fingerprint"] = graph.fingerprint
    return graph
