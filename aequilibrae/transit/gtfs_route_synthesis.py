from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import isfinite
from typing import Iterable

import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import linemerge

from aequilibrae.transit.gtfs_coverage import (
    FULLY_COVERED,
    TRIM_COVERED,
    GTFSCoverageAnalysis,
    GTFSRoutePattern,
    PatternDecision,
    StopCoverage,
    build_gtfs_route_patterns,
)
from aequilibrae.transit.transit_elements.mode_correspondence import mode_corresp

GEOMETRY_SOURCE_SHAPE = "gtfs-shape"
GEOMETRY_SOURCE_INFERRED_PREFERRED = "inferred-preferred"
GEOMETRY_SOURCE_INFERRED_FALLBACK = "inferred-fallback"
GEOMETRY_SOURCE_REJECTED = "rejected"

SEGMENT_OK = "ok"
SEGMENT_REJECTED = "rejected"
SEGMENT_UNTESTED = "untested"

STOP_MATCHED_MODAL = "matched-modal-link"
STOP_MATCHED_FALLBACK = "matched-fallback-link"
STOP_UNMATCHED = "unmatched"

REJECT_UNSUPPORTED_ROUTE_TYPE = "unsupported-route-type"
REJECT_UNMATCHED_STOP = "unmatched-stop"
REJECT_DISCONNECTED_STOP_PAIR = "disconnected-stop-pair"
REJECT_EXCESSIVE_SEGMENT_DISTANCE = "path-exceeds-maximum-distance"
REJECT_INSUFFICIENT_RETAINED_STOPS = "insufficient-retained-stops"

FALLBACK_PREFERRED_UNAVAILABLE = "preferred-path-unavailable"
FALLBACK_PREFERRED_EXCESSIVE_DETOUR = "preferred-path-exceeds-detour-ratio"
FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED = "priority-context-unsupported"


@dataclass(frozen=True)
class GTFSRouteSynthesisConfig:
    """Configuration for turning GTFS route patterns into network paths."""

    stop_match_distance: float = 25.0
    fallback_stop_match_distance: float = 100.0
    maximum_segment_distance: float | None = None
    preferred_path_detour_ratio: float = 2.0
    distance_cost_field: str = "distance"
    link_id_field: str = "link_id"
    direction_field: str = "direction"
    mode_field: str = "modes"
    priority_fields: tuple[str, ...] = (
        "link_type",
        "facility_type",
        "functional_class",
        "road_type",
        "highway",
    )
    preferred_priority_values: tuple[str, ...] = (
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "arterial",
        "main",
    )


@dataclass(frozen=True)
class GTFSGeometrySourceInventory:
    """Counts shape-bearing GTFS inputs before route synthesis begins."""

    route_pattern_count: int
    shape_count: int
    trip_count: int
    trips_with_shape_id: int
    trips_with_loaded_shape: int
    patterns_with_loaded_shape: int
    patterns_without_loaded_shape: int

    @property
    def has_shapes(self) -> bool:
        return self.shape_count > 0


@dataclass(frozen=True)
class RoutePatternSynthesisInput:
    """Accepted coverage-analysis output prepared for geometry synthesis."""

    pattern: GTFSRoutePattern
    coverage_decision: PatternDecision
    stop_coverage: tuple[StopCoverage, ...]

    @property
    def retained_stop_ids(self) -> tuple[str, ...]:
        return self.coverage_decision.retained_stop_ids

    @property
    def retained_internal_stop_ids(self) -> tuple[int, ...]:
        return self.coverage_decision.retained_internal_stop_ids


@dataclass(frozen=True)
class StopLinkCandidate:
    """One network link candidate for accessing a retained GTFS stop."""

    stop_id: str
    internal_stop_id: int
    link_id: int
    a_node: int
    b_node: int
    direction: int
    distance: float
    is_modal: bool
    is_priority: bool
    geometry: LineString


