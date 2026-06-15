from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import isfinite
from typing import Iterable

import geopandas as gpd
import pandas as pd
import shapely.ops
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import linemerge

from aequilibrae.transit.gtfs_coverage import (
    FULLY_COVERED,
    INSUFFICIENT_RETAINED_STOPS,
    TRIM_COVERED,
    GTFSCoverageAnalysis,
    GTFSRoutePattern,
    PatternDecision,
    StopCoverage,
    build_gtfs_route_patterns,
)
from aequilibrae.transit.route_map_matcher import RouteMapMatcher
from aequilibrae.transit.transit_elements.mode_correspondence import mode_corresp
from aequilibrae.utils.geo_utils import metre_crs_for_gdf

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
REJECT_INSUFFICIENT_RETAINED_STOPS = INSUFFICIENT_RETAINED_STOPS
REJECT_SHAPE_MISSING = "shape-missing"
REJECT_SHAPE_DISCONNECTED = "shape-disconnected-match"
REJECT_SHAPE_ROUTE_TYPE = "shape-route-type-incompatible"

FALLBACK_SHAPE_UNAVAILABLE = "shape-guided-unavailable"
FALLBACK_PREFERRED_UNAVAILABLE = "preferred-path-unavailable"
FALLBACK_PREFERRED_EXCESSIVE_DETOUR = "preferred-path-exceeds-detour-ratio"
FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED = "priority-context-unsupported"

GEOMETRY_MODE_DIAGNOSTIC_ONLY = "diagnostic-only"
GEOMETRY_MODE_INFER_NETWORK = "infer-network-paths"


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
class GTFSRouteSynthesisCacheStats:
    """Cache counters for route synthesis diagnostics and performance review."""

    stop_match_hits: int = 0
    stop_match_misses: int = 0
    graph_builds: int = 0
    path_hits: int = 0
    path_misses: int = 0
    dijkstra_hits: int = 0
    dijkstra_misses: int = 0


@dataclass(frozen=True)
class _RouteTypeGraphContext:
    links: gpd.GeoDataFrame
    link_rows: dict[int, object]
    graph: dict[int, list[tuple]]


