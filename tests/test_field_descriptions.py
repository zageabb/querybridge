"""Field description migration, inheritance and diagram rendering."""
import sqlite3

from application_layers import ensure_schema, resolved_descriptions
from schema_graphviz import dot_graph


def test_description_inheritance_and_override(tmp_path):
    conn = sqlite3.connect(tmp_path / "descriptions.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE qb_columns (id INTEGER PRIMARY KEY,comment TEXT);
        INSERT INTO qb_columns VALUES (1,'Purchasing Document Number');
        INSERT INTO qb_columns VALUES (2,'Company Code');
    """)
    ensure_schema(conn)
    conn.executescript("""
        INSERT INTO qb_layer_objects(id,kind,application_name,object_name,created_at)
        VALUES(1,'databricks','TAIJU','po_view','now'),
              (2,'application','TAIJU','dppp','now');
        INSERT INTO qb_layer_fields(id,object_id,field_name,ordinal_position)
        VALUES(1,1,'po_number',1),(2,2,'po_number',1);
        INSERT INTO qb_layer_lineage(id,target_field_id,source_column_id)
        VALUES(1,1,1);
        INSERT INTO qb_layer_lineage(id,target_field_id,upstream_field_id)
        VALUES(2,2,1);
    """)
    assert resolved_descriptions(conn)[1] == ('Purchasing Document Number','inherited')
    assert resolved_descriptions(conn)[2] == ('Purchasing Document Number','inherited')
    conn.execute("UPDATE qb_layer_fields SET description='TAIJU Purchase Order' WHERE id=2")
    assert resolved_descriptions(conn)[2] == ('TAIJU Purchase Order','explicit')
    assert resolved_descriptions(conn)[1] == ('Purchasing Document Number','inherited')
    conn.execute("UPDATE qb_layer_fields SET description='' WHERE id=2")
    conn.execute("INSERT INTO qb_layer_lineage(id,target_field_id,source_column_id) VALUES(3,1,2)")
    assert resolved_descriptions(conn)[1] == ('','ambiguous')
    assert resolved_descriptions(conn)[2][0] == ''
    ensure_schema(conn)  # migration idempotent
    assert 'description' in {r[1] for r in conn.execute("PRAGMA table_info(qb_layer_fields)")}
    conn.close()


def test_graphviz_field_description_optional():
    graph = {
        "tables": [{"id":1,"table_name":"EKKO","application_name":"SAP",
                    "fields":[{"id":2,"column_name":"EBELN","description":"Purchase order number",
                               "data_type":"CHAR(10)"}]}],
        "relationships": []
    }
    default = dot_graph(graph,mode="detail")
    expanded = dot_graph(graph,mode="detail",show_descriptions=True)
    assert 'TOOLTIP="Purchase order number"' in default
    assert 'Purchase order number</FONT>' not in default
    assert 'Purchase order number</FONT>' in expanded
