# Implementation Notes

## Geometry Source Inventory

- `GTFSReader.__load_shapes_table()` loads `shapes.txt` when present, transforms WGS84 shape points into the project SRID, and stores each shape as `gtfs_data.shapes[shape_id]`.
- `GTFSReader.__load_trips_table()` preserves `Trip.shape_id`, assigns `trip.shape` from `gtfs_data.shapes` when available, and always builds `trip._stop_based_shape` from ordered stops.
- `GTFSRouteSystemBuilder.__build_new_pattern()` copies `trip.shape` into `Pattern.raw_shape` and `trip._stop_based_shape` into `Pattern._stop_based_shape`.
- `Pattern.best_shape()` currently returns map-matched `Pattern.shape` if available, otherwise `Pattern.raw_shape`, otherwise the stop-based straight-line shape.
- `Pattern.map_match()` sends ordered stops plus optional raw GTFS shape geometry into `RouteMapMatcher.map_match_route()`, then stores `Pattern.pattern_mapping` rows for persistence.
- `filter-gtfs-to-network-coverage` already provides reusable route-pattern inputs through `GTFSRoutePattern`, `StopCoverage`, and `PatternDecision`. The synthesis change now exposes `RoutePatternSynthesisInput` to carry accepted full/trim coverage decisions into later geometry synthesis.

## Synthetic Fixtures

- Unit fixtures now cover a shape-bearing feed where one trip has a loaded `shape_id` and another references a missing shape.
- Unit fixtures also cover a no-shape feed, matching the current Karlsruhe GTFS constraint.
- A real local `shapes.txt` example is still absent and remains a validation todo for the shape-guided happy path.

## Stop-To-Stop Segment Solver Spike

- Retained GTFS stops are now matched symmetrically to candidate network links. Modal candidates inside
  `stop_match_distance` are preferred; fallback candidates inside `fallback_stop_match_distance` are used only when no
  modal candidate exists.
- The first stop-to-stop solver builds a directed link graph from `a_node`, `b_node`, `direction`, and a distance cost
  field, then searches candidate origin and destination access states with Dijkstra.
- The spike assembles inferred fallback segment geometry, pattern-mapping rows, and rejection diagnostics for unmatched
  stops, disconnected stop pairs, unsupported route types, and excessive segment distance.
- Current simplification: stop access uses full candidate links at segment ends rather than splitting/projecting links
  at the exact stop projection. This is acceptable for the spike and should be reviewed before persistence wiring.

## Street-Priority Preference

- Stop candidates now carry a configurable priority classification derived from `GTFSRouteSynthesisConfig.priority_fields`
  and `preferred_priority_values`.
- Each stop-to-stop segment always computes the unrestricted modal fallback path first. A preferred path is attempted
  only when both stop candidate sets include priority links, matching the design decision that local/secondary stop
  context should not be forced onto main streets.
- Preferred paths are selected when they are within `preferred_path_detour_ratio` of the fallback path. Otherwise the
  fallback path is used and diagnostics report either unavailable preferred routing, unsupported priority context, or an
  excessive preferred detour.

## Karlsruhe No-Shapes Sample Checkpoint

- A bounded sample over the first 40 coverage-accepted Karlsruhe GTFS patterns used the scratch GeoJSON-derived project
  `.karlsruhe-geojson-default-modes-20260610-apply-2`, service date `2026-06-10`, and projected both network links and
  stops to a metre CRS before synthesis.
- Coverage reproduced the prior checkpoint: 288 accepted patterns from 73 fully-covered and 215 trim-covered patterns,
  with 1,615 internal-gap and 19 network-discontinuity rejected patterns.
- Initial sample result before the one-stop fix: 40/40 sampled patterns connected, with 38 inferred-fallback patterns
  and 2 inferred-preferred patterns. Segment sources were 120 inferred-fallback and 14 inferred-preferred.
- Segment fallback reasons in that sample were mostly `priority-context-unsupported`, plus a few
  `preferred-path-unavailable` and one `preferred-path-exceeds-detour-ratio`.
- The sample exposed that trim-covered patterns can retain only one stop. Such patterns cannot yield assignment-ready
  route geometry, so synthesis now rejects them as `insufficient-retained-stops`.
- Performance warning from the initial sample: rebuilding Python routing state for each segment made Karlsruhe-scale
  synthesis too slow. This motivated the review-scale cache below before a full 288-pattern review.

## Review-Scale Synthesis Caching

- `GTFSRouteSynthesisCache` now prepares network links once and reuses stop matches, route-type modal graphs,
  route-type priority graphs, repeated stop-pair path results, and Dijkstra trees by route type and origin node across
  pattern synthesis calls.
- The cache exposes lightweight counters for stop-match hits/misses, graph builds, and path hits/misses so diagnostic
  runs can report whether the full Karlsruhe review is using the intended reuse path.
