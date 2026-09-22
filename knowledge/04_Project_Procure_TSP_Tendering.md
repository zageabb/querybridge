# Project Procure, TSP, Tendering and Reporting

**Suggested QueryBridge category:** package

## Established context

Project Procure is a key procurement working application in the SCM landscape.

TSP is a downstream extract/reporting consumer of Project Procure data in the discussed environment.

**Important rule:** poor Project Procure data will flow into TSP and TAIJU. TSP should not be used as independent proof that Project Procure is accurate.

## Project Procure entities

Previously discussed structures and concepts include:

- Project
- RFRFQ
- RFQ
- PREQ
- Supplier
- Quotation
- Scope Order Lines
- procurement item / package

## Required / useful Project Procure fields

A data-quality and integration assessment should attempt to capture:

- project number
- WBS
- procurement item ID
- item description
- item category
- stage
- status
- health / RAG
- critical flag
- responsible role
- supplier ID
- supplier name
- RFQ number
- PREQ number
- PR number
- PO number
- PREQ / PR / PO statuses
- required date
- planned date
- forecast date
- actual date
- original value
- converted value
- currency
- exchange rate
- exchange-rate date
- created date
- last-modified date
- comments
- risk reason
- delay reason
- overrides / exceptions

## Power BI / MSOLAP model previously seen

A procurement semantic model exposed objects named:

- `Fct Procure`
- `Dim Project`
- `Dim RFRFQ`
- `Dim RFQ`
- `Dim Supplier`
- `Dim PREQ`
- `Dim Quotation`
- `Dim Scope Order Lines`
- `Dim MDF`

Fields previously observed included:

- Project Number
- RFRFQ
- RFQ
- PREQ Number
- PREQ Status
- PO Number
- PO Sent To Supplier By
- supplier fields
- quotation fields
- delivery / due dates
- currency / exchange-rate fields
- quantities / prices
- procurement measures

**Caution:** earlier work assumed `Fct Procure` was the central fact table. That assumption must be validated in the model; semantic-model exposure is not authoritative source lineage.

## Tendering / PreCalc integration

Prior work included a UK pilot connecting:

```text
Project Procure
    ↔
Tendering PreCalc
```

using Supplier Online Quotations / quotation-transfer concepts.

This is relevant when looking for:

- tender-to-project continuity
- supplier quotation identifiers
- transferred scope items
- quotation revisions
- currency / pricing continuity
- procurement requirements created from tender assumptions

## TSP role

TSP has been used for reporting / insight access, including Power BI and Excel-based live extracts.

For schema reasoning:

- treat TSP as a reporting projection
- prefer Project Procure for source-process semantics
- use TSP/Power BI to discover useful business dimensions and measures
- do not infer physical source relationships purely from semantic model names
