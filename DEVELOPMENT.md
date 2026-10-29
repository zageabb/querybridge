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
