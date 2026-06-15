## Context

Karlsruhe ground-truth analysis showed VISUM connectors are geographically spread (median ~150 m spacing),
edge-biased relative to polygon centres, weakly demand-correlated in count, and not capacity-ranked. Noise
against VISUM connector IDs is acceptable; the objective is equivalent connector *nature* for later assignment
studies.

## Goals / Non-Goals

**Goals:**

- Library API for spread placement on internal zones.
- Deterministic, explainable rules aligned with empirical findings.
- Reuse existing bulk connector persistence and infinite connector capacity.

**Non-Goals:**

- Exact reproduction of VISUM connector endpoints.
- OMX period vs link capacity feasibility checks.
- Assignment-based validation.

## Decisions

1. **Count:** `clamp(round(perimeter / 625 m), 2, 4)`; +1 (capped) for zones in the top demand quartile when OMX
   totals are supplied.
2. **Candidates:** in-zone network nodes supporting all requested modes.
3. **Ranking:** boundary endpoint bonus, edge score (`dist_to_center / dist_to_edge`), motorway tie-break penalty,
   then smaller edge distance.
4. **Spacing:** greedy ≥150 m; second pass ≥100 m if fewer than `min( target, 2 )` nodes selected.
5. **External zones:** `bulk_connector_creation` with `k_connectors=1`, `limit_to_zone=False`.

## Risks / Trade-offs

- High noise vs any single reference connector set → accepted; pair-recall is a diagnostic only.
- Default projected CRS is Web Mercator; callers in mid-latitude studies should pass a local metric CRS.
- Motorway detection uses link-type patterns and a high capacity threshold; may mis-rank atypical networks.

## Open Questions

- None for this change. Assignment-equivalence studies remain future work.
