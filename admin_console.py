"""Administration of QueryBridge's LOCAL schema metadata.

This UI never opens a Databricks connection or alters physical Databricks tables.
It edits only qb_tables, qb_columns and qb_relationships in local SQLite.
"""
from __future__ import annotations

import hmac
import json
import re
import secrets
from pathlib import Path

from flask import Blueprint, jsonify, make_response, render_template, request, send_file
from sap_links_import import plan_import, apply_import

bp = Blueprint("admin", __name__, url_prefix="/admin")
ADMIN_CSRF_COOKIE = "qb_admin_csrf"
_db = None
_now = None

TABLE_COLUMNS = ("catalog", "schema_name", "table_name", "application_name", "description", "table_type")
FIELD_COLUMNS = ("column_name", "data_type", "nullable", "comment", "ordinal_position")


def create_admin_blueprint(db_func, now_func):
    global _db, _now
    _db, _now = db_func, now_func
    return bp


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def clean_text(value, name, max_length=200, required=False):
    if value is not None and not isinstance(value, str):
        raise ValueError(name + " must be text.")
    text = (value or "").strip()
    if required and not text:
        raise ValueError(name + " is required.")
    if len(text) > max_length or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError(f"{name} contains invalid characters or is too long (max {max_length}).")
    return text


def optional(value, name, length=200):
    return clean_text(value, name, length) or None


def nullable_choice(value):
    if value is None or value == "":
        return None
    if value in (True, 1, "1"):
        return 1
    if value in (False, 0, "0"):
        return 0
    raise ValueError("Nullable must be Yes, No or Unknown.")


def identity_exists(conn, data, exclude=None):
    return conn.execute(
        """SELECT id FROM qb_tables
           WHERE lower(coalesce(catalog,'')) = lower(coalesce(?, ''))
             AND lower(coalesce(schema_name,'')) = lower(coalesce(?, ''))
             AND lower(table_name) = lower(?)
             AND (? IS NULL OR id != ?)""",
        (data["catalog"], data["schema_name"], data["table_name"], exclude, exclude),
    ).fetchone() is not None


def field_exists(conn, table_id, name, exclude=None):
    return conn.execute(
        """SELECT id FROM qb_columns WHERE table_id=?
           AND lower(column_name)=lower(?)
           AND (? IS NULL OR id != ?)""",
        (table_id, name, exclude, exclude),
    ).fetchone() is not None


