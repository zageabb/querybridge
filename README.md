# QueryBridge

QueryBridge is a lightweight Flask application for harvesting Databricks schema metadata through SQL-only access and turning that metadata into a local graphical SQL query builder.

## Initial workflow

1. QueryBridge shows the SQL to run in Databricks.
2. Copy the result grid from Databricks and paste it into QueryBridge.
3. QueryBridge stores the metadata in local SQLite.
4. It generates the next metadata query for each discovered table.
5. Paste each result back into the matching table record.
6. The Query Builder uses the captured tables, fields and inferred relationships to generate SQL.

## Databricks metadata queries

Start with:

```sql
SHOW TABLES;
```

For each table QueryBridge generates:

```sql
DESCRIBE TABLE EXTENDED schema_name.table_name AS JSON;
```

The JSON form requires Databricks Runtime / SQL support for `DESCRIBE TABLE ... AS JSON`. QueryBridge also accepts the older human-readable `DESCRIBE TABLE` result as a fallback.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5086

## Storage

Local metadata is stored in `instance/querybridge.db`. No Databricks credentials are required because metadata is transferred manually by copy/paste.


## Named schema snapshots

Captured metadata can be saved as a named schema snapshot from the Metadata page.

A snapshot contains:

- catalogs, schemas and tables
- fields and Databricks data types
- field comments and nullability where available
- captured/inferred relationships
- enough metadata to reopen the schema later without reconnecting to Databricks

Snapshots are stored in the local SQLite database and are not removed when the working metadata is cleared.

### Save

Use **Save current schema** and give the current working schema a name. Saving again with the same name updates the saved snapshot.

### Load

Use **Load** on a saved snapshot to replace the current working metadata with that saved schema. The Query Builder then works against the restored schema.

### Export

Use **Export** to create a portable file named like:

```text
SCM_Production.querybridge.json
```

The export uses table/schema/column identities rather than local SQLite row IDs, so relationships can be rebuilt on another QueryBridge installation.

### Import

Use **Import schema** to add an exported QueryBridge JSON file to the local schema library. You can optionally load it immediately into the working area.


## Local LLM and schema intelligence

QueryBridge can use a locally hosted Ollama model to reason about the captured schema without requiring a live Databricks connection.

### LLM Setup

Open **LLM Setup** and configure:

- Ollama base URL
- model name
- temperature
- request timeout

Use **Load models** to query the configured Ollama server and **Save & test connection** to verify access.

### Schema Chat

**Schema Chat** sends the current working schema, known/inferred relationships and schema knowledge to the configured model. It can be used to:

- explain tables and fields
- identify likely source/target tables
- discuss joins
- draft Databricks SQL
- identify missing metadata or knowledge

QueryBridge instructs the model not to invent table or column names when answering schema-specific questions.

### Knowledge

The **Knowledge** page stores additional context such as:

- package or source-system information
- known relationship hints
- business rules
- naming conventions
- general schema notes

Knowledge is included in LLM context and is also saved inside named QueryBridge schema snapshots.

### AI Guess Links

From the Knowledge page, **AI Guess Links** asks the configured LLM to propose useful equality joins.

Each suggestion must identify real tables and fields from the captured schema. QueryBridge validates those names before storing the relationship. LLM-created links are marked with source `llm`, a confidence value and a reason supplied by the model.

The Query Builder can use those relationships when generating JOIN clauses.

### Schema snapshots and AI context

Named schema snapshots now carry:

- tables and fields
- Databricks types and comments
- heuristic relationships
- LLM-suggested relationships and reasons
- schema/package knowledge

Loading a different schema snapshot clears the previous schema-chat history so conversations do not mix context from different schemas.


### Built-in knowledge pack

The repository includes a curated TAIJU / SCM knowledge pack under `knowledge/`.

Open **Knowledge** and use **Import Knowledge Pack** to load the manifest-driven Markdown documents into the local QueryBridge Knowledge database.

The importer is idempotent by title:

- missing entries are added
- existing pack entries are refreshed
- user-created entries with different titles are retained

After a future `git pull`, use **Refresh Knowledge Pack** to bring any updated repository knowledge into the local database.


## Markdown knowledge documents

QueryBridge knowledge is Markdown-native. Knowledge documents support headings, lists, fenced code and Markdown tables. Open any knowledge item to view the rendered document or edit the raw Markdown with a live preview.

