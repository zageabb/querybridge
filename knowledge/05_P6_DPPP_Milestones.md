# Primavera P6, DPPP and Milestone Relationships

**Suggested QueryBridge category:** relationship

## Established context

TAIJU is intended to integrate procurement milestones with Primavera P6 while keeping P6 as the schedule / dependency authority.

External milestone information may come from:

- Project Procure
- SAP
- TSS / tender assumptions
- engineering
- suppliers
- manual / governed entries

TAIJU should link these to P6 rather than copy the entire scheduling model into another uncontrolled source.

## Working design / validate — central milestone model

A proposed central milestone service/model contains entities such as:

- `project_milestone`
- `milestone_relationship`
- `milestone_definition`
- `dppp_milestone_mapping`

This is a proposed canonical design rather than confirmed physical implementation.

## Suggested milestone attributes

Useful fields include:

- source system
- source object type
- source object ID
- source URL
- external ID
- project ID
- WBS ID / code / name / path
- P6 ObjectId
- P6 GUID
- P6 Activity ID
- activity name
- activity type
- activity status
- percent complete
- baseline date
- planned date
- required date
- forecast date
- committed date
- actual date
- early date
- late date
- total float
- variance
- critical flag
- constraint
- data date
- created / updated timestamps

## Relationship types

Potential milestone-link types previously discussed include:

Schedule logic:

- FINISH_START
- START_START
- FINISH_FINISH
- START_FINISH

Cross-system business relationships:

- REQUIRED_BEFORE
- REQUIRED_AFTER
- EQUIVALENT_TO
- DRIVES
- INFORMS
- RELATED_TO

## Linking approach

The preferred approach is low-effort and evidence-based.

Try matching in this order:

1. explicit external IDs
2. project + WBS
3. activity code
4. procurement / package identifier
5. semantic similarity of names
6. date proximity
7. learned / confirmed mapping rules

Where confidence is insufficient:

- show the suggested match
- allow one-click confirmation
- let the user select one anchor P6 activity
- expand neighbouring schedule logic from that anchor
- use manual WBS selection only as fallback

Every confirmed mapping should retain:

- source
- target
- confidence
- mapping method
- confirmation status
- timestamps / lineage

## DPPP milestone view

A DPPP milestone area should be able to show distinct observations such as:

- baseline
- required
- planned
- forecast
- committed
- actual

along with:

- source
- float
- status
- lineage

Do not collapse these dates into one generic “delivery date”.