class GTFSRouteSynthesisCache:
    """Reusable prepared network and routing cache for GTFS route synthesis."""

    def __init__(self, network_links: gpd.GeoDataFrame, config: GTFSRouteSynthesisConfig | None = None):
        self.config = GTFSRouteSynthesisConfig() if config is None else config
        self.links = _prepare_synthesis_links(network_links, self.config)
        self._stop_matches: dict[tuple[int, int], StopNetworkMatch] = {}
        self._route_contexts: dict[int, _RouteTypeGraphContext] = {}
        self._priority_contexts: dict[int, _RouteTypeGraphContext] = {}
        self._path_cache: dict[tuple, tuple[tuple[int, ...], tuple[int, ...], float] | None] = {}
        self._dijkstra_cache: dict[tuple[int, bool], dict[int, tuple[dict[int, float], dict[int, list[tuple]]]]] = {}
        self._stop_match_hits = 0
        self._stop_match_misses = 0
        self._graph_builds = 0
        self._path_hits = 0
        self._path_misses = 0
        self._dijkstra_hits = 0
        self._dijkstra_misses = 0

    @property
    def stats(self) -> GTFSRouteSynthesisCacheStats:
        return GTFSRouteSynthesisCacheStats(
            stop_match_hits=self._stop_match_hits,
            stop_match_misses=self._stop_match_misses,
            graph_builds=self._graph_builds,
            path_hits=self._path_hits,
            path_misses=self._path_misses,
            dijkstra_hits=self._dijkstra_hits,
            dijkstra_misses=self._dijkstra_misses,
        )

    def match_stop(
        self,
        stop_id: str,
        internal_stop_id: int,
        stop_geometry,
        route_type: int,
    ) -> StopNetworkMatch:
        key = (route_type, internal_stop_id)
        if key in self._stop_matches:
            self._stop_match_hits += 1
            return self._stop_matches[key]
        self._stop_match_misses += 1
        match = _match_stop_to_prepared_network(
            stop_id,
            internal_stop_id,
            stop_geometry,
            route_type,
            self.links,
            self.config,
        )
        self._stop_matches[key] = match
        return match

    def route_context(self, route_type: int) -> _RouteTypeGraphContext | None:
        return self._context(route_type, priority_only=False)

    def priority_context(self, route_type: int) -> _RouteTypeGraphContext | None:
        return self._context(route_type, priority_only=True)

    def best_path(
        self,
        route_type: int,
        from_candidates: tuple[StopLinkCandidate, ...],
        to_candidates: tuple[StopLinkCandidate, ...],
        priority_only: bool = False,
    ) -> tuple[tuple[int, ...], tuple[int, ...], float] | None:
        key = (
            route_type,
            priority_only,
            tuple(candidate.link_id for candidate in from_candidates),
            tuple(candidate.link_id for candidate in to_candidates),
        )
        if key in self._path_cache:
            self._path_hits += 1
            return self._path_cache[key]
        self._path_misses += 1
        context = self.priority_context(route_type) if priority_only else self.route_context(route_type)
        if context is None:
            self._path_cache[key] = None
            return None
        dijkstra_cache = self._dijkstra_cache.setdefault((route_type, priority_only), {})
        path = _best_segment_path(
            from_candidates,
            to_candidates,
            context.graph,
            context.link_rows,
            self.config,
            dijkstra_cache=dijkstra_cache,
            dijkstra_stats_callback=self._record_dijkstra_cache,
        )
        self._path_cache[key] = path
        return path

    def _record_dijkstra_cache(self, hit: bool) -> None:
        if hit:
            self._dijkstra_hits += 1
        else:
            self._dijkstra_misses += 1

    def _context(self, route_type: int, priority_only: bool) -> _RouteTypeGraphContext | None:
        contexts = self._priority_contexts if priority_only else self._route_contexts
        if route_type in contexts:
            return contexts[route_type]
        context = self._build_context(route_type, priority_only)
        if context is not None:
            contexts[route_type] = context
        return context

    def _build_context(self, route_type: int, priority_only: bool) -> _RouteTypeGraphContext | None:
        if route_type not in mode_corresp:
            return None
        route_mode = mode_corresp[route_type]
        links = self.links[self.links[self.config.mode_field].str.contains(route_mode, regex=False, na=False)]
        if priority_only:
            links = links[_priority_mask(links, self.config)]
        if links.empty:
            return None
        self._graph_builds += 1
        link_rows = {int(row[self.config.link_id_field]): row for _, row in links.iterrows()}
        return _RouteTypeGraphContext(
            links=links,
            link_rows=link_rows,
            graph=_build_link_graph(links, self.config),
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
class GTFSRouteGeometryPlan:
    """Mode-aware plan for GTFS route geometry review or synthesis."""

    mode: str
    coverage_analysis: GTFSCoverageAnalysis
    eligible_synthesis_inputs: tuple[RoutePatternSynthesisInput, ...]
    synthesis_inputs: tuple[RoutePatternSynthesisInput, ...]

    @property
    def diagnostic_only(self) -> bool:
        return self.mode == GEOMETRY_MODE_DIAGNOSTIC_ONLY

    @property
    def should_synthesize(self) -> bool:
        return bool(self.synthesis_inputs)


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


@dataclass(frozen=True)
class GTFSSynthesisQualitySummary:
    """Report-ready GTFS route synthesis quality tables."""

    pattern_summary: pd.DataFrame
    segment_summary: pd.DataFrame
    route_summary: pd.DataFrame
    route_type_summary: pd.DataFrame
    geometry_source_summary: pd.DataFrame
    fallback_reason_summary: pd.DataFrame
    rejection_reason_summary: pd.DataFrame


def summarize_synthesized_patterns(
    results: Iterable[SynthesizedPatternGeometry],
) -> GTFSSynthesisQualitySummary:
    """Build report tables for synthesized GTFS route-pattern geometry results."""

    pattern_rows = []
    segment_rows = []
    for pattern_index, result in enumerate(results):
        pattern_rows.append(_pattern_summary_row(pattern_index, result))
        segment_rows.extend(_segment_summary_rows(pattern_index, result))

    pattern_summary = pd.DataFrame(pattern_rows, columns=_PATTERN_SUMMARY_COLUMNS)
    segment_summary = pd.DataFrame(segment_rows, columns=_SEGMENT_SUMMARY_COLUMNS)

    return GTFSSynthesisQualitySummary(
        pattern_summary=pattern_summary,
        segment_summary=segment_summary,
        route_summary=_pattern_group_summary(pattern_summary, ("route_id", "route_type")),
        route_type_summary=_pattern_group_summary(pattern_summary, ("route_type",)),
        geometry_source_summary=_geometry_source_summary(pattern_summary, segment_summary),
        fallback_reason_summary=_fallback_reason_summary(segment_summary),
        rejection_reason_summary=_rejection_reason_summary(pattern_summary, segment_summary),
    )


def match_stop_to_network(
    stop_id: str,
    internal_stop_id: int,
    stop_geometry,
    route_type: int,
    network_links: gpd.GeoDataFrame,
    config: GTFSRouteSynthesisConfig | None = None,
    cache: GTFSRouteSynthesisCache | None = None,
) -> StopNetworkMatch:
    """Match one GTFS stop point to nearby route-compatible network links."""

    if cache is not None:
        return cache.match_stop(stop_id, internal_stop_id, stop_geometry, route_type)
    config = GTFSRouteSynthesisConfig() if config is None else config
    links = _prepare_synthesis_links(network_links, config)
    return _match_stop_to_prepared_network(stop_id, internal_stop_id, stop_geometry, route_type, links, config)


def _match_stop_to_prepared_network(
    stop_id: str,
    internal_stop_id: int,
    stop_geometry,
    route_type: int,
    links: gpd.GeoDataFrame,
    config: GTFSRouteSynthesisConfig,
) -> StopNetworkMatch:
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
    cache: GTFSRouteSynthesisCache | None = None,
) -> SynthesizedSegmentPath:
    """Infer one fallback shortest-distance network path between two matched stops."""

    config = cache.config if cache is not None else GTFSRouteSynthesisConfig() if config is None else config
    if route_type not in mode_corresp:
        return _rejected_segment(seq, from_match, to_match, REJECT_UNSUPPORTED_ROUTE_TYPE)
    if not from_match.candidates or not to_match.candidates:
        return _rejected_segment(seq, from_match, to_match, REJECT_UNMATCHED_STOP)

    if cache is not None:
        route_context = cache.route_context(route_type)
        if route_context is None:
            return _rejected_segment(seq, from_match, to_match, REJECT_UNSUPPORTED_ROUTE_TYPE)
        link_rows = route_context.link_rows
        fallback_path = cache.best_path(route_type, from_match.candidates, to_match.candidates)
    else:
        links = _prepare_synthesis_links(network_links, config)
        modal_links = links[links[config.mode_field].str.contains(mode_corresp[route_type], regex=False, na=False)]
        if modal_links.empty:
            return _rejected_segment(seq, from_match, to_match, REJECT_UNSUPPORTED_ROUTE_TYPE)
        link_rows = {int(row[config.link_id_field]): row for _, row in modal_links.iterrows()}
        graph = _build_link_graph(modal_links, config)
        fallback_path = _best_segment_path(from_match.candidates, to_match.candidates, graph, link_rows, config)
    if fallback_path is None:
        return _rejected_segment(seq, from_match, to_match, REJECT_DISCONNECTED_STOP_PAIR)

    preferred_path, fallback_reason = _preferred_segment_path(
        from_match, to_match, route_type, network_links, config, cache
    )
    path = _choose_segment_path(preferred_path, fallback_path, config)

    if cache is not None and path is preferred_path:
        priority_context = cache.priority_context(route_type)
        if priority_context is not None:
            link_rows = priority_context.link_rows
    elif cache is None and path is preferred_path:
        priority_links = modal_links[_priority_mask(modal_links, config)]
        link_rows = {int(row[config.link_id_field]): row for _, row in priority_links.iterrows()}

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


