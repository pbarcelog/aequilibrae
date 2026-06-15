"""Karlsruhe connector inference validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import openmatrix as omx
import pandas as pd

from aequilibrae import Project
from aequilibrae.project.network.connector_creation import bulk_connector_creation
from aequilibrae.project.network.spread_connector_creation import (
    SpreadConnectorConfig,
    bulk_spread_connector_creation,
)

EXTERNAL_ZONE_THRESHOLD = 1_000_000
KARLSRUHE_PROJECTED_CRS = "EPSG:25832"

VISUM_TOKEN_TO_MODE: dict[str, str] = {
    "CAR": "c",
    "HGV": "h",
    "PUTW": "w",
    "BIKE": "b",
    "WALK": "w",
    "BUS": "t",
    "TRAM": "l",
    "TRAIN": "r",
}

DEFAULT_INFERENCE_MODES = ("c", "h")


@dataclass(frozen=True)
class ModeConnectorAccuracy:
    """Accuracy of inferred connectors against ground truth for one matrix mode."""

    mode: str
    ground_truth_connectors: int
    covered_connectors: int
    coverage: float
    inferred_connectors: int
    spurious_connectors: int
    noise_rate: float

    @classmethod
    def empty(cls, mode: str) -> ModeConnectorAccuracy:
        return cls(mode, 0, 0, 0.0, 0, 0, 0.0)


@dataclass(frozen=True)
class MatrixConnectorAccuracy:
    """Combined accuracy across the matrix modes (e.g. car + hgv)."""

    modes: tuple[str, ...]
    ground_truth_connectors: int
    covered_connectors: int
    coverage: float
    inferred_connectors: int
    spurious_connectors: int
    noise_rate: float


def external_visum_geojson_folder(request) -> Path:
    folder = request.config.getoption("--visum-geojson-folder")
    if folder is None:
        raise pytest_skip_missing_folder()
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"VISUM GeoJSON input must be a folder: {folder}")
    return folder


def pytest_skip_missing_folder():
    import pytest

    pytest.skip("Pass --visum-geojson-folder to run Karlsruhe connector inference validation")


def parse_visum_tsysset_modes(value) -> frozenset[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return frozenset()
    text = str(value).strip()
    if not text:
        return frozenset()
    modes = set()
    for token in text.split(","):
        mode = VISUM_TOKEN_TO_MODE.get(token.strip().upper())
        if mode is not None:
            modes.add(mode)
    return frozenset(modes)


def modes_to_string(modes: Iterable[str]) -> str:
    return "".join(sorted(set(modes)))


def load_ground_truth_connector_pairs(folder: Path) -> pd.DataFrame:
    """Return unique (zone_no, node_no, modes) tuples from connector.geojson."""
    path = folder / "connector.geojson"
    if not path.is_file():
        raise FileNotFoundError(f"Ground-truth connector layer not found: {path}")

    connectors = gpd.read_file(path)
    records: list[tuple[int, int, str]] = []
    for _, row in connectors.iterrows():
        zone_no = int(row["ZONENO"])
        node_no = int(row["NODENO"])
        modes = modes_to_string(parse_visum_tsysset_modes(row.get("TSYSSET")))
        if modes:
            records.append((zone_no, node_no, modes))

    if not records:
        raise ValueError("connector.geojson produced no mode-bearing ground-truth pairs")

    return pd.DataFrame(records, columns=["zone_no", "node_no", "modes"]).drop_duplicates()


def load_zone_demand_from_omx(folder: Path, modes: Iterable[str] = ("Car", "HVG")) -> dict[int, float]:
    """Load zone production+attraction totals from the first matching OMX file."""
    omx_files = sorted(folder.glob("*.omx"))
    if not omx_files:
        return {}

    mode_list = list(modes)
    with omx.open_file(str(omx_files[0]), "r") as matrix_file:
        mapping = {int(key): int(value) for key, value in matrix_file.mapping("NO").items()}
        arrays = [np.array(matrix_file[mode_name]) for mode_name in mode_list]

    demand_by_zone: dict[int, float] = {}
    for zone_no, matrix_index in mapping.items():
        production = sum(float(array[matrix_index, :].sum()) for array in arrays)
        attraction = sum(float(array[:, matrix_index].sum()) for array in arrays)
        demand_by_zone[zone_no] = production + attraction
    return demand_by_zone


def internal_and_external_zone_ids(folder: Path, zone_ids: Iterable[int]) -> tuple[set[int], set[int]]:
    polygon_path = folder / "zone_polygon.geojson"
    if polygon_path.is_file():
        polygons = gpd.read_file(polygon_path)
        internal = {int(zone_id) for zone_id in polygons["NO"].tolist()}
        all_ids = {int(zone_id) for zone_id in zone_ids}
        return internal, all_ids - internal

    all_ids = {int(zone_id) for zone_id in zone_ids}
    internal = {zone_id for zone_id in all_ids if zone_id < EXTERNAL_ZONE_THRESHOLD}
    return internal, all_ids - internal


def bootstrap_visum_network_without_connectors(project: Project, folder: Path) -> int:
    project.network.create_from_visum_geojson(folder, accept_default_crs=True)
    return strip_centroid_connectors(project)


def strip_centroid_connectors(project: Project) -> int:
    with project.db_connection as conn:
        deleted = conn.execute("DELETE FROM links WHERE link_type='centroid_connector'").rowcount
    project.network.links.refresh()
    project.network.nodes.refresh_fields()
    return deleted


def infer_connectors_knn(
    project: Project,
    *,
    internal_zone_ids: set[int],
    external_zone_ids: set[int],
    modes: Iterable[str] = DEFAULT_INFERENCE_MODES,
    k_connectors: int = 1,
    projected_crs: str = KARLSRUHE_PROJECTED_CRS,
    distance_upper_bound: float = float("inf"),
) -> None:
    """k-nearest-neighbour connector inference baseline."""
    mode_list = list(modes)
    nodes = project.network.nodes.data
    links = project.network.links.data
    zones = project.zoning.data

    if internal_zone_ids:
        internal_zones = zones[zones.zone_id.isin(internal_zone_ids)]
        with project.db_connection_spatial as conn:
            bulk_connector_creation(
                conn=conn,
                project_nodes=nodes,
                project_links=links,
                project_zones=internal_zones,
                modes=mode_list,
                k_connectors=k_connectors,
                limit_to_zone=True,
                projected_crs=projected_crs,
                distance_upper_bound=distance_upper_bound,
            )
        links = project.network.links.data

    if external_zone_ids:
        external_zones = zones[zones.zone_id.isin(external_zone_ids)]
        with project.db_connection_spatial as conn:
            bulk_connector_creation(
                conn=conn,
                project_nodes=nodes,
                project_links=links,
                project_zones=external_zones,
                modes=mode_list,
                k_connectors=k_connectors,
                limit_to_zone=False,
                projected_crs=projected_crs,
                distance_upper_bound=distance_upper_bound,
            )

    project.network.links.refresh()


def infer_connectors_spread(
    project: Project,
    *,
    internal_zone_ids: set[int],
    external_zone_ids: set[int],
    modes: Iterable[str] = DEFAULT_INFERENCE_MODES,
    zone_demand: dict[int, float] | None = None,
    config: SpreadConnectorConfig | None = None,
    distance_upper_bound: float = float("inf"),
) -> None:
    """Spread connector inference using the library heuristic."""
    mode_list = list(modes)
    heuristic = config or SpreadConnectorConfig(projected_crs=KARLSRUHE_PROJECTED_CRS)
    nodes = project.network.nodes.data
    links = project.network.links.data
    zones = project.zoning.data

    with project.db_connection_spatial as conn:
        bulk_spread_connector_creation(
            conn,
            project_nodes=nodes,
            project_links=links,
            project_zones=zones,
            modes=mode_list,
            internal_zone_ids=internal_zone_ids,
            external_zone_ids=external_zone_ids,
            zone_demand=zone_demand,
            config=heuristic,
            distance_upper_bound=distance_upper_bound,
        )

    project.network.links.refresh()


def load_inferred_connector_pairs(project: Project) -> pd.DataFrame:
    sql = """
        SELECT
            zone_node.visum_zone_no AS zone_no,
            net_node.visum_node_no AS node_no,
            links.modes AS modes
        FROM links
        INNER JOIN nodes AS zone_node
            ON links.a_node = zone_node.node_id AND zone_node.is_centroid = 1
        INNER JOIN nodes AS net_node
            ON links.b_node = net_node.node_id AND net_node.is_centroid = 0
        WHERE links.link_type = 'centroid_connector'
    """
    with project.db_connection as conn:
        inferred = pd.read_sql(sql, conn)

    if inferred.empty:
        raise ValueError("No inferred centroid connectors found in the project")

    inferred["zone_no"] = inferred["zone_no"].astype(int)
    inferred["node_no"] = inferred["node_no"].astype(int)
    inferred["modes"] = inferred["modes"].fillna("").astype(str)
    return inferred.drop_duplicates()


def _mode_connector_triples(frame: pd.DataFrame, modes: Iterable[str]) -> set[tuple[int, int, str]]:
    allowed = set(modes)
    triples: set[tuple[int, int, str]] = set()
    for zone_no, node_no, mode_string in frame[["zone_no", "node_no", "modes"]].itertuples(index=False, name=None):
        for mode in str(mode_string):
            if mode in allowed:
                triples.add((int(zone_no), int(node_no), mode))
    return triples


def _connector_accuracy(
    ground_truth: pd.DataFrame,
    inferred: pd.DataFrame,
    *,
    modes: Iterable[str],
) -> tuple[int, int, int, int]:
    mode_list = tuple(modes)
    gt = _mode_connector_triples(ground_truth, mode_list)
    inf = _mode_connector_triples(inferred, mode_list)
    covered = len(gt & inf)
    spurious = len(inf - gt)
    return len(gt), covered, len(inf), spurious


def score_mode_accuracy(
    ground_truth: pd.DataFrame,
    inferred: pd.DataFrame,
    *,
    mode: str,
) -> ModeConnectorAccuracy:
    gt_count, covered, inf_count, spurious = _connector_accuracy(ground_truth, inferred, modes=[mode])
    if gt_count == 0 and inf_count == 0:
        return ModeConnectorAccuracy.empty(mode)
    return ModeConnectorAccuracy(
        mode=mode,
        ground_truth_connectors=gt_count,
        covered_connectors=covered,
        coverage=covered / gt_count if gt_count else 0.0,
        inferred_connectors=inf_count,
        spurious_connectors=spurious,
        noise_rate=spurious / inf_count if inf_count else 0.0,
    )


def score_matrix_mode_accuracy(
    ground_truth: pd.DataFrame,
    inferred: pd.DataFrame,
    *,
    modes: Iterable[str] = DEFAULT_INFERENCE_MODES,
) -> MatrixConnectorAccuracy:
    mode_list = tuple(modes)
    gt_count, covered, inf_count, spurious = _connector_accuracy(ground_truth, inferred, modes=mode_list)
    return MatrixConnectorAccuracy(
        modes=mode_list,
        ground_truth_connectors=gt_count,
        covered_connectors=covered,
        coverage=covered / gt_count if gt_count else 0.0,
        inferred_connectors=inf_count,
        spurious_connectors=spurious,
        noise_rate=spurious / inf_count if inf_count else 0.0,
    )


def score_all_mode_accuracies(
    ground_truth: pd.DataFrame,
    inferred: pd.DataFrame,
    *,
    modes: Iterable[str] = DEFAULT_INFERENCE_MODES,
) -> list[ModeConnectorAccuracy]:
    return [score_mode_accuracy(ground_truth, inferred, mode=mode) for mode in modes]
