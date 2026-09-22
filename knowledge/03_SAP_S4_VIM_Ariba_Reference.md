# SAP S/4HANA, OpenText VIM and Ariba Reference

**Suggested QueryBridge category:** package

## SAP procurement context

The SCM environment uses SAP S/4HANA procurement together with SAP Ariba and OpenText VIM.

Relevant business objects include:

- project
- WBS
- purchase requisition
- purchase order
- PO item
- goods receipt
- service entry
- supplier
- invoice
- accounting document

## OpenText VIM tables previously referenced

The following VIM objects have been discussed:

- `/OPT/VIM_1HEAD` — invoice/header data
- `/OPT/VIM_1ITEM` — item data
- `/OPT/VIM_1LOG` — processing log
- `/OPT/VIM_1HIST` — history
- `/OPT/VIM_1HSTAT` — header status/history status
- `/OPT/VIM_1OBJ` — linked objects
- `/OPT/VIM_EXC_H`
- `/OPT/VIM_EXC_L`
- `/OPT/VIM_EXC_T` — exception-related objects
- `/OPT/VIM_APPROVALS` — approvals
- `/OPT/VIM_7HEAD`
- `/OPT/VIM_7ITEM`
- `/OPT/VIM_7LOG` — document-processing related objects
- `/OPT/VIM_IMG`
- `/OPT/VIM_DOCREL` — image/document relationships

Exact availability and structure must be validated against the installed VIM release.

## /OPT/VIM_1HEAD fields previously discussed

Fields referenced in prior work include:

- `DOCID`
- `DOCTYPE`
- `STATUS`
- `CURR_ROLE`
- `CURR_PROC_TYPE`
- `BUKRS`
- `BELNR`
- `GJAHR`
- `BLART`
- `BLDAT`
- `BUDAT`
- `XBLNR`
- `LIFNR`
- `EBELN`
- `WERKS`
- `RMWWR`
- `WAERS`
- `SUPPLY_DATE`
- `PYMNT_TERMS`
- `CM_REF_NO`
- `CHANNEL_ID`
- `PAYMENT_METHOD`
- `INV_CAT`

There are also amount/tax, duplicate-check, extraction, validation and retry-related fields depending on release/customisation.

**Validation rule:** use SAP DDIC / SE11 or equivalent authoritative metadata for the actual environment before relying on an internet/reference field list.

## Relationship hints

Common conceptual relationships worth checking in the captured schema:

- VIM invoice → SAP company code via `BUKRS`
- VIM invoice → SAP accounting document via `BELNR` + `GJAHR` + company code
- VIM invoice → supplier via `LIFNR`
- VIM invoice → PO via `EBELN`
- VIM invoice → plant via `WERKS`

These are plausible joining concepts, but the correct key combination and field semantics should be validated against the live system.

## Invoice analytics concepts

Useful measures / states previously discussed include:

- blocked invoice
- missing GR
- invoice approval state
- workflow status
- invoice date
- due date
- touchless processing
- rework
- exception count
- approval delay

Do not confuse invoice document date with payment due date.
