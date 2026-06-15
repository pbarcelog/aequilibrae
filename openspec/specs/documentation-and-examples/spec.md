# Documentation And Examples Specification

## Purpose

This specification captures the current behavioral contract for documentation, examples, doctests, and documentation build workflows.
## Requirements
### Requirement: Documentation is Sphinx-based

The system SHALL maintain user documentation under the Sphinx documentation tree.

#### Scenario: Building documentation

- **WHEN** documentation is built locally or in CI
- **THEN** the system SHALL use `docs/source` as the source tree
- **AND** produce build outputs under the documentation build directory

### Requirement: API docs come from docstrings

The system SHALL expose public API documentation through autodoc-compatible docstrings.

#### Scenario: Documenting public APIs

- **WHEN** public classes, functions, or methods are documented
- **THEN** docstrings SHALL remain compatible with the Sphinx/reST style used by the project

#### Scenario: Changing public APIs

- **WHEN** public API behavior or signatures change
- **THEN** related docstrings and generated API documentation SHALL be updated

### Requirement: Examples remain executable

The system SHALL keep documentation examples aligned with executable project workflows.

#### Scenario: Running doctests

- **WHEN** documentation CI runs doctests
- **THEN** source docstrings and selected `.rst` examples SHALL execute successfully with the configured doctest fixtures

#### Scenario: Updating behavior used by examples

- **WHEN** behavior used by a documentation example changes
- **THEN** the corresponding example SHALL be updated or explicitly skipped with a clear reason

### Requirement: Gallery examples are maintained

The system SHALL maintain runnable gallery examples under the documentation examples tree.

#### Scenario: Building gallery documentation

- **WHEN** HTML documentation is built with gallery generation enabled
- **THEN** gallery examples SHALL be processed from `docs/source/examples`

### Requirement: Documentation deployment is controlled

The system SHALL publish documentation artifacts only through the configured CI deployment conditions.

#### Scenario: Building pull request documentation

- **WHEN** documentation CI runs for a pull request
- **THEN** it SHALL build documentation artifacts
- **AND** publish preview artifacts only when required secrets are available

#### Scenario: Building release documentation

- **WHEN** documentation CI runs for a release
- **THEN** it SHALL build release documentation artifacts
- **AND** publish release documentation only when required secrets are available

### Requirement: VISUM GeoJSON import is documented
The system SHALL document the VISUM GeoJSON import workflow and its traffic network scope, including selectable transport modes on network links and deferral of transit service layers.

#### Scenario: Documenting the import workflow
- **WHEN** the VISUM GeoJSON import API is added
- **THEN** user documentation SHALL describe required and optional layers, mapping configuration, CRS handling, assignment-ready field derivation, count-location import, multimodal network link modes, and deferred transit service and demand workflows

#### Scenario: Providing an executable example
- **WHEN** examples are updated for VISUM GeoJSON import
- **THEN** the documentation SHALL include an executable example or gallery script using compact local VISUM-like fixtures
- **AND** the example SHALL avoid external network downloads

### Requirement: VISUM SQLite import is documented
The system SHALL document the VISUM SQLite import workflow and its relationship to VISUM GeoJSON imports.

#### Scenario: Documenting the SQLite import workflow
- **WHEN** the VISUM SQLite import API is added
- **THEN** user documentation SHALL describe required and optional VISUM SQLite tables, CRS handling, mapping
  configuration, geometry reconstruction, assignment-field derivation, connector zero-time epsilon behavior,
  count-location scope, multimodal network link modes, and deferred transit service schedule tables and demand workflows

#### Scenario: Documenting connectivity validation
- **WHEN** VISUM SQLite import documentation is added
- **THEN** the documentation SHALL explain how SQLite source connectivity can be compared with SQLite-imported and
  GeoJSON-imported AequilibraE graph connectivity
- **AND** distinguish modal-connectivity validation from impedance or assignment-result comparison

#### Scenario: Providing an executable SQLite example
- **WHEN** examples are updated for VISUM SQLite import
- **THEN** the documentation SHALL include an executable example or gallery script using compact local VISUM-like SQLite
  fixtures
- **AND** the example SHALL avoid external network downloads