def resolve_pattern_loaded_shape(gtfs_data, pattern: GTFSRoutePattern) -> LineString | None:
    """Return the first loaded GTFS shape referenced by a pattern trip, if any."""

    shapes = getattr(gtfs_data, "shapes", {})
    if not shapes:
        return None
    for trip_id in pattern.trip_ids:
        trip = _trip_lookup(gtfs_data).get(str(trip_id))
        if trip is None:
            continue
        shape_id = _trip_shape_id(trip)
        if shape_id and shape_id in shapes:
            shape = shapes[shape_id]
            if shape is not None and not getattr(shape, "is_empty", False):
                return shape
    return None


def build_route_map_matcher(
    network_links: gpd.GeoDataFrame,
    stop_records: Iterable[tuple[str, object]],
    route_type: int,
    network_nodes: gpd.GeoDataFrame | None = None,
) -> RouteMapMatcher | None:
    """Build a route-type map matcher for the retained GTFS stops used in shape-guided synthesis."""

    if route_type not in mode_corresp:
        return None
    pt_mode = mode_corresp[route_type]
    links = network_links[network_links["modes"].astype(str).str.contains(pt_mode, regex=False, na=False)].copy()
    if links.empty:
        return None
    if "speed_ab" not in links.columns:
        links["speed_ab"] = 30.0
    if "speed_ba" not in links.columns:
        links["speed_ba"] = 30.0
    if "distance" not in links.columns:
        links["distance"] = links.geometry.length

    if network_nodes is None:
        network_nodes = _nodes_from_links(links)
    else:
        node_ids = set(links.a_node.astype(int)) | set(links.b_node.astype(int))
        network_nodes = network_nodes[network_nodes.node_id.isin(node_ids)]

    stop_rows = []
    for stop_id, geometry in stop_records:
        if geometry is None or getattr(geometry, "is_empty", False):
            continue
        stop_rows.append({"stop_id": str(stop_id), "geometry": geometry})
    if len(stop_rows) < 2:
        return None

    stops_gdf = gpd.GeoDataFrame(stop_rows, geometry="geometry", crs=network_links.crs)
    if network_nodes.empty or stops_gdf.empty:
        return None

    matcher = RouteMapMatcher(links, network_nodes, stops_gdf)
    matcher.initialize_graph()
    return matcher


