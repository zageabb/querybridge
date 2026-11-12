# Development Status

Last reviewed: 2026-10-02
Current development state: ACTIVE

## Purpose

This file is the common development ledger for both the user and AI agents. Existing project-specific planning documents remain valid; this file standardises status and completion evidence.

## Current objective

Continue the schema, SQL-builder, graphical join and AI-assisted query workflow with verifiable delivery evidence.

## Existing planning and evidence sources

- `README.md`
- `knowledge/`
- `GitHub pull requests`
- `GitHub Actions`

## Status values

- 🔵 PLANNED
- 🔨 IN PROGRESS
- 🚫 BLOCKED
- ⏳ AWAITING ACCEPTANCE
- ✅ COMPLETE
- 💤 DEFERRED

## Evidence standard

Do not mark an item COMPLETE because a person or AI says it is complete. Verify all applicable evidence:

1. implementation exists;
2. expected files changed;
3. a non-empty diff or equivalent implementation evidence exists;
4. tests exist or a reason for no test is recorded;
5. relevant tests pass;
6. CI passes where available;
7. commit/PR evidence is recorded;
8. the change is merged into the intended branch where required;
9. external/user acceptance is recorded separately.

If evidence is missing, use IN PROGRESS, BLOCKED or AWAITING ACCEPTANCE.

For coding work, an empty result, no write/edit action, unchanged branch HEAD, empty diff and missing requested validation are evidence that the task is not complete.

## Development ledger

### OPS-UDA-001 — UDA application subpath
Status: 🔨 IN PROGRESS
Scope: registered QueryBridge application only.
Changes: Flask single-hop trusted forwarded prefix; Jinja page base and static routing; same-origin API fetch adapter.
Security: backend ingress must be proxy-restricted. No UDA public proxy enablement.
Evidence: `tests/test_uda_subpath.py` and `.github/workflows/uda-tests.yml`; awaiting CI.
- [ ] Full CI passes and merged into main for UDA deployment
- [ ] User verifies GUI, AI chat, schema capture and SQL generation through UDA


### DEV-000 — Establish evidence-based development ledger

Status: ✅ COMPLETE

Requirement:
Give the user and AI agents one persistent place to see plans, progress and proof of completion.

Evidence:
- Files: `DEVELOPMENT.md`, `AGENTS.md`
- Git history records the commits creating this standard.
- Tests: not required for this documentation/process-only change.
- User acceptance: requested 2026-10-02.

Completion criteria:
- [x] Common statuses defined.
- [x] Evidence rules defined.
- [x] False-completion rule defined.
- [x] AI maintenance rule added.

## New item template

### DEV-XXX — Short title

Status: 🔵 PLANNED
Priority: Medium

Requirement:

Implementation:

Evidence:
- Commit:
- PR:
- Files:
- Tests:
- CI:
- Merged to intended branch:
- User/business acceptance:

Completion criteria:
- [ ] Implementation exists.
- [ ] Relevant files changed.
- [ ] Tests added/updated, or reason recorded.
- [ ] Relevant tests pass.
- [ ] CI passes where applicable.
- [ ] Commit/PR evidence recorded.
- [ ] Merged where required.
- [ ] External/user acceptance separated from development completion.

Notes:

## Parallel development coordination

Use the coordination fields on every active DEV item when parallel work is possible.

- **Owner/Agent** — the person or AI agent currently responsible for the item.
- **Branch** — the working branch or worktree used for the item.
- **Depends on** — DEV items, decisions or external prerequisites that must complete first.
- **Can run in parallel with** — DEV items that are safe to develop concurrently without conflicting ownership or sequencing.
- **Integration status** — for example: not started, isolated, ready for integration, integrated, or integration blocked.

Before starting parallel work, agents should check these fields and avoid claiming the same item, branch or overlapping integration responsibility. If two items touch the same subsystem or files, record the conflict explicitly and sequence or coordinate integration rather than assuming they are independent.

