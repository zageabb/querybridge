"""Full SAP DDIC CSV import: dry-run, descriptions, safety, batching and snapshots."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
import app as qb
from scripts.import_sap_ddic import main, run_import


@pytest.fixture()
def metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(qb, "DB_PATH", tmp_path / "querybridge.db")
    qb.init_db()
    return tmp_path


def csv_export(tmp_path, rows):
    path = tmp_path / "sap-ddic.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "TABLE_NAME", "TABLE_DESCRIPTION", "FIELD_NAME", "FIELD_DESCRIPTION",
            "DATA_TYPE", "LENGTH", "POSITION",
        ])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_import_all_descriptions_and_preserve_snapshot(metadata, capsys):
    path = csv_export(metadata, [
        {"TABLE_NAME": "EKKO", "TABLE_DESCRIPTION": "Purchasing document header",
         "FIELD_NAME": "EBELN", "FIELD_DESCRIPTION": "Purchasing Document Number",
         "DATA_TYPE": "CHAR", "LENGTH": "10", "POSITION": "1"},
        {"TABLE_NAME": "EKPO", "TABLE_DESCRIPTION": "Purchasing document item",
         "FIELD_NAME": "EBELN", "FIELD_DESCRIPTION": "Purchasing Document Number",
         "DATA_TYPE": "CHAR", "LENGTH": "10", "POSITION": "1"},
        {"TABLE_NAME": "EKPO", "TABLE_DESCRIPTION": "Purchasing document item",
         "FIELD_NAME": "EBELP", "FIELD_DESCRIPTION": "Purchasing Document Item",
         "DATA_TYPE": "NUMC", "LENGTH": "5", "POSITION": "2"},
        {"TABLE_NAME": "ZCUSTOM", "TABLE_DESCRIPTION": "Customer table",
         "FIELD_NAME": "ZKEY", "FIELD_DESCRIPTION": "Customer key",
         "DATA_TYPE": "CHAR", "LENGTH": "5", "POSITION": "1"},
    ])
    conn = qb.db()
    conn.execute(
        """INSERT INTO qb_schema_snapshots(name,description,snapshot_json,created_at,updated_at)
           VALUES ('before','',?, ?, ?)""",
        ('{"format":"querybridge-schema","format_version":1,"tables":[]}', qb.now_iso(), qb.now_iso()),
    )
    conn.commit()
    conn.close()

    assert main([str(path), "--db", str(qb.DB_PATH)]) == 0
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_tables").fetchone()[0] == 0
    conn.close()
    assert main([str(path), "--db", str(qb.DB_PATH), "--apply"]) == 0

    conn = qb.db()
    tables = conn.execute(
        "SELECT table_name,application_name,catalog,schema_name,description FROM qb_tables ORDER BY table_name"
    ).fetchall()
    assert [t["table_name"] for t in tables] == ["sap_ekko", "sap_ekpo"]
    assert all(t["application_name"] == "SAP S/4HANA" and not t["catalog"]
               and not t["schema_name"] for t in tables)
    assert tables[0]["description"] == "Purchasing document header"
    assert tables[1]["description"] == "Purchasing document item"
    fields = conn.execute(
        "SELECT column_name,data_type,comment FROM qb_columns ORDER BY column_name,table_id"
    ).fetchall()
    assert [(f["column_name"], f["data_type"]) for f in fields] == [
        ("EBELN", "CHAR(10)"), ("EBELN", "CHAR(10)"), ("EBELP", "NUMC(5)"),
    ]
    assert fields[2]["comment"] == "Purchasing Document Item"
    assert conn.execute("SELECT COUNT(*) FROM qb_relationships").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM qb_schema_snapshots").fetchone()[0] == 1
    snapshot = qb.serialize_working_schema(conn)
    assert snapshot["tables"][0]["description"] == "Purchasing document header"
    conn.close()

    assert main([str(path), "--db", str(qb.DB_PATH), "--apply"]) == 0
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_tables").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM qb_columns").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM qb_schema_snapshots").fetchone()[0] == 1
    conn.close()


def test_fills_only_blanks_never_overwrites_existing_descriptions(metadata):
    conn = qb.db()
    conn.execute(
        """INSERT INTO qb_tables(catalog,schema_name,table_name,application_name,description,captured_at)
           VALUES ('realcat','realschema','sap_ekko',NULL,'My trusted description',?)""",
        (qb.now_iso(),),
    )
    tid = conn.execute("SELECT id FROM qb_tables").fetchone()[0]
    conn.execute(
        """INSERT INTO qb_columns(table_id,ordinal_position,column_name,data_type,comment)
           VALUES (?,1,'EBELN','STRING','Existing field comment')""",
        (tid,),
    )
    conn.commit()
    conn.close()
    path = csv_export(metadata, [
        {"TABLE_NAME": "EKKO", "TABLE_DESCRIPTION": "SAP text",
         "FIELD_NAME": "EBELN", "FIELD_DESCRIPTION": "Another description",
         "DATA_TYPE": "CHAR", "LENGTH": "10", "POSITION": "1"},
        {"TABLE_NAME": "EKKO", "TABLE_DESCRIPTION": "SAP text",
         "FIELD_NAME": "LIFNR", "FIELD_DESCRIPTION": "Supplier account",
         "DATA_TYPE": "CHAR", "LENGTH": "10", "POSITION": "2"},
    ])
    assert main([str(path), "--db", str(qb.DB_PATH), "--apply"]) == 0
    conn = qb.db()
    assert conn.execute(
        "SELECT catalog,schema_name,application_name,description FROM qb_tables"
    ).fetchone()[:] == ("realcat", "realschema", None, "My trusted description")
    assert conn.execute(
        "SELECT data_type,comment FROM qb_columns WHERE column_name='EBELN'"
    ).fetchone()[:] == ("STRING", "Existing field comment")
    assert conn.execute(
        "SELECT comment FROM qb_columns WHERE column_name='LIFNR'"
    ).fetchone()[0] == "Supplier account"
    conn.close()


def test_import_rollback_on_unsorted_csv_and_ambiguous_matches(metadata, capsys):
    path = csv_export(metadata, [
        {"TABLE_NAME": "EKKO", "FIELD_NAME": "EBELN"},
        {"TABLE_NAME": "EKPO", "FIELD_NAME": "EBELP"},
        {"TABLE_NAME": "EKKO", "FIELD_NAME": "LIFNR"},
    ])
    assert main([str(path), "--db", str(qb.DB_PATH), "--apply"]) == 1
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_tables").fetchone()[0] == 0
    conn.execute(
        "INSERT INTO qb_tables(catalog,schema_name,table_name,captured_at) VALUES ('c1','a','sap_ekko',?)",
        (qb.now_iso(),),
    )
    conn.execute(
        "INSERT INTO qb_tables(catalog,schema_name,table_name,captured_at) VALUES ('c2','b','sap_ekko',?)",
        (qb.now_iso(),),
    )
    conn.commit()
    conn.close()
    path = csv_export(metadata, [{"TABLE_NAME": "EKKO", "FIELD_NAME": "EBELN"}])
    assert main([str(path), "--db", str(qb.DB_PATH), "--apply"]) == 1
    conn = qb.db()
    assert conn.execute("SELECT COUNT(*) FROM qb_columns").fetchone()[0] == 0
    conn.close()


def test_snapshot_restore_preserves_table_descriptions(metadata):
    conn = qb.db()
    conn.execute(
        """INSERT INTO qb_tables(table_name,application_name,description,captured_at)
           VALUES ('sap_test','SAP S/4HANA','Table description',?)""",
        (qb.now_iso(),),
    )
    snap = qb.serialize_working_schema(conn)
    qb.restore_working_schema(conn, snap)
    assert conn.execute("SELECT description FROM qb_tables").fetchone()[0] == "Table description"
    old = {"format": "querybridge-schema", "format_version": 1,
           "tables": [{k: v for k, v in snap["tables"][0].items() if k != "description"}],
           "relationships": [], "knowledge": [], "imports": []}
    # Already-saved legacy snapshots lacking the field must still be importable.
    # Use the actual full-format payload shape for compatibility.
    old = dict(snap)
    old["tables"] = [dict(snap["tables"][0])]
    del old["tables"][0]["description"]
    qb.restore_working_schema(conn, old)
    assert conn.execute("SELECT description FROM qb_tables").fetchone()[0] is None
    conn.close()
