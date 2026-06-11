## ADDED Requirements

### Requirement: GTFS route geometry is synthesized for assignment-ready import
The system SHALL produce route geometry and network link sequences for GTFS route patterns before imported service is
used for transit graph creation or assignment.

#### Scenario: Importing route patterns with network geometry
- **WHEN** GTFS route patterns are accepted for network-based import
- **THEN** the system SHALL create route geometry, route-link records, and pattern-to-network mapping records for the
  retained pattern stops
- **AND** the generated data SHALL satisfy the transit service table contracts required by transit graph creation

#### Scenario: Reporting geometry synthesis results
- **WHEN** GTFS route geometry synthesis completes
- **THEN** the system SHALL report counts of source-shaped, inferred, fallback, trimmed, and rejected patterns
- **AND** report segment-level reasons for fallback or rejection

### Requirement: GTFS shapes guide route synthesis when available
The system SHALL use GTFS `shapes.txt` as the preferred route-geometry source when a route pattern's trips reference
usable shape IDs.

#### Scenario: Using GTFS shape geometry
- **WHEN** a GTFS trip references a shape from `shapes.txt`
- **AND** the shape can be matched to a connected route-type-compatible project-network link sequence
- **THEN** the system SHALL use the shape-guided link sequence and geometry for the route pattern
- **AND** classify the pattern geometry source as source-shaped

#### Scenario: Falling back from unusable GTFS shapes
- **WHEN** a GTFS shape is missing, disconnected from the project network, incompatible with the route type, or fails
  configured quality thresholds
- **THEN** the system SHALL NOT silently accept the failed shape match
- **AND** either attempt configured stop-to-stop inference or reject the affected pattern with diagnostics

#### Scenario: Tracking missing shape examples
- **WHEN** implementation validation lacks a local GTFS fixture with `shapes.txt`
- **THEN** the system SHALL keep shape-guided behavior testable with synthetic fixtures
- **AND** document that a real shape-bearing feed remains an important validation todo

### Requirement: GTFS routes can be inferred from ordered stops when shapes are absent
The system SHALL infer route geometry from ordered GTFS stop patterns and the project network when GTFS shapes are not
available.

#### Scenario: Inferring stop-to-stop paths
- **WHEN** a GTFS route pattern has ordered retained stops but no usable GTFS shape
- **AND** at least two retained stops remain after any coverage trimming
- **THEN** the system SHALL match retained stops to the project network
- **AND** compute connected stop-to-stop paths between consecutive retained stops
- **AND** assemble those segment paths into a route geometry and network link sequence

#### Scenario: Rejecting patterns without enough retained stops
- **WHEN** coverage trimming leaves fewer than two retained GTFS stops for a route pattern
- **THEN** the system SHALL reject the pattern before assignment-ready geometry synthesis
- **AND** report the pattern as insufficient for route geometry rather than as an accepted trimmed pattern

#### Scenario: Rejecting indefensible inferred segments
- **WHEN** a retained stop cannot be matched, a stop pair cannot be connected, or every candidate path violates
  configured inference thresholds
- **THEN** the system SHALL reject the affected segment or pattern
- **AND** report the stop pair and threshold reason that prevented synthesis

### Requirement: Inferred routes prefer plausible main-street paths
The system SHALL prefer higher-priority or main-street paths for inferred GTFS route segments when they are plausible.

#### Scenario: Choosing a preferred main-street path
- **WHEN** both a preferred path and a fallback path connect a consecutive GTFS stop pair
- **AND** the preferred path distance is within the configured detour ratio relative to the fallback path
- **THEN** the system SHALL choose the preferred path
- **AND** record the segment as inferred-preferred

#### Scenario: Choosing a fallback secondary-street path
- **WHEN** the preferred path is unavailable or exceeds the configured detour ratio relative to the fallback path
- **THEN** the system SHALL use the fallback path when it satisfies all other inference thresholds
- **AND** record the segment as inferred-fallback

#### Scenario: Configuring route priority rules
- **WHEN** a project exposes link fields or source attributes that identify route priority, facility type, or
  main-street status
- **THEN** the system SHALL allow those fields to guide preferred-path selection
- **AND** SHALL NOT require one hardcoded link-type taxonomy for all projects

### Requirement: Synthesized GTFS routes preserve transparent quality diagnostics
The system SHALL retain enough diagnostics for users to review, edit, or reject inferred GTFS route geometry.

#### Scenario: Preserving per-segment quality
- **WHEN** a route segment is synthesized
- **THEN** the system SHALL report the geometry source, selected path distance, alternative path distance when
  available, detour ratio, matched stop references, and any fallback reason

#### Scenario: Preserving conservative labels for inferred data
- **WHEN** a route pattern includes inferred or fallback geometry
- **THEN** the system SHALL distinguish inferred geometry from source-shaped geometry in diagnostics
- **AND** SHALL NOT present inferred geometry as exact source-provided route geometry
