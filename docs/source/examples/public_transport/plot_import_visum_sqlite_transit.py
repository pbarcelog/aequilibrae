"""
.. _example_visum_sqlite_transit:

Import public transport from VISUM SQLite
=========================================

This example creates a tiny VISUM-like SQLite export with a traffic network and
public transport service data, then imports both into an AequilibraE project.
"""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from aequilibrae import Project


def create_visum_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE NETWORK(PROJECTIONDEFINITION TEXT);
            CREATE TABLE NODE(NO INTEGER PRIMARY KEY, NAME TEXT, TYPENO INTEGER, XCOORD REAL, YCOORD REAL);
            CREATE TABLE ZONE(NO INTEGER PRIMARY KEY, NAME TEXT, TYPENO INTEGER, XCOORD REAL, YCOORD REAL);
            CREATE TABLE TSYS(CODE TEXT PRIMARY KEY, NAME TEXT, TYPE TEXT, PCU REAL);
            CREATE TABLE MODE(CODE TEXT PRIMARY KEY, NAME TEXT, TSYSSET TEXT);
            CREATE TABLE LINKTYPE(NO INTEGER PRIMARY KEY, NAME TEXT, TSYSSET TEXT, CAPPRT INTEGER, V0PRT REAL);
            CREATE TABLE LINK(
                NO INTEGER,
                FROMNODENO INTEGER,
                TONODENO INTEGER,
                NAME TEXT,
                TYPENO INTEGER,
                TSYSSET TEXT,
                LENGTH REAL,
                CAPPRT INTEGER,
                V0PRT REAL,
                LC TEXT
            );
            CREATE TABLE CONNECTOR(
                ZONENO INTEGER,
                NODENO INTEGER,
                DIRECTION TEXT,
                TYPENO INTEGER,
                TSYSSET TEXT,
                LENGTH REAL,
                "T0_TSYS(CAR)" REAL,
                "T0_TSYS(BUS)" REAL,
                WEIGHTPRT REAL
            );
            CREATE TABLE COUNTLOCATION(NO INTEGER PRIMARY KEY, LINKNO INTEGER, FROMNODENO INTEGER, TONODENO INTEGER);
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
            CREATE TABLE LINEROUTE(LINENAME TEXT, NAME TEXT, DIRECTIONCODE TEXT, ISCIRCLELINE INTEGER);
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
            CREATE TABLE OPERATOR(NO INTEGER PRIMARY KEY, NAME TEXT);
            """
        )
        conn.execute("INSERT INTO NETWORK VALUES('EPSG:4326')")
        conn.executemany(
            "INSERT INTO TSYS VALUES(?, ?, ?, ?)",
            [("CAR", "Car", "PrT", 1.0), ("BUS", "Bus", "PuT", 4.0)],
        )
        conn.execute("INSERT INTO MODE VALUES('C', 'Car', 'CAR')")
        conn.execute("INSERT INTO LINKTYPE VALUES(1, 'arterial', 'CAR,BUS', 1200, 60)")
        conn.executemany(
            "INSERT INTO NODE VALUES(?, ?, ?, ?, ?)",
            [(1, "A", 1, 0.0, 0.0), (2, "B", 1, 0.01, 0.0)],
        )
        conn.executemany(
            "INSERT INTO ZONE VALUES(?, ?, ?, ?, ?)",
            [(1001, "Z1", 1, -0.01, 0.0), (1002, "Z2", 1, 0.02, 0.0)],
        )
        conn.execute("INSERT INTO LINK VALUES(100, 1, 2, 'AB', 1, 'CAR,BUS', 1.0, 1200, 60, 'ARTERIAL')")
        conn.executemany(
            'INSERT INTO CONNECTOR VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [
                (1001, 1, "O", 1, "CAR", 0.1, 1.0, None, 100),
                (1001, 1, "D", 1, "CAR", 0.1, 1.0, None, 100),
                (1002, 2, "O", 1, "CAR", 0.1, 1.0, None, 100),
                (1002, 2, "D", 1, "CAR", 0.1, 1.0, None, 100),
            ],
        )
        conn.execute("INSERT INTO COUNTLOCATION VALUES(1, 100, 1, 2)")
        conn.executemany(
            "INSERT INTO STOP VALUES(?, ?, ?, ?, ?)",
            [(10, "A", "Stop A", 0.0, 0.0), (20, "B", "Stop B", 0.01, 0.0)],
        )
        conn.executemany(
            "INSERT INTO STOPAREA VALUES(?, ?, ?, ?, ?, ?, ?)",
            [(10, 10, "SA", "Area A", 1, 0.0, 0.0), (20, 20, "SB", "Area B", 2, 0.01, 0.0)],
        )
        conn.executemany(
            "INSERT INTO STOPPOINT VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (100, 10, "A", "Point A", "BUS", 1, None, None, None),
                (200, 20, "B", "Point B", "BUS", 2, None, None, None),
            ],
        )
        conn.execute("INSERT INTO OPERATOR VALUES(1, 'Example Transit')")
        conn.execute("INSERT INTO LINE VALUES('B1', 'BUS', 1)")
        conn.execute("INSERT INTO LINEROUTE VALUES('B1', 'outbound', '>', 0)")
        conn.executemany(
            "INSERT INTO LINEROUTEITEM VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            [("B1", "outbound", ">", 1, 1, 1, 100, 0.0), ("B1", "outbound", ">", 2, 1, 2, 200, 0.0)],
        )
        conn.execute("INSERT INTO TIMEPROFILE VALUES('B1', 'outbound', '>', 'weekday', NULL, NULL, 1)")
        conn.executemany(
            "INSERT INTO TIMEPROFILEITEM VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("B1", "outbound", ">", "weekday", 1, 1, 0, 1, "00:00:00", "00:00:00"),
                ("B1", "outbound", ">", "weekday", 2, 2, 1, 0, "00:05:00", "00:05:00"),
            ],
        )
        conn.execute("INSERT INTO VEHJOURNEY VALUES(1, 'B1-1', '08:00:00', 'B1', 'outbound', '>', 'weekday', 1, 2, 1)")
        conn.execute("INSERT INTO VEHJOURNEYSECTION VALUES(1, 1, 1, 2, 1)")
        conn.commit()
    finally:
        conn.close()


with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
    temp_dir = Path(temp_dir)
    sqlite_path = temp_dir / "visum-transit.sqlite"
    create_visum_sqlite(sqlite_path)

    project = Project()
    project.new(temp_dir / "visum_project")

    network_report = project.network.create_from_visum_sqlite(sqlite_path, mode_mapping={"CAR": "c", "BUS": "t"})
    transit_report = project.transit.import_from_visum_sqlite(sqlite_path)

    period = project.network.periods.new_period(2, 7 * 3600, 9 * 3600, "Morning service")
    period.save()
    graph = project.transit.create_graph(
        period_id=2,
        with_inner_stop_transfers=False,
        with_outer_stop_transfers=False,
        with_walking_edges=False,
    )
    preload = project.transit.build_pt_preload(7 * 3600, 9 * 3600)

    print(network_report.imported_counts)
    print(transit_report.inserted_counts)
    print(len(graph.vertices), len(graph.edges))
    print(preload.to_dict("records"))

    project.close()
