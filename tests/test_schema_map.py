"""Schema Map: captured joins, isolated tables, application scope, Graphviz field ports."""
import pytest

import app as qb
from schema_graphviz import dot_graph


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "schema_map.db")
    qb.app.config["TESTING"] = True
    qb.init_db()
    conn = qb.db()
    tables = [
        ("projects", "TAIJU"),
        ("purchase_orders", "SAP S/4HANA"),
        ("milestones", "TAIJU"),
        ("isolated", "TAIJU"),
        ("unassigned", None),
    ]
    ids = {}
    for name, application in tables:
        cur = conn.execute(
            """INSERT INTO qb_tables (catalog, schema_name, table_name, application_name, captured_at)
               VALUES (?,?,?,?,?)""",
            ("some_catalog", "scm", name, application, qb.now_iso()),
        )
        ids[name] = cur.lastrowid
    fields = {}
    for table, column in [
        ("projects", "project_id"), ("projects", "project_no"),
        ("purchase_orders", "project_ref"), ("milestones", "project_ref"),
        ("isolated", "<img src=x onerror=alert(1)>"),
    ]:
        cur = conn.execute(
            """INSERT INTO qb_columns (table_id, ordinal_position, column_name, data_type, comment)
               VALUES (?,?,?,?,?)""",
            (ids[table], len(fields) + 1, column, "STRING", "note"),
        )
        fields[(table, column)] = cur.lastrowid

    conn.execute(
        """INSERT INTO qb_relationships
           (left_table_id,left_column_id,right_table_id,right_column_id,source,confidence,notes)
           VALUES (?,?,?,?,?,?,?)""",
        (ids["projects"], fields[("projects", "project_id")],
         ids["milestones"], fields[("milestones", "project_ref")],
         "manual", 0.97, "project link"),
    )
    conn.execute(
        """INSERT INTO qb_relationships
           (left_table_id,left_column_id,right_table_id,right_column_id,source,confidence,notes)
           VALUES (?,?,?,?,?,?,?)""",
        (ids["projects"], fields[("projects", "project_no")],
         ids["purchase_orders"], fields[("purchase_orders", "project_ref")],
         "llm", 0.81, "purchase order link"),
    )
    conn.commit()
    conn.close()
    return qb.app.test_client(), ids, fields


def test_page_uda_path(client):
    browser, _, _ = client
    headers = {
        "X-Forwarded-Prefix": "/apps/querybridge",
        "X-Forwarded-Host": "example.org",
        "X-Forwarded-Proto": "https",
    }
    page = browser.get("/schema-map", headers=headers)
    assert page.status_code == 200
    assert b"Schema Map" in page.data
    assert b'<base href="/apps/querybridge/">' in page.data
    assert b"/apps/querybridge/static/schema-map.js" in page.data
    assert b"/apps/querybridge/static/schema-diagram.js" in page.data
    assert b"Export SVG" in page.data


def test_overview_filter_unjoined_and_external(client):
    browser, ids, _ = client
    full = browser.get("/api/schema-map").json
    assert full["ok"]
    assert full["stats"]["total_tables"] == 5
    assert full["stats"]["shown_tables"] == 3
    assert full["stats"]["shown_joins"] == 2
    assert full["stats"]["unjoined_in_application"] == 2
    assert full["applications"] == ["SAP S/4HANA", "TAIJU"]
    assert full["has_unassigned"]
    assert {x["table_name"] for x in full["unjoined_tables"]} == {"isolated", "unassigned"}
    assert browser.get("/api/schema-map", query_string={"include_unjoined": "1"}).json["stats"]["shown_tables"] == 5

    within = browser.get("/api/schema-map", query_string={"application": "TAIJU"}).json
    assert within["stats"]["in_application"] == 3
    assert within["stats"]["shown_tables"] == 2
    assert within["stats"]["shown_joins"] == 1
    assert {x["table_name"] for x in within["unjoined_tables"]} == {"isolated"}
    cross = browser.get("/api/schema-map", query_string={
        "application": "TAIJU", "include_cross_app": "yes",
    }).json
    assert cross["stats"]["shown_tables"] == 3
    assert cross["stats"]["shown_joins"] == 2
    assert cross["stats"]["cross_application_tables"] == 1
    outside = next(t for t in cross["tables"] if t["table_name"] == "purchase_orders")
    assert outside["external"]

    without_label = browser.get("/api/schema-map", query_string={
        "application": "__unassigned__", "include_unjoined": "true",
    }).json
    assert [x["table_name"] for x in without_label["tables"]] == ["unassigned"]


