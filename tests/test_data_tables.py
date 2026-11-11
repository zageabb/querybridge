"""Data Tables CRUD, concurrency, audit and safety regression tests."""
import sqlite3

import pytest
from flask import Flask

from admin_console import create_admin_blueprint


@pytest.fixture
def client(tmp_path):
    database = tmp_path / "querybridge.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE qb_tables (
       id INTEGER PRIMARY KEY, table_name TEXT NOT NULL UNIQUE,
       application_name TEXT, description TEXT
    );
    CREATE TABLE qb_columns (
       id INTEGER PRIMARY KEY,
       table_id INTEGER NOT NULL REFERENCES qb_tables(id) ON DELETE CASCADE,
       column_name TEXT NOT NULL,
       ordinal_position INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE qb_admin_audit (
       id INTEGER PRIMARY KEY, action TEXT, entity_type TEXT,
       entity_id INTEGER, before_json TEXT, after_json TEXT,
       created_at TEXT
    );
    CREATE TABLE qb_llm_settings(id INTEGER PRIMARY KEY,base_url TEXT);
    INSERT INTO qb_tables(id,table_name,application_name)
       VALUES (1,'EKKO','SAP S/4HANA');
    INSERT INTO qb_columns(id,table_id,column_name) VALUES (1,1,'EBELN');
    """)
    connection.commit()
    connection.close()

    def db():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(create_admin_blueprint(db, lambda: "2026-11-11T00:00:00Z"))
    with app.test_client() as browser:
        page = browser.get("/admin/data-tables")
        assert page.status_code == 200
        token = page.data.decode().split("window.querybridgeAdminToken = ")[1].split(";")[0]
        import json
        yield browser, db, json.loads(token)


def write(client, token, method, path, payload):
    return client.open(
        path, method=method, json=payload, headers={"X-CSRF-Token": token}
    )


def test_list_search_update_audit_and_stale_edit(client):
    browser, db, token = client
    r = browser.get("/admin/api/data-tables").get_json()
    names = {item["name"] for item in r["tables"]}
    assert "qb_tables" in names
    assert "qb_llm_settings" not in names
    assert "qb_admin_audit" not in names
    data = browser.get("/admin/api/data-tables/qb_tables?q=EKKO").get_json()
    assert data["total"] == 1
    assert data["rows"][0]["values"]["table_name"] == "EKKO"
    version = data["rows"][0]["version"]
    no_token = browser.patch("/admin/api/data-tables/qb_tables/1", json={
        "confirm": True, "version": version, "values": {"description": "Test"}
    })
    assert no_token.status_code == 403
    updated = write(browser, token, "PATCH", "/admin/api/data-tables/qb_tables/1", {
        "confirm":True, "version":version, "values":{"description":"Local test"}
    })
    assert updated.status_code == 200, updated.get_json()
    stale = write(browser, token, "PATCH", "/admin/api/data-tables/qb_tables/1", {
        "confirm":True, "version":version, "values":{"description":"Stale"}
    })
    assert stale.status_code == 409
    assert db().execute("SELECT description FROM qb_tables WHERE id=1").fetchone()[0] == "Local test"
    assert db().execute("SELECT COUNT(*) FROM qb_admin_audit").fetchone()[0] == 1


def test_create_delete_fk_block_and_identifiers(client):
    browser, db, token = client
    invalid = write(browser, token, "POST", "/admin/api/data-tables/qb_tables", {
        "confirm":True, "values":{"table_name":"Z", "id":4}
    })
    assert invalid.status_code == 400
    created = write(browser, token, "POST", "/admin/api/data-tables/qb_tables", {
        "confirm":True, "values":{"table_name":"Other", "application_name":"Procure"}
    })
    assert created.status_code == 201, created.get_json()
    record_id = created.get_json()["id"]
    data = browser.get("/admin/api/data-tables/qb_tables").get_json()
    version = next(row["version"] for row in data["rows"] if row["values"]["id"] == record_id)
    deleted = write(browser, token, "DELETE", f"/admin/api/data-tables/qb_tables/{record_id}", {
        "confirm":True, "version":version
    })
    assert deleted.status_code == 200, deleted.get_json()
    data = browser.get("/admin/api/data-tables/qb_tables").get_json()
    version = next(row["version"] for row in data["rows"] if row["values"]["id"] == 1)
    blocked = write(browser, token, "DELETE", "/admin/api/data-tables/qb_tables/1", {
        "confirm":True, "version":version
    })
    assert blocked.status_code == 409
    assert db().execute("SELECT COUNT(*) FROM qb_columns").fetchone()[0] == 1
    assert browser.get("/admin/api/data-tables/sqlite_master").status_code == 404


def test_bad_page_and_sql_pattern_escape(client):
    browser, _, _ = client
    assert browser.get("/admin/api/data-tables/qb_tables?page=-1").status_code == 400
    assert browser.get("/admin/api/data-tables/qb_tables?q=%25").get_json()["total"] == 0
    assert browser.get("/admin/api/data-tables/qb_tables?q=EKKO").get_json()["total"] == 1
