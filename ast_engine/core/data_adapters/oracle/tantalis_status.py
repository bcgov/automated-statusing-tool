"""Tantalis lookups for the status report's first two tabs.

The Crown Land Status tab and the Status of Conflict tab report facts about a
Crown land file that are not spatial overlays: who applied, when the
application was received, what the tenure is, and which inactive tenures sit
on the same ground. They are read here, straight from the TANTALIS tables in
BCGW. The queries are the ones the ArcGIS Pro Automated Status Tool runs
(its one_status_tabs_one_and_two.py and tantalis_bigQuery.py), carried over.

Like the other Oracle readers, these functions take an open connection's cursor
from the caller and never open one themselves.

The Tantalis identifiers are passed to Oracle as bind variables. The one value
that is written into SQL text is the list of parcel ids in the inactive-tenure
query, which Oracle cannot take as a single bind variable; every id is turned
into an integer first, so only digits are ever written.
"""

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import geopandas as gpd
import oracledb

from ..base import ReadOptions, SpatialFilter
from ..exceptions import DataReadError
from .adapter import OracleAdapter
from .tantalis import TANTALIS_TABLE

logger = logging.getLogger(__name__)

# The tenure's own attributes, read from the same view the AOI shape comes from.
TENURE_FIELDS = (
    "TENURE_AREA_IN_HECTARES",
    "TENURE_TYPE",
    "INTRID_SID",
    "TENURE_SUBTYPE",
    "TENURE_PURPOSE",
    "TENURE_SUBPURPOSE",
    "TENURE_LOCATION",
    "TENURE_LEGAL_DESCRIPTION",
)

TENURE_DETAILS_SQL = f"""
    SELECT {", ".join(TENURE_FIELDS)}
    FROM {TANTALIS_TABLE} a
    WHERE a.CROWN_LANDS_FILE = :file_nbr
      AND a.DISPOSITION_TRANSACTION_SID = :disp_id
      AND a.INTRID_SID = :parcel_id
"""

APPLICANT_SQL = """
    SELECT ORGANIZATIONS_LEGAL_NAME, INDIVIDUALS_FIRST_NAME, INDIVIDUALS_LAST_NAME
    FROM WHSE_TANTALIS.TA_INTEREST_HOLDER_VW
    WHERE DISPOSITION_TRANSACTION_SID = :disp_id
"""

RECEIVED_DATE_SQL = """
    SELECT RECEIVED_DAT
    FROM WHSE_TANTALIS.TA_DISPOSITION_TRANSACTIONS
    WHERE DISPOSITION_TRANSACTION_SID = :disp_id
"""

# The interest parcels are found by their shape; the inactive tenures on them
# are then read by parcel id.
INTEREST_PARCELS_TABLE = "WHSE_TANTALIS.TA_INTEREST_PARCEL_SHAPES"
INTEREST_PARCEL_ID_FIELD = "INTRID_SID"

# Oracle takes at most 1000 values in one IN list.
MAX_IN_LIST = 1000

