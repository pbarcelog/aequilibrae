## Context

VISUM GeoJSON link and connector layers encode directional transport-system availability in `TSYSSET` and
`R_TSYSSET`. The existing GeoJSON importer can map arbitrary source transport-system tokens through `mode_mapping`,
but its default only includes private-traffic systems (`CAR`, `HGV`). Karlsruhe GeoJSON contains public-transport
systems such as `BUS`, `TRAM`, `TRAIN`, and `PUTW`, so a default import silently remains private-traffic oriented
unless the caller already knows to provide a broader mapping.

AequilibraE GTFS import stores public transport service in `public_transport.sqlite`. When GTFS route map matching is
enabled, the matcher filters project network links by mode ID using the GTFS route type correspondence. That means the
GeoJSON network mode mapping and GTFS route-type mapping must agree before GTFS service can be reliably matched to a
GeoJSON-built network.

## Goals / Non-Goals

**Goals:**

- Import all supported VISUM GeoJSON transport systems by default.
- Allow callers to restrict the import to a declared set of transport systems of interest.
- Preserve deterministic user overrides for source transport-system to AequilibraE mode mapping.
- Align public-transport mapping with GTFS route-type semantics for bus, tram/light-rail, and rail.
- Keep diagnostics explicit when source transport systems are unsupported, ignored, filtered out, or overridden.

**Non-Goals:**

- Import VISUM GeoJSON PT stops, line routes, or timetables.
- Import OD matrices from GeoJSON; OMX remains the matrix workflow.
- Clip, filter, or otherwise reduce a regional GTFS feed to the spatial coverage of the imported model.
- Add external street-name lookup, Google Maps enrichment, or fuzzy source-ID conflation.
- Change project database schemas, triggers, or mode ID length constraints.

## Decisions

1. **Default to all supported source transport systems.**

   The GeoJSON importer should use a broader default mapping instead of requiring every non-private token to be supplied
   by the caller. A proposed default source mapping is:

   - `CAR -> c`
   - `HGV -> h`
   - `BIKE -> b`
   - `WALK -> w`
   - `PUTW -> w`
   - `BUS -> t`
   - `TRAM -> l`
   - `TRAIN -> r`

   `t` is kept for bus/public transit because the existing project schema predefines mode `t` as `transit` and current
   GTFS bus map matching already uses `t`. `l` represents GTFS route type `0` (tram/streetcar/light rail), and `r`
   represents GTFS route type `2` (rail). Alternatives considered were mapping all PT systems to `t`, which is backward
   compatible but prevents mode-specific map matching, and mapping `BUS` to a new bus-specific letter, which conflicts
   less semantically but would break current GTFS bus expectations unless migrated everywhere at once.

2. **Use GTFS route type as the standard PT semantic layer.**

   VISUM PT tokens should be treated as source names that map onto GTFS-like categories. GTFS route types are the
   durable standard for the transit import path:

   - `0` tram/streetcar/light rail -> network mode `l`
   - `2` rail -> network mode `r`
   - `3` bus -> network mode `t`
   - existing supported bus-like route types remain mapped to `t` unless a more precise local mapping is introduced

   The GTFS route-type to mode mapping should be centralized or otherwise kept in sync with the GeoJSON default mapping.

3. **Add an explicit mode-interest filter rather than overloading ignored systems.**

   The importer should accept a parameter such as `transport_systems` or `systems_of_interest` that lists source
   `TSYSSET` tokens to import. When omitted, all supported tokens in the effective mapping are imported. When supplied,
   source tokens outside the list are filtered out with diagnostics. `ignored_transport_systems` remains useful for
   acknowledging unsupported tokens that the user wants to skip, but it should not be the main way to express a positive
   import subset.

4. **Keep user-provided `mode_mapping` authoritative.**

   If the caller provides `mode_mapping`, it should override the default mapping for those source tokens. The effective
   mapping is then filtered by any mode-interest parameter. This preserves existing advanced workflows, including merging
   `HGV` into car or mapping local PT categories to project-specific mode IDs.

5. **No database migration is required.**

   The existing `modes` table supports arbitrary single-character mode IDs, and the importer already creates or validates
   modes referenced by the mapping. New default PT mode IDs can be inserted during import like the current `HGV` default.

## Risks / Trade-offs

- **Existing users may rely on GeoJSON default imports being private-traffic only.** -> Mitigate with release notes,
  docs, and a positive transport-system filter example for `CAR`/`HGV`-only imports.
- **Mode letter semantics are constrained by existing defaults.** -> Keep `t` for bus/public transit compatibility and
  document `l`/`r` as GTFS-aligned PT submodes used for map matching.
- **GTFS feeds without `shapes.txt` depend heavily on map matching quality.** -> Ensure route-type matching selects the
  intended modal subgraph and leaves fallback geometry behavior unchanged when matching fails.
- **Regional GTFS feeds may be much larger than the GeoJSON graph.** -> This change only aligns modes. A supported route
  type can still fail map matching because some or all of its stops and segments fall outside the model coverage area.
  Route filtering, service-area clipping, and coverage-aware diagnostics remain separate workflow concerns unless later
  scoped.
- **Multiple PT tokens can appear on one VISUM link.** -> Preserve multi-mode link behavior by writing all mapped modes
  after filtering, using deterministic ordering.

## Open Questions

- Should a future GTFS workflow clip the feed by model extent, by imported zone polygons, by stop-to-link coverage, or by
  route-pattern coverage?
- Should out-of-coverage GTFS service be dropped before import, imported with straight-line geometry, or imported with
  explicit diagnostics that it is unsuitable for network-based assignment?
