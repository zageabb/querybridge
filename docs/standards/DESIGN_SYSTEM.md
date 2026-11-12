<!-- Imported from zageabb/Application-Standard/docs/DESIGN_SYSTEM.md, baseline v1.0; adaptation rules in ../SCREEN_STANDARDS_ADOPTION.md. Upstream remains authoritative. -->

# Taiju / SCM / Akira — shared design system baseline

**Status:** draft, reference-screen-derived. **Date:** 21 October 2026. **Owners:** application/project leads (TBD). **Implementation alignment:** React/MUI for new P1 web applications. Current source images are confidential user-supplied screenshots; they are not approved public brand material.

## 1. Principles
- Consistency should come from tokens, components, layouts and behaviour, not blindly cloning each page.
- Keep two shell families: **SCM/Taiju light navigation** and **Akira/Hitachi dark sidebar**. Both share underlying field, status, data and AI components.
- Preserve the compact enterprise information density for desktop procurement screens, while providing accessible narrow-screen alternatives.
- Include primary flows, busy/empty/error/restricted states, keyboard and responsive behaviour in Figma.
- Prefer official MUI Figma kit/components, with documented custom variants for procurement and AI patterns.

## 2. Source and confidence
- Visual reference and filenames: docs/TAIJU_SCREEN_REFERENCE.md.
- Measured from pixels at 1910 × 993 capture: white surfaces, near-white page regions, dark sidebar, red action accent, green/red/amber status dots and pale-blue update chips. These are **observations** only.
- CSS/MUI theme files, typography metrics and official brand design standards have NOT been supplied or independently validated. All numerical tokens below are **candidate** values, not certified Hitachi Energy brand standards.
- When the theme is provided: replace measured candidates, record theme/version/source and approval, and compare rendered screens with the originals.

## 3. Candidate visual foundations

| Semantic token | Candidate | Evidence/condition |
|---|---|---|
| surface.default | #FFFFFF | white cards and content |
| canvas.subtle | #FBFBFB | off-white application background, sampled |
| nav.dark | #222222 | Akira dark sidebar, sampled |
| text.primary | #222222 | primary titles, observed |
| accent.action | #BB3430 | a visible red element in the portfolio capture; may vary by control |
| status.good | #478B1A | green indicator in procurement screenshot, sampled |
| status.danger | #CC0000 | red dot in procurement screenshot, sampled |
| status.warning | #F9C846 | sampled anti-aliased amber indicator; verify filled centre |
| border.subtle | #D9D9D9 | approximate visual edge, **not directly confirmed as theme** |
| surface.info | pale blue | update timestamp ribbon; exact solid fill TBD |

**Important:** Contrast approval has NOT been completed for these candidates. Some status colours are intended for non-text marks, not text. Use semantic roles and accessible accompanying text. Do not use these values as a corporate brand palette without approval.

### Type, spacing, density
- Existing Taiju technology inventory mentions Noto Sans; typography family and font weights must be verified against source CSS.
- Draft typography roles: screen title, section heading, card title, body, control label, table value, caption/meta.
- Draft spacing scale: 4 px base step, 8 px regular rhythm; avoid absolute positioning.
- Define density mode **comfortable** for forms and **compact** for procurement grids; do not change hit target sizes based solely on visible row density.
- Draft container behaviour: fluid desktops, explicit max readable line lengths, stacked cards in narrow layouts.
- Finalise breakpoint mapping only after theme/source validation. Use CSS checkpoints from docs/SCREEN_BUILDING_STANDARD.md for initial QA.

## 4. Layout families
**Shell/Light (Taiju/SCM):** top brand/app bar, breadcrumbs, title/action/refresh line, main sections, optional Akira panel. **Shell/DarkNav (Akira):** dark left sidebar, selection states, wide content region, centred chat/agent catalogue. Each shell defines keyboard navigation, collapse, overflow, user menu and account information.

**Dashboard:** KPI groups, financial summary, status card/indicator timeline and table. **Detail:** project title with metadata; health ribbon; multiple summary cards; related item grid. **Workflow editor:** steps at left; accordion sections at right; clear Save/Publish. **AI chat:** greeting, message transcript, composer, attachment/tool states. **System state:** loading, error, no data, no permission, not_configured.

## 5. Components, prototyping and handoff
- Catalogue and code mappings: docs/FIGMA_COMPONENT_CATALOGUE.md.
- Specific construction rules: docs/SCREEN_BUILDING_STANDARD.md.
- Figma workflow: docs/FIGMA_WORKFLOW.md and docs/FIGMA_HANDOFF.md.
- Per-screen specifications: templates/SCREEN_SPEC.md, templates/FIGMA_HANDOFF.md.
- Acceptance: docs/SCREEN_QA_CHECKLIST.md, docs/ACCEPTANCE.md.
- No Figma file, component library, prototype or published styles are asserted to exist until their links are recorded.

## 6. Change control
Give every design token an ID, semantic purpose, source reference, status (draft/approved/deprecated), maintainer, version and release date. Capture component breaking changes, approved extensions and new variants in CHANGELOG.md and the screen handoff. Link production code versions separately.
