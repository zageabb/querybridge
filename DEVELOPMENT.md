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
