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
