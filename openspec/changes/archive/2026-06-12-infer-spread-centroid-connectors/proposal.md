## Why

Federated modelling workflows can provide a traffic network, zone polygons, centroids, and OMX demand without
centroid connectors. k-nearest attachment to the zone centroid does not reproduce the geographic nature of
real connector systems, which spread demand around zone perimeters with spacing rather than prioritising link
capacity or centroid proximity.

## What Changes

- Add a spread-based centroid connector placement heuristic for internal zones with polygon geometry.
- Scale connector counts from zone perimeter (typically 2–4), with optional demand-based +1 for high-demand zones.
- Prefer boundary-crossing endpoints and nodes closer to the polygon edge than to the polygon centre, with minimum
  spacing and a relaxed second pass when too few nodes are selected.
- De-prioritise motorway-class endpoints only as a tie-breaker.
- Keep external zones on global k=1 nearest attachment.
- Non-goals: matching VISUM connector IDs, capacity-feasibility against OMX totals, or assignment-equivalence
  validation (deferred).

## Capabilities

### New Capabilities

- `centroid-connector-inference`: spread-based connector placement when connectors are missing.

### Modified Capabilities

- None.

## Impact

- `aequilibrae/project/network/spread_connector_creation.py`
- `aequilibrae/project/network/connector_creation.py` (`insert_connector_pairs`)
- Karlsruhe opt-in validation under `tests/aeq/project/`
