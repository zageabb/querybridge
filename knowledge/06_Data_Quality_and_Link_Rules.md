# Data Quality, Reconciliation and Join Rules

**Suggested QueryBridge category:** business_rule

## General principle

TAIJU and QueryBridge should not infer certainty from missing or poor source data. AI cannot reliably reconstruct business events that were never captured.

## Data-quality dimensions

Useful checks include:

- completeness
- validity
- consistency
- uniqueness
- timeliness / staleness
- referential integrity
- source coverage
- reconciliation

## Known issue patterns

Prior work identified recurring risks such as:

- missing PO references
- missing dates
- stale updates
- differing values
- differing currencies
- WBS hierarchy differences
- one-to-many PO grain
- missing lifecycle transitions
- unclear source ownership
- missing lineage
- unlinked procurement items

## Evidence sample — QAS / supplied sample only

The following are sample observations and **must not be treated as production totals**:

- PREQ → PO references matched **17 / 17** where a PO reference was populated.
- Only **17 / 131** Project Procure records in that supplied sample had a PO number populated.
- SAP `OUR_REFERENCE` was blank across **977 supplied rows** in the reviewed sample.
- WBS candidates matched **5 / 6** tested values for project-level discovery.

Interpretation:

- linkage logic can work where the source actually carries the reference
- coverage / completeness can be the limiting factor
- a WBS match can identify a project context but does not prove a PO belongs to a specific RFQ or procurement package
- `OUR_REFERENCE` should not be globally mandated purely because it is convenient for integration; at least one business unit uses the field for another valid purpose

## Join safety rules

Before accepting an inferred join, check:

1. Are both fields present?
2. Are the data types compatible?
3. Is the relationship one-to-one, one-to-many or many-to-many?
4. Is the field stable across time?
5. Is it unique at the relevant grain?
6. Does it mean the same thing in both systems?
7. Could leading zeros / formatting cause false mismatches?
8. Is the join valid for all business units?
9. Is the rule current or historical?
10. Is there a better explicit identifier?

## Grain rule

Never join only because two fields have the same name.

A strong QueryBridge relationship should ideally record:

- left table
- left field
- right table
- right field
- expected cardinality
- confidence
- source of the rule
- business explanation
- applicable business unit / scope
- known exceptions

## Currency rule

Keep original and converted values separate.

When comparing or aggregating monetary values, retain:

- original amount
- original currency
- converted amount
- reporting/local currency
- exchange rate
- exchange-rate date

Do not aggregate mixed currencies without an explicit conversion rule.

## Date rule

Keep these separate where possible:

- required
- planned
- baseline
- forecast
- committed / acknowledged
- actual

A change in one should not overwrite another without an explicit business rule.
