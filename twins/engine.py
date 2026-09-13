"""Reproducible experimental harness around two identical sparse LIF networks.

The recurrent graph is real when loaded by ``load_connectome``. Sensory ports,
motor readouts, cue features and reward learning are explicitly engineered. One
episode tick runs four 1-ms neural integration steps; it is not a second of fly
life. No language model, scripted dialogue, emotion state or hidden controller is
used. The synthetic graph constructor is only an explicit test fixture.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import math
from typing import Any

import numpy as np
from scipy import sparse


PHASES = ("baseline", "familiarization", "recognition", "communication", "separation", "reunion")
PHASE_LENGTHS = dict(zip(PHASES, (50, 250, 100, 600, 150, 150)))
SYMBOLS = ("●", "▲", "■", "◆")
DT_MS = 1.0
NEURAL_STEPS_PER_TICK = 4
SIGNAL_TRIALS_PER_TICK = 8


def _softmax(x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(x, dtype=np.float64) / temperature
    e = np.exp(z - np.max(z, axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def _digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(np.asarray(array).tobytes())
    return digest.hexdigest()


@dataclass
class _FixtureGraph:
    ids: np.ndarray
    matrix: sparse.csr_matrix
    labels: list[str]
    regions: list[str]
    metadata: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        return _digest(self.matrix.data, self.matrix.indices, self.matrix.indptr)


def synthetic_graph(n: int = 128, seed: int = 12) -> _FixtureGraph:
    """Explicit synthetic test fixture. Never a fallback for unavailable data."""
    if n < 16:
        raise ValueError("A test graph needs at least 16 neurons")
    rng = np.random.default_rng(seed)
    rows = rng.integers(0, n, n * 9)
    cols = rng.integers(0, n, n * 9)
    sign = np.where(rng.random(n) < .2, -1., 1.)
    values = (rng.uniform(.1, .8, n * 9) * sign[cols]).astype(np.float32)
    matrix = sparse.coo_matrix((values, (rows, cols)), shape=(n, n)).tocsr()
    ids = np.array([f"test-{i}" for i in range(n)])
    return _FixtureGraph(ids, matrix, ids.tolist(), ["unannotated"] * n,
                         {"source": "SYNTHETIC TEST FIXTURE", "synthetic": True,
                          "data_mode": "synthetic-test", "license": "MIT"})


class Twin:
    """An independent copy of neural and learned state; identical initial seed."""

    def __init__(self, n: int, seed: int):
        self.rng = np.random.default_rng(seed)
        self.voltage = self.rng.uniform(-52., -48., n).astype(np.float32)
        self.spikes = np.zeros(n, dtype=bool)
        self.refractory = np.zeros(n, dtype=np.int8)
        self.trace = np.zeros(n, dtype=np.float32)
        self.step_spike_counts = np.zeros(n, dtype=np.uint8)
        self.familiarity = np.zeros(32, dtype=np.float64)
        self.eligibility = np.zeros(32, dtype=np.float64)
        # A small, identical random symmetry break contains no symbol semantics.
        self.sender = self.rng.normal(0., .02, (4, 4))
        self.receiver = self.rng.normal(0., .02, (4, 4))
        self.sender_baseline = np.zeros(4)
        self.receiver_baseline = np.zeros(4)
        self.spike_count = 0
        self.spike_rate = 0.
        self.total_spikes = 0
        self.neural_gate = 0.
        self.neural_bias = np.zeros(4, dtype=np.float64)
        self.neural_features = np.ones(32, dtype=np.float64)
        self.neural_readout = np.zeros(32, dtype=np.float64)
        self.x, self.y, self.heading, self.energy = .5, .5, 0., .75
        self.trail: deque[dict[str, float]] = deque(maxlen=100)

    def initial_hash(self) -> str:
        return _digest(self.voltage, self.spikes, self.refractory, self.trace,
                       self.familiarity, self.eligibility, self.sender, self.receiver)


class Experiment:
    """A local-only simulation with explicit experimental interventions.

    ``graph=None`` loads the real, downloaded connectome and raises a useful
    exception when it is unavailable. Pass ``synthetic_graph()`` explicitly for
    tests. Public methods return JSON-safe dictionaries.
    """

    def __init__(self, seed: int = 42, plasticity: bool = True, graph=None):
        if graph is None:
            from .connectome import load_connectome
            graph = load_connectome()
        self.graph = graph
        self.matrix = sparse.csr_matrix(graph.matrix, dtype=np.float32)
        self.n = self.matrix.shape[0]
        if self.n < 16 or self.matrix.shape != (self.n, self.n):
            raise ValueError("Connectome must be a square graph with at least 16 neurons")
        if not np.isfinite(self.matrix.data).all():
            raise ValueError("Connectome contains non-finite synaptic weights")
        self.seed = int(seed)
        self.plasticity = bool(plasticity)
        self.shuffle_signals = False
        self.neural_silenced = False
        self.automatic = True
        self.completed = False
        self.tick = 0
        self.phase = "baseline"
        self.phase_tick = 0
        self.rng = np.random.default_rng(self.seed + 2001)
        self.agents = [Twin(self.n, self.seed), Twin(self.n, self.seed)]
        self.initial_hashes = [a.initial_hash() for a in self.agents]
        self.agents[0].x, self.agents[0].heading = .30, .15
        self.agents[1].x, self.agents[1].heading = .70, math.pi + .15
        self.ports = self._make_ports()
        self.background = np.zeros(self.n, dtype=np.float32)
        self.background[self.ports["background"]] = 8.5
        self.sample_indices = self._make_sample()
        self._sample_xy = self._make_sample_geometry()
        sample_matrix = self.matrix[self.sample_indices][:, self.sample_indices].tocoo()
        self._sample_edges = [{"source": int(self.sample_indices[column]),
                               "target": int(self.sample_indices[row]), "weight_mv": float(weight)}
                              for row, column, weight in zip(sample_matrix.row, sample_matrix.col, sample_matrix.data)]
        regions = np.asarray(self.graph.regions)
        self._regions = {str(region): np.flatnonzero(regions == region) for region in np.unique(regions)}
        self._id_lookup: dict[str, int] | None = None
        self._outgoing = None
        self._graph_hash = str(getattr(graph, "fingerprint", "")) or _digest(
            self.matrix.data, self.matrix.indices, self.matrix.indptr)
        self._cue_projection = np.random.default_rng(715).normal(0., 1., (32, 8))
        cue_rng = np.random.default_rng(901)
        self.cues = cue_rng.normal(0., 1., (3, 8))
        self.cues /= np.linalg.norm(self.cues, axis=1, keepdims=True)
        self.recognition_results: deque[int] = deque(maxlen=400)
        self.signal_results: deque[int] = deque(maxlen=400)
        self.all_signal_trials = 0
        self.all_recognition_trials = 0
        self.signal_correct = 0
        self.reward_total = 0.
        self.confusion = np.zeros((4, 4), dtype=np.int64)
        self.symbol_counts = np.zeros((4, 4), dtype=np.int64)
        self.last_trial: dict[str, Any] | None = None
        self._pending_trials: list[dict[str, Any]] = []
        self._presentations: list[dict[str, Any] | None] = [None, None]
        self.events: deque[dict[str, Any]] = deque(maxlen=80)
        self.history: deque[dict[str, Any]] = deque(maxlen=360)
        self._event_id = 0
        self._event("initialization", "Two independent neural and learning states share the same initial hash.")
        self._event("provenance", "Real connectome topology; engineered sensory ports, readouts and external reward learning."
                    if not graph.metadata.get("synthetic", False) else "Explicit synthetic test graph: no FlyWire data in this run.")

    def _make_ports(self) -> dict[str, Any]:
        rng = np.random.default_rng(self.seed + 777)
        # Real sensory/descending classes when annotated. Their experimental
        # meaning and wiring remain invented, even when cell class is known.
        regions = np.asarray(self.graph.regions)
        sensory_pool = np.flatnonzero(regions == "sensory")
        motor_pool = np.flatnonzero(regions == "descending")
        classes = np.asarray(getattr(self.graph, "classes", ["unannotated"] * self.n))
        memory_pool = np.flatnonzero(classes == "Kenyon_Cell")
        if len(sensory_pool) < 32:
            sensory_pool = np.arange(self.n)
        if len(motor_pool) < 16:
            motor_pool = np.arange(self.n)
        if len(memory_pool) < 32:
            memory_pool = np.arange(self.n)
        width = max(2, min(128, self.n // 64))
        motor_width = min(256, max(4, len(motor_pool) // 4))
        return {"sensory": [rng.choice(sensory_pool, min(width, len(sensory_pool)), replace=False) for _ in range(16)],
                "left": rng.choice(motor_pool, motor_width, replace=False),
                "right": rng.choice(motor_pool, motor_width, replace=False),
                "readout": [rng.choice(memory_pool, min(64, max(2, len(memory_pool) // 32)), replace=False)
                            for _ in range(32)],
                "memory": rng.choice(memory_pool, min(512, len(memory_pool)), replace=False),
                "background": rng.choice(sensory_pool, min(len(sensory_pool), max(1, self.n // 50)), replace=False)}

    def _make_sample(self) -> np.ndarray:
        seeds = np.linspace(0, self.n - 1, min(40, self.n), dtype=int)
        neighbours = []
        for index in seeds:
            row = self.matrix.getrow(index)
            strongest = np.argsort(-np.abs(row.data))[:5]
            neighbours.extend(row.indices[strongest].tolist())
        sample = np.concatenate((self.ports["sensory"][0][:16], self.ports["left"][:12],
                                 seeds, np.asarray(neighbours, dtype=int),
                                 np.linspace(0, self.n - 1, min(450, self.n), dtype=int)))
        return np.unique(sample)

    def _make_sample_geometry(self) -> list[tuple[float, float]]:
        positions = getattr(self.graph, "positions", None)
        self._anatomical_layout = False
        if positions is not None:
            coordinates = np.asarray(positions, dtype=float)[self.sample_indices, :2]
            finite = np.isfinite(coordinates).all(axis=1)
            if finite.any():
                low, high = np.min(coordinates[finite], axis=0), np.max(coordinates[finite], axis=0)
                normalized = .06 + .88 * (coordinates - low) / np.maximum(high - low, 1.)
                normalized[~finite] = .5
                self._anatomical_layout = True
                return [(float(x), float(y)) for x, y in normalized]
        # Explicit test fixtures have no anatomical coordinates.
        points = []
        for k in range(len(self.sample_indices)):
            angle = k * 2.399963229728653
            radius = math.sqrt((k + .5) / len(self.sample_indices)) * .39
            points.append((.5 + math.cos(angle) * radius, .5 + math.sin(angle) * radius * .82))
        return points

    def _event(self, kind: str, message: str, **details) -> None:
        self._event_id += 1
        self.events.append({"id": self._event_id, "tick": self.tick,
                            "kind": kind, "message": message, **details})

    def _features(self, cue: np.ndarray, agent: Twin | None = None) -> np.ndarray:
        features = np.maximum(0., self._cue_projection @ cue)
        if agent is not None:
            features *= agent.neural_features
        norm = np.linalg.norm(features)
        return features / max(norm, 1e-12)

    @staticmethod
    def _familiarity_score(agent: Twin, features: np.ndarray) -> float:
        activation = agent.neural_gate * float(agent.familiarity @ features)
        return 1. / (1. + math.exp(-float(np.clip(activation, -30., 30.))))

    def _recognition_scores(self, index: int) -> dict[str, float]:
        agent = self.agents[index]
        familiar = self._familiarity_score(agent, self._features(self.cues[1 - index], agent))
        return {"partner": familiar,
                "novel": self._familiarity_score(agent, self._features(self.cues[2], agent)),
                "identical_cue": familiar}

    def _update_neural_readout(self, agent: Twin) -> None:
        """Engineered readout of actual spike traces, used by every learned policy."""
        if self.neural_silenced:
            agent.neural_gate = 0.
            agent.neural_bias.fill(0.)
            agent.neural_features.fill(1.)
            agent.neural_readout.fill(0.)
            return
        agent.neural_readout = np.array([float(agent.trace[indices].mean()) for indices in self.ports["readout"]])
        sensory = float(agent.trace[np.concatenate(self.ports["sensory"][:8])].mean())
        memory = float(agent.trace[self.ports["memory"]].mean())
        motor = float(agent.trace[np.concatenate((self.ports["left"], self.ports["right"]))].mean())
        agent.neural_gate = 1. - math.exp(-2. * (.5 * sensory + .3 * memory + .2 * motor))
        normalized = np.tanh(agent.neural_readout)
        agent.neural_features = 1. + .2 * (normalized - normalized.mean())
        grouped = normalized.reshape(4, 8).mean(axis=1)
        agent.neural_bias = .4 * (grouped - grouped.mean())

    @staticmethod
    def _policy(agent: Twin, role: str) -> np.ndarray:
        # Silencing makes the output distribution uniform; weights remain stored.
        return _softmax(agent.neural_gate * (getattr(agent, role) + agent.neural_bias[None, :]))

    def _prepare_presentations(self) -> None:
        self._presentations = [None, None]
        mode = "familiarization" if self.phase == "familiarization" or (
            self.phase == "reunion" and self.phase_tick % 2 == 0) else (
                "recognition" if self.phase in ("recognition", "reunion") else None)
        if mode is None:
            return
        for index in range(2):
            is_partner = self.tick % 3 != index if mode == "familiarization" else (
                bool((self.phase_tick // 2) % 2) if self.phase == "reunion" else bool(self.phase_tick % 2))
            cue = self.cues[1 - index] if is_partner else self.cues[2]
            observed = cue + self.rng.normal(0., .07 if mode == "familiarization" else .12, 8)
            self._presentations[index] = {"kind": mode, "is_partner": bool(is_partner), "cue": observed}

    def _neural_step(self, agent: Twin, sensory: np.ndarray) -> None:
        if self.neural_silenced:
            agent.voltage.fill(-52.)
            agent.spikes.fill(False)
            agent.trace.fill(0.)
            agent.refractory.fill(0)
            agent.step_spike_counts.fill(0)
            agent.spike_count, agent.spike_rate = 0, 0.
            self._update_neural_readout(agent)
            return
        current = self.background.copy()
        for indices, value in zip(self.ports["sensory"], sensory):
            current[indices] += float(value) * 28.
        count = 0
        agent.step_spike_counts.fill(0)
        for _ in range(NEURAL_STEPS_PER_TICK):
            synaptic = self.matrix @ agent.spikes.astype(np.float32)
            agent.refractory = np.maximum(agent.refractory - 1, 0)
            noise = agent.rng.normal(0., .035, self.n).astype(np.float32)
            agent.voltage += ((-52. - agent.voltage + current) / 20. + synaptic + noise)
            agent.voltage[agent.refractory > 0] = -52.
            np.maximum(agent.voltage, -85., out=agent.voltage)
            agent.spikes = (agent.voltage >= -45.) & (agent.refractory == 0)
            agent.voltage[agent.spikes] = -52.
            agent.refractory[agent.spikes] = 2
            agent.trace *= .95
            agent.trace += agent.spikes
            agent.step_spike_counts += agent.spikes
            count += int(agent.spikes.sum())
        agent.spike_count = count
        agent.total_spikes += count
        agent.spike_rate = count / (self.n * NEURAL_STEPS_PER_TICK * DT_MS / 1000.)
        self._update_neural_readout(agent)

    def _sensory(self, index: int) -> np.ndarray:
        agent = self.agents[index]
        partner = self.agents[1 - index]
        if self.phase == "baseline":
            # Explicit same-input control, despite different rendered bodies.
            return np.r_[np.full(8, .35), np.zeros(8)].astype(np.float32)
        visible = self.phase != "separation"
        cue = self.cues[1 - index] if visible else np.zeros(8)
        if self._presentations[index] is not None:
            cue = self._presentations[index]["cue"]
        distance = math.hypot(agent.x - partner.x, agent.y - partner.y)
        sensory = np.zeros(16, dtype=np.float32)
        sensory[:8] = np.clip((cue + 1.) * .5, 0., 1.) if visible else 0.
        # Different experiences are explicit, reproducible environmental inputs.
        sensory[8 + index] = .9 if visible else .1
        sensory[10] = max(0., 1. - distance) if visible else 0.
        sensory[11] = agent.energy
        sensory[12] = .5 + .5 * math.sin(self.tick * .08 + index * math.pi)
        if self.last_trial is not None and self.phase in ("communication", "reunion"):
            sensory[12 + self.last_trial["received_symbol"]] = 1.
        return sensory

    def _body_step(self, index: int) -> None:
        agent = self.agents[index]
        left = float(agent.trace[self.ports["left"]].mean())
        right = float(agent.trace[self.ports["right"]].mean())
        # An engineered differential motor readout of actual spike traces.
        agent.heading += .22 * math.tanh((right - left) * 3.)
        speed = .0048 * math.tanh(max(0., (left + right) * .5))
        agent.x += math.cos(agent.heading) * speed
        agent.y += math.sin(agent.heading) * speed
        lo_x, hi_x = (.04, .46) if self.phase == "separation" and index == 0 else (
            (.54, .96) if self.phase == "separation" else (.04, .96))
        if agent.x < lo_x or agent.x > hi_x:
            agent.x = float(np.clip(agent.x, lo_x, hi_x))
            agent.heading = math.pi - agent.heading
        if agent.y < .07 or agent.y > .93:
            agent.y = float(np.clip(agent.y, .07, .93))
            agent.heading = -agent.heading
        agent.heading = (agent.heading + math.pi) % (2. * math.pi) - math.pi
        agent.energy = float(np.clip(agent.energy - .00015, .1, 1.))
        agent.trail.append({"x": agent.x, "y": agent.y})

    def _familiarization_trial(self, index: int) -> None:
        agent = self.agents[index]
        presentation = self._presentations[index]
        if presentation is None or presentation["kind"] != "familiarization":
            return
        is_partner = presentation["is_partner"]
        features = self._features(presentation["cue"], agent)
        reward = float(is_partner)
        prediction = self._familiarity_score(agent, features)
        agent.eligibility *= .75
        agent.eligibility += features * .25
        learning_rate = 1.1 * agent.neural_gate if self.plasticity else 0.
        delta = learning_rate * (reward - prediction) * features
        agent.familiarity += delta
        self._pending_trials.append({"tick": self.tick, "phase": self.phase, "type": "familiarization",
                                     "agent": "AB"[index], "partner_cue": is_partner,
                                     "observed_cue": presentation["cue"].tolist(), "reward": reward,
                                     "prediction": prediction, "neural_gate": agent.neural_gate,
                                     "effective_learning_rate": learning_rate, "update_l2": float(np.linalg.norm(delta))})
        agent.energy = min(1., agent.energy + reward * .0007)

    def _recognition_trial(self, index: int) -> None:
        # Probe on noisy held-out cue presentations, with no learning.
        presentation = self._presentations[index]
        if presentation is None or presentation["kind"] != "recognition":
            return
        is_partner = presentation["is_partner"]
        agent = self.agents[index]
        features = self._features(presentation["cue"], agent)
        score = self._familiarity_score(agent, features)
        prediction = score >= .5
        self.recognition_results.append(int(prediction == is_partner))
        self.all_recognition_trials += 1
        self._pending_trials.append({"tick": self.tick, "phase": self.phase, "type": "recognition",
                                     "agent": "AB"[index], "partner_cue": is_partner,
                                     "observed_cue": presentation["cue"].tolist(), "score": score,
                                     "correct": int(prediction == is_partner), "neural_gate": agent.neural_gate,
                                     "effective_learning_rate": 0., "trial": self.all_recognition_trials})

    def _signal_trial(self) -> None:
        sender_index = self.all_signal_trials % 2
        sender = self.agents[sender_index]
        receiver = self.agents[1 - sender_index]
        context = int(self.rng.integers(4))
        # The sender observes context; the receiver observes only one symbol.
        send_prob = self._policy(sender, "sender")[context]
        symbol = int(sender.rng.choice(4, p=send_prob))
        received = int(self.rng.integers(4)) if self.shuffle_signals else symbol
        receive_prob = self._policy(receiver, "receiver")[received]
        action = int(receiver.rng.choice(4, p=receive_prob))
        reward = float(context == action)
        if self.plasticity:
            sender_adv = reward - sender.sender_baseline[context]
            receiver_adv = reward - receiver.receiver_baseline[received]
            sender.sender_baseline[context] += .04 * sender.neural_gate * sender_adv
            receiver.receiver_baseline[received] += .04 * receiver.neural_gate * receiver_adv
            sender.sender[context] -= .22 * sender.neural_gate * sender_adv * send_prob
            sender.sender[context, symbol] += .22 * sender.neural_gate * sender_adv
            receiver.receiver[received] -= .22 * receiver.neural_gate * receiver_adv * receive_prob
            receiver.receiver[received, action] += .22 * receiver.neural_gate * receiver_adv
            np.clip(sender.sender, -12., 12., out=sender.sender)
            np.clip(receiver.receiver, -12., 12., out=receiver.receiver)
        self.confusion[context, action] += 1
        self.symbol_counts[context, symbol] += 1
        self.all_signal_trials += 1
        self.signal_correct += int(reward)
        self.reward_total += reward
        self.signal_results.append(int(reward))
        self.last_trial = {"sender": "AB"[sender_index], "context": context,
                           "symbol": symbol, "received_symbol": received,
                           "action": action, "reward": reward, "shuffled": self.shuffle_signals,
                           "trial": self.all_signal_trials, "tick": self.tick, "phase": self.phase,
                           "type": "signal", "sender_gate": sender.neural_gate, "receiver_gate": receiver.neural_gate,
                           "sender_bias": sender.neural_bias.tolist(), "receiver_bias": receiver.neural_bias.tolist(),
                           "sender_learning_rate": .22 * sender.neural_gate if self.plasticity else 0.,
                           "receiver_learning_rate": .22 * receiver.neural_gate if self.plasticity else 0.,
                           "sender_probabilities": send_prob.tolist(), "receiver_probabilities": receive_prob.tolist()}
        self._pending_trials.append(self.last_trial.copy())
        sender.energy = min(1., sender.energy + reward * .00025)
        receiver.energy = min(1., receiver.energy + reward * .00025)

    def _divergence(self) -> tuple[float, float]:
        a, b = self.agents
        neural_distance = float(np.sqrt(np.mean((a.voltage - b.voltage) ** 2)))
        learning_distance = float(np.sqrt(np.mean((a.familiarity - b.familiarity) ** 2))
                                  + np.sqrt(np.mean((a.sender - b.sender) ** 2))
                                  + np.sqrt(np.mean((a.receiver - b.receiver) ** 2)))
        # A bounded engineering distance, not an individuality/consciousness score.
        return float(1. - math.exp(-(neural_distance / 7. + learning_distance / 4.))), neural_distance

    def communication_evaluation(self) -> dict[str, Any]:
        """Exact policy expectation on four balanced contexts, without training."""
        directional = []
        greedy = []
        for i in range(2):
            sender = self._policy(self.agents[i], "sender")
            receiver = self._policy(self.agents[1 - i], "receiver")
            channel = np.full((4, 4), .25) if self.shuffle_signals else np.eye(4)
            end_to_end = sender @ channel @ receiver
            directional.append(float(np.trace(end_to_end) / 4.))
            actions = np.argmax(receiver, axis=1)
            symbols = np.argmax(sender, axis=1)
            greedy.append(.25 if self.shuffle_signals else float(np.mean(actions[symbols] == np.arange(4))))
        return {"expected_accuracy": float(np.mean(directional)),
                "greedy_accuracy": float(np.mean(greedy)),
                "directional_accuracy": directional, "chance": .25,
                "method": "Exact neural-conditioned policy expectation over four balanced contexts at current measured neural state; no learning."}

    def step(self, n: int = 1) -> dict[str, Any]:
        if not isinstance(n, int) or n < 1 or n > 10000:
            raise ValueError("step count must be an integer from 1 to 10000")
        for _ in range(n):
            if self.completed and self.automatic:
                break
            self.tick += 1
            self.phase_tick += 1
            self._prepare_presentations()
            for i, agent in enumerate(self.agents):
                self._neural_step(agent, self._sensory(i))
            for i in range(2):
                self._body_step(i)
            if self.phase in ("familiarization", "reunion"):
                for i in range(2):
                    self._familiarization_trial(i)
            if self.phase in ("recognition", "reunion"):
                for i in range(2):
                    self._recognition_trial(i)
            if self.phase in ("communication", "reunion"):
                for _ in range(SIGNAL_TRIALS_PER_TICK):
                    self._signal_trial()
            if self.tick % 5 == 0:
                self._record_history()
            if self.tick % 100 == 0 and self.last_trial:
                self._event("measurement", f"Signalling: {np.mean(self.signal_results):.1%} over the latest {len(self.signal_results)} trials.",
                            accuracy=float(np.mean(self.signal_results)), trials=self.all_signal_trials)
            if self.automatic and self.phase_tick >= PHASE_LENGTHS[self.phase]:
                phase_index = PHASES.index(self.phase)
                if phase_index == len(PHASES) - 1:
                    self.completed = True
                    self._event("complete", "The six-phase protocol is complete. Export includes all measured trials and controls.")
                else:
                    self.set_phase(PHASES[phase_index + 1])
        return self.snapshot()

    def _record_history(self) -> None:
        divergence, distance = self._divergence()
        self.history.append({"tick": self.tick, "phase": self.phase, "divergence": divergence,
                             "state_distance": distance,
                             "communication_accuracy": float(np.mean(self.signal_results)) if self.signal_results else None,
                             "recognition_accuracy": float(np.mean(self.recognition_results)) if self.recognition_results else None,
                             "spike_rate_a": self.agents[0].spike_rate,
                             "spike_rate_b": self.agents[1].spike_rate})

    def set_phase(self, phase: str) -> None:
        if phase not in PHASES:
            raise ValueError(f"Unknown phase: {phase}; choose from {', '.join(PHASES)}")
        self.phase, self.phase_tick, self.completed = phase, 0, False
        if phase == "separation":
            self.agents[0].x = min(self.agents[0].x, .44)
            self.agents[1].x = max(self.agents[1].x, .56)
        self._event("phase", f"Phase changed to {phase}.", phase=phase)

    def command(self, action: str, **kwargs) -> dict[str, Any]:
        if action in ("phase", "set_phase"):
            self.set_phase(str(kwargs.get("phase", kwargs.get("value", ""))))
        elif action in ("plasticity", "set_plasticity"):
            self.plasticity = bool(kwargs.get("enabled", kwargs.get("value", True)))
            self._event("intervention", f"External associative plasticity {'enabled' if self.plasticity else 'frozen'}.")
        elif action in ("shuffle", "shuffle_signals"):
            self.shuffle_signals = bool(kwargs.get("enabled", kwargs.get("value", True)))
            self.signal_results.clear()
            self._event("intervention", f"Symbol channel randomization {'enabled' if self.shuffle_signals else 'disabled'}; rolling accuracy window cleared.")
        elif action in ("silence", "neural_silenced"):
            self.neural_silenced = bool(kwargs.get("enabled", kwargs.get("value", True)))
            if self.neural_silenced:
                for agent in self.agents:
                    self._neural_step(agent, np.zeros(16))
            self.signal_results.clear()
            self._event("intervention", f"Neural silencing {'enabled' if self.neural_silenced else 'disabled'}; neural gates, motor drive and learning follow measured activity.")
        elif action in ("automatic", "protocol"):
            self.automatic = bool(kwargs.get("enabled", kwargs.get("value", True)))
            self._event("intervention", f"Automatic phase progression {'enabled' if self.automatic else 'disabled'}.")
        elif action == "step":
            return self.step(int(kwargs.get("n", 1)))
        elif action == "reset":
            self.__init__(seed=int(kwargs.get("seed", self.seed)),
                          plasticity=bool(kwargs.get("plasticity", self.plasticity)), graph=self.graph)
        else:
            raise ValueError(f"Unknown action: {action}")
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        divergence, distance = self._divergence()
        evaluation = self.communication_evaluation()
        confidence_interval = None
        if self.signal_results:
            count = len(self.signal_results)
            proportion = float(np.mean(self.signal_results))
            z2 = 1.959963984540054 ** 2
            center = (proportion + z2 / (2 * count)) / (1 + z2 / count)
            half_width = math.sqrt(z2 * (proportion * (1 - proportion) / count + z2 / (4 * count * count))) / (1 + z2 / count)
            confidence_interval = [max(0., center - half_width), min(1., center + half_width)]
        twins = []
        for i, agent in enumerate(self.agents):
            activity = [{"index": int(index), "id": str(self.graph.ids[index]),
                         "x": self._sample_xy[k][0], "y": self._sample_xy[k][1],
                         "voltage": float(agent.voltage[index]),
                         "active": bool(agent.spikes[index]), "trace": float(agent.trace[index]),
                         "region": str(self.graph.regions[index])}
                        for k, index in enumerate(self.sample_indices)]
            twins.append({"id": "AB"[i], "name": ("EVE", "EVE₂")[i],
                          "color": ("#bcfb7b", "#d6afff")[i], "x": agent.x, "y": agent.y,
                          "heading": agent.heading, "energy": agent.energy,
                          "spike_rate": agent.spike_rate, "spike_count": agent.spike_count,
                          "total_spikes": agent.total_spikes, "activity": activity,
                          "region_rates": {region: float(agent.step_spike_counts[indices].mean() / .004)
                                           for region, indices in self._regions.items()},
                          "recognition": self._recognition_scores(i),
                          "neural_gate": agent.neural_gate, "neural_bias": agent.neural_bias.tolist(),
                          "neural_readout": agent.neural_readout.tolist(),
                          "weights": {"sender": self._policy(agent, "sender").tolist(),
                                      "receiver": self._policy(agent, "receiver").tolist(),
                                      "familiarity": agent.familiarity.tolist()},
                          "trail": list(agent.trail), "initial_state_hash": self.initial_hashes[i]})
        resources = [{"x": .14, "y": .17, "context": 0}, {"x": .86, "y": .17, "context": 1},
                     {"x": .14, "y": .83, "context": 2}, {"x": .86, "y": .83, "context": 3}]
        return {"schema_version": 1, "seed": self.seed, "tick": self.tick,
                "phase": self.phase, "phase_tick": self.phase_tick,
                "phase_progress": min(1., self.phase_tick / PHASE_LENGTHS[self.phase]),
                "neural_ms": self.tick * NEURAL_STEPS_PER_TICK * DT_MS,
                "neural_dt_ms": DT_MS, "neural_steps_per_tick": NEURAL_STEPS_PER_TICK,
                "plasticity": self.plasticity, "shuffle_signals": self.shuffle_signals,
                "neural_silenced": self.neural_silenced,
                "topology": {**self.graph.metadata, "neuron_count": self.n,
                             "edge_count": int(self.matrix.nnz), "graph_hash": self._graph_hash,
                             "initial_state_hash": self.initial_hashes[0],
                             "initial_states_identical": self.initial_hashes[0] == self.initial_hashes[1],
                             "model": "Sparse current-based LIF; 1 ms step",
                             "layout": "FlyWire annotated representative x/y positions, normalized 2D projection"
                             if self._anatomical_layout else "Abstract test layout; not anatomical coordinates",
                             "interface": "Engineered sensory ports and motor readouts",
                             "sample_edges": self._sample_edges,
                             "ports": {"sensory_ids": [[str(self.graph.ids[j]) for j in indices[:8]] for indices in self.ports["sensory"]],
                                       "memory_ids": [str(self.graph.ids[j]) for j in self.ports["memory"][:16]],
                                       "motor_left_ids": [str(self.graph.ids[j]) for j in self.ports["left"][:16]],
                                       "motor_right_ids": [str(self.graph.ids[j]) for j in self.ports["right"][:16]],
                                       "selection": "Seeded sensory, Kenyon-cell and descending annotations when available; engineered channel meanings",
                                       "id_list_scope": "Representative IDs; full indices in state-array export"},
                             "sample_count": len(self.sample_indices)},
                "twins": twins,
                "metrics": {"divergence": divergence, "state_distance": distance,
                            "state_distance_unit": "mV RMS", "divergence_unit": "bounded engineered state distance",
                            "recognition_accuracy": float(np.mean(self.recognition_results)) if self.recognition_results else None,
                            "recognition_trials": self.all_recognition_trials,
                            "communication_accuracy": float(np.mean(self.signal_results)) if self.signal_results else None,
                            "communication_greedy_accuracy": evaluation["greedy_accuracy"],
                            "communication_expected_accuracy": evaluation["expected_accuracy"],
                            "communication_chance": .25, "trial_count": self.all_signal_trials,
                            "trial_window": len(self.signal_results),
                            "communication_ci95": confidence_interval,
                            "communication_ci_method": "Wilson interval, recent trial window; adaptive trials are not independent biological replicates",
                            "communication_all_time_accuracy": self.signal_correct / self.all_signal_trials if self.all_signal_trials else None,
                            "mean_reward": self.reward_total / self.all_signal_trials if self.all_signal_trials else 0.},
                "history": list(self.history), "events": list(self.events),
                "channel": {"symbols": list(SYMBOLS), "confusion": self.confusion.tolist(),
                            "symbol_counts": self.symbol_counts.tolist(), "last_trial": self.last_trial,
                            "trials_per_tick": SIGNAL_TRIALS_PER_TICK,
                            "evaluation": evaluation,
                            "meaning": "Four arbitrary symbols; no natural language or preassigned semantics."},
                "arena": {"resources": resources, "bounds": [0., 1.],
                          "separated": self.phase == "separation",
                          "meaning": "Engineered virtual body; resource markers denote signalling contexts, not physical foraging success."},
                "protocol": {"automatic": self.automatic, "completed": self.completed,
                             "phases": [{"name": p, "ticks": PHASE_LENGTHS[p]} for p in PHASES]},
                "limitations": ["Connectivity alone does not recover an animal's full physiology.",
                                "Plasticity, cue learning and signalling are externally engineered layers.",
                                "Measured neural traces gate and bias external learned policies; this is an engineered hybrid, not a biological language circuit.",
                                "Identical sensory cues cannot establish individual partner identity.",
                                "Behaviour, accuracy or divergence cannot establish feelings or consciousness."]}

    def inspect_neuron(self, index_or_id: int | str) -> dict[str, Any]:
        """Inspect any real node, including actual signed incoming/outgoing edges."""
        if isinstance(index_or_id, int):
            index = index_or_id
        else:
            value = str(index_or_id).strip()
            if self._id_lookup is None:
                self._id_lookup = {str(node_id): i for i, node_id in enumerate(self.graph.ids)}
            if value in self._id_lookup:
                index = self._id_lookup[value]
            elif value.isdigit() and int(value) < self.n:
                index = int(value)
            else:
                raise ValueError("Neuron ID was not found in this connectome")
        if not 0 <= index < self.n:
            raise ValueError(f"Neuron index must be between 0 and {self.n - 1}")
        if self._outgoing is None:
            self._outgoing = self.matrix.tocsc()

        def edges(indices: np.ndarray, weights: np.ndarray) -> list[dict[str, Any]]:
            order = np.argsort(-np.abs(weights))[:12]
            return [{"index": int(indices[j]), "id": str(self.graph.ids[indices[j]]),
                     "weight_mv": float(weights[j])} for j in order]

        incoming = self.matrix.getrow(index)
        start, stop = self._outgoing.indptr[index:index + 2]
        return {"index": index, "id": str(self.graph.ids[index]),
                "label": str(self.graph.labels[index]), "region": str(self.graph.regions[index]),
                "incoming_count": int(incoming.nnz), "outgoing_count": int(stop - start),
                "incoming": edges(incoming.indices, incoming.data),
                "outgoing": edges(self._outgoing.indices[start:stop], self._outgoing.data[start:stop]),
                "twins": [{"id": "AB"[i], "voltage_mv": float(agent.voltage[index]),
                           "spiking": bool(agent.spikes[index]), "trace": float(agent.trace[index]),
                           "refractory_ms": int(agent.refractory[index])}
                          for i, agent in enumerate(self.agents)],
                "tick": self.tick, "neural_ms": self.tick * NEURAL_STEPS_PER_TICK * DT_MS,
                "source": self.graph.metadata.get("source", "FlyWire-derived graph")}

    def checkpoint_arrays(self) -> dict[str, np.ndarray]:
        """Array export for auditing. This is not a resumable checkpoint format."""
        values = {"neuron_ids": np.asarray(self.graph.ids),
                  "tick": np.array(self.tick), "seed": np.array(self.seed)}
        for i, agent in enumerate(self.agents):
            for field in ("voltage", "spikes", "trace", "refractory", "familiarity", "sender", "receiver", "neural_bias", "neural_readout"):
                values[f"{'AB'[i]}_{field}"] = getattr(agent, field).copy()
            values[f"{'AB'[i]}_neural_gate"] = np.array(agent.neural_gate)
        for name in ("sensory", "readout"):
            values[f"ports_{name}"] = np.stack(self.ports[name])
        for name in ("memory", "left", "right", "background"):
            values[f"ports_{name}"] = self.ports[name].copy()
        return values

    def drain_trials(self) -> list[dict[str, Any]]:
        """Transfer all unpersisted trial records to the server, exactly once."""
        records, self._pending_trials = self._pending_trials, []
        return records


def benchmark_learning(seeds=(11, 42, 73), ticks: int = 600) -> dict[str, Any]:
    """Paired multi-seed mechanism check with explicit synthetic neural dynamics.

    Plastic/frozen/shuffled/silenced conditions all run the same small neural
    fixture. This is not validation of full FlyWire biological capability.
    """
    runs = []
    for seed in seeds:
        for condition in ("plastic", "frozen", "shuffled", "silenced"):
            experiment = Experiment(seed=int(seed), plasticity=condition != "frozen", graph=synthetic_graph(32))
            experiment.shuffle_signals = condition == "shuffled"
            experiment.neural_silenced = condition == "silenced"
            experiment.set_phase("communication")
            experiment.automatic = False
            experiment.step(ticks)
            evaluation = experiment.communication_evaluation()
            runs.append({"seed": int(seed), "condition": condition,
                         "trials": experiment.all_signal_trials,
                         "last_400_accuracy": float(np.mean(experiment.signal_results)), **evaluation})
    return {"scope": "Neural-gated engineered signalling; explicit synthetic neural fixture; not a full FlyWire validation.",
            "seeds": list(seeds), "ticks": ticks, "runs": runs,
            "means": {condition: float(np.mean([r["expected_accuracy"] for r in runs if r["condition"] == condition]))
                      for condition in ("plastic", "frozen", "shuffled", "silenced")}}