def test_focus_table_and_invalid_params(client):
    browser, ids, _ = client
    focused = browser.get("/api/schema-map", query_string={
        "application": "TAIJU", "focus_table": str(ids["projects"]),
    }).json
    assert {x["table_name"] for x in focused["tables"]} == {"projects", "milestones"}
    isolated = browser.get("/api/schema-map", query_string={
        "application": "TAIJU", "focus_table": str(ids["isolated"]),
    }).json
    assert [x["table_name"] for x in isolated["tables"]] == ["isolated"]
    assert browser.get("/api/schema-map", query_string={"focus_table": "bogus"}).status_code == 400
    assert browser.get("/api/schema-map", query_string={
        "application": "TAIJU", "focus_table": str(ids["purchase_orders"]),
    }).status_code == 400
    assert browser.get("/api/schema-map/diagram", query_string={"mode": "nope"}).status_code == 400
    assert browser.get("/api/schema-map/diagram", query_string={"format": "txt"}).status_code == 400


def test_graphviz_source_exact_field_ports_and_safety(client):
    browser, ids, fields = client
    graph = browser.get("/api/schema-map", query_string={"include_unjoined": "1"}).json
    detail = dot_graph(graph, mode="detail", highlight_field=fields[("projects", "project_id")])
    assert f'T{ids["projects"]}:f{fields[("projects", "project_id")]}:e -- ' in detail
    assert f'T{ids["milestones"]}:f{fields[("milestones", "project_ref")]}:w' in detail
    assert "project link" in detail
    assert "onerror=alert(1)" in detail  # As plain graph label, never HTML element.
    assert "&lt;img src=x onerror=alert(1)&gt;" in detail
    assert "<img src=x" not in detail
    assert "fff0b3" in detail  # highlighted field
    overview = dot_graph(graph)
    assert "2 join" not in overview  # distinct table pairs, each has one join
    assert "1 join" in overview
    assert 'PORT="f' not in overview
    response = browser.get("/api/schema-map/diagram", query_string={
        "mode": "detail", "highlight_field": fields[("projects", "project_id")],
        "format": "dot",
    })
    assert response.status_code == 200
    assert response.mimetype == "text/vnd.graphviz"
    assert f'PORT="f{fields[("projects", "project_id")]}"' in response.get_data(as_text=True)
    assert browser.get("/api/schema-map/diagram", query_string={
        "mode": "detail", "highlight_field": 99999,
    }).status_code == 400


def test_graphviz_svg_rendering_and_export(client):
    browser, _, _ = client
    svg = browser.get("/api/schema-map/diagram", query_string={"mode": "detail"})
    assert svg.status_code == 200, svg.get_data(as_text=True)[:300]
    assert svg.mimetype == "image/svg+xml"
    assert b"<svg" in svg.data and b"project_id" in svg.data
    assert "default-src 'none'" in svg.headers["Content-Security-Policy"]
    image = browser.get("/api/schema-map/diagram", query_string={"download": "1"})
    assert 'querybridge-schema.svg' in image.headers["Content-Disposition"]
    dot = browser.get("/api/schema-map/diagram", query_string={
        "format": "dot", "download": "1",
    })
    assert 'querybridge-schema.dot' in dot.headers["Content-Disposition"]
