from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from aequilibrae.transit.gtfs_coverage import (
    FULLY_COVERED,
    INSUFFICIENT_RETAINED_STOPS,
    INTERNAL_GAP,
    MATCHED_MODAL_LINK,
    GTFSCoverageAnalysis,
    GTFSRoutePattern,
    PatternDecision,
    StopCoverage,
    build_gtfs_route_patterns,
)
from aequilibrae.transit.gtfs_route_synthesis import (
    FALLBACK_PREFERRED_EXCESSIVE_DETOUR,
    FALLBACK_PREFERRED_UNAVAILABLE,
    FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED,
    GEOMETRY_SOURCE_INFERRED_PREFERRED,
    GEOMETRY_SOURCE_INFERRED_FALLBACK,
    GEOMETRY_SOURCE_REJECTED,
    GTFSRouteSynthesisCache,
    GTFSRouteSynthesisConfig,
    PatternMappingRow,
    REJECT_DISCONNECTED_STOP_PAIR,
    REJECT_EXCESSIVE_SEGMENT_DISTANCE,
    REJECT_INSUFFICIENT_RETAINED_STOPS,
    REJECT_UNMATCHED_STOP,
    SEGMENT_OK,
    SEGMENT_REJECTED,
    SegmentPathDiagnostics,
    SynthesizedPatternGeometry,
    SynthesizedSegmentPath,
    infer_stop_to_stop_segment,
    inventory_gtfs_geometry_sources,
    match_stop_to_network,
    route_pattern_synthesis_inputs,
    summarize_synthesized_patterns,
    synthesize_inferred_pattern_geometry,
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


def test_route_pattern_synthesis_inputs_excludes_insufficient_retained_stops():
    pattern = _pattern("R1", ("A",))
    analysis = GTFSCoverageAnalysis(
        patterns=(pattern,),
        stop_coverage={pattern.key: _coverage_rows(pattern)},
        pattern_decisions={pattern.key: _decision(pattern, INSUFFICIENT_RETAINED_STOPS)},
    )

    inputs = route_pattern_synthesis_inputs(analysis)

    assert inputs == ()


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


def test_summarize_synthesized_patterns_reports_quality_by_review_dimension():
    preferred = _synthesized_result("R1", GEOMETRY_SOURCE_INFERRED_PREFERRED)
    fallback = _synthesized_result(
        "R1",
        GEOMETRY_SOURCE_INFERRED_FALLBACK,
        fallback_reason=FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED,
    )
    rejected = _synthesized_result(
        "R2",
        GEOMETRY_SOURCE_REJECTED,
        accepted=False,
        rejection_reason=REJECT_INSUFFICIENT_RETAINED_STOPS,
        stop_ids=("X",),
    )

    summary = summarize_synthesized_patterns((preferred, fallback, rejected))

    assert len(summary.pattern_summary) == 3
    assert len(summary.segment_summary) == 2

    route_summary = summary.route_summary.set_index("route_id")
    assert route_summary.loc["R1", "pattern_count"] == 2
    assert route_summary.loc["R1", "accepted_patterns"] == 2
    assert route_summary.loc["R1", "inferred_preferred_segment_count"] == 1
    assert route_summary.loc["R1", "inferred_fallback_segment_count"] == 1
    assert route_summary.loc["R2", "rejected_patterns"] == 1

    route_type_summary = summary.route_type_summary.set_index("route_type")
    assert route_type_summary.loc[3, "pattern_count"] == 3
    assert route_type_summary.loc[3, "accepted_patterns"] == 2

    source_counts = summary.geometry_source_summary.set_index(["level", "geometry_source"])["count"]
    assert source_counts.loc[("pattern", GEOMETRY_SOURCE_INFERRED_PREFERRED)] == 1
    assert source_counts.loc[("pattern", GEOMETRY_SOURCE_INFERRED_FALLBACK)] == 1
    assert source_counts.loc[("pattern", GEOMETRY_SOURCE_REJECTED)] == 1
    assert source_counts.loc[("segment", GEOMETRY_SOURCE_INFERRED_PREFERRED)] == 1
    assert source_counts.loc[("segment", GEOMETRY_SOURCE_INFERRED_FALLBACK)] == 1

    fallback_reasons = summary.fallback_reason_summary.set_index("reason")
    assert fallback_reasons.loc[FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED, "segment_count"] == 1

    rejection_reasons = summary.rejection_reason_summary.set_index(["level", "reason"])
    assert rejection_reasons.loc[("pattern", REJECT_INSUFFICIENT_RETAINED_STOPS), "count"] == 1


def test_synthesis_config_defaults_match_initial_no_shape_assumptions():
    config = GTFSRouteSynthesisConfig()

    assert config.preferred_path_detour_ratio == 2.0
    assert config.distance_cost_field == "distance"
    assert "highway" in config.priority_fields


def test_match_stop_to_network_prefers_modal_links_before_fallback():
    links = _network_links()

    modal_match = match_stop_to_network(
        "A",
        1,
        Point(0, 0),
        route_type=3,
        network_links=links,
        config=GTFSRouteSynthesisConfig(stop_match_distance=5, fallback_stop_match_distance=25),
    )
    fallback_match = match_stop_to_network(
        "OFF",
        99,
        Point(50, 20),
        route_type=3,
        network_links=links,
        config=GTFSRouteSynthesisConfig(stop_match_distance=5, fallback_stop_match_distance=25),
    )

    assert modal_match.status == "matched-modal-link"
    assert modal_match.candidates[0].link_id == 10
    assert fallback_match.status == "matched-fallback-link"
    assert fallback_match.candidates[0].link_id == 99


def test_infer_stop_to_stop_segment_finds_fallback_shortest_distance_path():
    links = _network_links()
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("C", 3, Point(200, 0), 3, links)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links)

    assert segment.diagnostics.status == SEGMENT_OK
    assert segment.geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK
    assert segment.link_ids == (10, 11)
    assert segment.directions == (1, 1)
    assert segment.diagnostics.fallback_path_distance == 200.0
    assert list(segment.geometry.coords) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]