@dataclass(frozen=True)
class StopNetworkMatch:
    """Network-link candidates for one retained GTFS stop."""

    stop_id: str
    internal_stop_id: int
    status: str
    candidates: tuple[StopLinkCandidate, ...]
    nearest_distance: float | None = None


@dataclass(frozen=True)
class SegmentPathDiagnostics:
    """Quality diagnostics for one inferred or shape-guided stop-to-stop segment."""

    seq: int
    from_stop_id: str
    to_stop_id: str
    status: str = SEGMENT_UNTESTED
    geometry_source: str | None = None
    reason: str | None = None
    selected_path_distance: float | None = None
    preferred_path_distance: float | None = None
    fallback_path_distance: float | None = None
    detour_ratio: float | None = None
    flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SynthesizedSegmentPath:
    """Network path chosen for one consecutive pair of retained GTFS stops."""

    seq: int
    from_stop_id: str
    to_stop_id: str
    from_internal_stop_id: int
    to_internal_stop_id: int
    link_ids: tuple[int, ...]
    directions: tuple[int, ...]
    geometry: LineString | None
    geometry_source: str
    diagnostics: SegmentPathDiagnostics


@dataclass(frozen=True)
class PatternMappingRow:
    """Candidate row for the transit ``pattern_mapping`` table."""

    pattern_id: int
    seq: int
    link_id: int
    direction: int
    geometry: LineString | None = None


@dataclass(frozen=True)
class SynthesizedPatternGeometry:
    """Assignment-ready geometry candidate for one GTFS route pattern."""

    pattern: GTFSRoutePattern
    coverage_decision: PatternDecision | None
    retained_stop_ids: tuple[str, ...]
    retained_internal_stop_ids: tuple[int, ...]
    segments: tuple[SynthesizedSegmentPath, ...]
    pattern_mapping: tuple[PatternMappingRow, ...]
    geometry: LineString | None
    geometry_source: str
    accepted: bool
    rejection_reason: str | None = None
    diagnostics: tuple[SegmentPathDiagnostics, ...] = field(default_factory=tuple)


def match_stop_to_network(
    stop_id: str,
    internal_stop_id: int,
    stop_geometry,
    route_type: int,
    network_links: gpd.GeoDataFrame,
    config: GTFSRouteSynthesisConfig | None = None,
) -> StopNetworkMatch:
    """Match one GTFS stop point to nearby route-compatible network links."""

    config = GTFSRouteSynthesisConfig() if config is None else config
    links = _prepare_synthesis_links(network_links, config)
    if route_type not in mode_corresp or links.empty:
        return StopNetworkMatch(stop_id, internal_stop_id, STOP_UNMATCHED, ())

    route_mode = mode_corresp[route_type]
    modal_mask = links[config.mode_field].str.contains(route_mode, regex=False, na=False)
    modal_candidates = _candidate_links(
        stop_id,
        internal_stop_id,
        stop_geometry,
        links[modal_mask],
        config.stop_match_distance,
        is_modal=True,
        config=config,
    )
    if modal_candidates:
        return StopNetworkMatch(
            stop_id,
            internal_stop_id,
            STOP_MATCHED_MODAL,
            modal_candidates,
            nearest_distance=modal_candidates[0].distance,
        )

    fallback_candidates = _candidate_links(
        stop_id,
        internal_stop_id,
        stop_geometry,
        links,
        config.fallback_stop_match_distance,
        is_modal=False,
        config=config,
    )
    if fallback_candidates:
        return StopNetworkMatch(
            stop_id,
            internal_stop_id,
            STOP_MATCHED_FALLBACK,
            fallback_candidates,
            nearest_distance=fallback_candidates[0].distance,
        )

    return StopNetworkMatch(stop_id, internal_stop_id, STOP_UNMATCHED, ())


