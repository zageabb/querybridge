# Procurement Lifecycle and Entity Model

**Suggested QueryBridge category:** relationship

## Established structures

### Project Procure structure

```text
Project
  ↓
RFRFQ
  ↓
RFQ
  ↓
PREQ
```

### SAP structure

```text
Project
  ↓
PR
  ↓
PO
```

A recurring integration requirement is to bridge the two structures, particularly around:

```text
PREQ ↔ PR ↔ PO
```

The exact relationship and grain must be validated in live data.

## Procurement lifecycle

A recurring end-to-end lifecycle is:

```text
Project / requirement
    ↓
RFQ / sourcing
    ↓
PREQ / PR
    ↓
PO
    ↓
Order acknowledgement / supplier commitment
    ↓
Delivery / service execution
    ↓
GR / Service Entry
    ↓
Invoice
    ↓
VIM workflow / payment processing
    ↓
Project / procurement reporting
```

## Object-centric relationship rule

Do not assume one procurement object maps one-to-one to the next.

Examples:

- one PR may create several POs
- one PO may contain multiple PO items
- one PO item may have multiple deliveries
- one PO item may have multiple GR postings
- one PO may be matched by multiple invoices
- one procurement requirement may be split across suppliers or orders

For query design, the **grain** must therefore be explicit.

## Recommended grain awareness

Common grains include:

- Project
- procurement item / package
- RFRFQ
- RFQ
- quotation
- PREQ
- PR
- PO header
- PO item
- delivery / schedule line
- GR posting
- service entry
- invoice header
- invoice item

A query that joins objects at different grains can multiply rows and overstate values.

## Procurement quality rules

PO creation and reporting should preserve correct:

- project
- WBS
- material / scope
- plant
- quantity
- UoM
- price
- currency
- tax handling
- delivery date
- supplier
- reference back to sourcing / procurement context

Poor quality in these fields can cause:

- incorrect project commitment reporting
- invoice mismatches
- blocked invoices
- unreliable delivery forecasts
- duplicate reconciliation work
- manual Excel corrections

## Working design / validate

A canonical analytical model previously proposed contains dimensions such as:

- `dim_project`
- `dim_supplier`
- `dim_material`
- `dim_currency`
- `dim_date`

and facts such as:

- `fact_purchase_order`
- `fact_grn`
- `fact_invoice`
- `fact_project_milestone`
- `fact_supplier_performance`
- `fact_forecast`

This is a modelling proposal, not confirmed physical table naming.
