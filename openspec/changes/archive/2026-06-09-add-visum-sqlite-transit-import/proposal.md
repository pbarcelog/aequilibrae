## Why

The Karlsruhe VISUM SQLite export contains populated public-transport lines, stops, route patterns, vehicle journeys,
and timetable data, but the current VISUM SQLite importer only builds the private-traffic network and leaves
`public_transport.sqlite` initialized but empty.

Importing VISUM public transport data into AequilibraE's existing transit database would let users carry a richer VISUM
model forward into transit graph, preload, and assignment workflows without first converting the source model to GTFS.

## What Changes

- Add a VISUM SQLite public-transport import workflow that reads VISUM stop, line-route, time-profile, and vehicle
  journey tables.
- Populate AequilibraE transit service tables in `public_transport.sqlite`, including agencies, stops, routes,
  route links, pattern mappings, trips, and trip schedules.
- Use preserved VISUM source identifiers from the already-imported network (`visum_node_no`, `visum_link_no`,
  `visum_zone_no`) to map VISUM line routes and stop points onto AequilibraE network records.
- Convert VISUM transit system codes such as `BUS`, `TRAM`, and `TRAIN` into AequilibraE/GTFS-style transit route types
  with configurable defaults.
- Report unsupported VISUM public-transport objects, including fare details, vehicle blocking/coupling, detailed
  transfer rules, and multi-calendar semantics, as deferred scope rather than silently dropping them.
- Add focused tests, documentation, and diagnostics for VISUM SQLite transit imports.

## Capabilities

### New Capabilities

- `visum-sqlite-transit-import`: Covers importing VISUM SQLite public-transport stops, line routes, patterns, trips, and
  schedules into AequilibraE's transit database.

### Modified Capabilities

- `transit-gtfs`: Extends the transit service-data storage contract so `public_transport.sqlite` may be populated by
  supported non-GTFS importers in addition to GTFS.

## Impact

- Affected code areas: `aequilibrae/project/network/visum_sqlite_importer.py`, possible new VISUM transit importer
  modules, `aequilibrae/transit/`, transit database writes, and importer diagnostics.
- Affected data systems: `project_database.sqlite` source-reference columns and `public_transport.sqlite` transit
  service tables.
- Affected docs/tests: VISUM SQLite import documentation, public transport docs, compact VISUM-like SQLite fixtures,
  Karlsruhe opt-in smoke checks, and transit graph/preload readiness tests.
- No breaking API changes are intended. Existing GTFS import and private-traffic VISUM SQLite import behavior should
  remain compatible.