def infer_stop_to_stop_segment(
    seq: int,
    from_match: StopNetworkMatch,
    to_match: StopNetworkMatch,
    route_type: int,
    network_links: gpd.GeoDataFrame,
    config: GTFSRouteSynthesisConfig | None = None,
) -> SynthesizedSegmentPath:
    """Infer one fallback shortest-distance network path between two matched stops."""

    config = GTFSRouteSynthesisConfig() if config is None else config
    if route_type not in mode_corresp:
        return _rejected_segment(seq, from_match, to_match, REJECT_UNSUPPORTED_ROUTE_TYPE)
    if not from_match.candidates or not to_match.candidates:
        return _rejected_segment(seq, from_match, to_match, REJECT_UNMATCHED_STOP)

    links = _prepare_synthesis_links(network_links, config)
    modal_links = links[links[config.mode_field].str.contains(mode_corresp[route_type], regex=False, na=False)]
    if modal_links.empty:
        return _rejected_segment(seq, from_match, to_match, REJECT_UNSUPPORTED_ROUTE_TYPE)

    link_rows = {int(row[config.link_id_field]): row for _, row in modal_links.iterrows()}
    graph = _build_link_graph(modal_links, config)
    fallback_path = _best_segment_path(from_match.candidates, to_match.candidates, graph, link_rows, config)
    if fallback_path is None:
        return _rejected_segment(seq, from_match, to_match, REJECT_DISCONNECTED_STOP_PAIR)

    preferred_path, fallback_reason = _preferred_segment_path(from_match, to_match, modal_links, config)
    path = _choose_segment_path(preferred_path, fallback_path, config)
    link_ids, directions, distance = path
    preferred_distance = None if preferred_path is None else preferred_path[2]
    fallback_distance = fallback_path[2]
    detour_ratio = (
        None if preferred_distance is None or fallback_distance <= 0 else preferred_distance / fallback_distance
    )
    geometry_source = (
        GEOMETRY_SOURCE_INFERRED_PREFERRED if path is preferred_path else GEOMETRY_SOURCE_INFERRED_FALLBACK
    )
    if geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK and preferred_path is not None:
        fallback_reason = FALLBACK_PREFERRED_EXCESSIVE_DETOUR

    if config.maximum_segment_distance is not None and distance > config.maximum_segment_distance:
        return _rejected_segment(
            seq,
            from_match,
            to_match,
            REJECT_EXCESSIVE_SEGMENT_DISTANCE,
            selected_path_distance=distance,
        )

    geometry = _assemble_path_geometry(link_ids, directions, link_rows)
    diagnostics = SegmentPathDiagnostics(
        seq=seq,
        from_stop_id=from_match.stop_id,
        to_stop_id=to_match.stop_id,
        status=SEGMENT_OK,
        geometry_source=geometry_source,
        reason=fallback_reason if geometry_source == GEOMETRY_SOURCE_INFERRED_FALLBACK else None,
        selected_path_distance=distance,
        preferred_path_distance=preferred_distance,
        fallback_path_distance=fallback_distance,
        detour_ratio=detour_ratio,
        flags=_segment_flags(geometry_source, fallback_reason),
    )
    return SynthesizedSegmentPath(
        seq=seq,
        from_stop_id=from_match.stop_id,
        to_stop_id=to_match.stop_id,
        from_internal_stop_id=from_match.internal_stop_id,
        to_internal_stop_id=to_match.internal_stop_id,
        link_ids=link_ids,
        directions=directions,
        geometry=geometry,
        geometry_source=geometry_source,
        diagnostics=diagnostics,
    )


