"""Controlled, audited record editor for QueryBridge's own local SQLite metadata.

Never connects to Databricks or source applications. Routes live on the existing
Admin blueprint so all mutations inherit its CSRF/origin guard.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from flask import jsonify, make_response, render_template, request

EDITABLE = frozenset({
    "qb_tables", "qb_columns", "qb_relationships", "qb_knowledge",
    "qb_layer_objects", "qb_layer_fields", "qb_layer_lineage",
    "qb_schema_snapshots", "qb_saved_queries",
})
MAX_PAGE_SIZE = 50
MAX_CELL_SIZE = 200_000


def quote(name):
    # Only identifiers obtained from SQLite introspection / fixed allowlist.
    return '"' + name.replace('"', '""') + '"'


def columns(conn, table):
    if table not in EDITABLE:
        raise ValueError("This is not an editable QueryBridge metadata table.")
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not existing:
        raise ValueError("This local table has not been created.")
    info = [dict(row) for row in conn.execute(f"PRAGMA table_info({quote(table)})")]
    if not any(c["name"] == "id" and c["pk"] for c in info):
        raise ValueError("The table has no supported id primary key.")
    return info


def row_to_json(row):
    return {key: value for key, value in dict(row).items()}


def signature(record):
    packed = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def checked_values(data, info, create=False):
    if not isinstance(data, dict) or not data:
        raise ValueError("Supply fields to change.")
    valid = {column["name"]: column for column in info if column["name"] != "id" and
             not column["hidden"]} if all("hidden" in c for c in info) else {
             column["name"]: column for column in info if column["name"] != "id"}
    if any(key not in valid for key in data):
        raise ValueError("Unknown or protected column supplied.")
    result = {}
    for key, value in data.items():
        col = valid[key]
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"{key}: enter a scalar value or null.")
        if isinstance(value, str) and (len(value.encode("utf-8")) > MAX_CELL_SIZE or "\x00" in value):
            raise ValueError(f"{key}: exceeds maximum text size or contains a NUL byte.")
        if isinstance(value, bool):
            value = int(value)
        # Use SQLite type affinity, so a numeric input does not accidentally
        # become a text value for INTEGER / REAL columns.
        affinity = (col["type"] or "").upper()
        if value is not None and "INT" in affinity:
            if isinstance(value, float) and not value.is_integer():
                raise ValueError(f"{key}: expected an integer.")
            try:
                if isinstance(value,str) and not re.fullmatch(r"[+-]?\d+",value.strip()):
                    raise ValueError()
                value = int(value)
            except (ValueError, OverflowError):
                raise ValueError(f"{key}: expected an integer.") from None
        elif value is not None and any(x in affinity for x in ("REAL", "FLOA", "DOUB")):
            try:
                value = float(value)
            except (ValueError, TypeError):
                raise ValueError(f"{key}: expected a number.") from None
        result[key] = value
    return result


def install(bp, db, now, csrf_cookie):
    def failure(error, status=400):
        return jsonify({"ok": False, "error": str(error)}), status

    def log(conn, action, table, identifier, before, after):
        conn.execute(
            """INSERT INTO qb_admin_audit
               (action,entity_type,entity_id,before_json,after_json,created_at)
               VALUES(?,?,?,?,?,?)""",
            (action, f"data:{table}", identifier,
             json.dumps(before, ensure_ascii=False) if before is not None else None,
             json.dumps(after, ensure_ascii=False) if after is not None else None, now()),
        )

    @bp.get("/data-tables")
    def data_tables_page():
        # Reuse Admin CSRF cookie, including when landing here without visiting Admin.
        import secrets
        token = request.cookies.get(csrf_cookie)
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]{40,64}", token):
            token = secrets.token_urlsafe(32)
        response = make_response(render_template("data_tables.html", csrf_token=token))
        response.set_cookie(
            csrf_cookie, token, path=f"{request.script_root.rstrip('/')}/",
            httponly=True, samesite="Lax", secure=request.is_secure,
        )
        return response

    @bp.get("/api/data-tables")
    def list_data_tables():
        conn = db()
        try:
            tables = []
            for name in sorted(EDITABLE):
                try:
                    info = columns(conn, name)
                except ValueError:
                    continue
                count = conn.execute(f"SELECT COUNT(*) FROM {quote(name)}").fetchone()[0]
                tables.append({"name": name, "count": count, "columns": len(info)})
            return jsonify({"ok": True, "tables": tables})
        finally:
            conn.close()

    @bp.get("/api/data-tables/<table>")
    def list_data_rows(table):
        conn = db()
        try:
            info = columns(conn, table)
            try:
                page = int(request.args.get("page", "1"))
                if page < 1 or page > 1000000:
                    raise ValueError()
            except ValueError:
                return failure("Invalid page.")
            search = (request.args.get("q") or "").strip()
            if len(search) > 200:
                return failure("Search text is too long.")
            text_cols = [c["name"] for c in info if c["name"] != "id"]
            where, args = "", []
            if search and text_cols:
                where = " WHERE " + " OR ".join(
                    f"CAST({quote(c)} AS TEXT) LIKE ? ESCAPE '\\'" for c in text_cols
                )
                escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                args = [f"%{escaped}%"] * len(text_cols)
            total = conn.execute(f"SELECT COUNT(*) FROM {quote(table)}{where}", args).fetchone()[0]
            rows = [
                {"values":row_to_json(r), "version":signature(row_to_json(r))}
                for r in conn.execute(
                    f"SELECT * FROM {quote(table)}{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                    (*args, MAX_PAGE_SIZE, (page - 1) * MAX_PAGE_SIZE),
                )
            ]
            return jsonify({"ok":True,"table":table,"columns":info,"rows":rows,
                            "total":total,"page":page,"page_size":MAX_PAGE_SIZE})
        except ValueError as exc:
            return failure(exc, 404)
        finally:
            conn.close()

    @bp.post("/api/data-tables/<table>")
    def create_data_row(table):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            return failure("Confirm the record creation.")
        conn = db()
        try:
            info = columns(conn, table)
            values = checked_values(payload.get("values"), info, create=True)
            names = list(values)
            with conn:
                result = conn.execute(
                    f"INSERT INTO {quote(table)} ({','.join(quote(x) for x in names)}) "
                    f"VALUES ({','.join('?' for _ in names)})",
                    [values[x] for x in names],
                )
                row = conn.execute(f"SELECT * FROM {quote(table)} WHERE id=?",
                                   (result.lastrowid,)).fetchone()
                log(conn, "data_record_create", table, result.lastrowid, None, row_to_json(row))
            return jsonify({"ok":True,"id":result.lastrowid}), 201
        except ValueError as exc:
            return failure(exc)
        except sqlite3.Error:
            return failure("Record rejected by database constraints; no changes saved.", 409)
        finally:
            conn.close()

    @bp.patch("/api/data-tables/<table>/<int:record_id>")
    def update_data_row(table, record_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            return failure("Confirm the record update.")
        if not isinstance(payload.get("version"),str):
            return failure("Missing record version; reload before editing.")
        conn = db()
        try:
            info = columns(conn, table)
            values = checked_values(payload.get("values"), info)
            with conn:
                prior = conn.execute(
                    f"SELECT * FROM {quote(table)} WHERE id=?", (record_id,)
                ).fetchone()
                if prior is None:
                    return failure("Record not found.",404)
                before = row_to_json(prior)
                if signature(before) != payload["version"]:
                    return failure("Record changed since it was loaded. Reload and review before saving.",409)
                conn.execute(
                    f"UPDATE {quote(table)} SET " +
                    ", ".join(f"{quote(k)}=?" for k in values) + " WHERE id=?",
                    [*values.values(),record_id],
                )
                after = row_to_json(conn.execute(
                    f"SELECT * FROM {quote(table)} WHERE id=?", (record_id,)
                ).fetchone())
                log(conn, "data_record_update", table, record_id, before, after)
            return jsonify({"ok": True, "version": signature(after)})
        except ValueError as exc:
            return failure(exc)
        except sqlite3.Error:
            return failure("Update rejected by database constraints; no changes saved.",409)
        finally:
            conn.close()

    @bp.delete("/api/data-tables/<table>/<int:record_id>")
    def delete_data_row(table, record_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            return failure("Confirm record deletion.")
        if not isinstance(payload.get("version"),str):
            return failure("Missing record version; reload before deleting.")
        conn = db()
        try:
            columns(conn, table)
            with conn:
                old = conn.execute(
                    f"SELECT * FROM {quote(table)} WHERE id=?", (record_id,)
                ).fetchone()
                if old is None:
                    return failure("Record not found.",404)
                before = row_to_json(old)
                if signature(before) != payload["version"]:
                    return failure("Record changed; reload before deleting.",409)
                # Do not silently cascade-delete dependent records. SQLite FK
                # cascades can otherwise remove large portions of a dictionary.
                child = conn.execute(f"SELECT 1 FROM {quote(table)} WHERE id=?",(record_id,)).fetchone()
                assert child
                conn.execute(f"DELETE FROM {quote(table)} WHERE id=?", (record_id,))
                log(conn,"data_record_delete",table,record_id,before,None)
            return jsonify({"ok": True})
        except ValueError as exc:
            return failure(exc)
        except sqlite3.Error:
            return failure("Delete blocked by database constraints; no changes saved.",409)
        finally:
            conn.close()
