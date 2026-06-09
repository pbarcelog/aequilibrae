## 1. Fixtures And Source Inspection

- [x] 1.1 Add compact VISUM-like SQLite fixtures covering operators, stops, stop areas, stop points, lines, line routes, route items, time profiles, vehicle journeys, and journey sections.
- [x] 1.2 Include fixture cases for partial vehicle journeys, midnight rollover schedules, route items without stops, and stop points mapped by node versus link.
- [x] 1.3 Add fixture project-network records with `visum_node_no`, `visum_link_no`, and `visum_zone_no` source-reference columns for deterministic mapping tests.
- [x] 1.4 Add source-table validation helpers that detect required VISUM public-transport tables and report row counts.

## 2. Importer API And Diagnostics

- [x] 2.1 Add a public VISUM SQLite transit import entry point on the transit gateway with a documented overwrite policy.
- [x] 2.2 Define a transit import report object for source row counts, inserted row counts, mapping coverage, unmapped records, deferred source features, and warnings.
- [x] 2.3 Validate that the target project network exposes compatible VISUM source-reference columns before writing transit service data.
- [x] 2.4 Implement transaction handling that rolls back failed transit imports and leaves the private-network database untouched.
- [x] 2.5 Remove or invalidate saved transit graphs when an overwrite import replaces service data.

## 3. Source Mapping

- [x] 3.1 Map VISUM `OPERATOR` records to AequilibraE `agencies`.
- [x] 3.2 Map VISUM `STOP`, `STOPAREA`, `STOPPOINT`, and fare-zone references to AequilibraE `stops` where representable.
- [x] 3.3 Map VISUM transit systems such as `BUS`, `TRAM`, and `TRAIN` to AequilibraE route types, PCEs, and capacities with override support.
- [x] 3.4 Map `LINEROUTEITEM.NODENO` sequences to imported project nodes using `visum_node_no`.
- [x] 3.5 Map `STOPPOINT` records to imported project nodes or links using `visum_node_no` and `visum_link_no`.
- [x] 3.6 Report unmapped transit systems, missing network source references, and unsupported source objects without silently dropping them.

## 4. Service Table Population

- [x] 4.1 Import line-route/time-profile combinations into `routes` as deterministic route patterns.
- [x] 4.2 Import successive stop pairs into `route_links` with stable sequence numbers and geometries.
- [x] 4.3 Import source network link sequences into `pattern_mapping` with correct AequilibraE link IDs and directions.
- [x] 4.4 Import VISUM vehicle journeys into `trips` with deterministic trip IDs and direction values.
- [x] 4.5 Convert `TIMEPROFILEITEM` arrival/departure offsets plus `VEHJOURNEY.DEP` into `trips_schedule` seconds from service-day start.
- [x] 4.6 Trim schedules according to `FROMTPROFITEMINDEX` and `TOTPROFITEMINDEX`.
- [x] 4.7 Preserve monotonic schedule values for journeys that cross midnight.

## 5. Graph And Preload Readiness

- [ ] 5.1 Add tests showing a successful VISUM transit import satisfies `Transit.create_graph()` required table checks.
- [ ] 5.2 Add tests showing imported schedules can be used by `Transit.build_pt_preload()` for a representative time window.
- [ ] 5.3 Add tests for graph-building failure diagnostics when required route, trip, or mapping data cannot be imported.

## 6. Karlsruhe Smoke Checks

- [ ] 6.1 Add an opt-in smoke test or validation script for `C:\Users\Pablo Barceló\Downloads\Karlsruhe\Karlsruhe-sqlite.sqlite3`.
- [ ] 6.2 Validate Karlsruhe source coverage for route items, stop points, route patterns, vehicle journeys, and inserted transit table counts.
- [ ] 6.3 Validate that the imported Karlsruhe transit data can build at least one transit graph over a practical time window.

## 7. Documentation

- [ ] 7.1 Document the VISUM SQLite transit import workflow, required prior network import, source-reference requirements, overwrite behavior, and deferred VISUM PT scope.
- [ ] 7.2 Add API docstrings for the public transit import entry point and report object.
- [ ] 7.3 Add or update an executable documentation example using compact local VISUM-like SQLite fixtures.
- [ ] 7.4 Update public transport database docs if new importer behavior changes table usage or provenance expectations.

## 8. Verification

- [ ] 8.1 Run focused VISUM SQLite transit importer unit tests.
- [ ] 8.2 Run focused transit graph and preload tests affected by the new import path.
- [ ] 8.3 Run focused VISUM SQLite private-network importer tests to guard compatibility.
- [ ] 8.4 Run relevant documentation/doctest checks for updated examples.
- [ ] 8.5 Run `openspec.cmd status --change add-visum-sqlite-transit-import` and resolve incomplete artifacts before implementation review.