def synthesize_inferred_pattern_geometry(
    synthesis_input: RoutePatternSynthesisInput,
    stops: dict[int, object],
    network_links: gpd.GeoDataFrame,
    pattern_id: int = -1,
    config: GTFSRouteSynthesisConfig | None = None,
) -> SynthesizedPatternGeometry:
    """Infer route geometry and pattern-mapping candidates from retained GTFS stops."""

    config = GTFSRouteSynthesisConfig() if config is None else config
    retained_stop_ids = synthesis_input.retained_stop_ids
    retained_internal_stop_ids = synthesis_input.retained_internal_stop_ids
    if len(retained_stop_ids) < 2:
        return SynthesizedPatternGeometry(
            pattern=synthesis_input.pattern,
            coverage_decision=synthesis_input.coverage_decision,
            retained_stop_ids=retained_stop_ids,
            retained_internal_stop_ids=retained_internal_stop_ids,
            segments=(),
            pattern_mapping=(),
            geometry=None,
            geometry_source=GEOMETRY_SOURCE_REJECTED,
            accepted=False,
            rejection_reason=REJECT_INSUFFICIENT_RETAINED_STOPS,
        )

    matches = [
        match_stop_to_network(
            stop_id,
            internal_stop_id,
            stops[internal_stop_id].geo,
            synthesis_input.pattern.route_type,
            network_links,
            config,
        )
        if internal_stop_id in stops and getattr(stops[internal_stop_id], "geo", None) is not None
        else StopNetworkMatch(stop_id, internal_stop_id, STOP_UNMATCHED, ())
        for stop_id, internal_stop_id in zip(retained_stop_ids, retained_internal_stop_ids, strict=True)
    ]

    segments = tuple(
        infer_stop_to_stop_segment(
            seq,
            from_match,
            to_match,
            synthesis_input.pattern.route_type,
            network_links,
            config,
        )
        for seq, (from_match, to_match) in enumerate(zip(matches[:-1], matches[1:], strict=True))
    )
    diagnostics = tuple(segment.diagnostics for segment in segments)
    rejected = tuple(segment for segment in segments if segment.diagnostics.status == SEGMENT_REJECTED)
    if rejected:
        return SynthesizedPatternGeometry(
            pattern=synthesis_input.pattern,
            coverage_decision=synthesis_input.coverage_decision,
            retained_stop_ids=retained_stop_ids,
            retained_internal_stop_ids=retained_internal_stop_ids,
            segments=segments,
            pattern_mapping=(),
            geometry=None,
            geometry_source=GEOMETRY_SOURCE_REJECTED,
            accepted=False,
            rejection_reason=rejected[0].diagnostics.reason,
            diagnostics=diagnostics,
        )

    mapping = _pattern_mapping_rows(pattern_id, segments)
    geometry = _merge_segment_geometries(segment.geometry for segment in segments)
    return SynthesizedPatternGeometry(
        pattern=synthesis_input.pattern,
        coverage_decision=synthesis_input.coverage_decision,
        retained_stop_ids=retained_stop_ids,
        retained_internal_stop_ids=retained_internal_stop_ids,
        segments=segments,
        pattern_mapping=mapping,
        geometry=geometry,
        geometry_source=_pattern_geometry_source(segments),
        accepted=True,
        diagnostics=diagnostics,
    )


def inventory_gtfs_geometry_sources(
    gtfs_data,
    patterns: Iterable[GTFSRoutePattern] | None = None,
) -> GTFSGeometrySourceInventory:
    """Summarize whether loaded GTFS patterns can use source ``shapes.txt`` geometry."""

    route_patterns = tuple(build_gtfs_route_patterns(gtfs_data) if patterns is None else patterns)
    shapes = getattr(gtfs_data, "shapes", {})
    trips_by_id = _trip_lookup(gtfs_data)
    trip_ids = tuple(sorted({trip_id for pattern in route_patterns for trip_id in pattern.trip_ids}))
    trips = tuple(trips_by_id[trip_id] for trip_id in trip_ids if trip_id in trips_by_id)

    trips_with_shape_id = tuple(trip for trip in trips if _trip_shape_id(trip))
    trips_with_loaded_shape = tuple(trip for trip in trips if _trip_shape_id(trip) in shapes)
    patterns_with_loaded_shape = sum(
        any(_trip_shape_id(trips_by_id[trip_id]) in shapes for trip_id in pattern.trip_ids if trip_id in trips_by_id)
        for pattern in route_patterns
    )

    return GTFSGeometrySourceInventory(
        route_pattern_count=len(route_patterns),
        shape_count=len(shapes),
        trip_count=len(trips),
        trips_with_shape_id=len(trips_with_shape_id),
        trips_with_loaded_shape=len(trips_with_loaded_shape),
        patterns_with_loaded_shape=patterns_with_loaded_shape,
        patterns_without_loaded_shape=len(route_patterns) - patterns_with_loaded_shape,
    )


