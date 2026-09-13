# The Twins: computational methods

This document describes the implementation in `twins/engine.py`, including its
deliberate approximations. Data provenance, licenses and primary biological
references are recorded in [SOURCES.md](SOURCES.md). Numeric outcomes belong in
[VALIDATION.md](VALIDATION.md), with the condition and seed that produced them.

## Model boundaries

Both agents use the full downloaded directed graph: 138,639 neurons and
15,091,983 weighted neuron-pair edges. `W[j, i]` is the signed weight from neuron
`i` to neuron `j`, in millivolts, obtained by multiplying the export's signed
connectivity count by 0.275. The recurrent graph is fixed throughout an
experiment. A shared read-only topology is paired with separate voltage, spike,
trace, refractory and learning arrays for the two agents.

The LIF dynamics, choice of sensory ports, virtual body, cue representations,
reinforcement schedules and learned readouts are engineered additions. Their
presence is not a reconstruction of biological memories or a claim to reproduce
the Eon/Shiu benchmark. In particular, this kernel does not implement that
reference model's exponentially decaying synaptic variable, 1.8 ms delay or
0.1 ms discretization. Its recurrent impulses arrive one 1 ms step after the
presynaptic spike. The changed dynamics require their own validation.

## Initial conditions and repeatability

Each twin is initialized with the same seed. Initial voltages are independent
draws per neuron from `Uniform(-52, -48)` mV, with the identical resulting array
in both twins. Spikes, traces, refractory counters and cue weights start at
zero. Sender and receiver logits start as `Normal(0, 0.02)` arrays; these small
random values contain no predefined symbol mapping. Separate random generators
start in the same state. The environment has its own generator, seeded with
`seed + 2001`.

The initial hash covers neural arrays and learning parameters, not a biological
identity. Bodies deliberately start on opposite sides of the arena with different
headings. The baseline bypasses those body differences and supplies identical
sensory input. Equal initialization and equal random draws then produce equal
neural states. Later cue schedules, body positions and sender/receiver roles
introduce distinct inputs and random draw histories. Repeating the same seed and
interventions is tested in one software environment; cross-platform bitwise
identity is not promised.

## Discrete neural update

One experiment tick contains four neural steps of `dt = 1 ms` for each twin.
With previous binary spikes `s`, voltage `v`, background/port current `I`, and
independent per-neuron noise `epsilon ~ Normal(0, 0.035)` mV, each step computes:

```text
synaptic = W @ s
refractory = max(refractory - 1, 0)
v = v + (-52 - v + I) / 20 + synaptic + epsilon
v[refractory > 0] = -52
v = max(v, -85)
s = (v >= -45) AND (refractory == 0)
v[s] = -52
refractory[s] = 2
trace = 0.95 * trace + s
```

The membrane leak uses a 20 ms time constant at this fixed step size. A spike
sets a two-step counter; because the counter is decremented before threshold
evaluation, the following integration step is suppressed and the next can
spike. Inputs received while refractory are discarded by the reset. The
**-85 mV floor is an engineering clamp**, not a recovered membrane property.
The trace is an arbitrary exponentially decaying activity statistic with a
time constant of approximately `-1 / log(0.95) = 19.5 ms`.

Input current has a tonic value of 8.5 at selected background ports. Each of
16 sensory channels adds its value multiplied by 28 at its own selected neuron
subset. Sensory port subsets can overlap. The membrane term treats these
values as voltage-equivalent current; this is not a biophysical conductance
model. Neither the floor, noise, tonic drive nor port amplitudes have been fitted
to this particular fly's measured activity.

The reported spike rate is the number of spikes over the last four integration
steps divided by `neuron_count * 0.004 seconds`. Region rates use the same
denominator per group. They are short-window simulation rates, not recordings.

## Ports, cues and virtual body

When annotations are available, input ports are drawn from the `sensory`
superclass and left/right motor readouts from `descending`. Selection uses
`seed + 777`; channel width is capped at 128 and each motor group at 256. For
small unannotated test fixtures, the candidate pool is all neurons. These
categories constrain the candidate pool but **do not identify the selected
neurons as receptors or motor circuits for the assigned task**. Left/right and
channel semantics are assigned by this experiment.