def test_synthesize_inferred_pattern_geometry_assembles_mapping_and_rejects_none():
    links = _network_links()
    pattern = _pattern("R1", ("A", "B", "C"))
    synthesis_input = _synthesis_input(pattern)
    stops = {
        1: SimpleNamespace(geo=Point(0, 0)),
        2: SimpleNamespace(geo=Point(100, 0)),
        3: SimpleNamespace(geo=Point(200, 0)),
    }

    result = synthesize_inferred_pattern_geometry(synthesis_input, stops, links, pattern_id=1001)

    assert result.accepted
    assert result.geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK
    assert [row.link_id for row in result.pattern_mapping] == [10, 11]
    assert [row.seq for row in result.pattern_mapping] == [0, 1]
    assert len(result.segments) == 2
    assert all(diagnostic.status == SEGMENT_OK for diagnostic in result.diagnostics)


def test_synthesize_inferred_pattern_geometry_rejects_unmatched_stops():
    links = _network_links()
    pattern = _pattern("R1", ("A", "B"))
    synthesis_input = _synthesis_input(pattern)
    stops = {
        1: SimpleNamespace(geo=Point(0, 0)),
        2: SimpleNamespace(geo=Point(500, 500)),
    }

    result = synthesize_inferred_pattern_geometry(
        synthesis_input,
        stops,
        links,
        config=GTFSRouteSynthesisConfig(stop_match_distance=5, fallback_stop_match_distance=10),
    )

    assert not result.accepted
    assert result.geometry_source == GEOMETRY_SOURCE_REJECTED
    assert result.rejection_reason == REJECT_UNMATCHED_STOP
    assert result.diagnostics[0].status == SEGMENT_REJECTED


def test_synthesize_inferred_pattern_geometry_rejects_single_retained_stop():
    links = _network_links()
    pattern = _pattern("R1", ("A",))
    synthesis_input = _synthesis_input(pattern)
    stops = {1: SimpleNamespace(geo=Point(0, 0))}

    result = synthesize_inferred_pattern_geometry(synthesis_input, stops, links)

    assert not result.accepted
    assert result.rejection_reason == REJECT_INSUFFICIENT_RETAINED_STOPS
    assert result.segments == ()
    assert result.pattern_mapping == ()


def test_infer_stop_to_stop_segment_rejects_disconnected_stop_pairs():
    links = _network_links(connected=False)
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("C", 3, Point(200, 0), 3, links)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links)

    assert segment.diagnostics.status == SEGMENT_REJECTED
    assert segment.diagnostics.reason == REJECT_DISCONNECTED_STOP_PAIR