Parallel execution does not weaken the completion standard: each DEV item still requires its own implementation, tests/validation, CI evidence where applicable, and integration/merge evidence before it can be marked COMPLETE.

## Maintenance rule

Update this file during the same development pass that changes implementation. When prose and repository evidence disagree, repository evidence wins.


### DEV-001 — Searchable schema explorer with field joins

Status: ⏳ AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: feature/searchable-schema-catalogue
Depends on: existing captured SQLite schema and relationship provenance
Can run in parallel with: non-overlapping development outside app.py, templates, styling and tests
Integration status: merged to main via PR #2 (squash commit 52e45a3930293a8ee3bf3893fb0a34b5ba6bfe02); user validation pending

Requirement:
A user-facing table of application, catalog, schema, table and field metadata, searchable
across identifiers and descriptions; selecting a field shows all recorded joins.

Implementation:
- New /catalogue page with server-side filtered, paginated metadata search
  and responsive field inspector.
- Bidirectional relationship lookup with SQL equality condition, target,
  confidence, source and notes; unlinked fields are explicitly identified.
- Optional explicit application name per table, without conflating it with
  Databricks catalog/schema. Label is editable and survives schema snapshot round trip.
- SQLite migration for legacy tables and backwards-compatible snapshot loading.
- Navigation entry on every existing application page.