def log_change(conn, action, entity, identifier, before=None, after=None):
    conn.execute(
        """INSERT INTO qb_admin_audit(action, entity_type, entity_id, before_json, after_json, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            action, entity, identifier,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            _now(),
        ),
    )


@bp.before_request
def guard():
    # A double-submit cookie ties the CSRF header to the same browser without
    # requiring Flask sessions or a shared secret between server workers.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("X-CSRF-Token", "")
        cookie_token = request.cookies.get(ADMIN_CSRF_COOKIE, "")
        if not supplied or not cookie_token or not hmac.compare_digest(supplied, cookie_token):
            return error("Invalid administration security token. Reload Admin and retry.", 403)
        # A cross-site page cannot read our CSRF token or send the custom
        # header without CORS, and explicit cross-origin headers are rejected.
        site = request.headers.get("Sec-Fetch-Site")
        if site and site != "same-origin":
            return error("Cross-origin administration changes are not allowed.", 403)
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/").lower() != request.host_url.rstrip("/").lower():
            return error("Cross-origin administration changes are not allowed.", 403)
    return None


@bp.get("")
@bp.get("/")
def dashboard():
    # Reuse the cookie so multiple Admin tabs remain usable. Set the cookie
    # under the forwarded UDA prefix, matching the proxied API request path.
    token = request.cookies.get(ADMIN_CSRF_COOKIE)
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{40,64}", token):
        token = secrets.token_urlsafe(32)
    response = make_response(render_template("admin.html", csrf_token=token))
    response.set_cookie(
        ADMIN_CSRF_COOKIE,
        token,
        path=f"{request.script_root.rstrip('/')}/",
        secure=request.is_secure,
        httponly=True,
        samesite="Lax",
    )
    return response


@bp.get("/api/sap-links/template")
def sap_links_template():
    return send_file(
        Path(__file__).resolve().parent / "samples" / "sap_s4hana_links_template.json",
        mimetype="application/json",
        as_attachment=True,
        download_name="sap_s4hana_links_template.json",
    )


@bp.post("/api/sap-links/preview")
def preview_sap_links():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("document"), dict):
        return error("Select a valid SAP relationships JSON file.")
    conn = _db()
    try:
        preview = plan_import(conn, payload["document"])
        return jsonify({"ok": True, "preview": preview})
    except (ValueError, TypeError) as exc:
        return error(str(exc))
    finally:
        conn.close()


@bp.post("/api/sap-links/apply")
def import_sap_links():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("document"), dict):
        return error("Select a valid SAP relationships JSON file.")
    if payload.get("confirm") is not True:
        return error("Confirm the import after reviewing the preview.")
    conn = _db()
    try:
        with conn:
            preview = apply_import(conn, payload["document"], _now())
            log_change(
                conn, "import_sap_links", "sap_import", None,
                after={"application": preview["application"], "counts": preview["counts"]},
            )
        return jsonify({"ok": True, "result": preview})
    except (ValueError, TypeError) as exc:
        return error(str(exc))
    except Exception:
        return error("SAP import was rolled back because the database rejected it.", 409)
    finally:
        conn.close()


@bp.get("/api/overview")
def overview():
    conn = _db()
    try:
        tables = [
            dict(row) for row in conn.execute(
                """SELECT t.id, t.catalog, t.schema_name, t.table_name, t.application_name,
                          t.table_type, COUNT(DISTINCT c.id) AS field_count,
                          COUNT(DISTINCT r.id) AS join_count
                   FROM qb_tables t
                   LEFT JOIN qb_columns c ON c.table_id=t.id
                   LEFT JOIN qb_relationships r
                     ON r.left_table_id=t.id OR r.right_table_id=t.id
                   GROUP BY t.id
                   ORDER BY coalesce(t.application_name, ''), coalesce(t.catalog, ''),
                            coalesce(t.schema_name, ''), t.table_name"""
            )
        ]
        stats = {
            name: conn.execute(f"SELECT COUNT(*) FROM {db_table}").fetchone()[0]
            for name, db_table in (
                ("tables", "qb_tables"), ("fields", "qb_columns"),
                ("joins", "qb_relationships"), ("snapshots", "qb_schema_snapshots"),
                ("knowledge", "qb_knowledge"),
            )
        }
        audit = [dict(row) for row in conn.execute(
            """SELECT id, action, entity_type, entity_id, created_at
               FROM qb_admin_audit ORDER BY id DESC LIMIT 25"""
        )]
        return jsonify({"ok": True, "stats": stats, "tables": tables, "audit": audit})
    finally:
        conn.close()


@bp.get("/api/tables/<int:table_id>")
def table_details(table_id):
    conn = _db()
    try:
        table = conn.execute(
            """SELECT id, catalog, schema_name, table_name, application_name, description, table_type
               FROM qb_tables WHERE id=?""", (table_id,)
        ).fetchone()
        if table is None:
            return error("Table not found.", 404)
        fields = [dict(row) for row in conn.execute(
            """SELECT c.id, c.ordinal_position, c.column_name, c.data_type,
                      c.nullable, c.comment, COUNT(r.id) AS join_count
               FROM qb_columns c
               LEFT JOIN qb_relationships r
                 ON r.left_column_id=c.id OR r.right_column_id=c.id
               WHERE c.table_id=?
               GROUP BY c.id ORDER BY c.ordinal_position, c.id""", (table_id,)
        )]
        joins = [dict(row) for row in conn.execute(
            """SELECT r.id, r.source, r.confidence, r.notes,
                      r.left_column_id, r.right_column_id,
                      lt.table_name AS left_table, lc.column_name AS left_field,
                      rt.table_name AS right_table, rc.column_name AS right_field
               FROM qb_relationships r
               JOIN qb_tables lt ON lt.id=r.left_table_id
               JOIN qb_columns lc ON lc.id=r.left_column_id
               JOIN qb_tables rt ON rt.id=r.right_table_id
               JOIN qb_columns rc ON rc.id=r.right_column_id
               WHERE r.left_table_id=? OR r.right_table_id=?
               ORDER BY r.id""", (table_id, table_id)
        )]
        return jsonify({"ok": True, "table": dict(table), "fields": fields, "joins": joins})
    finally:
        conn.close()


def table_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Provide a table object.")
    return {
        "catalog": optional(payload.get("catalog"), "Catalog"),
        "schema_name": optional(payload.get("schema_name"), "Schema"),
        "table_name": clean_text(payload.get("table_name"), "Table name", required=True),
        "application_name": optional(payload.get("application_name"), "Application", 120),
        "description": optional(payload.get("description"), "Table description", 1000),
        "table_type": optional(payload.get("table_type"), "Table type", 100),
    }


def field_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Provide a field object.")
    position = payload.get("ordinal_position")
    if position is not None and position != "":
        try:
            position = int(position)
        except (ValueError, TypeError):
            raise ValueError("Position must be a positive integer.") from None
        if position < 1 or position > 1000000:
            raise ValueError("Position must be from 1 to 1000000.")
    else:
        position = None
    return {
        "column_name": clean_text(payload.get("column_name"), "Field name", required=True),
        "data_type": optional(payload.get("data_type"), "Data type", 255),
        "nullable": nullable_choice(payload.get("nullable")),
        "comment": optional(payload.get("comment"), "Description", 4000),
        "ordinal_position": position,
    }


def perform_change(conn, action, data):
    if action in ("create_table", "update_table"):
        values = table_payload(data)
        table_id = data.get("id") if action == "update_table" else None
        old = None
        if table_id is not None:
            old_row = conn.execute("SELECT * FROM qb_tables WHERE id=?", (table_id,)).fetchone()
            if not old_row:
                raise ValueError("Table not found.")
            old = {key: old_row[key] for key in TABLE_COLUMNS}
        if identity_exists(conn, values, table_id):
            raise ValueError("A table already exists with this catalog, schema and name.")
        if action == "create_table":
            cur = conn.execute(
                """INSERT INTO qb_tables
                   (catalog,schema_name,table_name,application_name,description,table_type,captured_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (*[values[k] for k in TABLE_COLUMNS], _now()),
            )
            table_id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE qb_tables SET catalog=?,schema_name=?,table_name=?,
                   application_name=?,description=?,table_type=? WHERE id=?""",
                (*[values[k] for k in TABLE_COLUMNS], table_id),
            )
        log_change(conn, action, "table", table_id, old, values)
        return table_id

    if action == "delete_table":
        table_id = data.get("id")
        row = conn.execute("SELECT * FROM qb_tables WHERE id=?", (table_id,)).fetchone()
        if not row:
            raise ValueError("Table not found.")
        if data.get("confirm_name") != row["table_name"] or data.get("acknowledge_impact") is not True:
            raise ValueError("Confirm the exact table name and acknowledge affected fields and joins.")
        before = {k: row[k] for k in TABLE_COLUMNS}
        before["fields_removed"] = conn.execute("SELECT COUNT(*) FROM qb_columns WHERE table_id=?", (table_id,)).fetchone()[0]
        before["joins_removed"] = conn.execute(
            "SELECT COUNT(*) FROM qb_relationships WHERE left_table_id=? OR right_table_id=?",
            (table_id, table_id),
        ).fetchone()[0]
        conn.execute("DELETE FROM qb_tables WHERE id=?", (table_id,))
        log_change(conn, action, "table", table_id, before)
        return table_id

    if action in ("create_field", "update_field"):
        values = field_payload(data)
        old = None
        if action == "create_field":
            table_id = data.get("table_id")
            if not conn.execute("SELECT id FROM qb_tables WHERE id=?", (table_id,)).fetchone():
                raise ValueError("Table not found.")
            field_id = None
        else:
            field_id = data.get("id")
            old_row = conn.execute("SELECT * FROM qb_columns WHERE id=?", (field_id,)).fetchone()
            if not old_row:
                raise ValueError("Field not found.")
            table_id = old_row["table_id"]
            old = {key: old_row[key] for key in FIELD_COLUMNS}
        if field_exists(conn, table_id, values["column_name"], field_id):
            raise ValueError("A field already exists with that name in this table.")
        if values["ordinal_position"] is None:
            values["ordinal_position"] = (
                conn.execute(
                    "SELECT coalesce(MAX(ordinal_position),0)+1 FROM qb_columns WHERE table_id=?",
                    (table_id,),
                ).fetchone()[0]
                if action == "create_field" else old["ordinal_position"]
            )
        if action == "create_field":
            cur = conn.execute(
                """INSERT INTO qb_columns
                   (table_id,column_name,data_type,nullable,comment,ordinal_position)
                   VALUES (?,?,?,?,?,?)""",
                (table_id, *[values[k] for k in FIELD_COLUMNS]),
            )
            field_id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE qb_columns SET column_name=?,data_type=?,nullable=?,
                   comment=?,ordinal_position=? WHERE id=?""",
                (*[values[k] for k in FIELD_COLUMNS], field_id),
            )
        log_change(conn, action, "field", field_id, old, {"table_id": table_id, **values})
        return table_id

    if action == "delete_field":
        field_id = data.get("id")
        row = conn.execute("SELECT * FROM qb_columns WHERE id=?", (field_id,)).fetchone()
        if not row:
            raise ValueError("Field not found.")
        if data.get("confirm_name") != row["column_name"] or data.get("acknowledge_impact") is not True:
            raise ValueError("Confirm the exact field name and acknowledge affected joins.")
        before = {k: row[k] for k in FIELD_COLUMNS}
        before["joins_removed"] = conn.execute(
            "SELECT COUNT(*) FROM qb_relationships WHERE left_column_id=? OR right_column_id=?",
            (field_id, field_id),
        ).fetchone()[0]
        conn.execute("DELETE FROM qb_columns WHERE id=?", (field_id,))
        log_change(conn, action, "field", field_id, before)
        return row["table_id"]

    if action == "create_join":
        left = conn.execute("SELECT id, table_id FROM qb_columns WHERE id=?", (data.get("left_column_id"),)).fetchone()
        right = conn.execute("SELECT id, table_id FROM qb_columns WHERE id=?", (data.get("right_column_id"),)).fetchone()
        if not left or not right:
            raise ValueError("Both join fields must exist.")
        if left["table_id"] == right["table_id"]:
            raise ValueError("Join fields must belong to different tables.")
        duplicate = conn.execute(
            """SELECT id FROM qb_relationships
               WHERE (left_column_id=? AND right_column_id=?)
                  OR (left_column_id=? AND right_column_id=?)""",
            (left["id"], right["id"], right["id"], left["id"]),
        ).fetchone()
        if duplicate:
            raise ValueError("That relationship already exists.")
        notes = optional(data.get("notes"), "Join notes", 2000)
        cur = conn.execute(
            """INSERT INTO qb_relationships
               (left_table_id,left_column_id,right_table_id,right_column_id,
                confidence,source,notes) VALUES (?,?,?,?,1,'manual',?)""",
            (left["table_id"], left["id"], right["table_id"], right["id"], notes),
        )
        log_change(conn, action, "join", cur.lastrowid, None, {
            "left_column_id": left["id"], "right_column_id": right["id"], "notes": notes,
            "source": "manual", "confidence": 1,
        })
        return left["table_id"]

    if action == "delete_join":
        row = conn.execute("SELECT * FROM qb_relationships WHERE id=?", (data.get("id"),)).fetchone()
        if not row:
            raise ValueError("Join not found.")
        if data.get("confirm") is not True:
            raise ValueError("Deletion confirmation is required.")
        before = {
            k: row[k] for k in (
                "left_table_id", "left_column_id", "right_table_id", "right_column_id",
                "source", "confidence", "notes",
            )
        }
        conn.execute("DELETE FROM qb_relationships WHERE id=?", (row["id"],))
        log_change(conn, action, "join", row["id"], before)
        return row["left_table_id"]

    raise ValueError("Unsupported administration action.")


@bp.post("/api/change")
def change():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return error("Expected an action and data object.")
    action = payload.get("action")
    conn = _db()
    try:
        with conn:
            affected_id = perform_change(conn, action, payload["data"])
        return jsonify({"ok": True, "table_id": affected_id})
    except (ValueError, TypeError) as exc:
        return error(str(exc))
    except Exception:
        # No SQL exception internals should leak to a browser.
        return error("Database rejected the change. Check for duplicate names or conflicting links.", 409)
    finally:
        conn.close()