def test_infer_stop_to_stop_segment_rejects_excessive_distance():
    links = _network_links()
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("C", 3, Point(200, 0), 3, links)

    segment = infer_stop_to_stop_segment(
        0,
        from_match,
        to_match,
        3,
        links,
        config=GTFSRouteSynthesisConfig(maximum_segment_distance=150),
    )

    assert segment.diagnostics.status == SEGMENT_REJECTED
    assert segment.diagnostics.reason == REJECT_EXCESSIVE_SEGMENT_DISTANCE
    assert segment.diagnostics.selected_path_distance == 200.0


def test_infer_stop_to_stop_segment_chooses_preferred_path_within_detour_ratio():
    links = _priority_network_links(priority_distance=150.0)
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("B", 2, Point(100, 0), 3, links)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links)

    assert segment.geometry_source == GEOMETRY_SOURCE_INFERRED_PREFERRED
    assert segment.link_ids == (20, 21)
    assert segment.diagnostics.selected_path_distance == 150.0
    assert segment.diagnostics.preferred_path_distance == 150.0
    assert segment.diagnostics.fallback_path_distance == 100.0
    assert segment.diagnostics.detour_ratio == 1.5
    assert segment.diagnostics.flags == ("preferred-within-detour-ratio",)


def test_infer_stop_to_stop_segment_falls_back_when_preferred_path_is_too_long():
    links = _priority_network_links(priority_distance=250.0)
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("B", 2, Point(100, 0), 3, links)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links)

    assert segment.geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK
    assert segment.link_ids == (10,)
    assert segment.diagnostics.reason == FALLBACK_PREFERRED_EXCESSIVE_DETOUR
    assert segment.diagnostics.preferred_path_distance == 250.0
    assert segment.diagnostics.fallback_path_distance == 100.0
    assert segment.diagnostics.detour_ratio == 2.5


def test_infer_stop_to_stop_segment_falls_back_when_preferred_path_unavailable():
    links = _priority_network_links(priority_distance=150.0, connected_priority=False)
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("B", 2, Point(100, 0), 3, links)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links)

    assert segment.geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK
    assert segment.link_ids == (10,)
    assert segment.diagnostics.reason == FALLBACK_PREFERRED_UNAVAILABLE
    assert segment.diagnostics.preferred_path_distance is None
    assert segment.diagnostics.fallback_path_distance == 100.0


def test_infer_stop_to_stop_segment_skips_priority_when_stop_context_is_secondary():
    links = _priority_network_links(priority_distance=150.0)
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links)
    to_match = match_stop_to_network("LOCAL", 2, Point(100, 30), 3, links)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links)

    assert segment.geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK
    assert segment.diagnostics.reason == FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED


def test_priority_extraction_uses_configurable_fields_and_values():
    links = _priority_network_links(priority_distance=150.0, priority_field="pt_priority", priority_value="yes")
    config = GTFSRouteSynthesisConfig(priority_fields=("pt_priority",), preferred_priority_values=("yes",))
    from_match = match_stop_to_network("A", 1, Point(0, 0), 3, links, config=config)
    to_match = match_stop_to_network("B", 2, Point(100, 0), 3, links, config=config)

    segment = infer_stop_to_stop_segment(0, from_match, to_match, 3, links, config=config)

    assert from_match.candidates[1].is_priority
    assert to_match.candidates[1].is_priority
    assert segment.geometry_source == GEOMETRY_SOURCE_INFERRED_PREFERRED
    assert segment.link_ids == (20, 21)


def test_synthesis_cache_reuses_stop_matches_graphs_and_stop_pair_paths():
    links = _network_links()
    pattern = _pattern("R1", ("A", "B", "C"))
    synthesis_input = _synthesis_input(pattern)
    stops = {
        1: SimpleNamespace(geo=Point(0, 0)),
        2: SimpleNamespace(geo=Point(100, 0)),
        3: SimpleNamespace(geo=Point(200, 0)),
    }
    cache = GTFSRouteSynthesisCache(links)

    first = synthesize_inferred_pattern_geometry(synthesis_input, stops, links, pattern_id=1001, cache=cache)
    second = synthesize_inferred_pattern_geometry(synthesis_input, stops, links, pattern_id=1002, cache=cache)
    stats = cache.stats

    assert first.accepted
    assert second.accepted
    assert stats.stop_match_misses == 3
    assert stats.stop_match_hits == 3
    assert stats.graph_builds == 1
    assert stats.path_misses == 2
    assert stats.path_hits == 2


