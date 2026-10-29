"""Import an SAP S/4HANA ABAP Dictionary CSV into QueryBridge working metadata.

Usage:
  python scripts/import_sap_ddic.py sap_ddic.csv --db instance/querybridge.db
  python scripts/import_sap_ddic.py sap_ddic.csv --db instance/querybridge.db --apply

This is a bulk local metadata import, NOT a change to SAP/Databricks. It creates
no named QueryBridge schema snapshots and no guessed relationship edges.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

APPLICATION = "SAP S/4HANA"
REQUIRED = {"TABLE_NAME", "FIELD_NAME"}
ALIASES = {
    "TABNAME": "TABLE_NAME", "FIELDNAME": "FIELD_NAME",
    "TABLE_DESC": "TABLE_DESCRIPTION", "DDTEXT_TABLE": "TABLE_DESCRIPTION",
    "FIELD_DESC": "FIELD_DESCRIPTION", "DDTEXT_FIELD": "FIELD_DESCRIPTION",
    "DATATYPE": "DATA_TYPE", "LENG": "LENGTH", "POSITION": "POSITION",
}
OPTIONAL = {"TABLE_DESCRIPTION", "FIELD_DESCRIPTION", "DATA_TYPE", "POSITION", "LENGTH", "DECIMALS"}


def text(value, limit=1000):
    value = str(value or "").replace("\x00", "").strip()
    return value[:limit] or None


def read_rows(path, include_custom=False):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("The CSV has no header row.")
        columns = [ALIASES.get((v or "").strip().upper(), (v or "").strip().upper())
                   for v in reader.fieldnames]
        if not REQUIRED.issubset(columns):
            raise ValueError("The CSV must contain TABLE_NAME and FIELD_NAME columns.")
        for number, raw in enumerate(reader, start=2):
            row = dict(zip(columns, raw.values()))
            table = text(row.get("TABLE_NAME"), 120)
            field = text(row.get("FIELD_NAME"), 120)
            if not table or not field:
                raise ValueError(f"Line {number}: table and field names must be supplied.")
            if not include_custom and table.upper().startswith(("Z", "Y")):
                continue
            if field.startswith("."):
                continue
            row["TABLE_NAME"], row["FIELD_NAME"] = table, field
            row["_line"] = number
            yield row


def rows_grouped(path, include_custom=False):
    """Process sorted DDIC export table-by-table, using bounded memory."""
    table = None
    rows = []
    seen = set()
    for row in read_rows(path, include_custom):
        target = row["TABLE_NAME"].upper()
        if table is not None and target != table:
            if table in seen:
                raise ValueError("CSV must be ordered by TABLE_NAME: " + table)
            seen.add(table)
            yield rows
            rows = []
        table = target
        rows.append(row)
    if rows:
        if table in seen:
            raise ValueError("CSV must be sorted by TABLE_NAME (duplicate group): " + table)
        yield rows


def table_matches(conn, name):
    matches = conn.execute(
        """SELECT id, application_name, description, catalog, schema_name, table_name
           FROM qb_tables WHERE lower(table_name)=lower(?) ORDER BY id""",
        (name,),
    ).fetchall()
    if len(matches) <= 1:
        return matches[0] if matches else None
    preferred = [
        x for x in matches
        if (x["application_name"] or "").casefold() == APPLICATION.casefold()
    ]
    if len(preferred) == 1:
        return preferred[0]
    raise ValueError(
        f"Ambiguous existing QueryBridge table '{name}'. Resolve duplicates in Admin; "
        "bulk import will not guess a catalog/schema."
    )


def name_for_ddic(table, prefix):
    if table.startswith("/"):
        # Keep SAP namespaces as part of the identifier.
        return prefix + table
    return prefix + table.lower() if prefix else table


def run_import(conn, path, prefix="sap_", apply=False, include_custom=False):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(qb_tables)")}
    if "description" not in cols:
        raise ValueError("Run updated QueryBridge once first: qb_tables.description migration missing.")
    counts = defaultdict(int)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    for entries in rows_grouped(path, include_custom):
        sap_name = entries[0]["TABLE_NAME"]
        table_name = name_for_ddic(sap_name, prefix)
        item = table_matches(conn, table_name)
        table_desc = next((text(r.get("TABLE_DESCRIPTION"), 1000)
                           for r in entries if text(r.get("TABLE_DESCRIPTION"))), None)
        if item is None:
            counts["tables_added"] += 1
            if apply:
                cursor = conn.execute(
                    """INSERT INTO qb_tables
                       (catalog, schema_name, table_name, application_name, description,
                        table_type, captured_at, raw_source)
                       VALUES (NULL,NULL,?,?,?,'TABLE',?,'SAP DDIC CSV')""",
                    (table_name, APPLICATION, table_desc, timestamp),
                )
                table_id = cursor.lastrowid
            else:
                table_id = None
        else:
            table_id = item["id"]
            counts["tables_reused"] += 1
            if table_desc and not item["description"]:
                counts["table_descriptions_added"] += 1
                if apply:
                    conn.execute(
                        "UPDATE qb_tables SET description=? WHERE id=? AND (description IS NULL OR description='')",
                        (table_desc, table_id),
                    )

        existing_fields = {
            r["column_name"].casefold(): dict(r)
            for r in conn.execute(
                "SELECT id, column_name, data_type, comment FROM qb_columns WHERE table_id=?",
                (table_id,),
            ).fetchall()
        } if table_id is not None else {}
        next_position = conn.execute(
            "SELECT coalesce(max(ordinal_position),0) FROM qb_columns WHERE table_id=?", (table_id,),
        ).fetchone()[0] if table_id is not None else 0
        row_names = set()
        counts["tables_seen"] += 1
        for record in entries:
            field = record["FIELD_NAME"]
            key = field.casefold()
            if key in row_names:
                raise ValueError(f"Duplicate DDIC field in {sap_name}: {field}")
            row_names.add(key)
            dtype = text(record.get("DATA_TYPE"), 100)
            length = text(record.get("LENGTH"), 16)
            # Keep the original ABAP type label; no conversion to a Databricks type.
            if dtype and length and length.isdecimal() and int(length) > 0:
                dtype += f"({int(length)})"
            field_desc = text(record.get("FIELD_DESCRIPTION"), 4000)
            old = existing_fields.get(key)
            counts["fields_seen"] += 1
            if old is None:
                counts["fields_added"] += 1
                if apply:
                    next_position += 1
                    pos = text(record.get("POSITION"), 12)
                    position = int(pos) if pos and pos.isdecimal() and int(pos) > 0 else next_position
                    conn.execute(
                        """INSERT INTO qb_columns
                           (table_id,ordinal_position,column_name,data_type,comment)
                           VALUES (?,?,?,?,?)""",
                        (table_id, position, field, dtype, field_desc),
                    )
            else:
                updates = []
                params = []
                if dtype and not old["data_type"]:
                    updates.append("data_type=?")
                    params.append(dtype)
                    counts["field_types_added"] += 1
                if field_desc and not old["comment"]:
                    updates.append("comment=?")
                    params.append(field_desc)
                    counts["field_descriptions_added"] += 1
                if apply and updates:
                    conn.execute(
                        "UPDATE qb_columns SET " + ", ".join(updates) + " WHERE id=?",
                        (*params, old["id"]),
                    )
    return dict(counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="DDIC dictionary export CSV, sorted by TABLE_NAME")
    parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parents[1] / "instance/querybridge.db")
    parser.add_argument("--prefix", default="sap_", help="Table prefix matching QueryBridge capture (default: sap_)")
    parser.add_argument("--include-custom", action="store_true", help="Include Y* and Z* customer tables")
    parser.add_argument("--apply", action="store_true", help="Write to local QueryBridge DB; default dry run only")
    args = parser.parse_args(argv)
    if not args.csv_file.is_file():
        parser.error("CSV file does not exist: " + str(args.csv_file))
    if not args.db.is_file():
        parser.error("QueryBridge database does not exist: " + str(args.db))
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE" if args.apply else "BEGIN")
        stats = run_import(
            conn, args.csv_file, prefix=args.prefix, apply=args.apply,
            include_custom=args.include_custom,
        )
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        print(("APPLIED" if args.apply else "DRY RUN") + " SAP DDIC import:")
        for key in sorted(stats):
            print(f"  {key}: {stats[key]}")
        if not args.apply:
            print("No local metadata was modified. Rerun with --apply after reviewing.")
        else:
            print("Imported into working metadata; NO named schema snapshot and NO relationships created.")
        return 0
    except (ValueError, sqlite3.Error, OSError) as exc:
        conn.rollback()
        print("Import aborted; all changes rolled back: " + str(exc), file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
