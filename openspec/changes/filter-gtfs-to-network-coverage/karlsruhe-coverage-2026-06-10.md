# Karlsruhe GTFS Coverage Checkpoint

## Inputs

- Project: `.karlsruhe-geojson-default-modes-20260610-apply-2`
- GTFS feed: `C:\Users\Pablo Barceló\Downloads\Karlsruhe\google_transit`
- Service date: `2026-06-10`
- Modal-link threshold: 25 m
- Any-link model-range threshold: 100 m
- Workflow: diagnostic-only text-file scan of active GTFS trips, followed by `gtfs_coverage` stop classification and
  pattern decisions against the scratch project's network links.

## Feed Scope

- Active services: 186
- Active trips: 11,141
- Route patterns: 1,922

### Patterns By Route Type

| Route type | Patterns |
| --- | ---: |
| 0 | 73 |
| 2 | 366 |
| 3 | 1,483 |

## Pattern Decisions

| Route type | Decision | Patterns |
| --- | --- | ---: |
| 0 | fully-covered | 4 |
| 0 | trim-covered | 13 |
| 0 | internal-gap | 52 |
| 0 | network-discontinuity | 4 |
| 2 | fully-covered | 13 |
| 2 | trim-covered | 32 |
| 2 | internal-gap | 306 |
| 2 | network-discontinuity | 15 |
| 3 | fully-covered | 56 |
| 3 | trim-covered | 170 |
| 3 | internal-gap | 1,257 |

No unsupported route types were present in the active pattern set.

## Stop Classifications

| Route type | Stop status | Stops |
| --- | --- | ---: |
| 0 | matched-modal-link | 1,212 |
| 0 | ambiguous | 55 |
| 0 | near-model-no-modal-link | 141 |
| 0 | outside-model-range | 40 |
| 2 | matched-modal-link | 6,551 |
| 2 | near-model-no-modal-link | 1,576 |
| 2 | outside-model-range | 2,126 |
| 3 | matched-modal-link | 1,559 |
| 3 | ambiguous | 6 |
| 3 | near-model-no-modal-link | 1,305 |
| 3 | outside-model-range | 16,113 |

## Largest Route-Level Rejection Groups

| Route type | Route ID | Decision | Patterns |
| --- | --- | --- | ---: |
| 2 | `22-304-E-j26-15` | internal-gap | 79 |
| 2 | `22-305-E-j26-15` | internal-gap | 71 |
| 3 | `12-231-C-j26-1` | internal-gap | 38 |
| 3 | `32-125-C-j26-1` | internal-gap | 34 |
| 3 | `25-155-C-j26-11` | internal-gap | 32 |
| 3 | `30-227-C-j26-11` | internal-gap | 31 |
| 3 | `15-268-C-j26-1` | internal-gap | 27 |
| 0 | `21-7-E-j26-9` | internal-gap | 27 |

## Review Decision

The first implementation should remain diagnostic-only. The Karlsruhe run shows broad regional-feed coverage mismatch,
especially for bus route type `3`, where most stops are outside the model range and 1,257 patterns have internal gaps.
Wiring accepted or trimmed patterns into persistent GTFS import before reviewing these diagnostics would risk importing
a small and potentially misleading subset while many route variants remain rejected for internal coverage gaps.