def route_pattern_synthesis_inputs(
    coverage_analysis: GTFSCoverageAnalysis,
    accepted_decisions: tuple[str, ...] = (FULLY_COVERED, TRIM_COVERED),
) -> tuple[RoutePatternSynthesisInput, ...]:
    """Select coverage-approved patterns as synthesis inputs."""

    inputs = []
    accepted = set(accepted_decisions)
    for pattern in coverage_analysis.patterns:
        decision = coverage_analysis.pattern_decisions.get(pattern.key)
        if decision is None or decision.decision not in accepted:
            continue
        inputs.append(
            RoutePatternSynthesisInput(
                pattern=pattern,
                coverage_decision=decision,
                stop_coverage=coverage_analysis.stop_coverage[pattern.key],
            )
        )
    return tuple(inputs)


def _trip_lookup(gtfs_data) -> dict[str, object]:
    trips_by_id = {}
    for route_trips in getattr(gtfs_data, "trips", {}).values():
        for trips in route_trips.values():
            for trip in trips:
                trips_by_id[str(getattr(trip, "trip", ""))] = trip
    return trips_by_id


def _trip_shape_id(trip) -> str:
    return str(getattr(trip, "shape_id", "") or "")


def _prepare_synthesis_links(
    network_links: gpd.GeoDataFrame, config: GTFSRouteSynthesisConfig
) -> gpd.GeoDataFrame:
    required = {config.link_id_field, "a_node", "b_node", config.mode_field, "geometry"}
    missing = required - set(network_links.columns)
    if missing:
        raise ValueError(f"Network links must include {sorted(missing)} for GTFS route synthesis")
    links = network_links.copy()
    if config.direction_field not in links.columns:
        links[config.direction_field] = 0
    if config.distance_cost_field not in links.columns:
        links[config.distance_cost_field] = links.geometry.length
    return links


def _candidate_links(
    stop_id: str,
    internal_stop_id: int,
    stop_geometry,
    links: gpd.GeoDataFrame,
    threshold: float,
    is_modal: bool,
    config: GTFSRouteSynthesisConfig,
) -> tuple[StopLinkCandidate, ...]:
    if links.empty:
        return ()
    distances = links.geometry.distance(stop_geometry)
    candidates = []
    for idx, distance in distances[distances <= threshold].sort_values().items():
        row = links.loc[idx]
        candidates.append(
            StopLinkCandidate(
                stop_id=stop_id,
                internal_stop_id=internal_stop_id,
                link_id=int(row[config.link_id_field]),
                a_node=int(row.a_node),
                b_node=int(row.b_node),
                direction=int(row[config.direction_field]),
                distance=float(distance),
                is_modal=is_modal,
                is_priority=_is_priority_link(row, config),
                geometry=row.geometry,
            )
        )
    return tuple(candidates)


def _preferred_segment_path(
    from_match: StopNetworkMatch,
    to_match: StopNetworkMatch,
    modal_links: gpd.GeoDataFrame,
    config: GTFSRouteSynthesisConfig,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...], float] | None, str | None]:
    if not _priority_context_supported(from_match, to_match):
        return None, FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED

    priority_links = modal_links[_priority_mask(modal_links, config)]
    if priority_links.empty:
        return None, FALLBACK_PREFERRED_UNAVAILABLE

    priority_link_ids = {int(row[config.link_id_field]) for _, row in priority_links.iterrows()}
    from_candidates = tuple(candidate for candidate in from_match.candidates if candidate.link_id in priority_link_ids)
    to_candidates = tuple(candidate for candidate in to_match.candidates if candidate.link_id in priority_link_ids)
    if not from_candidates or not to_candidates:
        return None, FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED

    link_rows = {int(row[config.link_id_field]): row for _, row in priority_links.iterrows()}
    graph = _build_link_graph(priority_links, config)
    path = _best_segment_path(from_candidates, to_candidates, graph, link_rows, config)
    if path is None:
        return None, FALLBACK_PREFERRED_UNAVAILABLE
    return path, None