def synthesize_shape_guided_pattern_geometry(
    synthesis_input: RoutePatternSynthesisInput,
    stops: dict[int, object],
    route_shape: LineString,
    network_links: gpd.GeoDataFrame,
    pattern_id: int = -1,
    network_nodes: gpd.GeoDataFrame | None = None,
) -> SynthesizedPatternGeometry | None:
    """Synthesize route geometry from GTFS ``shapes.txt`` using the existing map matcher."""

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

    route_type = synthesis_input.pattern.route_type
    stop_records = []
    for stop_id, internal_stop_id in zip(retained_stop_ids, retained_internal_stop_ids, strict=True):
        stop = stops.get(internal_stop_id)
        if stop is None or getattr(stop, "geo", None) is None:
            return _shape_rejected_pattern(
                synthesis_input,
                retained_stop_ids,
                retained_internal_stop_ids,
                REJECT_SHAPE_DISCONNECTED,
            )
        stop_records.append((stop_id, stop.geo))

    matcher = build_route_map_matcher(network_links, stop_records, route_type, network_nodes)
    if matcher is None:
        return _shape_rejected_pattern(
            synthesis_input,
            retained_stop_ids,
            retained_internal_stop_ids,
            REJECT_SHAPE_ROUTE_TYPE,
        )

    utm_zone = metre_crs_for_gdf(network_links)
    to_matcher = Transformer.from_crs(network_links.crs, utm_zone, always_xy=True)
    from_matcher = Transformer.from_crs(utm_zone, network_links.crs, always_xy=True)
    route_shape_matcher = shapely.ops.transform(to_matcher.transform, route_shape)

    config = GTFSRouteSynthesisConfig()
    prepared_links = _prepare_synthesis_links(network_links, config)
    modal_links = prepared_links[
        prepared_links[config.mode_field].astype(str).str.contains(mode_corresp[route_type], regex=False, na=False)
    ]
    link_rows = {int(row[config.link_id_field]): row for _, row in modal_links.iterrows()}

    segments = []
    for seq in range(len(retained_stop_ids) - 1):
        from_stop_id = retained_stop_ids[seq]
        to_stop_id = retained_stop_ids[seq + 1]
        from_internal = retained_internal_stop_ids[seq]
        to_internal = retained_internal_stop_ids[seq + 1]
        segment = _shape_guided_segment(
            seq,
            from_stop_id,
            to_stop_id,
            from_internal,
            to_internal,
            stops,
            matcher,
            route_shape_matcher,
            to_matcher,
            from_matcher,
            link_rows,
            config,
        )
        if segment is None:
            return _shape_rejected_pattern(
                synthesis_input,
                retained_stop_ids,
                retained_internal_stop_ids,
                REJECT_SHAPE_DISCONNECTED,
            )
        segments.append(segment)

    diagnostics = tuple(segment.diagnostics for segment in segments)
    rejected = tuple(segment for segment in segments if segment.diagnostics.status == SEGMENT_REJECTED)
    if rejected:
        return _shape_rejected_pattern(
            synthesis_input,
            retained_stop_ids,
            retained_internal_stop_ids,
            rejected[0].diagnostics.reason or REJECT_SHAPE_DISCONNECTED,
            segments=segments,
            diagnostics=diagnostics,
        )

    mapping = _pattern_mapping_rows(pattern_id, tuple(segments))
    geometry = _merge_segment_geometries(segment.geometry for segment in segments)
    return SynthesizedPatternGeometry(
        pattern=synthesis_input.pattern,
        coverage_decision=synthesis_input.coverage_decision,
        retained_stop_ids=retained_stop_ids,
        retained_internal_stop_ids=retained_internal_stop_ids,
        segments=tuple(segments),
        pattern_mapping=mapping,
        geometry=geometry,
        geometry_source=GEOMETRY_SOURCE_SHAPE,
        accepted=True,
        diagnostics=diagnostics,
    )


