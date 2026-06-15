"""Spread-based centroid connector placement for zoned networks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from sqlite3 import Connection
from typing import Mapping, Union

import geopandas as gpd
import numpy as np
import pandas as pd

from aequilibrae.project.network.connector_creation import bulk_connector_creation, insert_connector_pairs

logger = logging.getLogger(__name__)

MOTORWAY_LINK_PATTERN = re.compile(r"motor|autobahn|freeway|highway|schnell", re.IGNORECASE)
HIGHWAY_CAPACITY_THRESHOLD = 50_000.0


@dataclass(frozen=True)
class SpreadConnectorConfig:
    """Heuristic spread placement tuned from federated network-demand studies."""

    min_spacing_m: float = 150.0
    relaxed_spacing_m: float = 100.0
    min_connectors: int = 2
    max_connectors: int = 4
    perimeter_m_per_connector: float = 625.0
    demand_quartile_for_extra_connector: float = 0.75
    projected_crs: Union[str, int] = "EPSG:3857"


def bulk_spread_connector_creation(
    conn: Connection,
    project_nodes: gpd.GeoDataFrame,
    project_links: gpd.GeoDataFrame,
    project_zones: gpd.GeoDataFrame,
    modes: list[str],
    *,
    internal_zone_ids: set[int] | None = None,
    external_zone_ids: set[int] | None = None,
    zone_demand: Mapping[int, float] | None = None,
    config: SpreadConnectorConfig | None = None,
    distance_upper_bound: float = float("inf"),
) -> None:
    """
    Create spread centroid connectors for internal zones and k=1 global links for external zones.

  Internal zones use perimeter-scaled counts, edge-biased greedy spacing, optional demand bump,
  and motorway de-prioritisation. Node capacity is not used.
    """
    assert project_links.crs == project_nodes.crs == project_zones.crs, "Mismatched CRS"
    assert modes, "Modes must be provided"

    heuristic = config or SpreadConnectorConfig()
    all_zone_ids = set(project_zones["zone_id"].astype(int))
    internal_ids = internal_zone_ids if internal_zone_ids is not None else all_zone_ids
    external_ids = external_zone_ids if external_zone_ids is not None else set()

    if internal_ids:
        internal_zones = project_zones[project_zones["zone_id"].isin(internal_ids)]
        pairs = select_spread_connector_pairs(
            internal_zones,
            project_nodes,
            project_links,
            modes=modes,
            zone_demand=zone_demand,
            config=heuristic,
        )
        if pairs.empty:
            raise ValueError("Spread connector heuristic produced no internal connector pairs")
        insert_connector_pairs(
            conn,
            project_nodes=project_nodes,
            project_links=project_links,
            pairs=pairs,
            modes=modes,
        )

    if external_ids:
        external_zones = project_zones[project_zones["zone_id"].isin(external_ids)]
        bulk_connector_creation(
            conn=conn,
            project_nodes=project_nodes,
            project_links=project_links,
            project_zones=external_zones,
            modes=modes,
            k_connectors=1,
            limit_to_zone=False,
            projected_crs=heuristic.projected_crs,
            distance_upper_bound=distance_upper_bound,
        )


def select_spread_connector_pairs(
    zones: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    links: gpd.GeoDataFrame,
    *,
    modes: list[str],
    zone_demand: Mapping[int, float] | None = None,
    config: SpreadConnectorConfig | None = None,
) -> pd.DataFrame:
    """Return centroid-to-node connector pairs for spread placement."""
    heuristic = config or SpreadConnectorConfig()
    eligible = _nodes_supporting_modes(nodes, modes)
    if eligible.empty:
        raise ValueError("No network nodes support the requested connector modes")

    motorway_nodes = _motorway_endpoint_node_ids(links)
    high_demand_zones = _high_demand_zone_ids(zone_demand, zones["zone_id"].astype(int).tolist(), heuristic)
    zone_to_nodes = zones.sindex.query(eligible.geometry, predicate="within")
    nodes_by_zone: dict[int, list[int]] = {}
    for node_idx, zone_idx in zip(zone_to_nodes[0], zone_to_nodes[1], strict=True):
        zone_id = int(zones.iloc[zone_idx]["zone_id"])
        nodes_by_zone.setdefault(zone_id, []).append(int(eligible.iloc[node_idx]["node_id"]))

    pairs: list[tuple[int, int]] = []
    zones_metric = zones.to_crs(heuristic.projected_crs)

    for zone_id, node_ids in nodes_by_zone.items():
        zone_row = zones_metric.loc[zones_metric["zone_id"] == zone_id]
        if zone_row.empty:
            continue
        zone_geometry_wgs = zones.loc[zones["zone_id"] == zone_id, "geometry"].iloc[0]
        perimeter_m = float(zone_row.geometry.iloc[0].length)
        target = _target_connector_count(zone_id, perimeter_m, zone_id in high_demand_zones, heuristic)

        zone_nodes = eligible[eligible["node_id"].isin(node_ids)]
        boundary_nodes = _boundary_endpoint_node_ids(zone_geometry_wgs, set(node_ids), links)
        candidates = _candidate_frame_for_zone(
            zone_id,
            zone_geometry_wgs,
            zone_nodes,
            boundary_nodes,
            motorway_nodes,
            eligible.crs,
            heuristic.projected_crs,
        )
        if candidates.empty:
            continue

        geom_lookup = zone_nodes.to_crs(heuristic.projected_crs).set_index("node_id")["geometry"]
        candidates["geometry"] = candidates["node_id"].map(geom_lookup)
        selected = _greedy_spread_select(
            candidates,
            target,
            min_spacing_m=heuristic.min_spacing_m,
            relaxed_spacing_m=heuristic.relaxed_spacing_m,
            min_connectors=heuristic.min_connectors,
        )
        pairs.extend((zone_id, node_id) for node_id in selected)

    return pd.DataFrame(pairs, columns=["a_node", "b_node"])


def _target_connector_count(
    zone_id: int,
    perimeter_m: float,
    high_demand: bool,
    config: SpreadConnectorConfig,
) -> int:
    del zone_id
    if perimeter_m <= 0:
        target = config.min_connectors
    else:
        target = int(round(perimeter_m / config.perimeter_m_per_connector))
    target = int(np.clip(target, config.min_connectors, config.max_connectors))
    if high_demand:
        target = min(config.max_connectors, target + 1)
    return target


def _high_demand_zone_ids(
    zone_demand: Mapping[int, float] | None,
    zone_ids: list[int],
    config: SpreadConnectorConfig,
) -> set[int]:
    if not zone_demand:
        return set()
    values = [float(zone_demand[zone_id]) for zone_id in zone_ids if zone_id in zone_demand]
    if not values:
        return set()
    threshold = float(np.quantile(values, config.demand_quartile_for_extra_connector))
    return {zone_id for zone_id in zone_ids if float(zone_demand.get(zone_id, 0.0)) >= threshold}


def _nodes_supporting_modes(nodes: gpd.GeoDataFrame, modes: list[str]) -> gpd.GeoDataFrame:
    mask = nodes["modes"].fillna("").apply(lambda value: all(mode in str(value) for mode in modes))
    return nodes.loc[mask & (nodes["is_centroid"] != 1), ["node_id", "geometry"]].copy()


def _motorway_endpoint_node_ids(links: gpd.GeoDataFrame) -> set[int]:
    motorway_nodes: set[int] = set()
    for _, link in links.iterrows():
        link_type = str(link.get("link_type", ""))
        capacity = max(float(link.get("capacity_ab") or 0.0), float(link.get("capacity_ba") or 0.0))
        if not MOTORWAY_LINK_PATTERN.search(link_type) and capacity < HIGHWAY_CAPACITY_THRESHOLD:
            continue
        motorway_nodes.add(int(link["a_node"]))
        motorway_nodes.add(int(link["b_node"]))
    return motorway_nodes


def _boundary_endpoint_node_ids(
    zone_geometry,
    zone_node_ids: set[int],
    links: gpd.GeoDataFrame,
) -> set[int]:
    boundary = zone_geometry.boundary
    crossing = links[links.geometry.intersects(boundary)]
    endpoints: set[int] = set()
    for _, link in crossing.iterrows():
        for node_id in (int(link["a_node"]), int(link["b_node"])):
            if node_id in zone_node_ids:
                endpoints.add(node_id)
    return endpoints


def _candidate_frame_for_zone(
    zone_id: int,
    zone_geometry,
    eligible_nodes: gpd.GeoDataFrame,
    boundary_nodes: set[int],
    motorway_nodes: set[int],
    source_crs,
    projected_crs: Union[str, int],
) -> pd.DataFrame:
    zone_metric = gpd.GeoSeries([zone_geometry], crs=source_crs).to_crs(projected_crs).iloc[0]
    center = zone_metric.centroid
    boundary = zone_metric.boundary
    nodes_metric = eligible_nodes.to_crs(projected_crs)

    records = []
    for _, row in nodes_metric.iterrows():
        point = row.geometry
        dist_edge = float(point.distance(boundary))
        dist_center = float(point.distance(center))
        node_id = int(row["node_id"])
        records.append(
            {
                "zone_id": zone_id,
                "node_id": node_id,
                "dist_to_edge_m": dist_edge,
                "dist_to_center_m": dist_center,
                "is_boundary": int(node_id in boundary_nodes),
                "motorway_penalty": int(node_id in motorway_nodes),
                "edge_score": dist_center / max(dist_edge, 1.0),
            }
        )
    return pd.DataFrame(records)


def _greedy_spread_select(
    candidates: pd.DataFrame,
    target: int,
    *,
    min_spacing_m: float,
    relaxed_spacing_m: float,
    min_connectors: int,
) -> list[int]:
    if candidates.empty or target <= 0:
        return []

    ordered = candidates.sort_values(
        by=["is_boundary", "edge_score", "motorway_penalty", "dist_to_edge_m"],
        ascending=[False, False, True, True],
    )
    selected_ids, selected_geoms = _greedy_pass(ordered, candidates, target, min_spacing_m)
    minimum_required = min(target, min_connectors)
    if len(selected_ids) < minimum_required:
        remaining = ordered[~ordered["node_id"].isin(selected_ids)]
        extra_ids, extra_geoms = _greedy_pass(
            remaining,
            candidates,
            target - len(selected_ids),
            relaxed_spacing_m,
            blocked_geoms=selected_geoms,
        )
        selected_ids.extend(extra_ids)
        selected_geoms.extend(extra_geoms)

    if not selected_ids:
        selected_ids.append(int(ordered.iloc[0]["node_id"]))
    return selected_ids


def _greedy_pass(
    ordered: pd.DataFrame,
    candidates: pd.DataFrame,
    target: int,
    spacing_m: float,
    *,
    blocked_geoms: list | None = None,
) -> tuple[list[int], list]:
    geom_by_node = dict(zip(candidates["node_id"], candidates["geometry"], strict=False))
    selected_ids: list[int] = []
    selected_geoms = list(blocked_geoms or [])

    for _, row in ordered.iterrows():
        if len(selected_ids) >= target:
            break
        node_id = int(row["node_id"])
        point = geom_by_node.get(node_id)
        if point is None:
            continue
        if any(point.distance(other) < spacing_m for other in selected_geoms):
            continue
        selected_ids.append(node_id)
        selected_geoms.append(point)

    return selected_ids, selected_geoms
