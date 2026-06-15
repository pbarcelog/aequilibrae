## ADDED Requirements

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