def synthesize_pattern_geometry(
    synthesis_input: RoutePatternSynthesisInput,
    stops: dict[int, object],
    network_links: gpd.GeoDataFrame,
    gtfs_data=None,
    pattern_id: int = -1,
    config: GTFSRouteSynthesisConfig | None = None,
    cache: GTFSRouteSynthesisCache | None = None,
    network_nodes: gpd.GeoDataFrame | None = None,
) -> SynthesizedPatternGeometry:
    """Synthesize one GTFS pattern, preferring source shapes and falling back to network inference."""

    route_shape = resolve_pattern_loaded_shape(gtfs_data, synthesis_input.pattern) if gtfs_data is not None else None
    if route_shape is not None:
        shape_result = synthesize_shape_guided_pattern_geometry(
            synthesis_input,
            stops,
            route_shape,
            network_links,
            pattern_id=pattern_id,
            network_nodes=network_nodes,
        )
        if shape_result is not None and shape_result.accepted:
            return shape_result

    inferred = synthesize_inferred_pattern_geometry(
        synthesis_input,
        stops,
        network_links,
        pattern_id=pattern_id,
        config=config,
        cache=cache,
    )
    if route_shape is not None and inferred.accepted:
        diagnostics = tuple(
            SegmentPathDiagnostics(
                seq=diagnostic.seq,
                from_stop_id=diagnostic.from_stop_id,
                to_stop_id=diagnostic.to_stop_id,
                status=diagnostic.status,
                geometry_source=diagnostic.geometry_source,
                reason=FALLBACK_SHAPE_UNAVAILABLE,
                selected_path_distance=diagnostic.selected_path_distance,
                preferred_path_distance=diagnostic.preferred_path_distance,
                fallback_path_distance=diagnostic.fallback_path_distance,
                detour_ratio=diagnostic.detour_ratio,
                flags=(*diagnostic.flags, FALLBACK_SHAPE_UNAVAILABLE),
            )
            for diagnostic in inferred.diagnostics
        )
        segments = tuple(
            SynthesizedSegmentPath(
                seq=segment.seq,
                from_stop_id=segment.from_stop_id,
                to_stop_id=segment.to_stop_id,
                from_internal_stop_id=segment.from_internal_stop_id,
                to_internal_stop_id=segment.to_internal_stop_id,
                link_ids=segment.link_ids,
                directions=segment.directions,
                geometry=segment.geometry,
                geometry_source=segment.geometry_source,
                diagnostics=diagnostics[segment.seq],
            )
            for segment in inferred.segments
        )
        return SynthesizedPatternGeometry(
            pattern=inferred.pattern,
            coverage_decision=inferred.coverage_decision,
            retained_stop_ids=inferred.retained_stop_ids,
            retained_internal_stop_ids=inferred.retained_internal_stop_ids,
            segments=segments,
            pattern_mapping=inferred.pattern_mapping,
            geometry=inferred.geometry,
            geometry_source=inferred.geometry_source,
            accepted=True,
            diagnostics=diagnostics,
        )
    return inferred


def synthesize_inferred_pattern_geometry(
    synthesis_input: RoutePatternSynthesisInput,
    stops: dict[int, object],
    network_links: gpd.GeoDataFrame,
    pattern_id: int = -1,
    config: GTFSRouteSynthesisConfig | None = None,
    cache: GTFSRouteSynthesisCache | None = None,
) -> SynthesizedPatternGeometry:
    """Infer route geometry and pattern-mapping candidates from retained GTFS stops."""

    if cache is None:
        config = GTFSRouteSynthesisConfig() if config is None else config
        cache = GTFSRouteSynthesisCache(network_links, config)
    else:
        config = cache.config
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
            cache,
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
            cache,
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


def plan_gtfs_route_geometry(
    coverage_analysis: GTFSCoverageAnalysis,
    mode: str = GEOMETRY_MODE_DIAGNOSTIC_ONLY,
    accepted_decisions: tuple[str, ...] = (FULLY_COVERED, TRIM_COVERED),
) -> GTFSRouteGeometryPlan:
    """Choose whether coverage-accepted GTFS patterns should remain diagnostic-only or enter synthesis."""

    if mode not in {GEOMETRY_MODE_DIAGNOSTIC_ONLY, GEOMETRY_MODE_INFER_NETWORK}:
        raise ValueError(
            "GTFS route geometry mode must be one of "
            f"{GEOMETRY_MODE_DIAGNOSTIC_ONLY!r} or {GEOMETRY_MODE_INFER_NETWORK!r}"
        )

    eligible = route_pattern_synthesis_inputs(coverage_analysis, accepted_decisions)
    synthesis_inputs = () if mode == GEOMETRY_MODE_DIAGNOSTIC_ONLY else eligible
    return GTFSRouteGeometryPlan(
        mode=mode,
        coverage_analysis=coverage_analysis,
        eligible_synthesis_inputs=eligible,
        synthesis_inputs=synthesis_inputs,
    )


_PATTERN_SUMMARY_COLUMNS = [
    "pattern_index",
    "route_id",
    "route_type",
    "direction_id",
    "pattern_key",
    "coverage_decision",
    "accepted",
    "geometry_source",
    "rejection_reason",
    "original_stop_count",
    "retained_stop_count",
    "trimmed",
    "segment_count",
    "mapping_row_count",
    "inferred_preferred_segment_count",
    "inferred_fallback_segment_count",
    "rejected_segment_count",
]

_SEGMENT_SUMMARY_COLUMNS = [
    "pattern_index",
    "route_id",
    "route_type",
    "direction_id",
    "pattern_key",
    "seq",
    "from_stop_id",
    "to_stop_id",
    "status",
    "geometry_source",
    "reason",
    "selected_path_distance",
    "preferred_path_distance",
    "fallback_path_distance",
    "detour_ratio",
    "link_count",
    "flags",
]


