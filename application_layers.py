"""Application consumption layers and field-level lineage for QueryBridge.

A layer is metadata only: source fields remain in qb_tables/qb_columns, while
Databricks and application objects contain only explicitly selected fields.
"""
from __future__ import annotations

import json
import sqlite3

from flask import jsonify, request


def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS qb_layer_objects (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ('databricks','application')),
        application_name TEXT NOT NULL,
        object_name TEXT NOT NULL,
        catalog TEXT NOT NULL DEFAULT '',
        schema_name TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(kind, application_name, catalog, schema_name, object_name)
    );
    CREATE TABLE IF NOT EXISTS qb_layer_fields (
        id INTEGER PRIMARY KEY,
        object_id INTEGER NOT NULL REFERENCES qb_layer_objects(id) ON DELETE CASCADE,
        field_name TEXT NOT NULL,
        data_type TEXT,
        expression TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        ordinal_position INTEGER NOT NULL DEFAULT 0,
        UNIQUE(object_id, field_name)
    );
    CREATE TABLE IF NOT EXISTS qb_layer_lineage (
        id INTEGER PRIMARY KEY,
        target_field_id INTEGER NOT NULL REFERENCES qb_layer_fields(id) ON DELETE CASCADE,
        source_column_id INTEGER REFERENCES qb_columns(id) ON DELETE CASCADE,
        upstream_field_id INTEGER REFERENCES qb_layer_fields(id) ON DELETE CASCADE,
        notes TEXT NOT NULL DEFAULT '',
        CHECK ((source_column_id IS NOT NULL) != (upstream_field_id IS NOT NULL)),
        UNIQUE(target_field_id,source_column_id),
        UNIQUE(target_field_id,upstream_field_id)
    );
    CREATE INDEX IF NOT EXISTS idx_qb_layer_lineage_source ON qb_layer_lineage(source_column_id);
    CREATE INDEX IF NOT EXISTS idx_qb_layer_lineage_upstream ON qb_layer_lineage(upstream_field_id);
    """)
    if "description" not in {r[1] for r in conn.execute("PRAGMA table_info(qb_layer_fields)")}:
        conn.execute("ALTER TABLE qb_layer_fields ADD COLUMN description TEXT NOT NULL DEFAULT ''")


def resolved_descriptions(conn):
    """Return explicit or unambiguous inherited description for each layer field.

    Multiple parents with conflicting descriptions are intentionally left
    unresolved. Never overwrite local wording with upstream metadata.
    """
    fields = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id,description FROM qb_layer_fields"
    )}
    upstream = {}
    for record in conn.execute("""
        SELECT l.target_field_id, l.upstream_field_id, c.comment AS source_comment
        FROM qb_layer_lineage l
        LEFT JOIN qb_columns c ON c.id=l.source_column_id
    """):
        upstream.setdefault(record["target_field_id"], []).append(
            (record["upstream_field_id"], record["source_comment"])
        )
    cache = {}
    def resolve(fid, visited):
        if fid in cache:
            return cache[fid]
        if fid not in fields or fid in visited:
            return ("", "none")
        explicit = (fields[fid]["description"] or "").strip()
        if explicit:
            cache[fid] = (explicit, "explicit")
            return cache[fid]
        inherited = set()
        for parent_id, source_comment in upstream.get(fid, []):
            if parent_id is None:
                desc = (source_comment or "").strip()
            else:
                desc, _ = resolve(parent_id, visited | {fid})
            if desc:
                inherited.add(desc)
        result = (next(iter(inherited)), "inherited") if len(inherited) == 1 else ("", "ambiguous" if len(inherited) > 1 else "none")
        cache[fid] = result
        return result
    return {fid: resolve(fid, set()) for fid in fields}



def install(bp, db, now):
    """Register endpoints on the existing Admin blueprint (and its CSRF guard)."""

    def bad(message, status=400):
        return jsonify({"ok": False, "error": message}), status

    def string(value, label, limit=255, required=False):
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text")
        value = value.strip()
        if (required and not value) or len(value) > limit or any(ord(x) < 32 for x in value):
            raise ValueError(f"{label} is missing or invalid")
        return value

    def audit(conn, action, entity, identifier, payload):
        conn.execute(
            """INSERT INTO qb_admin_audit
               (action,entity_type,entity_id,before_json,after_json,created_at)
               VALUES (?,?,?,NULL,?,?)""",
            (action,entity,identifier,json.dumps(payload,ensure_ascii=False),now()),
        )

    @bp.get("/api/layers")
    def get_layers():
        conn = db()
        try:
            ensure_schema(conn)
            objects = [dict(row) for row in conn.execute(
                "SELECT * FROM qb_layer_objects ORDER BY kind,application_name,object_name"
            )]
            fields = [dict(row) for row in conn.execute(
                """SELECT f.*,o.kind,o.application_name,o.object_name
                   FROM qb_layer_fields f JOIN qb_layer_objects o ON o.id=f.object_id
                   ORDER BY f.object_id,f.ordinal_position,f.id"""
            )]
            inherited = resolved_descriptions(conn)
            for field in fields:
                field["resolved_description"], field["description_source"] = inherited[field["id"]]
            lineage = [dict(row) for row in conn.execute(
                """SELECT l.*,c.column_name AS source_field,t.table_name AS source_table,
                          t.application_name AS source_application,
                          u.field_name AS upstream_field,p.object_name AS upstream_object
                   FROM qb_layer_lineage l
                   LEFT JOIN qb_columns c ON c.id=l.source_column_id
                   LEFT JOIN qb_tables t ON t.id=c.table_id
                   LEFT JOIN qb_layer_fields u ON u.id=l.upstream_field_id
                   LEFT JOIN qb_layer_objects p ON p.id=u.object_id
                   ORDER BY l.id"""
            )]
            sources = [dict(row) for row in conn.execute(
                """SELECT c.id,c.column_name,c.comment AS description,t.table_name,t.application_name,t.catalog,t.schema_name
                   FROM qb_columns c JOIN qb_tables t ON t.id=c.table_id
                   ORDER BY t.application_name,t.table_name,c.ordinal_position"""
            )]
            return jsonify({"ok": True,"objects":objects,"fields":fields,
                            "lineage":lineage,"sources":sources})
        finally:
            conn.close()

    @bp.post("/api/layers/objects")
    def add_object():
        payload = request.get_json(silent=True) or {}
        try:
            kind = string(payload.get("kind"),"Kind",required=True)
            if kind not in ("databricks","application"):
                raise ValueError("Kind must be databricks or application")
            application = string(payload.get("application_name"),"Application",120,True)
            name = string(payload.get("object_name"),"Object name",200,True)
            catalog = string(payload.get("catalog"),"Catalog",200)
            schema = string(payload.get("schema_name"),"Schema",200)
            description = string(payload.get("description"),"Description",2000)
            conn = db()
            try:
                ensure_schema(conn)
                with conn:
                    cursor = conn.execute(
                        """INSERT INTO qb_layer_objects
                           (kind,application_name,object_name,catalog,schema_name,description,created_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (kind,application,name,catalog,schema,description,now()),
                    )
                    audit(conn,"create_layer_object","layer_object",cursor.lastrowid,payload)
                return jsonify({"ok":True,"id":cursor.lastrowid}),201
            finally:
                conn.close()
        except (ValueError,sqlite3.IntegrityError) as exc:
            return bad(str(exc))

    @bp.post("/api/layers/fields")
    def add_field():
        payload = request.get_json(silent=True) or {}
        try:
            object_id = int(payload.get("object_id"))
            name = string(payload.get("field_name"),"Field name",200,True)
            dtype = string(payload.get("data_type"),"Type",200)
            expression = string(payload.get("expression"),"Transformation",2000)
            description = string(payload.get("description"),"Description",4000)
            conn = db()
            try:
                ensure_schema(conn)
                with conn:
                    obj = conn.execute("SELECT id FROM qb_layer_objects WHERE id=?",(object_id,)).fetchone()
                    if not obj:
                        raise ValueError("Layer object does not exist")
                    ordinal = conn.execute(
                        "SELECT coalesce(max(ordinal_position),0)+1 FROM qb_layer_fields WHERE object_id=?",
                        (object_id,),
                    ).fetchone()[0]
                    cur = conn.execute(
                        """INSERT INTO qb_layer_fields
                           (object_id,field_name,data_type,expression,description,ordinal_position)
                           VALUES (?,?,?,?,?,?)""",(object_id,name,dtype or None,expression,description,ordinal),
                    )
                    audit(conn,"create_layer_field","layer_field",cur.lastrowid,payload)
                return jsonify({"ok":True,"id":cur.lastrowid}),201
            finally:
                conn.close()
        except (TypeError,ValueError,sqlite3.IntegrityError) as exc:
            return bad(str(exc))

    @bp.patch("/api/layers/fields/<int:field_id>/description")
    def edit_layer_field_description(field_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "description" not in payload:
            return bad("Supply a description (empty to inherit).")
        try:
            description = string(payload["description"], "Description", 4000)
        except ValueError as exc:
            return bad(str(exc))
        conn = db()
        try:
            ensure_schema(conn)
            with conn:
                old = conn.execute("SELECT description FROM qb_layer_fields WHERE id=?", (field_id,)).fetchone()
                if old is None:
                    return bad("Field not found.",404)
                conn.execute("UPDATE qb_layer_fields SET description=? WHERE id=?", (description,field_id))
                audit(conn,"update_layer_field_description","layer_field",field_id,
                      {"before":old["description"],"after":description})
            return jsonify({"ok":True,"id":field_id,"description":description})
        finally:
            conn.close()

    @bp.patch("/api/layers/source-fields/<int:field_id>/description")
    def edit_source_field_description(field_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "description" not in payload:
            return bad("Supply a description.")
        try:
            description = string(payload["description"], "Description", 4000)
        except ValueError as exc:
            return bad(str(exc))
        conn = db()
        try:
            with conn:
                old = conn.execute("SELECT comment FROM qb_columns WHERE id=?",(field_id,)).fetchone()
                if old is None:
                    return bad("Source field not found.",404)
                conn.execute("UPDATE qb_columns SET comment=? WHERE id=?",(description,field_id))
                audit(conn,"update_source_field_description","column",field_id,
                      {"before":old["comment"],"after":description})
            return jsonify({"ok":True,"id":field_id,"description":description})
        finally:
            conn.close()

    @bp.post("/api/layers/lineage")
    def add_lineage():
        payload = request.get_json(silent=True) or {}
        try:
            target = int(payload.get("target_field_id"))
            source = payload.get("source_column_id")
            upstream = payload.get("upstream_field_id")
            if (source is None) == (upstream is None):
                raise ValueError("Select exactly one source field or upstream layer field")
            source = int(source) if source is not None else None
            upstream = int(upstream) if upstream is not None else None
            notes = string(payload.get("notes"),"Notes",2000)
            conn = db()
            try:
                ensure_schema(conn)
                with conn:
                    target_row = conn.execute(
                        """SELECT f.id,o.kind FROM qb_layer_fields f
                           JOIN qb_layer_objects o ON o.id=f.object_id WHERE f.id=?""",
                        (target,),
                    ).fetchone()
                    if not target_row:
                        raise ValueError("Target field does not exist")
                    if source is not None and not conn.execute(
                        "SELECT id FROM qb_columns WHERE id=?",(source,)
                    ).fetchone():
                        raise ValueError("Source column does not exist")
                    if upstream is not None:
                        upstream_row = conn.execute(
                            """SELECT f.id,o.kind FROM qb_layer_fields f
                               JOIN qb_layer_objects o ON o.id=f.object_id WHERE f.id=?""",
                            (upstream,),
                        ).fetchone()
                        if not upstream_row or upstream == target:
                            raise ValueError("Invalid upstream field")
                        if target_row["kind"] != "application" or upstream_row["kind"] != "databricks":
                            raise ValueError("Upstream mapping must be Databricks to application")
                    elif target_row["kind"] != "databricks":
                        raise ValueError("Source dictionary fields map to Databricks fields")
                    cur = conn.execute(
                        """INSERT INTO qb_layer_lineage
                           (target_field_id,source_column_id,upstream_field_id,notes)
                           VALUES (?,?,?,?)""",(target,source,upstream,notes),
                    )
                    audit(conn,"create_layer_lineage","layer_lineage",cur.lastrowid,payload)
                return jsonify({"ok":True,"id":cur.lastrowid}),201
            finally:
                conn.close()
        except (TypeError,ValueError,sqlite3.IntegrityError) as exc:
            return bad(str(exc))

    @bp.post("/api/layers/import")
    def import_layer_document():
        """Atomic, idempotent JSON selection import by stable object/field names.

        Objects may include field definitions; lineage is added afterwards using
        stable source column IDs or existing upstream field IDs.
        """
        document = request.get_json(silent=True) or {}
        try:
            if document.get("format") != "querybridge-application-layer" or document.get("version") != 1:
                raise ValueError("Expected querybridge-application-layer version 1")
            items = document.get("objects")
            if not isinstance(items,list) or len(items)>200:
                raise ValueError("objects must be an array of at most 200 entries")
            planned=[]
            for item in items:
                if not isinstance(item,dict):
                    raise ValueError("Each object must be a JSON object")
                kind=string(item.get("kind"),"Kind",required=True)
                if kind not in ("databricks","application"):
                    raise ValueError("Invalid kind")
                application=string(item.get("application_name"),"Application",120,True)
                name=string(item.get("object_name"),"Name",200,True)
                catalog=string(item.get("catalog"),"Catalog",200)
                schema=string(item.get("schema_name"),"Schema",200)
                fields=item.get("fields",[])
                if not isinstance(fields,list) or len(fields)>1000:
                    raise ValueError("fields must be an array (max 1000)")
                parsed=[]
                for field in fields:
                    if isinstance(field,str):
                        field={"field_name":field}
                    if not isinstance(field,dict):
                        raise ValueError("Invalid field")
                    parsed.append((string(field.get("field_name"),"Field",200,True),
                                   string(field.get("data_type"),"Type",200),
                                   string(field.get("expression"),"Expression",2000),
                                   string(field.get("description"),"Description",4000)))
                planned.append((kind,application,name,catalog,schema,parsed))
            if request.args.get("preview")=="1":
                return jsonify({"ok":True,"objects":len(planned),
                                "fields":sum(len(x[5]) for x in planned),"preview":True})
            conn=db()
            try:
                ensure_schema(conn)
                with conn:
                    for kind,app,name,catalog,schema,fields in planned:
                        conn.execute(
                            """INSERT OR IGNORE INTO qb_layer_objects
                               (kind,application_name,object_name,catalog,schema_name,created_at)
                               VALUES (?,?,?,?,?,?)""",(kind,app,name,catalog,schema,now()),
                        )
                        oid=conn.execute(
                            """SELECT id FROM qb_layer_objects WHERE kind=? AND application_name=?
                               AND object_name=? AND catalog=? AND schema_name=?""",
                            (kind,app,name,catalog,schema),
                        ).fetchone()[0]
                        for position,(field,dtype,expression,description) in enumerate(fields,1):
                            conn.execute(
                                """INSERT OR IGNORE INTO qb_layer_fields
                                   (object_id,field_name,data_type,expression,description,ordinal_position)
                                   VALUES (?,?,?,?,?,?)""",(oid,field,dtype or None,expression,description,position),
                            )
                    audit(conn,"import_application_layer","layer_object",None,
                          {"objects":len(planned),"fields":sum(len(x[5]) for x in planned)})
                return jsonify({"ok":True,"objects":len(planned),
                                "fields":sum(len(x[5]) for x in planned)})
            finally:
                conn.close()
        except (ValueError,sqlite3.IntegrityError) as exc:
            return bad(str(exc))

    @bp.delete("/api/layers/objects/<int:object_id>")
    def delete_object(object_id):
        conn=db()
        try:
            ensure_schema(conn)
            with conn:
                row=conn.execute("SELECT id FROM qb_layer_objects WHERE id=?",(object_id,)).fetchone()
                if not row:
                    return bad("Object not found",404)
                conn.execute("DELETE FROM qb_layer_objects WHERE id=?",(object_id,))
                audit(conn,"delete_layer_object","layer_object",object_id,{})
            return jsonify({"ok":True})
        finally:
            conn.close()
