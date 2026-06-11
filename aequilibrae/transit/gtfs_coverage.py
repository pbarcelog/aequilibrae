from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Iterable

import geopandas as gpd
import pandas as pd
from pyproj import CRS

from aequilibrae.transit.transit_elements.mode_correspondence import mode_corresp
from aequilibrae.utils.geo_utils import metre_crs_for_gdf

MATCHED_MODAL_LINK = "matched-modal-link"
NEAR_MODEL_NO_MODAL_LINK = "near-model-no-modal-link"
OUTSIDE_MODEL_RANGE = "outside-model-range"
AMBIGUOUS = "ambiguous"
UNMATCHED = "unmatched"
UNSUPPORTED_ROUTE_TYPE = "unsupported-route-type"

FULLY_COVERED = "fully-covered"
TRIM_COVERED = "trim-covered"
INSUFFICIENT_RETAINED_STOPS = "insufficient-retained-stops"
INTERNAL_GAP = "internal-gap"
NETWORK_DISCONTINUITY = "network-discontinuity"


@dataclass(frozen=True)
class GTFSCoverageConfig:
    """Distance settings for diagnostic GTFS-to-network coverage checks."""

    modal_match_distance: float = 25.0
    model_range_distance: float = 100.0
    ambiguity_distance: float = 0.001
    distance_bands: tuple[float, ...] = (10.0, 25.0, 50.0, 100.0)


@dataclass(frozen=True)
class GTFSRoutePattern:
    """A GTFS route variant identified by route, direction, and ordered source stops."""

    route_id: str
    route_type: int
    direction_id: int | None
    stop_ids: tuple[str, ...]
    internal_stop_ids: tuple[int, ...]
    trip_ids: tuple[str, ...]
    internal_route_id: int | None = None

    @property
    def key(self) -> tuple[str, int | None, tuple[str, ...]]:
        return self.route_id, self.direction_id, self.stop_ids


@dataclass(frozen=True)
class StopCoverage:
    """Diagnostic classification for one stop in one route pattern."""

    route_id: str
    route_type: int
    direction_id: int | None
    stop_sequence: int
    stop_id: str
    internal_stop_id: int
    status: str
    nearest_link: int | None
    nearest_modal_link: int | None
    nearest_link_distance: float | None
    nearest_modal_link_distance: float | None
    candidate_modal_links: tuple[int, ...] = field(default_factory=tuple)
    distance_band: str | None = None


@dataclass(frozen=True)
class PatternDecision:
    """Pattern-level diagnostic decision derived from stop coverage and modal continuity."""

    route_id: str
    route_type: int
    direction_id: int | None
    decision: str
    original_stop_count: int
    retained_stop_count: int
    retained_sequence_range: tuple[int, int] | None
    retained_stop_ids: tuple[str, ...]
    retained_internal_stop_ids: tuple[int, ...]
    internal_gap_stop_ids: tuple[str, ...] = field(default_factory=tuple)
    internal_gap_statuses: tuple[str, ...] = field(default_factory=tuple)
    discontinuity_stop_pair: tuple[str, str] | None = None
    discontinuity_link_pair: tuple[int, int] | None = None


@dataclass(frozen=True)
class GTFSCoverageAnalysis:
    """Route patterns and stop-level diagnostics produced by coverage analysis."""

    patterns: tuple[GTFSRoutePattern, ...]
    stop_coverage: dict[tuple[str, int | None, tuple[str, ...]], tuple[StopCoverage, ...]]
    pattern_decisions: dict[tuple[str, int | None, tuple[str, ...]], PatternDecision] = field(default_factory=dict)

    def stop_status_counts(self) -> pd.DataFrame:
        rows = [
            {"route_type": coverage.route_type, "route_id": coverage.route_id, "status": coverage.status}
            for coverages in self.stop_coverage.values()
            for coverage in coverages
        ]
        if not rows:
            return pd.DataFrame(columns=["route_type", "route_id", "status", "count"])
        df = pd.DataFrame(rows)
        return df.groupby(["route_type", "route_id", "status"]).size().rename("count").reset_index()

    def pattern_decision_counts(self) -> pd.DataFrame:
        rows = [
            {"route_type": decision.route_type, "route_id": decision.route_id, "decision": decision.decision}
            for decision in self.pattern_decisions.values()
        ]
        if not rows:
            return pd.DataFrame(columns=["route_type", "route_id", "decision", "count"])
        df = pd.DataFrame(rows)
        return df.groupby(["route_type", "route_id", "decision"]).size().rename("count").reset_index()


