## ADDED Requirements

### Requirement: Spread-based centroid connector placement
The system SHALL provide spread-based centroid connector creation for zones with polygon geometry when explicit
connectors are not supplied.

#### Scenario: Internal zone connector count scales with perimeter
- **WHEN** spread connector creation is requested for internal zones with polygon geometry
- **THEN** the system SHALL target between 2 and 4 connectors per zone based on zone perimeter
- **AND** MAY add one additional connector for zones in the top demand quartile when zone demand totals are provided

#### Scenario: Internal zone connectors are geographically spread
- **WHEN** spread connector creation selects nodes inside a zone polygon
- **THEN** the system SHALL enforce a minimum spacing between selected connector nodes
- **AND** SHALL retry with relaxed spacing when fewer than two nodes can be placed
- **AND** SHALL prefer boundary-crossing link endpoints and nodes closer to the polygon edge than to the polygon centre
- **AND** SHALL NOT use link capacity as the primary selection criterion

#### Scenario: External zones use global nearest attachment
- **WHEN** spread connector creation is requested for external zones without local polygon geometry
- **THEN** the system SHALL create one globally nearest centroid connector per zone for each requested mode set

#### Scenario: Spread connectors persist as centroid links
- **WHEN** spread connector pairs are selected
- **THEN** the system SHALL insert bidirectional centroid connector links with infinite capacity for the requested modes