Partner A, partner B and an unfamiliar cue are three fixed normalized random
eight-dimensional vectors. A seeded 32-by-8 projection, rectification and
unit-length normalization produce the cue features. Visible-partner cues,
distance, an agent-specific exposure channel, energy and a periodic drive enter
the sensory vector. A received symbol can also be fed into one of its last four
channels on the following tick. During baseline all agents receive the same
constant input. During separation partner channels are removed and the body is
confined to one side.

The virtual body uses mean left/right spike traces. Heading changes by
`0.22 * tanh(3 * (right - left))`; speed is
`0.0048 * tanh(max(0, (left + right)/2))` arena units per tick. With zero
readout activity, the body stops. Walls reflect
heading and clamp position. The bodies have no biomechanical joints or physics
engine. Resource markers illustrate the signalling game's four possible contexts;
their placement does not measure successful navigation or food consumption.
The energy variable is an engineered bounded state with per-tick decay and
reward increments, not a physiological metabolism or affect measure.

## Partner cue association

Each agent has a 32-element learned vector `w`. Familiarity is `sigmoid(g * w @ f)`
using the measured neural gate described below, with its pre-sigmoid value clipped to `[-30, 30]` for numerical
stability. Familiarization presents a partner cue on approximately two thirds
of ticks and the unfamiliar cue otherwise; the schedules for A and B have
different offsets. Training cue noise has standard deviation 0.07. The partner
target is one and the unfamiliar target is zero. Plasticity updates the
external cue readout by `1.1 * g * (reward - prediction) * f` when learning is
enabled. Each noisy cue is generated before neural integration and injected
into the input ports used by that trial.

Recognition presents balanced noisy partner/unfamiliar examples with standard
deviation 0.12 and a decision threshold of 0.5. The recognition phase does not
train. Reunion includes both new association training and recognition probes;
reunion recognition is therefore not an isolated frozen test. The unfamiliar
prototype is present during training: the test checks new noisy presentations
of learned categories, not generalization to arbitrary unseen individuals.

The `identical_cue` control is explicitly equal to the partner score. The model
cannot identify two entities whose only observable cue is identical. An
eligibility trace is recorded as `e = 0.75 * e + 0.25 * features`; it is not used
in the current parameter update and must not be described as a validated
three-factor biological plasticity rule.

## Four-symbol communication

Each agent owns a 4-by-4 sender-logit table and a 4-by-4 receiver-logit table.
A uniformly selected context is visible to the sender. A symbol is sampled
from the sender policy; the receiver samples an action after observing that
symbol. A shared reward is one when action equals context and zero otherwise.
Sender roles alternate. Symbols have no preassigned meanings and no language
model is used.

The sender and receiver use separate exponentially updated reward baselines
with step size `0.04 * g`. Their sampled-policy update is proportional to
`0.22 * g * (reward - baseline) * (one_hot(choice) - choice_probability)`, with each
logit clipped to `[-12, 12]`. Switching plasticity off freezes learned parameter
updates. The evolving neural state and body continue to run.

Channel randomization replaces each transmitted symbol with an independent
uniform symbol. It clears the rolling communication-accuracy window. For four
balanced contexts, a receiver that observes no context information has an exact
expected success probability of 0.25. Finite sampled trial windows can deviate
from that value. This control measures information conveyed by the channel,
not emotional or social attachment.

## Measured neural coupling and silencing

The graph and external learned readouts form an engineered hybrid. At every
tick, mean actual spike traces in the selected sensory (`S`), Kenyon-cell (`K`)
and descending/motor (`M`) groups determine:

```text
g = 1 - exp(-2 * (0.5*S + 0.3*K + 0.2*M))
u = tanh(mean trace in each of 32 readout groups)
feature_multiplier = 1 + 0.2*(u - mean(u))
bias = 0.4*(mean(u reshaped into 4 groups of 8) - mean(u))
policy = softmax(g * (learned_logits + bias))
```

The rectified cue projection is multiplied by `feature_multiplier` before
unit-length normalization. The same measured gate scales recognition, symbol
policy sharpness and learning gradients. Per-trial logs record gates, learning
rates, cue/reward or symbol/action outcomes. Representative selected neuron IDs
are exposed in provenance; full port indices are included in array exports.