def _pattern_summary_row(pattern_index: int, result: SynthesizedPatternGeometry) -> dict:
    decision = result.coverage_decision
    original_stop_count = decision.original_stop_count if decision is not None else len(result.pattern.stop_ids)
    retained_stop_count = len(result.retained_stop_ids)
    return {
        "pattern_index": pattern_index,
        "route_id": result.pattern.route_id,
        "route_type": result.pattern.route_type,
        "direction_id": result.pattern.direction_id,
        "pattern_key": repr(result.pattern.key),
        "coverage_decision": None if decision is None else decision.decision,
        "accepted": result.accepted,
        "geometry_source": result.geometry_source,
        "rejection_reason": result.rejection_reason,
        "original_stop_count": original_stop_count,
        "retained_stop_count": retained_stop_count,
        "trimmed": retained_stop_count < original_stop_count,
        "segment_count": len(result.segments),
        "mapping_row_count": len(result.pattern_mapping),
        "inferred_preferred_segment_count": _segment_count(result, GEOMETRY_SOURCE_INFERRED_PREFERRED),
        "inferred_fallback_segment_count": _segment_count(result, GEOMETRY_SOURCE_INFERRED_FALLBACK),
        "rejected_segment_count": _segment_count(result, GEOMETRY_SOURCE_REJECTED),
    }


def _segment_summary_rows(pattern_index: int, result: SynthesizedPatternGeometry) -> list[dict]:
    rows = []
    segments_by_seq = {segment.seq: segment for segment in result.segments}
    diagnostics = result.diagnostics or tuple(segment.diagnostics for segment in result.segments)
    for diagnostic in diagnostics:
        segment = segments_by_seq.get(diagnostic.seq)
        rows.append(
            {
                "pattern_index": pattern_index,
                "route_id": result.pattern.route_id,
                "route_type": result.pattern.route_type,
                "direction_id": result.pattern.direction_id,
                "pattern_key": repr(result.pattern.key),
                "seq": diagnostic.seq,
                "from_stop_id": diagnostic.from_stop_id,
                "to_stop_id": diagnostic.to_stop_id,
                "status": diagnostic.status,
                "geometry_source": diagnostic.geometry_source,
                "reason": diagnostic.reason,
                "selected_path_distance": diagnostic.selected_path_distance,
                "preferred_path_distance": diagnostic.preferred_path_distance,
                "fallback_path_distance": diagnostic.fallback_path_distance,
                "detour_ratio": diagnostic.detour_ratio,
                "link_count": 0 if segment is None else len(segment.link_ids),
                "flags": ",".join(diagnostic.flags),
            }
        )
    return rows


def _segment_count(result: SynthesizedPatternGeometry, geometry_source: str) -> int:
    return sum(1 for segment in result.segments if segment.geometry_source == geometry_source)


def _pattern_group_summary(pattern_summary: pd.DataFrame, group_columns: tuple[str, ...]) -> pd.DataFrame:
    columns = [
        *group_columns,
        "pattern_count",
        "accepted_patterns",
        "rejected_patterns",
        "original_stop_count",
        "retained_stop_count",
        "trimmed_patterns",
        "segment_count",
        "mapping_row_count",
        "inferred_preferred_segment_count",
        "inferred_fallback_segment_count",
        "rejected_segment_count",
    ]
    if pattern_summary.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        pattern_summary.groupby(list(group_columns), dropna=False)
        .agg(
            pattern_count=("pattern_index", "count"),
            accepted_patterns=("accepted", "sum"),
            original_stop_count=("original_stop_count", "sum"),
            retained_stop_count=("retained_stop_count", "sum"),
            trimmed_patterns=("trimmed", "sum"),
            segment_count=("segment_count", "sum"),
            mapping_row_count=("mapping_row_count", "sum"),
            inferred_preferred_segment_count=("inferred_preferred_segment_count", "sum"),
            inferred_fallback_segment_count=("inferred_fallback_segment_count", "sum"),
            rejected_segment_count=("rejected_segment_count", "sum"),
        )
        .reset_index()
    )
    grouped["rejected_patterns"] = grouped["pattern_count"] - grouped["accepted_patterns"]
    return grouped[columns]


def _geometry_source_summary(pattern_summary: pd.DataFrame, segment_summary: pd.DataFrame) -> pd.DataFrame:
    columns = ["level", "geometry_source", "count"]
    frames = []
    if not pattern_summary.empty:
        patterns = pattern_summary.groupby("geometry_source", dropna=False).size().reset_index(name="count")
        patterns.insert(0, "level", "pattern")
        frames.append(patterns)
    if not segment_summary.empty:
        segments = segment_summary.groupby("geometry_source", dropna=False).size().reset_index(name="count")
        segments.insert(0, "level", "segment")
        frames.append(segments)
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns].sort_values(columns[:2]).reset_index(drop=True)