The renderer escapes raw HTML before rendering Markdown, keeping the local document viewer safe while preserving Markdown structures.

## AI Skills and reviewable schema changes

QueryBridge includes built-in local AI skills inspired by the bounded skill/action patterns in Context Studio and the review-first schema workflow in System Knowledge Designer.

Built-in skills cover:

- relationship analysis
- schema curation
- field type review
- knowledge-grounded schema reasoning

AI can propose local metadata-model operations including:

- add/remove/rename tables
- add/remove/rename fields
- change field data types
- change nullability
- add/remove relationships

AI proposals never alter Databricks and never apply automatically. They are stored in the **AI Skills** review queue and must be explicitly **Applied** or **Rejected**. QueryBridge validates the proposal when generated and again immediately before application.


### Local Schema SQL Analysis

Schema Chat can use the built-in **Local Schema SQL Analysis** skill to run read-only SQLite `SELECT` statements over QueryBridge's locally captured metadata.

It does **not** connect to Databricks.

For each analysis request QueryBridge builds an isolated in-memory database containing only:

- `schema_tables`
- `schema_fields`
- `schema_relationships`
- `schema_knowledge`

The LLM can use joins, filters, CTEs, grouping and aggregates across those local analysis tables. It can issue multiple SELECTs in one chat turn before producing its final answer.

The sandbox has no access to QueryBridge chat history, LLM settings or other application tables, and is switched to SQLite `query_only` mode before the AI can query it.

Other enabled AI skills are also included in Schema Chat context, so relationship analysis, field-type review, schema curation and custom skills can reason over the same locally stored schema.


## Import Databricks SQL into Query Builder

The Query Builder supports round-trip import of existing Databricks SELECT statements.

Use **Import SQL** to paste a query from Databricks. QueryBridge parses it with the Databricks SQL dialect and attempts to map the query back to the locally stored schema.

The importer currently reconstructs or preserves:

- SELECT fields
- field aliases
- raw expressions such as CASE or aggregates
- FROM table
- table aliases
- JOIN clauses
- WHERE
- GROUP BY
- HAVING
- QUALIFY
- ORDER BY
- LIMIT
- OFFSET
- DISTINCT
- WITH / CTE prefix where it can be preserved safely

Fields that match the stored schema are loaded as normal Query Builder fields and highlighted in the schema browser. Expressions that cannot be reduced to a single stored field are preserved as expression items rather than discarded.

After import, fields can be added or removed in the normal visual builder. If a newly selected field comes from a table that was not part of the imported query, QueryBridge uses stored relationships to add an appropriate JOIN where possible; otherwise it uses a CROSS JOIN and shows a warning.

If the imported query contains equality JOINs that are not already known to QueryBridge, the builder offers **Create relationship proposal from imported JOINs**. These links go to the AI Skills proposal queue for explicit review before they become trusted schema relationships.

The import process uses only the locally stored schema for matching. It does not connect to Databricks.


## Relationship cleanup and provenance

QueryBridge records the source of every stored relationship. The **Knowledge** page now includes **Relationship controls** so old heuristic relationships can be removed without losing links created through newer workflows.

**Clear auto-generated links** deletes only relationships with source `auto`. It preserves relationships whose source is `llm`, `ai-approved`, `manual`, snapshot/restored provenance, and approved relationships observed in imported SQL.

Legacy heuristic inference is disabled by default. This prevents cleared `auto` links from being recreated when table metadata is refreshed, an AI schema proposal is applied, or a snapshot without explicit relationships is loaded. It can be explicitly re-enabled from the Relationship controls panel if needed.


## Schema Explorer

Open **Schema Explorer** from the top navigation to browse the **current working schema** as a searchable table.

- Search over application label, catalog, schema, table name, field name, field type and field comment. Search is case-insensitive and runs against local SQLite (75 rows per page).
- The **Application** filter uses an optional source-application label, separate from Databricks catalog and schema. Select any field, type an application name (for example SAP S/4HANA, P6 or TAIJU), and select **Save application** to label its table. An unlabelled table appears as *Unassigned*. The app name is a user-assigned description, not an inferred Databricks identity.
- Selecting a field opens the inspector with all stored relationships in either direction, the target field, equality join condition, relationship source, confidence and notes. Fields with no stored join show an explicit no-relationships state; no joins are guessed by the browser.
- Application labels are preserved in named schema snapshots and portable exports. Older snapshot files still load, leaving application labels unassigned.
- A table with no captured columns is still visible in the browser. Application assignments are stored locally only; they never write to Databricks.

