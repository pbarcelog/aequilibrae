## 1. Geometry Source Inventory

- [x] 1.1 Inventory current GTFS loader support for `shapes.txt`, trip shape IDs, route shapes, stop patterns, and map-matching inputs.
- [x] 1.2 Identify or extend reusable route-pattern diagnostics from `filter-gtfs-to-network-coverage` for synthesis input.
- [x] 1.3 Define data structures for synthesized pattern geometry, segment paths, pattern mapping rows, and per-segment quality diagnostics.
- [x] 1.4 Add synthetic GTFS fixtures for both shape-bearing and no-shape feeds.

## 2. Shape-Guided Happy Path

- [ ] 2.1 Implement shape-guided route synthesis when GTFS `shapes.txt` is present and trips reference usable shape IDs.
- [ ] 2.2 Validate shape-guided link sequences for route-type compatibility, connectivity, and retained stop coverage.
- [ ] 2.3 Add diagnostics for missing shapes, shape mismatch, disconnected shape matches, and route-type incompatibility.
- [ ] 2.4 Add tests for successful shape-guided synthesis and fallback from unusable shapes.
- [ ] 2.5 Record the lack of a real local `shapes.txt` example as a validation todo and keep synthetic coverage explicit.

## 3. Stop-To-Stop Inference

- [ ] 3.1 Implement stop matching for retained GTFS pattern stops against route-type modal links and fallback compatible links.
- [ ] 3.2 Build stop-to-stop shortest path reconstruction over the project network using distance as the initial routing cost.
- [ ] 3.3 Assemble segment paths into route geometry, route links, and pattern mapping candidates.
- [ ] 3.4 Reject segments or patterns that cannot match stops, cannot connect stop pairs, or violate configured maximum thresholds.
- [ ] 3.5 Add focused tests for connected inference, unmatched stops, disconnected stop pairs, and excessive detours.

## 4. Street-Priority Preference

- [ ] 4.1 Add configurable priority extraction for main-street or higher-priority links using available project fields.
- [ ] 4.2 Compare preferred-path and fallback-path candidates for each stop pair.
- [ ] 4.3 Choose preferred paths when they are within the configured detour ratio, initially 2.0.
- [ ] 4.4 Choose and flag fallback paths when preferred paths are unavailable or more than 100% longer than fallback paths.
- [ ] 4.5 Add tests for preferred-path selection, fallback selection, unavailable preferred paths, and configurable priority fields.

## 5. Persistence And Review Checkpoint

- [ ] 5.1 Wire accepted synthesized patterns into GTFS import persistence for `routes`, `route_links`, `pattern_mapping`, trips, and schedules.
- [ ] 5.2 Keep diagnostic-only analysis available separately from inference/import mode.
- [ ] 5.3 Produce quality summaries by pattern, route, route type, geometry source, fallback reason, and rejection reason.
- [ ] 5.4 Run a Karlsruhe no-shapes synthesis review checkpoint and compare inferred output with prior coverage diagnostics.
- [ ] 5.5 Decide whether per-segment quality diagnostics need durable database storage or can remain report artifacts.

## 6. Documentation And Validation

- [ ] 6.1 Document GTFS geometry synthesis modes: source-shaped, inferred-preferred, inferred-fallback, and rejected.
- [ ] 6.2 Document the qualitative-modeling assumptions and limitations for no-shape GTFS feeds.
- [ ] 6.3 Run focused transit synthesis tests and relevant GTFS import/map-matching tests.
- [ ] 6.4 Run relevant GeoJSON/network integration tests for route-type mode alignment and network graph compatibility.
- [ ] 6.5 Run OpenSpec validation/status checks and confirm the change is apply-ready or apply-complete according to scope.
