"""SAP import and schema Q&A regression tests, including the reported table-list issue."""
import copy
import json
from pathlib import Path

import pytest
import app as qb

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "samples" / "sap_s4hana_links_template.json"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "import.db")
    qb.app.config.update(TESTING=True)
    qb.init_db()
    return qb.app.test_client()


def csrf(client):
    page = client.get("/admin")
    assert page.status_code == 200
    return page.get_data(as_text=True).split('window.querybridgeAdminToken = "')[1].split('"')[0]


def post(client, token, endpoint, manifest, confirm=False):
    return client.post(
        "/admin/api/sap-links/" + endpoint,
        json={"document": manifest, "confirm": confirm},
        headers={"X-CSRF-Token": token},
    )


def sample():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def test_sap_sample_template_and_proxy_url(client):
    response = client.get("/admin/api/sap-links/template")
    assert response.status_code == 200
    assert response.json["format"] == "querybridge-sap-links"
    assert "sap_s4hana_links_template.json" in response.headers["Content-Disposition"]
    page = client.get("/admin", headers={
        "X-Forwarded-Prefix": "/apps/querybridge",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "example.org",
    })
    assert b"/apps/querybridge/static/sap-links.js" in page.data
    assert b"/apps/querybridge/admin/api/sap-links/template" in page.data
    assert b"Confirm and import" in page.data


def test_preview_does_not_write_and_import_creates_missing_without_catalog_or_schema(client):
    manifest = sample()
    token = csrf(client)
    assert post(client, token, "preview", manifest).status_code == 200
    preview = post(client, token, "preview", manifest).json["preview"]
    assert preview["application"] == "SAP S/4HANA"
    assert preview["counts"] == {
        "tables_to_add": 8,
        "fields_to_add": 14,
        "links_to_add": 10,
        "links_already_present": 0,
    }

    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_tables").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM qb_schema_snapshots").fetchone()[0] == 0
    conn.close()

    assert post(client, token, "apply", manifest).status_code == 400
    done = post(client, token, "apply", manifest, confirm=True)
    assert done.status_code == 200, done.json
    assert done.json["result"]["counts"] == preview["counts"]
    conn = qb.db()
    tables = conn.execute(
        "SELECT table_name,application_name,catalog,schema_name FROM qb_tables ORDER BY table_name"
    ).fetchall()
    assert [t["table_name"] for t in tables] == ["sap_ekbe", "sap_ekes", "sap_ekko", "sap_ekpo", "sap_eket", "sap_lfa1", "sap_makt", "sap_mara"]
    assert all(t["application_name"] == "SAP S/4HANA" for t in tables)
    assert all(t["catalog"] is None and t["schema_name"] is None for t in tables)
    assert conn.execute("SELECT COUNT(*) FROM qb_columns").fetchone()[0] == 14
    assert conn.execute("SELECT COUNT(*) FROM qb_relationships").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM qb_schema_snapshots").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM qb_admin_audit WHERE action='import_sap_links'").fetchone()[0] == 1
    assert conn.execute("SELECT DISTINCT source FROM qb_relationships").fetchone()[0] == "sap-import"
    conn.close()

    second = post(client, token, "preview", manifest).json["preview"]["counts"]
    assert second == {
        "tables_to_add": 0,
        "fields_to_add": 0,
        "links_to_add": 0,
        "links_already_present": 10,
    }
    assert post(client, token, "apply", manifest, confirm=True).status_code == 200
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_tables").fetchone()[0] == 8
    assert conn.execute("SELECT COUNT(*) FROM qb_relationships").fetchone()[0] == 10
    conn.close()


def test_existing_table_and_field_preserved_and_missing_field_added(client):
    token = csrf(client)
    conn = qb.db()
    conn.execute(
        """INSERT INTO qb_tables(catalog,schema_name,table_name,application_name,captured_at)
           VALUES('customcat','proc','sap_ekko',NULL,?)""",
        (qb.now_iso(),),
    )
    table_id = conn.execute("SELECT id FROM qb_tables WHERE table_name='sap_ekko'").fetchone()[0]
    conn.execute(
        "INSERT INTO qb_columns(table_id,ordinal_position,column_name,data_type) VALUES (?,?,?,?)",
        (table_id, 1, "EBELN", "EXISTING_TYPE"),
    )
    conn.commit()
    conn.close()
    result = post(client, token, "apply", sample(), confirm=True)
    assert result.status_code == 200, result.json
    conn = qb.db()
    t = conn.execute(
        "SELECT catalog,schema_name,application_name FROM qb_tables WHERE id=?", (table_id,)
    ).fetchone()
    assert (t["catalog"], t["schema_name"], t["application_name"]) == ("customcat", "proc", None)
    assert conn.execute(
        "SELECT data_type FROM qb_columns WHERE table_id=? AND column_name='EBELN'",
        (table_id,),
    ).fetchone()[0] == "EXISTING_TYPE"
    assert conn.execute(
        "SELECT COUNT(*) FROM qb_columns WHERE table_id=? AND column_name='LIFNR'",
        (table_id,),
    ).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM qb_tables WHERE lower(table_name)='sap_ekko'").fetchone()[0] == 1
    conn.close()