The browser displays the active working schema, **not all saved schema snapshots at once**. Load a saved snapshot from the Metadata page to explore it.


## Metadata Administration

**Admin** opens directly from the navigation with **no separate password or sign-in**.
It edits QueryBridge's locally captured SQLite metadata, not physical Databricks tables.

The dashboard shows totals for tables, fields, stored joins, snapshots and knowledge,
a searchable table browser, a field editor, join controls, and the last 25 recorded
administrative changes.

You can:
- add, rename and remove captured tables and update application, catalog, schema and type;
- add, rename, retype, reorder, change nullability, describe or delete captured fields;
- add a documented manual equality join between different tables, or remove a saved join.

Deleting a local table or field also removes its stored joins, so these actions
require exact-name and second-step confirmation. Existing named snapshots are not
modified; save a new snapshot before major editing. Existing saved SQL and knowledge
may still refer to renamed or deleted metadata.

### Access and security

The Admin screen **inherits QueryBridge's existing network/application access**.
Anyone who can reach QueryBridge can open Admin and modify local metadata. Do not
expose QueryBridge directly to the public internet; restrict access at the existing
UDA/Caddy proxy or your private network. The Admin API uses a dedicated browser cookie with an anti-CSRF token
sent by the page on write requests. This does not depend on a Flask session
or an application-wide signing secret. The cookie is scoped to QueryBridge's
UDA path, including when the application runs behind a reverse proxy.
Cross-origin administration changes are rejected. **No admin password
or configuration is required.**

An optional QUERYBRIDGE_SESSION_SECRET environment variable provides a stable
Flask session signing key across restarts and multiple workers; otherwise a strong
random per-process key is generated. For HTTPS-only reverse-proxy deployments,
QUERYBRIDGE_COOKIE_SECURE=1 is still recommended. Keep the backend shielded
behind the trusted reverse proxy, with HTTPS at the browser.

This removal applies to the separate Admin password only; it does not change
QueryBridge's existing metadata capture or AI schema workflows or grant live
Databricks access.


## Schema Map: visualise table and field relationships

Open **Schema Map** from the QueryBridge navigation. This is a *read-only* view of
the current working metadata in the local SQLite database: neither Databricks nor
saved schema snapshots are queried or modified.

- **Overview:** every represented table is one node; recorded field-level joins
  are counted between table pairs, so a pair with three joins has one labelled line.
- **Detail:** Graphviz renders fields as rows in table-shaped nodes and attaches
  each recorded relationship to its exact source and target field ports (as in
  the ER workbench of system-knowledge-designer). Select a field to
  highlight that field's relationships.
- **Application:** filter by the user-assigned application label, including
  **Unassigned**, or select all applications. Optionally include linked tables
  from other applications; external tables are coloured separately. Joins
  between external-only tables are not inferred or added to a filtered view.
- **Unjoined:** the sidebar always lists tables lacking stored joins *within
  the current filter*. **Show all tables, including unjoined** includes these in
  the diagram; you may also focus on an unjoined table individually.
- **Focus:** narrow to one table plus its directly joined tables, useful for
  large schemas. Use **Fit / Reset**, zoom, and the scrollable canvas.
- **Export:** download Graphviz SVG and DOT, or copy/export equivalent Mermaid
  .mmd text for use in Mermaid Final. Mermaid is exported, not required to
  render the Schema Map page.

The view uses only **saved relationships** (manual, inferred, or AI-approved)
and does not invent new joins, foreign-key direction or cardinality. Saved
relationship provenance, confidence and notes appear in the sidebar.

### Graphviz runtime dependency

The server needs the Graphviz dot executable to render SVG:

    sudo apt-get update
    sudo apt-get install -y graphviz
    dot -V

Graphviz is already used by the ER visualisation in
system-knowledge-designer; no connection to that app is required.
If Graphviz is missing, Schema Map shows an explicit error and the Mermaid
source/export remains available. The GitHub Python CI workflow checks SVG
rendering with Graphviz installed. For very large maps, the SVG renderer
limits diagrams to 250 tables; filter by application or select a focus table.