def build_gtfs_route_patterns(gtfs_data, service_date: str | None = None) -> tuple[GTFSRoutePattern, ...]:
    """Build deterministic route patterns from loaded ``GTFSReader`` trip and stop-time data."""

    patterns: dict[tuple[str, int | None, tuple[str, ...]], GTFSRoutePattern] = {}
    trip_ids: dict[tuple[str, int | None, tuple[str, ...]], list[str]] = {}

    for route_id in sorted(gtfs_data.trips):
        route = gtfs_data.routes[route_id]
        route_type = int(route.route_type)
        for trips in gtfs_data.trips[route_id].values():
            for trip in trips:
                if service_date is not None and not _trip_operates_on_date(gtfs_data, trip, service_date):
                    continue
                stop_times = gtfs_data.stop_times[trip.trip].sort_values("stop_sequence")
                source_stop_ids = tuple(str(stop_id) for stop_id in stop_times.stop.to_list())
                internal_stop_ids = tuple(int(stop_id) for stop_id in stop_times.stop_id.to_list())
                direction_id = _optional_int(getattr(trip, "direction_id", None))
                key = (str(route_id), direction_id, source_stop_ids)
                trip_ids.setdefault(key, []).append(str(trip.trip))
                patterns.setdefault(
                    key,
                    GTFSRoutePattern(
                        route_id=str(route_id),
                        route_type=route_type,
                        direction_id=direction_id,
                        stop_ids=source_stop_ids,
                        internal_stop_ids=internal_stop_ids,
                        trip_ids=(),
                        internal_route_id=_optional_int(getattr(route, "route_id", None)),
                    ),
                )

    return tuple(
        GTFSRoutePattern(
            route_id=pattern.route_id,
            route_type=pattern.route_type,
            direction_id=pattern.direction_id,
            stop_ids=pattern.stop_ids,
            internal_stop_ids=pattern.internal_stop_ids,
            trip_ids=tuple(sorted(trip_ids[pattern.key])),
            internal_route_id=pattern.internal_route_id,
        )
        for pattern in patterns.values()
    )


def analyze_gtfs_coverage(
    gtfs_data,
    network_links: gpd.GeoDataFrame,
    service_date: str | None = None,
    config: GTFSCoverageConfig | None = None,
    gtfs_crs: str | int | CRS | None = None,
) -> GTFSCoverageAnalysis:
    """Classify loaded GTFS route-pattern stops against project network coverage."""

    config = GTFSCoverageConfig() if config is None else config
    patterns = build_gtfs_route_patterns(gtfs_data, service_date)
    stop_coverage = classify_pattern_stops(
        patterns,
        gtfs_data.stops,
        network_links,
        config=config,
        gtfs_crs=gtfs_crs or getattr(gtfs_data, "srid", None),
    )
    pattern_decisions = decide_pattern_coverage(patterns, stop_coverage, network_links)
    return GTFSCoverageAnalysis(
        patterns=patterns,
        stop_coverage=stop_coverage,
        pattern_decisions=pattern_decisions,
    )


def classify_pattern_stops(
    patterns: Iterable[GTFSRoutePattern],
    stops: dict[int, object],
    network_links: gpd.GeoDataFrame,
    config: GTFSCoverageConfig | None = None,
    gtfs_crs: str | int | CRS | None = None,
) -> dict[tuple[str, int | None, tuple[str, ...]], tuple[StopCoverage, ...]]:
    """Classify each stop in each route pattern against modal and any-link coverage."""

    config = GTFSCoverageConfig() if config is None else config
    prepared_links = _prepare_links(network_links)
    projected_links, projected_stops = _project_links_and_stops(prepared_links, stops, gtfs_crs)
    coverage: dict[tuple[str, int | None, tuple[str, ...]], tuple[StopCoverage, ...]] = {}

    for pattern in patterns:
        rows = []
        for sequence, (source_stop_id, internal_stop_id) in enumerate(
            zip(pattern.stop_ids, pattern.internal_stop_ids, strict=True)
        ):
            rows.append(
                _classify_stop(
                    pattern,
                    sequence,
                    source_stop_id,
                    internal_stop_id,
                    projected_stops,
                    projected_links,
                    config,
                )
            )
        coverage[pattern.key] = tuple(rows)
    return coverage


