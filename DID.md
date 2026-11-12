# QueryBridge — Design Intent & Decisions

## Purpose
Capture source application/Databricks metadata, curate field-level joins and source-to-EDP-to-consuming-application lineage, search/inspect dictionaries, build SQL, and export readable offline schema diagrams.

## Personas and permissions
Schema analysts, data architects, authorised metadata maintainers and administrators. Read-only exploration and export must not silently enable editing. Admin-managed data-layer additions and record edits retain their existing API permissions and audit controls.

## Architecture
Existing Flask/Jinja + vanilla JavaScript with local SQLite and Graphviz, client-side HTML5/SVG view and export. Server authority remains the canonical `layer_graph.py` / `schema_map.py` metadata API. Never infer an unrecorded join, field availability or actual UI control from a label.

## Visual approach
Adopt Application-Standard v1.0 screen governance. Use shared app shell, semantic colour/type/space/density tokens, navigation patterns, keyboard focus, light and dark themes, responsive desktop/tablet/mobile. Use Material 3/MUI-compatible component patterns when appropriate but keep specialist schema canvas as a documented custom extension.

## Data layer interaction
- Source dictionary — captured SAP or other source application tables and fields.
- Databricks / EDP — explicitly selected physical/derived fields, catalog.schema.table where available.
- Application consumption — recorded consuming application's technical fields, UI labels only where specifically documented.
- Combined — both Databricks and Application entities with directional recorded field mappings; excludes source dictionary noise.
- End-to-end — source → EDP → application provenance, distinct join/lineage semantics.

## Confirmed product choices
Keep old Graphviz and new draggable HTML5 canvas as user-selectable modes. PNG/SVG image export should reflect the currently chosen renderer and filters. Offline HTML remains an immutable, read-only snapshot. Preserve filters, table positions, themes and accessibility where supported.

## Exceptions and controls
Flask is grandfathered; rewrite requires a separately approved architectural decision. Ubuntu UDA prefix compatibility uses trusted `ProxyFix` conventions; separately verify direct and `/apps/querybridge/` routes. Enterprise integrations remain optional, with `not_configured` distinct from legitimate empty result. No sensitive corporate source screenshots or records in public repositories or Figma.

## Design and delivery status
Figma draft created 2026-11-12: https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5
Design/CI/application implementation and user acceptance are separate gates; Figma designs are proposals and do not change deployed screens.
