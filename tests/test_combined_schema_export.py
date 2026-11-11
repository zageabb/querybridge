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


def test_current_view_export_is_explicitly_scoped(client):
    response = client.get(
        "/api/schema-map/export-html?subset=1&layer=combined&application=TAIJU"
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    match = re.search(r'<script type="application/json" id="snapshot">(.*?)</script>', page, re.S)
    assert match
    snap = json.loads(match.group(1))
    assert snap["scope"] == "selected view only"
    assert set(snap["layers"]) == {"combined"}
    assert all(t["application_name"] == "TAIJU"
               for t in snap["layers"]["combined"]["tables"])
    assert b"Export current view HTML" in client.get("/schema-map").data


def test_graphviz_offline_layout_positions_are_embedded(client):
    from schema_html_export import graphviz_layout
    graph = client.get("/api/schema-map?layer=combined").get_json()
    positions = graphviz_layout(graph)
    # When Graphviz is available, every visible table must have a position.
    if not positions:
        pytest.skip("Graphviz dot unavailable on this installation")
    assert set(positions) == {str(table["id"]) for table in graph["tables"]}
    assert all(len(coords) == 2 and all(isinstance(v, float) for v in coords)
               for coords in positions.values())
    html = client.get("/api/schema-map/export-html?subset=1&layer=combined").get_data(as_text=True)
    payload = re.search(r'<script type="application/json" id="snapshot">(.*?)</script>', html, re.S)
    assert payload
    snapshot = json.loads(payload.group(1))
    assert snapshot["layouts"]["combined"] == positions


def test_offline_export_contains_interactive_graphviz_routing(client):
    html = client.get("/api/schema-map/export-html?layer=combined").get_data(as_text=True)
    assert 'function layoutNodes(' in html
    assert 'function drawEdges(' in html
    assert 'function routedPath(' in html
    assert 'function bindTableDrag(' in html
    assert 'function clearRoute(' in html
    assert 'marker-end' in html
    assert 'Field descriptions' in html
    assert 'function highlight(' in html
    assert 'mouse' not in html.lower() or 'wheel' in html
    assert 'src="http' not in html


def test_graphviz_layout_no_network_or_script_injection():
    from schema_html_export import graphviz_layout
    graph = {
        "tables": [
            {"id": 1, "table_name": '<script>alert(1)</script>', "fields": []},
            {"id": 2, "table_name": "target", "fields": []},
        ],
        "relationships": [
            {"left_table_id": 1, "right_table_id": 2, "relationship_type": "lineage"}
        ],
    }
    positions = graphviz_layout(graph)
    assert not positions or set(positions) == {"1", "2"}
    # Graphviz only sees numeric local IDs; captured table names are never DOT input.


def test_live_interactive_schema_renderer_and_theme_controls(client):
    response = client.get("/schema-map")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'id="map-renderer"' in page
    assert 'value="interactive"' in page
    assert 'value="graphviz"' in page
    assert 'id="map-theme-toggle"' in page
    assert 'id="map-interactive-frame"' in page


def test_live_inline_export_and_saved_theme_toggle(client):
    response = client.get(
        "/api/schema-map/export-html?inline=1&subset=1&layer=combined&theme=dark"
    )
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("inline;")
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
    page = response.get_data(as_text=True)
    assert 'id="theme-toggle"' in page
    assert 'querybridge.theme' in page
    assert 'data-theme="dark"' in page or 'setTheme(snapshot.initial' in page
    assert 'function bindTableDrag(' in page
    assert 'function routedPath(' in page


def test_default_export_still_downloads_independent_html(client):
    response = client.get("/api/schema-map/export-html?subset=1&layer=combined")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment;")
    html = response.get_data(as_text=True)
    assert "--panel:" in html
    assert 'id="theme-toggle"' in html
    assert "<script" in html


def test_live_and_standalone_theme_modes_and_draggable_view(client):
    from pathlib import Path
    live = client.get("/schema-map")
    assert live.status_code == 200
    page = live.get_data(as_text=True)
    assert 'id="map-theme-toggle"' in page
    assert 'id="map-renderer"' in page
    assert 'value="interactive"' in page
    assert 'value="graphviz"' in page
    assert 'id="map-interactive-frame"' in page
    assert "theme.js" in page

    embedded = client.get(
        "/api/schema-map/export-html?inline=1&embedded=1&subset=1&layer=source&theme=dark"
    )
    assert embedded.status_code == 200
    assert embedded.headers["Content-Disposition"].startswith("inline")
    assert "frame-ancestors 'self'" in embedded.headers["Content-Security-Policy"]
    html = embedded.get_data(as_text=True)
    assert 'id="theme-toggle"' in html
    assert 'id="reset-positions"' in html
    assert 'querybridge.theme' in html
    assert 'querybridge.schema.map.positions.v1' in html
    assert 'data-embedded="true"' in html or 'dataset.embedded' in html
    assert '--bg:#f4f7fb' in html
    assert '--bg:#101820' in html
    match = re.search(r'<script type="application/json" id="snapshot">(.*?)</script>', html, re.S)
    assert match
    initial = json.loads(match.group(1))["initial"]
    assert initial["theme"] == "dark"
    assert initial["embedded"] is True

    download = client.get("/api/schema-map/export-html?layer=source&theme=light")
    assert download.headers["Content-Disposition"].startswith("attachment")
    assert json.loads(re.search(
        r'<script type="application/json" id="snapshot">(.*?)</script>',
        download.get_data(as_text=True), re.S
    ).group(1))["initial"]["embedded"] is False


def test_shared_notes_style_theme_asset_is_available(client):
    response=client.get("/static/theme.js")
    assert response.status_code == 200
    script=response.get_data(as_text=True)
    assert "querybridge.theme" in script
    assert "localStorage" in script
    assert "data-theme" in script or "dataset.theme" in script
    for url in ("/", "/catalogue", "/schema-map"):
        page=client.get(url)
        assert page.status_code == 200
        assert "theme.js" in page.get_data(as_text=True)
