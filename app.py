from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import time
import requests
import markdown as markdown_lib
import sqlglot
from sqlglot import exp
from markupsafe import Markup, escape
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "querybridge.db"

app = Flask(__name__)
app.secret_key = "querybridge-local-dev"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS qb_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog TEXT,
            schema_name TEXT,
            table_name TEXT NOT NULL,
            table_type TEXT,
            is_temporary INTEGER DEFAULT 0,
            raw_source TEXT,
            captured_at TEXT NOT NULL,
            UNIQUE(catalog, schema_name, table_name)
        );

        CREATE TABLE IF NOT EXISTS qb_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL REFERENCES qb_tables(id) ON DELETE CASCADE,
            ordinal_position INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            data_type TEXT,
            nullable INTEGER,
            comment TEXT,
            raw_json TEXT,
            UNIQUE(table_id, column_name)
        );

        CREATE TABLE IF NOT EXISTS qb_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_type TEXT NOT NULL,
            table_id INTEGER REFERENCES qb_tables(id) ON DELETE SET NULL,
            source_sql TEXT,
            raw_text TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            left_table_id INTEGER NOT NULL REFERENCES qb_tables(id) ON DELETE CASCADE,
            left_column_id INTEGER NOT NULL REFERENCES qb_columns(id) ON DELETE CASCADE,
            right_table_id INTEGER NOT NULL REFERENCES qb_tables(id) ON DELETE CASCADE,
            right_column_id INTEGER NOT NULL REFERENCES qb_columns(id) ON DELETE CASCADE,
            confidence REAL NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'auto',
            UNIQUE(left_column_id, right_column_id)
        );

        CREATE TABLE IF NOT EXISTS qb_saved_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            query_json TEXT NOT NULL,
            sql_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_schema_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_llm_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            provider TEXT NOT NULL DEFAULT 'ollama',
            base_url TEXT NOT NULL DEFAULT 'http://localhost:11434',
            model TEXT NOT NULL DEFAULT '',
            temperature REAL NOT NULL DEFAULT 0.2,
            timeout_seconds INTEGER NOT NULL DEFAULT 120,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_ai_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            instructions TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            builtin INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qb_schema_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT,
            skill_key TEXT,
            model TEXT,
            operations_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS qb_relationship_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            auto_inference_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )
    relationship_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(qb_relationships)").fetchall()
    }
    if "notes" not in relationship_columns:
        conn.execute("ALTER TABLE qb_relationships ADD COLUMN notes TEXT")

    conn.execute(
        """
        INSERT OR IGNORE INTO qb_llm_settings
        (id, provider, base_url, model, temperature, timeout_seconds, updated_at)
        VALUES (1, 'ollama', 'http://localhost:11434', '', 0.2, 120, ?)
        """,
        (now_iso(),),
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO qb_relationship_settings
        (id, auto_inference_enabled, updated_at)
        VALUES (1, 0, ?)
        """,
        (now_iso(),),
    )

    builtin_skills = [
        (
            "relationship-analysis",
            "Relationship analysis",
            "Find plausible joins between captured tables using schema metadata and knowledge.",
            "Propose only equality relationships between real captured fields. Prefer explicit business keys, documented identifiers and knowledge-backed rules. Include confidence and a concise reason. Do not apply changes directly.",
        ),
        (
            "schema-curator",
            "Schema curator",
            "Propose reviewable structural improvements to the local QueryBridge schema model.",
            "You may propose add_table, remove_table, rename_table, add_field, remove_field, rename_field, change_field_type and set_field_nullable operations. Never invent a destructive change without explaining why. Treat the captured schema as metadata, not the live Databricks database.",
        ),
        (
            "field-type-review",
            "Field type review",
            "Review field names, comments and business knowledge for likely type or nullability corrections.",
            "Prefer conservative type corrections. Only propose change_field_type or set_field_nullable when evidence is strong. Preserve the original field unless the requested change materially improves the local model.",
        ),
        (
            "knowledge-grounded-schema",
            "Knowledge-grounded schema reasoning",
            "Use Markdown knowledge, package notes and source-authority rules to improve schema understanding.",
            "Ground every proposal in the supplied schema or knowledge. If evidence is insufficient, return no operation rather than guessing. Relationship hints in knowledge may justify add_relationship proposals.",
        ),
        (
            "local-schema-sql-analysis",
            "Local Schema SQL Analysis",
            "Run read-only SELECT statements against QueryBridge's local captured schema metadata to analyse tables, fields, relationships and knowledge.",
            "Use the local_schema_select tool whenever a SQL query over the locally stored schema would give a more precise answer. Query only schema_tables, schema_fields, schema_relationships and schema_knowledge. You may JOIN, GROUP BY, aggregate, filter and use CTEs. This tool never connects to Databricks and never queries live business data.",
        ),
    ]
    for skill_key, name, description, instructions in builtin_skills:
        conn.execute(
            """
            INSERT OR IGNORE INTO qb_ai_skills
            (skill_key, name, description, instructions, enabled, builtin, updated_at)
            VALUES (?, ?, ?, ?, 1, 1, ?)
            """,
            (skill_key, name, description, instructions, now_iso()),
        )
        conn.execute(
            """
            UPDATE qb_ai_skills
            SET name = ?, description = ?
            WHERE skill_key = ? AND builtin = 1
            """,
            (name, description, skill_key),
        )

    conn.commit()
    conn.close()


def quote_ident(value: str) -> str:
    tick = chr(96)
    return tick + value.replace(tick, tick + tick) + tick


def qualified_name(row) -> str:
    parts = []
    if row["catalog"]:
        parts.append(quote_ident(row["catalog"]))
    if row["schema_name"]:
        parts.append(quote_ident(row["schema_name"]))
    parts.append(quote_ident(row["table_name"]))
    return ".".join(parts)


def parse_bool(value) -> int:
    return 1 if str(value).strip().lower() in {"true", "1", "yes", "y"} else 0


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def parse_grid(text: str):
    text = text.strip()
    if not text:
        return []

    lines = [line for line in text.splitlines() if line.strip()]
    sample = "\n".join(lines[:10])

    delimiter = None
    if "\t" in sample:
        delimiter = "\t"
    elif "," in sample:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;|").delimiter
        except csv.Error:
            delimiter = ","
    elif "|" in sample:
        delimiter = "|"

    if delimiter:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
    else:
        rows = [re.split(r"\s{2,}", line.strip()) for line in lines]

    if not rows:
        return []

    headers = [normalize_header(x) for x in rows[0]]
    result = []
    for values in rows[1:]:
        if not any(str(v).strip() for v in values):
            continue
        values = list(values) + [""] * max(0, len(headers) - len(values))
        result.append({headers[i]: values[i].strip() for i in range(len(headers))})
    return result


def row_value(row, *names):
    for name in names:
        key = normalize_header(name)
        if key in row and row[key] != "":
            return row[key]
    return None


def type_json_to_sql(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    name = str(value.get("name", "unknown")).upper()

    if name in {"DECIMAL", "NUMERIC"}:
        p = value.get("precision")
        s = value.get("scale")
        return f"{name}({p},{s})" if p is not None and s is not None else name
    if name in {"VARCHAR", "CHAR"} and value.get("length") is not None:
        return f"{name}({value['length']})"
    if name == "ARRAY" and "element_type" in value:
        return f"ARRAY<{type_json_to_sql(value['element_type'])}>"
    if name == "MAP" and "key_type" in value and "value_type" in value:
        return f"MAP<{type_json_to_sql(value['key_type'])},{type_json_to_sql(value['value_type'])}>"
    if name == "STRUCT" and isinstance(value.get("fields"), list):
        fields = []
        for field in value["fields"]:
            fields.append(f"{field.get('name')}:{type_json_to_sql(field.get('type'))}")
        return "STRUCT<" + ",".join(fields) + ">"
    return name


def extract_json_object(text: str):
    cleaned = text.strip()

    # Direct JSON first.
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, str):
            return json.loads(obj)
    except Exception:
        pass

    # Databricks grid copies can include a column heading around the JSON cell.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Sometimes the grid copy escapes the JSON cell.
            try:
                return json.loads(bytes(candidate, "utf-8").decode("unicode_escape"))
            except Exception:
                pass
    return None


def auto_relationship_inference_enabled(conn):
    row = conn.execute(
        "SELECT auto_inference_enabled FROM qb_relationship_settings WHERE id = 1"
    ).fetchone()
    return bool(row and row["auto_inference_enabled"])


def infer_relationships(conn, force=False):
    if not force and not auto_relationship_inference_enabled(conn):
        return 0

    conn.execute("DELETE FROM qb_relationships WHERE source = 'auto'")
    inserted = 0
    columns = conn.execute(
        """
        SELECT c.id column_id, c.table_id, lower(c.column_name) column_key,
               c.column_name, t.table_name
        FROM qb_columns c
        JOIN qb_tables t ON t.id = c.table_id
        """
    ).fetchall()

    by_name = {}
    for col in columns:
        by_name.setdefault(col["column_key"], []).append(col)

    generic = {"id", "name", "date", "type", "status", "description", "comment", "value"}
    seen = set()

    for key, group in by_name.items():
        if len(group) < 2 or key in generic:
            continue
        key_like = key.endswith(("_id", "_key", "_number", "_no", "_code")) or key.startswith(("id_", "key_"))
        confidence = 0.92 if key_like else 0.72
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                if left["table_id"] == right["table_id"]:
                    continue
                pair = tuple(sorted((left["column_id"], right["column_id"])))
                if pair in seen:
                    continue
                seen.add(pair)
                if left["column_id"] <= right["column_id"]:
                    lc, rc = left, right
                else:
                    lc, rc = right, left
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO qb_relationships
                    (left_table_id, left_column_id, right_table_id, right_column_id, confidence, source)
                    VALUES (?, ?, ?, ?, ?, 'auto')
                    """,
                    (lc["table_id"], lc["column_id"], rc["table_id"], rc["column_id"], confidence),
                )
                inserted += cursor.rowcount

    return inserted