The rendering and API routes respect QueryBridge's existing UDA reverse-proxy
prefix, including /apps/querybridge/. Do not expose the underlying Flask
service outside the existing trusted network/application boundary.

## AI schema proposals and Application labels

The **AI Skills & Schema Proposals** page works with the current locally captured
schema. Every table's optional `application_name` is included in the LLM's
schema description. AI read-only SQL can now use `application_name` in
`schema_tables` and `schema_fields`, and the endpoint application labels
`left_application` / `right_application` in `schema_relationships`.

For example, the AI can count captured tables belonging to **SAP S/4HANA**
without confusing that user-assigned application label with the actual
Databricks catalog/schema. Unassigned tables have NULL application names in
the SQL views. The original catalog/schema/table and field identifiers are
unchanged. These metadata views are isolated and read-only.

**Review with no changes:** If the LLM returns `"operations": []`, the result
is an informational *no changes* review, not a broken or stale proposal.
There is nothing to apply; use **Dismiss** to close it. This also corrects
previously saved no-operation reviews when the page reloads. For proposals
with actual invalid or outdated operations, the page shows the validation
reason and keeps Apply disabled. The server rejects direct attempts to apply
empty proposals while retaining review history and approval requirements.



## Ask questions about schema (without creating a change proposal)

On **AI Skills**, choose **Ask about schema** for read-only questions, or
**Generate change proposal** when you want edits reviewed before application.
Answers are saved in the same history but have an **answer** status and no
Apply button; use Dismiss when finished.

Straightforward table inventory requests such as **List of tables**, **Show
all tables** and **List tables for SAP S/4HANA** are answered by reading
QueryBridge's SQLite working schema directly, without relying on the LLM's
interpretation or requiring Ollama to be online. Results show table names,
application labels, catalog/schema (if known), and counts of fields and saved
joins. Long results are bounded to 500 displayed tables; Schema Explorer
remains available for complete browsing.

Other questions use the configured LLM as a read-only schema assistant. That
assistant is directed to answer the actual information request, using the
local SQL metadata tool where needed, rather than reporting that no schema
changes were necessary. Information requests do not create or apply schema
changes. Original change-proposal workflow remains governed and unchanged,
including older saved proposals (which can be dismissed normally).

## Import SAP S/4HANA table links into the current subset

Open **Admin → SAP S/4HANA relationship import**, and download the starter
JSON file. The same file is stored in
`samples/sap_s4hana_links_template.json` in this repository.

The format is **querybridge-sap-links, version 1** and includes:
- `application`: must be `SAP S/4HANA`;
- `tables`: optional table definitions and field names. Fields can be strings
  or objects with `name` and optional `data_type`;
- `links`: individual equality join candidates with `left` and `right`
  objects containing `table` and `field`, and optional `confidence`
  (number from 0 to 1) and `reason`.

Example link:

    {
      "left": {"table": "EKKO", "field": "EBELN"},
      "right": {"table": "EKPO", "field": "EBELN"},
      "confidence": 0.95,
      "reason": "Purchasing header to purchasing item"
    }

To import:

1. Edit the starter JSON with the SAP tables, fields and links you actually
   want. **Review and validate the sample joins against your SAP extraction
   before using them**, including client-key (e.g. MANDT) conditions and
   S/4HANA Business Partner transformations.
2. Select it in Admin and click **Preview import**. QueryBridge lists new
   tables, fields and joins, and identifies existing joins to skip.
3. Click **Confirm and import** and approve the confirmation dialog. The
   changes appear in Schema Explorer and Schema Map.

If a referenced table or field is missing from your **current local subset**,
QueryBridge adds it so the relationship can be represented. **New tables are
labelled SAP S/4HANA but have NULL Catalog and NULL Schema**; the importer
does not invent Databricks locations or field types. Existing tables and
fields are reused unchanged, even if their application is currently blank.
Ambiguous duplicate table names fail validation rather than guessing.

The import is additive, idempotent, and atomic. It records the source
`sap-import` on new joins and logs the operation in Admin audit. Repeating the
same file skips existing tables, fields and relationships. **No named schema
snapshot is created, updated or overwritten.** The importer does not connect
to or modify SAP, Databricks or external data. It is available to anyone who
can reach the existing password-free Admin screen, with the same CSRF
validation. Files are limited to 1 MB in the browser and the importer
enforces table/field/join counts server-side.
