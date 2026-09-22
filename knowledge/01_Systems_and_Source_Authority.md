# Systems and Source Authority

**Suggested QueryBridge category:** business_rule

## Established rule

Source authority is **question-specific**. A single source should not automatically be treated as authoritative for every field in a business object.

## Practical source-routing rules

### SAP S/4HANA

Use SAP as the primary authority for:

- current PO number
- PO line / item structure
- current PO status
- posted goods receipts
- accounting / posted actuals
- committed purchasing values, subject to the required reporting definition

### Project Procure

Use Project Procure as the primary working source for:

- procurement planning / execution workflow
- RFQ / RFRFQ / PREQ working structures
- procurement item status
- procurement-specific working dates and responsibilities
- package-level working context
- user-entered procurement health / commentary where present

### Primavera P6

Use P6 as the primary authority for:

- project schedule structure
- activity dates
- schedule logic / dependencies
- baseline / planned schedule values
- float / criticality where available

### Supplier acknowledgement / OA

Use supplier confirmation / order acknowledgement for:

- supplier-committed delivery dates
- latest confirmed supplier commitments

Do not automatically overwrite planned or forecast dates with committed dates. They are different observations.

### VIM

Use VIM for:

- invoice workflow status
- invoice-processing state
- workflow / approval state
- invoice document identifiers and extracted invoice attributes

### DPPP

DPPP should be treated as a governed planning / working layer that reuses source values and adds user-facing projections or context. It should not silently become the system of record for values already governed in SAP, P6, VIM or another authoritative source.

### TSP / Power BI

TSP / Power BI is downstream reporting / extraction in the discussed environment. Do not use TSP as evidence that Project Procure source data is correct.

## Important semantic distinctions

The following should remain separate concepts even if a UI shows them together:

- planned date
- required date
- forecast date
- committed / confirmed date
- actual date

Also distinguish:

- PO value
- outstanding PO value
- invoice value
- document currency
- local/reporting currency
- original value
- converted value
- exchange rate
- exchange-rate date

## Conflict handling

When sources disagree:

1. retain both observations where they represent different business meanings
2. retain source and timestamp
3. apply a question-specific authority rule
4. expose the contradiction where required
5. do not let an AI agent silently choose a value without an explicit rule

## Working design / validate

A canonical source-routing table would be useful, with fields such as:

- business concept
- source system
- source object / table
- source field
- authority level
- refresh latency
- owner
- override rule
- conflict rule
- effective dates