def _synthesized_result(
    route_id,
    geometry_source,
    accepted=True,
    fallback_reason=None,
    rejection_reason=None,
    stop_ids=("A", "B"),
):
    pattern = _pattern(route_id, stop_ids)
    geometry = LineString([(0, 0), (100, 0)]) if accepted else None
    diagnostics = ()
    segments = ()
    mapping = ()
    if accepted:
        diagnostic = SegmentPathDiagnostics(
            seq=0,
            from_stop_id=stop_ids[0],
            to_stop_id=stop_ids[1],
            status=SEGMENT_OK,
            geometry_source=geometry_source,
            reason=fallback_reason,
            selected_path_distance=100.0,
            preferred_path_distance=100.0 if geometry_source == GEOMETRY_SOURCE_INFERRED_PREFERRED else None,
            fallback_path_distance=100.0,
        )
        segments = (
            SynthesizedSegmentPath(
                seq=0,
                from_stop_id=stop_ids[0],
                to_stop_id=stop_ids[1],
                from_internal_stop_id=1,
                to_internal_stop_id=2,
                link_ids=(10,),
                directions=(1,),
                geometry=geometry,
                geometry_source=geometry_source,
                diagnostics=diagnostic,
            ),
        )
        diagnostics = (diagnostic,)
        mapping = (PatternMappingRow(pattern_id=1001, seq=0, link_id=10, direction=1, geometry=geometry),)

    return SynthesizedPatternGeometry(
        pattern=pattern,
        coverage_decision=_decision(pattern, FULLY_COVERED) if accepted else _decision(pattern, rejection_reason),
        retained_stop_ids=pattern.stop_ids,
        retained_internal_stop_ids=pattern.internal_stop_ids,
        segments=segments,
        pattern_mapping=mapping,
        geometry=geometry,
        geometry_source=geometry_source,
        accepted=accepted,
        rejection_reason=rejection_reason,
        diagnostics=diagnostics,
    )


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


def _synthesis_input(pattern):
    return SimpleNamespace(
        pattern=pattern,
        coverage_decision=_decision(pattern, FULLY_COVERED),
        retained_stop_ids=pattern.stop_ids,
        retained_internal_stop_ids=pattern.internal_stop_ids,
    )


def _network_links(connected=True):
    second_a_node = 2 if connected else 4
    return gpd.GeoDataFrame(
        [
            {
                "link_id": 10,
                "a_node": 1,
                "b_node": 2,
                "direction": 1,
                "distance": 100.0,
                "modes": "t",
                "geometry": LineString([(0, 0), (100, 0)]),
            },
            {
                "link_id": 11,
                "a_node": second_a_node,
                "b_node": 3,
                "direction": 1,
                "distance": 100.0,
                "modes": "t",
                "geometry": LineString([(100, 0), (200, 0)]),
            },
            {
                "link_id": 99,
                "a_node": 9,
                "b_node": 10,
                "direction": 0,
                "distance": 100.0,
                "modes": "c",
                "geometry": LineString([(0, 20), (100, 20)]),
            },
        ],
        geometry="geometry",
        crs="EPSG:3857",
    )


def _priority_network_links(
    priority_distance,
    connected_priority=True,
    priority_field="highway",
    priority_value="primary",
):
    second_priority_a_node = 5 if connected_priority else 6
    half_distance = priority_distance / 2.0
    rows = [
        {
            "link_id": 10,
            "a_node": 1,
            "b_node": 2,
            "direction": 1,
            "distance": 100.0,
            "modes": "t",
            "geometry": LineString([(0, 0), (100, 0)]),
            priority_field: "local",
        },
        {
            "link_id": 20,
            "a_node": 3,
            "b_node": 5,
            "direction": 1,
            "distance": half_distance,
            "modes": "t",
            "geometry": LineString([(0, 0), (50, 10)]),
            priority_field: priority_value,
        },
        {
            "link_id": 21,
            "a_node": second_priority_a_node,
            "b_node": 4,
            "direction": 1,
            "distance": half_distance,
            "modes": "t",
            "geometry": LineString([(50, 10), (100, 0)]),
            priority_field: priority_value,
        },
        {
            "link_id": 30,
            "a_node": 2,
            "b_node": 8,
            "direction": 1,
            "distance": 40.0,
            "modes": "t",
            "geometry": LineString([(100, 0), (100, 40)]),
            priority_field: "local",
        },
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:3857")


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
