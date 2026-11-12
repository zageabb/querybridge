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
| QB-10 | LLM Setup (/llm-setup) | Configure model settings and connection status | Desktop draft, screen spec pending |
| QB-11 | Knowledge document detail | Document fields and review context | Desktop draft |
| QB-12 | Snapshot workflows | Compare/switch captured schema snapshot | Desktop draft |

### Screens and interaction states that still need design
Login/permission/no_permission; source unavailable / not_configured; loading, zero records, import parsing failures; table edit unsaved/validation/success; connection errors; AI tool failure/stream; file export success/failure; mobile navigation and 200%-zoom variants.

## Field-level design rules
Mapped Databricks and Application views must show only recorded fields; lineage arrow is not a SQL JOIN. Application consumption screen fields are not necessarily visible UI controls. Always show missing upstream and status clearly without deriving connections from name similarity.

## Design system
Reuse common shell, screen header, filters, data rows, side inspector, empty/error, action buttons and modal patterns. Keep light/dark theme. No corporate branding is approved.

## Editable Figma frame links (draft)

| Screen | Figma frame |
|---|---|
| QB-01 Metadata | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-2) |
| QB-02 Explorer | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-53) · [Mobile](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=3-33) |
| QB-03 Map | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-104) · [Dark](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=3-2) · [Mobile](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=3-56) |
| QB-04 Query Builder | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-162) · [Mobile](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=3-79) |
| QB-05 Data Tables | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-215) |
| QB-06 Knowledge | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-266) |
| QB-07 Schema Chat | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-319) |
| QB-08 AI Skills | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-372) |
| QB-09 Administration | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=2-425) |
| QB-10 LLM Setup | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=6-8) |
| QB-11 Knowledge Document | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=6-43) |
| QB-12 Snapshots | [Desktop](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=6-78) |
| Shared state patterns | [Loading, empty, unavailable, restricted](https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5?node-id=6-113) |

**Screen spec work**: see `docs/screens/QB-XX.md`; these remain proposed and are not code implementation evidence.
