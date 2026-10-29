"""Schema Explorer search, joins, application labels and snapshot compatibility."""
import sqlite3
import pytest
import app as qb

@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "catalogue.db")
    qb.init_db()
    conn = qb.db()
    conn.execute(
        "INSERT INTO qb_tables(catalog,schema_name,table_name,application_name,captured_at) VALUES (?,?,?,?,?)",
        ("edp_scm", "procurement", "purchase_orders", "SAP S/4HANA", qb.now_iso()),
    )
    conn.execute(
        "INSERT INTO qb_tables(catalog,schema_name,table_name,application_name,captured_at) VALUES (?,?,?,?,?)",
        ("planning", "scheduling", "milestones", None, qb.now_iso()),
    )
    conn.execute(
        "INSERT INTO qb_tables(catalog,schema_name,table_name,captured_at) VALUES (?,?,?,?)",
        ("planning", "scheduling", "empty_table", qb.now_iso()),
    )
    purchase = conn.execute("SELECT id FROM qb_tables WHERE table_name='purchase_orders'").fetchone()[0]
    milestone = conn.execute("SELECT id FROM qb_tables WHERE table_name='milestones'").fetchone()[0]
    for table_id, ordinal, name, comment in [
        (purchase, 1, "project_id", "Purchase project reference"),
        (purchase, 2, "po_number", "Purchase order number"),
        (milestone, 1, "project_ref", "Milestone project reference"),
    ]:
        conn.execute(
            "INSERT INTO qb_columns(table_id,ordinal_position,column_name,data_type,comment) VALUES (?,?,?,?,?)",
            (table_id, ordinal, name, "STRING", comment),
        )
    a = conn.execute("SELECT id FROM qb_columns WHERE column_name='project_id'").fetchone()[0]
    b = conn.execute("SELECT id FROM qb_columns WHERE column_name='project_ref'").fetchone()[0]
    conn.execute(
        """INSERT INTO qb_relationships
           (left_table_id,left_column_id,right_table_id,right_column_id,confidence,source,notes)
           VALUES (?,?,?,?,?,?,?)""",
        (purchase, a, milestone, b, 0.88, "ai-approved", "Project business key"),
    )
    conn.commit()
    conn.close()
    qb.app.config["TESTING"] = True
    return qb.app.test_client()

def test_explorer_and_full_search(client):
    page = client.get("/catalogue")
    assert page.status_code == 200
    assert b"Schema Explorer" in page.data
    assert b"SAP S/4HANA" in page.data
    result = client.get("/api/catalogue/fields").json
    assert result["ok"] and result["total"] == 4
    assert any(row["field_id"] is None and row["table_name"] == "empty_table" for row in result["rows"])
    for term in ["SAP S/4HANA", "edp_scm", "procurement", "purchase_orders",
                 "po_number", "STRING", "Purchase order number"]:
        found = client.get("/api/catalogue/fields", query_string={"q": term}).json
        assert found["total"] > 0, term
        assert any(row["table_name"] == "purchase_orders" for row in found["rows"])
    filtered = client.get("/api/catalogue/fields", query_string={"application": "SAP S/4HANA"}).json
    assert filtered["total"] == 2
    assert all(row["application_name"] == "SAP S/4HANA" for row in filtered["rows"])
    assert client.get("/api/catalogue/fields", query_string={"q": "not-here"}).json["total"] == 0
    assert client.get("/api/catalogue/fields", query_string={"q": "%' OR 1=1 --"}).json["total"] == 0

def test_bidirectional_joins_and_provenance(client):
    rows = client.get("/api/catalogue/fields").json["rows"]
    ids = {r["column_name"]: r["field_id"] for r in rows if r["field_id"]}
    left = client.get(f"/api/catalogue/fields/{ids['project_id']}/joins").json
    right = client.get(f"/api/catalogue/fields/{ids['project_ref']}/joins").json
    for result, expected_target in [(left, "project_ref"), (right, "project_id")]:
        assert result["ok"] and len(result["joins"]) == 1
        link = result["joins"][0]
        assert link["target_column"] == expected_target
        assert link["confidence"] == 0.88
        assert link["source"] == "ai-approved"
        assert link["notes"] == "Project business key"
        unquoted = link["condition"].replace(chr(96), "")
        assert "edp_scm.procurement.purchase_orders.project_id" in unquoted
        assert "planning.scheduling.milestones.project_ref" in unquoted
    assert client.get(f"/api/catalogue/fields/{ids['po_number']}/joins").json["joins"] == []
    assert client.get("/api/catalogue/fields/999999/joins").status_code == 404

def test_application_assignment_snapshot_roundtrip(client):
    conn = qb.db()
    table_id = conn.execute("SELECT id FROM qb_tables WHERE table_name='milestones'").fetchone()[0]
    conn.close()
    endpoint = f"/api/catalogue/tables/{table_id}/application"
    assert client.post(endpoint, json={"application_name": " Primavera P6 "}).json["application_name"] == "Primavera P6"
    assert client.get("/api/catalogue/fields", query_string={"q": "Primavera P6"}).json["total"] == 1
    assert client.post(endpoint, json={"application_name": "x" * 121}).status_code == 400
    assert client.post(endpoint, json={"application_name": 5}).status_code == 400
    assert client.post("/api/catalogue/tables/999999/application", json={"application_name": "X"}).status_code == 404
    conn = qb.db()
    payload = qb.serialize_working_schema(conn)
    assert {t["table_name"]: t["application_name"] for t in payload["tables"]}["milestones"] == "Primavera P6"
    qb.restore_working_schema(conn, payload)
    assert conn.execute("SELECT application_name FROM qb_tables WHERE table_name='milestones'").fetchone()[0] == "Primavera P6"
    for t in payload["tables"]:
        t.pop("application_name", None)
    qb.restore_working_schema(conn, payload)
    assert conn.execute("SELECT application_name FROM qb_tables WHERE table_name='milestones'").fetchone()[0] is None
    conn.rollback()
    conn.close()

def test_application_column_migrates_legacy_database(monkeypatch, tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE qb_tables (
      id INTEGER PRIMARY KEY AUTOINCREMENT, catalog TEXT, schema_name TEXT,
      table_name TEXT NOT NULL, table_type TEXT, is_temporary INTEGER DEFAULT 0,
      raw_source TEXT, captured_at TEXT NOT NULL,
      UNIQUE(catalog, schema_name, table_name)
    )""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(qb, "DB_PATH", path)
    qb.init_db()
    conn = qb.db()
    assert "application_name" in [row["name"] for row in conn.execute("PRAGMA table_info(qb_tables)")]
    conn.close()

def test_proxy_prefix_for_schema_explorer(client):
    headers = {"X-Forwarded-Prefix": "/apps/querybridge",
               "X-Forwarded-Host": "example.org", "X-Forwarded-Proto": "https"}
    page = client.get("/catalogue", headers=headers)
    assert page.status_code == 200
    assert b'<base href="/apps/querybridge/">' in page.data
    assert b'/apps/querybridge/static/uda-path.js' in page.data
    assert client.get("/api/catalogue/fields", headers=headers).status_code == 200
