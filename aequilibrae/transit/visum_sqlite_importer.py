import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import shapely

from aequilibrae.project.network.visum_geojson_importer import VisumGeoJSONDiagnostic


REQUIRED_VISUM_TRANSIT_TABLES = {
    "STOP",
    "STOPAREA",
    "STOPPOINT",
    "LINE",
    "LINEROUTE",
    "LINEROUTEITEM",
    "TIMEPROFILE",
    "TIMEPROFILEITEM",
    "VEHJOURNEY",
    "VEHJOURNEYSECTION",
    "TSYS",
    "OPERATOR",
}
DEFERRED_VISUM_TRANSIT_TABLES = {
    "BLOCKITEMTYPE",
    "BLOCKVERSION",
    "DISTANCEFAREITEM",
    "FAREMODEL",
    "FARESUPPLEMENTITEM",
    "FARESYSTEM",
    "FAREZONE",
    "STOPTOFAREZONE",
    "TICKETTYPE",
    "TICKETTYPETODSEGFARESYSTEM",
    "TRANSFERWALKTIMESTOPAREA",
    "VEHCOMB",
    "VEHJOURNEYCOUPLESECTION",
    "VEHJOURNEYCOUPLESECTIONITEM",
    "VEHJOURNEYITEM",
    "VEHUNIT",
    "VEHUNITTOVEHCOMB",
    "ZONECOUNTFAREITEM",
}
REQUIRED_NETWORK_SOURCE_COLUMNS = {
    "nodes": {"visum_node_no", "visum_zone_no"},
    "links": {"visum_link_no"},
    "zones": {"visum_zone_no"},
}


@dataclass
class VisumSQLiteTransitReport:
    """Diagnostics and provenance returned by a VISUM SQLite transit import."""

    diagnostics: list[VisumGeoJSONDiagnostic] = field(default_factory=list)
    source_table_counts: dict[str, int] = field(default_factory=dict)
    inserted_counts: dict[str, int] = field(default_factory=dict)
    mapping_coverage: dict[str, dict[str, int]] = field(default_factory=dict)
    unmapped_records: dict[str, list[object]] = field(default_factory=dict)
    deferred_features: dict[str, int] = field(default_factory=dict)
    transit_system_mapping: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[VisumGeoJSONDiagnostic]:
        return [diag for diag in self.diagnostics if diag.severity == "error"]

    @property
    def warnings(self) -> list[VisumGeoJSONDiagnostic]:
        return [diag for diag in self.diagnostics if diag.severity == "warning"]

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        layer: str | None = None,
        field: str | None = None,
        source_id: object | None = None,
    ) -> None:
        self.diagnostics.append(VisumGeoJSONDiagnostic(severity, code, message, layer, field, source_id))

    def raise_for_errors(self) -> None:
        if self.errors:
            messages = "; ".join(f"{diag.code}: {diag.message}" for diag in self.errors[:5])
            raise ValueError(f"VISUM SQLite transit import failed validation: {messages}")


def discover_visum_sqlite_transit(path: str | Path) -> VisumSQLiteTransitReport:
    """Validate VISUM SQLite transit source tables and report source row counts."""

    report = VisumSQLiteTransitReport()
    db_path = Path(path)
    if not db_path.exists():
        report.add("error", "missing-input", f"VISUM SQLite path does not exist: {db_path}")
        return report
    if not db_path.is_file():
        report.add("error", "invalid-input", f"VISUM SQLite input must be a file: {db_path}")
        return report

    try:
        with sqlite3.connect(db_path) as conn:
            tables = _source_tables(conn)
            table_names = set(tables)
            for table in sorted(table_names & REQUIRED_VISUM_TRANSIT_TABLES):
                count_sql = f'SELECT COUNT(*) FROM "{tables[table]}"'
                report.source_table_counts[table] = conn.execute(count_sql).fetchone()[0]
            for table in sorted(table_names & DEFERRED_VISUM_TRANSIT_TABLES):
                count = conn.execute(f'SELECT COUNT(*) FROM "{tables[table]}"').fetchone()[0]
                if count:
                    report.deferred_features[table] = count
                    report.add(
                        "warning",
                        "deferred-table",
                        f"VISUM SQLite transit table '{table}' is recognized but deferred",
                        layer=table,
                    )
    except sqlite3.Error as exc:
        report.add("error", "invalid-sqlite", f"Could not read VISUM SQLite database: {exc}")
        return report

    for table in sorted(REQUIRED_VISUM_TRANSIT_TABLES - set(report.source_table_counts)):
        report.add("error", "missing-table", f"Required VISUM SQLite transit table '{table}' was not provided", table)
    return report