def _fallback_reason_summary(segment_summary: pd.DataFrame) -> pd.DataFrame:
    columns = ["reason", "segment_count"]
    if segment_summary.empty:
        return pd.DataFrame(columns=columns)
    fallbacks = segment_summary[segment_summary["geometry_source"] == GEOMETRY_SOURCE_INFERRED_FALLBACK].copy()
    if fallbacks.empty:
        return pd.DataFrame(columns=columns)
    fallbacks["reason"] = fallbacks["reason"].fillna("none")
    return fallbacks.groupby("reason", dropna=False).size().reset_index(name="segment_count").sort_values("reason")


def _rejection_reason_summary(pattern_summary: pd.DataFrame, segment_summary: pd.DataFrame) -> pd.DataFrame:
    columns = ["level", "reason", "count"]
    frames = []
    if not pattern_summary.empty:
        rejected_patterns = pattern_summary[~pattern_summary["accepted"]].copy()
        if not rejected_patterns.empty:
            rejected_patterns["reason"] = rejected_patterns["rejection_reason"].fillna("none")
            patterns = rejected_patterns.groupby("reason", dropna=False).size().reset_index(name="count")
            patterns.insert(0, "level", "pattern")
            frames.append(patterns)
    if not segment_summary.empty:
        rejected_segments = segment_summary[segment_summary["status"] == SEGMENT_REJECTED].copy()
        if not rejected_segments.empty:
            rejected_segments["reason"] = rejected_segments["reason"].fillna("none")
            segments = rejected_segments.groupby("reason", dropna=False).size().reset_index(name="count")
            segments.insert(0, "level", "segment")
            frames.append(segments)
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns].sort_values(columns[:2]).reset_index(drop=True)


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
    route_type: int,
    network_links: gpd.GeoDataFrame,
    config: GTFSRouteSynthesisConfig,
    cache: GTFSRouteSynthesisCache | None = None,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...], float] | None, str | None]:
    if not _priority_context_supported(from_match, to_match):
        return None, FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED

    if cache is not None:
        priority_context = cache.priority_context(route_type)
        if priority_context is None:
            return None, FALLBACK_PREFERRED_UNAVAILABLE
        priority_link_ids = set(priority_context.link_rows)
    else:
        links = _prepare_synthesis_links(network_links, config)
        modal_links = links[links[config.mode_field].str.contains(mode_corresp[route_type], regex=False, na=False)]
        priority_links = modal_links[_priority_mask(modal_links, config)]
        if priority_links.empty:
            return None, FALLBACK_PREFERRED_UNAVAILABLE
        priority_link_ids = {int(row[config.link_id_field]) for _, row in priority_links.iterrows()}

    from_candidates = tuple(candidate for candidate in from_match.candidates if candidate.link_id in priority_link_ids)
    to_candidates = tuple(candidate for candidate in to_match.candidates if candidate.link_id in priority_link_ids)
    if not from_candidates or not to_candidates:
        return None, FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED

    if cache is not None:
        path = cache.best_path(route_type, from_candidates, to_candidates, priority_only=True)
    else:
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
    if segments and all(segment.geometry_source == GEOMETRY_SOURCE_SHAPE for segment in segments):
        return GEOMETRY_SOURCE_SHAPE
    if segments and all(segment.geometry_source == GEOMETRY_SOURCE_INFERRED_PREFERRED for segment in segments):
        return GEOMETRY_SOURCE_INFERRED_PREFERRED
    return GEOMETRY_SOURCE_INFERRED_FALLBACK


def _nodes_from_links(links: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    nodes: dict[int, Point] = {}
    for _, row in links.iterrows():
        coords = list(row.geometry.coords)
        nodes.setdefault(int(row.a_node), Point(coords[0]))
        nodes.setdefault(int(row.b_node), Point(coords[-1]))
    if not nodes:
        return gpd.GeoDataFrame(columns=["node_id", "geometry"], geometry="geometry", crs=links.crs)
    return gpd.GeoDataFrame(
        [{"node_id": node_id, "geometry": geometry} for node_id, geometry in nodes.items()],
        geometry="geometry",
        crs=links.crs,
    )


def _shape_rejected_pattern(
    synthesis_input: RoutePatternSynthesisInput,
    retained_stop_ids: tuple[str, ...],
    retained_internal_stop_ids: tuple[int, ...],
    rejection_reason: str,
    segments: tuple[SynthesizedSegmentPath, ...] = (),
    diagnostics: tuple[SegmentPathDiagnostics, ...] = (),
) -> SynthesizedPatternGeometry:
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
        rejection_reason=rejection_reason,
        diagnostics=diagnostics,
    )


