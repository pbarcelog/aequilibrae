import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from aequilibrae.project.network.spread_connector_creation import (
    SpreadConnectorConfig,
    select_spread_connector_pairs,
)


def test_select_spread_connector_pairs_prefers_edge_nodes():
    crs = "EPSG:25832"
    zone = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    zones = gpd.GeoDataFrame({"zone_id": [1], "geometry": [zone]}, crs=crs)

    nodes = gpd.GeoDataFrame(
        {
            "node_id": [10, 11, 12],
            "is_centroid": [0, 0, 0],
            "modes": ["ch", "ch", "ch"],
            "geometry": [Point(50, 500), Point(500, 500), Point(950, 500)],
        },
        crs=crs,
    )
    links = gpd.GeoDataFrame(
        {
            "a_node": [10, 12],
            "b_node": [99, 99],
            "link_type": ["local", "local"],
            "capacity_ab": [1000, 1000],
            "capacity_ba": [1000, 1000],
            "geometry": [LineString([(50, 500), (0, 500)]), LineString([(950, 500), (1000, 500)])],
        },
        crs=crs,
    )

    config = SpreadConnectorConfig(
        min_spacing_m=200.0,
        relaxed_spacing_m=100.0,
        min_connectors=2,
        max_connectors=2,
        perimeter_m_per_connector=2000.0,
        projected_crs=crs,
    )
    pairs = select_spread_connector_pairs(zones, nodes, links, modes=["c", "h"], config=config)

    assert set(pairs["b_node"].tolist()) == {10, 12}
