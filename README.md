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
