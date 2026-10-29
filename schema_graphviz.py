"""Graphviz rendering for captured QueryBridge table/field relationships.

Based on the Graphviz HTML-table/field-port approach already used by
zageabb/system-knowledge-designer/services/graph_renderer.py.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
from collections import defaultdict


def safe_html(value, max_len=140):
    value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return html.escape(value[:max_len], quote=True)


def dot_string(value):
    return json.dumps(str(value or ""), ensure_ascii=True)


def title(table):
    return ".".join(
        str(table[k]) for k in ("catalog", "schema_name", "table_name") if table.get(k)
    )


def dot_graph(payload, mode="overview", highlight_field=None):
    if mode not in ("overview", "detail"):
        raise ValueError("Diagram mode must be overview or detail.")
    tables = payload["tables"]
    relationships = payload["relationships"]
    by_id = {t["id"]: t for t in tables}
    lines = [
        "graph QueryBridge {",
        "graph [rankdir=LR, bgcolor=\"transparent\", overlap=false, splines=true, "
        "pad=0.25, nodesep=0.65, ranksep=1.0, outputorder=edgesfirst];",
        'edge [color="#5b79a3", penwidth=1.4, fontname="Arial", fontsize=9, fontcolor="#475467"];',
        'node [fontname="Arial", fontsize=11];',
    ]
    for table in tables:
        tid = int(table["id"])
        external = bool(table.get("external"))
        joined = bool(table.get("joined"))
        fill = "#fff8e8" if external else "#eff6ff" if joined else "#f8fafc"
        border = "#f79009" if external else "#667da1" if joined else "#98a2b3"
        label = title(table)
        if mode == "overview":
            caption = safe_html(label, 180)
            app = safe_html(table.get("application_name") or "Unassigned", 90)
            count = int(table.get("field_count") or 0)
            body = (
                f'<TABLE BORDER="1" COLOR="{border}" CELLBORDER="0" '
                f'CELLSPACING="0" CELLPADDING="7" BGCOLOR="{fill}">'
                f'<TR><TD><B>{caption}</B></TD></TR>'
                f'<TR><TD><FONT COLOR="#667085" POINT-SIZE="10">'
                f'{app} · {count} fields</FONT></TD></TR></TABLE>'
            )
        else:
            rows = [
                f'<TR><TD COLSPAN="2" BGCOLOR="{fill}" CELLPADDING="8">'
                f'<B>{safe_html(label, 180)}</B><BR/>'
                f'<FONT COLOR="#667085" POINT-SIZE="10">'
                f'{safe_html(table.get("application_name") or "Unassigned", 90)}'
                f'</FONT></TD></TR>'
            ]
            fields = table.get("fields", [])
            for field in fields:
                fid = int(field["id"])
                color = "#fff0b3" if fid == highlight_field else (
                    "#eaf4ff" if any(
                        fid == link["left_column_id"] or fid == link["right_column_id"]
                        for link in relationships
                    ) else "#ffffff"
                )
                rows.append(
                    f'<TR><TD PORT="f{fid}" BGCOLOR="{color}" ALIGN="LEFT">'
                    f'{safe_html(field["column_name"], 140)}</TD>'
                    f'<TD BGCOLOR="{color}" ALIGN="LEFT">'
                    f'<FONT POINT-SIZE="9" COLOR="#667085">'
                    f'{safe_html(field.get("data_type") or "—", 60)}'
                    f'</FONT></TD></TR>'
                )
            if not fields:
                rows.append(
                    '<TR><TD COLSPAN="2"><FONT COLOR="#98a2b3">'
                    '(no captured fields)</FONT></TD></TR>'
                )
            body = (
                f'<TABLE BORDER="1" COLOR="{border}" CELLBORDER="1" '
                f'CELLSPACING="0" CELLPADDING="6" BGCOLOR="#ffffff">'
                + "".join(rows) + "</TABLE>"
            )
        lines.append(
            f'T{tid} [shape=plain, id="table-{tid}", label=<{body}>, '
            f'tooltip={dot_string(label)}];'
        )

    if mode == "overview":
        pairs = defaultdict(list)
        for link in relationships:
            a, b = sorted((int(link["left_table_id"]), int(link["right_table_id"])))
            pairs[(a, b)].append(link)
        for (a, b), pair in sorted(pairs.items()):
            if a not in by_id or b not in by_id:
                continue
            details = "; ".join(
                f'{item["left_field"]} = {item["right_field"]} '
                f'({item["source"]})' for item in pair[:12]
            )
            count = len(pair)
            lines.append(
                f'T{a} -- T{b} [label={dot_string(str(count) + " join" + ("s" if count != 1 else ""))}, '
                f'tooltip={dot_string(details)}];'
            )
    else:
        for link in relationships:
            left_id, right_id = int(link["left_table_id"]), int(link["right_table_id"])
            if left_id not in by_id or right_id not in by_id:
                continue
            left_field, right_field = int(link["left_column_id"]), int(link["right_column_id"])
            is_highlighted = highlight_field in (left_field, right_field)
            color = "#0b71dd" if is_highlighted else "#8295ac"
            width = 3.4 if is_highlighted else 1.4
            source = link.get("source") or "saved"
            confidence = link.get("confidence")
            tooltip = (
                f'{title(by_id[left_id])}.{link["left_field"]} = '
                f'{title(by_id[right_id])}.{link["right_field"]}'
                f' | source={source} | confidence={confidence} | {link.get("notes") or ""}'
            )
            lines.append(
                f'T{left_id}:f{left_field}:e -- T{right_id}:f{right_field}:w '
                f'[id="join-{int(link["id"])}", color={dot_string(color)}, '
                f'penwidth={width}, tooltip={dot_string(tooltip)}];'
            )
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_svg(dot_source):
    try:
        output = subprocess.run(
            ["dot", "-Tsvg"],
            input=dot_source.encode("utf-8"), capture_output=True, timeout=25,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Graphviz 'dot' is not installed on the QueryBridge server.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Diagram rendering timed out. Filter by application or focus table.") from exc
    if output.returncode:
        raise RuntimeError("Graphviz could not render this diagram. Try a smaller filter.")
    return output.stdout
