<!-- Imported from zageabb/Application-Standard/docs/SCREEN_BUILDING_STANDARD.md, baseline v1.0; adaptation rules in ../SCREEN_STANDARDS_ADOPTION.md. Upstream remains authoritative. -->

# Screen Building Standard — reusable UI applications

**Revision:** 1.0 draft, 21 October 2026. **Scope:** new and changed P1/P2/P3 web screens; adapt appropriately for P4 native tools. This document is an implementation and design acceptance standard, not proof that the screenshots specify production-approved brand tokens.

## 1. Starting principle
Reuse approved Taiju/SCM/Akira screen patterns and MUI components first. Separate data, API state and business rules from the visual layout. A design should be recognisable as part of the same application family without forcing every tool into the same page shell. Follow docs/DESIGN_SYSTEM.md, docs/FIGMA_COMPONENT_CATALOGUE.md, docs/SCREEN_QA_CHECKLIST.md and templates/SCREEN_SPEC.md.

## 2. Screen construction sequence
1. Give the screen an ID, owner, application profile, user goal, primary action, required permissions and navigation entry/exit.
2. Choose one shell: **Taiju/SCM light** (top app bar and breadcrumbs), **Akira workspace** (dark sidebar and large content region), or **embedded assistant** (right drawer).
3. Choose a page archetype: launcher, overview/dashboard, dataset table, detail view, multistep form, AI conversation, specialist canvas, system/error.
4. Draw the information hierarchy before colouring: header and current location → primary information → user action → secondary context. Align in a common grid.
5. Compose from tokenised primitives/components rather than custom CSS per screen. Use responsive auto-layout in Figma and CSS layout in implementation.
6. Specify source, loading, error, zero-data, permission, disabled, validation, submitted, saved and stale states.
7. Define behaviour for keyboard, pointer, touch, 200% zoom, responsive widths, long labels and variable row counts.
8. Record component-to-code mappings and API/data ownership before developer handoff.
9. Review screenshots and acceptance at target widths; record deviations. Do not declare complete because Figma looks good.

## 3. Layout and responsive composition
- Use the existing desktop screenshots as **1910 × 993 px reference captures**, not as a required app viewport, device size, or breakpoint.
- Wide desktop: allow multi-column KPIs and large procurement tables. Keep sticky utility/header controls without obscuring content.
- Normal laptop: retain key controls and let dense grids scroll horizontally within their table region; preserve the primary action.
- Tablet: stack KPI rows, convert secondary summary panels to collapsible regions, and use controlled column visibility.
- Mobile: use a collapsible navigation drawer, one-column cards, logical field order, and task-centric list/detail views instead of shrinking desktop tables.
- Draft QA checkpoints: 1440, 1280, 1024, 768 and 390 CSS px, plus 200% zoom. These are **test checkpoints**, not asserted existing MUI theme breakpoints.
- Use an 8 px spacing system (4 px half-step where needed), 44 × 44 CSS px touch targets where practicable, visible focus and consistently named spacing tokens. Exact radius/height/colour values must be confirmed against the app's theme.
- Never fix a full-screen chat input at a position where viewport height or on-screen keyboard hides the send action.

## 4. Navigation, headers and context
- Page title is unique and meaningful. Breadcrumbs represent the real navigation route, not merely display text.
- Top utility menu and app switcher are consistent across Taiju modules; Akira may use its own sidebar shell with shared login/account components.
- Use one primary action per task view (e.g. Create TSS, Publish), with clear disabled and permission reasons.
- Persist filters/selection only when business rules permit; distinguish a saved favourite from an unsaved one.
- Distinguish navigation, modal action, destructive action and download/export icons with text or accessible name.

## 5. Cards, tables and financial figures
- Dashboard cards contain label, measure, unit, optional comparison, timestamp/source and meaningful zero/unknown state.
- Differentiate zero (0), unknown (—), not available (N/A) and **integration not configured**; never convert them to the same visual placeholder.
- Tables define row IDs, stable sorting, filters, pagination/virtualisation threshold, export contents, column resizing, keyboard navigation, selection and permitted edits. Use right alignment and tabular digits for numeric values.
- Large procurement tables should keep identity columns visible when horizontal scrolling; disclose hidden columns.
- For spend use explicit currency (USD in supplied screenshots), aggregation scale and context. A display such as "k 1,658,054.2" is ambiguous unless k and USD are explained.
- For green/amber/red status dots always provide a legend or accessible tooltip with text, rule/threshold, source and last evaluation time. Red must not be inferred automatically to mean an actual incident.

## 6. Forms and workflow
- Use visible labels, descriptive helper text, required indicators, controlled dropdown options and validation feedback near the field.
- Keep section/step navigation aligned with form sections. Changes should not disappear when moving between sections; indicate unsaved edits.
- Name and explain Save Draft, Update, Publish, Cancel and Close. Confirm consequential actions.
- Dates use explicit locale/timezone; numeric fields define units, precision, permitted ranges and meaningful zero.
- Conditional/derived values must specify source dependencies. Disabled should be different from read-only and permission-restricted.

## 7. AI/chat and specialist views
- Separate conversation transcript, source/citations, prompt composer, send/stop, attachment context and model/tool status.
- Show when a message is thinking/streaming, complete, errored or blocked. Do not imitate an authoritative result while a tool is unavailable.
- Respect sensitive corporate data constraints; screenshots, transcripts and examples use synthetic or explicitly authorised data.
- For optional enterprise integration show not_configured as a real state, not empty success.
- For charts and diagram canvases, include accessible summaries and downloadable or tabular alternatives.

## 8. Technical implementation rules
- New P1 web screens: follow the repository's React/MUI baseline and component map; TanStack Table where appropriate; React Hook Form for forms.
- Prefer semantic HTML, keyboard support and MUI tokens over absolute coordinates. Exceptions require an ADR.
- API calls use typed integration contracts; no raw enterprise credentials or secrets in the browser.
- Ubuntu route-base compatibility is configuration driven and labelled LOCAL_UBUNTU_PROXY_COMPAT in code; visual components may not hardcode reverse-proxy URLs.
- Define API data statuses: loading, success, empty, error, stale, not_configured, and no_permission as applicable.
- Separate design QA, unit/E2E testing, screenshot comparison, browser acceptance, deployment and business approval.

## 9. Screen sign-off
Do not sign off until the handoff template includes responsive widths, all meaningful interaction states, accessibility, component mapping, integration/data contracts, snapshot evidence, reviewed exceptions, owner and version. Record both Figma URL and live implementation URL only when they actually exist.
