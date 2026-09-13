import json

import numpy as np
import pytest

from twins.engine import Experiment, benchmark_learning, synthetic_graph


@pytest.fixture
def experiment():
    return Experiment(graph=synthetic_graph(96), seed=42)


def test_initial_states_and_same_input_control_are_identical(experiment):
    assert experiment.initial_hashes[0] == experiment.initial_hashes[1]
    experiment.step(30)
    np.testing.assert_array_equal(experiment.agents[0].voltage, experiment.agents[1].voltage)
    np.testing.assert_array_equal(experiment.agents[0].spikes, experiment.agents[1].spikes)
    assert experiment.snapshot()["metrics"]["divergence"] == 0.


def test_seed_replays_identical_experiment(experiment):
    second = Experiment(graph=synthetic_graph(96), seed=42)
    experiment.step(75)
    second.step(75)
    assert experiment.snapshot() == second.snapshot()


def test_experience_diverges_and_recurrent_weights_stay_fixed(experiment):
    weights = experiment.matrix.data.copy()
    experiment.set_phase("familiarization")
    experiment.step(30)
    assert experiment.snapshot()["metrics"]["divergence"] > .01
    assert not np.array_equal(experiment.agents[0].voltage, experiment.agents[1].voltage)
    np.testing.assert_array_equal(weights, experiment.matrix.data)


def test_frozen_learning_leaves_parameters_unchanged(experiment):
    experiment.command("plasticity", enabled=False)
    initial = [(agent.familiarity.copy(), agent.sender.copy(), agent.receiver.copy()) for agent in experiment.agents]
    experiment.set_phase("familiarization")
    experiment.step(30)
    experiment.set_phase("communication")
    experiment.step(30)
    for agent, arrays in zip(experiment.agents, initial):
        for actual, expected in zip((agent.familiarity, agent.sender, agent.receiver), arrays):
            np.testing.assert_array_equal(actual, expected)


def test_partner_association_generalizes_but_cannot_distinguish_identical_cues(experiment):
    experiment.set_phase("familiarization")
    experiment.step(250)
    for twin in experiment.snapshot()["twins"]:
        assert twin["recognition"]["partner"] > twin["recognition"]["novel"] + .35
        assert twin["recognition"]["partner"] == twin["recognition"]["identical_cue"]
    experiment.set_phase("recognition")
    before = [agent.familiarity.copy() for agent in experiment.agents]
    experiment.step(90)
    assert experiment.snapshot()["metrics"]["recognition_accuracy"] > .85
    for agent, initial in zip(experiment.agents, before):
        np.testing.assert_array_equal(agent.familiarity, initial)


def test_signalling_learning_and_random_channel_control():
    report = benchmark_learning(seeds=(11, 42, 73), ticks=600)
    assert report["means"]["plastic"] > .5
    assert abs(report["means"]["frozen"] - .25) < .02
    assert abs(report["means"]["shuffled"] - .25) < 1e-12


def test_no_receiver_context_leak_and_shuffle_exact_chance(experiment):
    experiment.step(40)
    experiment.agents[0].sender[:] = np.eye(4) * 8
    experiment.agents[1].receiver[:] = np.eye(4) * 8
    # The measured neural gate softens these aligned parameter tables.
    assert experiment.communication_evaluation()["directional_accuracy"][0] > .9
    expected = np.trace(experiment._policy(experiment.agents[0], "sender") @
                        experiment._policy(experiment.agents[1], "receiver")) / 4
    assert experiment.communication_evaluation()["directional_accuracy"][0] == pytest.approx(expected)
    experiment.command("shuffle_signals", enabled=True)
    assert abs(experiment.communication_evaluation()["expected_accuracy"] - .25) < 1e-12


def test_protocol_completes_and_json_has_no_nan(experiment):
    snapshot = experiment.step(1400)
    assert snapshot["protocol"]["completed"]
    assert snapshot["tick"] == 1300
    assert snapshot["neural_ms"] == 5200.
    json.dumps(snapshot, allow_nan=False)


