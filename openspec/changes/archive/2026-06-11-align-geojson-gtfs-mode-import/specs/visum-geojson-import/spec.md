## MODIFIED Requirements

### Requirement: VISUM mappings are deterministic and configurable
The system SHALL use deterministic default mappings and allow user-provided overrides for VISUM transport systems,
link classes, and fields.

#### Scenario: Importing supported transport systems by default
- **WHEN** VISUM transport-system values are mapped to AequilibraE modes without a user-provided subset
- **THEN** the system SHALL map all supported source transport systems in imported network layers into
  single-character AequilibraE mode identifiers
- **AND** include supported public-transport systems such as bus, tram/light-rail, and rail in the default mapping
- **AND** create or validate the mapped AequilibraE modes before importing links or connectors that reference them
- **AND** report the effective mapping in the import diagnostics

#### Scenario: Filtering transport systems of interest
- **WHEN** a VISUM GeoJSON import is requested with an explicit set of source transport systems of interest
- **THEN** the system SHALL import only source transport-system tokens included in that set and supported by the
  effective mapping
- **AND** filter out other source transport-system tokens before deciding directional link and connector availability
- **AND** report transport systems and records skipped because of the requested filter
- **AND** skip records whose transport systems are all filtered out, with diagnostics that identify the skipped scope

#### Scenario: Mapping unknown transport systems
- **WHEN** imported VISUM private-traffic or public-transport network layers contain source transport-system values
  outside the effective mapping and outside the explicitly ignored set
- **THEN** the system SHALL report the unmapped transport-system values encountered
- **AND** require the caller to map, filter, or explicitly ignore those transport systems before import writes affected
  records to the project database

#### Scenario: Mapping heavy goods vehicles
- **WHEN** VISUM transport systems include `HGV`
- **THEN** the default mapping SHALL preserve `HGV` as a separate AequilibraE mode
- **AND** the system SHALL create or validate the mapped AequilibraE mode before importing links or connectors that
  reference it
- **AND** allow users to override the mapping to merge `HGV` into car mode when desired

#### Scenario: Mapping GTFS-aligned public transport systems
- **WHEN** VISUM transport systems include public transport tokens that correspond to GTFS route types
- **THEN** the default mapping SHALL assign those source tokens to AequilibraE mode IDs that are coherent with the
  GTFS route-type to network-mode correspondence
- **AND** allow users to override public-transport mappings when a project uses custom mode IDs

#### Scenario: Mapping link types
- **WHEN** VISUM link-class or type values are mapped to AequilibraE link types
- **THEN** the system SHALL create or validate corresponding AequilibraE link types according to the configured mapping
- **AND** report any unmapped link-type values that prevent import

#### Scenario: Avoiding runtime AI mapping
- **WHEN** the importer maps VISUM fields or values
- **THEN** the system SHALL use configured deterministic rules
- **AND** SHALL NOT require a runtime GenAI service to decide mappings
