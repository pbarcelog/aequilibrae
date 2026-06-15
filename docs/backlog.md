# Development backlog

## Completed stage (present objectives)

The current stage focused on importing and reconciling **disjoint model artefacts** when network,
public transport, and demand do not share a single VISUM-style identifier graph:

- VISUM network import from SQLite and GeoJSON
- OMX demand import
- GTFS / public transport import with coverage and geometry synthesis where needed
- Heuristic completion when explicit relationships are missing (for example spread-based centroid
  connectors inferred from coordinates and zone polygons)

In this federated dataspace posture, the system may not rely on pre-existing links between sources.
It uses explicit topology when available and falls back to geometry and heuristics when it is not.

## Pre-stage 2 — fine-tuning and portability

Before the validation-and-assignment stage below, harden the import and reconciliation layer against
**non-VISUM and mixed-origin** inputs:

- exercise VISUM SQLite/GeoJSON, OMX, and GTFS workflows on files from suppliers, formats, and naming
  conventions beyond the current Karlsruhe and VISUM reference cases
- document which behaviours are universal (coordinate-based attachment, coverage filtering) versus
  VISUM-specific (field names, transport-system tokens, connector semantics)
- adjust mappings, diagnostics, and heuristics where tests reveal brittle or over-fitted assumptions
- expand automated tests and opt-in smoke fixtures for at least one non-VISUM or multi-source scenario

The README reflects this gap explicitly: present interfaces are **capable** of federated assembly but
their **generality** is not yet proven across origins.

## Next stage — validation, assignment, and model adjustment

The following items define the next development phase. They build on the import and reconciliation
work above and shift emphasis from **model assembly** to **model use and calibration**.

### 1. Sensors

Ingest and represent sensor observations (counts, speeds, travel times, or other traffic measurements)
so they can be referenced against the project network and assignment outputs.

### 2. Execute assignments

Run traffic (and, where relevant, public transport) assignments on models assembled from federated
sources, using the imported demand matrices and completed connectivity.

### 3. Compare results with reference data

#### 3.1 Compulsory — sensory data

Compare assignment outputs against sensor observations. This is the primary validation loop for the
next phase: link volumes, speeds, or other metrics derived from assignment should be checked against
measured data on the same network.

#### 3.2 Optional — other data sources

Extend comparison to additional reference datasets when available, for example:

- floating car data (FCD)
- other third-party mobility or traffic feeds

These comparisons are supplementary to the sensor-based validation, not a substitute for it.

### 4. Actions driven by comparison

Define logic that reacts to validation gaps between model results and reference data. Examples:

- adjust centroid connectors (count, location, or attachment nodes)
- flag or revise suspect network or demand inputs
- other calibration or connectivity changes triggered by systematic mismatches

The goal is not only to **measure** error but to support **closed-loop improvement** of the model
when federated inputs and heuristics leave residual bias.

## Out of scope for this backlog item

- Exact VISUM connector reproduction (pair-level ground truth matching)
- Assignment-equivalence studies against a single reference model (noted as future research)

These remain useful diagnostics but are not the primary success criterion for the federated import
stage already delivered.
