# Sources, data provenance and installation audit

Verified on **13 September 2026** against the primary repositories, their pinned
files, FlyWire's own data guidance, and the downloaded bytes. This record
distinguishes the research data, upstream software and this project's additions.

## What is actually loaded

The default loader uses the complete **Eon FlyWire v783 model export**, containing
**138,639 neuron IDs and 15,091,983 directed weighted connections**. These are
counts measured from the downloaded CSV and Parquet, not marketing numbers.
The sum of absolute signed connectivity counts is **54,492,922**. A weighted
connection is one neuron-pair edge; it may represent several anatomical synapses.

All 15,091,983 rows were checked against the completeness table: both root IDs
match the IDs at their presynaptic/postsynaptic indices, with **zero mismatches**.
The resulting CSR contains 15,091,983 nonzero entries and takes approximately
121.3 MB for values and indices. One observed load on this Windows machine took
5.06 seconds; this is an observation, not a performance guarantee.

The optional official annotation table joins **138,625** of these neurons. It
provides cell classes, cell types, predicted neurotransmitters and anatomical
anchor positions. Fourteen unmatched neurons remain explicitly unannotated.

FlyWire's current web portal separately reports FAFB v783 as **139,255 neurons
and 3,732,460 connections**. These are different published/exported tables and
filtering conventions. This application displays its loaded graph's measured
counts, and does not equate the two. The interactive Codex download page required
Google sign-in during the check; the pinned repository files below were publicly
downloadable without authentication. [FlyWire Codex](https://codex.flywire.ai/),
[download portal](https://codex.flywire.ai/api/download).

## Repository pins and code licenses

| Primary source | Inspected commit | Software license | Role here |
| --- | --- | --- | --- |
| [Eon fly-brain](https://github.com/eonsystemspbc/fly-brain/tree/a3db62f9436074e485c0278290c2164ed6150808) | `a3db62f9436074e485c0278290c2164ed6150808` | GPL-2.0 root license; nested paper model retains an MIT notice | Source of two cached data files; upstream program code is not bundled or executed |
| [Eon LIF fork](https://github.com/eonsystemspbc/drosophila_brain_model_lif/tree/c976c7a90b2ac5a472c028b5862974217e93573f) | `c976c7a90b2ac5a472c028b5862974217e93573f` | MIT | Audited older reference implementation |
| [Shiu/Spiller original model](https://github.com/philshiu/Drosophila_brain_model/tree/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960) | `91bdd1e7dcf193f3e7ca5a8933497fcef63b7960` | MIT, Philip Shiu and Nico Spiller | Original research implementation and model assumptions |
| [FlyWire annotations](https://github.com/flyconnectome/flywire_annotations/tree/8587524c1748ce5ef2080822a2fc890fc03bf597) | `8587524c1748ce5ef2080822a2fc890fc03bf597` | No repository-level software license detected; public FlyWire data terms apply to the annotation data | Cached official v783 neuron annotation table |

See the actual [Eon GPL license](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/LICENSE)
and [nested MIT notice](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/code/paper-phil-drosophila/LICENSE).
Downloading a GPL repository's data does not grant permission to relabel
FlyWire's underlying data as MIT. The Twins' original code license and these
external licenses remain separate. If upstream GPL software is incorporated in
a later revision, its distribution obligations must be reviewed at that time.

## Reproducible assets

The fetcher requests immutable commit URLs, checks exact byte length and SHA-256,
then writes a local provenance manifest. Cached data files are excluded from Git.
The checksum values below were calculated from successfully downloaded files on
the audit date; future fetches compare bytes against these fixed values.

| Filename | Bytes | SHA-256 |
| --- | ---: | --- |
| `2025_Completeness_783.csv` | 3,465,987 | `52b0ac6094cd32c546f8d4c341e094376f48f4e791f8db9b166de5dff8199ea4` |
| `2025_Connectivity_783.parquet` | 100,804,642 | `efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347` |
| `Supplemental_file1_neuron_annotations.tsv` | 31,718,505 | `9a4f8b2f843196074431ebd7cd883536afa1be86c8a4ce90970441e8be81d1be` |

Direct files: [neuron IDs](https://raw.githubusercontent.com/eonsystemspbc/fly-brain/a3db62f9436074e485c0278290c2164ed6150808/data/2025_Completeness_783.csv),
[connectivity](https://raw.githubusercontent.com/eonsystemspbc/fly-brain/a3db62f9436074e485c0278290c2164ed6150808/data/2025_Connectivity_783.parquet),
[annotations](https://raw.githubusercontent.com/flyconnectome/flywire_annotations/8587524c1748ce5ef2080822a2fc890fc03bf597/supplemental_files/Supplemental_file1_neuron_annotations.tsv).

The connectivity schema includes `Presynaptic_ID`, `Postsynaptic_ID`,
`Presynaptic_Index`, `Postsynaptic_Index`, `Connectivity`, `Excitatory`, and
`Excitatory x Connectivity`. Our loader uses post-neuron rows and pre-neuron
columns, with the signed connectivity multiplied by **0.275 mV**. Decimal root
IDs are kept as strings when sent to the browser because these numbers exceed
JavaScript's exact integer range. The raw source graph is not normalized.

Annotations' `pos_x/y/z` are anchor points, usually on a neuron's backbone, in
**4 × 4 × 40 nm voxel space**. The loader converts these to micrometres using
`[0.004, 0.004, 0.04]`. They are neither complete neuron shapes nor inferred
locations. `super_class` is exposed as a broad anatomical grouping; it is not
a neuropil segmentation. [Official annotation column definitions](https://github.com/flyconnectome/flywire_annotations/blob/8587524c1748ce5ef2080822a2fc890fc03bf597/supplemental_files/README.md).

## Data rights and attribution

FlyWire states that its public-release data is provided under **CC BY-NC 4.0**.
This includes attribution and a noncommercial restriction. Do not describe it
as unrestricted commercial-use data or as CC BY-NC-SA. Preserve source credits,
license links and a description of modifications in redistributed derived
datasets. This repository downloads the data to a local cache instead of
redistributing it as project-owned content. [FlyWire citation and release
guidelines](https://flywire.ai/guidelines), [CC BY-NC 4.0 legal
text](https://creativecommons.org/licenses/by-nc/4.0/legalcode).

The canonical connectivity archive is also available through the FlyWire
Consortium on Zenodo, including a larger `proofread_connections_783.feather`
file (852 MB) and synapse-coordinate products (9.5 GB). Those files are a
separate export and are not required for this implementation. [FlyWire
connectivity archive](https://zenodo.org/records/10676866).

## Installation status

The current Eon benchmark suite exposes Brian2 CPU, Brian2CUDA, PyTorch, NEST
GPU, GeNN and Brian2GeNN runners. Its main Conda environment pins Python 3.10
and NumPy 1.26.4 and includes CUDA-oriented packages. GeNN compilation requires
additional system dependencies; NEST GPU requires its own patched source build.
Brian2GeNN uses a separate environment because of incompatible Brian2 version
requirements. These are not drop-in requirements for this Windows application.
[Eon installation guide](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/README.md),
[pinned environment](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/environment.yml).

The older Shiu reference uses Python 3.10, Brian2 2.5.1 and NumPy 1.24. Its
default configuration is v630; the README explains the v783 file substitution.
[Reference environment](https://github.com/philshiu/Drosophila_brain_model/blob/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960/environment.yml).

The Twins loader was actually run with Python 3.12 on Windows using NumPy,
SciPy and PyArrow. It does not require Conda, CUDA, a language-model API, CAVE
credentials, remote execution or the Eon benchmark environment. Its own kernel
is an independently written experimental implementation; running it is not a
validation of numerical parity with Eon's six backends.

## Scientific interpretation

The Shiu model is a simplified spiking network. The paper explicitly discusses
missing morphology, receptor dynamics, gap junctions, non-spiking neurons,
internal state and long-range neuromodulation. Anatomical and neurotransmitter
prediction errors further limit conclusions. The published sensorimotor results
do not validate partner recognition, language learning or subjective experience.
[Shiu et al., Nature 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11446845/).

Mushroom-body and dopamine research motivates trying reward-dependent plasticity,
but does not specify a unique whole-brain learning rule. Biological experiments
show compartment-specific memory updating and reciprocal circuit interactions.
The Twins' learning layer is therefore an engineered hypothesis, not a recovered
memory system. [Aso and Rubin, eLife 2016](https://elifesciences.org/articles/16135),
[Cervantes-Sandoval et al., eLife 2017](https://elifesciences.org/articles/23789).

Two copies begin with identical graph and initialized model state; this means
identical computational initial conditions, not two established biological
individuals. Behavioral divergence, cue discrimination and successful symbolic
trials should be assessed against frozen-learning, shuffled-channel, unfamiliar
cue and other controls. Success is a task score under the implemented interface.
It establishes neither emotion, suffering, consciousness nor language in the
human sense. Network animation shows calculated state, not an empirical recording
of a living brain.

## Primary citations

- Dorkenwald et al. (2024), *Neuronal wiring diagram of an adult brain*.
  [Nature, DOI 10.1038/s41586-024-07558-y](https://doi.org/10.1038/s41586-024-07558-y).
- Schlegel et al. (2024), *Whole-brain annotation and multi-connectome cell typing
  of Drosophila*. [Nature, DOI 10.1038/s41586-024-07686-5](https://doi.org/10.1038/s41586-024-07686-5).
- Shiu et al. (2024), *A Drosophila computational brain model reveals sensorimotor
  processing*. [Nature, DOI 10.1038/s41586-024-07763-9](https://doi.org/10.1038/s41586-024-07763-9).
- FlyWire Consortium (2024), *FlyWire Whole-brain Connectome Connectivity Data*.
  [Zenodo, DOI 10.5281/zenodo.10676866](https://doi.org/10.5281/zenodo.10676866).

Acknowledgment: the FlyWire Consortium and its proofreaders; Princeton's Murthy
and Seung labs; the Jefferis laboratory's annotation work; Philip Shiu, Nico
Spiller and collaborators; and Eon Systems for the public model data export.
