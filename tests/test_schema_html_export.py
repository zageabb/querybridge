"""Regression tests for the standalone, offline HTML schema export."""
import json
import re
import pytest
import app as qb

@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "export.db")
    qb.app.config["TESTING"] = True
    qb.init_db()
    conn = qb.db()
    a = conn.execute("INSERT INTO qb_tables (table_name, application_name, captured_at) VALUES (?,?,?)",
                     ("projects", "TAIJU", qb.now_iso())).lastrowid
    b = conn.execute("INSERT INTO qb_tables (table_name, application_name, captured_at) VALUES (?,?,?)",
                     ("orders", "SAP", qb.now_iso())).lastrowid
    x = conn.execute("INSERT INTO qb_columns (table_id,ordinal_position,column_name,data_type) VALUES (?,?,?,?)",
                     (a,1,"<script>alert(1)</script>","STRING")).lastrowid
    y = conn.execute("INSERT INTO qb_columns (table_id,ordinal_position,column_name,data_type) VALUES (?,?,?,?)",
                     (b,1,"project_ref","STRING")).lastrowid
    conn.execute("INSERT INTO qb_relationships (left_table_id,left_column_id,right_table_id,right_column_id,source) VALUES (?,?,?,?,?)",
                 (a,x,b,y,"manual"))
    conn.commit()
    conn.close()
    return qb.app.test_client()

def test_html_export_is_complete_offline_and_escaped(client):
    response=client.get("/api/schema-map/export-html")
    assert response.status_code==200
    assert response.mimetype=="text/html"
    assert 'attachment;' in response.headers["Content-Disposition"]
    page=response.get_data(as_text=True)
    assert 'application/json' in page
    assert 'pointerdown' in page
    assert 'wheel' in page
    assert 'highlight' in page
    assert '<script>alert(1)</script>' not in page
    assert 'src="http' not in page
    assert '<link ' not in page
    match=re.search(r'<script type="application/json" id="snapshot">(.*?)</script>',page,re.S)
    assert match
    data=json.loads(match.group(1))
    assert {x["table_name"] for x in data["tables"]}=={"projects","orders"}
    assert len(data["relationships"])==1

def test_schema_map_shows_export_action(client):
    response=client.get("/schema-map")
    assert response.status_code==200
    assert b"Export interactive HTML" in response.data