def _choose_segment_path(
    preferred_path: tuple[tuple[int, ...], tuple[int, ...], float] | None,
    fallback_path: tuple[tuple[int, ...], tuple[int, ...], float],
    config: GTFSRouteSynthesisConfig,
) -> tuple[tuple[int, ...], tuple[int, ...], float]:
    if preferred_path is None:
        return fallback_path
    if preferred_path[2] <= fallback_path[2] * config.preferred_path_detour_ratio:
        return preferred_path
    return fallback_path


def _priority_context_supported(from_match: StopNetworkMatch, to_match: StopNetworkMatch) -> bool:
    return any(candidate.is_priority for candidate in from_match.candidates) and any(
        candidate.is_priority for candidate in to_match.candidates
    )


def _priority_mask(links: gpd.GeoDataFrame, config: GTFSRouteSynthesisConfig):
    mask = None
    for priority_field in config.priority_fields:
        if priority_field not in links.columns:
            continue
        field_mask = links[priority_field].astype(str).str.lower().isin(config.preferred_priority_values)
        mask = field_mask if mask is None else mask | field_mask
    if mask is None:
        return links.index != links.index
    return mask


def _is_priority_link(row, config: GTFSRouteSynthesisConfig) -> bool:
    for priority_field in config.priority_fields:
        if priority_field not in row.index:
            continue
        if str(row[priority_field]).lower() in config.preferred_priority_values:
            return True
    return False


def _segment_flags(geometry_source: str, fallback_reason: str | None) -> tuple[str, ...]:
    if geometry_source == GEOMETRY_SOURCE_INFERRED_PREFERRED:
        return ("preferred-within-detour-ratio",)
    if fallback_reason is None:
        return ("fallback-shortest-distance",)
    return ("fallback-shortest-distance", fallback_reason)


def _pattern_geometry_source(segments: tuple[SynthesizedSegmentPath, ...]) -> str:
    if segments and all(segment.geometry_source == GEOMETRY_SOURCE_INFERRED_PREFERRED for segment in segments):
        return GEOMETRY_SOURCE_INFERRED_PREFERRED
    return GEOMETRY_SOURCE_INFERRED_FALLBACK


def _build_link_graph(modal_links: gpd.GeoDataFrame, config: GTFSRouteSynthesisConfig) -> dict[int, list[tuple]]:
    graph: dict[int, list[tuple[int, float, int, int]]] = {}
    for _, row in modal_links.iterrows():
        link_id = int(row[config.link_id_field])
        a_node = int(row.a_node)
        b_node = int(row.b_node)
        direction = int(row[config.direction_field])
        cost = _link_cost(row, config)
        graph.setdefault(a_node, [])
        graph.setdefault(b_node, [])
        if direction in (0, 1):
            graph[a_node].append((b_node, cost, link_id, 1))
        if direction in (0, -1):
            graph[b_node].append((a_node, cost, link_id, -1))
    return graph


def _best_segment_path(
    from_candidates: tuple[StopLinkCandidate, ...],
    to_candidates: tuple[StopLinkCandidate, ...],
    graph: dict[int, list[tuple]],
    link_rows: dict[int, object],
    config: GTFSRouteSynthesisConfig,
) -> tuple[tuple[int, ...], tuple[int, ...], float] | None:
    direct = _direct_shared_link_path(from_candidates, to_candidates, link_rows, config)
    if direct is not None:
        return direct

    best_path = None
    best_distance = float("inf")
    destination_states = [
        state for candidate in to_candidates for state in _destination_states(candidate, link_rows, config)
    ]
    for origin_candidate in from_candidates:
        for origin_node, origin_link_id, origin_direction, origin_cost in _origin_states(
            origin_candidate, link_rows, config
        ):
            distances, paths = _dijkstra(origin_node, graph)
            for destination_node, destination_link_id, destination_direction, destination_cost in destination_states:
                if destination_node not in distances:
                    continue
                middle = paths[destination_node]
                sequence = [(origin_link_id, origin_direction), *middle, (destination_link_id, destination_direction)]
                sequence = _dedupe_adjacent_links(sequence)
                distance = origin_cost + distances[destination_node] + destination_cost
                if distance < best_distance:
                    best_distance = distance
                    best_path = sequence

    if best_path is None or not isfinite(best_distance):
        return None
    link_ids = tuple(link_id for link_id, _ in best_path)
    directions = tuple(direction for _, direction in best_path)
    return link_ids, directions, best_distance


