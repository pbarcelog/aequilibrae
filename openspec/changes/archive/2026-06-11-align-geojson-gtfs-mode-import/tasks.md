## 1. GeoJSON Mode Import Semantics

- [x] 1.1 Inventory current VISUM GeoJSON mode mapping behavior, diagnostics, and tests for unmapped, ignored, and custom-mapped `TSYSSET` values.
- [x] 1.2 Expand the default VISUM GeoJSON transport-system mapping to include supported private, active, walk-access, bus, tram/light-rail, and rail systems.
- [x] 1.3 Add a positive transport-system filter parameter for caller-selected systems of interest while preserving `mode_mapping` overrides and `ignored_transport_systems`.
- [x] 1.4 Update import diagnostics and report fields to show effective mapping, filtered systems, ignored systems, and records skipped after filtering.
- [x] 1.5 Add focused GeoJSON importer tests for all-supported default import, private-only filtering, custom overrides, unknown tokens, and PT-only links.
- [x] 1.6 Re-import the Karlsruhe GeoJSON graph with default supported modes and inspect mode counts, PT link counts, and diagnostics as a review checkpoint.

## 2. GTFS Route-Type Mode Alignment

- [x] 2.1 Update GTFS route-type to network-mode correspondence for bus, tram/light-rail, and rail according to the design.
- [x] 2.2 Add tests that GTFS map matching selects the expected modal subgraph for route types `0`, `2`, and `3`.
- [x] 2.3 Verify unsupported GTFS route types are still skipped with warnings and do not block non-map-matched GTFS import.
- [x] 2.4 Run a Karlsruhe GTFS-to-GeoJSON-model exploration using the corrected mapping and summarize stop/link coverage by route type, distinguishing unsupported route types from supported routes outside model coverage, as a review checkpoint.

## 3. Documentation And Validation

- [x] 3.1 Update `create_from_visum_geojson(...)` API documentation for default mode import, systems-of-interest filtering, overrides, and ignored systems.
- [x] 3.2 Update Sphinx examples or narrative docs for a GeoJSON graph plus GTFS public-transport workflow.
- [x] 3.3 Run focused project and transit test subsets covering GeoJSON import and GTFS map matching.
- [x] 3.4 Run OpenSpec validation/status checks and confirm the change is apply-complete.
