"""Read-only local schema relationship graph for QueryBridge.

Provides table- and field-level relationships as captured in SQLite, never
guesses missing joins or connects to the original Databricks source.
"""
from __future__ import annotations

from collections import defaultdict

from flask import Blueprint, Response, jsonify, render_template, request, current_app
from schema_graphviz import dot_graph, render_svg, render_png
from schema_html_export import export_html

bp = Blueprint("schema_map", __name__)
_database = None
UNASSIGNED = "__unassigned__"


def create_schema_map_blueprint(database):
    global _database
    _database = database
    return bp


@bp.get("/schema-map")
def screen():
    return render_template("schema_map.html")


def as_bool(value):
    return str(value or "").lower() in ("1", "true", "yes", "on")


@bp.get("/api/schema-map")
def schema_map_data():
    application = (request.args.get("application") or "").strip()
    layer = (request.args.get("layer") or "source").strip()
    if layer not in ("source","databricks","application","lineage","combined"):
        return jsonify({"ok":False,"error":"Invalid layer."}),400
    include_unjoined = as_bool(request.args.get("include_unjoined"))
    include_cross_app = as_bool(request.args.get("include_cross_app"))
    focus_raw = (request.args.get("focus_table") or "").strip()
    try:
        focus_id = int(focus_raw) if focus_raw else None
        if focus_id is not None and focus_id < 1:
            raise ValueError()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid focus table ID."}), 400

    conn = _database()
    try:
        if layer != "source":
            from layer_graph import graph
            try:
                return jsonify(graph(conn,layer,application,focus_id,include_unjoined,include_cross_app))
            except ValueError as exc:
                return jsonify({"ok":False,"error":str(exc)}),400
        all_tables = [
            dict(r) for r in conn.execute(
                """SELECT t.id, t.catalog, t.schema_name, t.table_name,
                          t.application_name, t.table_type, COUNT(c.id) AS field_count
                   FROM qb_tables t
                   LEFT JOIN qb_columns c ON c.table_id=t.id
                   GROUP BY t.id
                   ORDER BY coalesce(t.application_name,''), coalesce(t.catalog,''),
                            coalesce(t.schema_name,''), t.table_name, t.id"""
            )
        ]
        table_by_id = {t["id"]: t for t in all_tables}
        applications = sorted(
            {t["application_name"] for t in all_tables if t["application_name"]},
            key=str.casefold,
        )
        if not application:
            base_ids = set(table_by_id)
        elif application == UNASSIGNED:
            base_ids = {t["id"] for t in all_tables if not t["application_name"]}
        else:
            base_ids = {t["id"] for t in all_tables if t["application_name"] == application}

        if focus_id is not None and focus_id not in base_ids:
            return jsonify({"ok": False, "error": "Selected table is not in this application."}), 400

        raw_links = [
            dict(r) for r in conn.execute(
                """SELECT r.id, r.left_table_id, r.left_column_id,
                          r.right_table_id, r.right_column_id,
                          lc.column_name AS left_field, rc.column_name AS right_field,
                          r.confidence, r.source, r.notes
                   FROM qb_relationships r
                   JOIN qb_columns lc ON lc.id=r.left_column_id AND lc.table_id=r.left_table_id
                   JOIN qb_columns rc ON rc.id=r.right_column_id AND rc.table_id=r.right_table_id
                   JOIN qb_tables lt ON lt.id=r.left_table_id
                   JOIN qb_tables rt ON rt.id=r.right_table_id
                   ORDER BY r.id"""
            )
        ]

        scope_ids = set(base_ids)
        if application and include_cross_app:
            for link in raw_links:
                left, right = link["left_table_id"], link["right_table_id"]
                if left in base_ids:
                    scope_ids.add(right)
                if right in base_ids:
                    scope_ids.add(left)
        scoped_links = [
            link for link in raw_links
            if link["left_table_id"] in scope_ids and link["right_table_id"] in scope_ids
            and (not application
                 or link["left_table_id"] in base_ids
                 or link["right_table_id"] in base_ids)
        ]
        linked_ids = {
            value
            for link in scoped_links
            for value in (link["left_table_id"], link["right_table_id"])
        }
        unjoined = [
            table_by_id[table_id]
            for table_id in base_ids if table_id not in linked_ids
        ]
        unjoined.sort(key=lambda t: (
            (t["application_name"] or "").casefold(),
            (t["catalog"] or "").casefold(),
            (t["schema_name"] or "").casefold(),
            t["table_name"].casefold(),
        ))

        if focus_id is not None:
            visible_ids = {focus_id}
            for link in scoped_links:
                if link["left_table_id"] == focus_id:
                    visible_ids.add(link["right_table_id"])
                if link["right_table_id"] == focus_id:
                    visible_ids.add(link["left_table_id"])
            if focus_id not in linked_ids and not include_unjoined:
                # Focused table still shows even without joins, allowing inspection.
                visible_ids = {focus_id}
        else:
            visible_ids = scope_ids if include_unjoined else linked_ids

        visible_links = [
            link for link in scoped_links
            if link["left_table_id"] in visible_ids and link["right_table_id"] in visible_ids
        ]
        visible_tables = []
        for table in all_tables:
            if table["id"] in visible_ids:
                item = dict(table)
                item["external"] = bool(application and table["id"] not in base_ids)
                item["joined"] = table["id"] in linked_ids
                item["fields"] = []
                visible_tables.append(item)

        if visible_tables:
            # Bounded only by the current selected scope (not a global LIMIT).
            placeholders = ",".join("?" for _ in visible_tables)
            fields = conn.execute(
                f"""SELECT id, table_id, column_name, data_type, nullable,
                           comment, ordinal_position
                    FROM qb_columns WHERE table_id IN ({placeholders})
                    ORDER BY table_id, ordinal_position, id""",
                [item["id"] for item in visible_tables],
            ).fetchall()
            by_table = {t["id"]: t for t in visible_tables}
            for field in fields:
                by_table[field["table_id"]]["fields"].append({**dict(field), "description":field["comment"],"description_source":"explicit" if field["comment"] else "none"})

        return jsonify({
            "ok": True,
            "applications": applications,
            "has_unassigned": any(not t["application_name"] for t in all_tables),
            "tables": visible_tables,
            "relationships": visible_links,
            "unjoined_tables": [
                {"id": t["id"], "table_name": t["table_name"],
                 "application_name": t["application_name"],
                 "catalog": t["catalog"], "schema_name": t["schema_name"]}
                for t in unjoined
            ],
            "stats": {
                "total_tables": len(all_tables),
                "in_application": len(base_ids),
                "shown_tables": len(visible_tables),
                "shown_joins": len(visible_links),
                "unjoined_in_application": len(unjoined),
                "cross_application_tables": sum(1 for t in visible_tables if t["external"]),
            },
        })
    finally:
        conn.close()


