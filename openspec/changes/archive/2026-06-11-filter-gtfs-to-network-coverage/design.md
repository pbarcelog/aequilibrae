## Context

AequilibraE can import GTFS service data and can map-match route patterns against a project network. After aligning
GeoJSON network modes with GTFS route types, the remaining Karlsruhe issue is not route-type support: the KVV GTFS feed
uses supported route types `0`, `2`, and `3`. The issue is coverage. The feed is regional, while the model network has
limited spatial and modal coverage, especially for bus.

GTFS provides ordered stops per trip in `stop_times.txt` through `trip_id` and `stop_sequence`. A GTFS route/line can
contain many different variants, so coverage must be evaluated at the route-pattern level rather than for a whole line.

## Goals / Non-Goals

**Goals:**

- Build deterministic GTFS route patterns from ordered stop sequences.
- Evaluate stop proximity to both route-type modal links and any model link.
- Distinguish outside-model coverage from near-model-but-not-modal coverage.
- Accept full patterns when all required stops are covered and the modal path is continuous.
- Allow conservative trimming when unmatched stops occur only at the beginning and/or end of a pattern.
- Reject patterns with internal unmatched stops or internal route discontinuities.
- Produce reviewable diagnostics before importing or map matching a filtered GTFS subset.

**Non-Goals:**

- Automatically modify the project network to add missing streets or transit links.
- Infer internal route detours through non-modeled streets.
- Import disconnected internal route fragments.
- Call external routing, geocoding, or map-enrichment services.
- Solve transfer, fare, frequency, or capacity modeling beyond preserving GTFS service data for accepted patterns.

## Decisions

1. **Use route patterns, not route rows, as the filtering unit.**

   Pattern identity should be derived from `route_id`, `direction_id` when available, and the ordered list of `stop_id`
   values sorted by `stop_sequence`. This respects branches, short turns, and service variants. Alternatives considered:
   filtering by `route_id` only, which is too coarse, or filtering by every `trip_id`, which duplicates identical stop
   sequences and makes diagnostics noisy.

2. **Classify every stop before deciding the pattern.**

   Each stop in a pattern should receive a status:

   - `matched-modal-link`: near a candidate link for the GTFS route type
   - `near-model-no-modal-link`: near some model link, but not the required modal subgraph
   - `outside-model-range`: farther than the configured any-link threshold
   - `ambiguous`: multiple candidate links are close enough and cannot be resolved deterministically
   - `unmatched`: no usable candidate under the configured matching rules

   Distances should be recorded in threshold bands rather than hidden behind one hard cutoff. The initial diagnostic
   defaults use a configurable 25 m modal-link match threshold, a configurable 100 m any-link model-range threshold,
   and 10 m, 25 m, 50 m, and 100 m diagnostic bands to help diagnose bus stop offsets and model simplification.

3. **Trim only prefix/suffix gaps.**

   If unmatched stops form only a prefix and/or suffix around one contiguous matched block, the pattern can be accepted
   as `trimmed` for the model coverage area. If unmatched stops occur inside the retained matched block, the pattern is
   rejected as an `internal-gap`. This avoids inventing a simpler route through missing internal streets.

4. **Require continuity for accepted patterns.**

   Matching stops to nearby links is not enough. The retained matched stop/link sequence must be connectable through the
   route-type modal graph. Patterns that cannot be connected are rejected as `network-discontinuity`.

5. **Keep filtering separate from full GTFS import initially.**

   The first implementation should produce diagnostics and a reusable filtered-pattern decision set in memory. Wiring
   this directly into persistent GTFS import is deferred until after diagnostics have been reviewed against Karlsruhe and
   synthetic fixtures.

## Risks / Trade-offs

- **Strict thresholds can reject valid bus service with offset stops.** -> Record multiple distance bands and make
  thresholds configurable rather than relying on one universal distance.
- **Loose thresholds can attach stops to the wrong road or direction.** -> Keep conservative defaults and classify
  ambiguous matches explicitly.
- **Pattern-level filtering may produce many diagnostics for large regional feeds.** -> Summarize by route type, route,
  pattern decision, and stop classification, while retaining source IDs for drill-down.
- **Continuity checks can be expensive on large modal graphs.** -> Start with candidate pruning and focused shortest-path
  checks between consecutive retained stops.
- **Trimmed patterns change the GTFS service envelope.** -> Report original and retained stop counts, retained stop
  sequence range, and reason for trimming.

## Open Questions

- Should route-type-specific default thresholds be introduced after Karlsruhe diagnostics, or is one configurable
  modal-link threshold sufficient for the first persistent workflow?
- Should reviewed coverage diagnostics be written as an optional artifact under the project folder after the Karlsruhe
  checkpoint, or remain an in-memory/reporting workflow?