def _shape_guided_segment(
    seq: int,
    from_stop_id: str,
    to_stop_id: str,
    from_internal_stop_id: int,
    to_internal_stop_id: int,
    stops: dict[int, object],
    matcher: RouteMapMatcher,
    route_shape,
    to_matcher: Transformer,
    from_matcher: Transformer,
    link_rows: dict[int, object],
    config: GTFSRouteSynthesisConfig,
) -> SynthesizedSegmentPath | None:
    from_geo = stops[from_internal_stop_id].geo
    to_geo = stops[to_internal_stop_id].geo
    stop_rows = [
        {"stop_id": from_stop_id, "geometry": shapely.ops.transform(to_matcher.transform, from_geo)},
        {"stop_id": to_stop_id, "geometry": shapely.ops.transform(to_matcher.transform, to_geo)},
    ]
    stops_gdf = gpd.GeoDataFrame(stop_rows, geometry="geometry", crs=matcher.crs)
    matched = matcher.map_match_route(stops_gdf, route_shape, pattern_id=str(seq))
    if matched.empty:
        return None

    link_ids = tuple(int(link_id) for link_id in matched.link_id)
    directions = tuple(int(direction) for direction in matched.dir)
    distance = sum(_link_cost(link_rows[link_id], config) for link_id in link_ids if link_id in link_rows)
    geometry = shapely.ops.transform(from_matcher.transform, matcher.assemble_shape(matched))
    diagnostics = SegmentPathDiagnostics(
        seq=seq,
        from_stop_id=from_stop_id,
        to_stop_id=to_stop_id,
        status=SEGMENT_OK,
        geometry_source=GEOMETRY_SOURCE_SHAPE,
        selected_path_distance=distance if distance > 0 else None,
        flags=("shape-guided",),
    )
    return SynthesizedSegmentPath(
        seq=seq,
        from_stop_id=from_stop_id,
        to_stop_id=to_stop_id,
        from_internal_stop_id=from_internal_stop_id,
        to_internal_stop_id=to_internal_stop_id,
        link_ids=link_ids,
        directions=directions,
        geometry=geometry,
        geometry_source=GEOMETRY_SOURCE_SHAPE,
        diagnostics=diagnostics,
    )


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
    dijkstra_cache: dict[int, tuple[dict[int, float], dict[int, list[tuple[int, int]]]]] | None = None,
    dijkstra_stats_callback=None,
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
            distances, paths = _cached_dijkstra(origin_node, graph, dijkstra_cache, dijkstra_stats_callback)
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


def _cached_dijkstra(
    origin_node: int,
    graph: dict[int, list[tuple]],
    dijkstra_cache: dict[int, tuple[dict[int, float], dict[int, list[tuple[int, int]]]]] | None,
    stats_callback=None,
) -> tuple[dict[int, float], dict[int, list[tuple[int, int]]]]:
    if dijkstra_cache is None:
        return _dijkstra(origin_node, graph)
    if origin_node in dijkstra_cache:
        if stats_callback is not None:
            stats_callback(True)
        return dijkstra_cache[origin_node]
    if stats_callback is not None:
        stats_callback(False)
    result = _dijkstra(origin_node, graph)
    dijkstra_cache[origin_node] = result
    return result


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
                    geometry=segment.geometry,
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
    "GEOMETRY_MODE_DIAGNOSTIC_ONLY",
    "GEOMETRY_MODE_INFER_NETWORK",
    "GTFSGeometrySourceInventory",
    "GTFSRouteGeometryPlan",
    "GTFSRouteSynthesisCache",
    "GTFSRouteSynthesisCacheStats",
    "GTFSRouteSynthesisConfig",
    "GTFSSynthesisQualitySummary",
    "FALLBACK_PREFERRED_EXCESSIVE_DETOUR",
    "FALLBACK_PREFERRED_UNAVAILABLE",
    "FALLBACK_PRIORITY_CONTEXT_UNSUPPORTED",
    "PatternMappingRow",
    "REJECT_DISCONNECTED_STOP_PAIR",
    "REJECT_EXCESSIVE_SEGMENT_DISTANCE",
    "REJECT_INSUFFICIENT_RETAINED_STOPS",
    "REJECT_UNMATCHED_STOP",
    "REJECT_SHAPE_DISCONNECTED",
    "REJECT_SHAPE_MISSING",
    "REJECT_SHAPE_ROUTE_TYPE",
    "REJECT_UNSUPPORTED_ROUTE_TYPE",
    "FALLBACK_SHAPE_UNAVAILABLE",
    "RoutePatternSynthesisInput",
    "build_route_map_matcher",
    "resolve_pattern_loaded_shape",
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
    "plan_gtfs_route_geometry",
    "route_pattern_synthesis_inputs",
    "summarize_synthesized_patterns",
    "synthesize_inferred_pattern_geometry",
    "synthesize_pattern_geometry",
    "synthesize_shape_guided_pattern_geometry",
]