Evidence:
- Files: app.py; templates/catalogue.html; templates/* navigation;
  static/style.css; tests/test_catalogue.py; README.md.
- Tests: tests/test_catalogue.py covers search, app filter, injection-like text,
  relationship direction/provenance, snapshot compatibility, legacy DB migration,
  write validation and reverse-proxy path.
- CI: QueryBridge Python Check (includes pytest) and UDA Compatibility passed on PR #2.
- Commit/PR: feature/searchable-schema-catalogue, https://github.com/zageabb/querybridge/pull/2.
- Merged to intended branch: main, squash commit 52e45a3930293a8ee3bf3893fb0a34b5ba6bfe02.
- User/business acceptance: pending user test in UDA.

Completion criteria:
- [x] Implementation exists on feature branch.
- [x] Relevant files changed.
- [x] Tests written.
- [x] Automated tests pass.
- [x] CI passes.
- [x] PR reviewed and merged.
- [ ] User verifies schema search and joins in deployed UI.

Notes:
This feature uses local metadata only, and does not infer new relationships.
The optional application label is intentionally separate from Databricks catalog and schema.


### DEV-002 — Authenticated local metadata administration

Status: ⏳ AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: feature/metadata-admin-console
Depends on: DEV-001 Schema Explorer and current SQLite schema
Can run in parallel with: changes outside schema metadata/navigation
Integration status: merged into main via PR #3; user deployment/acceptance pending

Requirement:
Provide an administrative data overview and controlled create, update, delete capabilities
for locally stored application/table/field/relationship metadata.

Implementation:
- Admin dashboard with table search, field editor, relationship controls and recent-change log.
- Fail-closed password + signing-secret configuration, session login, four-hour session
  expiry, CSRF protection for admin writes, and logout.
- Validation against missing/duplicate names and invalid types/nullability/ordering.
- Deletion prompts with cascade counts and explicit acknowledgement.
- Persistent qb_admin_audit records for changes.
- Reverse-proxy-safe script/API links.
- Existing Databricks source data remains untouched.

Evidence:
- Files: admin_console.py, app.py, templates/admin.html, static/admin.js,
  static/style.css, tests/test_admin.py, navigation templates, README.md.
- Tests: tests/test_admin.py for login, disabled mode, CSRF, UDA subpath,
  CRUD, join direction, deletion impacts, audit and input validation.
- CI: QueryBridge Python Check (pytest + JS syntax) and UDA Compatibility passed on PR #3.
- PR: https://github.com/zageabb/querybridge/pull/3
- Merged to main: yes (squash commit cef1f09a57ced42bbf7b7f871d412abbee958135).
- User acceptance: pending.

Completion criteria:
- [x] Backend and frontend implemented on feature branch.
- [x] Tests written.
- [x] Automated tests pass.
- [x] CI checks pass.
- [x] PR merged into main.
- [ ] Admin verifies UI and database data on deployed installation.

Notes:
Admin protects the *new* endpoints, not QueryBridge's other legacy metadata
mutation workflows. Before major deletions, save a named schema snapshot.


### DEV-003 — Remove separate Admin password

Status: ⏳ AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: feature/admin-no-password
Depends on: DEV-002 metadata administration
Can run in parallel with: non-admin changes
Integration status: merged to main via PR #4, user deployment/acceptance pending

Requirement:
Open the Admin screen immediately in this single-user QueryBridge installation
without a separate password or administrator sign-in step.

Implementation:
- Remove admin login, logout, account-configuration gate and sign-in UI.
- Preserve server-side input validation, audit logging and confirmations for deletes.
- Preserve session-based anti-CSRF token on admin mutations; issue it automatically on
  Admin page load without any login, and return 403 on missing/invalid tokens.
- Generate a secure random Flask session signing key by default; optionally use the
  configured shared QUERYBRIDGE_SESSION_SECRET for stable multi-worker sessions.
- Keep UDA subpath compatibility and update user documentation.

Security boundary:
Anyone who can access the QueryBridge app can use Admin. Network/reverse-proxy
access control must restrict the entire application. This does not add Databricks writes.

Evidence:
- Files: admin_console.py, templates/admin.html, app.py, tests/test_admin.py,
  README.md, DEVELOPMENT.md.
- Tests: password-free page/API access, CSRF rejection, UDA route, CRUD and audit.
- CI: QueryBridge Python Check and UDA Compatibility both passed on PR #4.
- PR: https://github.com/zageabb/querybridge/pull/4
- Merged: yes, squash commit 070a8c5609ff8ab867f42da4052694a9ed20332a.
- User acceptance: pending.

Completion criteria:
- [x] Implementation and revised tests exist.
- [x] Automated tests pass.
- [x] CI checks pass.
- [x] PR merged into main.
- [ ] Deployed UI confirmed by user.


### DEV-004 — Fix Admin security-token error in UDA deployment

Status: ⏳ AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: fix/admin-csrf-worker-safe
Depends on: DEV-003 password-free Admin
Integration status: merged into main via PR #5; deployed user confirmation pending

Observed:
User reported "Invalid administration security token. Reload Admin and retry."
after removal of Admin password. The prior implementation stored the anti-CSRF
token in a signed Flask session while app.py now generates random signing
secrets per process by default. Different workers may reject each other's
session cookie; a missing/undelivered cookie can yield the same symptom.

Implementation:
- Use a dedicated double-submit CSRF cookie and matching request header in
  Admin, independent of Flask's session-signing key.
- Scope the cookie to the app's UDA forwarded mount path; mark HttpOnly and
  SameSite=Lax, Secure for HTTPS.
- Check same-origin browser request headers when present; continue rejecting
  missing/mismatched tokens.
- Keep password-free Admin, existing validation, audit and delete prompts.
- Add regression for different worker secrets and reverse-proxy cookie path.

Evidence:
- Files: admin_console.py, tests/test_admin.py, README.md.
- Tests: passed, including secret-rotation, forwarded prefix/cookie path, missing cookie and cross-origin guards.
- CI: QueryBridge Python Check and UDA Compatibility both passed on PR #5.
- PR: https://github.com/zageabb/querybridge/pull/5
- Merged to main: yes, squash commit e50461e7e6abe12c1c6b726ae62a7242e0a828d2.
- User acceptance: pending after UDA deployment.

Completion criteria:
- [x] Code and regression tests added.
- [x] Tests pass.
- [x] Both CI workflows green.
- [x] PR merged to main.
- [ ] User verifies editing in deployed Admin.


### DEV-005 — Visual Schema Map with Graphviz field links and Mermaid export

Status: ⏳ AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: feature/schema-relationship-map
Depends on: DEV-001 Schema Explorer and captured metadata/joins
Integration status: merged to main through PR #6; UDA user acceptance pending

Requirement:
Provide an overview of stored table relationships, a detailed field-level
relationship diagram, the option to include unjoined tables, and application
filtering. Compare and reuse ideas from Mermaid Final and the entity diagram
capability of System Knowledge Designer.

Architecture:
- Graphviz HTML table rows/field ports from System Knowledge Designer's
  established renderer are adapted for precise local schema visualisation.
- Mermaid Final compatibility remains through .mmd export.
- New read-only Schema Map Flask blueprint and JSON/SVG/DOT endpoints.
- New canvas, table search/inspector, application, unassigned, unjoined,
  cross-application and one-hop focus filters, field highlighting and zoom.
- Distinct style for isolated and cross-application tables.
- Client-side labels escaped for Mermaid export; server-side data escaped for
  Graphviz. No AI-generated or hypothetical joins.

Evidence:
- Files: schema_map.py, schema_graphviz.py, templates/schema_map.html,
  static/schema-map.js, static/schema-diagram.js, static/style.css,
  app.py, navigation templates, tests/test_schema_map.py,
  tests/test_schema_diagram.cjs, README.md, Python CI workflow.
- Tests: new Graphviz API/UI/field ports/UDA tests and Node Mermaid generator tests.
- CI: QueryBridge Python Check (Graphviz, Node, pytest) and UDA Compatibility passed for e28c32635999001c7b5b8fdcf8fbd73b78ea613f.
- PR: https://github.com/zageabb/querybridge/pull/6
- Merged: yes; squash commit 6426330d23eb4eb7f5de3869d72a9decd87f4634.
- User acceptance: pending on deployed Ubuntu app.

Completion criteria:
- [x] Implementation and tests written.
- [x] Automated tests green.
- [x] CI workflows green.
- [x] PR merged into main.
- [ ] User confirms diagram works with live metadata in UDA.


### DEV-006 — Restore application awareness and no-change proposal handling

Status: ⏳ AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: fix/ai-proposals-application-awareness
Depends on: DEV-001 application label, AI Skills and local schema SQL analysis
Integration status: merged to main via PR #7, user UDA verification pending

Observed:
AI Skills proposal #8 ("No schema changes required") displayed "This proposal
no longer validates against the current schema" in the screenshot despite
having no operations. AI schema context and isolated SQL analysis omitted the
newly introduced application_name, so AI could not reliably scope review by
source application.

Implementation:
- Carry application_name through LLM schema context and read-only
  schema_tables/schema_fields metadata, plus left/right application labels
  for schema_relationships.
- Explain the distinction between application and catalog/schema in AI SQL
  reference and planner instructions.
- Classify proposed records into ready, no_changes, invalid; keep real stale
  operations blocked, with per-operation validation reasons.
- Show an informative no-change state and Dismiss action instead of a
  misleading stale warning. Reject applying empty lists even by direct POST.
- Preserve existing schema identities, snapshot format and approved operations.

Evidence:
- Files: app.py, templates/ai_skills.html, static/style.css,
  tests/test_ai_application_proposals.py, README.md, DEVELOPMENT.md.
- Automated tests: metadata SQL application filters, no-op review, invalid
  proposal reasons, valid apply and LLM prompt application context.
- CI: QueryBridge Python Check and UDA Compatibility green for PR #7, head 848ad50cdf594a3245fcb7865a314e4dcd64c4e4.
- PR: https://github.com/zageabb/querybridge/pull/7
- Merged to main: yes, squash commit cacf6bf59a9d3cabbc8bc3e42690d46971702864.
- User acceptance: pending deployed UDA verification.

Completion criteria:
- [x] Implementation and regression tests added.
- [x] Automated tests pass.
- [x] CI green before merge.
- [x] PR merged into main.
- [ ] User verifies proposal #8 warning removed and app-specific review accurate.



### DEV-007 — Actual schema answers and SAP link imports

Status: AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: fix/ai-schema-informational-answers
Depends on: DEV-006 application metadata, Admin and schema proposal validation
Integration status: merged to main via PR #8, deployed user acceptance pending

Observed:
AI Skills "List of tables" produced proposal #9 with a generic "no schema
changes required" statement, not an answer with the actual captured tables.
Its no-op proposal displayed a disabled Apply button. Subsequent user request
requires an SAP S/4HANA relationship import format that can add missing
tables/fields to the working subset without assigning a schema or saving a
schema snapshot.

Implemented:
- Separate read-only Ask about schema from Generate change proposal, with
  distinct history/status and no Apply for read-only answers.
- Local deterministic table inventory responses, optionally filtered by
  application, with field/join counts and no Ollama dependency.
- Other informational questions use a read-only LLM prompt.
- Backward-compatible request_kind/request_text migration on proposals.
- Dedicated SAP JSON manifest, sample purchasing/supplier relationship data,
  upload preview and explicit confirm in Admin.
- Atomic, idempotent import of missing local tables/fields/links. Newly added
  tables have NULL catalog/schema and SAP S/4HANA application; existing data
  and named snapshots remain unchanged.
- Admin CSRF and audit preserved.

Evidence:
- Files: app.py, schema_answers.py, sap_links_import.py, admin_console.py,
  templates/ai_skills.html, templates/admin.html, static/sap-links.js,
  static/style.css, samples/sap_s4hana_links_template.json,
  tests/test_schema_answers_and_sap_import.py, README.md, CI workflow.
- CI: QueryBridge Python Check and UDA Compatibility both green for PR #8 head 7a57e691ab39bccffad146ffa9456111b2f3e8f3.
- PR: https://github.com/zageabb/querybridge/pull/8
- Merge to main: yes, squash commit 30b31ced88d2d2258242b96ce2c104ed4f0f192d.
- UDA user acceptance: pending.

Completion criteria:
- [x] Code, sample and tests added.
- [x] Full tests and CI green.
- [x] PR merged into main.
- [ ] User verifies file import, table listing and missing metadata in deployed UDA.



### DEV-008 — SAP DDIC complete dictionary import with descriptions

Status: AWAITING ACCEPTANCE
Priority: High
Owner/Agent: ChatGPT
Branch: feature/sap-ddic-full-dictionary-import
Depends on: DEV-007 SAP link JSON import, metadata application labels
Integration status: merged via PR #9, actual SAP DDIC data and Ubuntu acceptance pending

User requirement:
Pull the full standard SAP S/4HANA table dictionary with field descriptions
and allow importing all metadata without assigning Databricks catalog/schema
or creating named schema snapshots.

Limitations:
There is no single externally available, release-independent "complete" SAP
table and field dictionary. The installed system's DDIC is the authoritative
source. Access/permission to the specific SAP environment is not connected,
so the importer accepts its exported records but cannot fetch them remotely.

Implementation:
- Supply a read-only HANA SQL template exporting activated DD02L/DD02T/DD03L
  plus English description text from DD04T/DD03T to CSV.
- Add scripts/import_sap_ddic.py for efficient CSV streaming import of all
  captured table/field rows (dry-run default; explicit --apply).
- Preserve existing table/field records; fill blank descriptions/types only.
- Add qb_tables.description with old-database migration; maintain snapshot
  roundtrip and backward compatibility.
- Expose descriptions to Admin, Schema Explorer search and AI schema context.
- Default names match sap_* convention; leave new local Catalog/Schema NULL.
- No synthetic relationships, snapshot saves, source database writes, or
  automatic Databricks operations.
- Add Admin discoverability and downloadable SQL template, README documentation.
- Test rollback, duplicate table ambiguity, idempotence, descriptions and
  snapshot compatibility.

Evidence:
- Files: scripts/export_sap_ddic_hana.sql, scripts/import_sap_ddic.py, app.py,
  admin_console.py, templates/admin.html, static/admin.js,
  tests/test_sap_ddic_bulk_import.py, README.md and DEVELOPMENT.md.
- Tests: all Python tests passed, including full DDIC CSV import and snapshot tests.
- CI: QueryBridge Python Check and UDA Compatibility both green on PR #9, head 735809e9d54b395e54c259f138e718957af48cf6.
- PR: https://github.com/zageabb/querybridge/pull/9
- Merged to main: yes, squash commit 89cda2fea065b83638e0385e9b6482524ff98561.
- User acceptance: pending actual SAP CSV and Ubuntu bulk run.

Completion criteria:
- [x] Read-only export template, importer, metadata model and tests added.
- [x] Relevant tests passing.
- [x] CI green.
- [x] PR merged.
- [ ] Real SAP dictionary export/Ubuntu deployment verified.


### DEV-016 — P0 combined Databricks + Application UI schema and offline HTML

Status: REBASED ON PR15 — CI AND USER ACCEPTANCE PENDING
Priority: P0
Owner/Agent: ChatGPT
Branch: fix/p0-export-rebase-pr15
Depends on: DEV-005, merged source→EDP→application layer features PRs #11–14
Integration status: PR #17 superseded by reconciled branch; **not merged**; old export PR #10 overlaps and must not be merged independently

Requirement:
Show Databricks/EDP selected technical fields side by side with consuming
application fields, joined by explicitly recorded directional field mappings.
Supply that combined view in both Schema Map and a single offline interactive
HTML export with filter, pan/zoom, expand/collapse and field highlighting.

Implementation:
- New `combined` layer graph projection reuses explicit layer lineage metadata;
  includes recorded Databricks→application field mappings, excludes source dictionaries
  from this focused two-layer view and maintains source lineage in End-to-end.
- Schema Map layer selector, API and Graphviz/Mermaid mapping directions.
- Offline HTML snapshot contains Source, Databricks, Application, Combined and
  End-to-end graphs; interactive layer/application/focus/unjoined/cross-app
  filters, search, zoom/pan and exact field-endpoint mapping links.
- Read-only export with escaped JSON; does not access source business records.
- Tests for different-named UI fields, multi-source and fan-out lineage,
  Graphviz field ports and portable HTML bundle.

Evidence:
- PR: https://github.com/zageabb/querybridge/pull/17
- Issue: https://github.com/zageabb/querybridge/issues/16
- Tests added: tests/test_combined_schema_export.py
- CI: **No checks or workflow runs reported at review time**. No green-CI claim.
- User/business acceptance: pending deployment.

Completion criteria:
- [x] Implementation committed to feature branch.
- [x] Regression tests written.
- [ ] Python and Node tests verified passing.
- [ ] UDA compatibility CI verified green.
- [ ] PR merged to main.
- [ ] User confirms combined map and offline export against real TAIJU mappings.

Notes:
The application metadata layer holds consumed application fields; actual UI
screen/control display labels require explicitly captured UI metadata and
must not be inferred from technical field names.


### DEV-017 — Graphviz-quality field connector routing in exported HTML

Status: IMPLEMENTED IN FEATURE BRANCH; CI / USER ACCEPTANCE PENDING
Priority: High
Branch: feature/html-export-graphviz-routing
Depends on: DEV-016 (combined UI/export), Graphviz on export server
Requirement: Replace simplistic fixed-grid diagram lines with Graphviz-ranked table layout and live HTML5/SVG orthogonal connectors that attach to exact field rows.
Implementation: server-side Graphviz dot -Tplain node rank/order; self-contained HTML SVG connector routing with rounded orthogonal corners, obstacle-aware gutter candidates, directional lineage arrows, draggable table cards and link redraw on drag, expand/collapse and filter updates. No external runtime dependencies.
Evidence: tests/test_combined_schema_export.py extended with Graphviz metadata and HTML interaction checks; CI and merge pending.
Completion criteria:
- [x] Source implementation and regression tests committed
- [ ] Full automated tests green
- [ ] UDA CI green
- [ ] Merged to main
- [ ] Manual test of representative complex TAIJU mapped schema


### DEV-018 — Notes-style themes and a draggable live Schema Map

Status: IMPLEMENTED ON FEATURE BRANCH — CI AND USER ACCEPTANCE PENDING
Priority: High
Branch: feature/schema-map-live-interactive-themes
Depends on: DEV-017 merged Graphviz-quality offline HTML renderer
Requirement: Give both QueryBridge and its exported schema viewer persistent light/dark themes like Notes; allow moving tables and rerouting links in both the live map and export.
Implementation: Shared `static/theme.js` and dark CSS palette across QueryBridge pages; themed self-contained offline HTML; live Schema Map switch between draggable embedded offline-renderer engine and original Graphviz output; same recorded field-to-field mappings and filters; saved positions and reset.
Evidence: `tests/test_combined_schema_export.py` includes theme and embedded view coverage; automated CI pending.
Completion criteria:
- [x] Code and tests added
- [ ] Full CI green
- [ ] Merged main
- [ ] Manually verified in light/dark and live/standalone views


### DEV-019 — Application consumption, Schema Explorer layers, and canvas-aware image export

Status: IMPLEMENTED ON FEATURE BRANCH — CI/USER ACCEPTANCE PENDING
Branch: fix/application-consumption-view-aware-exports
Scope: Layer-specific application choices and actionable empty consumption state; Schema Explorer Databricks + Application and field inspector; PNG/SVG export of currently selected Graphviz or draggable HTML5 canvas; CI syntax check for explorer.
Tests: tests/test_combined_schema_export.py (consumption layer, explorer, Graphviz PNG, interactive exporter availability), existing schema tests.
Safety: No guessed mappings. Canvas export respects local placement, visible fields and selected layer. No business data rows embedded.
- [x] Feature code and regression tests committed
- [ ] CI green
- [ ] Merge to main
- [ ] Verify with real TAIJU application mapping data


### DEV-020 — Adopt Application-Standard screen governance and create Figma redesign
- **Status:** IN PROGRESS — documentation/Figma draft, CI and manual visual/user acceptance pending.
- **Priority:** high; future UI work must follow the adopted governance gate.
- **Branch:** `docs/adopt-application-standard-and-figma`.
- **Reference:** `zageabb/Application-Standard` v1.0, not a verified separate `standard_template` repository.
- **Requirements:** inspect current screens, align non-destructively with standard's AGENTS, development register, DID, versions, screen specs, Figma handoff, component reuse and user manual. Do **not** rewrite Flask/SQLite merely to match preferred React/FastAPI examples.
- **Gap assessment:** see `docs/SCREEN_STANDARDS_ADOPTION.md`; inherited QueryBridge AGENTS/DEVELOPMENT present but DID, STANDARD_VERSION, screen inventory/spec and Figma handoff missing prior to this change.
- **Figma draft:** https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5 ; nine desktop screens, dark schema map, three mobile screens; editable concept art, not code parity or accepted implementation.
- **Documentation paths:** `STANDARD_VERSION.md`, `DID.md`, `docs/SCREEN_STANDARDS_ADOPTION.md`, `docs/SCREEN_INVENTORY.md`, `docs/SCREEN_SPEC.md`, `docs/FIGMA_HANDOFF.md`; update README and AGENTS.
- **Capability reuse assessment:** Application-Standard registry identifies `schema-graph` as a QueryBridge-originated candidate; no published compatible shared package verified; retain existing implementation and review reuse before new features.
- **Manual impact:** documentation/design-only change; current user-visible routes and workflows untouched. README remains current user guide; actual UI implementation PRs must update manual concurrently.
- **Security:** synthetic demo data only; Figma does not contain production/source corporate records. Enterprise connectors remain optional.
- **Completion evidence:** files [x]; Figma draft [x]; automated docs/code CI [ ]; merged [ ]; direct/UDA [not applicable to docs change]; owner design acceptance [ ].
- **Next:** create per-screen QB-XX specs; approve common tokens and Figma frames; implement shared shell and screen updates in focused green-CI PRs with responsive/manual QA.