def decide_pattern_coverage(
    patterns: Iterable[GTFSRoutePattern],
    stop_coverage: dict[tuple[str, int | None, tuple[str, ...]], tuple[StopCoverage, ...]],
    network_links: gpd.GeoDataFrame,
) -> dict[tuple[str, int | None, tuple[str, ...]], PatternDecision]:
    """Decide whether each pattern is fully covered, trim-covered, skipped, or rejected."""

    decisions = {}
    for pattern in patterns:
        coverages = stop_coverage[pattern.key]
        decisions[pattern.key] = _decide_one_pattern(pattern, coverages, network_links)
    return decisions


def _decide_one_pattern(
    pattern: GTFSRoutePattern, coverages: tuple[StopCoverage, ...], network_links: gpd.GeoDataFrame
) -> PatternDecision:
    if pattern.route_type not in mode_corresp:
        return _pattern_decision(pattern, UNSUPPORTED_ROUTE_TYPE, coverages, None)

    matched_indices = [idx for idx, coverage in enumerate(coverages) if coverage.status == MATCHED_MODAL_LINK]
    if not matched_indices:
        return _pattern_decision(
            pattern,
            INTERNAL_GAP,
            coverages,
            None,
            internal_gap_coverages=coverages,
        )

    first_matched, last_matched = matched_indices[0], matched_indices[-1]
    retained = coverages[first_matched : last_matched + 1]
    if len(retained) < 2:
        return _pattern_decision(pattern, INSUFFICIENT_RETAINED_STOPS, coverages, (first_matched, last_matched))

    internal_gaps = tuple(coverage for coverage in retained if coverage.status != MATCHED_MODAL_LINK)
    if internal_gaps:
        return _pattern_decision(
            pattern,
            INTERNAL_GAP,
            coverages,
            (first_matched, last_matched),
            internal_gap_coverages=internal_gaps,
        )

    continuity = _check_modal_continuity(pattern.route_type, retained, network_links)
    if continuity is not None:
        link_pair, stop_pair = continuity
        return _pattern_decision(
            pattern,
            NETWORK_DISCONTINUITY,
            coverages,
            (first_matched, last_matched),
            discontinuity_stop_pair=stop_pair,
            discontinuity_link_pair=link_pair,
        )

    decision = FULLY_COVERED if first_matched == 0 and last_matched == len(coverages) - 1 else TRIM_COVERED
    return _pattern_decision(pattern, decision, coverages, (first_matched, last_matched))


def _pattern_decision(
    pattern: GTFSRoutePattern,
    decision: str,
    coverages: tuple[StopCoverage, ...],
    retained_range: tuple[int, int] | None,
    internal_gap_coverages: tuple[StopCoverage, ...] = (),
    discontinuity_stop_pair: tuple[str, str] | None = None,
    discontinuity_link_pair: tuple[int, int] | None = None,
) -> PatternDecision:
    retained = () if retained_range is None else coverages[retained_range[0] : retained_range[1] + 1]
    return PatternDecision(
        route_id=pattern.route_id,
        route_type=pattern.route_type,
        direction_id=pattern.direction_id,
        decision=decision,
        original_stop_count=len(coverages),
        retained_stop_count=len(retained),
        retained_sequence_range=retained_range,
        retained_stop_ids=tuple(coverage.stop_id for coverage in retained),
        retained_internal_stop_ids=tuple(coverage.internal_stop_id for coverage in retained),
        internal_gap_stop_ids=tuple(coverage.stop_id for coverage in internal_gap_coverages),
        internal_gap_statuses=tuple(coverage.status for coverage in internal_gap_coverages),
        discontinuity_stop_pair=discontinuity_stop_pair,
        discontinuity_link_pair=discontinuity_link_pair,
    )


def _check_modal_continuity(
    route_type: int,
    retained: tuple[StopCoverage, ...],
    network_links: gpd.GeoDataFrame,
) -> tuple[tuple[int, int], tuple[str, str]] | None:
    if len(retained) <= 1:
        return None
    if not {"link_id", "a_node", "b_node", "modes"}.issubset(network_links.columns):
        return None

    mode = mode_corresp[route_type]
    links = network_links[network_links.modes.str.contains(mode, regex=False, na=False)].copy()
    if links.empty:
        first = retained[0]
        second = retained[1]
        return (first.nearest_modal_link or -1, second.nearest_modal_link or -1), (first.stop_id, second.stop_id)
    if "direction" not in links.columns:
        links = links.assign(direction=0)

    endpoints = {
        int(row.link_id): (int(row.a_node), int(row.b_node), int(row.direction))
        for row in links.itertuples(index=False)
    }
    adjacency = _modal_adjacency(endpoints.values())

    for first, second in zip(retained[:-1], retained[1:], strict=True):
        if first.nearest_modal_link == second.nearest_modal_link:
            continue
        if first.nearest_modal_link not in endpoints or second.nearest_modal_link not in endpoints:
            return _continuity_failure(first, second)
        first_a, first_b, _ = endpoints[first.nearest_modal_link]
        second_a, second_b, _ = endpoints[second.nearest_modal_link]
        if not _any_node_reachable((first_a, first_b), (second_a, second_b), adjacency):
            return _continuity_failure(first, second)
    return None


