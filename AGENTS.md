# AI Development Instructions

## Repository workflow

Before changing code:
1. Read `README.md`.
2. Read `DEVELOPMENT.md`.
3. Read relevant design, TODO, roadmap, release, phase and audit documents.
4. Inspect the existing implementation before proposing replacement architecture.

## Development completion evidence

For every meaningful feature or bug fix, create or update its entry in `DEVELOPMENT.md`.

Use only these states where applicable: PLANNED, IN PROGRESS, BLOCKED, AWAITING ACCEPTANCE, COMPLETE, DEFERRED.

Never mark a coding task COMPLETE merely because an agent says it is complete. Verify repository evidence:
- implementation exists;
- relevant files changed;
- a non-empty diff or equivalent evidence exists;
- tests exist or the reason for no test is recorded;
- relevant tests pass;
- CI passes where available;
- commit/PR evidence is recorded;
- merge status is recorded where required;
- external/user acceptance is kept separate.

An empty result, no write/edit action, unchanged branch HEAD, empty diff, or missing requested validation means the task is not complete.

When documentation conflicts with code, tests, Git history or CI, repository evidence wins.


## Application-Standard 1.0 adopted — mandatory for future changes (2026-11-12)

Standard source: `zageabb/Application-Standard` (`standards/Application_Design_Development_Standard_v1.0.md`). Follow `STANDARD_VERSION.md`, `DID.md`, `docs/SCREEN_STANDARDS_ADOPTION.md`, `docs/SCREEN_INVENTORY.md`, `docs/SCREEN_SPEC.md` and `docs/FIGMA_HANDOFF.md` after existing mandatory read order. Keep this existing Flask/Jinja/JavaScript/SQLite codebase; the optional React/MUI/FastAPI preference is **not an instruction to rewrite**.

- **Screen gate:** Before changing a UI, create/update its QB-XX screen spec with user goal, permissions, route, field/API ownership, relevant Figma frame ID, keyboard/touch/mobile behaviour, 1440/1280/1024/768/390 + 200% zoom checks, loading/empty/error/stale/no_permission/not_configured states, and theme/token mapping. Compare against Figma and actual screenshots; a draft Figma file is not proof of parity.
- **Common design:** Prefer shared shell/navigation, semantic light/dark CSS tokens, reusable filter/field/inspector/table/actions/alerts over one-off styles. Retain old Graphviz and new draggable HTML5 views; preserve five data-layer choices, explicit lineage, no guessed joins or UI fields, theme persistence and offline exports.
- **User manual:** In the same feature/bugfix PR, update end-user instructions in README or the dedicated manual and record affected sections; do not close a user-visible change while instructions are stale.
- **Shared capability gate:** Inspect Application-Standard registry/capability policy and `zageabb/shared-capabilities` for existing approved packages before duplicating significant functionality; registry candidate ≠ validated dependency. Record decision and licence/runtime/tests.
- **Quality gate:** Record tests, exact CI result and SHA, current PR/merge, actual UDA direct/prefixed behaviour, and separate user acceptance. New UI needs keyboard/focus/contrast and responsive QA; no blind mark COMPLETE. No forced green-CI bypass.
- **Proxy:** Label prefix-specific compatibility changes `LOCAL_UBUNTU_PROXY_COMPAT`; test `/` and `/apps/querybridge/` assets/API/headers with trusted proxy boundaries. No hardcoded hostnames or enterprise credentials.
- **Architecture exceptions:** Document any new framework, UI library, backend adapter, data migration or paid integration as a reviewed DID/ADR with a rollback; no production changes without explicit approval.
