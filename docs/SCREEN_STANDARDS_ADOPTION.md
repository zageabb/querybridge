# QueryBridge screen standards adoption / gap analysis

**Reference:** `zageabb/Application-Standard` v1.0. **Audit:** 2026-11-12. **Status:** proposed redesign / governance adopted, implementation pending.

| Requirement | Existing QueryBridge evidence | Decision / gap |
|---|---|---|
| Common navigation | Per-page Jinja `topbar`, site links | Consolidate into one shared partial and responsive navigation including active route/breadcrumb |
| Light/dark mode | `static/theme.js`, dark mode in `static/style.css` and HTML export | Preserve; replace overlapping one-off CSS with semantic light/dark tokens; test all pages |
| Common typography/spacing | Individual CSS, per-screen rules | Adopt common tokenized spacing/typography/density and explicit component variants |
| Source→EDP→App layers | `layer_graph.py`, Schema Explorer / Map | Preserve all five layer choices, exact recorded lineage and per-layer filters |
| Diagram canvas | Graphviz + HTML5 draggable/SVG rendering | Keep both modes, field endpoints, keyboard alternatives, offline HTML; responsive/narrow behaviour |
| SQL builder | `templates/builder.html` and JS | Preserve data model/SQL output, reorganize visual flow into panels and step navigation |
| Metadata and import | `templates/index.html` and capture workflow | Clarify source, parse/validation/error states and copy-paste import flow |
| Table and admin edit | Admin routes and `data_tables.html` | Expose actual permission, read-only, dirty, save, validation, audit states |
| Loading/empty/error | Mixed partial coverage | Standardize explicit loading, true zero, no_permission, error, not_configured, stale and retry |
| Accessibility | Native form controls, varying canvas treatment | Audit WCAG 2.2 AA contrast, keyboard focus, non-colour meanings, 200% zoom, SVG accessible summary |
| Responsive browser | Desktop-dense layouts, some CSS media queries | Design/test 1440,1280,1024,768,390 and mobile task-first list/detail alternatives |
| Standard repository docs | AGENTS, DEVELOPMENT present | Add DID, STANDARD_VERSION, SCREEN_INVENTORY, SCREEN_SPEC, FIGMA_HANDOFF, manual review |
| CI+deploy | Python, JS, UDA compatibility workflows | Preserve green-CI merge gate; add screenshot/screen tests and separate live verification |
| Reusable code | Candidate registry includes QueryBridge schema-graph | Check version/licensing/runtime before extracting or adopting shared capability |
| Figma proof | Created draft editable screen designs | Draft only; no code parity or owner visual approval claimed |

## UI implementation sequencing
1. Confirm shared shell tokens and navigation; no data/API refactor.
2. Implement Metadata and Schema Explorer shell using Figma approved frames.
3. Implement Schema Map controls with Graphviz/HTML5 parity and export behaviour.
4. Implement Query Builder/Data Tables workflow layouts.
5. Implement Knowledge/AI/Admin screens.
6. Complete mobile adaptation, interaction states, accessibility QA and screenshot comparisons.

## Required per-screen gate
Use `docs/SCREEN_SPEC.md` and `docs/FIGMA_HANDOFF.md` prior to UI work. Every PR includes affected screen IDs, acceptance state matrix, keyboard/touch/zoom/responsive checks, runtime/API mapping, user manual updates, CI run and direct/UDA route evidence. Design must use synthetic data. Screen design approval does not equal implementation acceptance.

## Documented technology decision
Keep Flask/Jinja/SQLite/JS until the user approves a migration. MUI is a visual and component-pattern reference; do not claim the current app is React/MUI. Current palette is application-local, not an approved corporate standard.
