## Why

VISUM GeoJSON sources can include public-transport-capable links through `TSYSSET` values such as `BUS`, `TRAM`,
and `TRAIN`, but the current default import only maps private-traffic modes unless the caller provides an explicit
mapping. A GeoJSON graph that later receives GTFS service data needs coherent network modes for bus, tram, and rail
so GTFS map matching searches the intended network links.

## What Changes

- Change VISUM GeoJSON mode import semantics so the caller can request the transport systems of interest and, by
  default, imports all supported transport systems declared in the source.
- Define deterministic default mappings for supported VISUM transport systems, including public-transport systems,
  while preserving user overrides for custom mode IDs or ignored systems.
- Align public-transport defaults with GTFS route-type semantics so bus, tram, and rail service can be matched against
  the corresponding network modes.
- Update diagnostics so skipped, unsupported, overridden, or ignored transport systems are explicit in the import
  report.
- Update tests and user-facing documentation for GeoJSON graph import followed by GTFS public transport import.
- Non-goals: this change does not import VISUM GeoJSON stop/line/timetable layers, does not implement GTFS matrix
  import, does not clip or filter regional GTFS feeds to the model coverage area, and does not introduce external
  map/geocoding enrichment.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `visum-geojson-import`: change transport-system mapping requirements from private-traffic defaults to configurable
  all-supported defaults with user-selectable modes of interest.
- `transit-gtfs`: define how GTFS route types correspond to project network mode IDs for map matching and GeoJSON-built
  networks.

## Impact

- `aequilibrae/project/network/visum_geojson_importer.py` default mode mapping, validation, diagnostics, and report data.
- `aequilibrae/project/network/network.py` public API documentation for `create_from_visum_geojson(...)` parameters.
- `aequilibrae/transit/transit_elements/mode_correspondence.py` and GTFS map-matching behavior for route-type to mode
  selection.
- Tests under `tests/aeq/project/` and `tests/aeq/transit/`.
- Sphinx examples/docs that describe VISUM GeoJSON import and GTFS import workflows.
