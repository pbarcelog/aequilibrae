from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from shapely.geometry import LineString

from aequilibrae.transit.gtfs_coverage import (
    FULLY_COVERED,
    TRIM_COVERED,
    GTFSCoverageAnalysis,
    GTFSRoutePattern,
    PatternDecision,
    StopCoverage,
    build_gtfs_route_patterns,
)

GEOMETRY_SOURCE_SHAPE = "gtfs-shape"
GEOMETRY_SOURCE_INFERRED_PREFERRED = "inferred-preferred"
GEOMETRY_SOURCE_INFERRED_FALLBACK = "inferred-fallback"
GEOMETRY_SOURCE_REJECTED = "rejected"

SEGMENT_OK = "ok"
SEGMENT_REJECTED = "rejected"
SEGMENT_UNTESTED = "untested"


@dataclass(frozen=True)
class GTFSRouteSynthesisConfig:
    """Configuration for turning GTFS route patterns into network paths."""

    stop_match_distance: float = 25.0
    fallback_stop_match_distance: float = 100.0
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


__all__ = [
    "GEOMETRY_SOURCE_INFERRED_FALLBACK",
    "GEOMETRY_SOURCE_INFERRED_PREFERRED",
    "GEOMETRY_SOURCE_REJECTED",
    "GEOMETRY_SOURCE_SHAPE",
    "GTFSGeometrySourceInventory",
    "GTFSRouteSynthesisConfig",
    "PatternMappingRow",
    "RoutePatternSynthesisInput",
    "SEGMENT_OK",
    "SEGMENT_REJECTED",
    "SEGMENT_UNTESTED",
    "SegmentPathDiagnostics",
    "SynthesizedPatternGeometry",
    "SynthesizedSegmentPath",
    "inventory_gtfs_geometry_sources",
    "route_pattern_synthesis_inputs",
]
