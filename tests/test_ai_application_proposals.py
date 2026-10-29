"""Regression: application-aware AI and no-change proposals."""
import json

import pytest
import app as qb


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "ai_apps.db")
    qb.app.config["TESTING"] = True
    qb.init_db()
    conn = qb.db()
    ids = {}
    for catalog, schema, name, application in [
        ("qcat", "proc", "sap_ekko", "SAP S/4HANA"),
        ("qcat", "proc", "sap_ekpo", "SAP S/4HANA"),
        ("qcat", "scm", "milestones", "TAIJU"),
        ("qcat", "proc", "unassigned", None),
    ]:
        cur = conn.execute(
            """INSERT INTO qb_tables(catalog,schema_name,table_name,application_name,captured_at)
               VALUES(?,?,?,?,?)""",
            (catalog, schema, name, application, qb.now_iso()),
        )
        ids[name] = cur.lastrowid
    for name in ("sap_ekko", "sap_ekpo", "milestones"):
        conn.execute(
            "INSERT INTO qb_columns(table_id, ordinal_position, column_name, data_type) VALUES (?,?,?,?)",
            (ids[name], 1, "project_id", "STRING"),
        )
    left = conn.execute("SELECT id FROM qb_columns WHERE table_id=?", (ids["sap_ekko"],)).fetchone()[0]
    right = conn.execute("SELECT id FROM qb_columns WHERE table_id=?", (ids["milestones"],)).fetchone()[0]
    conn.execute(
        """INSERT INTO qb_relationships
           (left_table_id, left_column_id, right_table_id, right_column_id, confidence, source, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (ids["sap_ekko"], left, ids["milestones"], right, 0.93, "manual", "cross-app"),
    )
    conn.commit()
    conn.close()
    return qb.app.test_client()


def save_proposal(operations, title):
    conn = qb.db()
    cur = conn.execute(
        """INSERT INTO qb_schema_proposals
           (title,summary,skill_key,model,operations_json,status,created_at)
           VALUES (?, 'review summary','schema-curator','test',?,'proposed',?)""",
        (title, operations, qb.now_iso()),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def test_application_in_text_and_readonly_sql_metadata(client):
    conn = qb.db()
    context = qb.schema_context_text(conn)
    assert "TABLE " + qb.qualified_name({"catalog": "qcat", "schema_name": "proc", "table_name": "sap_ekko"}) in context
    for name in ("SAP S/4HANA", "TAIJU", "Unassigned"):
        assert "APPLICATION " + name in context
    assert "application_name" in qb.local_schema_sql_reference()
    assert "left_application" in qb.local_schema_sql_reference()
    tables = qb.execute_local_schema_select(
        conn,
        "SELECT application_name, COUNT(*) n FROM schema_tables GROUP BY application_name ORDER BY application_name"
    )
    assert [(x["application_name"], x["n"]) for x in tables["rows"]] == [
        (None, 1), ("SAP S/4HANA", 2), ("TAIJU", 1),
    ]
    fields = qb.execute_local_schema_select(
        conn,
        "SELECT table_name FROM schema_fields WHERE application_name='SAP S/4HANA' ORDER BY table_name"
    )
    assert [x["table_name"] for x in fields["rows"]] == ["sap_ekko", "sap_ekpo"]
    links = qb.execute_local_schema_select(
        conn,
        "SELECT left_application, right_application FROM schema_relationships",
    )
    assert links["rows"] == [{"left_application": "SAP S/4HANA", "right_application": "TAIJU"}]
    conn.close()


def test_noop_proposal_does_not_claim_schema_changed(client):
    proposal_id = save_proposal("[]", "No schema changes required")
    page = client.get("/ai-skills").get_data(as_text=True)
    assert f"#{proposal_id} · No schema changes required" in page
    assert "No schema changes were proposed. This is an informational review" in page
    assert "no changes</span>" in page
    assert "Review complete. No changes are pending" in page
    assert "This proposal cannot be applied" not in page
    result = client.post(f"/schema/proposals/{proposal_id}/apply", follow_redirects=True)
    assert b"contains no schema changes to apply" in result.data
    conn = qb.db()
    assert conn.execute("SELECT status FROM qb_schema_proposals WHERE id=?", (proposal_id,)).fetchone()[0] == "proposed"
    conn.close()
    assert client.post(f"/schema/proposals/{proposal_id}/reject").status_code == 302


def test_real_invalid_and_malformed_still_flagged(client):
    save_proposal(json.dumps([{
        "action": "remove_field", "catalog": "qcat", "schema_name": "proc",
        "table_name": "sap_ekko", "column_name": "nonexistent",
    }]), "Missing field")
    save_proposal("not-json", "Damaged operations")
    page = client.get("/ai-skills").get_data(as_text=True)
    assert "This proposal cannot be applied to the current schema." in page
    assert "field does not exist" in page
    assert "Saved operations are malformed." in page


def test_valid_proposal_still_applies(client):
    proposal_id = save_proposal(json.dumps([{
        "action": "add_field", "catalog": "qcat", "schema_name": "proc",
        "table_name": "sap_ekko", "column_name": "new_id", "data_type": "STRING",
    }]), "Add field")
    response = client.post(f"/schema/proposals/{proposal_id}/apply", follow_redirects=True)
    assert b"Applied schema proposal" in response.data
    conn = qb.db()
    assert conn.execute(
        """SELECT COUNT(*) FROM qb_columns c JOIN qb_tables t ON t.id=c.table_id
           WHERE t.table_name='sap_ekko' AND c.column_name='new_id'"""
    ).fetchone()[0] == 1
    conn.close()


def test_generated_noop_proposal_gets_application_context(client, monkeypatch):
    messages = {}
    def fake_agent(conn, prompt, **kwargs):
        messages["system"], messages["user"] = prompt[0]["content"], prompt[1]["content"]
        return json.dumps({
            "title": "No schema changes required",
            "summary": "Already meets the supplied request",
            "operations": [],
        }), []
    monkeypatch.setattr(qb, "run_schema_chat_agent", fake_agent)
    conn = qb.db()
    proposal_id, valid, invalid = qb.create_ai_schema_proposal(
        conn, "Review SAP S/4HANA application tables"
    )
    conn.commit()
    conn.close()
    assert (valid, invalid) == (0, 0)
    assert "APPLICATION SAP S/4HANA" in messages["user"]
    assert "APPLICATION TAIJU" in messages["user"]
    assert "application_name" in messages["system"]
    page = client.get("/ai-skills").get_data(as_text=True)
    assert f"#{proposal_id} · No schema changes required" in page
    assert "This proposal cannot be applied" not in page
