<!-- Imported from zageabb/Application-Standard/docs/FIGMA_COMPONENT_CATALOGUE.md, baseline v1.0; adaptation rules in ../SCREEN_STANDARDS_ADOPTION.md. Upstream remains authoritative. -->

# Figma component catalogue and React/MUI mapping

**Status:** proposed library design based on the 10 supplied 2026-10-21 application screenshots. Screenshots demonstrate visible states; unseen business logic is to be confirmed. Start with the official MUI Design Kit, subject to licence and availability. This catalogue is **not** evidence that a live Figma library exists.

## Figma library organisation
- 00 Foundations — colour modes, type styles, grid/spacing, radii, elevation, icons, semantic status.
- 01 Primitives — text, icons, dividers, avatar, surfaces, focus markers.
- 02 Controls — buttons, search, filters, text inputs, selects, checkboxes, date fields, chips, tooltips, menus.
- 03 Navigation — top bar, app switcher, dark sidebar, breadcrumbs, page header, tabs, section navigator.
- 04 Data — metric/KPI card, status-dot-with-label, status timeline, data grid, financial summary, pagination, export actions.
- 05 Workflows — field section, accordion, process stepper, audit/history, save/publish actions.
- 06 AI — assistant panel, chat composer, message, agent/app card, citations, streaming/progress.
- 07 Patterns — dashboard, project detail, sourcing strategy list/editor, AI landing, AI chat.
- 08 Screen prototypes — working reference designs only after explicitly built/approved.
- 09 Archive — superseded variants with a replacement link.

## Component mapping register
| Figma component or pattern | Preferred React mapping | Key properties/states |
|---|---|---|
| AppShell/Light | MUI AppBar, Toolbar, Container/Box | breadcrumbs, toolbar actions, density, responsive |
| AppShell/DarkNav | Drawer, List, Box | expanded, collapsed, selected, inaccessible |
| ProjectBreadcrumbs | Breadcrumbs, Link | active route, overflow |
| ScreenHeader | Typography, Stack, Button | title, subtitle, metadata, primary action |
| StatusDot | Box or approved custom + Tooltip | healthy, attention, risk, neutral, unknown, disabled |
| KPI/MetricCard | Card, Typography, Stack | amount, label, unit, source, loading, unknown |
| DataTable/Procurement | TanStack Table + MUI Table | sort, filter, hide, select, export, scroll, edit |
| Form/Text | TextField | required, invalid, disabled, read-only, help |
| Form/Select | Select / Autocomplete | empty, loading, invalid, dependent |
| Form/Section | Accordion / Paper | expanded, dirty, validation-summary |
| Workflow/Steps | Stepper / approved custom | progress, completed, blocked, unknown |
| ActionToolbar | Stack, IconButton, Tooltip, Menu | search, refresh, export, actions |
| AppLauncherCard | Card, CardActionArea | enabled, disabled, permission, favourite |
| AssistantPanel | Drawer or Box + chat composition | open, closed, streaming, error |
| AI/Composer | multiline TextField + buttons | typing, attachment, sending, unavailable |
| AI/Message | Box + approved Markdown renderer | roles, citations, timestamps, errors |
| EmptyAndLoading | Skeleton, Alert, Progress | zero data, fetching, failed, not configured |
| StatusDonut | approved chart library | counts, legend, no data, keyboard alternative |

## Naming and variant rules
- Use **component/category/variant** naming; property names map to code concepts: size, variant, state, density, mode.
- No separate copies per screen for identical buttons, fields, cards or status symbols.
- Use modes Light and Dark Navigation only where the reference actually establishes a distinction.
- Icon-only actions MUST expose accessible text and a tooltip.
- Components include default, hover, focus-visible, active/selected, disabled, invalid and loading variants where meaningful.
- Keep selected tab distinct from hovered tab. Separate yellow *potential risk* from red *at risk* status visually and textually.
- Every graphical status has a non-colour equivalent; chart legends, table cell labels and ARIA descriptions must match.

## Patterns derived from supplied screenshots
1. SCM home/launcher — Akira greeting + grouped applications and quick links.
2. Digital PPP portfolio — status donut, supplier spend, health KPI cards, dense data table.
3. Project detail — project ribbon, milestone/status icons, summary tiles, line-item grid.
4. Tender Sourcing Strategy list — favourites, searchable table, health status symbols.
5. TSS editor — left-hand step menu, hierarchical sections, structured inputs, publish.
6. Akira landing/chat — dark sidebar, centred chat, tool search, agent cards.
7. Embedded Akira assistant — right-side panel coexisting with project detail.
8. Loading/transitional overlay — explicit progress state rather than an empty working page.

## Validation
Confirm Noto Sans or actual source theme font before final token approval. Perform checks at the screen sizes in SCREEN_BUILDING_STANDARD.md and against WCAG 2.2 AA where applicable. When the official MUI kit does not cover specialist needs, document the custom component and its API/states in docs/LIBRARY_REGISTER.md.
