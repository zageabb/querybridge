"""Read-only graph projection of QueryBridge application layer lineage.

Keeps existing source schema tables untouched. Converts recorded provenance
into the established Schema Map payload contract without pretending lineage is
an equality JOIN. Layer graph IDs occupy a disjoint positive range.
"""
from collections import defaultdict

from flask import jsonify

TABLE_OFFSET = 1_000_000_000
FIELD_OFFSET = 2_000_000_000
SOURCE_FIELD_OFFSET = 3_000_000_000
SOURCE_TABLE_OFFSET = 4_000_000_000
REL_OFFSET = 5_000_000_000
VALID_LAYERS = {"databricks", "application", "lineage"}


def graph(conn, layer, application="", focus_id=None, include_unjoined=False):
    if layer not in VALID_LAYERS:
        raise ValueError("Invalid application layer")
    # install() is a backwards-compatible lazy migration, including on GET.
    from application_layers import ensure_schema
    ensure_schema(conn)
    objects = [dict(r) for r in conn.execute(
        "SELECT * FROM qb_layer_objects ORDER BY kind,application_name,object_name,id"
    )]
    fields = [dict(r) for r in conn.execute(
        "SELECT * FROM qb_layer_fields ORDER BY object_id,ordinal_position,id"
    )]
    lineage = [dict(r) for r in conn.execute(
        "SELECT * FROM qb_layer_lineage ORDER BY id"
    )]
    apps = sorted({o["application_name"] for o in objects}, key=str.casefold)
    if application and application not in apps:
        # Match existing Schema Map behaviour: no results for unknown apps.
        return empty(apps)
    base = [o for o in objects if not application or o["application_name"] == application]
    base_ids = {o["id"] for o in base}
    by_field = {f["id"]: f for f in fields}
    by_object = {o["id"]: o for o in objects}
    def owner(fid):
        f = by_field.get(fid)
        return by_object.get(f["object_id"]) if f else None

    # Include only the selected layer and its immediate lineage parents.
    wanted = set()
    for obj in base:
        if layer == "databricks" and obj["kind"] == "databricks":
            wanted.add(obj["id"])
        elif layer == "application" and obj["kind"] == "application":
            wanted.add(obj["id"])
        elif layer == "lineage":
            wanted.add(obj["id"])
    for link in lineage:
        to = owner(link["target_field_id"])
        upstream = owner(link["upstream_field_id"]) if link["upstream_field_id"] else None
        if to and to["id"] in wanted and upstream:
            wanted.add(upstream["id"])
    if layer == "application":
        # Application view shows consumers and the Databricks fields they use.
        wanted = {x for x in wanted if by_object[x]["kind"] in ("application", "databricks")}

    tables = {}
    for oid in wanted:
        o = by_object[oid]
        tid = TABLE_OFFSET + oid
        tables[tid] = {
            "id": tid, "catalog": o["catalog"], "schema_name": o["schema_name"],
            "table_name": o["object_name"], "application_name": o["application_name"],
            "table_type": o["kind"].upper(), "field_count": 0,
            "external": oid not in base_ids, "joined": False, "fields": [],
            "layer_kind": o["kind"], "description": o["description"],
        }
    for field in fields:
        tid = TABLE_OFFSET + field["object_id"]
        if tid not in tables:
            continue
        tables[tid]["fields"].append({
            "id": FIELD_OFFSET + field["id"], "table_id": tid,
            "column_name": field["field_name"], "data_type": field["data_type"],
            "nullable": None, "comment": field["expression"],
            "ordinal_position": field["ordinal_position"],
        })
    for t in tables.values():
        t["field_count"] = len(t["fields"])
    links = []
    source_columns = {}
    if layer in ("databricks", "lineage"):
        ids = sorted({r["source_column_id"] for r in lineage if r["source_column_id"]})
        if ids:
            placeholders = ",".join("?" for _ in ids)
            source_columns = {r["id"]: dict(r) for r in conn.execute(
                f"""SELECT c.id,c.table_id,c.column_name,c.data_type,c.nullable,
                           c.comment,c.ordinal_position,t.table_name,t.application_name,
                           t.catalog,t.schema_name,t.table_type
                    FROM qb_columns c JOIN qb_tables t ON t.id=c.table_id
                    WHERE c.id IN ({placeholders})""", ids
            )}
    for edge in lineage:
        to = owner(edge["target_field_id"])
        if not to or TABLE_OFFSET + to["id"] not in tables:
            continue
        if edge["upstream_field_id"]:
            upstream = owner(edge["upstream_field_id"])
            if not upstream or TABLE_OFFSET + upstream["id"] not in tables:
                continue
            left_tid, left_fid = TABLE_OFFSET + upstream["id"], FIELD_OFFSET + edge["upstream_field_id"]
            left_name = by_field[edge["upstream_field_id"]]["field_name"]
        else:
            if layer == "application":
                continue
            src = source_columns.get(edge["source_column_id"])
            if not src:
                continue
            left_tid, left_fid = SOURCE_TABLE_OFFSET + src["table_id"], SOURCE_FIELD_OFFSET + src["id"]
            left_name = src["column_name"]
            if left_tid not in tables:
                tables[left_tid] = {
                    "id": left_tid, "catalog": src["catalog"],
                    "schema_name": src["schema_name"], "table_name": src["table_name"],
                    "application_name": src["application_name"], "table_type": src["table_type"],
                    "field_count": 0, "external": True, "joined": False,
                    "fields": [], "layer_kind": "source",
                }
            if all(f["id"] != left_fid for f in tables[left_tid]["fields"]):
                tables[left_tid]["fields"].append({
                    "id": left_fid, "table_id": left_tid, "column_name": left_name,
                    "data_type": src["data_type"], "nullable": src["nullable"],
                    "comment": src["comment"], "ordinal_position": src["ordinal_position"],
                })
                tables[left_tid]["field_count"] += 1
        links.append({
            "id": REL_OFFSET + edge["id"], "left_table_id": left_tid,
            "left_column_id": left_fid, "right_table_id": TABLE_OFFSET + to["id"],
            "right_column_id": FIELD_OFFSET + edge["target_field_id"],
            "left_field": left_name,
            "right_field": by_field[edge["target_field_id"]]["field_name"],
            "confidence": None, "source": "lineage", "notes": edge["notes"] or "",
            "relationship_type": "lineage",
        })
    linked = {tid for r in links for tid in (r["left_table_id"], r["right_table_id"])}
    for tid, table in tables.items():
        table["joined"] = tid in linked
    unjoined = [
        {"id":t["id"],"table_name":t["table_name"],"application_name":t["application_name"],
         "catalog":t["catalog"],"schema_name":t["schema_name"]}
        for t in tables.values() if t["id"] not in linked
    ]
    if focus_id is not None:
        if focus_id not in tables:
            raise ValueError("Selected table is not in this layer.")
        visible = {focus_id}
        for edge in links:
            if edge["left_table_id"] == focus_id:
                visible.add(edge["right_table_id"])
            elif edge["right_table_id"] == focus_id:
                visible.add(edge["left_table_id"])
    else:
        visible = set(tables) if include_unjoined else linked
    shown = sorted((t for tid,t in tables.items() if tid in visible),
                   key=lambda t:(t["layer_kind"],t["table_name"].casefold(),t["id"]))
    edges = [r for r in links if r["left_table_id"] in visible and r["right_table_id"] in visible]
    return {
        "ok":True, "layer":layer, "applications":apps, "has_unassigned":False,
        "tables":shown, "relationships":edges, "unjoined_tables":unjoined,
        "stats":{
            "total_tables":len(tables), "in_application":sum(1 for t in tables.values() if not t["external"]),
            "shown_tables":len(shown), "shown_joins":len(edges),
            "unjoined_in_application":len(unjoined),
            "cross_application_tables":sum(1 for t in shown if t["external"]),
        },
    }


def empty(applications):
    return {
        "ok":True,"applications":applications,"has_unassigned":False,
        "tables":[],"relationships":[],"unjoined_tables":[],
        "stats":{"total_tables":0,"in_application":0,"shown_tables":0,
                 "shown_joins":0,"unjoined_in_application":0,"cross_application_tables":0},
    }
