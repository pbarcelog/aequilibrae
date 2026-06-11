from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from aequilibrae.transit.gtfs_coverage import (
    AMBIGUOUS,
    FULLY_COVERED,
    INSUFFICIENT_RETAINED_STOPS,
    INTERNAL_GAP,
    MATCHED_MODAL_LINK,
    NEAR_MODEL_NO_MODAL_LINK,
    NETWORK_DISCONTINUITY,
    OUTSIDE_MODEL_RANGE,
    TRIM_COVERED,
    UNSUPPORTED_ROUTE_TYPE,
    GTFSCoverageConfig,
    GTFSRoutePattern,
    analyze_gtfs_coverage,
    build_gtfs_route_patterns,
    classify_pattern_stops,
    decide_pattern_coverage,
)


def test_build_gtfs_route_patterns_groups_by_route_direction_and_ordered_stops():
    gtfs_data = SimpleNamespace(
        routes={
            "R1": SimpleNamespace(route_id=11, route_type=3),
            "R2": SimpleNamespace(route_id=12, route_type=0),
        },
        trips={
            "R1": {
                "hash-1": [
                    SimpleNamespace(trip="T1", route="R1", direction_id=0, service_id="WK"),
                    SimpleNamespace(trip="T2", route="R1", direction_id=0, service_id="WK"),
                ],
                "hash-2": [SimpleNamespace(trip="T3", route="R1", direction_id=1, service_id="WK")],
                "hash-3": [SimpleNamespace(trip="T4", route="R1", direction_id=0, service_id="WK")],
            },
            "R2": {"hash-4": [SimpleNamespace(trip="T5", route="R2", direction_id=0, service_id="WK")]},
        },
        stop_times={
            "T1": _stop_times(["A", "B", "C"], [1, 2, 3]),
            "T2": _stop_times(["A", "B", "C"], [1, 2, 3]),
            "T3": _stop_times(["A", "B", "C"], [1, 2, 3]),
            "T4": _stop_times(["A", "C"], [1, 3]),
            "T5": _stop_times(["X", "Y"], [4, 5]),
        },
        services={"WK": SimpleNamespace(dates={"2026-06-10"})},
    )

    patterns = build_gtfs_route_patterns(gtfs_data, service_date="2026-06-10")

    assert len(patterns) == 4
    by_key = {pattern.key: pattern for pattern in patterns}
    assert by_key[("R1", 0, ("A", "B", "C"))].trip_ids == ("T1", "T2")
    assert by_key[("R1", 1, ("A", "B", "C"))].trip_ids == ("T3",)
    assert by_key[("R1", 0, ("A", "C"))].trip_ids == ("T4",)
    assert by_key[("R2", 0, ("X", "Y"))].route_type == 0


