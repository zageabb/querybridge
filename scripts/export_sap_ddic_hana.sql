-- SAP S/4HANA on-premise/private-cloud ABAP Dictionary metadata export
-- Run READ-ONLY in an authorised HANA SQL console with access to the SAP ABAP schema.
-- Replace SAPABAP1 with your *actual* ABAP database schema. Do not assume it.
-- Export the result to a UTF-8 CSV with header row, sorted by TABLE_NAME, POSITION.
-- If your SAP environment does not permit direct HANA SQL, ask ABAP/Basis to
-- export equivalent DD02L/DD02T/DD03L/DD03T/DD04T records in this column layout.
--
-- This export lists activated transparent DDIC tables and their declared fields.
-- This is NOT a source of complete join conditions; DD08L/DD05S plus functional
-- review are needed for SAP relationships and client/language conditions.
--
-- Uses active, current DDIC versions (AS4LOCAL=A, AS4VERS=0000 where present).
-- Filtered to transparent tables; for a broader inventory, review TABCLASS
-- and CDS data-definition sources separately. Excludes names starting Z/Y as
-- a basic custom filter only; partner namespaces/packages may still be included.
SELECT
    hdr."TABNAME" AS TABLE_NAME,
    COALESCE(NULLIF(TRIM(tt."DDTEXT"), ''), '') AS TABLE_DESCRIPTION,
    fld."FIELDNAME" AS FIELD_NAME,
    COALESCE(
      NULLIF(TRIM(et."DDTEXT"), ''),
      NULLIF(TRIM(ft."DDTEXT"), ''),
      ''
    ) AS FIELD_DESCRIPTION,
    fld."DATATYPE" AS DATA_TYPE,
    fld."POSITION" AS POSITION,
    fld."LENG" AS LENGTH,
    fld."DECIMALS" AS DECIMALS,
    fld."KEYFLAG" AS KEY_FLAG,
    fld."ROLLNAME" AS DATA_ELEMENT,
    hdr."TABCLASS" AS TABLE_CLASS
FROM "SAPABAP1"."DD02L" AS hdr
INNER JOIN "SAPABAP1"."DD03L" AS fld
    ON fld."TABNAME" = hdr."TABNAME"
   AND fld."AS4LOCAL" = 'A'
   AND fld."AS4VERS" = '0000'
LEFT JOIN "SAPABAP1"."DD02T" AS tt
    ON tt."TABNAME" = hdr."TABNAME"
   AND tt."AS4LOCAL" = 'A'
   AND tt."AS4VERS" = '0000'
   AND tt."DDLANGUAGE" = 'E'
LEFT JOIN "SAPABAP1"."DD04T" AS et
    ON et."ROLLNAME" = fld."ROLLNAME"
   AND et."AS4LOCAL" = 'A'
   AND et."AS4VERS" = '0000'
   AND et."DDLANGUAGE" = 'E'
LEFT JOIN "SAPABAP1"."DD03T" AS ft
    ON ft."TABNAME" = fld."TABNAME"
   AND ft."FIELDNAME" = fld."FIELDNAME"
   AND ft."AS4LOCAL" = 'A'
   AND ft."DDLANGUAGE" = 'E'
WHERE hdr."AS4LOCAL" = 'A'
  AND hdr."AS4VERS" = '0000'
  AND hdr."TABCLASS" = 'TRANSP'
  AND hdr."TABNAME" NOT LIKE 'Z%'
  AND hdr."TABNAME" NOT LIKE 'Y%'
  AND fld."FIELDNAME" NOT LIKE '.%'
ORDER BY hdr."TABNAME", fld."POSITION", fld."FIELDNAME";