def render_markdown_html(content):
    """Render Markdown safely, including GitHub-style tables and fenced code."""
    safe_source = str(escape(content or ""))
    rendered = markdown_lib.markdown(
        safe_source,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    return Markup(rendered)


def ai_skill_rows(conn, enabled_only=False):
    sql = """
        SELECT id, skill_key, name, description, instructions, enabled, builtin, updated_at
        FROM qb_ai_skills
    """
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY builtin DESC, name"
    return conn.execute(sql).fetchall()


def ai_skill_context(skills):
    return "\n\n".join(
        f"SKILL: {row['name']} ({row['skill_key']})\n"
        f"PURPOSE: {row['description']}\n"
        f"INSTRUCTIONS: {row['instructions']}"
        for row in skills
    )


def resolve_table(conn, table_name, schema_name=None, catalog=None):
    if not table_name:
        return None
    sql = "SELECT * FROM qb_tables WHERE lower(table_name) = lower(?)"
    params = [table_name]
    if schema_name:
        sql += " AND lower(COALESCE(schema_name,'')) = lower(?)"
        params.append(schema_name)
    if catalog:
        sql += " AND lower(COALESCE(catalog,'')) = lower(?)"
        params.append(catalog)
    sql += " ORDER BY id LIMIT 1"
    return conn.execute(sql, params).fetchone()


def resolve_column(conn, table_name, column_name, schema_name=None, catalog=None):
    if not table_name or not column_name:
        return None
    return find_column(conn, table_name, column_name, schema_name, catalog)


def operation_reason(operation):
    return str(operation.get("reason") or "").strip()[:2000]


def validate_schema_operations(conn, operations):
    allowed = {
        "add_table",
        "remove_table",
        "rename_table",
        "add_field",
        "remove_field",
        "rename_field",
        "change_field_type",
        "set_field_nullable",
        "add_relationship",
        "remove_relationship",
    }
    if not isinstance(operations, list):
        raise ValueError("AI proposal operations must be a list.")

    table_rows = conn.execute(
        "SELECT id, catalog, schema_name, table_name FROM qb_tables ORDER BY id"
    ).fetchall()
    tables = {}
    fields = {}
    for row in table_rows:
        key = (
            (row["catalog"] or "").casefold(),
            (row["schema_name"] or "").casefold(),
            row["table_name"].casefold(),
        )
        tables[key] = {
            "catalog": row["catalog"],
            "schema_name": row["schema_name"],
            "table_name": row["table_name"],
        }
        fields[key] = {
            value["column_name"].casefold()
            for value in conn.execute(
                "SELECT column_name FROM qb_columns WHERE table_id = ?",
                (row["id"],),
            ).fetchall()
        }

    relationships = set()
    relationship_rows = conn.execute(
        """
        SELECT
            lt.catalog left_catalog, lt.schema_name left_schema, lt.table_name left_table,
            lc.column_name left_column,
            rt.catalog right_catalog, rt.schema_name right_schema, rt.table_name right_table,
            rc.column_name right_column
        FROM qb_relationships r
        JOIN qb_tables lt ON lt.id = r.left_table_id
        JOIN qb_columns lc ON lc.id = r.left_column_id
        JOIN qb_tables rt ON rt.id = r.right_table_id
        JOIN qb_columns rc ON rc.id = r.right_column_id
        """
    ).fetchall()

    def table_key(catalog, schema_name, table_name):
        return (
            (catalog or "").casefold(),
            (schema_name or "").casefold(),
            (table_name or "").casefold(),
        )

    def resolve_state_table(table_name, schema_name=None, catalog=None):
        if not table_name:
            return None
        wanted_name = str(table_name).casefold()
        wanted_schema = None if schema_name in {None, ""} else str(schema_name).casefold()
        wanted_catalog = None if catalog in {None, ""} else str(catalog).casefold()
        candidates = [
            key for key in tables
            if key[2] == wanted_name
            and (wanted_schema is None or key[1] == wanted_schema)
            and (wanted_catalog is None or key[0] == wanted_catalog)
        ]
        return sorted(candidates)[0] if candidates else None

    def field_identity(table_key_value, column_name):
        return table_key_value + ((column_name or "").casefold(),)

    def relation_identity(left_identity, right_identity):
        return tuple(sorted((left_identity, right_identity)))

    for row in relationship_rows:
        left_table_key = table_key(
            row["left_catalog"], row["left_schema"], row["left_table"]
        )
        right_table_key = table_key(
            row["right_catalog"], row["right_schema"], row["right_table"]
        )
        relationships.add(
            relation_identity(
                field_identity(left_table_key, row["left_column"]),
                field_identity(right_table_key, row["right_column"]),
            )
        )

    checked = []

    for index, raw in enumerate(operations, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Operation {index} is not an object.")
        op = dict(raw)
        action = str(op.get("action") or "").strip()
        error = None
        if action not in allowed:
            raw_action = (
                op.get("action")
                or op.get("operation")
                or op.get("type")
                or op.get("op")
                or op.get("change")
                or "<missing>"
            )
            checked.append(
                {
                    "index": index,
                    "action": action or str(raw_action),
                    "operation": op,
                    "valid": False,
                    "error": f"unsupported action '{raw_action}'",
                }
            )
            continue

        if action == "add_table":
            name = str(op.get("table_name") or "").strip()
            key = table_key(op.get("catalog"), op.get("schema_name"), name)
            if not name:
                error = "table_name is required"
            elif key in tables:
                error = "table already exists"
            else:
                tables[key] = {
                    "catalog": op.get("catalog"),
                    "schema_name": op.get("schema_name"),
                    "table_name": name,
                }
                fields[key] = set()

        elif action in {"remove_table", "rename_table"}:
            key = resolve_state_table(
                op.get("table_name"), op.get("schema_name"), op.get("catalog")
            )
            if not key:
                error = "table does not exist"
            elif action == "remove_table":
                field_ids = {field_identity(key, field) for field in fields.get(key, set())}
                relationships = {
                    rel for rel in relationships
                    if rel[0] not in field_ids and rel[1] not in field_ids
                }
                tables.pop(key, None)
                fields.pop(key, None)
            else:
                new_name = str(op.get("new_name") or "").strip()
                new_key = table_key(key[0], key[1], new_name)
                if not new_name:
                    error = "new_name is required"
                elif new_key in tables:
                    error = "target table name already exists"
                else:
                    existing_fields = fields.pop(key, set())
                    table_value = tables.pop(key)
                    table_value["table_name"] = new_name
                    tables[new_key] = table_value
                    fields[new_key] = existing_fields
                    remapped = set()
                    for rel in relationships:
                        pair = []
                        for identity in rel:
                            if identity[:3] == key:
                                pair.append(new_key + (identity[3],))
                            else:
                                pair.append(identity)
                        remapped.add(relation_identity(pair[0], pair[1]))
                    relationships = remapped

        elif action in {
            "add_field",
            "remove_field",
            "rename_field",
            "change_field_type",
            "set_field_nullable",
        }:
            key = resolve_state_table(
                op.get("table_name"), op.get("schema_name"), op.get("catalog")
            )
            if not key:
                error = "table does not exist"
            else:
                column_name = str(op.get("column_name") or "").strip()
                column_key = column_name.casefold()
                exists = bool(column_name) and column_key in fields[key]

                if action == "add_field":
                    if not column_name:
                        error = "column_name is required"
                    elif exists:
                        error = "field already exists"
                    elif not str(op.get("data_type") or "").strip():
                        error = "data_type is required"
                    else:
                        fields[key].add(column_key)

                elif not exists:
                    error = "field does not exist"

                elif action == "remove_field":
                    identity = field_identity(key, column_name)
                    relationships = {
                        rel for rel in relationships
                        if identity not in rel
                    }
                    fields[key].discard(column_key)

                elif action == "rename_field":
                    new_name = str(op.get("new_name") or "").strip()
                    new_key = new_name.casefold()
                    if not new_name:
                        error = "new_name is required"
                    elif new_key in fields[key]:
                        error = "target field name already exists"
                    else:
                        fields[key].discard(column_key)
                        fields[key].add(new_key)
                        old_identity = field_identity(key, column_name)
                        new_identity = field_identity(key, new_name)
                        remapped = set()
                        for rel in relationships:
                            pair = [
                                new_identity if identity == old_identity else identity
                                for identity in rel
                            ]
                            remapped.add(relation_identity(pair[0], pair[1]))
                        relationships = remapped

                elif action == "change_field_type":
                    if not str(op.get("data_type") or "").strip():
                        error = "data_type is required"

                elif action == "set_field_nullable":
                    if "nullable" not in op:
                        error = "nullable is required"

        elif action in {"add_relationship", "remove_relationship"}:
            left_table_key = resolve_state_table(
                op.get("left_table"), op.get("left_schema"), op.get("left_catalog")
            )
            right_table_key = resolve_state_table(
                op.get("right_table"), op.get("right_schema"), op.get("right_catalog")
            )
            left_column = str(op.get("left_column") or "").strip()
            right_column = str(op.get("right_column") or "").strip()

            if (
                not left_table_key
                or not right_table_key
                or left_column.casefold() not in fields.get(left_table_key, set())
                or right_column.casefold() not in fields.get(right_table_key, set())
            ):
                error = "relationship fields do not both exist"
            elif left_table_key == right_table_key:
                error = "relationship must connect different tables"
            else:
                rel_key = relation_identity(
                    field_identity(left_table_key, left_column),
                    field_identity(right_table_key, right_column),
                )
                if action == "add_relationship":
                    if rel_key in relationships:
                        error = "relationship already exists"
                    else:
                        relationships.add(rel_key)
                else:
                    if rel_key not in relationships:
                        error = "relationship does not exist"
                    else:
                        relationships.discard(rel_key)

        checked.append(
            {
                "index": index,
                "action": action,
                "operation": op,
                "valid": error is None,
                "error": error,
            }
        )

    return checked

def apply_schema_operations(conn, operations):
    checked = validate_schema_operations(conn, operations)
    invalid = [item for item in checked if not item["valid"]]
    if invalid:
        details = "; ".join(
            f"#{item['index']} {item['action']}: {item['error']}" for item in invalid
        )
        raise ValueError(f"Schema proposal is no longer valid: {details}")

    applied = []

    for item in checked:
        op = item["operation"]
        action = item["action"]
        reason = operation_reason(op)

        if action == "add_table":
            conn.execute(
                """
                INSERT INTO qb_tables
                (catalog, schema_name, table_name, table_type, is_temporary, raw_source, captured_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    op.get("catalog"),
                    op.get("schema_name"),
                    str(op["table_name"]).strip(),
                    str(op.get("table_type") or "table").strip(),
                    json.dumps({"source": "ai-approved", "reason": reason}),
                    now_iso(),
                ),
            )

        elif action == "remove_table":
            table = resolve_table(conn, op.get("table_name"), op.get("schema_name"), op.get("catalog"))
            conn.execute("DELETE FROM qb_tables WHERE id = ?", (table["id"],))

        elif action == "rename_table":
            table = resolve_table(conn, op.get("table_name"), op.get("schema_name"), op.get("catalog"))
            conn.execute(
                "UPDATE qb_tables SET table_name = ?, captured_at = ? WHERE id = ?",
                (str(op["new_name"]).strip(), now_iso(), table["id"]),
            )

        elif action == "add_field":
            table = resolve_table(conn, op.get("table_name"), op.get("schema_name"), op.get("catalog"))
            ordinal = conn.execute(
                "SELECT COALESCE(MAX(ordinal_position), 0) + 1 n FROM qb_columns WHERE table_id = ?",
                (table["id"],),
            ).fetchone()["n"]
            nullable = op.get("nullable")
            nullable_value = None if nullable is None else int(bool(nullable))
            conn.execute(
                """
                INSERT INTO qb_columns
                (table_id, ordinal_position, column_name, data_type, nullable, comment, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table["id"],
                    ordinal,
                    str(op["column_name"]).strip(),
                    str(op["data_type"]).strip(),
                    nullable_value,
                    str(op.get("comment") or "").strip() or None,
                    json.dumps({"source": "ai-approved", "reason": reason}),
                ),
            )

        elif action == "remove_field":
            column = resolve_column(
                conn, op.get("table_name"), op.get("column_name"), op.get("schema_name"), op.get("catalog")
            )
            conn.execute("DELETE FROM qb_columns WHERE id = ?", (column["column_id"],))

        elif action == "rename_field":
            column = resolve_column(
                conn, op.get("table_name"), op.get("column_name"), op.get("schema_name"), op.get("catalog")
            )
            conn.execute(
                "UPDATE qb_columns SET column_name = ? WHERE id = ?",
                (str(op["new_name"]).strip(), column["column_id"]),
            )

        elif action == "change_field_type":
            column = resolve_column(
                conn, op.get("table_name"), op.get("column_name"), op.get("schema_name"), op.get("catalog")
            )
            conn.execute(
                "UPDATE qb_columns SET data_type = ? WHERE id = ?",
                (str(op["data_type"]).strip(), column["column_id"]),
            )

        elif action == "set_field_nullable":
            column = resolve_column(
                conn, op.get("table_name"), op.get("column_name"), op.get("schema_name"), op.get("catalog")
            )
            conn.execute(
                "UPDATE qb_columns SET nullable = ? WHERE id = ?",
                (int(bool(op.get("nullable"))), column["column_id"]),
            )

        elif action == "add_relationship":
            left = resolve_column(
                conn, op.get("left_table"), op.get("left_column"), op.get("left_schema"), op.get("left_catalog")
            )
            right = resolve_column(
                conn, op.get("right_table"), op.get("right_column"), op.get("right_schema"), op.get("right_catalog")
            )
            if left["column_id"] > right["column_id"]:
                left, right = right, left
            confidence = max(0.0, min(1.0, float(op.get("confidence", 0.8))))
            conn.execute(
                """
                INSERT INTO qb_relationships
                (left_table_id, left_column_id, right_table_id, right_column_id, confidence, source, notes)
                VALUES (?, ?, ?, ?, ?, 'ai-approved', ?)
                ON CONFLICT(left_column_id, right_column_id)
                DO UPDATE SET confidence = excluded.confidence, source = 'ai-approved', notes = excluded.notes
                """,
                (
                    left["table_id"],
                    left["column_id"],
                    right["table_id"],
                    right["column_id"],
                    confidence,
                    reason,
                ),
            )

        elif action == "remove_relationship":
            left = resolve_column(
                conn, op.get("left_table"), op.get("left_column"), op.get("left_schema"), op.get("left_catalog")
            )
            right = resolve_column(
                conn, op.get("right_table"), op.get("right_column"), op.get("right_schema"), op.get("right_catalog")
            )
            conn.execute(
                """
                DELETE FROM qb_relationships
                WHERE (left_column_id = ? AND right_column_id = ?)
                   OR (left_column_id = ? AND right_column_id = ?)
                """,
                (
                    left["column_id"],
                    right["column_id"],
                    right["column_id"],
                    left["column_id"],
                ),
            )

        applied.append(action)

    infer_relationships(conn)
    return applied


def normalise_ai_operation(raw):
    if not isinstance(raw, dict):
        return raw

    op = dict(raw)

    # Some models return {"add_relationship": {...}} instead of an action field.
    supported_or_alias_keys = {
        "add_table", "create_table", "new_table",
        "remove_table", "delete_table", "drop_table",
        "rename_table", "update_table_name", "change_table_name",
        "add_field", "add_column", "create_field", "create_column", "new_field", "new_column",
        "remove_field", "remove_column", "delete_field", "delete_column", "drop_field", "drop_column",
        "rename_field", "rename_column", "update_field_name", "change_column_name",
        "change_field_type", "change_type", "change_column_type", "modify_type", "update_type", "set_data_type", "update_data_type",
        "set_field_nullable", "set_nullable", "change_nullable", "update_nullability", "set_nullability",
        "add_relationship", "add_link", "create_link", "link_tables", "link_fields", "add_join", "create_relationship", "link",
        "remove_relationship", "delete_link", "remove_link", "unlink_tables", "remove_join", "delete_relationship",
    }
    if not any(
        op.get(key) not in {None, ""}
        for key in ("action", "operation", "type", "op", "change", "action_type", "kind", "command")
    ):
        if len(op) == 1:
            only_key, only_value = next(iter(op.items()))
            normalised_key = re.sub(
                r"[^a-z0-9]+", "_", str(only_key).strip().casefold()
            ).strip("_")
            if normalised_key in supported_or_alias_keys and isinstance(only_value, dict):
                op = {**only_value, "action": normalised_key}

    action_value = (
        op.get("action")
        or op.get("operation")
        or op.get("type")
        or op.get("op")
        or op.get("change")
        or op.get("action_type")
        or op.get("kind")
        or op.get("command")
        or ""
    )
    action = re.sub(r"[^a-z0-9]+", "_", str(action_value).strip().casefold()).strip("_")

    action_aliases = {
        "create_table": "add_table",
        "new_table": "add_table",
        "delete_table": "remove_table",
        "drop_table": "remove_table",
        "update_table_name": "rename_table",
        "change_table_name": "rename_table",
        "add_column": "add_field",
        "create_field": "add_field",
        "create_column": "add_field",
        "new_field": "add_field",
        "new_column": "add_field",
        "delete_field": "remove_field",
        "delete_column": "remove_field",
        "remove_column": "remove_field",
        "drop_field": "remove_field",
        "drop_column": "remove_field",
        "rename_column": "rename_field",
        "update_field_name": "rename_field",
        "change_column_name": "rename_field",
        "change_type": "change_field_type",
        "change_column_type": "change_field_type",
        "modify_type": "change_field_type",
        "update_type": "change_field_type",
        "set_data_type": "change_field_type",
        "update_data_type": "change_field_type",
        "set_nullable": "set_field_nullable",
        "change_nullable": "set_field_nullable",
        "update_nullability": "set_field_nullable",
        "set_nullability": "set_field_nullable",
        "add_link": "add_relationship",
        "create_link": "add_relationship",
        "link_tables": "add_relationship",
        "link_fields": "add_relationship",
        "add_join": "add_relationship",
        "create_relationship": "add_relationship",
        "link": "add_relationship",
        "delete_link": "remove_relationship",
        "remove_link": "remove_relationship",
        "unlink_tables": "remove_relationship",
        "remove_join": "remove_relationship",
        "delete_relationship": "remove_relationship",
    }
    action = action_aliases.get(action, action)
    op["action"] = action

    def first(*names):
        for name in names:
            value = op.get(name)
            if value is not None and value != "":
                return value
        return None

    if action in {
        "add_table",
        "remove_table",
        "rename_table",
        "add_field",
        "remove_field",
        "rename_field",
        "change_field_type",
        "set_field_nullable",
    }:
        if not op.get("table_name"):
            op["table_name"] = first("table", "tableName", "source_table", "entity", "entity_name")
        if not op.get("schema_name"):
            op["schema_name"] = first("schema", "schemaName", "table_schema")
        if not op.get("catalog"):
            op["catalog"] = first("catalog_name", "catalogName", "table_catalog")

    if action in {
        "add_field",
        "remove_field",
        "rename_field",
        "change_field_type",
        "set_field_nullable",
    }:
        if not op.get("column_name"):
            op["column_name"] = first(
                "field_name", "field", "column", "columnName", "fieldName"
            )

    if action in {"rename_table", "rename_field"} and not op.get("new_name"):
        op["new_name"] = first(
            "new_table_name",
            "new_column_name",
            "new_field_name",
            "to_name",
            "target_name",
            "replacement_name",
        )

    if action in {"add_field", "change_field_type"} and not op.get("data_type"):
        op["data_type"] = first(
            "field_type", "column_type", "datatype", "new_type", "new_data_type"
        )

    if action == "set_field_nullable" and "nullable" not in op:
        nullable = first("is_nullable", "null_allowed", "allow_null")
        if nullable is not None:
            if isinstance(nullable, str):
                op["nullable"] = nullable.strip().casefold() in {
                    "true", "1", "yes", "y", "nullable", "null"
                }
            else:
                op["nullable"] = bool(nullable)

    if action in {"add_relationship", "remove_relationship"}:
        left = op.get("left") if isinstance(op.get("left"), dict) else {}
        right = op.get("right") if isinstance(op.get("right"), dict) else {}

        op["left_table"] = (
            op.get("left_table")
            or first("source_table", "from_table", "child_table", "many_table")
            or left.get("table")
            or left.get("table_name")
        )
        op["left_column"] = (
            op.get("left_column")
            or first("source_column", "from_column", "source_field", "child_column", "many_column")
            or left.get("column")
            or left.get("column_name")
            or left.get("field")
        )
        op["right_table"] = (
            op.get("right_table")
            or first("target_table", "to_table", "parent_table", "one_table")
            or right.get("table")
            or right.get("table_name")
        )
        op["right_column"] = (
            op.get("right_column")
            or first("target_column", "to_column", "target_field", "parent_column", "one_column")
            or right.get("column")
            or right.get("column_name")
            or right.get("field")
        )

        op["left_schema"] = (
            op.get("left_schema")
            or first("source_schema", "from_schema")
            or left.get("schema")
            or left.get("schema_name")
        )
        op["right_schema"] = (
            op.get("right_schema")
            or first("target_schema", "to_schema")
            or right.get("schema")
            or right.get("schema_name")
        )
        op["left_catalog"] = (
            op.get("left_catalog")
            or first("source_catalog", "from_catalog")
            or left.get("catalog")
        )
        op["right_catalog"] = (
            op.get("right_catalog")
            or first("target_catalog", "to_catalog")
            or right.get("catalog")
        )

    if not op.get("reason"):
        op["reason"] = first("rationale", "explanation", "why", "note", "notes") or ""

    return op


def normalise_ai_operations(payload):
    if isinstance(payload, list):
        payload = {"operations": payload}
    if not isinstance(payload, dict):
        raise ValueError("The AI response was not a JSON object or operations list.")

    operations = None
    for key in ("operations", "changes", "proposals", "actions"):
        if key in payload:
            operations = payload.get(key)
            break
    if not isinstance(operations, list):
        raise ValueError("The AI response did not contain an operations list.")

    return {
        "title": str(
            payload.get("title")
            or payload.get("name")
            or "AI schema proposal"
        ).strip()[:240],
        "summary": str(
            payload.get("summary")
            or payload.get("description")
            or payload.get("reasoning")
            or ""
        ).strip()[:4000],
        "operations": [normalise_ai_operation(item) for item in operations],
    }

def create_ai_schema_proposal(conn, request_text, selected_skill_keys=None):
    all_skills = ai_skill_rows(conn, enabled_only=True)
    selected = set(selected_skill_keys or [])
    skills = [row for row in all_skills if not selected or row["skill_key"] in selected]
    if not skills:
        raise ValueError("No enabled AI skills are selected.")

    context = schema_context_text(conn, include_relationships=True, max_chars=70000)
    settings = get_llm_settings(conn)

    system = """You are QueryBridge's governed schema-change planner.
You work only on QueryBridge's LOCAL metadata model; you are not modifying live Databricks.
Use the supplied skills, schema and knowledge. Return JSON only.

Supported operations:
- add_table: table_name, optional schema_name/catalog/table_type, reason
- remove_table: table_name, optional schema_name/catalog, reason
- rename_table: table_name, new_name, optional schema_name/catalog, reason
- add_field: table_name, column_name, data_type, optional nullable/comment/schema_name/catalog, reason
- remove_field: table_name, column_name, optional schema_name/catalog, reason
- rename_field: table_name, column_name, new_name, optional schema_name/catalog, reason
- change_field_type: table_name, column_name, data_type, optional schema_name/catalog, reason
- set_field_nullable: table_name, column_name, nullable, optional schema_name/catalog, reason
- add_relationship: left_table, left_column, right_table, right_column, optional left_schema/right_schema/left_catalog/right_catalog/confidence, reason
- remove_relationship: the same relationship identity fields, reason

Return exactly this JSON structure:
{
  "title": "short title",
  "summary": "why these changes are proposed",
  "operations": [
    {
      "action": "one_exact_supported_action_name"
    }
  ]
}

The key MUST be named "action". The action value MUST be exactly one of:
add_table, remove_table, rename_table, add_field, remove_field, rename_field,
change_field_type, set_field_nullable, add_relationship, remove_relationship.

Rules:
- Never invent an existing table or field for operations that require an existing object.
- Structural additions may introduce a new table/field only when the user's request or knowledge supports it.
- Destructive operations must have a clear reason.
- Prefer no change over a weak guess.
- Relationships must be useful equality joins.
- Confidence is 0..1.
- Do not emit SQL DDL; emit only the structured operations above.
"""

    user = (
        "ACTIVE AI SKILLS\n"
        + ai_skill_context(skills)
        + "\n\nUSER REQUEST\n"
        + (request_text or "Review the schema and propose useful, knowledge-grounded improvements.")
        + "\n\nSCHEMA AND KNOWLEDGE\n"
        + context
    )

    raw = call_llm(
        conn,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
    )
    parsed = extract_json_payload(raw)
    proposal = normalise_ai_operations(parsed)
    checked = validate_schema_operations(conn, proposal["operations"])

    valid_operations = [item["operation"] for item in checked if item["valid"]]
    invalid = [item for item in checked if not item["valid"]]
    if invalid:
        rejected_text = "; ".join(
            (
                f"#{item['index']} {item['action']}: {item['error']} "
                f"(returned {json.dumps(item['operation'], ensure_ascii=False)[:500]})"
            )
            for item in invalid
        )
        proposal["summary"] = (
            proposal["summary"]
            + ("\n\n" if proposal["summary"] else "")
            + "QueryBridge rejected invalid AI operations before saving: "
            + rejected_text
        )
    proposal["operations"] = valid_operations

    cursor = conn.execute(
        """
        INSERT INTO qb_schema_proposals
        (title, summary, skill_key, model, operations_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'proposed', ?)
        """,
        (
            proposal["title"],
            proposal["summary"],
            ",".join(row["skill_key"] for row in skills),
            settings.get("model"),
            json.dumps(proposal["operations"], ensure_ascii=False),
            now_iso(),
        ),
    )
    return cursor.lastrowid, len(valid_operations), len(invalid)



LOCAL_ANALYSIS_TABLES = {
    "schema_tables",
    "schema_fields",
    "schema_relationships",
    "schema_knowledge",
}


def build_local_schema_analysis_db(conn):
    """Build an isolated in-memory database containing only schema/knowledge analysis data."""
    analysis = sqlite3.connect(":memory:")
    analysis.row_factory = sqlite3.Row
    analysis.executescript(
        """
        CREATE TABLE schema_tables (
            table_id INTEGER,
            catalog TEXT,
            schema_name TEXT,
            table_name TEXT,
            table_type TEXT,
            is_temporary INTEGER,
            captured_at TEXT
        );

        CREATE TABLE schema_fields (
            field_id INTEGER,
            table_id INTEGER,
            catalog TEXT,
            schema_name TEXT,
            table_name TEXT,
            ordinal_position INTEGER,
            column_name TEXT,
            data_type TEXT,
            nullable INTEGER,
            comment TEXT
        );

        CREATE TABLE schema_relationships (
            relationship_id INTEGER,
            left_catalog TEXT,
            left_schema TEXT,
            left_table TEXT,
            left_column TEXT,
            right_catalog TEXT,
            right_schema TEXT,
            right_table TEXT,
            right_column TEXT,
            confidence REAL,
            source TEXT,
            notes TEXT
        );

        CREATE TABLE schema_knowledge (
            knowledge_id INTEGER,
            title TEXT,
            category TEXT,
            content TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE INDEX idx_schema_tables_name ON schema_tables(table_name);
        CREATE INDEX idx_schema_fields_table ON schema_fields(table_name, column_name);
        CREATE INDEX idx_schema_relationships_left ON schema_relationships(left_table, left_column);
        CREATE INDEX idx_schema_relationships_right ON schema_relationships(right_table, right_column);
        CREATE INDEX idx_schema_knowledge_category ON schema_knowledge(category);
        """
    )

    analysis.executemany(
        """
        INSERT INTO schema_tables
        (table_id, catalog, schema_name, table_name, table_type, is_temporary, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["id"],
                row["catalog"],
                row["schema_name"],
                row["table_name"],
                row["table_type"],
                row["is_temporary"],
                row["captured_at"],
            )
            for row in conn.execute(
                """
                SELECT id, catalog, schema_name, table_name, table_type, is_temporary, captured_at
                FROM qb_tables
                ORDER BY COALESCE(catalog,''), COALESCE(schema_name,''), table_name
                """
            ).fetchall()
        ],
    )

    analysis.executemany(
        """
        INSERT INTO schema_fields
        (field_id, table_id, catalog, schema_name, table_name,
         ordinal_position, column_name, data_type, nullable, comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["field_id"],
                row["table_id"],
                row["catalog"],
                row["schema_name"],
                row["table_name"],
                row["ordinal_position"],
                row["column_name"],
                row["data_type"],
                row["nullable"],
                row["comment"],
            )
            for row in conn.execute(
                """
                SELECT
                    c.id field_id,
                    t.id table_id,
                    t.catalog,
                    t.schema_name,
                    t.table_name,
                    c.ordinal_position,
                    c.column_name,
                    c.data_type,
                    c.nullable,
                    c.comment
                FROM qb_columns c
                JOIN qb_tables t ON t.id = c.table_id
                ORDER BY t.table_name, c.ordinal_position
                """
            ).fetchall()
        ],
    )

    analysis.executemany(
        """
        INSERT INTO schema_relationships
        (relationship_id, left_catalog, left_schema, left_table, left_column,
         right_catalog, right_schema, right_table, right_column,
         confidence, source, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["relationship_id"],
                row["left_catalog"],
                row["left_schema"],
                row["left_table"],
                row["left_column"],
                row["right_catalog"],
                row["right_schema"],
                row["right_table"],
                row["right_column"],
                row["confidence"],
                row["source"],
                row["notes"],
            )
            for row in conn.execute(
                """
                SELECT
                    r.id relationship_id,
                    lt.catalog left_catalog,
                    lt.schema_name left_schema,
                    lt.table_name left_table,
                    lc.column_name left_column,
                    rt.catalog right_catalog,
                    rt.schema_name right_schema,
                    rt.table_name right_table,
                    rc.column_name right_column,
                    r.confidence,
                    r.source,
                    r.notes
                FROM qb_relationships r
                JOIN qb_tables lt ON lt.id = r.left_table_id
                JOIN qb_columns lc ON lc.id = r.left_column_id
                JOIN qb_tables rt ON rt.id = r.right_table_id
                JOIN qb_columns rc ON rc.id = r.right_column_id
                ORDER BY r.confidence DESC, r.id
                """
            ).fetchall()
        ],
    )

    analysis.executemany(
        """
        INSERT INTO schema_knowledge
        (knowledge_id, title, category, content, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["id"],
                row["title"],
                row["category"],
                row["content"],
                row["created_at"],
                row["updated_at"],
            )
            for row in conn.execute(
                """
                SELECT id, title, category, content, created_at, updated_at
                FROM qb_knowledge
                ORDER BY category, title
                """
            ).fetchall()
        ],
    )

    analysis.commit()
    analysis.execute("PRAGMA query_only = ON")
    return analysis