def _direct_shared_link_path(
    from_candidates: tuple[StopLinkCandidate, ...],
    to_candidates: tuple[StopLinkCandidate, ...],
    link_rows: dict[int, object],
    config: GTFSRouteSynthesisConfig,
) -> tuple[tuple[int, ...], tuple[int, ...], float] | None:
    to_link_ids = {candidate.link_id for candidate in to_candidates}
    for candidate in from_candidates:
        if candidate.link_id not in to_link_ids or candidate.link_id not in link_rows:
            continue
        row = link_rows[candidate.link_id]
        direction = int(row[config.direction_field])
        path_direction = 1 if direction in (0, 1) else -1
        return (candidate.link_id,), (path_direction,), _link_cost(row, config)
    return None


def _origin_states(
    candidate: StopLinkCandidate, link_rows: dict[int, object], config: GTFSRouteSynthesisConfig
) -> tuple[tuple[int, int, int, float], ...]:
    if candidate.link_id not in link_rows:
        return ()
    row = link_rows[candidate.link_id]
    cost = _link_cost(row, config)
    states = []
    if candidate.direction in (0, 1):
        states.append((candidate.b_node, candidate.link_id, 1, cost))
    if candidate.direction in (0, -1):
        states.append((candidate.a_node, candidate.link_id, -1, cost))
    return tuple(states)


def _destination_states(
    candidate: StopLinkCandidate, link_rows: dict[int, object], config: GTFSRouteSynthesisConfig
) -> tuple[tuple[int, int, int, float], ...]:
    if candidate.link_id not in link_rows:
        return ()
    row = link_rows[candidate.link_id]
    cost = _link_cost(row, config)
    states = []
    if candidate.direction in (0, 1):
        states.append((candidate.a_node, candidate.link_id, 1, cost))
    if candidate.direction in (0, -1):
        states.append((candidate.b_node, candidate.link_id, -1, cost))
    return tuple(states)


def _dijkstra(
    origin_node: int, graph: dict[int, list[tuple]]
) -> tuple[dict[int, float], dict[int, list[tuple[int, int]]]]:
    distances = {origin_node: 0.0}
    paths = {origin_node: []}
    queue = [(0.0, origin_node)]
    while queue:
        distance, node = heappop(queue)
        if distance > distances[node]:
            continue
        for next_node, cost, link_id, direction in graph.get(node, []):
            next_distance = distance + cost
            if next_distance >= distances.get(next_node, float("inf")):
                continue
            distances[next_node] = next_distance
            paths[next_node] = [*paths[node], (link_id, direction)]
            heappush(queue, (next_distance, next_node))
    return distances, paths