# Inactive Crown land tenures on a set of interest parcels: tenures whose
# current status is inactive, at the tenure stage, on a file that has no
# tenure in good standing or on offer. {parcels} is the parcel id condition.
INACTIVE_LANDS_SQL = """
    SELECT
          CAST(IP.INTRID_SID AS NUMBER) INTRID_SID,
          CAST(DT.DISPOSITION_TRANSACTION_SID AS NUMBER) DISPOSITION_TRANSACTION_SID,
          DS.FILE_CHR,
          SG.STAGE_NME,
          TT.ACTIVATION_CDE AS DTS_ACTIVATION_CDE,
          TT.STATUS_NME,
          TS.EFFECTIVE_DAT,
          PU.PURPOSE_NME,
          SP.SUBPURPOSE_NME,
          TY.TYPE_NME,
          ST.SUBTYPE_NME,
          DT.LOCATION_DSC,
          PR.LEGAL_NAME AS HOLDER_ORGANNSATION_NAME,
          PR.FIRST_NAME || ' ' || PR.LAST_NAME AS HOLDER_INDIVIDUAL_NAME
    FROM WHSE_TANTALIS.TA_DISPOSITION_TRANSACTIONS DT
      JOIN WHSE_TANTALIS.TA_INTEREST_PARCELS IP
        ON DT.DISPOSITION_TRANSACTION_SID = IP.DISPOSITION_TRANSACTION_SID
          AND IP.EXPIRY_DAT IS NULL
      JOIN WHSE_TANTALIS.TA_DISP_TRANS_STATUSES TS
        ON DT.DISPOSITION_TRANSACTION_SID = TS.DISPOSITION_TRANSACTION_SID
          AND TS.EXPIRY_DAT IS NULL
      JOIN WHSE_TANTALIS.TA_DISPOSITIONS DS
        ON DS.DISPOSITION_SID = DT.DISPOSITION_SID
      JOIN WHSE_TANTALIS.TA_STAGES SG
        ON SG.CODE_CHR = TS.CODE_CHR_STAGE
      JOIN WHSE_TANTALIS.TA_STATUS TT
        ON TT.CODE_CHR = TS.CODE_CHR_STATUS
      JOIN WHSE_TANTALIS.TA_AVAILABLE_TYPES TY
        ON TY.TYPE_SID = DT.TYPE_SID
      JOIN WHSE_TANTALIS.TA_AVAILABLE_SUBTYPES ST
        ON ST.SUBTYPE_SID = DT.SUBTYPE_SID
          AND ST.TYPE_SID = DT.TYPE_SID
      JOIN WHSE_TANTALIS.TA_AVAILABLE_PURPOSES PU
        ON PU.PURPOSE_SID = DT.PURPOSE_SID
      JOIN WHSE_TANTALIS.TA_AVAILABLE_SUBPURPOSES SP
        ON SP.SUBPURPOSE_SID = DT.SUBPURPOSE_SID
          AND SP.PURPOSE_SID = DT.PURPOSE_SID
      JOIN WHSE_TANTALIS.TA_ORGANIZATION_UNITS OU
        ON OU.ORG_UNIT_SID = DT.ORG_UNIT_SID
      JOIN WHSE_TANTALIS.TA_TENANTS TE
        ON TE.DISPOSITION_TRANSACTION_SID = DT.DISPOSITION_TRANSACTION_SID
          AND TE.SEPARATION_DAT IS NULL
      JOIN WHSE_TANTALIS.TA_INTERESTED_PARTIES PR
        ON PR.INTERESTED_PARTY_SID = TE.INTERESTED_PARTY_SID
    WHERE
          TT.ACTIVATION_CDE = 'INACT' AND
          SG.STAGE_NME = 'TENURE' AND
          {parcels} AND
          DS.FILE_CHR NOT IN (SELECT TEN.CROWN_LANDS_FILE
                               FROM WHSE_TANTALIS.TA_CROWN_TENURES_VW TEN
                               WHERE TEN.TENURE_STATUS IN ('DISPOSITION IN GOOD STANDING', 'OFFERED', 'OFFER ACCEPTED'))
    ORDER BY TS.EFFECTIVE_DAT DESC
"""


@dataclass(frozen=True)
class InactiveTenure:
    """One inactive Crown land tenure on the AOI, as the Status of Conflict tab lists it.

    disposition_id  the tenure's disposition transaction id.
    file_number     its Crown land file.
    interest_type   its purpose and type, e.g. "QUARRYING LICENCE".
    holders         who held it; several holders are joined with " / ".
    """

    disposition_id: int
    file_number: str
    interest_type: str
    holders: str


def fetch_tenure_details(
    cursor: Any,
    file_number: str,
    disposition_id: int | str,
    parcel_id: int | str,
) -> dict[str, list[str]]:
    """Return the tenure's attributes: for each of TENURE_FIELDS, its values.

    A value list has one entry per different value, sorted, as text. It is
    empty when the tenure has nothing in that field, or when no parcel matches
    the three identifiers.
    """
    rows = _query(
        cursor,
        TENURE_DETAILS_SQL,
        {"file_nbr": file_number, "disp_id": disposition_id, "parcel_id": parcel_id},
        "Tantalis tenure lookup",
    )
    return {
        field: sorted({_text(row[index]) for row in rows if row[index] is not None})
        for index, field in enumerate(TENURE_FIELDS)
    }


def fetch_applicant_name(cursor: Any, disposition_id: int | str) -> str:
    """Return the name of whoever holds the interest on a disposition.

    An organization's legal name, or a person's first and last name. When the
    disposition has several holders their names are joined with "; ". Empty
    when it has none.

    The result is personal information. It belongs in the status report and
    nowhere else - it must not be logged.
    """
    rows = _query(cursor, APPLICANT_SQL, {"disp_id": disposition_id}, "Tantalis applicant lookup")
    names = []
    for organization, first_name, last_name in rows:
        name = " ".join(str(part).strip() for part in (organization, first_name, last_name) if part)
        if name and name not in names:
            names.append(name)
    return "; ".join(names)


