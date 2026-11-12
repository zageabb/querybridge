# QueryBridge — standard adoption record

- **Reference:** [Application-Standard](https://github.com/zageabb/Application-Standard), `standards/Application_Design_Development_Standard_v1.0.md`.
- **Adopted version:** 1.0 documentation baseline (proposed visual tokens, not certified brand).
- **Application profile:** existing self-hosted data/schema engineering tool; web browser desktop/mobile.
- **Assessment date:** 2026-11-12.
- **Existing stack:** Flask, Jinja, vanilla JavaScript, SQLite, Graphviz + standalone HTML5/SVG; no technology-stack rewrite required for adoption.
- **Architecture exception:** React/MUI/FastAPI/PostgreSQL are preferred for *new* enterprise web projects, **not mandatory for existing applications**. QueryBridge's current implementation remains supported. Review new dependencies through ADR and capability registry before changing.
- **Shell:** shared responsive QueryBridge application shell; light/dark token modes; specialist full-screen diagram and query builder workspaces.
- **Source of truth:** `AGENTS.md`, `DEVELOPMENT.md`, `DID.md`, `docs/SCREEN_STANDARDS_ADOPTION.md`, `docs/SCREEN_INVENTORY.md`, `docs/FIGMA_HANDOFF.md`.
- **Figma:** https://www.figma.com/design/EDqSijN3CkN06Q06ZM9hI5 (draft design frames, not implementation approval).
- **Non-goals:** no forced UI rewrite, no replacement of source graph joins or data storage, no enterprise integration activation.
- **Status:** documentation governance adopted; individual screen implementation parity, responsive acceptance, accessibility and deployed UDA acceptance pending.
