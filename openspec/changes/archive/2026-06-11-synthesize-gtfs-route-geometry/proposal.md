## Why

GTFS feeds provide enough data to reconstruct public-transport service skeletons, but assignment workflows also need
route geometry and network link sequences. When a feed lacks `shapes.txt`, or when shapes cannot be reliably matched to
the project network, AequilibraE needs a transparent inference workflow that can generate a first qualitative,
assignment-usable transit network from GTFS stops and the model graph.

## What Changes

- Add a GTFS route-geometry synthesis workflow that produces route geometry, route links, and pattern-to-network link
  mappings for assignment-ready public transport import.
- Treat GTFS `shapes.txt` as the preferred happy path when present, using shapes to guide map matching and link-sequence
  reconstruction.
- When `shapes.txt` is absent, infer stop-to-stop paths through the project network from ordered GTFS stop patterns.
- Prefer route-type modal links and main-street or higher-priority links when they produce a reasonable path, while
  allowing lower-priority links when the preferred path is unavailable or more than the configured detour threshold.
- Record segment-level and pattern-level quality diagnostics, including inferred segments, fallback choices, unmatched
  stops, excessive detours, disconnected segments, and mode or street-priority compromises.
- Preserve the diagnostic-first coverage behavior as an analysis mode, but add an explicit inference mode for generating
  a first rough import suitable for qualitative assignment.
- Non-goals: this change does not guarantee exact real-world transit geometry, calibrate PT assignment results, infer
  demand, call external routing/map services, or automatically edit the project network to add missing links.
- Important deferred example gap: the current Karlsruhe GTFS feed available to this work does not include `shapes.txt`.
  A future fixture/feed with GTFS shapes is needed to validate and tune the happy path against source-provided geometry.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `transit-gtfs`: add assignment-usable GTFS route-geometry synthesis from GTFS shapes when available and from
  stop-to-stop network inference when shapes are absent.

## Impact

- `aequilibrae/transit/` GTFS builder, coverage diagnostics, route map matching, and route-system persistence.
- Project network graph access for route-type modal subgraphs, main-street preference, fallback routing, and link
  sequence reconstruction.
- Transit database writes for `routes`, `route_links`, `pattern_mapping`, trips, and schedules when synthesized routes
  are accepted for import.
- Tests under `tests/aeq/transit/` for GTFS shape-guided matching, no-shape stop-to-stop inference, street-priority
  preference, detour thresholds, rejected segments, and quality diagnostics.
- Sphinx documentation for GTFS import modes: diagnostic coverage, shape-guided synthesis, and inferred geometry
  synthesis.
