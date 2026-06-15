## Implementation Notes

### Karlsruhe GeoJSON Re-import Checkpoint

Imported `C:\Users\Pablo Barceló\Downloads\Karlsruhe` into:

`C:\tmp\aequilibrae\.karlsruhe-geojson-default-modes-20260610-apply-2`

Default mode mapping used:

- `CAR -> c`
- `HGV -> h`
- `BIKE -> b`
- `WALK -> w`
- `PUTW -> w`
- `BUS -> t`
- `TRAM -> l`
- `TRAIN -> r`

Imported counts:

- nodes: 8,432
- zones: 726
- source links: 10,902
- connectors: 2,821
- project links total: 14,058
- links with any PT mode (`t`, `l`, or `r`): 5,395

Links by mode:

- `b`: 11,067
- `c`: 10,575
- `h`: 10,606
- `l`: 612
- `r`: 356
- `t`: 5,243
- `w`: 4,283

### Karlsruhe GTFS Coverage Checkpoint

The KVV GTFS feed contains only route types now supported by the default correspondence: `0`, `2`, and `3`.
There were no unsupported route types in the feed. Coverage problems are therefore model-extent or modal-coverage
issues, not route-type support issues.

Stop-to-modal-link coverage:

- route type `0` (`l`): 348 stops, 612 candidate links, median modal distance 4.34 m, 323 stops within 500 m,
  12 stops farther than 500 m from any model link
- route type `2` (`r`): 778 stops, 356 candidate links, median modal distance 17.41 m, 586 stops within 500 m,
  179 stops farther than 500 m from any model link
- route type `3` (`t`): 3,334 stops, 5,243 candidate links, median modal distance 2,347.32 m, 1,019 stops within
  500 m, 1,930 stops farther than 500 m from any model link

This confirms that a future GTFS preparation change should handle feed clipping, filtering, or coverage diagnostics
before full regional service is imported for assignment.