def test_analyze_gtfs_coverage_classifies_stop_statuses():
    gtfs_data = SimpleNamespace(
        srid=3857,
        routes={"BUS": SimpleNamespace(route_id=1, route_type=3), "FERRY": SimpleNamespace(route_id=2, route_type=4)},
        trips={
            "BUS": {"hash-1": [SimpleNamespace(trip="TB", route="BUS", direction_id=0, service_id="WK")]},
            "FERRY": {"hash-2": [SimpleNamespace(trip="TF", route="FERRY", direction_id=0, service_id="WK")]},
        },
        stop_times={
            "TB": _stop_times(["MATCH", "NEAR", "OUT"], [1, 2, 3]),
            "TF": _stop_times(["UNSUPPORTED"], [4]),
        },
        stops={
            1: SimpleNamespace(stop_id=1, stop="MATCH", geo=Point(50, 5)),
            2: SimpleNamespace(stop_id=2, stop="NEAR", geo=Point(50, 50)),
            3: SimpleNamespace(stop_id=3, stop="OUT", geo=Point(500, 500)),
            4: SimpleNamespace(stop_id=4, stop="UNSUPPORTED", geo=Point(0, 0)),
        },
        services={"WK": SimpleNamespace(dates={"2026-06-10"})},
    )
    links = gpd.GeoDataFrame(
        [
            {"link_id": 10, "modes": "t", "geometry": LineString([(0, 0), (100, 0)])},
            {"link_id": 20, "modes": "c", "geometry": LineString([(0, 50), (100, 50)])},
        ],
        geometry="geometry",
        crs="EPSG:3857",
    )

    analysis = analyze_gtfs_coverage(
        gtfs_data,
        links,
        service_date="2026-06-10",
        config=GTFSCoverageConfig(modal_match_distance=10, model_range_distance=75),
    )
    statuses = {
        coverage.stop_id: coverage
        for pattern_coverage in analysis.stop_coverage.values()
        for coverage in pattern_coverage
    }

    assert statuses["MATCH"].status == MATCHED_MODAL_LINK
    assert statuses["MATCH"].nearest_modal_link == 10
    assert statuses["MATCH"].nearest_modal_link_distance == pytest.approx(5.0)
    assert statuses["NEAR"].status == NEAR_MODEL_NO_MODAL_LINK
    assert statuses["NEAR"].nearest_link == 20
    assert statuses["NEAR"].nearest_link_distance == pytest.approx(0.0)
    assert statuses["NEAR"].nearest_modal_link_distance == pytest.approx(50.0)
    assert statuses["OUT"].status == OUTSIDE_MODEL_RANGE
    assert statuses["UNSUPPORTED"].status == UNSUPPORTED_ROUTE_TYPE

    counts = analysis.stop_status_counts()
    assert set(counts.status) == {
        MATCHED_MODAL_LINK,
        NEAR_MODEL_NO_MODAL_LINK,
        OUTSIDE_MODEL_RANGE,
        UNSUPPORTED_ROUTE_TYPE,
    }


def test_classify_pattern_stops_reports_ambiguous_modal_candidates():
    pattern = GTFSRoutePattern(
        route_id="BUS",
        route_type=3,
        direction_id=0,
        stop_ids=("CENTER",),
        internal_stop_ids=(1,),
        trip_ids=("T1",),
    )
    stops = {1: SimpleNamespace(stop_id=1, stop="CENTER", geo=Point(50, 0))}
    links = gpd.GeoDataFrame(
        [
            {"link_id": 10, "modes": "t", "geometry": LineString([(0, -5), (100, -5)])},
            {"link_id": 11, "modes": "t", "geometry": LineString([(0, 5), (100, 5)])},
        ],
        geometry="geometry",
        crs="EPSG:3857",
    )

    coverage = classify_pattern_stops(
        [pattern],
        stops,
        links,
        config=GTFSCoverageConfig(modal_match_distance=10, ambiguity_distance=0.01),
        gtfs_crs=3857,
    )[pattern.key][0]

    assert coverage.status == AMBIGUOUS
    assert coverage.nearest_modal_link in {10, 11}
    assert coverage.candidate_modal_links == (10, 11)


@pytest.mark.parametrize(
    ("source_stop_ids", "internal_stop_ids", "expected_decision", "expected_range", "expected_retained"),
    [
        (("A", "B", "C"), (1, 2, 3), FULLY_COVERED, (0, 2), ("A", "B", "C")),
        (("OUT", "A", "B"), (99, 1, 2), TRIM_COVERED, (1, 2), ("A", "B")),
        (("A", "B", "OUT"), (1, 2, 99), TRIM_COVERED, (0, 1), ("A", "B")),
        (("OUT1", "A", "B", "OUT2"), (98, 1, 2, 99), TRIM_COVERED, (1, 2), ("A", "B")),
    ],
)
def test_decide_pattern_coverage_accepts_full_and_prefix_suffix_trimmed_patterns(
    source_stop_ids,
    internal_stop_ids,
    expected_decision,
    expected_range,
    expected_retained,
):
    pattern, stops, links = _coverage_fixture(source_stop_ids, internal_stop_ids)

    decision = _decision_for(pattern, stops, links)

    assert decision.decision == expected_decision
    assert decision.original_stop_count == len(source_stop_ids)
    assert decision.retained_stop_count == len(expected_retained)
    assert decision.retained_sequence_range == expected_range
    assert decision.retained_stop_ids == expected_retained


