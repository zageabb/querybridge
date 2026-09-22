from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import requests
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


def infer_relationships(conn):
    conn.execute("DELETE FROM qb_relationships WHERE source = 'auto'")
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
                conn.execute(
                    """
                    INSERT OR IGNORE INTO qb_relationships
                    (left_table_id, left_column_id, right_table_id, right_column_id, confidence, source)
                    VALUES (?, ?, ?, ?, ?, 'auto')
                    """,
                    (lc["table_id"], lc["column_id"], rc["table_id"], rc["column_id"], confidence),
                )




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

        stored, skipped, _ = llm_guess_relationships(conn)
        conn.commit()
        flash(
            f"LLM relationship pass complete: {stored} stored/updated, {skipped} skipped.",
            "success",
        )
    except Exception as exc:
        conn.rollback()
        flash(f"LLM link analysis failed: {exc}", "error")
    finally:
        conn.close()
    return redirect(url_for("knowledge") + "#relationships")


@app.route("/chat")
def schema_chat():
    conn = db()
    settings = get_llm_settings(conn)
    messages = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, role, content, created_at
            FROM qb_chat_messages
            ORDER BY id
            LIMIT 200
            """
        ).fetchall()
    ]
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
        system = """You are QueryBridge, a local schema assistant.
Use only the supplied QueryBridge schema, relationships and knowledge for schema-specific claims.
Help the user understand tables, fields, likely joins, and draft Databricks SQL.
Do not invent tables or columns. If information is missing, say what metadata or knowledge would resolve it.
When you write SQL, prefer explicit JOIN clauses and fully qualified names when available."""

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
            {"role": "system", "content": system + "\n\n" + context},
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
        answer = call_llm(conn, messages)
        conn.execute(
            """
            INSERT INTO qb_chat_messages(role, content, created_at)
            VALUES ('assistant', ?, ?)
            """,
            (answer, now_iso()),
        )
        conn.commit()
        return jsonify({"ok": True, "answer": answer})
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
    if not fields:
        return jsonify({"sql": "-- Drag fields here to build a query.", "joins": []})

    conn = db()
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
