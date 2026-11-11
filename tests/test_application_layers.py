"""Application layer regression tests: lineage, isolation and generic imports."""
import sqlite3

from flask import Blueprint, Flask

from application_layers import install
from sap_links_import import normalise


def test_generic_relationship_format():
    doc = {
        "format": "querybridge-links", "format_version": 1, "application": "Procure",
        "tables": [{"name": "requests", "fields": ["id"]},
                   {"name": "lines", "fields": ["request_id"]}],
        "links": [{"left": {"table": "requests", "field": "id"},
                   "right": {"table": "lines", "field": "request_id"}}],
    }
    application, definitions, links = normalise(doc)
    assert application == "Procure"
    assert len(definitions) == 2
    assert len(links) == 1


def test_layers_preserve_source_tables_and_connect_lineage(tmp_path):
    database = str(tmp_path / "querybridge.sqlite")
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE qb_tables (
            id INTEGER PRIMARY KEY, table_name TEXT, application_name TEXT
        );
        CREATE TABLE qb_columns (
            id INTEGER PRIMARY KEY, table_id INTEGER REFERENCES qb_tables(id),
            column_name TEXT
        );
        CREATE TABLE qb_admin_audit (
            action TEXT, entity_type TEXT, entity_id INTEGER,
            before_json TEXT, after_json TEXT, created_at TEXT
        );
        INSERT INTO qb_tables VALUES (1,'EKKO','SAP S/4HANA');
        INSERT INTO qb_columns VALUES (1,1,'EBELN');
        INSERT INTO qb_columns VALUES (2,1,'BUKRS');
    """)
    connection.commit()
    connection.close()

    def db():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    app = Flask(__name__)
    bp = Blueprint("admin", __name__, url_prefix="/admin")
    install(bp, db, lambda: "2026-11-11T00:00:00Z")
    app.register_blueprint(bp)
    client = app.test_client()

    def post(path, payload):
        response = client.post("/admin/api/layers/" + path, json=payload)
        assert response.status_code in (200, 201), response.get_json()
        return response.get_json()["id"] if "id" in response.get_json() else None

    db_obj = post("objects", {"kind": "databricks", "application_name": "TAIJU",
                               "object_name": "sap_po_view"})
    app_obj = post("objects", {"kind": "application", "application_name": "TAIJU",
                                "object_name": "dppp"})
    db_field = post("fields", {"object_id": db_obj, "field_name": "po_number"})
    app_field = post("fields", {"object_id": app_obj, "field_name": "po_number"})
    post("lineage", {"target_field_id": db_field, "source_column_id": 1})
    post("lineage", {"target_field_id": app_field, "upstream_field_id": db_field})

    invalid = client.post("/admin/api/layers/lineage",
                          json={"target_field_id": app_field, "source_column_id": 2})
    assert invalid.status_code == 400
    assert client.get("/admin/api/layers").get_json()["lineage"][1]["upstream_field"] == "po_number"

    raw = db()
    assert raw.execute("SELECT COUNT(*) FROM qb_columns").fetchone()[0] == 2
    raw.close()

    response = client.post("/admin/api/layers/import?preview=1", json={
        "format": "querybridge-application-layer", "version": 1,
        "objects": [{"kind": "application", "application_name": "TAIJU",
                     "object_name": "dppp", "fields": ["po_number", "vendor"]}]
    })
    assert response.status_code == 200
    assert response.get_json()["preview"] is True