def validate_local_schema_select(sql):
    sql = (sql or "").strip()
    if not sql:
        raise ValueError("Local schema SELECT is empty.")

    # sqlite3.execute rejects multiple statements. The analysis database is isolated,
    # contains no application secrets and is switched to PRAGMA query_only before use.
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()

    if not re.match(r"(?is)^(select|with)\b", sql):
        raise ValueError("Local schema analysis only permits SELECT statements or SELECT CTEs.")

    return sql


def execute_local_schema_select(conn, sql, row_limit=250, timeout_seconds=2.0):
    sql = validate_local_schema_select(sql)
    analysis = build_local_schema_analysis_db(conn)
    started = time.monotonic()

    def progress_guard():
        return 1 if time.monotonic() - started > timeout_seconds else 0

    analysis.set_progress_handler(progress_guard, 5000)
    try:
        cursor = analysis.execute(sql)
        columns = [item[0] for item in (cursor.description or [])]
        rows = cursor.fetchmany(max(1, min(int(row_limit), 500)) + 1)
        truncated = len(rows) > row_limit
        rows = rows[:row_limit]

        serialised_rows = []
        for row in rows:
            serialised_rows.append(
                {
                    columns[index]: row[index]
                    for index in range(len(columns))
                }
            )

        result = {
            "sql": sql,
            "columns": columns,
            "rows": serialised_rows,
            "row_count": len(serialised_rows),
            "truncated": truncated,
        }

        encoded = json.dumps(result, ensure_ascii=False, default=str)
        if len(encoded) > 50000:
            result["rows"] = serialised_rows[:50]
            result["row_count"] = len(result["rows"])
            result["truncated"] = True
            result["note"] = "Result was truncated by QueryBridge's local analysis context limit."

        return result
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).casefold():
            raise ValueError("Local schema SELECT exceeded the analysis time limit.") from exc
        raise ValueError(f"Local schema SELECT failed: {exc}") from exc
    finally:
        analysis.close()


def local_schema_sql_reference():
    return """LOCAL SCHEMA SQL TABLES

schema_tables(
  table_id, catalog, schema_name, table_name, table_type, is_temporary, captured_at
)

schema_fields(
  field_id, table_id, catalog, schema_name, table_name,
  ordinal_position, column_name, data_type, nullable, comment
)

schema_relationships(
  relationship_id,
  left_catalog, left_schema, left_table, left_column,
  right_catalog, right_schema, right_table, right_column,
  confidence, source, notes
)

schema_knowledge(
  knowledge_id, title, category, content, created_at, updated_at
)

These are isolated local copies of QueryBridge metadata for analysis. They do not contain Databricks business rows."""


def parse_schema_chat_agent_response(raw):
    payload = extract_json_payload(raw)
    if not isinstance(payload, dict):
        return {"kind": "answer", "answer": raw}

    kind = str(
        payload.get("kind")
        or payload.get("type")
        or payload.get("action")
        or ""
    ).strip().casefold()

    sql = payload.get("sql") or payload.get("query")
    if sql and kind in {"tool", "select", "query", "local_schema_select", "run_select", ""}:
        return {
            "kind": "tool",
            "tool": "local_schema_select",
            "sql": str(sql),
            "purpose": str(payload.get("purpose") or payload.get("reason") or ""),
        }

    answer = (
        payload.get("answer")
        or payload.get("response")
        or payload.get("content")
        or payload.get("message")
    )
    if answer is not None:
        return {"kind": "answer", "answer": str(answer)}

    return {"kind": "answer", "answer": raw}