@bp.get("/api/schema-map/diagram")
def diagram():
    """Draw the same filtered graph as the browser's JSON API."""
    output_format = request.args.get("format", "svg")
    mode = request.args.get("mode", "overview")
    if output_format not in ("svg", "dot", "png") or mode not in ("overview", "detail"):
        return jsonify({"ok": False, "error": "Unsupported diagram format or view."}), 400
    raw_highlight = request.args.get("highlight_field", "").strip()
    try:
        highlighted = int(raw_highlight) if raw_highlight else None
        if highlighted is not None and highlighted < 1:
            raise ValueError
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid field selection."}), 400

    result = schema_map_data()
    if isinstance(result, tuple):
        return result
    payload = result.get_json()
    if len(payload["tables"]) > 250:
        return jsonify({
            "ok": False,
            "error": "More than 250 tables are selected. Filter by application or choose a focus table.",
        }), 422
    field_ids = {c["id"] for t in payload["tables"] for c in t["fields"]}
    if highlighted is not None and highlighted not in field_ids:
        return jsonify({"ok": False, "error": "Selected field is outside the diagram."}), 400
    effective_mode = mode  # Overview is table-only in every layer; Detail shows field ports.
    source = dot_graph(payload, mode=effective_mode, highlight_field=highlighted,
                       show_descriptions=as_bool(request.args.get("show_descriptions")))
    if output_format == "dot":
        response = Response(source, mimetype="text/vnd.graphviz")
    else:
        try:
            rendered = render_png(source) if output_format == "png" else render_svg(source)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        response = Response(rendered, mimetype="image/png" if output_format == "png" else "image/svg+xml")
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    response.headers["Cache-Control"] = "no-store"
    if request.args.get("download") == "1":
        ext = output_format
        response.headers["Content-Disposition"] = f'attachment; filename="querybridge-schema.{ext}"'
    return response


@bp.get("/api/schema-map/export-html")
def export_standalone_html():
    """A portable snapshot of every layer, including a focused two-lane UI view."""
    chosen = request.args.get("layer", "combined")
    if chosen not in ("source", "databricks", "application", "combined", "lineage"):
        return jsonify({"ok": False, "error": "Invalid layer."}), 400
    from urllib.parse import urlencode
    subset = as_bool(request.args.get("subset"))
    layers = {}
    for name in (chosen,) if subset else ("source", "databricks", "application", "combined", "lineage"):
        params = {"layer": name, "include_unjoined": "1", "include_cross_app": "1"}
        if subset:
            for key in ("application", "focus_table", "include_unjoined", "include_cross_app"):
                if key in request.args:
                    params[key] = request.args[key]
        with current_app.test_request_context("/api/schema-map?" + urlencode(params)):
            result = schema_map_data()
        if isinstance(result, tuple):
            return result
        layers[name] = result.get_json()
    snapshot = {
        "layers": layers,
        "scope": "selected view only" if subset else "all captured schema layers",
        "initial": {
            "layer": chosen,
            "application": request.args.get("application", ""),
            "mode": request.args.get("mode", "detail"),
            "theme": "dark" if request.args.get("theme") == "dark" else "light",
            "embedded": request.args.get("embedded") == "1",
        },
    }
    response = Response(export_html(snapshot), mimetype="text/html")
    response.headers["Content-Disposition"] = ('inline' if request.args.get("inline") == "1" else 'attachment') + '; filename="querybridge-schema-map.html"'
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'"
    return response