def fetch_received_dates(cursor: Any, disposition_id: int | str) -> list[str]:
    """Return the date(s) a disposition's application was received, as text."""
    rows = _query(cursor, RECEIVED_DATE_SQL, {"disp_id": disposition_id}, "Tantalis received date lookup")
    return sorted({_text(row[0]) for row in rows if row[0] is not None})


def fetch_inactive_tenures(connection: Any, cursor: Any, aoi: gpd.GeoDataFrame) -> list[InactiveTenure]:
    """Return the inactive Crown land tenures on the interest parcels the AOI touches.

    Two steps, as in the ArcGIS Pro tool: find the interest parcels whose shape
    meets the AOI, then read the inactive tenures recorded against those
    parcels. A tenure with several holders comes back once, its holders joined.
    The most recently changed tenure is first.

    Returns an empty list when the AOI touches no interest parcel, or none of
    them carries an inactive tenure.
    """
    parcels = OracleAdapter(connection, cursor).read(
        read_options=ReadOptions(
            spatial_filter=SpatialFilter(aoi=aoi, predicate="intersects"),
            keep_columns=[INTEREST_PARCEL_ID_FIELD],
        ),
        table=INTEREST_PARCELS_TABLE,
    )
    parcel_ids = sorted({int(value) for value in parcels[INTEREST_PARCEL_ID_FIELD].dropna()}) if not parcels.empty else []
    if not parcel_ids:
        logger.info("No interest parcels meet the AOI; no inactive tenures to report")
        return []

    sql = INACTIVE_LANDS_SQL.format(parcels=_parcel_condition(parcel_ids))
    rows = _query(cursor, sql, {}, "Tantalis inactive tenure lookup")
    return _inactive_tenures(rows)


def _parcel_condition(parcel_ids: Iterable[int]) -> str:
    """Build the SQL condition selecting a list of interest parcels.

    Oracle takes at most 1000 values in one IN list, so a longer list is
    written as several IN lists joined with OR. Each id is written through
    int(), so the text can only ever hold digits.
    """
    ids = [int(parcel_id) for parcel_id in parcel_ids]
    chunks = [ids[start:start + MAX_IN_LIST] for start in range(0, len(ids), MAX_IN_LIST)]
    conditions = [
        "IP.INTRID_SID IN (" + ",".join(str(parcel_id) for parcel_id in chunk) + ")"
        for chunk in chunks
    ]
    return "(" + " OR ".join(conditions) + ")"


def _inactive_tenures(rows: list[tuple]) -> list[InactiveTenure]:
    """Turn the inactive-tenure query's rows into one record per tenure.

    The query returns a row for every holder of every parcel of a tenure. A
    tenure is listed once, in the order it first appears, with each different
    holder named once.
    """
    tenures: dict[int, dict[str, Any]] = {}
    for row in rows:
        (_, disposition_id, file_number, _, _, _, _, purpose, _, tenure_type, _, _, organization, individual) = row
        # An organization has a legal name; a person has a first and last name.
        holder = (str(organization or "").strip() + str(individual or "").strip()).strip()
        tenure = tenures.setdefault(
            int(disposition_id),
            {
                "file_number": str(file_number),
                "interest_type": f"{purpose} {tenure_type}",
                "holders": [],
            },
        )
        if holder and holder not in tenure["holders"]:
            tenure["holders"].append(holder)

    return [
        InactiveTenure(
            disposition_id=disposition_id,
            file_number=tenure["file_number"],
            interest_type=tenure["interest_type"],
            holders=" / ".join(tenure["holders"]),
        )
        for disposition_id, tenure in tenures.items()
    ]


def _query(cursor: Any, sql: str, bind_vars: dict[str, Any], what: str) -> list[tuple]:
    """Run a query and return its rows; a database error becomes a DataReadError."""
    try:
        cursor.execute(sql, bind_vars)
        return cursor.fetchall()
    except oracledb.DatabaseError as exc:
        raise DataReadError(f"{what} failed: {exc}") from exc


def _text(value: Any) -> str:
    """A database value as the report shows it: text, whole numbers without ".0"."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
