"""
The status report: the three tabs of a status in one Excel workbook.

    Crown Land Status         the status summary                    (Tab 1)
    Status of Conflict        inactive Crown land tenures           (Tab 2)
    Conflicts & Constraints   what the AOI overlaps, by category    (Tab 3)
    Data Sources              where each dataset was read from

This is the workbook the ArcGIS Pro Automated Status Tool hands over, with its
sheets in the same order. Each sheet has its own writer (crown_land_status.py,
conflicts_report.py); this module only puts them together.
"""

from pathlib import Path
from typing import Iterable, Optional, Sequence

import openpyxl

from ast_engine.core.data_adapters.oracle.tantalis_status import InactiveTenure

from .conflicts_report import DatasetReport, ReportHeader, add_conflicts_sheets
from .crown_land_status import (
    CROWN_LAND_STATUS_SHEET_NAME,
    CrownLandStatus,
    add_crown_land_status_sheet,
    add_status_of_conflict_sheet,
)


def write_status_report(
    path: str | Path,
    *,
    header: ReportHeader,
    datasets: Iterable[DatasetReport],
    crown_land_status: CrownLandStatus,
    inactive_tenures: Optional[Sequence[InactiveTenure]],
) -> Path:
    """Write the status report workbook and return its path.

    inactive_tenures  the inactive Crown land tenures on the AOI; an empty list
                      when it has none, and None when they could not be read -
                      the Status of Conflict tab then says it was not evaluated.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    book = openpyxl.Workbook()
    # A new workbook comes with one empty sheet; the report's own sheets replace it.
    book.remove(book.active)

    geomark_cell = add_crown_land_status_sheet(book, crown_land_status)
    add_status_of_conflict_sheet(book, crown_land_status.crown_file_number, inactive_tenures)
    add_conflicts_sheets(
        book,
        header,
        datasets,
        # The Conflicts & Constraints header repeats the Geomark typed into the
        # Crown Land Status tab.
        geomark_reference=f"'{CROWN_LAND_STATUS_SHEET_NAME}'!{geomark_cell}",
    )

    book.save(path)
    return path
