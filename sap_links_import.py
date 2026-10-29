"""Preview and import documented SAP S/4HANA links to local QueryBridge metadata.

Additive, idempotent and transactional: no Databricks access, no named schema
snapshots, no fabricated catalog/schema or field data types.
"""
from __future__ import annotations

from collections import defaultdict

FORMAT = "querybridge-sap-links"
APPLICATION = "SAP S/4HANA"
MAX_TABLES = 250
MAX_FIELDS = 1500
MAX_LINKS = 700


def clean(value, what, limit=200):
    if not isinstance(value, str):
        raise ValueError(f"{what} must be text.")
    value = value.strip()
    if not value or len(value) > limit or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"{what} must contain 1-{limit} printable characters.")
    return value


def normalise(document):
    if not isinstance(document, dict) or document.get("format") != FORMAT or document.get("format_version") != 1:
        raise ValueError("This is not a supported QueryBridge SAP links JSON file (format_version 1).")
    if document.get("application") != APPLICATION:
        raise ValueError("Application must be SAP S/4HANA for this importer.")
    tables = document.get("tables", [])
    links = document.get("links")
    if not isinstance(tables, list) or not isinstance(links, list):
        raise ValueError("The file must contain tables and links arrays.")
    if len(tables) > MAX_TABLES or len(links) > MAX_LINKS:
        raise ValueError("The file exceeds the table or link limit.")

    definitions = {}
    for i, item in enumerate(tables, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Table #{i} must be an object.")
        name = clean(item.get("name"), f"Table #{i} name")
        fields = item.get("fields", [])
        if not isinstance(fields, list):
            raise ValueError(f"Table {name}: fields must be an array.")
        entry = definitions.setdefault(name.casefold(), {"name": name, "fields": {}})
        for raw in fields:
            if isinstance(raw, str):
                field, dtype = clean(raw, "Field name"), None
            elif isinstance(raw, dict):
                field = clean(raw.get("name"), "Field name")
                dtype = raw.get("data_type")
                if dtype is not None:
                    dtype = clean(dtype, "Data type", 255)
            else:
                raise ValueError(f"Table {name}: fields must contain names or field objects.")
            previous = entry["fields"].get(field.casefold())
            if previous and previous["data_type"] and dtype and previous["data_type"] != dtype:
                raise ValueError(f"Conflicting field types supplied for {name}.{field}.")
            entry["fields"][field.casefold()] = {
                "name": field, "data_type": dtype or (previous or {}).get("data_type")
            }

    prepared_links = []
    seen_links = set()
    for i, item in enumerate(links, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Link #{i} must be an object.")
        endpoints = []
        for side in ("left", "right"):
            obj = item.get(side)
            if not isinstance(obj, dict):
                raise ValueError(f"Link #{i} {side} endpoint must be an object.")
            table = clean(obj.get("table"), f"Link #{i} {side} table")
            field = clean(obj.get("field"), f"Link #{i} {side} field")
            entry = definitions.setdefault(table.casefold(), {"name": table, "fields": {}})
            entry["fields"].setdefault(field.casefold(), {"name": field, "data_type": None})
            endpoints.append((table, field))
        if endpoints[0][0].casefold() == endpoints[1][0].casefold():
            raise ValueError(f"Link #{i} must connect two different tables.")
        link_key = tuple(sorted((t.casefold(), f.casefold()) for t, f in endpoints))
        if link_key in seen_links:
            raise ValueError(f"Link #{i} is a duplicate of an earlier link.")
        seen_links.add(link_key)
        confidence = item.get("confidence", 0.9)
        if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1:
            raise ValueError(f"Link #{i} confidence must be a number from 0 to 1.")
        reason = item.get("reason", "")
        if reason:
            reason = clean(reason, "Reason", 2000)
        prepared_links.append({
            "left": endpoints[0], "right": endpoints[1],
            "confidence": float(confidence),
            "reason": reason or "Imported from reviewed SAP S/4HANA relationship file.",
        })

    if not prepared_links and not definitions:
        raise ValueError("The SAP links file contains no tables, fields or links.")
    if len(definitions) > MAX_TABLES or sum(len(x["fields"]) for x in definitions.values()) > MAX_FIELDS:
        raise ValueError("The imported SAP subset exceeds the table/field limit.")
    return definitions, prepared_links


def select_table(conn, name):
    matches = conn.execute(
        "SELECT id,table_name,application_name,catalog,schema_name FROM qb_tables WHERE lower(table_name)=lower(?) ORDER BY id",
        (name,),
    ).fetchall()
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    labelled = [
        row for row in matches
        if (row["application_name"] or "").casefold() == APPLICATION.casefold()
    ]
    if len(labelled) == 1:
        return labelled[0]
    raise ValueError(
        f"Multiple captured tables are named {name}. Resolve the ambiguous table in Admin first; "
        "the importer will not guess which catalog/schema to use."
    )


def plan_import(conn, document):
    definitions, links = normalise(document)
    table_ids = {}
    new_tables, new_fields, new_links, existing_links = [], [], [], []
    fields_by_table = {}
    for name_key, entry in definitions.items():
        row = select_table(conn, entry["name"])
        table_ids[name_key] = row["id"] if row else None
        if row is None:
            new_tables.append(entry["name"])
            fields_by_table[name_key] = {}
        else:
            fields_by_table[name_key] = {
                r["column_name"].casefold(): r["id"]
                for r in conn.execute(
                    "SELECT id,column_name FROM qb_columns WHERE table_id=?", (row["id"],)
                ).fetchall()
            }
        for field_key, field in entry["fields"].items():
            if field_key not in fields_by_table[name_key]:
                new_fields.append({
                    "table": entry["name"], "field": field["name"],
                    "data_type": field["data_type"],
                })

    for link in links:
        left, right = link["left"], link["right"]
        lid = fields_by_table[left[0].casefold()].get(left[1].casefold())
        rid = fields_by_table[right[0].casefold()].get(right[1].casefold())
        existing = False
        if lid is not None and rid is not None:
            existing = conn.execute(
                """SELECT id FROM qb_relationships
                   WHERE (left_column_id=? AND right_column_id=?)
                      OR (left_column_id=? AND right_column_id=?)""",
                (lid, rid, rid, lid),
            ).fetchone() is not None
        rendered = {
            "left": f"{left[0]}.{left[1]}",
            "right": f"{right[0]}.{right[1]}",
            "reason": link["reason"], "confidence": link["confidence"],
        }
        (existing_links if existing else new_links).append(rendered)

    return {
        "application": APPLICATION,
        "new_tables": sorted(new_tables, key=str.casefold),
        "new_fields": sorted(new_fields, key=lambda x: (x["table"].casefold(), x["field"].casefold())),
        "new_links": new_links,
        "existing_links": existing_links,
        "counts": {
            "tables_to_add": len(new_tables),
            "fields_to_add": len(new_fields),
            "links_to_add": len(new_links),
            "links_already_present": len(existing_links),
        },
        "note": (
            "Missing tables will be added with SAP S/4HANA as Application and blank "
            "Catalog/Schema; missing fields have no invented type. Existing records "
            "are preserved. No named schema snapshot is created."
        ),
    }


def apply_import(conn, document, timestamp):
    """Caller must run in a SQLite transaction; do not commit here."""
    preview = plan_import(conn, document)
    definitions, links = normalise(document)
    fields_by_table = {}
    table_ids = {}
    for name_key, entry in definitions.items():
        existing_table = select_table(conn, entry["name"])
        if existing_table is None:
            cur = conn.execute(
                """INSERT INTO qb_tables
                   (catalog,schema_name,table_name,application_name,table_type,captured_at)
                   VALUES (NULL,NULL,?,?,'TABLE',?)""",
                (entry["name"], APPLICATION, timestamp),
            )
            table_id = cur.lastrowid
        else:
            table_id = existing_table["id"]
        table_ids[name_key] = table_id
        existing_fields = {
            row["column_name"].casefold(): row["id"]
            for row in conn.execute(
                "SELECT id,column_name FROM qb_columns WHERE table_id=?", (table_id,)
            ).fetchall()
        }
        next_pos = conn.execute(
            "SELECT coalesce(max(ordinal_position),0) FROM qb_columns WHERE table_id=?",
            (table_id,),
        ).fetchone()[0] or 0
        for key, field in entry["fields"].items():
            if key not in existing_fields:
                next_pos += 1
                cur = conn.execute(
                    """INSERT INTO qb_columns(table_id,ordinal_position,column_name,data_type)
                       VALUES (?,?,?,?)""",
                    (table_id, next_pos, field["name"], field["data_type"]),
                )
                existing_fields[key] = cur.lastrowid
        fields_by_table[name_key] = existing_fields

    for link in links:
        left, right = link["left"], link["right"]
        left_tid = table_ids[left[0].casefold()]
        right_tid = table_ids[right[0].casefold()]
        left_fid = fields_by_table[left[0].casefold()][left[1].casefold()]
        right_fid = fields_by_table[right[0].casefold()][right[1].casefold()]
        prior = conn.execute(
            """SELECT id FROM qb_relationships
               WHERE (left_column_id=? AND right_column_id=?)
                  OR (left_column_id=? AND right_column_id=?)""",
            (left_fid, right_fid, right_fid, left_fid),
        ).fetchone()
        if prior is None:
            conn.execute(
                """INSERT INTO qb_relationships
                   (left_table_id,left_column_id,right_table_id,right_column_id,confidence,source,notes)
                   VALUES (?,?,?,?,?,'sap-import',?)""",
                (left_tid, left_fid, right_tid, right_fid, link["confidence"], link["reason"]),
            )
    return preview
