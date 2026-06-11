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
