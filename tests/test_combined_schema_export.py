"""Combined Databricks/UI schema map and portable HTML export regression tests."""
import json
import re

import pytest

import app as qb
from application_layers import ensure_schema


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "combined.db")
    qb.app.config["TESTING"] = True
    qb.init_db()
    conn = qb.db()
    ensure_schema(conn)
    conn.execute(
        """INSERT INTO qb_tables (id, table_name, application_name, captured_at)
           VALUES (1, 'EKKO', 'SAP S/4HANA', ?)""", (qb.now_iso(),)
    )
    conn.execute(
        """INSERT INTO qb_columns (id,table_id,column_name,ordinal_position,data_type)
           VALUES (1,1,'EBELN',1,'STRING')"""
    )
    for oid, kind, name, catalog, schema in (
        (10, "databricks", "po_view", "edp", "procurement"),
        (20, "application", "Purchase Order UI", "", ""),
    ):
        conn.execute(
            """INSERT INTO qb_layer_objects
               (id,kind,application_name,object_name,catalog,schema_name,description,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (oid, kind, "TAIJU", name, catalog, schema, "", qb.now_iso()),
        )
    for fid, oid, name in (
        (11,10,"po_number"), (12,10,"supplier_id"),
        (21,20,"PO Number"), (22,20,"Supplier"),
    ):
        conn.execute(
            """INSERT INTO qb_layer_fields
               (id,object_id,field_name,data_type,expression,ordinal_position)
               VALUES (?,?,?,?,?,?)""",
            (fid, oid, name, "STRING", "", fid),
        )
    conn.execute(
        """INSERT INTO qb_layer_lineage
           (id,target_field_id,source_column_id) VALUES (1,11,1)"""
    )
    conn.execute(
        """INSERT INTO qb_layer_lineage
           (id,target_field_id,upstream_field_id) VALUES (2,21,11)"""
    )
    conn.execute(
        """INSERT INTO qb_layer_lineage
           (id,target_field_id,upstream_field_id) VALUES (3,21,12)"""
    )
    conn.execute(
        """INSERT INTO qb_layer_lineage
           (id,target_field_id,upstream_field_id) VALUES (4,22,12)"""
    )
    conn.commit()
    conn.close()
    return qb.app.test_client()


def test_combined_contains_only_databricks_and_ui_fields_with_exact_mappings(client):
    response = client.get("/api/schema-map?layer=combined&application=TAIJU")
    assert response.status_code == 200
    graph = response.get_json()
    assert graph["layer"] == "combined"
    assert {t["layer_kind"] for t in graph["tables"]} == {"databricks", "application"}
    assert {t["table_name"] for t in graph["tables"]} == {"po_view", "Purchase Order UI"}
    assert all(t["table_name"] != "EKKO" for t in graph["tables"])
    edges = [r for r in graph["relationships"] if r["relationship_type"] == "lineage"]
    assert {(r["left_field"], r["right_field"]) for r in edges} == {
        ("po_number", "PO Number"),
        ("supplier_id", "PO Number"),
        ("supplier_id", "Supplier"),
    }
    assert len({r["id"] for r in edges}) == 3
    assert all("EBELN" not in [f["column_name"] for f in t["fields"]]
               for t in graph["tables"])


def test_combined_graphviz_field_ports_and_direction(client):
    response = client.get("/api/schema-map/diagram?layer=combined&mode=detail&format=dot")
    assert response.status_code == 200
    dot = response.get_data(as_text=True)
    assert 'PORT="f2000000011"' in dot
    assert 'PORT="f2000000021"' in dot
    assert "dir=forward" in dot
    assert "style=dashed" in dot
    assert "PO Number" in dot


def test_portable_html_embeds_five_layers_and_active_combined_view(client):
    response = client.get(
        "/api/schema-map/export-html?layer=combined&application=TAIJU&mode=detail"
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Export" not in response.headers["Content-Disposition"] or "attachment" in response.headers["Content-Disposition"]
    assert "Databricks + Application (UI)" in page
    assert "pointerdown" in page and "changeZoom" in page
    assert 'src="http' not in page
    assert "<link " not in page
    match = re.search(r'<script type="application/json" id="snapshot">(.*?)</script>', page, re.S)
    assert match
    snapshot = json.loads(match.group(1))
    assert set(snapshot["layers"]) == {
        "source", "databricks", "application", "combined", "lineage"
    }
    assert snapshot["initial"]["layer"] == "combined"
    assert snapshot["initial"]["application"] == "TAIJU"
    graph = snapshot["layers"]["combined"]
    assert len([e for e in graph["relationships"] if e["relationship_type"] == "lineage"]) == 3


def test_combined_visible_in_live_schema_map_and_rejects_invalid_export_layer(client):
    page = client.get("/schema-map")
    assert b"Databricks + Application (UI)" in page.data
    assert b"Export Interactive HTML" in page.data
    assert client.get("/api/schema-map/export-html?layer=invalid").status_code == 400
