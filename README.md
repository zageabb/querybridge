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
