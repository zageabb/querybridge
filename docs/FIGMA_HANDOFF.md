# QueryBridge — Figma Design Handoff

- **Figma file:** https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5
- **Design date:** 2026-11-12
- **Status:** DRAFT — native editable frames; synthetic sample data; not implementation-ready or user-approved.
- **Reference:** Application-Standard v1.0 screen-building, design-system, QA checklist and screen-spec templates.
- **Owner:** QueryBridge project.
- **Technical implementation:** Flask/Jinja/JavaScript; use shared components and tokens in this stack, not an assumed React migration.
- **Responsive:** desktop 1440×920, mobile 390×844 drafts; 1280/1024/768, zoom 200% not yet formally validated.
- **Theming:** Light and dark screen examples; semantic token consolidation remains implementation work.
- **Prototype:** static editable visual layouts, not functional clickable transitions; no Figma parity assertion.
- **Library:** Figma Material 3 library available, reuse its components where applicable and approved; specialist graph controls documented as custom.
- **Privacy:** only synthetic example schemas; no actual SAP/EDP or corporate data imported.

## Handoff expectations
Every approved Figma frame must link a QB-XX screen spec, component-to-code mapping, final token values and keyboard/responsive/empty/error states. A code PR must cite Figma URL, baseline screenshot and pass tests plus direct/UDA route checks. User acceptance recorded separately.

## Design frame inventory
Nine editable desktop page frames QB-01 through QB-09; one dark Schema Map; mobile Schema Explorer, Schema Map and Query Builder. Outstanding QB-10+ and state variants are tracked in `docs/SCREEN_INVENTORY.md`.

## Known gaps
Not yet verified in actual running QueryBridge. No automated browser screenshot diff or WCAG AA audit. MUI/Material 3 reuse is a design reference; application runs Flask, not a Material 3 implementation.
