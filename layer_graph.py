"""Project reviewed QueryBridge schema joins across source, Databricks and app layers.

Databricks/Application views contain ONLY selected fields at the selected level.
Recorded source equality joins are projected only when *both endpoints* have
explicit lineage mappings. End-to-end displays provenance edges as well.
No missing field, JOIN, cardinality or transformation is inferred.
"""
from __future__ import annotations

from collections import defaultdict

from application_layers import ensure_schema

TABLE_OFFSET = 1_000_000_000
FIELD_OFFSET = 2_000_000_000
SOURCE_FIELD_OFFSET = 3_000_000_000
SOURCE_TABLE_OFFSET = 4_000_000_000
REL_OFFSET = 5_000_000_000
JOIN_OFFSET = 6_000_000_000
VALID_LAYERS = {"databricks", "application", "lineage"}


def empty(applications):
    return {
        "ok": True, "applications": applications, "has_unassigned": False,
        "tables": [], "relationships": [], "unjoined_tables": [],
        "stats": {
            "total_tables": 0, "in_application": 0, "shown_tables": 0,
            "shown_joins": 0, "unjoined_in_application": 0,
            "cross_application_tables": 0,
        },
    }


def graph(conn, layer, application="", focus_id=None, include_unjoined=False,
          include_cross_app=False):
    if layer not in VALID_LAYERS:
        raise ValueError("Invalid application layer")
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
    applications = sorted({o["application_name"] for o in objects}, key=str.casefold)
    if application and application not in applications:
        return empty(applications)

    object_by_id = {o["id"]: o for o in objects}
    field_by_id = {f["id"]: f for f in fields}
    fields_by_object = defaultdict(list)
    for f in fields:
        fields_by_object[f["object_id"]].append(f)

    # Only explicitly selected mappings are eligible for projection.
    source_to_db = defaultdict(set)
    db_to_app = defaultdict(set)
    source_ids = set()
    for edge in lineage:
        target = field_by_id.get(edge["target_field_id"])
        if not target:
            continue
        target_obj = object_by_id.get(target["object_id"])
        if not target_obj:
            continue
        if edge["source_column_id"] is not None and target_obj["kind"] == "databricks":
            source_to_db[edge["source_column_id"]].add(target["id"])
            source_ids.add(edge["source_column_id"])
        elif edge["upstream_field_id"] is not None and target_obj["kind"] == "application":
            upstream = field_by_id.get(edge["upstream_field_id"])
            if upstream and object_by_id[upstream["object_id"]]["kind"] == "databricks":
                db_to_app[upstream["id"]].add(target["id"])

    # Actual source joins remain authoritative; never join by matching names.
    source_joins = []
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='qb_relationships'"
    ).fetchone():
        source_joins = [dict(r) for r in conn.execute(
            """SELECT r.id,r.left_table_id,r.right_table_id,r.left_column_id,
                      r.right_column_id,lc.column_name AS left_field,
                      rc.column_name AS right_field,r.source,r.confidence,r.notes
               FROM qb_relationships r
               JOIN qb_columns lc ON lc.id=r.left_column_id
               JOIN qb_columns rc ON rc.id=r.right_column_id
               ORDER BY r.id"""
        )]

    kind = layer if layer != "lineage" else None
    base_objects = {
        o["id"] for o in objects
        if (not application or o["application_name"] == application)
        and (kind is None or o["kind"] == kind)
    }
    visible_object_ids = set(base_objects)
    if layer == "lineage":
        # Include parents only of the requested app's selected endpoints.
        changed = True
        while changed:
            changed = False
            for edge in lineage:
                dest = field_by_id.get(edge["target_field_id"])
                upstream = field_by_id.get(edge["upstream_field_id"]) if edge["upstream_field_id"] else None
                if dest and upstream and dest["object_id"] in visible_object_ids:
                    if upstream["object_id"] not in visible_object_ids:
                        visible_object_ids.add(upstream["object_id"])
                        changed = True

    tables = {}
    def add_layer_table(oid):
        if oid not in object_by_id:
            return
        obj = object_by_id[oid]
        tid = TABLE_OFFSET + oid
        if tid in tables:
            return
        selected = fields_by_object[oid]
        tables[tid] = {
            "id": tid, "catalog": obj["catalog"], "schema_name": obj["schema_name"],
            "table_name": obj["object_name"], "application_name": obj["application_name"],
            "table_type": obj["kind"].upper(), "layer_kind": obj["kind"],
            "description": obj["description"], "external": oid not in base_objects,
            "joined": False, "field_count": len(selected),
            "fields": [{
                "id": FIELD_OFFSET + f["id"], "table_id": tid,
                "column_name": f["field_name"], "data_type": f["data_type"],
                "nullable": None, "comment": f["expression"],
                "ordinal_position": f["ordinal_position"],
            } for f in selected],
        }

    for oid in visible_object_ids:
        add_layer_table(oid)

    def valid_layer_pair(left, right):
        if left not in field_by_id or right not in field_by_id:
            return False
        left_obj = object_by_id[field_by_id[left]["object_id"]]
        right_obj = object_by_id[field_by_id[right]["object_id"]]
        return ((not application or left_obj["application_name"] == application
                 or right_obj["application_name"] == application)
                and TABLE_OFFSET + left_obj["id"] in tables
                and TABLE_OFFSET + right_obj["id"] in tables)

    links = []
    seen = set()

    def append_join(lid, left, right, origin, confidence, notes):
        if not valid_layer_pair(left, right) or left == right:
            return
        lf, rf = field_by_id[left], field_by_id[right]
        lt, rt = TABLE_OFFSET + lf["object_id"], TABLE_OFFSET + rf["object_id"]
        if lt == rt:
            return
        key = ("join", tuple(sorted((left, right))), origin)
        if key in seen:
            return
        seen.add(key)
        links.append({
            "id": lid, "left_table_id": lt, "right_table_id": rt,
            "left_column_id": FIELD_OFFSET + left, "right_column_id": FIELD_OFFSET + right,
            "left_field": lf["field_name"], "right_field": rf["field_name"],
            "confidence": confidence, "source": origin, "notes": notes or "",
            "relationship_type": "join",
        })

    # Source joins projected to mapped fields. Their provenance is retained;
    # these are documented candidate joins, not proof of Databricks key equality.
    for src in source_joins:
        db_left = source_to_db[src["left_column_id"]]
        db_right = source_to_db[src["right_column_id"]]
        if layer in ("databricks", "lineage"):
            for left in sorted(db_left):
                for right in sorted(db_right):
                    append_join(
                        JOIN_OFFSET + src["id"] * 1_000_000 + left * 1000 + right,
                        left, right, "mapped:" + str(src["source"]),
                        src["confidence"], src["notes"],
                    )
        if layer in ("application", "lineage"):
            for a in db_left:
                for b in db_right:
                    for left in db_to_app[a]:
                        for right in db_to_app[b]:
                            append_join(
                                JOIN_OFFSET + 1_000_000_000_000 + src["id"] * 1_000_000
                                + left * 1000 + right,
                                left, right, "mapped:" + str(src["source"]),
                                src["confidence"], src["notes"],
                            )

    # End-to-end adds actual upstream provenance with direction. It is not a
    # database equality JOIN, and is never used to infer one.
    if layer == "lineage":
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            source_rows = [dict(r) for r in conn.execute(
                f"""SELECT c.id,c.table_id,c.column_name,c.data_type,c.nullable,
                           c.comment,c.ordinal_position,t.table_name,t.application_name,
                           t.catalog,t.schema_name,t.table_type
                    FROM qb_columns c JOIN qb_tables t ON t.id=c.table_id
                    WHERE c.id IN ({placeholders})""",sorted(source_ids)
            )]
        else:
            source_rows = []
        source_by_id = {s["id"]: s for s in source_rows}
        for edge in lineage:
            target = field_by_id.get(edge["target_field_id"])
            if not target or TABLE_OFFSET + target["object_id"] not in tables:
                continue
            if edge["upstream_field_id"] is not None:
                upstream = field_by_id.get(edge["upstream_field_id"])
                if not upstream or TABLE_OFFSET + upstream["object_id"] not in tables:
                    continue
                left_tid = TABLE_OFFSET + upstream["object_id"]
                left_fid = FIELD_OFFSET + upstream["id"]
                left_name = upstream["field_name"]
            else:
                src = source_by_id.get(edge["source_column_id"])
                if not src:
                    continue
                left_tid = SOURCE_TABLE_OFFSET + src["table_id"]
                left_fid = SOURCE_FIELD_OFFSET + src["id"]
                left_name = src["column_name"]
                if left_tid not in tables:
                    tables[left_tid] = {
                        "id": left_tid, "catalog": src["catalog"],
                        "schema_name": src["schema_name"], "table_name": src["table_name"],
                        "application_name": src["application_name"],
                        "table_type": src["table_type"], "layer_kind": "source",
                        "external": True, "joined": False, "field_count": 0, "fields": [],
                    }
                if not any(f["id"] == left_fid for f in tables[left_tid]["fields"]):
                    tables[left_tid]["fields"].append({
                        "id": left_fid, "table_id": left_tid, "column_name": left_name,
                        "data_type": src["data_type"], "nullable": src["nullable"],
                        "comment": src["comment"], "ordinal_position": src["ordinal_position"],
                    })
                    tables[left_tid]["field_count"] += 1
            links.append({
                "id": REL_OFFSET + edge["id"], "left_table_id": left_tid,
                "right_table_id": TABLE_OFFSET + target["object_id"],
                "left_column_id": left_fid,
                "right_column_id": FIELD_OFFSET + target["id"],
                "left_field": left_name, "right_field": target["field_name"],
                "confidence": None, "source": "lineage", "notes": edge["notes"] or "",
                "relationship_type": "lineage",
            })

    # Explicitly include only selected fields, even for source parents. An
    # unmapped original source field never leaks into a consumption view.
    linked = {tid for l in links for tid in (l["left_table_id"], l["right_table_id"])}
    for tid, table in tables.items():
        table["joined"] = tid in linked

    unjoined = sorted(
        [{"id": t["id"],"table_name":t["table_name"],
          "application_name":t["application_name"],"catalog":t["catalog"],
          "schema_name":t["schema_name"]}
         for t in tables.values() if t["id"] not in linked],
        key=lambda t:(t["application_name"] or "",t["table_name"]),
    )
    if focus_id is not None:
        if focus_id not in tables:
            raise ValueError("Selected table is not in this layer.")
        visible = {focus_id}
        for l in links:
            if l["left_table_id"] == focus_id:
                visible.add(l["right_table_id"])
            elif l["right_table_id"] == focus_id:
                visible.add(l["left_table_id"])
    else:
        # Selected fields are always visible by default in derived layers,
        # regardless of whether an explicit relationship was imported.
        visible = set(tables)
    shown = sorted(
        (t for tid,t in tables.items() if tid in visible),
        key=lambda t:(t["layer_kind"],t["table_name"].casefold(),t["id"]),
    )
    shown_links = [
        l for l in links if l["left_table_id"] in visible and l["right_table_id"] in visible
    ]
    return {
        "ok": True, "layer": layer, "applications": applications,
        "has_unassigned": False, "tables": shown,
        "relationships": shown_links, "unjoined_tables": unjoined,
        "stats": {
            "total_tables": len(tables), "in_application": len(base_objects),
            "shown_tables": len(shown), "shown_joins": len(shown_links),
            "unjoined_in_application": len(unjoined),
            "cross_application_tables": sum(1 for t in shown if t["external"]),
        },
    }
