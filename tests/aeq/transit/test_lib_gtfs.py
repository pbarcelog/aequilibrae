import pytest
import geopandas as gpd
from shapely.geometry import LineString, Point
from types import SimpleNamespace

from aequilibrae.project.database_connection import database_connection
from aequilibrae.transit.lib_gtfs import GTFSRouteSystemBuilder


@pytest.fixture(scope="function")
def route_system_builder(build_gtfs_project):
    gtfs_file = build_gtfs_project.project.project_base_path / "gtfs_coquimbo.zip"
    with database_connection("transit") as transit_conn:
        yield GTFSRouteSystemBuilder(
            network=transit_conn, agency_identifier="LISERCO, LISANCO, LINCOSUR", file_path=gtfs_file
        )


def test_set_capacities(route_system_builder):
    route_system_builder.set_capacities({0: [150, 300], 3: [42, 56]})
    assert route_system_builder.gtfs_data.__dict__["__capacities__"] == {0: [150, 300], 3: [42, 56]}


def test_set_pces(route_system_builder):
    route_system_builder.set_pces({1: 2.5, 3: 6.2})
    assert route_system_builder.gtfs_data.__dict__["__pces__"] == {1: 2.5, 3: 6.2}


def test_dates_available(route_system_builder):
    dates = route_system_builder.dates_available()
    assert isinstance(dates, list)


def test_set_allow_map_match(route_system_builder):
    assert route_system_builder.__dict__["_GTFSRouteSystemBuilder__do_execute_map_matching"] is False
    route_system_builder.set_allow_map_match(True)
    assert route_system_builder.__dict__["_GTFSRouteSystemBuilder__do_execute_map_matching"] is True


def test_map_match_tuple_exception(route_system_builder):
    with pytest.raises(TypeError):
        route_system_builder.map_match(route_types=3)


def test_map_match_int_exception(route_system_builder):
    with pytest.raises(TypeError):
        route_system_builder.map_match(route_types=[3.5])


def test_map_match(route_system_builder, caplog):
    route_system_builder.load_date("2016-04-13")
    route_system_builder.set_allow_map_match(True)
    route_system_builder.map_match([3, 1, 2])
    route_system_builder.save_to_disk()

    assert "Skipping the following route_types as they have no corresponding road mode: [1]" in caplog.text

    with database_connection("transit") as transit_conn:
        assert transit_conn.execute("SELECT * FROM pattern_mapping;").fetchone()[0] > 1


def test_builds_map_matchers_uses_gtfs_route_type_modal_subgraphs(monkeypatch):
    class FakeRouteMapMatcher:
        def __init__(self, link_gdf, nodes_gdf, stops_gdf):
            self.link_modes = set(link_gdf.modes)
            self.stop_ids = set(stops_gdf.stop_id)
            self.node_ids = set(nodes_gdf.node_id)
            self.initialized = False

        def initialize_graph(self):
            self.initialized = True

    monkeypatch.setattr("aequilibrae.transit.lib_gtfs.RouteMapMatcher", FakeRouteMapMatcher)

    builder = object.__new__(GTFSRouteSystemBuilder)
    links = gpd.GeoDataFrame(
        [
            {"link_id": 1, "a_node": 1, "b_node": 2, "modes": "l", "geometry": LineString([(0.0, 0.0), (0.01, 0.0)])},
            {"link_id": 2, "a_node": 3, "b_node": 4, "modes": "r", "geometry": LineString([(0.0, 0.01), (0.01, 0.01)])},
            {"link_id": 3, "a_node": 5, "b_node": 6, "modes": "t", "geometry": LineString([(0.0, 0.02), (0.01, 0.02)])},
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    nodes = gpd.GeoDataFrame(
        [
            {"node_id": 1, "geometry": Point(0.0, 0.0)},
            {"node_id": 2, "geometry": Point(0.01, 0.0)},
            {"node_id": 3, "geometry": Point(0.0, 0.01)},
            {"node_id": 4, "geometry": Point(0.01, 0.01)},
            {"node_id": 5, "geometry": Point(0.0, 0.02)},
            {"node_id": 6, "geometry": Point(0.01, 0.02)},
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    builder.project = SimpleNamespace(
        network=SimpleNamespace(links=SimpleNamespace(data=links), nodes=SimpleNamespace(data=nodes))
    )
    builder.select_stops = {
        "tram": SimpleNamespace(stop_id="tram", route_type=0, geo=Point(0.005, 0.0)),
        "rail": SimpleNamespace(stop_id="rail", route_type=2, geo=Point(0.005, 0.01)),
        "bus": SimpleNamespace(stop_id="bus", route_type=3, geo=Point(0.005, 0.02)),
    }
    builder.map_matchers = {}
    builder.srid = 4326

    builder.builds_map_matchers()

    assert set(builder.map_matchers) == {"l", "r", "t"}
    assert builder.map_matchers["l"].link_modes == {"l"}
    assert builder.map_matchers["l"].stop_ids == {"tram"}
    assert builder.map_matchers["r"].link_modes == {"r"}
    assert builder.map_matchers["r"].stop_ids == {"rail"}
    assert builder.map_matchers["t"].link_modes == {"t"}
    assert builder.map_matchers["t"].stop_ids == {"bus"}
    assert all(matcher.initialized for matcher in builder.map_matchers.values())


def test_set_agency_identifier(route_system_builder):
    assert route_system_builder.gtfs_data.agency.agency != "CTA"
    route_system_builder.set_agency_identifier("CTA")
    assert route_system_builder.gtfs_data.agency.agency == "CTA"


def test_set_feed(route_system_builder):
    assert route_system_builder.gtfs_data.archive_dir.stem == "gtfs_coquimbo"


def test_set_description(route_system_builder):
    route_system_builder.set_description("CTA2019 fixed by John Doe after strong coffee")
    assert route_system_builder.description == "CTA2019 fixed by John Doe after strong coffee"


def test_set_date(route_system_builder):
    route_system_builder.set_date("2016-04-13")
    assert route_system_builder.__target_date__ == "2016-04-13"


def test_load_date(route_system_builder):
    route_system_builder.load_date("2016-04-13")
    assert route_system_builder.gtfs_data.agency.service_date == "2016-04-13"
    assert "101387" in route_system_builder.select_routes.keys()


def test_load_date_srid_exception(route_system_builder):
    route_system_builder.srid = None
    with pytest.raises(ValueError):
        route_system_builder.load_date("2016-04-13")


def test_load_date_not_available_date_exception(route_system_builder):
    with pytest.raises(ValueError):
        route_system_builder.load_date("2020-06-01")


def test_save_to_disk(route_system_builder):
    route_system_builder.load_date("2016-04-13")
    route_system_builder.save_to_disk()

    with database_connection("transit") as transit_conn:
        assert len(transit_conn.execute("SELECT * FROM route_links").fetchall()) == 78
        assert len(transit_conn.execute("SELECT * FROM trips;").fetchall()) == 360
        assert len(transit_conn.execute("SELECT * FROM routes;").fetchall()) == 2
