## 1. Library API

- [x] 1.1 Add `SpreadConnectorConfig` and `bulk_spread_connector_creation`
- [x] 1.2 Add `select_spread_connector_pairs` for testability
- [x] 1.3 Add `insert_connector_pairs` helper in `connector_creation.py`

## 2. Heuristic tweaks

- [x] 2.1 Relaxed spacing second pass (100 m)
- [x] 2.2 Demand quartile +1 connector
- [x] 2.3 Motorway de-prioritisation tie-breaker

## 3. Validation

- [x] 3.1 Synthetic unit test for edge-biased spread selection
- [x] 3.2 Karlsruhe opt-in spread validation with OMX demand loading

## 4. OpenSpec

- [x] 4.1 Add centroid-connector-inference capability spec
- [x] 4.2 Archive change
