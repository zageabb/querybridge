# QueryBridge Screen Inventory — v0.1

**Figma design**: https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5
**Status**: editable draft frames with synthetic examples; actual app implementation not redesigned.

| ID | Route / screen | Primary task | Design status |
|---|---|---|---|
| QB-01 | Metadata (/) | Capture source tables, inspect imports, saved snapshots | Desktop draft |
| QB-02 | Schema Explorer (/catalogue) | Explore source, Databricks, application and combined fields; inspect mappings | Desktop and mobile draft |
| QB-03 | Schema Map (/schema-map) | Explore accurate joins/lineage, drag Graphviz/HTML5, export | Desktop, dark and mobile draft |
| QB-04 | Query Builder (/builder) | Choose tables and joins; inspect generated SQL | Desktop and mobile draft |
| QB-05 | Data Tables (/admin/data-tables) | Search/inspect/edit authorised database records | Desktop draft |
| QB-06 | Knowledge (/knowledge) | Search and inspect evidence/document contents | Desktop draft |
| QB-07 | Schema Chat (/schema-chat) | AI question and source context | Desktop draft |
| QB-08 | AI Skills (/ai-skills) | Inspect/configure approved AI skills | Desktop draft |
| QB-09 | Administration (/admin) | Layer object/field/lineage metadata, permissions, audit | Desktop draft |
| QB-10 | LLM Setup (/llm-setup) | Configure model settings and connection status | Additional screen spec required |
| QB-11 | Knowledge document detail | Document fields and review context | Additional screen spec required |
| QB-12 | Snapshot workflows | Compare/switch captured schema snapshot | Additional screen spec required |

### Screens and interaction states that still need design
Login/permission/no_permission; source unavailable / not_configured; loading, zero records, import parsing failures; table edit unsaved/validation/success; connection errors; AI tool failure/stream; file export success/failure; mobile navigation and 200%-zoom variants.

## Field-level design rules
Mapped Databricks and Application views must show only recorded fields; lineage arrow is not a SQL JOIN. Application consumption screen fields are not necessarily visible UI controls. Always show missing upstream and status clearly without deriving connections from name similarity.

## Design system
Reuse common shell, screen header, filters, data rows, side inspector, empty/error, action buttons and modal patterns. Keep light/dark theme. No corporate branding is approved.