def run_schema_chat_agent(conn, messages, max_tool_calls=6):
    tool_runs = []
    working = list(messages)

    for _ in range(max_tool_calls + 1):
        raw = call_llm(conn, working, json_mode=True)
        decision = parse_schema_chat_agent_response(raw)

        if decision["kind"] == "answer":
            return decision["answer"], tool_runs

        sql = decision["sql"]
        result = execute_local_schema_select(conn, sql)
        tool_runs.append(
            {
                "sql": result["sql"],
                "row_count": result["row_count"],
                "truncated": result["truncated"],
                "purpose": decision.get("purpose") or "",
            }
        )

        working.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "kind": "tool",
                        "tool": "local_schema_select",
                        "sql": sql,
                        "purpose": decision.get("purpose") or "",
                    },
                    ensure_ascii=False,
                ),
            }
        )
        working.append(
            {
                "role": "user",
                "content": (
                    "LOCAL_SCHEMA_SELECT_RESULT\n"
                    + json.dumps(result, ensure_ascii=False, default=str)
                    + "\n\nUse this result as evidence. Run another local_schema_select if useful, "
                    "otherwise return your final answer."
                ),
            }
        )

    raise ValueError("Schema Chat reached the local SELECT tool-call limit before producing an answer.")


def get_llm_settings(conn):
    row = conn.execute("SELECT * FROM qb_llm_settings WHERE id = 1").fetchone()
    if not row:
        return {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "",
            "temperature": 0.2,
            "timeout_seconds": 120,
        }
    return dict(row)


def normalize_base_url(value):
    return (value or "").strip().rstrip("/")


def ollama_models(base_url, timeout_seconds=15):
    url = normalize_base_url(base_url) + "/api/tags"
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    return [
        item.get("name")
        for item in payload.get("models", [])
        if isinstance(item, dict) and item.get("name")
    ]


def call_llm(conn, messages, json_mode=False):
    settings = get_llm_settings(conn)
    provider = settings.get("provider") or "ollama"
    if provider != "ollama":
        raise ValueError(f"Unsupported LLM provider: {provider}")

    base_url = normalize_base_url(settings.get("base_url"))
    model = (settings.get("model") or "").strip()

    if not base_url:
        raise ValueError("Configure an Ollama base URL in LLM Setup.")
    if not model:
        raise ValueError("Configure an Ollama model in LLM Setup.")

    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": float(settings.get("temperature") or 0.2)
        },
    }
    if json_mode:
        body["format"] = "json"

    try:
        response = requests.post(
            base_url + "/api/chat",
            json=body,
            timeout=int(settings.get("timeout_seconds") or 120),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Could not reach the configured Ollama server: {exc}") from exc

    payload = response.json()
    content = ((payload.get("message") or {}).get("content") or "").strip()
    if not content:
        raise ValueError("The LLM returned an empty response.")
    return content


def knowledge_rows(conn):
    return conn.execute(
        """
        SELECT id, title, category, content, created_at, updated_at
        FROM qb_knowledge
        ORDER BY category, title
        """
    ).fetchall()



def import_builtin_knowledge_pack(conn):
    manifest_path = BASE_DIR / "knowledge" / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Built-in knowledge manifest was not found.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "querybridge-knowledge-manifest":
        raise ValueError("Built-in knowledge manifest format is invalid.")

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Built-in knowledge manifest has no entries list.")

    added = 0
    updated = 0
    skipped = 0

    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue

        title = str(entry.get("title") or "").strip()
        category = str(entry.get("category") or "general").strip() or "general"
        filename = str(entry.get("file") or "").strip()

        if not title or not filename:
            skipped += 1
            continue

        safe_name = Path(filename).name
        file_path = BASE_DIR / "knowledge" / safe_name
        if not file_path.exists() or not file_path.is_file():
            skipped += 1
            continue

        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            skipped += 1
            continue

        existing = conn.execute(
            "SELECT id FROM qb_knowledge WHERE lower(title) = lower(?)",
            (title,),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE qb_knowledge
                SET category = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (category, content, now_iso(), existing["id"]),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO qb_knowledge
                (title, category, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, category, content, now_iso(), now_iso()),
            )
            added += 1

    return {
        "pack": manifest.get("pack") or "Built-in knowledge pack",
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total": len(entries),
    }


def schema_context_text(conn, include_relationships=True, max_chars=60000):
    tables = conn.execute(
        """
        SELECT * FROM qb_tables
        ORDER BY COALESCE(catalog,''), COALESCE(schema_name,''), table_name
        """
    ).fetchall()

    lines = ["QUERYBRIDGE WORKING SCHEMA"]
    for table in tables:
        lines.append("")
        lines.append(f"TABLE {qualified_name(table)}")
        columns = conn.execute(
            """
            SELECT column_name, data_type, nullable, comment
            FROM qb_columns
            WHERE table_id = ?
            ORDER BY ordinal_position
            """,
            (table["id"],),
        ).fetchall()
        for col in columns:
            detail = f"- {col['column_name']} : {col['data_type'] or 'UNKNOWN'}"
            if col["nullable"] is not None:
                detail += " NULLABLE" if col["nullable"] else " NOT NULL"
            if col["comment"]:
                detail += f" -- {col['comment']}"
            lines.append(detail)

    if include_relationships:
        relationships = conn.execute(
            """
            SELECT
                lt.catalog left_catalog, lt.schema_name left_schema, lt.table_name left_table,
                lc.column_name left_column,
                rt.catalog right_catalog, rt.schema_name right_schema, rt.table_name right_table,
                rc.column_name right_column,
                r.confidence, r.source, r.notes
            FROM qb_relationships r
            JOIN qb_tables lt ON lt.id = r.left_table_id
            JOIN qb_columns lc ON lc.id = r.left_column_id
            JOIN qb_tables rt ON rt.id = r.right_table_id
            JOIN qb_columns rc ON rc.id = r.right_column_id
            ORDER BY r.confidence DESC, r.id
            """
        ).fetchall()

        if relationships:
            lines.extend(["", "KNOWN / INFERRED RELATIONSHIPS"])
            for rel in relationships:
                left = ".".join(
                    x for x in [rel["left_catalog"], rel["left_schema"], rel["left_table"], rel["left_column"]] if x
                )
                right = ".".join(
                    x for x in [rel["right_catalog"], rel["right_schema"], rel["right_table"], rel["right_column"]] if x
                )
                note = f" -- {rel['notes']}" if rel["notes"] else ""
                lines.append(
                    f"- {left} = {right} "
                    f"[source={rel['source']}, confidence={rel['confidence']:.2f}]{note}"
                )

    knowledge = knowledge_rows(conn)
    if knowledge:
        lines.extend(["", "SCHEMA / PACKAGE KNOWLEDGE"])
        for item in knowledge:
            lines.append(f"[{item['category']}] {item['title']}")
            lines.append(item["content"])

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Context truncated by QueryBridge]"
    return text


