from types import SimpleNamespace

import pandas as pd
import pytest
from shapely.geometry import LineString

from aequilibrae.transit.gtfs_coverage import (
    FULLY_COVERED,
    INTERNAL_GAP,
    MATCHED_MODAL_LINK,
    GTFSCoverageAnalysis,
    GTFSRoutePattern,
    PatternDecision,
    StopCoverage,
    build_gtfs_route_patterns,
)
from aequilibrae.transit.gtfs_route_synthesis import (
    GEOMETRY_SOURCE_INFERRED_PREFERRED,
    GTFSRouteSynthesisConfig,
    PatternMappingRow,
    SegmentPathDiagnostics,
    SynthesizedPatternGeometry,
    SynthesizedSegmentPath,
    inventory_gtfs_geometry_sources,
    route_pattern_synthesis_inputs,
)


def test_inventory_gtfs_geometry_sources_counts_shape_bearing_patterns(shape_bearing_gtfs_data):
    patterns = build_gtfs_route_patterns(shape_bearing_gtfs_data)

    inventory = inventory_gtfs_geometry_sources(shape_bearing_gtfs_data, patterns)

    assert inventory.has_shapes
    assert inventory.route_pattern_count == 2
    assert inventory.shape_count == 1
    assert inventory.trip_count == 2
    assert inventory.trips_with_shape_id == 2
    assert inventory.trips_with_loaded_shape == 1
    assert inventory.patterns_with_loaded_shape == 1
    assert inventory.patterns_without_loaded_shape == 1


def test_inventory_gtfs_geometry_sources_reports_no_shape_feed(no_shape_gtfs_data):
    patterns = build_gtfs_route_patterns(no_shape_gtfs_data)

    inventory = inventory_gtfs_geometry_sources(no_shape_gtfs_data, patterns)

    assert not inventory.has_shapes
    assert inventory.route_pattern_count == 1
    assert inventory.shape_count == 0
    assert inventory.trips_with_shape_id == 0
    assert inventory.patterns_without_loaded_shape == 1


def test_route_pattern_synthesis_inputs_keeps_only_accepted_coverage_decisions():
    accepted_pattern = _pattern("R1", ("A", "B"))
    rejected_pattern = _pattern("R2", ("C", "D"))
    analysis = GTFSCoverageAnalysis(
        patterns=(accepted_pattern, rejected_pattern),
        stop_coverage={
            accepted_pattern.key: _coverage_rows(accepted_pattern),
            rejected_pattern.key: _coverage_rows(rejected_pattern),
        },
        pattern_decisions={
            accepted_pattern.key: _decision(accepted_pattern, FULLY_COVERED),
            rejected_pattern.key: _decision(rejected_pattern, INTERNAL_GAP),
        },
    )

    inputs = route_pattern_synthesis_inputs(analysis)

    assert len(inputs) == 1
    assert inputs[0].pattern == accepted_pattern
    assert inputs[0].retained_stop_ids == ("A", "B")
    assert inputs[0].retained_internal_stop_ids == (1, 2)


def test_synthesis_result_data_structures_capture_segment_and_mapping_quality():
    pattern = _pattern("R1", ("A", "B"))
    diagnostic = SegmentPathDiagnostics(
        seq=0,
        from_stop_id="A",
        to_stop_id="B",
        status="ok",
        geometry_source=GEOMETRY_SOURCE_INFERRED_PREFERRED,
        selected_path_distance=100.0,
        preferred_path_distance=100.0,
        fallback_path_distance=80.0,
        detour_ratio=1.25,
        flags=("preferred-within-detour-ratio",),
    )
    geometry = LineString([(0, 0), (100, 0)])
    segment = SynthesizedSegmentPath(
        seq=0,
        from_stop_id="A",
        to_stop_id="B",
        from_internal_stop_id=1,
        to_internal_stop_id=2,
        link_ids=(10, 11),
        directions=(1, 1),
        geometry=geometry,
        geometry_source=GEOMETRY_SOURCE_INFERRED_PREFERRED,
        diagnostics=diagnostic,
    )
    mapping = (
        PatternMappingRow(pattern_id=1001, seq=0, link_id=10, direction=1, geometry=geometry),
        PatternMappingRow(pattern_id=1001, seq=1, link_id=11, direction=1, geometry=geometry),
    )

    result = SynthesizedPatternGeometry(
        pattern=pattern,
        coverage_decision=_decision(pattern, FULLY_COVERED),
        retained_stop_ids=("A", "B"),
        retained_internal_stop_ids=(1, 2),
        segments=(segment,),
        pattern_mapping=mapping,
        geometry=geometry,
        geometry_source=GEOMETRY_SOURCE_INFERRED_PREFERRED,
        accepted=True,
        diagnostics=(diagnostic,),
    )

    assert result.accepted
    assert result.segments[0].link_ids == (10, 11)
    assert result.pattern_mapping[1].link_id == 11
    assert result.diagnostics[0].detour_ratio == 1.25


