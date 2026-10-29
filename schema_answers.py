"""Deterministic answers for simple QueryBridge schema inventory requests.

Pure read-only SQLite queries ensure a request such as "List of tables"
actually lists captured tables, rather than producing an AI "no changes" reply.
"""
from __future__ import annotations

import re
from collections import defaultdict

_TABLE_REQUEST = re.compile(
    r"^\s*(?:please\s+)?"
    r"(?:list|show|display)\s+"
    r"(?:(?:me|all|the|of|my|current|available|existing|captured|a)\s+)*"
    r"tables?"
    r"(?:\s+(?:by\s+application|(?:for|in|from|of)\s+(.+?)))?"
    r"\s*[?!.]?\s*$",
    re.IGNORECASE,
)

_QUESTION = re.compile(
    r"^\s*(?:what|which)\s+tables?\s+(?:do\s+we\s+have|are\s+available|are\s+captured)"
    r"\s*[?!.]?\s*$",
    re.IGNORECASE,
)


def inventory_application(request_text):
    """Return (matches, scope text); no mutation/change-intent guessing."""
    match = _TABLE_REQUEST.fullmatch((request_text or "").strip())
    if match:
        return True, (match.group(1) or "").strip()
    if _QUESTION.fullmatch((request_text or "").strip()):
        return True, ""
    return False, ""


def render_table_inventory(conn, requested_application="", limit=500):
    """Render grounded, bounded metadata from the current working local schema."""
    rows = [
        dict(row) for row in conn.execute(
            """SELECT t.id, t.catalog, t.schema_name, t.table_name, t.application_name,
                      (SELECT COUNT(*) FROM qb_columns c WHERE c.table_id=t.id) AS fields,
                      (SELECT COUNT(*) FROM qb_relationships r
                       WHERE r.left_table_id=t.id OR r.right_table_id=t.id) AS joins
               FROM qb_tables t
               ORDER BY COALESCE(t.application_name,'') COLLATE NOCASE,
                        COALESCE(t.catalog,'') COLLATE NOCASE,
                        COALESCE(t.schema_name,'') COLLATE NOCASE,
                        t.table_name COLLATE NOCASE, t.id"""
        )
    ]
    available = sorted(
        {x["application_name"] for x in rows if x["application_name"]}, key=str.casefold
    )
    requested = re.sub(r"^\s*(?:the\s+)?", "", (requested_application or "").strip())
    requested = re.sub(r"\s+application\s*$", "", requested, flags=re.IGNORECASE).strip(" \"'")
    if requested.casefold() in ("", "all", "all applications", "any application"):
        requested = ""
    if requested.casefold() in ("unassigned", "unlabelled", "unlabeled"):
        matches = [r for r in rows if not r["application_name"]]
        scope = "Unassigned"
    elif requested:
        choices = [a for a in available if a.casefold() == requested.casefold()]
        if not choices:
            choices = [a for a in available if requested.casefold() in a.casefold()]
        if len(choices) != 1:
            options = ", ".join(available) or "(none)"
            if len(choices) > 1:
                return (
                    "Table inventory — application filter is ambiguous",
                    f"'{requested}' matches multiple application labels: {', '.join(choices)}. "
                    f"Please use the full application name. Available labels: {options}.",
                )
            return (
                "Table inventory — application not found",
                f"No captured tables are assigned an application matching '{requested}'. "
                f"Available application labels: {options}. "
                "Unassigned tables can be requested using 'List tables for Unassigned'.",
            )
        scope = choices[0]
        matches = [r for r in rows if r["application_name"] == scope]
    else:
        scope = "all applications"
        matches = rows

    title = "Table inventory" + (" — " + scope if requested else "")
    count = len(matches)
    if count == 0:
        return title, (
            f"No tables are captured for {scope} in the current local QueryBridge schema. "
            "Use Metadata to capture tables or Admin to add local metadata."
        )

    shown = matches[:limit]
    lines = [
        f"{count} captured table(s) for {scope} in the current QueryBridge working schema.",
        f"Showing {len(shown)} of {count} table(s)." if len(shown) < count else "",
        "",
    ]
    groups = defaultdict(list)
    for row in shown:
        groups[row["application_name"] or "Unassigned"].append(row)
    for application, group in groups.items():
        lines.append(f"APPLICATION: {application} ({len(group)} shown)")
        for item in group:
            path = ".".join(
                part for part in (item["catalog"], item["schema_name"], item["table_name"])
                if part
            )
            lines.append(
                f"  • {path} — {item['fields']} fields, {item['joins']} saved joins"
            )
        lines.append("")
    lines.append("Source: current local QueryBridge metadata, not live Databricks data.")
    if len(shown) < count:
        lines.append("Use Schema Explorer for the complete searchable inventory.")
    return title, "\n".join(line for line in lines if line is not None).strip()
