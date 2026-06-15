## 1. Pattern Extraction And Stop Classification

- [x] 1.1 Inventory existing GTFS reader/builder data structures for trips, routes, stops, stop times, route types, and map-matching inputs.
- [x] 1.2 Add or identify a reusable route-pattern representation based on `route_id`, `direction_id`, and ordered `stop_id` sequence.
- [x] 1.3 Implement configurable stop-to-link proximity classification against route-type modal links and any project network link.
- [x] 1.4 Add diagnostics for matched-modal, near-model-no-modal, outside-model-range, ambiguous, unmatched, and unsupported-route-type stops.
- [x] 1.5 Add focused tests for pattern grouping and stop classification using synthetic GTFS/network fixtures.

## 2. Conservative Pattern Decisions

- [x] 2.1 Implement pattern decision logic for fully covered, trim-covered, internal-gap rejected, network-discontinuity rejected, and unsupported-route-type skipped patterns.
- [x] 2.2 Ensure prefix/suffix trimming reports original stop count, retained stop count, retained stop-sequence range, and retained source stop IDs.
- [x] 2.3 Ensure internal unmatched stops are rejected and never pruned into a simplified substitute route.
- [x] 2.4 Add continuity checks over the route-type modal graph for retained matched stop/link sequences.
- [x] 2.5 Add focused tests for full coverage, prefix trim, suffix trim, both-end trim, internal gap rejection, and continuity rejection.

## 3. Karlsruhe Review Checkpoint

- [x] 3.1 Run GTFS coverage analysis for the Karlsruhe GTFS feed against the GeoJSON-built PT model.
- [x] 3.2 Summarize coverage decisions by route type, route identifier, and pattern decision.
- [x] 3.3 Summarize rejected pattern reasons, distinguishing outside-model coverage from near-model-no-modal coverage and network discontinuity.
- [x] 3.4 Review whether the first implementation should stop at diagnostics or feed accepted/trimmed patterns into persistent GTFS import.

## 4. Documentation And Validation

- [x] 4.1 Document GTFS coverage analysis, conservative trimming, internal-gap rejection, and model-coverage diagnostics.
- [x] 4.2 Run focused transit tests and relevant GeoJSON/GTFS integration tests.
- [x] 4.3 Run OpenSpec validation/status checks and confirm the change is apply-ready or apply-complete according to scope.
