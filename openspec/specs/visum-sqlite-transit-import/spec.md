# visum-sqlite-transit-import Specification

## Purpose

Import VISUM SQLite public-transport service data into a project's transit database by mapping stops, lines, routes, and vehicle journeys to network records already imported with compatible VISUM source identifiers. Complements GTFS-based transit workflows; it does not replace GTFS import or route-geometry synthesis requirements under the transit GTFS capability.

## Requirements
### Requirement: VISUM SQLite transit source tables are validated
The system SHALL validate required VISUM SQLite public-transport source tables before importing transit service data.

#### Scenario: Importing with required source tables
- **WHEN** a VISUM SQLite transit import is requested with `STOP`, `STOPAREA`, `STOPPOINT`, `LINE`, `LINEROUTE`, `LINEROUTEITEM`, `TIMEPROFILE`, `TIMEPROFILEITEM`, `VEHJOURNEY`, `VEHJOURNEYSECTION`, `TSYS`, and `OPERATOR` tables
- **THEN** the system SHALL accept the source table set for transit import processing
- **AND** report the detected public-transport source objects and row counts

#### Scenario: Rejecting missing required source tables
- **WHEN** a VISUM SQLite transit import is requested without one or more required public-transport source tables
- **THEN** the system SHALL reject the transit import before writing transit service data
- **AND** report diagnostics naming the missing source tables

### Requirement: VISUM transit references are mapped to the imported network
The system SHALL map VISUM public-transport line-route and stop-point references to AequilibraE network records using
preserved VISUM source identifiers.

#### Scenario: Mapping line route nodes
- **WHEN** VISUM `LINEROUTEITEM.NODENO` values reference nodes in the imported project network
- **THEN** the system SHALL map those route items through the corresponding AequilibraE node records
- **AND** use the mapped network topology to create route-link and pattern-mapping records

#### Scenario: Mapping stop points
- **WHEN** VISUM `STOPPOINT` records reference a source node or source link that exists in the imported project network
- **THEN** the system SHALL create AequilibraE transit stops for those stop points
- **AND** preserve enough stop metadata to distinguish stop points that share a stop or stop area

#### Scenario: Rejecting insufficient network references
- **WHEN** the project network does not expose the VISUM source-reference columns or does not cover required line-route or stop-point references
- **THEN** the system SHALL reject the transit import before writing transit service data
- **AND** report source-reference coverage counts for the failed mapping

### Requirement: VISUM stops and operators are imported
The system SHALL import supported VISUM public-transport operators and stop points into AequilibraE transit tables.

#### Scenario: Importing operators as agencies
- **WHEN** VISUM `OPERATOR` records are present
- **THEN** the system SHALL create corresponding records in the `agencies` table
- **AND** use those agencies when importing related lines and trips

#### Scenario: Importing stop points
- **WHEN** VISUM stop, stop-area, and stop-point records are importable
- **THEN** the system SHALL create records in the `stops` table with stop identifiers, names, route type information, and point geometries
- **AND** associate stops with imported agencies and fare-zone metadata when representable by the current transit schema

### Requirement: VISUM line routes are imported as route patterns
The system SHALL import supported VISUM public-transport lines, line routes, and time profiles as AequilibraE route
patterns.

#### Scenario: Importing line route patterns
- **WHEN** a VISUM line-route and time-profile combination has an importable transit system and ordered route items
- **THEN** the system SHALL create a `routes` record for the corresponding AequilibraE pattern
- **AND** assign deterministic route, pattern, direction, route type, PCE, and capacity values

#### Scenario: Importing route links
- **WHEN** successive importable stops exist along a VISUM route pattern
- **THEN** the system SHALL create `route_links` records connecting the stop sequence
- **AND** store source-faithful route-link geometry where available or deterministic stop-to-stop geometry where route geometry is not represented in the transit schema

#### Scenario: Importing pattern mappings
- **WHEN** VISUM line-route node sequences map to imported AequilibraE network links
- **THEN** the system SHALL create `pattern_mapping` records that associate route patterns with project network link IDs and directions
- **AND** report diagnostics for any route segment that cannot be mapped to the imported network

### Requirement: VISUM vehicle journeys are imported as trips and schedules
The system SHALL import supported VISUM vehicle journeys into AequilibraE trip and trip-schedule records.

#### Scenario: Importing complete vehicle journeys
- **WHEN** a VISUM `VEHJOURNEY` references an importable line route and time profile
- **THEN** the system SHALL create a `trips` record for that vehicle journey
- **AND** create `trips_schedule` records from the referenced `TIMEPROFILEITEM` arrival and departure offsets

#### Scenario: Importing partial vehicle journeys
- **WHEN** a VISUM `VEHJOURNEY` specifies `FROMTPROFITEMINDEX` and `TOTPROFITEMINDEX`
- **THEN** the system SHALL trim the imported schedule to the referenced time-profile item range
- **AND** preserve the resulting stop sequence order in `trips_schedule.seq`

#### Scenario: Handling midnight rollovers
- **WHEN** a VISUM vehicle journey schedule crosses midnight
- **THEN** the system SHALL store monotonic arrival and departure values as seconds from the service-day start
- **AND** allow values greater than 24 hours when needed to preserve trip order

### Requirement: VISUM transit import reports deferred public-transport features
The system SHALL report recognized VISUM public-transport source features that are not imported into the current
AequilibraE transit schema.

#### Scenario: Reporting unsupported source features
- **WHEN** VISUM fare, transfer-walk-time, vehicle blocking, coupling, depot, or unsupported calendar tables contain records
- **THEN** the system SHALL report those source features as deferred transit-import scope
- **AND** SHALL NOT silently imply that those records were imported

### Requirement: VISUM transit imports are graph-ready
The system SHALL produce transit service data that can be used by existing AequilibraE transit graph and preload
workflows.

#### Scenario: Building a transit graph after import
- **WHEN** a VISUM SQLite transit import completes successfully
- **THEN** the imported `stops`, `routes`, `route_links`, `trips`, and `trips_schedule` tables SHALL contain the data required by `Transit.create_graph()`

#### Scenario: Computing preload after import
- **WHEN** transit preload is requested for a time window covered by imported VISUM vehicle journeys
- **THEN** the system SHALL be able to aggregate imported trips into link-direction preload values through existing preload logic