class VisumSQLiteTransitImporter:
    def __init__(
        self,
        project,
        path: str | Path,
        *,
        overwrite: bool = False,
        transit_system_mapping: Mapping[str, int] | None = None,
    ) -> None:
        self.project = project
        self.path = Path(path)
        self.overwrite = overwrite
        self.transit_system_mapping = {
            "BUS": 3,
            "TRAIN": 2,
            "TRAM": 0,
            **{str(k).upper(): int(v) for k, v in (transit_system_mapping or {}).items()},
        }
        self.report = VisumSQLiteTransitReport(transit_system_mapping=dict(self.transit_system_mapping))

    def doWork(self) -> VisumSQLiteTransitReport:
        discovery = discover_visum_sqlite_transit(self.path)
        self.report.source_table_counts.update(discovery.source_table_counts)
        self.report.deferred_features.update(discovery.deferred_features)
        self.report.diagnostics.extend(discovery.diagnostics)
        self.report.raise_for_errors()

        with sqlite3.connect(self.path) as source_conn, self.project.db_connection as project_conn:
            source_conn.row_factory = sqlite3.Row
            self._validate_network_source_columns(project_conn)
            self.report.raise_for_errors()
            self._validate_network_reference_coverage(source_conn, project_conn)
            self._validate_transit_system_mapping(source_conn)
            self.report.raise_for_errors()

        with self.project.transit_connection as transit_conn:
            self._validate_overwrite_policy(transit_conn)
            self.report.raise_for_errors()
            transit_conn.manual_transaction()
            with transit_conn:
                if self.overwrite:
                    self._clear_transit_tables(transit_conn)
                with sqlite3.connect(self.path) as source_conn, self.project.db_connection_spatial as project_conn:
                    source_conn.row_factory = sqlite3.Row
                    self._insert_agencies(source_conn, transit_conn)
                    self._insert_stops(source_conn, project_conn, transit_conn)

        self.report.add(
            "warning",
            "service-import-partial",
            "VISUM SQLite transit operators and stops were imported; route patterns and schedules are pending",
        )
        if self.overwrite:
            self._invalidate_saved_graphs()
        return self.report

    def _validate_network_source_columns(self, conn: sqlite3.Connection) -> None:
        for table, required_columns in REQUIRED_NETWORK_SOURCE_COLUMNS.items():
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
            for column in sorted(required_columns - columns):
                self.report.add(
                    "error",
                    "missing-network-source-column",
                    f"Project table '{table}' is missing required VISUM source-reference column '{column}'",
                    layer=table,
                    field=column,
                )

    def _validate_network_reference_coverage(
        self,
        source_conn: sqlite3.Connection,
        project_conn: sqlite3.Connection,
    ) -> None:
        project_nodes = _integer_set(
            project_conn.execute("SELECT visum_node_no FROM nodes WHERE visum_node_no IS NOT NULL")
        )
        project_links = _integer_set(
            project_conn.execute("SELECT visum_link_no FROM links WHERE visum_link_no IS NOT NULL")
        )

        route_nodes = [
            int(row[0])
            for row in source_conn.execute('SELECT NODENO FROM "LINEROUTEITEM" WHERE NODENO IS NOT NULL').fetchall()
        ]
        distinct_route_nodes = set(route_nodes)
        missing_route_nodes = sorted(distinct_route_nodes - project_nodes)
        self._add_coverage(
            "linerouteitem_nodes",
            len(distinct_route_nodes),
            len(distinct_route_nodes - set(missing_route_nodes)),
        )
        if missing_route_nodes:
            self.report.unmapped_records["linerouteitem_nodes"] = missing_route_nodes[:25]
            self.report.add(
                "error",
                "unmapped-line-route-nodes",
                "VISUM line-route node references are not covered by project nodes",
                layer="LINEROUTEITEM",
            )

        stop_rows = source_conn.execute('SELECT NO, NODENO, LINKNO FROM "STOPPOINT"').fetchall()
        missing_stop_points = []
        matched_stop_points = 0
        for stop_no, node_no, link_no in stop_rows:
            node_match = node_no is not None and int(node_no) in project_nodes
            link_match = link_no is not None and int(link_no) in project_links
            if node_match or link_match:
                matched_stop_points += 1
            else:
                missing_stop_points.append(int(stop_no))
        self._add_coverage("stoppoints", len(stop_rows), matched_stop_points)
        if missing_stop_points:
            self.report.unmapped_records["stoppoints"] = missing_stop_points[:25]
            self.report.add(
                "error",
                "unmapped-stop-points",
                "VISUM stop-point references are not covered by project nodes or links",
                layer="STOPPOINT",
            )

    def _validate_overwrite_policy(self, conn: sqlite3.Connection) -> None:
        service_tables = ["agencies", "stops", "routes", "route_links", "pattern_mapping", "trips", "trips_schedule"]
        existing = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in service_tables
            if _table_exists(conn, table)
        }
        if not self.overwrite and any(existing.values()):
            self.report.add(
                "error",
                "transit-data-exists",
                "VISUM SQLite transit import requires overwrite=True when transit service tables are not empty",
            )
        self.report.mapping_coverage["existing_transit_rows"] = existing

    def _validate_transit_system_mapping(self, conn: sqlite3.Connection) -> None:
        mapped_codes = set(self.transit_system_mapping)
        put_codes = {
            str(row["CODE"]).upper()
            for row in conn.execute('SELECT CODE FROM "TSYS" WHERE UPPER(TYPE)=?', ("PUT",)).fetchall()
        }
        for code in sorted(put_codes - mapped_codes):
            self.report.add(
                "warning",
                "unmapped-transit-system",
                f"VISUM transit system '{code}' has no route-type mapping and will use route_type=-1 where needed",
                layer="TSYS",
                source_id=code,
            )

    def _clear_transit_tables(self, conn: sqlite3.Connection) -> None:
        tables = [
            "links",
            "nodes",
            "stop_connectors",
            "zones",
            "trips_schedule",
            "trips",
            "pattern_mapping",
            "route_links",
            "routes",
            "stops",
            "fare_rules",
            "fare_attributes",
            "fare_zones",
            "agencies",
        ]
        cleared = {}
        for table in tables:
            if not _table_exists(conn, table):
                continue
            cleared[table] = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            conn.execute(f'DELETE FROM "{table}"')
        self.report.mapping_coverage["cleared_transit_rows"] = cleared

    def _insert_agencies(self, source_conn: sqlite3.Connection, transit_conn: sqlite3.Connection) -> None:
        rows = source_conn.execute('SELECT NO, NAME FROM "OPERATOR" ORDER BY NO').fetchall()
        transit_conn.executemany(
            """
            INSERT INTO agencies (agency_id, agency, description)
            VALUES (?, ?, ?)
            """,
            [
                (
                    int(row["NO"]),
                    _clean_text(row["NAME"], f"VISUM operator {row['NO']}"),
                    "Imported from VISUM OPERATOR",
                )
                for row in rows
            ],
        )
        self.report.inserted_counts["agencies"] = len(rows)

    def _insert_stops(
        self,
        source_conn: sqlite3.Connection,
        project_conn: sqlite3.Connection,
        transit_conn: sqlite3.Connection,
    ) -> None:
        default_agency_id = self._default_agency_id(source_conn)
        node_geometries = _project_node_geometries(project_conn)
        link_geometries = _project_link_geometries(project_conn)
        link_ids = _project_link_ids(project_conn)
        fare_zones = _stop_fare_zones(source_conn)
        rows = source_conn.execute(
            """
            SELECT
                sp.NO stop_point_no,
                sp.CODE stop_point_code,
                sp.NAME stop_point_name,
                sp.TSYSSET stop_point_tsysset,
                sp.NODENO stop_point_node_no,
                sp.LINKNO stop_point_link_no,
                sp.RELPOS stop_point_relpos,
                sa.NO stop_area_no,
                sa.STOPNO stop_no,
                sa.CODE stop_area_code,
                sa.NAME stop_area_name,
                sa.NODENO stop_area_node_no,
                s.CODE stop_code,
                s.NAME stop_name
            FROM "STOPPOINT" sp
            LEFT JOIN "STOPAREA" sa ON sp.STOPAREANO = sa.NO
            LEFT JOIN "STOP" s ON sa.STOPNO = s.NO
            ORDER BY sp.NO
            """
        ).fetchall()
        data = []
        for row in rows:
            link_id = _link_id_for_stop_point(row, link_ids)
            geometry = _geometry_for_stop_point(row, node_geometries, link_geometries)
            route_type = self._route_type(row["stop_point_tsysset"])
            stop_code = _clean_text(
                row["stop_point_code"],
                _clean_text(row["stop_area_code"], _clean_text(row["stop_code"], str(row["stop_point_no"]))),
            )
            stop_name = _clean_text(
                row["stop_point_name"],
                _clean_text(row["stop_area_name"], _clean_text(row["stop_name"], stop_code)),
            )
            data.append(
                (
                    str(row["stop_point_no"]),
                    stop_code,
                    default_agency_id,
                    link_id,
                    None,
                    stop_name,
                    None if row["stop_area_no"] is None else str(row["stop_area_no"]),
                    f"VISUM STOP={row['stop_no']} STOPAREA={row['stop_area_no']}",
                    None,
                    None,
                    fare_zones.get(row["stop_no"]),
                    route_type,
                    geometry.wkb,
                    4326,
                )
            )

        transit_conn.executemany(
            """
            INSERT INTO stops (
                stop_id,
                stop,
                agency_id,
                link,
                dir,
                name,
                parent_station,
                description,
                street,
                zone_id,
                transit_fare_zone,
                route_type,
                geometry
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GeomFromWKB(?, ?))
            """,
            data,
        )
        self.report.inserted_counts["stops"] = len(data)

    def _default_agency_id(self, conn: sqlite3.Connection) -> int:
        row = conn.execute('SELECT NO FROM "OPERATOR" ORDER BY NO LIMIT 1').fetchone()
        return int(row["NO"]) if row is not None else 1

    def _route_type(self, tsysset) -> int:
        route_types = []
        for token in _split_tsysset(tsysset):
            mapped = self.transit_system_mapping.get(token)
            if mapped is not None:
                route_types.append(mapped)
        return min(route_types) if route_types else -1

    def _invalidate_saved_graphs(self) -> None:
        with self.project.db_connection as conn:
            if _table_exists(conn, "transit_graph_configs"):
                removed = conn.execute("SELECT COUNT(*) FROM transit_graph_configs").fetchone()[0]
                conn.execute("DELETE FROM transit_graph_configs")
                self.report.mapping_coverage["removed_transit_graph_configs"] = {
                    "total": removed,
                    "matched": removed,
                    "missing": 0,
                }

    def _add_coverage(self, name: str, total: int, matched: int) -> None:
        self.report.mapping_coverage[name] = {"total": total, "matched": matched, "missing": total - matched}