def _continuity_failure(first: StopCoverage, second: StopCoverage) -> tuple[tuple[int, int], tuple[str, str]]:
    return (
        (first.nearest_modal_link or -1, second.nearest_modal_link or -1),
        (first.stop_id, second.stop_id),
    )


def _modal_adjacency(link_endpoints: Iterable[tuple[int, int, int]]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {}
    for a_node, b_node, direction in link_endpoints:
        adjacency.setdefault(a_node, set())
        adjacency.setdefault(b_node, set())
        if direction in (0, 1):
            adjacency[a_node].add(b_node)
        if direction in (0, -1):
            adjacency[b_node].add(a_node)
    return adjacency


def _any_node_reachable(
    origins: tuple[int, int], destinations: tuple[int, int], adjacency: dict[int, set[int]]
) -> bool:
    destination_set = set(destinations)
    visited = set()
    stack = list(origins)
    while stack:
        node = stack.pop()
        if node in destination_set:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adjacency.get(node, set()) - visited)
    return False


def _classify_stop(
    pattern: GTFSRoutePattern,
    sequence: int,
    source_stop_id: str,
    internal_stop_id: int,
    projected_stops: gpd.GeoDataFrame,
    projected_links: gpd.GeoDataFrame,
    config: GTFSCoverageConfig,
) -> StopCoverage:
    if pattern.route_type not in mode_corresp:
        return _coverage_row(pattern, sequence, source_stop_id, internal_stop_id, UNSUPPORTED_ROUTE_TYPE)

    if internal_stop_id not in projected_stops.index or projected_links.empty:
        return _coverage_row(pattern, sequence, source_stop_id, internal_stop_id, UNMATCHED)

    stop_geometry = projected_stops.loc[internal_stop_id].geometry
    all_distances = projected_links.geometry.distance(stop_geometry)
    nearest_link, nearest_link_distance = _nearest_link(all_distances, projected_links)

    modal_mode = mode_corresp[pattern.route_type]
    modal_links = projected_links[projected_links.modes.str.contains(modal_mode, regex=False, na=False)]
    if modal_links.empty:
        status = _model_status(nearest_link_distance, config)
        return _coverage_row(
            pattern,
            sequence,
            source_stop_id,
            internal_stop_id,
            status,
            nearest_link=nearest_link,
            nearest_link_distance=nearest_link_distance,
            distance_band=_distance_band(nearest_link_distance, config.distance_bands),
        )

    modal_distances = modal_links.geometry.distance(stop_geometry)
    nearest_modal_link, nearest_modal_link_distance = _nearest_link(modal_distances, modal_links)
    modal_candidates = modal_distances[modal_distances <= config.modal_match_distance]
    candidate_link_ids = tuple(int(modal_links.loc[idx].link_id) for idx in modal_candidates.index)

    if nearest_modal_link_distance is not None and nearest_modal_link_distance <= config.modal_match_distance:
        status = MATCHED_MODAL_LINK
        min_distance = float(modal_candidates.min())
        competing = modal_candidates[modal_candidates <= min_distance + config.ambiguity_distance]
        if competing.shape[0] > 1:
            status = AMBIGUOUS
            candidate_link_ids = tuple(int(modal_links.loc[idx].link_id) for idx in competing.index)
    else:
        status = _model_status(nearest_link_distance, config)

    return _coverage_row(
        pattern,
        sequence,
        source_stop_id,
        internal_stop_id,
        status,
        nearest_link=nearest_link,
        nearest_modal_link=nearest_modal_link,
        nearest_link_distance=nearest_link_distance,
        nearest_modal_link_distance=nearest_modal_link_distance,
        candidate_modal_links=candidate_link_ids,
        distance_band=_distance_band(nearest_modal_link_distance, config.distance_bands),
    )


