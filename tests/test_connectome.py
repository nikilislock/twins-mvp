"""Data orientation, integrity and exact identifier preservation regressions."""

import csv
import hashlib

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from scipy import sparse

from twins.connectome import Graph, load_connectome, verify_asset


@pytest.fixture
def data_dir(tmp_path):
    with (tmp_path / "2025_Completeness_783.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["", "Completed"])
        writer.writerows([["720575940596125868", True], ["720575940597856265", True], ["720575940597944841", True]])
    pq.write_table(pa.table({"Presynaptic_Index": [0, 0, 1, 2], "Postsynaptic_Index": [1, 1, 2, 0],
                             "Excitatory x Connectivity": [2., 3., -4., 1.]}), tmp_path / "2025_Connectivity_783.parquet")
    return tmp_path


def test_orientation_and_duplicate_aggregation(data_dir):
    graph = load_connectome(data_dir, verify=False)
    drive = graph.matrix @ np.array([1., 0., 0.])
    np.testing.assert_allclose(drive, [0., 5 * 0.275, 0.])
    assert graph.matrix[2, 1] == pytest.approx(-4 * 0.275)
    assert graph.n_neurons == 3 and graph.n_edges == 3
    assert graph.ids[0] == "720575940596125868"
    assert graph.metadata["graph_mode"] == "full"


def test_missing_real_data_never_falls_back_to_synthetic(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_data"):
        load_connectome(tmp_path)


def test_bad_indices_are_rejected(data_dir):
    pq.write_table(pa.table({"Presynaptic_Index": [3], "Postsynaptic_Index": [0], "Excitatory x Connectivity": [1.]}), data_dir / "2025_Connectivity_783.parquet")
    with pytest.raises(ValueError, match="outside"):
        load_connectome(data_dir, verify=False)


def test_integrity_detects_same_length_corruption(tmp_path):
    path = tmp_path / "example"
    path.write_bytes(b"abc")
    asset = {"bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
    verify_asset(path, asset)
    path.write_bytes(b"abd")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_asset(path, asset)


def test_optional_annotation_joins_exact_ids_and_converts_coordinates(data_dir):
    with (data_dir / "Supplemental_file1_neuron_annotations.tsv").open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["root_id", "pos_x", "pos_y", "pos_z", "cell_type", "cell_class", "flow", "super_class", "top_nt"])
        writer.writerow(["720575940596125868", 100, 200, 300, "KCg-m", "Kenyon_Cell", "intrinsic", "central", "acetylcholine"])
    graph = load_connectome(data_dir, verify=False)
    np.testing.assert_allclose(graph.positions[0], [0.4, 0.8, 12.])
    assert graph.labels[0] == "KCg-m"
    assert graph.metadata["annotated_neurons"] == 1
    assert np.isnan(graph.positions[1]).all()


def test_explicit_crop_is_deterministic_and_labelled(data_dir):
    first = load_connectome(data_dir, max_neurons=2, verify=False)
    second = load_connectome(data_dir, max_neurons=2, verify=False)
    assert first.fingerprint == second.fingerprint
    assert first.n_neurons == 2
    assert first.metadata["original_neurons"] == 3
    assert "subgraph" in first.metadata["graph_mode"]
    assert first.metadata["synthetic"] is False


def test_fingerprint_changes_with_connection_not_annotation():
    a = Graph(np.array(["1", "2"]), sparse.csr_matrix([[0., 1.], [0., 0.]]))
    b = Graph(np.array(["1", "2"]), sparse.csr_matrix([[0., 2.], [0., 0.]]))
    c = Graph(np.array(["1", "2"]), sparse.csr_matrix([[0., 1.], [0., 0.]]), labels=["A", "B"])
    assert a.fingerprint != b.fingerprint
    assert a.fingerprint == c.fingerprint
