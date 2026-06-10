## Why

Regional GTFS feeds can cover a much wider service area than an imported model network, even when GTFS route types and
network modes are aligned. Importing such feeds without a coverage filter risks creating broken, over-simplified, or
misleading public transport lines in the model.

## What Changes

- Add a diagnostic-first GTFS coverage analysis workflow that evaluates GTFS route patterns against the project network
  before full GTFS import or map matching.
- Build route patterns from GTFS trips using ordered `stop_sequence` values rather than treating a route/line as a
  single homogeneous object.
- Match GTFS stops to candidate model links using the GTFS route-type to network-mode correspondence.
- Classify stop coverage as matched to modal links, near the model but not near modal links, outside model range,
  ambiguous, or unmatched.
- Classify each route pattern as fully covered, trim-covered at the beginning/end, rejected because of internal gaps,
  rejected because of network discontinuity, or skipped because of unsupported route type.
- Allow conservative trimming only when unmatched stops are a prefix and/or suffix of the ordered pattern.
- Report coverage diagnostics that explain why patterns are accepted, trimmed, rejected, or skipped.
- Non-goals: this change does not automatically enrich the model with missing streets, infer missing bus detours,
  import partial internal route segments, call external map services, or silently simplify internal route gaps.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `transit-gtfs`: add GTFS-to-network coverage analysis and conservative pattern filtering before network-based GTFS
  import/map matching.

## Impact

- `aequilibrae/transit/` GTFS builder, reader, or helper modules for route-pattern extraction and coverage analysis.
- Project network link access for modal and any-link stop proximity checks.
- GTFS map-matching workflow, which can consume accepted/trimmed pattern decisions in a later implementation step.
- Tests under `tests/aeq/transit/`, with synthetic GTFS/network fixtures for prefix/suffix trimming, internal gaps,
  outside-coverage stops, and unsupported route types.
- Documentation for GTFS import preparation and regional feed filtering.