def _coverage_row(
    pattern: GTFSRoutePattern,
    sequence: int,
    source_stop_id: str,
    internal_stop_id: int,
    status: str,
    nearest_link: int | None = None,
    nearest_modal_link: int | None = None,
    nearest_link_distance: float | None = None,
    nearest_modal_link_distance: float | None = None,
    candidate_modal_links: tuple[int, ...] = (),
    distance_band: str | None = None,
) -> StopCoverage:
    return StopCoverage(
        route_id=pattern.route_id,
        route_type=pattern.route_type,
        direction_id=pattern.direction_id,
        stop_sequence=sequence,
        stop_id=source_stop_id,
        internal_stop_id=internal_stop_id,
        status=status,
        nearest_link=nearest_link,
        nearest_modal_link=nearest_modal_link,
        nearest_link_distance=nearest_link_distance,
        nearest_modal_link_distance=nearest_modal_link_distance,
        candidate_modal_links=candidate_modal_links,
        distance_band=distance_band,
    )


def _prepare_links(network_links: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if network_links.empty:
        return network_links.copy()
    links = network_links.copy()
    if "link_id" not in links.columns or "modes" not in links.columns:
        raise ValueError("Network links must include 'link_id' and 'modes' columns")
    if links.crs is None:
        raise ValueError("Network links must have a CRS for GTFS coverage analysis")
    return links


def _project_links_and_stops(
    links: gpd.GeoDataFrame, stops: dict[int, object], gtfs_crs: str | int | CRS | None
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if links.empty:
        crs = CRS.from_user_input(gtfs_crs or 4326)
        return links.set_crs(crs, allow_override=True), gpd.GeoDataFrame(columns=["stop_id", "geometry"], crs=crs)

    metre_crs = metre_crs_for_gdf(links)
    projected_links = links.to_crs(metre_crs)
    if gtfs_crs is None:
        gtfs_crs = links.crs
    stop_rows = [
        {"stop_id": int(stop_id), "geometry": stop.geo}
        for stop_id, stop in stops.items()
        if getattr(stop, "geo", None) is not None
    ]
    stop_gdf = gpd.GeoDataFrame(stop_rows, geometry="geometry", crs=gtfs_crs)
    if stop_gdf.empty:
        stop_gdf = gpd.GeoDataFrame(columns=["stop_id", "geometry"], crs=gtfs_crs)
    projected_stops = stop_gdf.to_crs(metre_crs).set_index("stop_id", drop=False)
    return projected_links, projected_stops


def _nearest_link(distances: pd.Series, links: gpd.GeoDataFrame) -> tuple[int | None, float | None]:
    if distances.empty:
        return None, None
    idx = distances.idxmin()
    distance = float(distances.loc[idx])
    if not isfinite(distance):
        return None, None
    return int(links.loc[idx].link_id), distance


def _model_status(nearest_link_distance: float | None, config: GTFSCoverageConfig) -> str:
    if nearest_link_distance is None:
        return UNMATCHED
    if nearest_link_distance <= config.model_range_distance:
        return NEAR_MODEL_NO_MODAL_LINK
    return OUTSIDE_MODEL_RANGE


def _distance_band(distance: float | None, bands: tuple[float, ...]) -> str | None:
    if distance is None:
        return None
    for band in bands:
        if distance <= band:
            return f"<= {band:g} m"
    return f"> {max(bands):g} m" if bands else None


def _trip_operates_on_date(gtfs_data, trip, service_date: str) -> bool:
    service = gtfs_data.services.get(trip.service_id)
    return service is not None and service_date in service.dates


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


__all__ = [
    "AMBIGUOUS",
    "FULLY_COVERED",
    "GTFSCoverageAnalysis",
    "GTFSCoverageConfig",
    "GTFSRoutePattern",
    "INSUFFICIENT_RETAINED_STOPS",
    "INTERNAL_GAP",
    "MATCHED_MODAL_LINK",
    "NEAR_MODEL_NO_MODAL_LINK",
    "NETWORK_DISCONTINUITY",
    "OUTSIDE_MODEL_RANGE",
    "PatternDecision",
    "StopCoverage",
    "TRIM_COVERED",
    "UNMATCHED",
    "UNSUPPORTED_ROUTE_TYPE",
    "analyze_gtfs_coverage",
    "build_gtfs_route_patterns",
    "classify_pattern_stops",
    "decide_pattern_coverage",
]
