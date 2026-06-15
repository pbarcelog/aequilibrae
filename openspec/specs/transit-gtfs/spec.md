# Transit GTFS Specification

## Purpose

This specification captures the current behavioral contract for GTFS import, transit databases, transit graph creation, and transit assignment support.
## Requirements
### Requirement: Transit database is available

The system SHALL ensure that every loaded project has a transit database available for public transport workflows.

#### Scenario: Loading transit gateway

- **WHEN** a project loads its transit gateway
- **THEN** the system SHALL create `public_transport.sqlite` if it does not exist
- **AND** initialize transit tables and triggers

### Requirement: GTFS route systems can be built

The system SHALL create GTFS route-system builders configured for the active project and agency.

#### Scenario: Creating a GTFS builder

- **WHEN** a GTFS builder is requested with agency, file path, day, and description
- **THEN** the system SHALL return a builder configured with default transit capacities and passenger-car equivalents
- **AND** connect builder progress signals to the transit gateway

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

### Requirement: Transit graphs are period-aware

The system SHALL create, save, remove, and load transit graphs by project network period.

#### Scenario: Creating a transit graph

- **WHEN** a transit graph is created without an explicit period
- **THEN** the system SHALL use the project's default period
- **AND** store the graph in the transit graph registry for that period

#### Scenario: Loading saved transit graphs

- **WHEN** saved transit graphs are loaded
- **THEN** the system SHALL load graph configurations for requested periods or all available periods

### Requirement: Transit preload can be computed

The system SHALL compute transit preload vectors over a requested time window.

#### Scenario: Computing preload

- **WHEN** transit preload is requested with start and end times
- **THEN** the system SHALL aggregate transit trips active in the requested window into link-direction preload values

#### Scenario: Selecting inclusion condition

- **WHEN** an inclusion condition is specified
- **THEN** the system SHALL include trips according to start, end, midpoint, or any-stop schedule logic as supported

### Requirement: Transit assignment is supported

The system SHALL support public transport assignment through transit classes and Optimal Strategies workflows.

#### Scenario: Executing transit assignment

- **WHEN** a transit assignment is configured with transit classes and required graph data
- **THEN** the system SHALL execute the selected transit assignment procedure
- **AND** expose assignment results through the assignment result interfaces

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

### Requirement: GTFS coverage analysis builds route patterns from stop sequences
The system SHALL evaluate GTFS network coverage using route patterns derived from ordered stop sequences.

#### Scenario: Building route patterns from trips
- **WHEN** GTFS coverage analysis is requested
- **THEN** the system SHALL group trips by `route_id`, `direction_id` when available, and ordered `stop_id` sequence
  sorted by `stop_sequence`
- **AND** SHALL preserve representative trip IDs and source route identifiers for diagnostics

#### Scenario: Preserving route variants
- **WHEN** two trips share a `route_id` but have different ordered stop sequences
- **THEN** the system SHALL evaluate them as separate route patterns

### Requirement: GTFS stops are classified against model coverage
The system SHALL classify each GTFS pattern stop against the project network and route-type modal subgraph.

#### Scenario: Classifying stops near modal links
- **WHEN** a GTFS pattern stop is within the configured modal-link matching threshold for the pattern route type
- **THEN** the system SHALL classify the stop as matched to a modal link
- **AND** record the candidate link reference and distance used for the match

#### Scenario: Classifying stops near model links but not modal links
- **WHEN** a GTFS pattern stop is near the project network but not within the configured threshold for the route-type
  modal subgraph
- **THEN** the system SHALL classify the stop as near the model but not near the modal graph
- **AND** report nearest-link and nearest-modal-link distances separately

#### Scenario: Classifying stops outside model range
- **WHEN** a GTFS pattern stop is farther than the configured model-range threshold from any project network link
- **THEN** the system SHALL classify the stop as outside model range
- **AND** report that classification separately from unsupported route types

#### Scenario: Classifying ambiguous stop matches
- **WHEN** multiple candidate modal links satisfy the stop matching rules and the match cannot be resolved
  deterministically
- **THEN** the system SHALL classify the stop as ambiguous
- **AND** report the competing candidate links and distances

### Requirement: GTFS patterns are conservatively accepted, trimmed, or rejected
The system SHALL use stop classifications and modal network continuity to decide whether a GTFS pattern can be used in
the project model.

#### Scenario: Accepting fully covered continuous patterns
- **WHEN** all stops in a GTFS pattern are matched to modal links
- **AND** the matched stop/link sequence is continuous through the route-type modal graph
- **THEN** the system SHALL classify the pattern as fully covered

#### Scenario: Trimming prefix and suffix gaps
- **WHEN** unmatched or outside-range stops occur only before the first retained matched stop or after the last retained
  matched stop
- **AND** the retained matched stop/link sequence is continuous through the route-type modal graph
- **THEN** the system SHALL classify the pattern as trim-covered
- **AND** report the original stop count, retained stop count, and retained stop-sequence range

#### Scenario: Rejecting internal unmatched stops
- **WHEN** unmatched, ambiguous, outside-range, or near-model-no-modal stops occur between retained matched stops in a
  GTFS pattern
- **THEN** the system SHALL reject the pattern as having an internal gap
- **AND** report the internal stop IDs and their classifications

#### Scenario: Rejecting modal network discontinuities
- **WHEN** pattern stops can be matched locally but the retained sequence cannot be connected through the route-type
  modal graph
- **THEN** the system SHALL reject the pattern as having a network discontinuity
- **AND** report the stop pair or segment where continuity failed

#### Scenario: Skipping unsupported route types
- **WHEN** a GTFS pattern has a route type without a network-mode correspondence
- **THEN** the system SHALL skip the pattern for network coverage analysis
- **AND** report the unsupported route type without treating it as an outside-model coverage problem

### Requirement: GTFS coverage analysis is diagnostic-first
The system SHALL report GTFS coverage decisions without silently simplifying internal route gaps.

#### Scenario: Reporting pattern decision summaries
- **WHEN** GTFS coverage analysis completes
- **THEN** the system SHALL report counts of fully covered, trim-covered, internally rejected, discontinuity rejected,
  and unsupported-route-type patterns
- **AND** summarize stop classifications by route type and route identifier

#### Scenario: Preserving conservative behavior
- **WHEN** a GTFS pattern contains internal coverage gaps or internal modal discontinuities
- **THEN** the system SHALL NOT create a simplified substitute route by pruning internal stops
- **AND** SHALL leave internal segment modeling to a separate explicit workflow

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

#### Scenario: Keeping diagnostic-only review separate
- **WHEN** GTFS route review is requested in diagnostic-only mode
- **THEN** the system SHALL report coverage and synthesis eligibility without producing inferred geometry
- **AND** SHALL require an explicit inference/import mode before route geometry or link sequences are synthesized

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

