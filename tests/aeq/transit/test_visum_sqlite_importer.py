import sqlite3
from pathlib import Path

import pytest

from aequilibrae.transit.visum_sqlite_importer import VisumSQLiteTransitImporter, discover_visum_sqlite_transit


def _create_visum_transit_sqlite(path: Path, *, omit_table: str | None = None) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE STOP(NO INTEGER PRIMARY KEY, CODE TEXT, NAME TEXT, XCOORD REAL, YCOORD REAL);
            CREATE TABLE STOPAREA(
                NO INTEGER PRIMARY KEY,
                STOPNO INTEGER,
                CODE TEXT,
                NAME TEXT,
                NODENO INTEGER,
                XCOORD REAL,
                YCOORD REAL
            );
            CREATE TABLE STOPPOINT(
                NO INTEGER PRIMARY KEY,
                STOPAREANO INTEGER,
                CODE TEXT,
                NAME TEXT,
                TSYSSET TEXT,
                NODENO INTEGER,
                FROMNODENO INTEGER,
                LINKNO INTEGER,
                RELPOS REAL
            );
            CREATE TABLE LINE(NAME TEXT PRIMARY KEY, TSYSCODE TEXT, OPERATORNO INTEGER);
            CREATE TABLE LINEROUTE(
                LINENAME TEXT,
                NAME TEXT,
                DIRECTIONCODE TEXT,
                ISCIRCLELINE INTEGER
            );
            CREATE TABLE LINEROUTEITEM(
                LINENAME TEXT,
                LINEROUTENAME TEXT,
                DIRECTIONCODE TEXT,
                "INDEX" INTEGER,
                ISROUTEPOINT INTEGER,
                NODENO INTEGER,
                STOPPOINTNO INTEGER,
                POSTLENGTH REAL
            );
            CREATE TABLE TIMEPROFILE(
                LINENAME TEXT,
                LINEROUTENAME TEXT,
                DIRECTIONCODE TEXT,
                NAME TEXT,
                VEHCOMBNO INTEGER,
                "HEADWAY(AP)" TEXT,
                REFITEMINDEX INTEGER
            );
            CREATE TABLE TIMEPROFILEITEM(
                LINENAME TEXT,
                LINEROUTENAME TEXT,
                DIRECTIONCODE TEXT,
                TIMEPROFILENAME TEXT,
                "INDEX" INTEGER,
                LRITEMINDEX INTEGER,
                ALIGHT INTEGER,
                BOARD INTEGER,
                ARR TEXT,
                DEP TEXT
            );
            CREATE TABLE VEHJOURNEY(
                NO INTEGER PRIMARY KEY,
                NAME TEXT,
                DEP TEXT,
                LINENAME TEXT,
                LINEROUTENAME TEXT,
                DIRECTIONCODE TEXT,
                TIMEPROFILENAME TEXT,
                FROMTPROFITEMINDEX INTEGER,
                TOTPROFITEMINDEX INTEGER,
                OPERATORNO INTEGER
            );
            CREATE TABLE VEHJOURNEYSECTION(
                VEHJOURNEYNO INTEGER,
                NO INTEGER,
                FROMTPROFITEMINDEX INTEGER,
                TOTPROFITEMINDEX INTEGER,
                VALIDDAYSNO INTEGER
            );
            CREATE TABLE TSYS(CODE TEXT PRIMARY KEY, NAME TEXT, TYPE TEXT);
            CREATE TABLE OPERATOR(NO INTEGER PRIMARY KEY, NAME TEXT);
            CREATE TABLE FARESYSTEM(NO INTEGER PRIMARY KEY, NAME TEXT);
            CREATE TABLE TRANSFERWALKTIMESTOPAREA(
                FROMSTOPAREANO INTEGER,
                TOSTOPAREANO INTEGER,
                TSYSCODE TEXT,
                TIME REAL
            );
            """
        )
        conn.executemany(
            "INSERT INTO STOP VALUES(?, ?, ?, ?, ?)",
            [(1, "S1", "Stop 1", 0.0, 0.0), (2, "S2", "Stop 2", 0.01, 0.0)],
        )
        conn.executemany(
            "INSERT INTO STOPAREA VALUES(?, ?, ?, ?, ?, ?, ?)",
            [(10, 1, "SA1", "Area 1", 10, 0.0, 0.0), (20, 2, "SA2", "Area 2", 20, 0.01, 0.0)],
        )
        conn.executemany(
            "INSERT INTO STOPPOINT VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (100, 10, "SP1", "Point 1", "BUS", 10, None, None, None),
                (200, 20, "SP2", "Point 2", "BUS", None, 10, 1000, 0.5),
            ],
        )
        conn.executemany("INSERT INTO TSYS VALUES(?, ?, ?)", [("BUS", "Bus", "PuT"), ("CAR", "Car", "PrT")])
        conn.execute("INSERT INTO OPERATOR VALUES(1, 'Transit Operator')")
        conn.execute("INSERT INTO LINE VALUES('B1', 'BUS', 1)")
        conn.execute("INSERT INTO LINEROUTE VALUES('B1', 'outbound', '>', 0)")
        conn.executemany(
            "INSERT INTO LINEROUTEITEM VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("B1", "outbound", ">", 1, 1, 10, 100, 0.0),
                ("B1", "outbound", ">", 2, 0, 15, None, 0.0),
                ("B1", "outbound", ">", 3, 1, 20, 200, 0.0),
            ],
        )
        conn.execute("INSERT INTO TIMEPROFILE VALUES('B1', 'outbound', '>', 'weekday', NULL, NULL, 1)")
        conn.executemany(
            "INSERT INTO TIMEPROFILEITEM VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("B1", "outbound", ">", "weekday", 1, 1, 0, 1, "00:00:00", "00:00:00"),
                ("B1", "outbound", ">", "weekday", 2, 3, 1, 0, "00:05:00", "00:05:00"),
            ],
        )
        conn.executemany(
            "INSERT INTO VEHJOURNEY VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "B1-1", "23:58:00", "B1", "outbound", ">", "weekday", 1, 2, 1),
                (2, "B1-2", "08:00:00", "B1", "outbound", ">", "weekday", 2, 2, 1),
            ],
        )
        conn.executemany("INSERT INTO VEHJOURNEYSECTION VALUES(?, ?, ?, ?, ?)", [(1, 1, 1, 2, 1), (2, 1, 2, 2, 1)])
        conn.execute("INSERT INTO FARESYSTEM VALUES(1, 'Fare system')")
        conn.execute("INSERT INTO TRANSFERWALKTIMESTOPAREA VALUES(10, 20, 'BUS', 120.0)")
        if omit_table is not None:
            conn.execute(f'DROP TABLE "{omit_table}"')
        conn.commit()
    finally:
        conn.close()
    return path


def _add_visum_reference_network(project):
    with project.db_connection_spatial as conn:
        conn.execute("ALTER TABLE nodes ADD COLUMN visum_node_no INTEGER")
        conn.execute("ALTER TABLE nodes ADD COLUMN visum_zone_no INTEGER")
        conn.execute("ALTER TABLE links ADD COLUMN visum_link_no INTEGER")
        conn.execute("ALTER TABLE zones ADD COLUMN visum_zone_no INTEGER")
        conn.executemany(
            """
            INSERT INTO nodes (node_id, is_centroid, modes, visum_node_no, geometry)
            VALUES (?, 0, 't', ?, GeomFromText(?, 4326))
            """,
            [(10, 10, "POINT(0 0)"), (15, 15, "POINT(0.005 0)"), (20, 20, "POINT(0.01 0)")],
        )
        conn.execute(
            """
            INSERT INTO zones (zone_id, area, name, visum_zone_no, geometry)
            VALUES (
                1,
                0,
                'Z1',
                1,
                GeomFromText('MULTIPOLYGON(((0 0, 0.001 0, 0.001 0.001, 0 0.001, 0 0)))', 4326)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO links
                (link_id, a_node, b_node, direction, distance, modes, link_type, visum_link_no, geometry)
            VALUES
                (1, 10, 15, 0, 0.5, 't', 'default', 1000, GeomFromText('LINESTRING(0 0, 0.005 0)', 4326))
            """
        )
        conn.execute(
            """
            INSERT INTO links
                (link_id, a_node, b_node, direction, distance, modes, link_type, visum_link_no, geometry)
            VALUES
                (2, 15, 20, 0, 0.5, 't', 'default', 1001, GeomFromText('LINESTRING(0.005 0, 0.01 0)', 4326))
            """
        )


@pytest.fixture
def visum_transit_sqlite_file(tmp_path):
    return _create_visum_transit_sqlite(tmp_path / "visum-transit.sqlite3")


def test_discover_visum_sqlite_transit_reports_required_and_deferred_tables(visum_transit_sqlite_file):
    report = discover_visum_sqlite_transit(visum_transit_sqlite_file)

    assert not report.errors
    assert report.source_table_counts["STOPPOINT"] == 2
    assert report.source_table_counts["VEHJOURNEY"] == 2
    assert report.deferred_features == {"FARESYSTEM": 1, "TRANSFERWALKTIMESTOPAREA": 1}
    assert {diag.code for diag in report.warnings} == {"deferred-table"}


def test_discover_visum_sqlite_transit_rejects_missing_required_table(tmp_path):
    path = _create_visum_transit_sqlite(tmp_path / "visum-transit.sqlite3", omit_table="STOPPOINT")

    report = discover_visum_sqlite_transit(path)

    assert {diag.code for diag in report.errors} == {"missing-table"}
    assert {diag.layer for diag in report.errors} == {"STOPPOINT"}


def test_import_from_visum_sqlite_validates_source_reference_coverage(empty_project, visum_transit_sqlite_file):
    _add_visum_reference_network(empty_project)

    report = empty_project.transit.import_from_visum_sqlite(visum_transit_sqlite_file)

    assert not report.errors
    assert report.mapping_coverage["linerouteitem_nodes"] == {"total": 3, "matched": 3, "missing": 0}
    assert report.mapping_coverage["stoppoints"] == {"total": 2, "matched": 2, "missing": 0}
    assert report.mapping_coverage["existing_transit_rows"]["stops"] == 0
    assert report.inserted_counts == {
        "agencies": 1,
        "stops": 2,
        "routes": 1,
        "route_links": 1,
        "pattern_mapping": 2,
    }
    assert any(diag.code == "service-import-partial" for diag in report.warnings)

    with empty_project.transit_connection as conn:
        assert conn.execute("SELECT agency_id, agency FROM agencies").fetchall() == [(1, "Transit Operator")]
        stops = conn.execute(
            "SELECT stop_id, stop, agency_id, link, name, parent_station, route_type FROM stops"
        ).fetchall()

    assert stops == [
        ("100", "SP1", 1, None, "Point 1", "10", 3),
        ("200", "SP2", 1, 1, "Point 2", "20", 3),
    ]

    with empty_project.transit_connection as conn:
        routes = conn.execute(
            "SELECT pattern_id, route_id, route, agency_id, shortname, route_type, pce FROM routes"
        ).fetchall()
        route_links = conn.execute(
            "SELECT transit_link, pattern_id, seq, from_stop, to_stop FROM route_links"
        ).fetchall()
        pattern_mapping = conn.execute(
            "SELECT pattern_id, seq, link, dir FROM pattern_mapping ORDER BY seq"
        ).fetchall()

    assert routes == [(1, 1, "B1", 1, "B1", 3, 4)]
    assert route_links == [(1, 1, 0, 100, 200)]
    assert pattern_mapping == [(1, 0, 1, 1), (1, 1, 2, 1)]


def test_import_from_visum_sqlite_rejects_project_without_source_reference_columns(
    empty_project,
    visum_transit_sqlite_file,
):
    with pytest.raises(ValueError, match="missing-network-source-column"):
        empty_project.transit.import_from_visum_sqlite(visum_transit_sqlite_file)


def test_import_from_visum_sqlite_requires_overwrite_for_existing_service_data(
    empty_project,
    visum_transit_sqlite_file,
):
    _add_visum_reference_network(empty_project)
    with empty_project.transit_connection as conn:
        conn.execute("INSERT INTO agencies (agency_id, agency) VALUES (1, 'Existing')")

    with pytest.raises(ValueError, match="transit-data-exists"):
        empty_project.transit.import_from_visum_sqlite(visum_transit_sqlite_file)

    report = empty_project.transit.import_from_visum_sqlite(visum_transit_sqlite_file, overwrite=True)

    assert not report.errors
    assert report.mapping_coverage["existing_transit_rows"]["agencies"] == 1
    assert report.mapping_coverage["cleared_transit_rows"]["agencies"] == 1
    assert report.inserted_counts == {
        "agencies": 1,
        "stops": 2,
        "routes": 1,
        "route_links": 1,
        "pattern_mapping": 2,
    }

    with empty_project.transit_connection as conn:
        assert conn.execute("SELECT agency_id, agency FROM agencies").fetchall() == [(1, "Transit Operator")]
        assert conn.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 2


def test_import_from_visum_sqlite_rolls_back_failed_transit_writes(
    empty_project,
    visum_transit_sqlite_file,
    monkeypatch,
):
    _add_visum_reference_network(empty_project)
    with empty_project.transit_connection as conn:
        conn.execute("INSERT INTO agencies (agency_id, agency) VALUES (1, 'Existing')")

    def fail_insert_stops(*_args, **_kwargs):
        raise RuntimeError("forced stop failure")

    monkeypatch.setattr(VisumSQLiteTransitImporter, "_insert_stops", fail_insert_stops)

    with pytest.raises(RuntimeError, match="forced stop failure"):
        empty_project.transit.import_from_visum_sqlite(visum_transit_sqlite_file, overwrite=True)

    with empty_project.transit_connection as conn:
        assert conn.execute("SELECT agency_id, agency FROM agencies").fetchall() == [(1, "Existing")]
        assert conn.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 0


def test_import_from_visum_sqlite_overwrite_invalidates_saved_transit_graph_configs(
    empty_project,
    visum_transit_sqlite_file,
):
    _add_visum_reference_network(empty_project)
    with empty_project.db_connection as conn:
        conn.execute("INSERT INTO transit_graph_configs (period_id, config) VALUES (1, '{}')")

    report = empty_project.transit.import_from_visum_sqlite(visum_transit_sqlite_file, overwrite=True)

    assert report.mapping_coverage["removed_transit_graph_configs"] == {"total": 1, "matched": 1, "missing": 0}
    with empty_project.db_connection as conn:
        assert conn.execute("SELECT COUNT(*) FROM transit_graph_configs").fetchone()[0] == 0