def test_decide_pattern_coverage_rejects_internal_gap_without_pruning_substitute_route():
    pattern, stops, links = _coverage_fixture(("A", "NEAR", "B"), (1, 50, 2))

    decision = _decision_for(pattern, stops, links)

    assert decision.decision == INTERNAL_GAP
    assert decision.retained_stop_ids == ("A", "NEAR", "B")
    assert decision.internal_gap_stop_ids == ("NEAR",)
    assert decision.internal_gap_statuses == (NEAR_MODEL_NO_MODAL_LINK,)


def test_decide_pattern_coverage_rejects_trimmed_pattern_with_one_retained_stop():
    pattern, stops, links = _coverage_fixture(("OUT1", "A", "OUT2"), (98, 1, 99))

    decision = _decision_for(pattern, stops, links)

    assert decision.decision == INSUFFICIENT_RETAINED_STOPS
    assert decision.retained_stop_count == 1
    assert decision.retained_stop_ids == ("A",)


def test_decide_pattern_coverage_skips_unsupported_route_type():
    pattern, stops, links = _coverage_fixture(("A", "B"), (1, 2), route_type=4)

    decision = _decision_for(pattern, stops, links)

    assert decision.decision == UNSUPPORTED_ROUTE_TYPE
    assert decision.retained_stop_count == 0


def test_decide_pattern_coverage_rejects_modal_network_discontinuity():
    pattern, stops, links = _coverage_fixture(("A", "C"), (1, 3), connected=False)

    decision = _decision_for(pattern, stops, links)

    assert decision.decision == NETWORK_DISCONTINUITY
    assert decision.discontinuity_stop_pair == ("A", "C")
    assert decision.discontinuity_link_pair == (10, 11)


def _decision_for(pattern, stops, links):
    coverage = classify_pattern_stops(
        [pattern],
        stops,
        links,
        config=GTFSCoverageConfig(modal_match_distance=10, model_range_distance=75),
        gtfs_crs=3857,
    )
    return decide_pattern_coverage([pattern], coverage, links)[pattern.key]


def _coverage_fixture(source_stop_ids, internal_stop_ids, route_type=3, connected=True):
    pattern = GTFSRoutePattern(
        route_id="BUS",
        route_type=route_type,
        direction_id=0,
        stop_ids=source_stop_ids,
        internal_stop_ids=internal_stop_ids,
        trip_ids=("T1",),
    )
    stop_points = {
        1: Point(10, 0),
        2: Point(75, 0),
        3: Point(150, 0),
        50: Point(75, 50),
        98: Point(-500, 500),
        99: Point(500, 500),
    }
    stops = {
        internal_stop_id: SimpleNamespace(
            stop_id=internal_stop_id,
            stop=source_stop_id,
            geo=stop_points[internal_stop_id],
        )
        for source_stop_id, internal_stop_id in zip(source_stop_ids, internal_stop_ids, strict=True)
    }
    second_a_node = 2 if connected else 3
    links = gpd.GeoDataFrame(
        [
            {
                "link_id": 10,
                "a_node": 1,
                "b_node": 2,
                "direction": 0,
                "modes": "t",
                "geometry": LineString([(0, 0), (100, 0)]),
            },
            {
                "link_id": 11,
                "a_node": second_a_node,
                "b_node": 4,
                "direction": 0,
                "modes": "t",
                "geometry": LineString([(100, 0), (200, 0)]),
            },
            {
                "link_id": 20,
                "a_node": 5,
                "b_node": 6,
                "direction": 0,
                "modes": "c",
                "geometry": LineString([(0, 50), (100, 50)]),
            },
        ],
        geometry="geometry",
        crs="EPSG:3857",
    )
    return pattern, stops, links


def _stop_times(source_stop_ids, internal_stop_ids):
    return pd.DataFrame(
        {
            "stop": source_stop_ids,
            "stop_id": internal_stop_ids,
            "stop_sequence": range(len(source_stop_ids)),
        }
    )
