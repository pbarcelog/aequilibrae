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
