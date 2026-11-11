"""Graph projection tests for recorded TAIJU field lineage."""
import sqlite3

from application_layers import ensure_schema
from layer_graph import graph, SOURCE_FIELD_OFFSET, FIELD_OFFSET


def test_layer_views_keep_source_dictionary_intact(tmp_path):
    conn = sqlite3.connect(tmp_path / "layers.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
      CREATE TABLE qb_tables (
        id INTEGER PRIMARY KEY, table_name TEXT, application_name TEXT,
        catalog TEXT, schema_name TEXT, table_type TEXT
      );
      CREATE TABLE qb_columns (
        id INTEGER PRIMARY KEY, table_id INTEGER REFERENCES qb_tables(id),
        column_name TEXT, data_type TEXT, nullable INTEGER, comment TEXT,
        ordinal_position INTEGER
      );
      INSERT INTO qb_tables VALUES(1,'EKKO','SAP S/4HANA',NULL,NULL,'TABLE');
      INSERT INTO qb_columns VALUES(1,1,'EBELN','CHAR(10)',0,NULL,1);
      INSERT INTO qb_columns VALUES(2,1,'BUKRS','CHAR(4)',0,NULL,2);
    """)
    ensure_schema(conn)
    conn.execute("""
      INSERT INTO qb_layer_objects
      (id,kind,application_name,object_name,created_at)
      VALUES(1,'databricks','TAIJU','sap_purchase_order_view','2026-11-11')
    """)
    conn.execute("""
      INSERT INTO qb_layer_objects
      (id,kind,application_name,object_name,created_at)
      VALUES(2,'application','TAIJU','dppp','2026-11-11')
    """)
    conn.execute("""
      INSERT INTO qb_layer_fields(id,object_id,field_name,ordinal_position)
      VALUES(1,1,'po_number',1),(2,2,'po_number',1)
    """)
    conn.execute("""
      INSERT INTO qb_layer_lineage(id,target_field_id,source_column_id)
      VALUES(1,1,1)
    """)
    conn.execute("""
      INSERT INTO qb_layer_lineage(id,target_field_id,upstream_field_id)
      VALUES(2,2,1)
    """)
    conn.commit()

    data = graph(conn, "databricks", "TAIJU", include_unjoined=True)
    assert len(data["relationships"]) == 0
    assert len(data["tables"]) == 1
    assert data["tables"][0]["layer_kind"] == "databricks"
    assert [f["column_name"] for f in data["tables"][0]["fields"]] == ["po_number"]

    consumption = graph(conn, "application", "TAIJU", include_unjoined=True)
    assert len(consumption["relationships"]) == 0
    assert len(consumption["tables"]) == 1
    assert {t["table_name"] for t in consumption["tables"]} == {"dppp"}

    lineage = graph(conn, "lineage", "TAIJU", include_unjoined=True)
    assert len(lineage["relationships"]) == 2
    assert len(lineage["tables"]) == 3
    assert graph(conn, "lineage", "Unknown", include_unjoined=True)["tables"] == []
    assert conn.execute("SELECT COUNT(*) FROM qb_columns").fetchone()[0] == 2
    assert conn.execute("SELECT column_name FROM qb_columns WHERE id=2").fetchone()[0] == "BUKRS"
    # Application and source field identifiers may never collide.
    assert SOURCE_FIELD_OFFSET + 1 != FIELD_OFFSET + 1
    conn.close()