def test_invalid_and_ambiguous_rejected_without_partial_writes(client):
    token = csrf(client)
    manifest = sample()
    for mutate in [
        lambda x: x.update({"format": "invalid"}),
        lambda x: x["links"][0].update({"confidence": 4}),
        lambda x: x["links"].append(copy.deepcopy(x["links"][0])),
        lambda x: x["links"][0]["right"].update({"table": "sap_ekko"}),
    ]:
        copy_data = copy.deepcopy(manifest)
        mutate(copy_data)
        assert post(client, token, "preview", copy_data).status_code == 400
        assert post(client, token, "apply", copy_data, confirm=True).status_code == 400
    conn = qb.db()
    for schema in ("s1", "s2"):
        conn.execute(
            """INSERT INTO qb_tables(catalog,schema_name,table_name,captured_at)
               VALUES ('cat',?,?,?)""", (schema, "sap_ekko", qb.now_iso()),
        )
    conn.commit()
    conn.close()
    invalid = post(client, token, "apply", manifest, confirm=True)
    assert invalid.status_code == 400
    assert "Multiple captured tables" in invalid.json["error"]
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_tables").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM qb_relationships").fetchone()[0] == 0
    conn.close()


def test_import_keeps_existing_named_snapshot_unchanged(client):
    token = csrf(client)
    conn = qb.db()
    payload = json.dumps({"format": "querybridge-schema", "format_version": 1, "tables": []})
    conn.execute(
        """INSERT INTO qb_schema_snapshots(name, description, snapshot_json, created_at, updated_at)
           VALUES('my existing snapshot','',?,?,?)""",
        (payload, qb.now_iso(), qb.now_iso()),
    )
    conn.commit()
    conn.close()
    assert post(client, token, "apply", sample(), confirm=True).status_code == 200
    conn = qb.db()
    actual = conn.execute("SELECT snapshot_json FROM qb_schema_snapshots").fetchall()
    assert [row["snapshot_json"] for row in actual] == [payload]
    conn.close()


def test_list_tables_returns_real_captured_names_without_llm(client, monkeypatch):
    conn = qb.db()
    conn.execute(
        """INSERT INTO qb_tables(catalog,schema_name,table_name,application_name,captured_at)
           VALUES('testcat','purchase','sap_ekko','SAP S/4HANA',?)""",
        (qb.now_iso(),),
    )
    conn.commit()
    conn.close()
    def llm_must_not_run(*args, **kwargs):
        raise AssertionError("Inventory must use SQLite and not Ollama")
    monkeypatch.setattr(qb, "run_schema_chat_agent", llm_must_not_run)

    response = client.post(
        "/schema/proposals/create",
        data={"request_text": "List of tables", "intent": "answer"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "sap_ekko" in text and "testcat.purchase.EKKO" in text
    assert "Schema answer" in text or "Table inventory" in text
    assert "No schema changes were proposed. This is an informational review" not in text
    conn = qb.db()
    record = conn.execute(
        "SELECT request_kind,operations_json,summary FROM qb_schema_proposals ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert record["request_kind"] == "answer"
    assert record["operations_json"] == "[]"
    assert "testcat.purchase.EKKO" in record["summary"]
    conn.close()


def test_asking_application_filtered_inventory_and_no_apply_button(client):
    token = csrf(client)
    assert post(client, token, "apply", sample(), confirm=True).status_code == 200
    response = client.post(
        "/schema/proposals/create",
        data={"request_text": "List tables for SAP S/4HANA", "intent": "answer"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    assert "sap_ekko" in text and "EKPO" in text
    assert 'proposal-status answer' in text
    assert "Read-only answer from the current local schema" in text
    # No Apply button inside an informational record.
    assert "Apply proposal</button>" not in text