def test_synthesis_config_defaults_match_initial_no_shape_assumptions():
    config = GTFSRouteSynthesisConfig()

    assert config.preferred_path_detour_ratio == 2.0
    assert config.distance_cost_field == "distance"
    assert "highway" in config.priority_fields


def _pattern(route_id, stop_ids):
    return GTFSRoutePattern(
        route_id=route_id,
        route_type=3,
        direction_id=0,
        stop_ids=stop_ids,
        internal_stop_ids=tuple(range(1, len(stop_ids) + 1)),
        trip_ids=(f"T-{route_id}",),
        internal_route_id=1,
    )


def _coverage_rows(pattern):
    return tuple(
        StopCoverage(
            route_id=pattern.route_id,
            route_type=pattern.route_type,
            direction_id=pattern.direction_id,
            stop_sequence=sequence,
            stop_id=stop_id,
            internal_stop_id=internal_stop_id,
            status=MATCHED_MODAL_LINK,
            nearest_link=sequence + 10,
            nearest_modal_link=sequence + 10,
            nearest_link_distance=0.0,
            nearest_modal_link_distance=0.0,
        )
        for sequence, (stop_id, internal_stop_id) in enumerate(
            zip(pattern.stop_ids, pattern.internal_stop_ids, strict=True)
        )
    )


def _decision(pattern, decision):
    retained = pattern.stop_ids if decision == FULLY_COVERED else ()
    retained_internal = pattern.internal_stop_ids if decision == FULLY_COVERED else ()
    retained_range = (0, len(pattern.stop_ids) - 1) if decision == FULLY_COVERED else None
    return PatternDecision(
        route_id=pattern.route_id,
        route_type=pattern.route_type,
        direction_id=pattern.direction_id,
        decision=decision,
        original_stop_count=len(pattern.stop_ids),
        retained_stop_count=len(retained),
        retained_sequence_range=retained_range,
        retained_stop_ids=retained,
        retained_internal_stop_ids=retained_internal,
    )


def _stop_times(source_stop_ids, internal_stop_ids):
    return pd.DataFrame(
        {
            "stop": source_stop_ids,
            "stop_id": internal_stop_ids,
            "stop_sequence": range(len(source_stop_ids)),
        }
    )


def _gtfs_data(shapes, trips, stop_times):
    return SimpleNamespace(
        routes={"R1": SimpleNamespace(route_id=1, route_type=3)},
        trips={"R1": trips},
        stop_times=stop_times,
        services={"WK": SimpleNamespace(dates={"2026-06-10"})},
        shapes=shapes,
    )


def _trip(trip_id, shape_id=""):
    return SimpleNamespace(
        trip=trip_id,
        route="R1",
        direction_id=0,
        service_id="WK",
        shape_id=shape_id,
    )

@pytest.fixture
def shape_bearing_gtfs_data():
    return _gtfs_data(
        shapes={"shape-1": LineString([(0, 0), (1, 1)])},
        trips={
            "hash-with-shape": [_trip("T-shaped", "shape-1")],
            "hash-missing-shape": [_trip("T-missing", "shape-missing")],
        },
        stop_times={
            "T-shaped": _stop_times(["A", "B"], [1, 2]),
            "T-missing": _stop_times(["A", "C"], [1, 3]),
        },
    )


@pytest.fixture
def no_shape_gtfs_data():
    return _gtfs_data(
        shapes={},
        trips={"hash-no-shape": [_trip("T-no-shape")]},
        stop_times={"T-no-shape": _stop_times(["A", "B"], [1, 2])},
    )