def extract_json_payload(text):
    cleaned = (text or "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start_obj = cleaned.find("{")
    end_obj = cleaned.rfind("}")
    if start_obj >= 0 and end_obj > start_obj:
        try:
            return json.loads(cleaned[start_obj : end_obj + 1])
        except Exception:
            pass

    start_arr = cleaned.find("[")
    end_arr = cleaned.rfind("]")
    if start_arr >= 0 and end_arr > start_arr:
        try:
            return json.loads(cleaned[start_arr : end_arr + 1])
        except Exception:
            pass
    return None


def find_column(conn, table_name, column_name, schema_name=None, catalog=None):
    sql = """
        SELECT
            c.id column_id, c.table_id, c.column_name,
            t.catalog, t.schema_name, t.table_name
        FROM qb_columns c
        JOIN qb_tables t ON t.id = c.table_id
        WHERE lower(t.table_name) = lower(?)
          AND lower(c.column_name) = lower(?)
    """
    params = [table_name, column_name]

    if schema_name:
        sql += " AND lower(COALESCE(t.schema_name,'')) = lower(?)"
        params.append(schema_name)
    if catalog:
        sql += " AND lower(COALESCE(t.catalog,'')) = lower(?)"
        params.append(catalog)

    sql += " ORDER BY t.id LIMIT 1"
    return conn.execute(sql, params).fetchone()


def save_llm_relationship(conn, left, right, confidence, reason):
    if not left or not right or left["column_id"] == right["column_id"]:
        return False

    if left["column_id"] > right["column_id"]:
        left, right = right, left

    existing = conn.execute(
        """
        SELECT id, source, confidence
        FROM qb_relationships
        WHERE left_column_id = ? AND right_column_id = ?
        """,
        (left["column_id"], right["column_id"]),
    ).fetchone()

    confidence = max(0.0, min(1.0, float(confidence or 0.75)))

    if existing:
        if existing["source"] == "manual":
            return False
        conn.execute(
            """
            UPDATE qb_relationships
            SET confidence = ?, source = 'llm', notes = ?
            WHERE id = ?
            """,
            (max(confidence, float(existing["confidence"] or 0)), reason, existing["id"]),
        )
        return True

    conn.execute(
        """
        INSERT INTO qb_relationships
        (left_table_id, left_column_id, right_table_id, right_column_id, confidence, source, notes)
        VALUES (?, ?, ?, ?, ?, 'llm', ?)
        """,
        (
            left["table_id"],
            left["column_id"],
            right["table_id"],
            right["column_id"],
            confidence,
            reason,
        ),
    )
    return True


def llm_guess_relationships(conn):
    context = schema_context_text(conn, include_relationships=True, max_chars=50000)
    system = """You are QueryBridge's schema relationship analyst.
Infer plausible SQL JOIN relationships only from the supplied schema and knowledge.
Do not invent tables or columns.
Prefer keys, identifiers, business rules, package conventions, and existing field comments.
Return JSON only in this shape:
{
  "relationships": [
    {
      "left_table": "table",
      "left_schema": "optional schema or null",
      "left_catalog": "optional catalog or null",
      "left_column": "column",
      "right_table": "table",
      "right_schema": "optional schema or null",
      "right_catalog": "optional catalog or null",
      "right_column": "column",
      "confidence": 0.0,
      "reason": "short explanation"
    }
  ]
}
Only include relationships useful as equality joins. Confidence must be between 0 and 1."""
    user = "Analyse this working schema and propose the most useful table links.\n\n" + context
    raw = call_llm(
        conn,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        json_mode=True,
    )

    payload = extract_json_payload(raw)
    if isinstance(payload, list):
        suggestions = payload
    elif isinstance(payload, dict):
        suggestions = payload.get("relationships", [])
    else:
        raise ValueError("The LLM response was not valid JSON.")

    stored = 0
    skipped = 0
    details = []

    for item in suggestions:
        if not isinstance(item, dict):
            skipped += 1
            continue

        left = find_column(
            conn,
            item.get("left_table"),
            item.get("left_column"),
            item.get("left_schema"),
            item.get("left_catalog"),
        ) if item.get("left_table") and item.get("left_column") else None

        right = find_column(
            conn,
            item.get("right_table"),
            item.get("right_column"),
            item.get("right_schema"),
            item.get("right_catalog"),
        ) if item.get("right_table") and item.get("right_column") else None

        if not left or not right or left["table_id"] == right["table_id"]:
            skipped += 1
            continue

        confidence = item.get("confidence", 0.75)
        reason = (item.get("reason") or "Suggested by configured LLM").strip()

        if save_llm_relationship(conn, left, right, confidence, reason):
            stored += 1
            details.append(
                f"{left['table_name']}.{left['column_name']} = "
                f"{right['table_name']}.{right['column_name']}"
            )
        else:
            skipped += 1

    return stored, skipped, details


def snapshot_table_identity(table):
    return {
        "catalog": table.get("catalog"),
        "schema_name": table.get("schema_name"),
        "table_name": table.get("table_name"),
    }


def snapshot_key(catalog, schema_name, table_name, column_name=None):
    base = (catalog or "", schema_name or "", table_name or "")
    return base + ((column_name or ""),) if column_name is not None else base


def serialize_working_schema(conn):
    tables = conn.execute(
        """
        SELECT * FROM qb_tables
        ORDER BY COALESCE(catalog,''), COALESCE(schema_name,''), table_name
        """
    ).fetchall()

    payload_tables = []
    for table in tables:
        columns = conn.execute(
            """
            SELECT ordinal_position, column_name, data_type, nullable, comment, raw_json
            FROM qb_columns
            WHERE table_id = ?
            ORDER BY ordinal_position
            """,
            (table["id"],),
        ).fetchall()

        payload_tables.append(
            {
                "catalog": table["catalog"],
                "schema_name": table["schema_name"],
                "table_name": table["table_name"],
                "table_type": table["table_type"],
                "is_temporary": table["is_temporary"],
                "raw_source": table["raw_source"],
                "captured_at": table["captured_at"],
                "columns": [dict(column) for column in columns],
            }
        )

    relationships = conn.execute(
        """
        SELECT
            r.confidence, r.source, r.notes,
            lt.catalog left_catalog, lt.schema_name left_schema, lt.table_name left_table,
            lc.column_name left_column,
            rt.catalog right_catalog, rt.schema_name right_schema, rt.table_name right_table,
            rc.column_name right_column
        FROM qb_relationships r
        JOIN qb_tables lt ON lt.id = r.left_table_id
        JOIN qb_columns lc ON lc.id = r.left_column_id
        JOIN qb_tables rt ON rt.id = r.right_table_id
        JOIN qb_columns rc ON rc.id = r.right_column_id
        ORDER BY r.id
        """
    ).fetchall()

    payload_relationships = []
    for rel in relationships:
        payload_relationships.append(
            {
                "left": {
                    "catalog": rel["left_catalog"],
                    "schema_name": rel["left_schema"],
                    "table_name": rel["left_table"],
                    "column_name": rel["left_column"],
                },
                "right": {
                    "catalog": rel["right_catalog"],
                    "schema_name": rel["right_schema"],
                    "table_name": rel["right_table"],
                    "column_name": rel["right_column"],
                },
                "confidence": rel["confidence"],
                "source": rel["source"],
                "notes": rel["notes"],
            }
        )

    knowledge = [
        {
            "title": row["title"],
            "category": row["category"],
            "content": row["content"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in knowledge_rows(conn)
    ]

    return {
        "format": "querybridge-schema",
        "format_version": 1,
        "generated_at": now_iso(),
        "tables": payload_tables,
        "relationships": payload_relationships,
        "knowledge": knowledge,
    }


def validate_snapshot(payload):
    if not isinstance(payload, dict):
        raise ValueError("Schema file must contain a JSON object.")
    if payload.get("format") != "querybridge-schema":
        raise ValueError("This is not a QueryBridge schema export.")
    if payload.get("format_version") != 1:
        raise ValueError(
            f"Unsupported QueryBridge schema format version: {payload.get('format_version')}"
        )
    if not isinstance(payload.get("tables"), list):
        raise ValueError("Schema export does not contain a tables list.")

    for table in payload["tables"]:
        if not isinstance(table, dict) or not table.get("table_name"):
            raise ValueError("A table in the schema export is missing table_name.")
        if not isinstance(table.get("columns", []), list):
            raise ValueError(f"Columns for {table.get('table_name')} are invalid.")

    return payload


def restore_working_schema(conn, payload):
    validate_snapshot(payload)

    conn.execute("DELETE FROM qb_relationships")
    conn.execute("DELETE FROM qb_imports")
    conn.execute("DELETE FROM qb_knowledge")
    conn.execute("DELETE FROM qb_chat_messages")
    conn.execute("DELETE FROM qb_columns")
    conn.execute("DELETE FROM qb_tables")

    table_ids = {}
    column_ids = {}
    field_count = 0

    for table in payload["tables"]:
        captured_at = table.get("captured_at") or now_iso()
        cursor = conn.execute(
            """
            INSERT INTO qb_tables
            (catalog, schema_name, table_name, table_type, is_temporary, raw_source, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table.get("catalog"),
                table.get("schema_name"),
                table["table_name"],
                table.get("table_type"),
                int(bool(table.get("is_temporary", 0))),
                table.get("raw_source"),
                captured_at,
            ),
        )
        table_id = cursor.lastrowid
        table_key = snapshot_key(
            table.get("catalog"), table.get("schema_name"), table["table_name"]
        )
        table_ids[table_key] = table_id

        for position, column in enumerate(table.get("columns", []), start=1):
            column_name = column.get("column_name")
            if not column_name:
                continue
            cursor = conn.execute(
                """
                INSERT INTO qb_columns
                (table_id, ordinal_position, column_name, data_type, nullable, comment, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table_id,
                    column.get("ordinal_position") or position,
                    column_name,
                    column.get("data_type"),
                    column.get("nullable"),
                    column.get("comment"),
                    column.get("raw_json"),
                ),
            )
            column_ids[snapshot_key(
                table.get("catalog"),
                table.get("schema_name"),
                table["table_name"],
                column_name,
            )] = cursor.lastrowid
            field_count += 1

    restored_relationships = 0
    for rel in payload.get("relationships", []):
        left = rel.get("left") or {}
        right = rel.get("right") or {}
        left_table_key = snapshot_key(
            left.get("catalog"), left.get("schema_name"), left.get("table_name")
        )
        right_table_key = snapshot_key(
            right.get("catalog"), right.get("schema_name"), right.get("table_name")
        )
        left_column_key = snapshot_key(
            left.get("catalog"),
            left.get("schema_name"),
            left.get("table_name"),
            left.get("column_name"),
        )
        right_column_key = snapshot_key(
            right.get("catalog"),
            right.get("schema_name"),
            right.get("table_name"),
            right.get("column_name"),
        )

        if (
            left_table_key not in table_ids
            or right_table_key not in table_ids
            or left_column_key not in column_ids
            or right_column_key not in column_ids
        ):
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO qb_relationships
            (left_table_id, left_column_id, right_table_id, right_column_id, confidence, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_ids[left_table_key],
                column_ids[left_column_key],
                table_ids[right_table_key],
                column_ids[right_column_key],
                float(rel.get("confidence", 0)),
                rel.get("source") or "snapshot",
                rel.get("notes"),
            ),
        )
        restored_relationships += 1

    for item in payload.get("knowledge", []):
        if not isinstance(item, dict) or not item.get("title") or not item.get("content"):
            continue
        conn.execute(
            """
            INSERT INTO qb_knowledge
            (title, category, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item["title"],
                item.get("category") or "general",
                item["content"],
                item.get("created_at") or now_iso(),
                item.get("updated_at") or now_iso(),
            ),
        )

    if not payload.get("relationships"):
        infer_relationships(conn)
        restored_relationships = conn.execute(
            "SELECT COUNT(*) n FROM qb_relationships"
        ).fetchone()["n"]

    return len(table_ids), field_count, restored_relationships


def store_named_snapshot(conn, name, description, payload):
    name = (name or "").strip()
    if not name:
        raise ValueError("Give the schema snapshot a name.")

    payload = dict(payload)
    payload["snapshot_name"] = name
    payload["description"] = (description or "").strip()
    payload["saved_at"] = now_iso()

    existing = conn.execute(
        "SELECT id, created_at FROM qb_schema_snapshots WHERE name = ?",
        (name,),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE qb_schema_snapshots
            SET description = ?, snapshot_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload["description"],
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
                existing["id"],
            ),
        )
        return existing["id"], True

    cursor = conn.execute(
        """
        INSERT INTO qb_schema_snapshots
        (name, description, snapshot_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            name,
            payload["description"],
            json.dumps(payload, ensure_ascii=False),
            now_iso(),
            now_iso(),
        ),
    )
    return cursor.lastrowid, False


def safe_export_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._")
    return cleaned or "querybridge_schema"


def import_table_list(raw_text: str, catalog_override: str, schema_override: str):
    rows = parse_grid(raw_text)
    if not rows:
        raise ValueError("No rows were recognised. Include the Databricks result headers when copying the grid.")

    conn = db()
    added = 0
    updated = 0

    for row in rows:
        table_name = row_value(row, "tableName", "table_name", "tablename", "name")
        if not table_name:
            continue

        schema_name = schema_override.strip() or row_value(
            row, "database", "schema", "schema_name", "table_schema", "namespace"
        )
        catalog = catalog_override.strip() or row_value(row, "catalog", "catalog_name", "table_catalog")
        table_type = row_value(row, "table_type", "type")
        is_temp = parse_bool(row_value(row, "isTemporary", "is_temporary") or "false")

        existing = conn.execute(
            """
            SELECT id FROM qb_tables
            WHERE COALESCE(catalog,'') = COALESCE(?, '')
              AND COALESCE(schema_name,'') = COALESCE(?, '')
              AND table_name = ?
            """,
            (catalog, schema_name, table_name),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE qb_tables
                SET table_type = COALESCE(?, table_type),
                    is_temporary = ?,
                    raw_source = ?,
                    captured_at = ?
                WHERE id = ?
                """,
                (table_type, is_temp, json.dumps(row), now_iso(), existing["id"]),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO qb_tables
                (catalog, schema_name, table_name, table_type, is_temporary, raw_source, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (catalog, schema_name, table_name, table_type, is_temp, json.dumps(row), now_iso()),
            )
            added += 1

    conn.execute(
        """
        INSERT INTO qb_imports(import_type, source_sql, raw_text, imported_at)
        VALUES ('show_tables', 'SHOW TABLES;', ?, ?)
        """,
        (raw_text, now_iso()),
    )
    conn.commit()
    conn.close()
    return added, updated


def import_description(table_id: int, raw_text: str):
    conn = db()
    table = conn.execute("SELECT * FROM qb_tables WHERE id = ?", (table_id,)).fetchone()
    if not table:
        conn.close()
        raise ValueError("Table was not found.")

    parsed_json = extract_json_object(raw_text)
    columns = []

    if parsed_json and isinstance(parsed_json.get("columns"), list):
        for idx, col in enumerate(parsed_json["columns"], start=1):
            columns.append(
                {
                    "position": idx,
                    "name": col.get("name"),
                    "type": type_json_to_sql(col.get("type")),
                    "nullable": None if "nullable" not in col else int(bool(col.get("nullable"))),
                    "comment": col.get("comment"),
                    "raw_json": json.dumps(col, ensure_ascii=False),
                }
            )

        conn.execute(
            """
            UPDATE qb_tables
            SET catalog = COALESCE(?, catalog),
                schema_name = COALESCE(?, schema_name),
                table_type = COALESCE(?, table_type)
            WHERE id = ?
            """,
            (
                parsed_json.get("catalog_name"),
                parsed_json.get("schema_name"),
                parsed_json.get("type"),
                table_id,
            ),
        )
    else:
        rows = parse_grid(raw_text)
        position = 0
        for row in rows:
            name = row_value(row, "col_name", "column_name", "name")
            dtype = row_value(row, "data_type", "type")
            if not name or name.startswith("#"):
                continue
            position += 1
            columns.append(
                {
                    "position": position,
                    "name": name,
                    "type": dtype,
                    "nullable": None,
                    "comment": row_value(row, "comment"),
                    "raw_json": json.dumps(row, ensure_ascii=False),
                }
            )

    if not columns:
        conn.close()
        raise ValueError(
            "No columns were recognised. Prefer DESCRIBE TABLE EXTENDED ... AS JSON, "
            "or paste the full DESCRIBE result including its headers."
        )

    conn.execute("DELETE FROM qb_columns WHERE table_id = ?", (table_id,))
    for col in columns:
        if not col["name"]:
            continue
        conn.execute(
            """
            INSERT INTO qb_columns
            (table_id, ordinal_position, column_name, data_type, nullable, comment, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_id,
                col["position"],
                col["name"],
                col["type"],
                col["nullable"],
                col["comment"],
                col["raw_json"],
            ),
        )

    conn.execute(
        """
        INSERT INTO qb_imports(import_type, table_id, source_sql, raw_text, imported_at)
        VALUES ('describe_table', ?, ?, ?, ?)
        """,
        (
            table_id,
            "DESCRIBE TABLE EXTENDED " + qualified_name(table) + " AS JSON;",
            raw_text,
            now_iso(),
        ),
    )

    infer_relationships(conn)
    conn.commit()
    conn.close()
    return len(columns)


init_db()

@app.route("/")
def index():
    conn = db()
    tables = conn.execute(
        """
        SELECT t.*, COUNT(c.id) column_count
        FROM qb_tables t
        LEFT JOIN qb_columns c ON c.table_id = t.id
        GROUP BY t.id
        ORDER BY COALESCE(t.catalog,''), COALESCE(t.schema_name,''), t.table_name
        """
    ).fetchall()
    rel_count = conn.execute("SELECT COUNT(*) n FROM qb_relationships").fetchone()["n"]
    snapshot_rows = conn.execute(
        """
        SELECT id, name, description, snapshot_json, created_at, updated_at
        FROM qb_schema_snapshots
        ORDER BY updated_at DESC, name
        """
    ).fetchall()
    conn.close()

    table_cards = []
    for table in tables:
        qname = qualified_name(table)
        table_cards.append(
            {
                **dict(table),
                "qualified_name": qname,
                "describe_sql": f"DESCRIBE TABLE EXTENDED {qname} AS JSON;",
                "fallback_sql": f"DESCRIBE TABLE EXTENDED {qname};",
            }
        )

    snapshots = []
    for row in snapshot_rows:
        try:
            snapshot_payload = json.loads(row["snapshot_json"])
            snapshot_tables = snapshot_payload.get("tables", [])
            table_count = len(snapshot_tables)
            field_count = sum(len(t.get("columns", [])) for t in snapshot_tables)
            relationship_count = len(snapshot_payload.get("relationships", []))
            knowledge_count = len(snapshot_payload.get("knowledge", []))
        except Exception:
            table_count = 0
            field_count = 0
            relationship_count = 0
            knowledge_count = 0

        snapshots.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "table_count": table_count,
                "field_count": field_count,
                "relationship_count": relationship_count,
                "knowledge_count": knowledge_count,
            }
        )

    return render_template(
        "index.html",
        tables=table_cards,
        relationship_count=rel_count,
        snapshots=snapshots,
    )



@app.post("/schemas/save")
def save_schema_snapshot():
    name = request.form.get("name", "")
    description = request.form.get("description", "")
    conn = db()
    try:
        payload = serialize_working_schema(conn)
        if not payload["tables"]:
            raise ValueError("There is no captured schema to save yet.")
        _, updated = store_named_snapshot(conn, name, description, payload)
        conn.commit()
        action = "updated" if updated else "saved"
        flash(f'Schema snapshot "{name.strip()}" {action}.', "success")
    except Exception as exc:
        conn.rollback()
        flash(str(exc), "error")
    finally:
        conn.close()
    return redirect(url_for("index") + "#schema-library")


@app.post("/schemas/import")
def import_schema_snapshot():
    uploaded = request.files.get("schema_file")
    requested_name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    load_now = request.form.get("load_now") == "1"

    if not uploaded or not uploaded.filename:
        flash("Choose a QueryBridge JSON schema file to import.", "error")
        return redirect(url_for("index") + "#schema-library")

    conn = db()
    try:
        payload = json.load(uploaded.stream)
        validate_snapshot(payload)

        imported_name = (
            requested_name
            or str(payload.get("snapshot_name") or "").strip()
            or Path(uploaded.filename).stem
        )
        imported_description = description or str(payload.get("description") or "").strip()

        snapshot_id, updated = store_named_snapshot(
            conn, imported_name, imported_description, payload
        )

        if load_now:
            table_count, field_count, rel_count = restore_working_schema(conn, payload)
            flash(
                f'Imported and loaded "{imported_name}": '
                f"{table_count} tables, {field_count} fields, {rel_count} links.",
                "success",
            )
        else:
            action = "updated" if updated else "imported"
            flash(f'Schema snapshot "{imported_name}" {action}.', "success")

        conn.commit()
    except Exception as exc:
        conn.rollback()
        flash(f"Schema import failed: {exc}", "error")
    finally:
        conn.close()

    return redirect(url_for("index") + "#schema-library")


@app.post("/schemas/<int:snapshot_id>/load")
def load_schema_snapshot(snapshot_id):
    conn = db()
    try:
        row = conn.execute(
            "SELECT * FROM qb_schema_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        if not row:
            raise ValueError("Schema snapshot was not found.")

        payload = json.loads(row["snapshot_json"])
        table_count, field_count, rel_count = restore_working_schema(conn, payload)
        conn.commit()
        flash(
            f'Loaded "{row["name"]}": '
            f"{table_count} tables, {field_count} fields, {rel_count} links.",
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"Could not load schema: {exc}", "error")
    finally:
        conn.close()

    return redirect(url_for("index") + "#schema-library")


@app.get("/schemas/<int:snapshot_id>/export")
def export_schema_snapshot(snapshot_id):
    conn = db()
    row = conn.execute(
        "SELECT name, snapshot_json FROM qb_schema_snapshots WHERE id = ?",
        (snapshot_id,),
    ).fetchone()
    conn.close()

    if not row:
        return Response("Schema snapshot not found.", status=404, mimetype="text/plain")

    filename = safe_export_name(row["name"]) + ".querybridge.json"
    try:
        payload = json.loads(row["snapshot_json"])
        body = json.dumps(payload, indent=2, ensure_ascii=False)
    except Exception:
        body = row["snapshot_json"]

    return Response(
        body,
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.post("/schemas/<int:snapshot_id>/delete")
def delete_schema_snapshot(snapshot_id):
    conn = db()
    row = conn.execute(
        "SELECT name FROM qb_schema_snapshots WHERE id = ?",
        (snapshot_id,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM qb_schema_snapshots WHERE id = ?", (snapshot_id,))
        conn.commit()
        flash(f'Deleted schema snapshot "{row["name"]}".', "success")
    else:
        flash("Schema snapshot was not found.", "error")
    conn.close()
    return redirect(url_for("index") + "#schema-library")



@app.route("/llm", methods=["GET"])
def llm_setup():
    conn = db()
    settings = get_llm_settings(conn)
    conn.close()
    return render_template("llm_setup.html", settings=settings)


@app.post("/llm")
def save_llm_setup():
    base_url = normalize_base_url(request.form.get("base_url"))
    model = (request.form.get("model") or "").strip()
    temperature_raw = request.form.get("temperature", "0.2")
    timeout_raw = request.form.get("timeout_seconds", "120")
    action = request.form.get("action", "save")

    try:
        temperature = float(temperature_raw)
        timeout_seconds = int(timeout_raw)
        if temperature < 0 or temperature > 2:
            raise ValueError("Temperature must be between 0 and 2.")
        if timeout_seconds < 5 or timeout_seconds > 1800:
            raise ValueError("Timeout must be between 5 and 1800 seconds.")
        if not base_url:
            raise ValueError("Base URL is required.")

        conn = db()
        conn.execute(
            """
            UPDATE qb_llm_settings
            SET provider = 'ollama', base_url = ?, model = ?,
                temperature = ?, timeout_seconds = ?, updated_at = ?
            WHERE id = 1
            """,
            (base_url, model, temperature, timeout_seconds, now_iso()),
        )
        conn.commit()

        if action == "test":
            models = ollama_models(base_url, min(timeout_seconds, 30))
            if model and model not in models:
                flash(
                    f"Connected to Ollama. Model '{model}' was not returned by /api/tags.",
                    "error",
                )
            else:
                model_text = f" Model: {model}." if model else ""
                flash(
                    f"Connected to Ollama successfully. {len(models)} model(s) available.{model_text}",
                    "success",
                )
        else:
            flash("LLM settings saved.", "success")
        conn.close()
    except Exception as exc:
        flash(str(exc), "error")

    return redirect(url_for("llm_setup"))


@app.get("/api/llm/models")
def api_llm_models():
    conn = db()
    settings = get_llm_settings(conn)
    conn.close()
    requested_url = normalize_base_url(request.args.get("base_url"))
    base_url = requested_url or settings.get("base_url")
    try:
        models = ollama_models(
            base_url,
            min(int(settings.get("timeout_seconds") or 120), 30),
        )
        return jsonify({"ok": True, "models": models})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "models": []}), 502



@app.post("/api/markdown/render")
def api_render_markdown():
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or "")
    return jsonify({"ok": True, "html": str(render_markdown_html(content))})


@app.get("/knowledge/<int:item_id>")
def knowledge_document(item_id):
    conn = db()
    item = conn.execute(
        """
        SELECT id, title, category, content, created_at, updated_at
        FROM qb_knowledge
        WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    conn.close()
    if not item:
        return Response("Knowledge document not found.", status=404, mimetype="text/plain")
    return render_template(
        "knowledge_document.html",
        item=dict(item),
        rendered=render_markdown_html(item["content"]),
    )


@app.post("/knowledge/<int:item_id>/edit")
def edit_knowledge_document(item_id):
    title = (request.form.get("title") or "").strip()
    category = (request.form.get("category") or "general").strip()
    content = request.form.get("content") or ""
    if not title or not content.strip():
        flash("Knowledge title and Markdown content are required.", "error")
        return redirect(url_for("knowledge_document", item_id=item_id))

    conn = db()
    item = conn.execute("SELECT id FROM qb_knowledge WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return Response("Knowledge document not found.", status=404, mimetype="text/plain")
    conn.execute(
        """
        UPDATE qb_knowledge
        SET title = ?, category = ?, content = ?, updated_at = ?
        WHERE id = ?
        """,
        (title, category, content, now_iso(), item_id),
    )
    conn.commit()
    conn.close()
    flash("Knowledge document updated.", "success")
    return redirect(url_for("knowledge_document", item_id=item_id))


@app.route("/ai-skills")
def ai_skills():
    conn = db()
    skills = [dict(row) for row in ai_skill_rows(conn)]
    proposal_rows = conn.execute(
        """
        SELECT id, title, summary, skill_key, model, operations_json, status, created_at, reviewed_at
        FROM qb_schema_proposals
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()
    proposals = []
    for row in proposal_rows:
        try:
            operations = json.loads(row["operations_json"])
        except Exception:
            operations = []
        checked = validate_schema_operations(conn, operations) if row["status"] == "proposed" else []
        proposals.append(
            {
                **dict(row),
                "operations": operations,
                "checked": checked,
                "valid_now": all(item["valid"] for item in checked) if checked else row["status"] != "proposed",
            }
        )
    table_count = conn.execute("SELECT COUNT(*) n FROM qb_tables").fetchone()["n"]
    field_count = conn.execute("SELECT COUNT(*) n FROM qb_columns").fetchone()["n"]
    conn.close()
    return render_template(
        "ai_skills.html",
        skills=skills,
        proposals=proposals,
        table_count=table_count,
        field_count=field_count,
    )



@app.post("/ai-skills/create")
def create_ai_skill():
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    instructions = (request.form.get("instructions") or "").strip()
    if not name or not instructions:
        flash("Custom skill name and instructions are required.", "error")
        return redirect(url_for("ai_skills"))

    skill_key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:100] or "custom-skill"
    conn = db()
    base_key = skill_key
    suffix = 2
    while conn.execute("SELECT 1 FROM qb_ai_skills WHERE skill_key = ?", (skill_key,)).fetchone():
        skill_key = f"{base_key}-{suffix}"
        suffix += 1

    conn.execute(
        """
        INSERT INTO qb_ai_skills
        (skill_key, name, description, instructions, enabled, builtin, updated_at)
        VALUES (?, ?, ?, ?, 1, 0, ?)
        """,
        (skill_key, name[:180], description[:1000], instructions, now_iso()),
    )
    conn.commit()
    conn.close()
    flash(f'Custom AI skill "{name}" created and enabled.', "success")
    return redirect(url_for("ai_skills"))


@app.post("/ai-skills/<int:skill_id>/delete")
def delete_ai_skill(skill_id):
    conn = db()
    row = conn.execute(
        "SELECT name, builtin FROM qb_ai_skills WHERE id = ?",
        (skill_id,),
    ).fetchone()
    if not row:
        conn.close()
        return Response("AI skill not found.", status=404, mimetype="text/plain")
    if row["builtin"]:
        conn.close()
        flash("Built-in AI skills cannot be deleted; disable them instead.", "error")
        return redirect(url_for("ai_skills"))

    conn.execute("DELETE FROM qb_ai_skills WHERE id = ?", (skill_id,))
    conn.commit()
    conn.close()
    flash(f'Custom AI skill "{row["name"]}" deleted.', "success")
    return redirect(url_for("ai_skills"))


@app.post("/ai-skills/<int:skill_id>/toggle")
def toggle_ai_skill(skill_id):
    conn = db()
    row = conn.execute("SELECT enabled, name FROM qb_ai_skills WHERE id = ?", (skill_id,)).fetchone()
    if not row:
        conn.close()
        return Response("AI skill not found.", status=404, mimetype="text/plain")
    enabled = 0 if row["enabled"] else 1
    conn.execute(
        "UPDATE qb_ai_skills SET enabled = ?, updated_at = ? WHERE id = ?",
        (enabled, now_iso(), skill_id),
    )
    conn.commit()
    conn.close()
    flash(f'{row["name"]} {"enabled" if enabled else "disabled"}.', "success")
    return redirect(url_for("ai_skills"))


@app.post("/ai-skills/<int:skill_id>/update")
def update_ai_skill(skill_id):
    instructions = (request.form.get("instructions") or "").strip()
    if not instructions:
        flash("Skill instructions cannot be empty.", "error")
        return redirect(url_for("ai_skills"))
    conn = db()
    row = conn.execute("SELECT id, name FROM qb_ai_skills WHERE id = ?", (skill_id,)).fetchone()
    if not row:
        conn.close()
        return Response("AI skill not found.", status=404, mimetype="text/plain")
    conn.execute(
        "UPDATE qb_ai_skills SET instructions = ?, updated_at = ? WHERE id = ?",
        (instructions, now_iso(), skill_id),
    )
    conn.commit()
    conn.close()
    flash(f'{row["name"]} instructions updated.', "success")
    return redirect(url_for("ai_skills"))


@app.post("/schema/proposals/create")
def create_schema_proposal():
    request_text = (request.form.get("request_text") or "").strip()
    selected_skills = request.form.getlist("skills")
    conn = db()
    try:
        proposal_id, valid_count, invalid_count = create_ai_schema_proposal(
            conn,
            request_text or "Review the current schema and knowledge and propose useful improvements.",
            selected_skills,
        )
        conn.commit()
        flash(
            f"AI schema proposal #{proposal_id} created with {valid_count} valid operation(s)"
            + (f"; {invalid_count} invalid AI operation(s) were discarded." if invalid_count else "."),
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"AI schema proposal failed: {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("ai_skills") + "#proposals")


@app.post("/schema/proposals/<int:proposal_id>/apply")
def apply_schema_proposal(proposal_id):
    conn = db()
    try:
        proposal = conn.execute(
            "SELECT * FROM qb_schema_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        if not proposal:
            raise ValueError("Schema proposal was not found.")
        if proposal["status"] != "proposed":
            raise ValueError(f"Schema proposal is already {proposal['status']}.")

        operations = json.loads(proposal["operations_json"])
        applied = apply_schema_operations(conn, operations)
        conn.execute(
            """
            UPDATE qb_schema_proposals
            SET status = 'applied', reviewed_at = ?
            WHERE id = ?
            """,
            (now_iso(), proposal_id),
        )
        conn.commit()
        flash(
            f"Applied schema proposal #{proposal_id}: {len(applied)} operation(s).",
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"Could not apply schema proposal: {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("ai_skills") + "#proposals")


@app.post("/schema/proposals/<int:proposal_id>/reject")
def reject_schema_proposal(proposal_id):
    conn = db()
    proposal = conn.execute(
        "SELECT status FROM qb_schema_proposals WHERE id = ?",
        (proposal_id,),
    ).fetchone()
    if not proposal:
        conn.close()
        return Response("Schema proposal not found.", status=404, mimetype="text/plain")
    if proposal["status"] == "proposed":
        conn.execute(
            """
            UPDATE qb_schema_proposals
            SET status = 'rejected', reviewed_at = ?
            WHERE id = ?
            """,
            (now_iso(), proposal_id),
        )
        conn.commit()
        flash(f"Schema proposal #{proposal_id} rejected.", "success")
    else:
        flash(f"Schema proposal is already {proposal['status']}.", "error")
    conn.close()
    return redirect(url_for("ai_skills") + "#proposals")



@app.post("/relationships/clear-auto")
def clear_auto_relationships():
    conn = db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) n FROM qb_relationships WHERE source = 'auto'"
        ).fetchone()["n"]
        conn.execute("DELETE FROM qb_relationships WHERE source = 'auto'")
        conn.commit()
        flash(
            f"Cleared {count} auto-generated relationship(s). "
            "AI, approved, imported and manual links were preserved.",
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"Could not clear auto-generated links: {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("knowledge") + "#relationships")


@app.post("/relationships/auto-inference")
def set_auto_relationship_inference():
    enabled = (request.form.get("enabled") or "0") == "1"
    conn = db()
    try:
        conn.execute(
            """
            UPDATE qb_relationship_settings
            SET auto_inference_enabled = ?, updated_at = ?
            WHERE id = 1
            """,
            (1 if enabled else 0, now_iso()),
        )
        created = 0
        if enabled:
            created = infer_relationships(conn, force=True)
        conn.commit()
        if enabled:
            flash(
                f"Automatic heuristic relationship inference enabled. "
                f"{created} auto relationship(s) generated from the current schema.",
                "success",
            )
        else:
            flash(
                "Automatic heuristic relationship inference disabled. "
                "Existing auto links were left in place until you clear them.",
                "success",
            )
    except Exception as exc:
        conn.rollback()
        flash(f"Could not update automatic relationship inference: {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("knowledge") + "#relationships")


@app.route("/knowledge")
def knowledge():
    conn = db()
    items = [dict(row) for row in knowledge_rows(conn)]
    relationships = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                r.id, r.confidence, r.source, r.notes,
                lt.table_name left_table, lc.column_name left_column,
                rt.table_name right_table, rc.column_name right_column
            FROM qb_relationships r
            JOIN qb_tables lt ON lt.id = r.left_table_id
            JOIN qb_columns lc ON lc.id = r.left_column_id
            JOIN qb_tables rt ON rt.id = r.right_table_id
            JOIN qb_columns rc ON rc.id = r.right_column_id
            ORDER BY r.source DESC, r.confidence DESC, r.id
            """
        ).fetchall()
    ]
    table_count = conn.execute("SELECT COUNT(*) n FROM qb_tables").fetchone()["n"]
    column_count = conn.execute("SELECT COUNT(*) n FROM qb_columns").fetchone()["n"]

    relationship_source_counts = {
        row["source"]: row["n"]
        for row in conn.execute(
            """
            SELECT source, COUNT(*) n
            FROM qb_relationships
            GROUP BY source
            ORDER BY source
            """
        ).fetchall()
    }
    auto_link_count = int(relationship_source_counts.get("auto", 0))
    auto_inference_enabled = auto_relationship_inference_enabled(conn)

    manifest_path = BASE_DIR / "knowledge" / "manifest.json"
    pack_info = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = manifest.get("entries", [])
            titles = [
                str(entry.get("title") or "").strip()
                for entry in entries
                if isinstance(entry, dict) and entry.get("title")
            ]
            imported_count = 0
            for title in titles:
                if conn.execute(
                    "SELECT 1 FROM qb_knowledge WHERE lower(title) = lower(?)",
                    (title,),
                ).fetchone():
                    imported_count += 1
            pack_info = {
                "name": manifest.get("pack") or "Built-in knowledge pack",
                "entry_count": len(entries),
                "imported_count": imported_count,
            }
        except Exception:
            pack_info = None

    conn.close()
    return render_template(
        "knowledge.html",
        items=items,
        relationships=relationships,
        table_count=table_count,
        column_count=column_count,
        pack_info=pack_info,
        relationship_source_counts=relationship_source_counts,
        auto_link_count=auto_link_count,
        auto_inference_enabled=auto_inference_enabled,
    )



@app.post("/knowledge/import-pack")
def import_knowledge_pack():
    conn = db()
    try:
        result = import_builtin_knowledge_pack(conn)
        conn.commit()
        flash(
            f'{result["pack"]} imported: '
            f'{result["added"]} added, {result["updated"]} updated'
            + (f', {result["skipped"]} skipped.' if result["skipped"] else '.'),
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"Knowledge pack import failed: {exc}", "error")
    finally:
        conn.close()

    return redirect(url_for("knowledge"))


@app.post("/knowledge")
def add_knowledge():
    title = (request.form.get("title") or "").strip()
    category = (request.form.get("category") or "general").strip()
    content = (request.form.get("content") or "").strip()

    if not title or not content:
        flash("Knowledge title and content are required.", "error")
        return redirect(url_for("knowledge"))

    conn = db()
    conn.execute(
        """
        INSERT INTO qb_knowledge(title, category, content, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, category, content, now_iso(), now_iso()),
    )
    conn.commit()
    conn.close()
    flash("Knowledge item added.", "success")
    return redirect(url_for("knowledge"))


@app.post("/knowledge/<int:item_id>/delete")
def delete_knowledge(item_id):
    conn = db()
    conn.execute("DELETE FROM qb_knowledge WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    flash("Knowledge item deleted.", "success")
    return redirect(url_for("knowledge"))


@app.post("/relationships/guess")
def guess_relationships():
    conn = db()
    try:
        table_count = conn.execute("SELECT COUNT(*) n FROM qb_tables").fetchone()["n"]
        field_count = conn.execute("SELECT COUNT(*) n FROM qb_columns").fetchone()["n"]
        if not table_count or not field_count:
            raise ValueError("Capture a schema with fields before asking the LLM to infer links.")

        proposal_id, valid_count, invalid_count = create_ai_schema_proposal(
            conn,
            "Analyse the current schema and knowledge. Propose the most useful missing equality relationships only. Do not propose other structural changes.",
            ["relationship-analysis", "knowledge-grounded-schema"],
        )
        conn.commit()
        flash(
            f"Relationship proposal #{proposal_id} created with {valid_count} link operation(s)"
            + (f"; {invalid_count} invalid suggestion(s) were discarded." if invalid_count else "."),
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"LLM link analysis failed: {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("ai_skills") + "#proposals")


@app.route("/chat")
def schema_chat():
    conn = db()
    settings = get_llm_settings(conn)
    messages = []
    for row in conn.execute(
        """
        SELECT id, role, content, created_at
        FROM qb_chat_messages
        ORDER BY id
        LIMIT 200
        """
    ).fetchall():
        item = dict(row)
        item["rendered"] = render_markdown_html(item["content"]) if item["role"] == "assistant" else None
        messages.append(item)
    table_count = conn.execute("SELECT COUNT(*) n FROM qb_tables").fetchone()["n"]
    knowledge_count = conn.execute("SELECT COUNT(*) n FROM qb_knowledge").fetchone()["n"]
    conn.close()
    return render_template(
        "chat.html",
        messages=messages,
        settings=settings,
        table_count=table_count,
        knowledge_count=knowledge_count,
    )


@app.post("/api/chat")
def api_schema_chat():
    body = request.get_json(silent=True) or {}
    question = (body.get("message") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "Enter a question."}), 400

    conn = db()
    try:
        context = schema_context_text(conn, include_relationships=True)
        active_skills = ai_skill_rows(conn, enabled_only=True)
        skills_context = ai_skill_context(active_skills)

        system = """You are QueryBridge, a local schema assistant.
You analyse the schema CAPTURED LOCALLY inside QueryBridge. You do not connect to Databricks and you do not claim to have queried live Databricks data.

Use the supplied QueryBridge schema, relationships, Markdown knowledge and enabled AI skills.
You have one read-only analysis tool named local_schema_select. It runs SELECT statements only against an isolated in-memory copy of QueryBridge's local schema metadata.

Use local_schema_select whenever querying the local metadata would improve accuracy—for example:
- find all fields with names containing supplier, project, PO, PR, WBS or dates;
- compare data types across tables;
- count tables or fields;
- find repeated field names;
- inspect inferred/AI/manual relationships;
- search knowledge text;
- identify tables with no relationships;
- investigate likely join candidates.

You may run several SELECT statements before answering.

For every turn, return JSON only in one of these forms.

To run a local SELECT:
{
  "kind": "tool",
  "tool": "local_schema_select",
  "sql": "SELECT ...",
  "purpose": "short reason for this query"
}

To answer:
{
  "kind": "answer",
  "answer": "Markdown answer for the user"
}

Never request INSERT, UPDATE, DELETE, DDL or changes through local_schema_select.
Do not invent tables or fields. If evidence is missing, say so.
When drafting Databricks SQL for the user, clearly distinguish that draft SQL from the local SQLite analysis queries used internally.
"""

        history = conn.execute(
            """
            SELECT role, content
            FROM qb_chat_messages
            ORDER BY id DESC
            LIMIT 12
            """
        ).fetchall()
        history = list(reversed(history))

        messages = [
            {
                "role": "system",
                "content": (
                    system
                    + "\n\nENABLED AI SKILLS\n"
                    + skills_context
                    + "\n\n"
                    + local_schema_sql_reference()
                    + "\n\nCAPTURED SCHEMA / RELATIONSHIP / KNOWLEDGE CONTEXT\n"
                    + context
                ),
            },
            *[
                {"role": row["role"], "content": row["content"]}
                for row in history
                if row["role"] in {"user", "assistant"}
            ],
            {"role": "user", "content": question},
        ]

        conn.execute(
            """
            INSERT INTO qb_chat_messages(role, content, created_at)
            VALUES ('user', ?, ?)
            """,
            (question, now_iso()),
        )

        answer, tool_runs = run_schema_chat_agent(conn, messages, max_tool_calls=6)

        conn.execute(
            """
            INSERT INTO qb_chat_messages(role, content, created_at)
            VALUES ('assistant', ?, ?)
            """,
            (answer, now_iso()),
        )
        conn.commit()

        return jsonify({
            "ok": True,
            "answer": answer,
            "html": str(render_markdown_html(answer)),
            "tool_runs": tool_runs,
        })
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        conn.close()


@app.post("/chat/clear")
def clear_schema_chat():
    conn = db()
    conn.execute("DELETE FROM qb_chat_messages")
    conn.commit()
    conn.close()
    flash("Schema chat cleared.", "success")
    return redirect(url_for("schema_chat"))


@app.post("/capture/tables")
def capture_tables():
    raw_text = request.form.get("raw_text", "")
    catalog = request.form.get("catalog", "")
    schema_name = request.form.get("schema_name", "")
    try:
        added, updated = import_table_list(raw_text, catalog, schema_name)
        flash(f"Imported table list: {added} added, {updated} updated.", "success")
    except Exception as exc:
        flash(str(exc), "error")
    return redirect(url_for("index"))


@app.post("/capture/table/<int:table_id>")
def capture_table(table_id):
    raw_text = request.form.get("raw_text", "")
    try:
        count = import_description(table_id, raw_text)
        flash(f"Stored {count} columns.", "success")
    except Exception as exc:
        flash(str(exc), "error")
    return redirect(url_for("index") + f"#table-{table_id}")


@app.post("/reset")
def reset_metadata():
    conn = db()
    conn.execute("DELETE FROM qb_relationships")
    conn.execute("DELETE FROM qb_columns")
    conn.execute("DELETE FROM qb_tables")
    conn.execute("DELETE FROM qb_imports")
    conn.execute("DELETE FROM qb_knowledge")
    conn.execute("DELETE FROM qb_chat_messages")
    conn.commit()
    conn.close()
    flash("Working metadata cleared. Saved schema snapshots were kept.", "success")
    return redirect(url_for("index"))


def match_local_table(conn, table_name, schema_name=None, catalog=None):
    if not table_name:
        return None
    sql = """
        SELECT *
        FROM qb_tables
        WHERE lower(table_name) = lower(?)
    """
    params = [table_name]
    if schema_name:
        sql += " AND lower(COALESCE(schema_name,'')) = lower(?)"
        params.append(schema_name)
    if catalog:
        sql += " AND lower(COALESCE(catalog,'')) = lower(?)"
        params.append(catalog)
    sql += " ORDER BY id LIMIT 1"
    return conn.execute(sql, params).fetchone()


def local_field_exists(conn, table_id, column_name):
    if not table_id or not column_name:
        return None
    return conn.execute(
        """
        SELECT id, column_name, data_type
        FROM qb_columns
        WHERE table_id = ? AND lower(column_name) = lower(?)
        LIMIT 1
        """,
        (table_id, column_name),
    ).fetchone()


def imported_join_relationship_candidates(conn, select_expr, alias_map):
    candidates = []
    seen = set()

    for join in select_expr.args.get("joins") or []:
        on_expr = join.args.get("on")
        if on_expr is None:
            continue

        for eq in on_expr.find_all(exp.EQ):
            left = eq.left
            right = eq.right
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue

            left_source = alias_map.get((left.table or "").casefold())
            right_source = alias_map.get((right.table or "").casefold())
            if not left_source or not right_source:
                continue
            if not left_source.get("table_id") or not right_source.get("table_id"):
                continue
            if left_source["table_id"] == right_source["table_id"]:
                continue

            left_field = local_field_exists(conn, left_source["table_id"], left.name)
            right_field = local_field_exists(conn, right_source["table_id"], right.name)
            if not left_field or not right_field:
                continue

            pair = tuple(sorted((left_field["id"], right_field["id"])))
            if pair in seen:
                continue
            seen.add(pair)

            existing = conn.execute(
                """
                SELECT id, source, confidence
                FROM qb_relationships
                WHERE (left_column_id = ? AND right_column_id = ?)
                   OR (left_column_id = ? AND right_column_id = ?)
                LIMIT 1
                """,
                (
                    left_field["id"],
                    right_field["id"],
                    right_field["id"],
                    left_field["id"],
                ),
            ).fetchone()

            if existing:
                continue

            candidates.append(
                {
                    "left_table": left_source["table_name"],
                    "left_schema": left_source.get("schema_name"),
                    "left_catalog": left_source.get("catalog"),
                    "left_column": left_field["column_name"],
                    "right_table": right_source["table_name"],
                    "right_schema": right_source.get("schema_name"),
                    "right_catalog": right_source.get("catalog"),
                    "right_column": right_field["column_name"],
                    "confidence": 1.0,
                    "reason": "Observed equality JOIN in imported Databricks SQL.",
                }
            )

    return candidates


def parse_databricks_query_to_builder(conn, raw_sql):
    raw_sql = (raw_sql or "").strip()
    if not raw_sql:
        raise ValueError("Paste a Databricks SELECT statement first.")

    try:
        tree = sqlglot.parse_one(raw_sql, read="databricks")
    except Exception as exc:
        raise ValueError(f"Could not parse Databricks SQL: {exc}") from exc

    select_expr = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select_expr is None:
        raise ValueError("QueryBridge can currently import SELECT queries only.")

    warnings = []
    sources = []
    alias_map = {}

    def source_record(source_expr, role, join_sql=None):
        table_id = None
        catalog = None
        schema_name = None
        table_name = None
        alias = None
        matched = False
        source_sql = source_expr.sql(dialect="databricks")

        if isinstance(source_expr, exp.Table):
            table_name = source_expr.name
            schema_name = source_expr.db or None
            catalog = source_expr.catalog or None
            alias = source_expr.alias or table_name
            row = match_local_table(conn, table_name, schema_name, catalog)
            if row is None and (schema_name or catalog):
                row = match_local_table(conn, table_name)
            if row:
                table_id = row["id"]
                catalog = row["catalog"]
                schema_name = row["schema_name"]
                table_name = row["table_name"]
                matched = True
        else:
            alias = getattr(source_expr, "alias", None) or None

        record = {
            "role": role,
            "table_id": table_id,
            "catalog": catalog,
            "schema_name": schema_name,
            "table_name": table_name,
            "alias": alias,
            "matched": matched,
            "source_sql": source_sql,
        }
        if join_sql is not None:
            record["join_sql"] = join_sql

        if alias:
            alias_map[str(alias).casefold()] = record
        if table_name:
            alias_map[str(table_name).casefold()] = record
        return record

    from_expr = select_expr.args.get("from_")
    if from_expr and from_expr.this is not None:
        base = source_record(from_expr.this, "from")
        sources.append(base)
        if not base["matched"]:
            warnings.append(
                f"FROM source '{base['source_sql']}' is not matched to the stored local schema."
            )
    else:
        warnings.append("The imported SELECT has no simple FROM source.")

    for join in select_expr.args.get("joins") or []:
        join_source = join.this
        record = source_record(
            join_source,
            "join",
            join_sql=join.sql(dialect="databricks"),
        )
        sources.append(record)
        if not record["matched"]:
            warnings.append(
                f"JOIN source '{record['source_sql']}' is not matched to the stored local schema."
            )

    fields = []
    unmatched_fields = []

    matched_sources = [item for item in sources if item.get("table_id")]

    def column_ref_payload(column):
        if not isinstance(column, exp.Column):
            return None
        qualifier = (column.table or "").casefold()
        source = alias_map.get(qualifier) if qualifier else None
        if source is None and len(matched_sources) == 1:
            source = matched_sources[0]
        return {
            "alias": column.table or (source.get("alias") if source else None),
            "column": column.name,
            "table_id": source.get("table_id") if source else None,
            "table_name": source.get("table_name") if source else None,
        }

    structured_joins = []
    for join_index, join in enumerate(select_expr.args.get("joins") or [], start=1):
        target_alias = None
        if isinstance(join.this, exp.Table):
            target_alias = join.this.alias or join.this.name
        else:
            target_alias = getattr(join.this, "alias", None) or None

        join_columns = []
        on_expr = join.args.get("on")
        if on_expr is not None:
            for column in on_expr.find_all(exp.Column):
                payload = column_ref_payload(column)
                if payload:
                    join_columns.append(payload)

        pairs = []
        if on_expr is not None:
            for eq in on_expr.find_all(exp.EQ):
                if isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column):
                    left_payload = column_ref_payload(eq.left)
                    right_payload = column_ref_payload(eq.right)
                    if left_payload and right_payload:
                        pairs.append(
                            {
                                "left": left_payload,
                                "right": right_payload,
                                "sql": eq.sql(dialect="databricks"),
                            }
                        )

        join_type_parts = [
            str(join.args.get("side") or "").upper(),
            str(join.args.get("kind") or "").upper(),
        ]
        join_type = " ".join(part for part in join_type_parts if part).strip()
        if not join_type:
            join_type = "INNER"

        structured_joins.append(
            {
                "index": join_index,
                "join_type": join_type,
                "target_alias": target_alias,
                "target_table_id": alias_map.get((target_alias or "").casefold(), {}).get("table_id"),
                "on_sql": on_expr.sql(dialect="databricks") if on_expr is not None else None,
                "columns": join_columns,
                "pairs": pairs,
            }
        )

    def split_and_predicates(expression):
        if isinstance(expression, exp.And):
            return split_and_predicates(expression.left) + split_and_predicates(expression.right)
        return [expression]

    criteria = []
    where_expr = select_expr.args.get("where")
    if where_expr is not None and where_expr.this is not None:
        for predicate in split_and_predicates(where_expr.this):
            refs = []
            for column in predicate.find_all(exp.Column):
                payload = column_ref_payload(column)
                if payload:
                    refs.append(payload)
            criteria.append(
                {
                    "sql": predicate.sql(dialect="databricks"),
                    "columns": refs,
                }
            )

    for projection in select_expr.expressions:
        output_alias = projection.alias if isinstance(projection, exp.Alias) else None
        core = projection.this if isinstance(projection, exp.Alias) else projection

        if isinstance(core, exp.Column) and not isinstance(core.this, exp.Star):
            qualifier = (core.table or "").casefold()
            source = alias_map.get(qualifier) if qualifier else None

            if source is None and len(matched_sources) == 1:
                source = matched_sources[0]
            elif source is None and not qualifier:
                possible = [
                    item
                    for item in matched_sources
                    if local_field_exists(conn, item["table_id"], core.name)
                ]
                if len(possible) == 1:
                    source = possible[0]

            if source and source.get("table_id"):
                field = local_field_exists(conn, source["table_id"], core.name)
                if field:
                    fields.append(
                        {
                            "kind": "field",
                            "table_id": source["table_id"],
                            "column_name": field["column_name"],
                            "source_alias": source.get("alias"),
                            "output_alias": output_alias,
                            "imported": True,
                        }
                    )
                    continue

            unmatched_fields.append(projection.sql(dialect="databricks"))

        fields.append(
            {
                "kind": "expression",
                "sql": projection.sql(dialect="databricks"),
                "label": output_alias or projection.alias_or_name or projection.sql(dialect="databricks"),
                "imported": True,
            }
        )

    modifiers = {}
    for key in ("where", "group", "having", "qualify", "order", "limit", "offset"):
        value = select_expr.args.get(key)
        modifiers[key] = value.sql(dialect="databricks") if value is not None else None

    with_expr = select_expr.args.get("with_")
    with_sql = with_expr.sql(dialect="databricks") if with_expr is not None else None

    if unmatched_fields:
        warnings.append(
            f"{len(unmatched_fields)} selected expression(s) could not be mapped to a stored field and were preserved as raw expressions."
        )

    relationship_candidates = imported_join_relationship_candidates(
        conn, select_expr, alias_map
    )

    state = {
        "raw_sql": raw_sql,
        "with_sql": with_sql,
        "distinct": bool(select_expr.args.get("distinct")),
        "sources": sources,
        "joins": structured_joins,
        "criteria": criteria,
        "modifiers": modifiers,
        "warnings": warnings,
    }

    return {
        "fields": fields,
        "state": state,
        "warnings": warnings,
        "unmatched_fields": unmatched_fields,
        "relationship_candidates": relationship_candidates,
    }


def create_imported_join_proposal(conn, candidates):
    operations = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        operations.append(
            {
                "action": "add_relationship",
                "left_table": item.get("left_table"),
                "left_schema": item.get("left_schema"),
                "left_catalog": item.get("left_catalog"),
                "left_column": item.get("left_column"),
                "right_table": item.get("right_table"),
                "right_schema": item.get("right_schema"),
                "right_catalog": item.get("right_catalog"),
                "right_column": item.get("right_column"),
                "confidence": 1.0,
                "reason": item.get("reason") or "Observed JOIN in imported SQL.",
            }
        )

    checked = validate_schema_operations(conn, operations)
    valid = [item["operation"] for item in checked if item["valid"]]
    if not valid:
        raise ValueError("No new valid relationships were found in the imported SQL.")

    settings = get_llm_settings(conn)
    cursor = conn.execute(
        """
        INSERT INTO qb_schema_proposals
        (title, summary, skill_key, model, operations_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'proposed', ?)
        """,
        (
            "Relationships observed in imported SQL",
            "These links were observed directly in a pasted Databricks SELECT and are proposed for review before becoming trusted QueryBridge relationships.",
            "imported-sql",
            settings.get("model"),
            json.dumps(valid, ensure_ascii=False),
            now_iso(),
        ),
    )
    return cursor.lastrowid, len(valid)


def build_sql_from_imported_state(conn, fields, imported_state):
    sources = imported_state.get("sources") or []
    modifiers = imported_state.get("modifiers") or {}
    warnings = list(imported_state.get("warnings") or [])

    if not sources:
        raise ValueError("Imported query state has no FROM source.")

    aliases = {}
    source_table_ids = []
    for source in sources:
        table_id = source.get("table_id")
        if table_id:
            aliases[int(table_id)] = source.get("alias") or source.get("table_name")
            source_table_ids.append(int(table_id))

    selected_table_ids = []
    for field in fields:
        if field.get("kind") == "expression":
            continue
        try:
            table_id = int(field["table_id"])
        except Exception:
            continue
        if table_id not in selected_table_ids:
            selected_table_ids.append(table_id)

    next_alias = 1
    used_aliases = {str(value) for value in aliases.values() if value}
    for table_id in selected_table_ids:
        if table_id in aliases:
            continue
        while f"qb{next_alias}" in used_aliases:
            next_alias += 1
        alias = f"qb{next_alias}"
        next_alias += 1
        aliases[table_id] = alias
        used_aliases.add(alias)

    selected_parts = []
    for field in fields:
        if field.get("kind") == "expression":
            sql_text = (field.get("sql") or "").strip()
            if sql_text:
                selected_parts.append(sql_text)
            continue

        table_id = int(field["table_id"])
        column_name = str(field["column_name"])
        row = conn.execute(
            """
            SELECT t.*, c.column_name
            FROM qb_tables t
            JOIN qb_columns c ON c.table_id = t.id
            WHERE t.id = ? AND lower(c.column_name) = lower(?)
            LIMIT 1
            """,
            (table_id, column_name),
        ).fetchone()
        if not row:
            continue

        alias = aliases.get(table_id)
        expression_sql = (
            f"{quote_ident(alias)}.{quote_ident(row['column_name'])}"
            if alias
            else quote_ident(row["column_name"])
        )

        output_alias = (field.get("output_alias") or "").strip()
        if output_alias:
            expression_sql += f" AS {quote_ident(output_alias)}"
        selected_parts.append(expression_sql)

    if not selected_parts:
        selected_parts = ["*"]

    base = sources[0]
    sql_lines = []
    prefix = imported_state.get("with_sql")
    if prefix:
        sql_lines.append(prefix)

    select_head = "SELECT DISTINCT" if imported_state.get("distinct") else "SELECT"
    sql_lines.extend(
        [
            select_head,
            "    " + ",\n    ".join(selected_parts),
            f"FROM {base.get('source_sql')}",
        ]
    )

    joined_ids = set()
    if base.get("table_id"):
        joined_ids.add(int(base["table_id"]))

    for source in sources[1:]:
        join_sql = source.get("join_sql")
        if join_sql:
            sql_lines.append(join_sql)
        if source.get("table_id"):
            joined_ids.add(int(source["table_id"]))

    for table_id in selected_table_ids:
        if table_id in joined_ids:
            continue

        table = conn.execute(
            "SELECT * FROM qb_tables WHERE id = ?",
            (table_id,),
        ).fetchone()
        if not table:
            continue

        placeholders = ",".join("?" for _ in joined_ids) if joined_ids else ""
        rel = None
        if joined_ids:
            params = [table_id, *joined_ids, *joined_ids, table_id]
            rel = conn.execute(
                f"""
                SELECT r.*, lc.column_name left_name, rc.column_name right_name
                FROM qb_relationships r
                JOIN qb_columns lc ON lc.id = r.left_column_id
                JOIN qb_columns rc ON rc.id = r.right_column_id
                WHERE (r.left_table_id = ? AND r.right_table_id IN ({placeholders}))
                   OR (r.left_table_id IN ({placeholders}) AND r.right_table_id = ?)
                ORDER BY
                    CASE r.source
                        WHEN 'manual' THEN 1
                        WHEN 'ai-approved' THEN 2
                        WHEN 'llm' THEN 3
                        WHEN 'auto' THEN 4
                        ELSE 5
                    END,
                    r.confidence DESC
                LIMIT 1
                """,
                params,
            ).fetchone()

        new_alias = aliases[table_id]

        if rel:
            if rel["left_table_id"] == table_id:
                new_col = rel["left_name"]
                existing_id = rel["right_table_id"]
                existing_col = rel["right_name"]
            else:
                new_col = rel["right_name"]
                existing_id = rel["left_table_id"]
                existing_col = rel["left_name"]

            existing_alias = aliases.get(existing_id)
            if existing_alias:
                sql_lines.append(
                    f"INNER JOIN {qualified_name(table)} AS {quote_ident(new_alias)}"
                )
                sql_lines.append(
                    f"    ON {quote_ident(new_alias)}.{quote_ident(new_col)} = "
                    f"{quote_ident(existing_alias)}.{quote_ident(existing_col)}"
                )
            else:
                sql_lines.append(
                    f"CROSS JOIN {qualified_name(table)} AS {quote_ident(new_alias)}"
                )
                warnings.append(
                    f"No usable alias was available for the detected relationship to {table['table_name']}; CROSS JOIN used."
                )
        else:
            sql_lines.append(
                f"CROSS JOIN {qualified_name(table)} AS {quote_ident(new_alias)}"
            )
            warnings.append(
                f"No stored relationship was found for added table {table['table_name']}; CROSS JOIN used."
            )

        joined_ids.add(table_id)

    for key in ("where", "group", "having", "qualify", "order", "limit", "offset"):
        value = modifiers.get(key)
        if value:
            sql_lines.append(value)

    sql_lines.append(";")
    return "\n".join(sql_lines), warnings


@app.route("/builder")
def builder():
    conn = db()
    tables = conn.execute(
        "SELECT * FROM qb_tables ORDER BY COALESCE(schema_name,''), table_name"
    ).fetchall()
    payload = []
    for table in tables:
        cols = conn.execute(
            """
            SELECT id, column_name, data_type, ordinal_position
            FROM qb_columns
            WHERE table_id = ?
            ORDER BY ordinal_position
            """,
            (table["id"],),
        ).fetchall()
        if cols:
            payload.append(
                {
                    **dict(table),
                    "qualified_name": qualified_name(table),
                    "columns": [dict(c) for c in cols],
                }
            )
    conn.close()
    return render_template("builder.html", tables=payload)



@app.post("/api/import-sql")
def api_import_sql():
    body = request.get_json(silent=True) or {}
    conn = db()
    try:
        parsed = parse_databricks_query_to_builder(conn, body.get("sql"))
        return jsonify({"ok": True, **parsed})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@app.post("/api/import-sql/relationship-proposal")
def api_import_sql_relationship_proposal():
    body = request.get_json(silent=True) or {}
    conn = db()
    try:
        proposal_id, count = create_imported_join_proposal(
            conn, body.get("candidates") or []
        )
        conn.commit()
        return jsonify({"ok": True, "proposal_id": proposal_id, "count": count})
    except Exception as exc:
        conn.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        conn.close()


@app.get("/api/schema")
def api_schema():
    conn = db()
    tables = conn.execute("SELECT * FROM qb_tables ORDER BY table_name").fetchall()
    result = []
    for table in tables:
        cols = conn.execute(
            "SELECT * FROM qb_columns WHERE table_id = ? ORDER BY ordinal_position",
            (table["id"],),
        ).fetchall()
        item = dict(table)
        item["qualified_name"] = qualified_name(table)
        item["columns"] = [dict(c) for c in cols]
        result.append(item)
    relationships = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM qb_relationships ORDER BY confidence DESC, id"
        ).fetchall()
    ]
    conn.close()
    return jsonify({"tables": result, "relationships": relationships})


@app.post("/api/build-sql")
def api_build_sql():
    body = request.get_json(silent=True) or {}
    fields = body.get("fields", [])
    imported_state = body.get("imported_state")

    conn = db()
    if imported_state:
        try:
            sql_text, warnings = build_sql_from_imported_state(
                conn, fields, imported_state
            )
            conn.close()
            return jsonify({
                "sql": sql_text,
                "joins": [],
                "warnings": warnings,
                "imported": True,
            })
        except Exception as exc:
            conn.close()
            return jsonify({
                "sql": f"-- Could not rebuild imported query: {exc}",
                "joins": [],
                "warnings": [str(exc)],
                "imported": True,
            }), 400

    if not fields:
        conn.close()
        return jsonify({"sql": "-- Drag fields here to build a query.", "joins": []})
    resolved = []
    for field in fields:
        table_id = int(field["table_id"])
        column_name = str(field["column_name"])
        row = conn.execute(
            """
            SELECT t.*, c.id column_id, c.column_name, c.data_type
            FROM qb_tables t
            JOIN qb_columns c ON c.table_id = t.id
            WHERE t.id = ? AND c.column_name = ?
            """,
            (table_id, column_name),
        ).fetchone()
        if row:
            resolved.append(row)

    if not resolved:
        conn.close()
        return jsonify({"sql": "-- No valid fields selected.", "joins": []})

    table_order = []
    table_rows = {}
    for row in resolved:
        if row["id"] not in table_rows:
            table_rows[row["id"]] = row
            table_order.append(row["id"])

    aliases = {table_id: f"t{i + 1}" for i, table_id in enumerate(table_order)}
    select_parts = [
        f"{aliases[row['id']]}.{quote_ident(row['column_name'])}" for row in resolved
    ]

    base_id = table_order[0]
    sql_lines = [
        "SELECT",
        "    " + ",\n    ".join(select_parts),
        f"FROM {qualified_name(table_rows[base_id])} AS {aliases[base_id]}",
    ]

    joined = {base_id}
    join_notes = []

    for table_id in table_order[1:]:
        placeholders = ",".join("?" for _ in joined)
        params = [table_id, *joined, *joined, table_id]
        rel = conn.execute(
            f"""
            SELECT r.*,
                   lc.column_name left_name,
                   rc.column_name right_name
            FROM qb_relationships r
            JOIN qb_columns lc ON lc.id = r.left_column_id
            JOIN qb_columns rc ON rc.id = r.right_column_id
            WHERE (r.left_table_id = ? AND r.right_table_id IN ({placeholders}))
               OR (r.left_table_id IN ({placeholders}) AND r.right_table_id = ?)
            ORDER BY r.confidence DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        if rel:
            if rel["left_table_id"] == table_id:
                new_col = rel["left_name"]
                existing_table_id = rel["right_table_id"]
                existing_col = rel["right_name"]
            else:
                new_col = rel["right_name"]
                existing_table_id = rel["left_table_id"]
                existing_col = rel["left_name"]

            sql_lines.append(
                f"INNER JOIN {qualified_name(table_rows[table_id])} AS {aliases[table_id]}"
            )
            sql_lines.append(
                f"    ON {aliases[table_id]}.{quote_ident(new_col)} = "
                f"{aliases[existing_table_id]}.{quote_ident(existing_col)}"
            )
            join_notes.append(
                {
                    "table_id": table_id,
                    "joined_to": existing_table_id,
                    "left": new_col,
                    "right": existing_col,
                    "confidence": rel["confidence"],
                }
            )
        else:
            sql_lines.append(
                f"CROSS JOIN {qualified_name(table_rows[table_id])} AS {aliases[table_id]}"
            )
            join_notes.append(
                {
                    "table_id": table_id,
                    "warning": "No inferred relationship was available; CROSS JOIN used.",
                }
            )
        joined.add(table_id)

    sql_lines.append(";")
    conn.close()
    return jsonify({"sql": "\n".join(sql_lines), "joins": join_notes})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5086, debug=True)