def _source_tables(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row[0].upper(): row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND UPPER(name)=?",
        (table.upper(),),
    ).fetchone() is not None


def _integer_set(rows) -> set[int]:
    return {int(row[0]) for row in rows if row[0] is not None}


def _clean_text(value, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _split_tsysset(value) -> list[str]:
    if value is None:
        return []
    return [token.strip().upper() for token in str(value).split(",") if token.strip()]


def _project_node_geometries(conn: sqlite3.Connection) -> dict[int, object]:
    rows = conn.execute(
        "SELECT visum_node_no, AsBinary(geometry) FROM nodes WHERE visum_node_no IS NOT NULL"
    ).fetchall()
    return {int(row[0]): shapely.from_wkb(row[1]) for row in rows if row[1] is not None}


def _project_link_geometries(conn: sqlite3.Connection) -> dict[int, object]:
    rows = conn.execute(
        "SELECT visum_link_no, AsBinary(geometry) FROM links WHERE visum_link_no IS NOT NULL"
    ).fetchall()
    return {int(row[0]): shapely.from_wkb(row[1]) for row in rows if row[1] is not None}


def _project_link_ids(conn: sqlite3.Connection) -> dict[int, int]:
    rows = conn.execute("SELECT visum_link_no, link_id FROM links WHERE visum_link_no IS NOT NULL").fetchall()
    return {int(row[0]): int(row[1]) for row in rows if row[0] is not None}


def _stop_fare_zones(conn: sqlite3.Connection) -> dict[int, str]:
    if not _table_exists(conn, "STOPTOFAREZONE"):
        return {}
    rows = conn.execute('SELECT STOPNO, FAREZONENO FROM "STOPTOFAREZONE" ORDER BY STOPNO, FAREZONENO').fetchall()
    fare_zones: dict[int, list[str]] = {}
    for stop_no, fare_zone_no in rows:
        fare_zones.setdefault(int(stop_no), []).append(str(fare_zone_no))
    return {stop_no: ",".join(values) for stop_no, values in fare_zones.items()}


def _link_id_for_stop_point(row: sqlite3.Row, link_ids: Mapping[int, int]) -> int | None:
    link_no = row["stop_point_link_no"]
    if link_no is None:
        return None
    return link_ids.get(int(link_no))


def _geometry_for_stop_point(
    row: sqlite3.Row,
    node_geometries: Mapping[int, object],
    link_geometries: Mapping[int, object],
):
    node_no = row["stop_point_node_no"] if row["stop_point_node_no"] is not None else row["stop_area_node_no"]
    if node_no is not None and int(node_no) in node_geometries:
        return node_geometries[int(node_no)]

    link_no = row["stop_point_link_no"]
    if link_no is not None and int(link_no) in link_geometries:
        relpos = 0.5 if row["stop_point_relpos"] is None else float(row["stop_point_relpos"])
        relpos = max(0.0, min(1.0, relpos))
        return link_geometries[int(link_no)].interpolate(relpos, normalized=True)

    raise ValueError(f"Could not derive geometry for VISUM STOPPOINT {row['stop_point_no']}")