def test_separation_confines_bodies(experiment):
    experiment.set_phase("separation")
    experiment.step(50)
    assert experiment.agents[0].x <= .46
    assert experiment.agents[1].x >= .54


def test_inspector_uses_real_edge_orientation(experiment):
    node = experiment.inspect_neuron(5)
    assert node["incoming_count"] == experiment.matrix.getrow(5).nnz
    assert node["outgoing_count"] == experiment.matrix.getcol(5).nnz
    assert experiment.inspect_neuron("test-5")["index"] == 5
    with pytest.raises(ValueError):
        experiment.inspect_neuron("not-a-node")


def test_reset_replays_initial_state(experiment):
    original = experiment.snapshot()
    experiment.step(60)
    experiment.command("reset", seed=42)
    assert original == experiment.snapshot()


def test_unknown_interventions_are_rejected(experiment):
    with pytest.raises(ValueError):
        experiment.command("execute_shell")
    with pytest.raises(ValueError):
        experiment.set_phase("love")


def test_recurrent_connectivity_causally_changes_neural_activity():
    graph = synthetic_graph(96)
    ablated = synthetic_graph(96)
    ablated.matrix.data[:] = 0
    connected_experiment = Experiment(graph=graph)
    ablated_experiment = Experiment(graph=ablated)
    connected_experiment.step(40)
    ablated_experiment.step(40)
    assert not np.array_equal(connected_experiment.agents[0].voltage, ablated_experiment.agents[0].voltage)
    assert connected_experiment.agents[0].total_spikes != ablated_experiment.agents[0].total_spikes


def test_silencing_disables_neural_output_learning_and_motor_drive(experiment):
    experiment.set_phase("communication")
    experiment.step(30)
    assert all(agent.neural_gate > 0 for agent in experiment.agents)
    initial = [(agent.sender.copy(), agent.receiver.copy(), agent.x, agent.y) for agent in experiment.agents]
    experiment.command("silence", enabled=True)
    assert experiment.communication_evaluation()["expected_accuracy"] == .25
    experiment.step(10)
    for agent, (sender, receiver, x, y) in zip(experiment.agents, initial):
        assert agent.neural_gate == 0.
        assert not agent.spikes.any()
        assert not agent.trace.any()
        np.testing.assert_array_equal(agent.sender, sender)
        np.testing.assert_array_equal(agent.receiver, receiver)
        assert agent.x == x and agent.y == y
    experiment.command("silence", enabled=False)
    experiment.step(10)
    assert all(agent.neural_gate > 0 for agent in experiment.agents)


def test_every_trial_is_drained_exactly_once(experiment):
    experiment.set_phase("familiarization")
    experiment.step(3)
    trials = experiment.drain_trials()
    assert len(trials) == 6
    assert all(record["type"] == "familiarization" and "neural_gate" in record for record in trials)
    assert experiment.drain_trials() == []
    experiment.set_phase("recognition")
    experiment.step(3)
    trials = experiment.drain_trials()
    assert len(trials) == 6
    assert all(record["effective_learning_rate"] == 0 for record in trials)
    experiment.set_phase("communication")
    experiment.step(3)
    trials = experiment.drain_trials()
    assert len(trials) == 24
    assert all(record["type"] == "signal" and "sender_gate" in record for record in trials)
    json.dumps(trials, allow_nan=False)


def test_actual_neural_trace_state_changes_policy(experiment):
    agent = experiment.agents[0]
    agent.sender[:] = np.eye(4) * 5
    before = experiment._policy(agent, "sender").copy()
    agent.trace[:] = .7
    agent.trace[experiment.ports["readout"][0]] = 3.
    experiment._update_neural_readout(agent)
    after = experiment._policy(agent, "sender")
    assert not np.allclose(before, after)
    assert agent.neural_gate > .5


def test_reunion_probes_are_balanced_and_have_no_training_update(experiment):
    experiment.set_phase("reunion")
    experiment.step(8)
    trials = experiment.drain_trials()
    probes = [trial for trial in trials if trial["type"] == "recognition"]
    assert sum(trial["partner_cue"] for trial in probes) == len(probes) / 2
    assert all(trial["effective_learning_rate"] == 0 for trial in probes)
