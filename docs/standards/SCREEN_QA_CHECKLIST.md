<!-- Imported from zageabb/Application-Standard/docs/SCREEN_QA_CHECKLIST.md, baseline v1.0; adaptation rules in ../SCREEN_STANDARDS_ADOPTION.md. Upstream remains authoritative. -->

# Screen Design / UI QA acceptance checklist

Run this per screen when reviewing Figma and again against a running application. Mark each item PASS / FAIL / N/A with owner and evidence; an empty checklist is not approval.

## A. Definition and design
- [ ] Screen ID, purpose, role, route, entry/exit, owner, version and prototype/Figma link recorded.
- [ ] Correct Taiju/SCM or Akira shell and shared component instances selected.
- [ ] Hierarchy, alignment, grid, spacing, type and colours use named design tokens.
- [ ] Final tokens verified against source styles; drafts are labelled draft.
- [ ] Screens at 1440 / 1280 / 1024 / 768 / 390 CSS px reviewed (or documented exception).
- [ ] Full content remains usable at 200% zoom with long descriptions/translated labels.

## B. Interaction and data
- [ ] Primary actions have defined outcomes; navigation/back/close works.
- [ ] Search, sort, filters, favourites, paging, export and history states are specified where present.
- [ ] Meaningful loading, zero-data, failed, stale, not_configured, no-permission and retry states are handled.
- [ ] Status dots/charts include text equivalents and business thresholds.
- [ ] Dates, money, rounding, units, unknown and 0 values are visibly distinct.
- [ ] Forms cover required, optional, disabled, read-only, invalid, dirty and saved states.
- [ ] Publish/deletion/irreversible actions protect against accidental activation.
- [ ] AI messages disclose streaming, sources, tool failures, data restrictions and prompt attachments.

## C. Accessibility and security
- [ ] Tab order, keyboard operation, visible focus, ESC/back behaviour reviewed.
- [ ] Inputs have labels and errors linked to fields; icon actions have accessible names.
- [ ] Contrast targeted at WCAG 2.2 AA: normal text 4.5:1, large text 3:1, important non-text 3:1 unless exempt; automated checks supplemented by human testing.
- [ ] No colour-only communication. Touch targets meet WCAG 2.2 target sizing or documented exception.
- [ ] User-entered text/Markdown sanitised; sensitive data, identifiers and private screenshots handled under approved policy.
- [ ] API auth, permissions, not_configured and error messages do not leak secrets.

## D. Technical and evidence
- [ ] Component mapping to MUI/custom approved extension and test coverage recorded.
- [ ] Responsive and visual parity screenshots attached to screen spec.
- [ ] Direct-host and prefixed Ubuntu deployment tested where applicable.
- [ ] CI + behavioural/browser tests, commit SHA, deployment URL and business acceptance recorded separately.
- [ ] Unresolved issues have owners and exception/ADR links; no screenshot-only completion claims.

See docs/SCREEN_BUILDING_STANDARD.md and templates/SCREEN_SPEC.md.
