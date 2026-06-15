## ADDED Requirements

### Requirement: GTFS route types select matching network modes
The system SHALL use deterministic GTFS route-type to AequilibraE network-mode correspondence when map matching GTFS
route patterns against a project network.

#### Scenario: Matching supported GTFS route types
- **WHEN** GTFS map matching is requested for a supported route type
- **THEN** the system SHALL select candidate project network links using the AequilibraE mode ID configured for that
  GTFS route type
- **AND** the default correspondence SHALL include bus route type `3`, tram/light-rail route type `0`, and rail route
  type `2`

#### Scenario: Aligning with GeoJSON-built networks
- **WHEN** a project network is built from VISUM GeoJSON with default supported public-transport mappings
- **THEN** GTFS route types for bus, tram/light-rail, and rail SHALL map-match against the corresponding imported
  public-transport network modes
- **AND** the correspondence SHALL NOT require VISUM public-transport stop, line, route, or timetable layers to be
  present

#### Scenario: Reporting unsupported GTFS route types
- **WHEN** GTFS map matching is requested for a route type without a network-mode correspondence
- **THEN** the system SHALL skip that route type for map matching
- **AND** report the skipped route type without preventing import of route, stop, trip, and schedule data that can be
  stored without map matching
