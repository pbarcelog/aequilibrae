## Context

AequilibraE can load GTFS service data, build route patterns from ordered stop sequences, and map-match patterns against
project network links. The current Karlsruhe GTFS feed available for investigation does not include `shapes.txt`, so it
can describe lines, trips, stops, and schedules but not the physical path between stops. Assignment workflows still need
route geometry, `route_links`, and `pattern_mapping` records that connect transit service to the project network.

The objective is not a perfect public-transport model. The objective is to automate a first model-ready draft that can
produce qualitative assignment results and expose diagnostics for later editing, calibration, and review.

## Goals / Non-Goals

**Goals:**

- Use GTFS `shapes.txt` as the preferred source of route geometry when available.
- Synthesize route geometry and network link sequences when GTFS shapes are absent.
- Infer stop-to-stop paths using the project network and route-type modal correspondence.
- Prefer main-street or higher-priority paths when they are plausible, while allowing lower-priority links when the
  preferred path is unavailable or excessively circuitous.
- Persist accepted synthesized routes into the transit database in the same tables used by current GTFS import:
  `routes`, `route_links`, `pattern_mapping`, `trips`, and `trips_schedule`.
- Record quality diagnostics so users can distinguish source-shaped, inferred, fallback, trimmed, and rejected segments.

**Non-Goals:**

- Exact replication of observed vehicle paths when GTFS shapes are absent.
- Automatic editing of the project network to add missing streets, rail links, stops, or connectors.
- External routing, geocoding, map matching, or enrichment services.
- Calibration of demand, public-transport capacity, frequencies, fares, or assignment results.
- Treating inferred geometry as authoritative source truth.

## Decisions

1. **Separate diagnostic mode from inference/import mode.**

   Coverage diagnostics remain conservative and can reject internal gaps without creating substitute routes. Inference
   mode is explicit and attempts to bridge stop-to-stop gaps through the project network using documented heuristics.
   This avoids mixing "what is directly covered" with "what we inferred to make a first assignment-ready model".

2. **Prefer GTFS shapes when present.**

   When `shapes.txt` is available and trips reference shape IDs, those shapes should guide the link sequence and route
   geometry. The matcher should still validate that matched links are topologically connected and compatible with the
   route type. The current local Karlsruhe feed has no `shapes.txt`, so a future shape-bearing fixture is needed before
   this branch can be fully tuned.

3. **Use stop-to-stop shortest paths when shapes are absent.**

   For each accepted GTFS route pattern, consecutive matched stops should be connected through shortest paths on the
   project network. Distance is the initial cost because it is stable and available on links, and because this workflow
   targets qualitative first results rather than calibrated travel times.

4. **Score alternative paths by street priority and detour.**

   The inferencer should compare at least two path candidates when the network exposes useful priority information:

   - a preferred-path candidate using route-type modal links and main-street or higher-priority links;
   - a fallback candidate allowing lower-priority compatible links.

   If the preferred path exists and its distance is not more than the configured detour ratio over the fallback path,
   the preferred path should be used. The initial detour-ratio default should be 2.0, meaning the preferred path can be
   up to 100% longer than the fallback before the inferencer chooses the fallback. If the preferred path is unavailable,
   the fallback may be used and flagged.

5. **Keep priority classification configurable and data-driven.**

   The code should not assume one universal "main street" taxonomy. It should accept project fields such as link type,
   functional class, mode set, or importer-provided source fields when present. The first implementation can define a
   default priority extractor for existing AequilibraE link fields and allow callers to override it.

6. **Persist inference quality, not only geometry.**

   Transit service tables already hold route geometry and pattern mapping. This change should avoid schema changes in
   the first implementation if existing fields can carry required route and mapping data. Quality diagnostics can remain
   in memory or be exported as reports unless persistence is needed later. If durable per-segment quality storage becomes
   required, it should be handled by a separate database-migration change.

7. **Reject only when inference is not defensible.**

   A segment should be rejected when stops cannot be matched to the project network, no connected path exists, the path
   exceeds configured maximum distance/detour limits, or the route type has no usable correspondence. Pattern import
   should fail or be skipped with diagnostics when required segments are rejected.

## Risks / Trade-offs

- **Inferred routes may differ from real-world service paths.** -> Store quality diagnostics and make inferred/fallback
  segments visible for review.
- **Main-street preference can overfit private-network hierarchy.** -> Keep the priority rule configurable and compare
  against unrestricted fallback paths.
- **Fallback routing through secondary streets can make PT service look more precise than it is.** -> Flag fallback
  segments and expose summary counts.
- **GTFS shapes may not align cleanly with the model network.** -> Validate topology and fall back to stop-to-stop
  inference only with explicit diagnostics.
- **Route synthesis can be expensive for large feeds.** -> Cache stop matches, graph objects, and repeated stop-pair
  paths; group identical patterns before routing.
- **Transit database schema changes are risky.** -> Avoid schema changes for the first implementation and keep quality
  reports separate unless a durable storage need is proven.
- **No local shape-bearing GTFS example is currently available.** -> Add a todo to obtain or create a small fixture with
  `shapes.txt` before finalizing shape-guided behavior.