- `synthesize_inferred_pattern_geometry`, `match_stop_to_network`, and `infer_stop_to_stop_segment` remain usable without
  an explicit cache, but review-scale runs should create one cache per projected network/configuration and pass it to
  every pattern synthesis call.

## Karlsruhe Full No-Shapes Review Checkpoint

- A full review over all 288 previously coverage-accepted Karlsruhe GTFS patterns completed with one shared
  `GTFSRouteSynthesisCache`. The review exposed that 94 of those patterns retained fewer than two stops after trimming.
- The coverage/synthesis contract now treats fewer than two retained stops as `insufficient-retained-stops`, so those 94
  patterns should be rejected before assignment-ready synthesis in subsequent runs.
- Results: 194 accepted synthesized patterns and 94 rejected patterns.
- Pattern sources: 128 `inferred-fallback`, 66 `inferred-preferred`, and 94 `rejected`.
- Rejection reason: all 94 rejected patterns had `insufficient-retained-stops` after coverage trimming.
- Segment sources among accepted patterns: 727 `inferred-fallback` and 631 `inferred-preferred`.
- Segment fallback reasons: 680 `priority-context-unsupported`, 37 `preferred-path-unavailable`, and 10
  `preferred-path-exceeds-detour-ratio`; 631 preferred segments had no fallback reason.
- Cache counters: 928 stop-match hits, 624 stop-match misses, 6 graph builds, 1,137 path hits, 899 path misses,
  1,622 Dijkstra-tree hits, and 1,357 Dijkstra-tree misses.
- Runtime was about 513 seconds including GTFS text scanning, coverage analysis, projection, and synthesis. This is
  practical for a diagnostic checkpoint but still not fast enough to treat as the final import path without further
  profiling or moving more routing work into existing graph machinery.

## Quality Summary Reports

- `summarize_synthesized_patterns()` now turns a collection of `SynthesizedPatternGeometry` results into report-ready
  pandas tables.
- The pattern detail table records route ID, route type, direction, coverage decision, retained stop counts, trim flag,
  geometry source, acceptance status, rejection reason, segment counts, and mapping-row counts.
- The segment detail table records stop pair, status, geometry source, fallback or rejection reason, selected and
  alternative path distances, detour ratio, link count, and flags.
- Grouped summaries are produced by route, route type, geometry source, fallback reason, and rejection reason. These
  summaries are intended for diagnostic review and export; they do not introduce persistent diagnostic tables.

## Diagnostic-Only Geometry Planning

- `plan_gtfs_route_geometry()` makes route-geometry mode explicit before persistence wiring. The default mode is
  `diagnostic-only`, which reports coverage-accepted pattern eligibility but returns no synthesis inputs.
- `infer-network-paths` mode returns the same eligible coverage-approved patterns as synthesis inputs. This keeps
  conservative coverage review separate from inferred route generation and gives future import wiring an explicit mode
  boundary.

## Accepted Synthesis Persistence Adapter

- `GTFSRouteSystemBuilder.apply_synthesized_route_geometries()` now adapts accepted `SynthesizedPatternGeometry`
  results onto the existing in-memory `Pattern`, `Trip`, and `Link` objects before `save_to_disk()`.
- Rejected or unsynthesized patterns are pruned from `select_patterns`, `select_trips`, and `select_links` when this
  adapter is used. Accepted patterns receive synthesized route geometry, WKB-backed `pattern_mapping` rows, synthesized
  route-link geometries, and trips/schedules trimmed to retained stops.
- The adapter reuses the current persistence methods for `routes`, `route_links`, `pattern_mapping`, `trips`, and
  `trips_schedule`; it does not add new database tables or direct SQL write paths.

## Shape-Guided Happy Path

- `resolve_pattern_loaded_shape()` selects the first loaded GTFS shape referenced by a pattern trip.
- `build_route_map_matcher()` prepares a route-type modal matcher for retained pattern stops.
- `synthesize_shape_guided_pattern_geometry()` map-matches each consecutive retained stop pair against the source shape
  and classifies accepted segments as `gtfs-shape`.
- `synthesize_pattern_geometry()` prefers the shape-guided branch when a loaded shape exists and falls back to
  stop-to-stop inference with `shape-guided-unavailable` diagnostics when shape matching fails.
- Shape rejection reasons include `shape-disconnected-match` and `shape-route-type-incompatible`.
- A real local `shapes.txt` feed is still absent; synthetic fixtures and monkeypatched matcher tests cover the branch.

## Diagnostic Persistence Decision

- Per-segment quality diagnostics will remain in memory and/or report artifacts for this change.
- Persistence wiring should use diagnostics to gate writes: accepted source-shaped, inferred-preferred, and
  inferred-fallback patterns can be written; rejected patterns and rejected segments must be skipped and reported.
- Durable diagnostic tables are deferred. If users later need per-segment quality diagnostics inside the project
  database, that should be handled by a separate database-migration change.