The **neural silence** intervention sets voltage to rest and spikes/traces to
zero; the gate becomes zero, learned policies become uniform, cue scores become
0.5, movement stops and learned parameters stop updating. Existing learned
weights are preserved. Turning silence off permits the network to integrate
again. This causal dependency is a design choice of this hybrid. It does not
prove these are biological learning circuits or that the full FlyWire topology
is necessary for task success. Gates can approach saturation under high tonic
activity; compare actual readout traces before interpreting their variation.

## Protocol and time scales

| Phase | Experiment ticks | Operations after neural/body update |
| --- | ---: | --- |
| Baseline | 50 | Same-input comparison |
| Familiarization | 250 | Two cue association trials per tick |
| Recognition | 100 | Two frozen cue probes per tick |
| Communication | 600 | Eight signalling trials per tick |
| Separation | 150 | Partner cues removed; bodies separated |
| Reunion | 150 | Alternating cue association/probe ticks; eight signalling trials |

The complete automatic protocol is 1,300 ticks and **5,200 ms of neural
integration**. Eight symbolic game trials occur after four neural steps. The
signalling task is accelerated experimental bookkeeping and is not eight
biologically plausible conversations in 4 ms. The wall-clock speed setting
changes how often the program attempts ticks. Neural time, experiment ticks,
symbol trials and elapsed wall time should not be interchanged.

## Metrics and display

Let `RMS(x)` denote the root mean square over an array. State distance is
`dV = RMS(vA - vB)` in mV. Learning distance is
`dL = RMS(wA - wB) + RMS(senderA - senderB) + RMS(receiverA - receiverB)`.
The displayed bounded divergence is:

```text
D = 1 - exp(-(dV / 7 + dL / 4))
```

The divisors are chosen display scales. Divergence is an engineering distance,
not a probability, statistical significance level, individuality score or
consciousness measure. It can grow because of noise histories or assigned
inputs even if no useful task learning occurs.

Communication accuracy is separately reported for the latest at most 400
sampled trials, for all trials, and as an exact current-policy expectation.
The policy expectation averages the diagonal of the sender-channel-receiver
transition matrix over four uniformly likely contexts and both directions.
Greedy accuracy instead takes the maximum-probability decisions. Recognition
accuracy uses a separate rolling window of at most 400 balanced probes. None
of these windows automatically supplies a confidence interval.

The network panel renders a selected set of real neurons and actual edges
between them. It does not draw every neuron. The positions are a normalized
2D projection of official anchor coordinates, when available; the production
inspector can query any node by exact FlyWire ID or index. Missing annotations
do not imply that a neuron is absent from the dynamics. Broad groups in the
panel come from `super_class`, not precise neuropil boundaries.

## Records, replay and verification scope

The local archive records run metadata, interventions, phase events, individual
task trials and periodic displayed-state snapshots. Standard replay is based on
snapshots every five ticks plus explicitly persisted states. It is not a
complete recording of every spike in all 138,639 neurons. The optional array
export contains current neural and learned state for inspection; it omits
random-generator state and other required fields and is **not a resumable
checkpoint**.

If multiple actions occur while paused at one tick, its replay frame is the
last saved state for that tick; the individual actions and events retain their
order in the archive. Full-state array export and the neuron inspector always
refer to the live engine, so these controls are disabled while browsing an
archived run. Recorded snapshots contain sampled neurons, not arbitrary
historical per-neuron voltage lookup.

Small synthetic fixtures test repeatability, equality under identical input,
divergence under changed experience, frozen learning, cue controls, and response
to removing recurrent connections. These are software/mechanism tests. A
three-seed signalling comparison runs the same small synthetic neural fixture
under plastic, frozen, shuffled and silenced conditions; it is a mechanism
check, not a population-level experiment. A separately executed full-graph protocol establishes that the
actual data, runtime and archive work together. It does not demonstrate that
biological FlyWire structure is necessary or uniquely effective for the learned
tasks; that requires matched topology, sign and readout ablations and a broader
experimental design.
