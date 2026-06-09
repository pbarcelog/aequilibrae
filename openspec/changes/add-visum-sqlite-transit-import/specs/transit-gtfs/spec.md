## MODIFIED Requirements

### Requirement: Transit tables store imported service data
The system SHALL store imported transit service data in the transit database using the transit table specification for
all supported transit import sources.

#### Scenario: Storing GTFS route data
- **WHEN** GTFS route data is imported
- **THEN** the system SHALL store route patterns, agency references, route metadata, capacities, passenger-car equivalents, and route geometry

#### Scenario: Storing GTFS trip schedules
- **WHEN** GTFS trip schedules are imported
- **THEN** the system SHALL store trip IDs, sequence numbers, arrivals, and departures with trip relationships

#### Scenario: Storing supported non-GTFS transit service data
- **WHEN** a supported non-GTFS transit importer writes service data to the transit database
- **THEN** the system SHALL populate the transit service tables using the same route, pattern, trip, and schedule contracts required by transit graph creation
- **AND** preserve importer-specific source provenance through supported fields or diagnostics
