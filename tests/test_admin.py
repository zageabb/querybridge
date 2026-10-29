"""No-login Admin, worker-independent CSRF, integrity and proxy checks."""
import pytest

import app as qb


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "admin.db")
    # The Admin screen must work without either old setup variable.
    monkeypatch.delenv("QUERYBRIDGE_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("QUERYBRIDGE_SESSION_SECRET", raising=False)
    qb.app.config.update(TESTING=True)
    qb.init_db()
    yield qb.app.test_client()


def csrf_for(client):
    # Token is a double-submit cookie, independent of the Flask session.
    page = client.get("/admin")
    assert page.status_code == 200
    assert b"Metadata Administration" in page.data
    assert b"Sign in" not in page.data
    assert b"QUERYBRIDGE_ADMIN_PASSWORD" not in page.data
    token = page.get_data(as_text=True).split('window.querybridgeAdminToken = "')[1].split('"')[0]
    assert len(token) >= 40
    assert "qb_admin_csrf=" in page.headers["Set-Cookie"]
    assert "HttpOnly" in page.headers["Set-Cookie"]
    return token


def change(client, token, action, data):
    return client.post(
        "/admin/api/change",
        json={"action": action, "data": data},
        headers={"X-CSRF-Token": token},
    )


def test_admin_opens_without_password_or_setup(client):
    assert client.get("/admin/api/overview").status_code == 200
    assert client.get("/admin/login").status_code == 404
    assert client.post("/admin/login", data={"password": "unused"}).status_code == 404
    assert client.post("/admin/logout").status_code == 404
    assert client.post("/admin/api/change", json={"action": "create_table", "data": {}}).status_code == 403
    token = csrf_for(client)
    assert token
    assert change(client, token, "create_table", {"table_name": "new_table"}).status_code == 200
    assert client.get("/admin/api/overview").json["stats"]["tables"] == 1


def test_csrf_protects_writes_and_uda_prefix(client):
    assert client.get("/admin/api/overview").status_code == 200
    assert client.post("/admin/api/change", json={"action": "create_table", "data": {}}).status_code == 403
    token = csrf_for(client)
    assert client.post("/admin/api/change", json={"action": "create_table", "data": {}}).status_code == 403
    assert client.post(
        "/admin/api/change", json={"action": "create_table", "data": {}},
        headers={"X-CSRF-Token": "incorrect"},
    ).status_code == 403
    assert change(client, token, "not-supported", {}).status_code == 400

    # Origin checks add protection when the browser supplies origin metadata.
    malicious = {
        "X-CSRF-Token": token,
        "Origin": "https://another.example.org",
        "Sec-Fetch-Site": "cross-site",
    }
    assert client.post(
        "/admin/api/change", json={"action": "create_table", "data": {"table_name": "bad"}},
        headers=malicious,
    ).status_code == 403
    assert client.post(
        "/admin/api/change", json={"action": "create_table", "data": {"table_name": "bad"}},
        headers={"X-CSRF-Token": token, "Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"},
    ).status_code == 200

    headers = {
        "X-Forwarded-Prefix": "/apps/querybridge",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "example.org",
    }
    result = client.get("/admin", headers=headers)
    assert result.status_code == 200
    assert b'<base href="/apps/querybridge/">' in result.data
    assert b"/apps/querybridge/static/admin.js" in result.data
    assert "Path=/apps/querybridge/" in result.headers["Set-Cookie"]
    assert "Secure" in result.headers["Set-Cookie"]


def test_csrf_survives_server_secret_rotation(client):
    # Regression: multiple web workers may have distinct Flask session secrets.
    token = csrf_for(client)
    previous_key = qb.app.secret_key
    try:
        qb.app.secret_key = "a different worker's signing key"
        response = change(client, token, "create_table", {"table_name": "survived"})
        assert response.status_code == 200, response.json
        assert client.get("/admin/api/overview").json["stats"]["tables"] == 1
    finally:
        qb.app.secret_key = previous_key


def test_admin_csrf_cookie_required(client):
    token = csrf_for(client)
    client.delete_cookie("qb_admin_csrf")
    assert change(client, token, "create_table", {"table_name": "no_cookie"}).status_code == 403
    assert client.get("/admin/api/overview").json["stats"]["tables"] == 0


def test_full_metadata_admin_workflow(client):
    token = csrf_for(client)

    def create_table(name):
        result = change(client, token, "create_table", {
            "catalog": "main", "schema_name": "scm", "table_name": name,
            "application_name": "TAIJU", "table_type": "VIEW",
        })
        assert result.status_code == 200, result.json
        return result.json["table_id"]

    first = create_table("projects")
    second = create_table("orders")
    assert change(client, token, "create_table", {
        "catalog": "MAIN", "schema_name": "scm", "table_name": "PROJECTS",
    }).status_code == 400
    data = client.get("/admin/api/overview").json
    assert data["stats"]["tables"] == 2
    assert len(data["tables"]) == 2

    def create_field(table_id, name):
        response = change(client, token, "create_field", {
            "table_id": table_id, "column_name": name, "data_type": "STRING",
            "nullable": "0", "comment": "business key",
        })
        assert response.status_code == 200, response.json

    create_field(first, "project_id")
    create_field(second, "project_ref")
    assert change(client, token, "create_field", {
        "table_id": first, "column_name": "PROJECT_ID", "data_type": "INT",
    }).status_code == 400
    a = client.get(f"/admin/api/tables/{first}").json["fields"][0]
    b = client.get(f"/admin/api/tables/{second}").json["fields"][0]
    assert a["nullable"] == 0 and a["ordinal_position"] == 1

    assert change(client, token, "update_field", {
        "id": a["id"], "column_name": "project_id", "data_type": "BIGINT",
        "nullable": "1", "comment": "updated", "ordinal_position": "2",
    }).status_code == 200
    assert client.get(f"/admin/api/tables/{first}").json["fields"][0]["data_type"] == "BIGINT"

    assert change(client, token, "create_join", {
        "left_column_id": a["id"], "right_column_id": b["id"], "notes": "business key",
    }).status_code == 200
    reverse = change(client, token, "create_join", {
        "left_column_id": b["id"], "right_column_id": a["id"],
    })
    assert reverse.status_code == 400
    details = client.get(f"/admin/api/tables/{second}").json
    assert details["fields"][0]["join_count"] == 1
    assert details["joins"][0]["source"] == "manual"
    assert details["joins"][0]["confidence"] == 1.0
    join_id = details["joins"][0]["id"]
    assert change(client, token, "delete_join", {"id": join_id}).status_code == 400
    assert change(client, token, "delete_join", {"id": join_id, "confirm": True}).status_code == 200
    assert client.get(f"/admin/api/tables/{first}").json["joins"] == []

    assert change(client, token, "create_join", {
        "left_column_id": a["id"], "right_column_id": b["id"],
    }).status_code == 200
    assert change(client, token, "delete_field", {
        "id": a["id"], "confirm_name": "project_id"
    }).status_code == 400
    assert change(client, token, "delete_field", {
        "id": a["id"], "confirm_name": "project_id", "acknowledge_impact": True
    }).status_code == 200
    assert client.get(f"/admin/api/tables/{second}").json["joins"] == []
    assert change(client, token, "update_table", {
        "id": second, "catalog": "main", "schema_name": "scm",
        "table_name": "purchase_orders", "application_name": "SAP S/4HANA",
        "table_type": "TABLE",
    }).status_code == 200
    assert client.get(f"/admin/api/tables/{second}").json["table"]["application_name"] == "SAP S/4HANA"

    assert change(client, token, "delete_table", {
        "id": second, "confirm_name": "purchase_orders",
    }).status_code == 400
    assert change(client, token, "delete_table", {
        "id": second, "confirm_name": "purchase_orders", "acknowledge_impact": True,
    }).status_code == 200
    assert client.get(f"/admin/api/tables/{second}").status_code == 404
    final = client.get("/admin/api/overview").json
    assert final["stats"]["tables"] == 1
    assert final["stats"]["fields"] == 0
    assert final["stats"]["joins"] == 0
    assert len(final["audit"]) >= 8


def test_admin_operations_do_not_modify_saved_schema_or_core_tables(client):
    token = csrf_for(client)
    conn = qb.db()
    conn.execute(
        """INSERT INTO qb_schema_snapshots(name, description, snapshot_json, created_at, updated_at)
           VALUES ('protected-snapshot','','{"format":"querybridge-schema","format_version":1,"tables":[]}',?,?)""",
        (qb.now_iso(), qb.now_iso())
    )
    conn.commit()
    conn.close()
    created = change(client, token, "create_table", {"table_name": "local_only"})
    assert created.status_code == 200
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_schema_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT name FROM qb_schema_snapshots").fetchone()[0] == "protected-snapshot"
    assert conn.execute("SELECT COUNT(*) FROM qb_saved_queries").fetchone()[0] == 0
    conn.close()


def test_invalid_inputs_never_change_local_schema(client):
    token = csrf_for(client)
    for payload in [
        {"table_name": ""},
        {"table_name": "name" + chr(10) + "other"},
        {"table_name": "x" * 201},
        {"table_name": {"injected": "not text"}},
    ]:
        assert change(client, token, "create_table", payload).status_code == 400
    result = change(client, token, "create_table", {"table_name": "valid"})
    table_id = result.json["table_id"]
    for payload in [
        {"table_id": table_id, "column_name": ""},
        {"table_id": table_id, "column_name": "field", "nullable": "sometimes"},
        {"table_id": table_id, "column_name": "field", "ordinal_position": "-1"},
        {"table_id": table_id, "column_name": "field", "data_type": "x" * 256},
    ]:
        assert change(client, token, "create_field", payload).status_code == 400
    assert client.get(f"/admin/api/tables/{table_id}").json["fields"] == []
