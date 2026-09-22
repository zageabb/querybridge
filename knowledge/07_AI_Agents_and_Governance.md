# AI Agents, Orchestration and Governance

**Suggested QueryBridge category:** general

## Established direction

TAIJU has been discussed as a platform that can use specialist AI agents across procurement, invoices, milestones, project health, suppliers and reporting.

The AI layer should be evidence-based and grounded in governed source data.

## Agent responsibilities

Potential specialist areas include:

- invoice / VIM status
- PO / commitment analysis
- GR / missing receipt analysis
- procurement health
- supplier performance
- project milestones
- schedule risk
- project health
- forecasting
- sourcing / offer evaluation

## Routing principle

Questions should be routed to the authoritative source for the concept.

Examples:

- “What is the current PO status?” → SAP
- “Why is the invoice blocked?” → VIM + relevant SAP matching information
- “What is the latest P6 milestone?” → P6
- “What is the procurement working status?” → Project Procure / governed DPPP view
- “What is the project health summary?” → governed TAIJU / DPPP calculation using source evidence

## Agent register fields previously recommended

A governed agent catalogue can include:

- owner
- purpose
- allowed sources
- allowed actions
- read-only vs transactional
- human approval requirements
- confidence / thresholds
- evaluations
- logs
- version
- prompt / policy version

## Human approval

Human approval should remain explicit for:

- commercial commitments
- contractual decisions
- supplier-facing actions
- external communications
- irreversible source-system changes
- actions with significant financial impact

## Trust rules

AI answers should ideally state or retain:

- source
- timestamp / freshness
- evidence used
- uncertainty
- contradictions
- missing information
- whether the conclusion is observed, derived or predicted

## Knowledge architecture

Prior review of TAIJU knowledge material found that generic boilerplate reduces usefulness.

The strongest separation is:

- **North Star** — purpose and principles
- **Knowledge context** — reusable business/system facts
- **Ontology** — entities, relationships and synonyms
- **Processes** — stages, inputs, outputs and controls
- **Agents** — capabilities, boundaries, inputs and outputs
- **Routing** — source / tool selection rules
- **Prompts** — version-controlled behavioural instructions

For QueryBridge, knowledge should therefore favour concrete facts and rules over repeated general descriptions.