def _dedupe_adjacent_links(sequence: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    deduped = []
    for item in sequence:
        if not deduped or deduped[-1] != item:
            deduped.append(item)
    return tuple(deduped)


def _link_cost(row, config: GTFSRouteSynthesisConfig) -> float:
    value = float(row[config.distance_cost_field])
    if not isfinite(value) or value <= 0:
        return max(float(row.geometry.length), 0.001)
    return value


def _assemble_path_geometry(
    link_ids: tuple[int, ...], directions: tuple[int, ...], link_rows: dict[int, object]
) -> LineString | None:
    geoms = []
    for link_id, direction in zip(link_ids, directions, strict=True):
        if link_id not in link_rows:
            continue
        coords = list(link_rows[link_id].geometry.coords)
        if direction == -1:
            coords = list(reversed(coords))
        geoms.append(LineString(coords))
    return _merge_segment_geometries(geoms)


def _merge_segment_geometries(geometries: Iterable[LineString | None]) -> LineString | None:
    valid = tuple(geometry for geometry in geometries if geometry is not None and not geometry.is_empty)
    if not valid:
        return None
    merged = linemerge(valid)
    if isinstance(merged, LineString):
        return merged
    coords = []
    for geometry in valid:
        part = list(geometry.coords)
        if coords and part and coords[-1] == part[0]:
            coords.extend(part[1:])
        else:
            coords.extend(part)
    return LineString(coords) if len(coords) >= 2 else None


def _pattern_mapping_rows(
    pattern_id: int, segments: tuple[SynthesizedSegmentPath, ...]
) -> tuple[PatternMappingRow, ...]:
    rows = []
    for segment in segments:
        for link_id, direction in zip(segment.link_ids, segment.directions, strict=True):
            rows.append(
                PatternMappingRow(
                    pattern_id=pattern_id,
                    seq=len(rows),
                    link_id=link_id,
                    direction=direction,
                )
            )
    return tuple(rows)


def _rejected_segment(
    seq: int,
    from_match: StopNetworkMatch,
    to_match: StopNetworkMatch,
    reason: str,
    selected_path_distance: float | None = None,
) -> SynthesizedSegmentPath:
    diagnostics = SegmentPathDiagnostics(
        seq=seq,
        from_stop_id=from_match.stop_id,
        to_stop_id=to_match.stop_id,
        status=SEGMENT_REJECTED,
        geometry_source=GEOMETRY_SOURCE_REJECTED,
        reason=reason,
        selected_path_distance=selected_path_distance,
        fallback_path_distance=selected_path_distance,
    )
    return SynthesizedSegmentPath(
        seq=seq,
        from_stop_id=from_match.stop_id,
        to_stop_id=to_match.stop_id,
        from_internal_stop_id=from_match.internal_stop_id,
        to_internal_stop_id=to_match.internal_stop_id,
        link_ids=(),
        directions=(),
        geometry=None,
        geometry_source=GEOMETRY_SOURCE_REJECTED,
        diagnostics=diagnostics,
    )


__all__ = [
    "GEOMETRY_SOURCE_INFERRED_FALLBACK",
    "GEOMETRY_SOURCE_INFERRED_PREFERRED",
    "GEOMETRY_SOURCE_REJECTED",
    "GEOMETRY_SOURCE_SHAPE",
    "GTFSGeometrySourceInventory",
    "GTFSRouteSynthesisConfig",
    "FALLBACK_PREFERRED_EXCESSIVE_DETOUR",
    "FALLBACK_PREFERRED_UNAVAILABLE",
    "FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED",
    "PatternMappingRow",
    "REJECT_DISCONNECTED_STOP_PAIR",
    "REJECT_EXCESSIVE_SEGMENT_DISTANCE",
    "REJECT_INSUFFICIENT_RETAINED_STOPS",
    "REJECT_UNMATCHED_STOP",
    "REJECT_UNSUPPORTED_ROUTE_TYPE",
    "RoutePatternSynthesisInput",
    "SEGMENT_OK",
    "SEGMENT_REJECTED",
    "SEGMENT_UNTESTED",
    "SegmentPathDiagnostics",
    "STOP_MATCHED_FALLBACK",
    "STOP_MATCHED_MODAL",
    "STOP_UNMATCHED",
    "StopLinkCandidate",
    "StopNetworkMatch",
    "SynthesizedPatternGeometry",
    "SynthesizedSegmentPath",
    "infer_stop_to_stop_segment",
    "inventory_gtfs_geometry_sources",
    "match_stop_to_network",
    "route_pattern_synthesis_inputs",
    "synthesize_inferred_pattern_geometry",
]
