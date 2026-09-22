# TAIJU / SCM Cockpit — Core Context

**Suggested QueryBridge category:** package

## Established context

- **TAIJU** is the current internal name for the platform previously referred to as **SCM Cockpit**.
- TAIJU is intended as a cross-functional Supply Chain Management intelligence and decision-support layer rather than a replacement for source systems.
- The environment spans procurement, project delivery, suppliers, finance, scheduling, invoice processing, reporting and AI-assisted workflows.
- Systems repeatedly discussed as part of the TAIJU landscape include:
  - SAP S/4HANA
  - SAP Ariba
  - OpenText VIM
  - Project Procure
  - Primavera P6
  - DPPP
  - Power BI / semantic models
  - supplier / market sources
  - documents and file-based sources
- The operating principle is **capture once, reuse many times**, reducing duplicate data entry while retaining source lineage.
- Human accountability remains important. Commercial, contractual and externally visible actions should not be silently automated without appropriate approval.

## DPPP

**DPPP** has been discussed as a Digital / Dynamic PPP.

Core intent:

- preserve a common standard and required information
- let users arrange fields and views to suit their work
- avoid forcing duplicate entry where authoritative data already exists elsewhere
- reuse SAP, Procure, P6 and other authoritative sources where possible
- expose gaps instead of hiding them
- retain lineage and ownership for every reused or derived value

The standard should define:

- required concepts and fields
- lifecycle stages
- relationships
- ownership
- controls
- minimum data requirements

It should not require every user to follow one rigid screen order.

## TAIJU design intent

A recurring target architecture is:

```text
Source systems / documents
        ↓
Governed SCM data products / canonical model
        ↓
Shared intelligence / rules / ontology
        ↓
TAIJU application + specialist AI agents
        ↓
Users / approvals / business decisions
        ↓
Approved actions back to source systems
```

Potential data products previously discussed include:

- Supplier 360
- Project Procurement Status
- RFQ / Offer
- Purchase Commitment / Delivery
- Supplier Risk
- Cost / Savings
- Contract / Obligation
- Engineering Requirement
- Actions / Decisions

## Reasoning philosophy

The strongest recurring approach has been:

1. understand the project schedule and required dates
2. understand procurement dependencies
3. identify delivery, supplier and invoice risks
4. quantify financial or project impact
5. provide evidence and source lineage
6. support a human decision or approved action

This is often described as **schedule-first reasoning**.

## Terminology

Use these terms carefully:

- **TAIJU** — current application / platform name.
- **SCM Cockpit** — historical name.
- **Orchestrator** — working term for coordination across specialist agents.
- **Akira** — only use as an underlying AI/framework name where that is confirmed in the implementation.
