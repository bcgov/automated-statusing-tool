"""
Crown Land Status and Status of Conflict: the status report's first two tabs.

    Crown Land Status    the status summary: the file, the applicant, where the
                         land is and what administrative areas it falls in, and
                         the blank lines each business area fills in by hand
    Status of Conflict   the inactive Crown land tenures on the same ground

These are "Tab 1" and "Tab 2" of the ArcGIS Pro Automated Status Tool (the
sheets its one_status_tabs_one_and_two.py writes), carried over: the same
sections, in the same order, with the same line titles, fonts, alternating grey
bands and thick boxes. Many lines are written blank on purpose - they are the
form the people working the file complete.

The writers here only lay cells out. What goes in them is a CrownLandStatus,
built from a run by job_status.py.

What is different from the ArcGIS Pro tool's sheets:

  - a line whose dataset could not be read says "FAILED", and one whose dataset
    was not part of the run says "Not checked". The tool left both blank, which
    reads the same as "none found";
  - "Provincial Forest Exclusion" is followed by a "Provincial Forest
    Exclusion2" line, the way Addition and Deletion are. The tool listed the
    title twice, so the second value replaced the first and the exclusion's
    description was never shown;
  - "Status Run By" names the person who submitted the status, not the Windows
    account the tool ran under.

Text is always written as text, never as a formula (see excel.set_text).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Sequence, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from ast_engine.core.data_adapters.oracle.tantalis_status import InactiveTenure

from .excel import draw_box, set_text

CROWN_LAND_STATUS_SHEET_NAME = "Crown Land Status"
STATUS_OF_CONFLICT_SHEET_NAME = "Status of Conflict"

# Printed in red at the top of both sheets.
DISCLAIMER = "This product contains sensitive information.  INTERNAL GOVERNMENT USE ONLY"

# What a line says when its dataset could not be read, or was not run at all.
TEXT_FAILED = "FAILED"
TEXT_NOT_CHECKED = "Not checked"

TEAL = "31869B"
RED = "FF0000"
GREY_FILL = PatternFill("solid", fgColor="E6E6E6")
INACTIVE_FILL = PatternFill("solid", fgColor="FFFF00")

# A line's title, and its value.
TITLE_FONT = Font(size=11)
VALUE_FONT = Font(color=TEAL, size=9)
WRAP = Alignment(wrapText=True)

TITLE_COLUMN = 1
VALUE_COLUMN = 2

PURPOSE = (
    "Purpose: The purpose of this status summary is to present the "
    "information gathered by each person involved in the status phase to form the complete "
    "status package. The status summary sheet should be used in conjunction with the ILRR "
    "Custom Theme Report to provide a full status package. The information on the summary "
    "is meant to benefit the business leads, decision makers and others who are preparing "
    "the tenure documents and decision summary to streamline the process by avoiding "
    "duplicate parties researching information at multiple stages in the process."
)

SEE_TAB_3 = "SEE TAB 3  CONFLICTS & CONSTRAINTS FOR COMPLETE STATUS"

INACTIVE_ONLY_NOTICE = "'Status of Conflict' only evaluates against inactive crown land tenures."
NO_INACTIVE_NOTICE = INACTIVE_ONLY_NOTICE + " No inactive crown land tenures reported."
NOT_EVALUATED_NOTICE = (
    "ERROR: The AST was unable to evaluate the AOI against inactive crown land tenures. "
    "Please contact FCBCIntranet-SharePointSupport@gov.bc.ca for support"
)

# A line's value: one text, or several, each on its own row.
Value = Union[str, Sequence[str]]


@dataclass(frozen=True)
class CrownLandStatus:
    """Everything the Crown Land Status tab reports that is not typed in by hand.

    A field that holds several values (a tuple) is listed one value per row.
    Every field defaults to empty, which is what an uploaded AOI with no
    TANTALIS file has for the tenure's own facts.

    run_by / run_date       who submitted the status, and the day it ran.
    crown_file_number / disposition_number / region
                            what the status was asked for.
    applicant_name          the interest holder on the disposition.
    received_dates          when the disposition's application was received.
    tenure_*, parcel_numbers
                            the tenure's own attributes, from TANTALIS.
    the rest                what the AOI falls in, from the Tab 1 registry.
    """

    run_date: date
    run_by: str = ""
    crown_file_number: str = ""
    disposition_number: str = ""
    region: str = ""
    applicant_name: str = ""
    received_dates: Value = ()
    tenure_area_ha: Value = ()
    tenure_location: Value = ()
    tenure_legal_description: Value = ()
    tenure_type: Value = ()
    tenure_subtype: Value = ()
    tenure_purpose: Value = ()
    tenure_subpurpose: Value = ()
    parcel_numbers: Value = ()
    mapsheets: Value = ()
    pins: Value = ()
    pins_adjacent: Value = ()
    pins_right_of_way: Value = ()
    assessment_areas: Value = ()
    regional_districts: Value = ()
    municipalities: Value = ()
    electoral_districts: Value = ()
    provincial_forest: Value = ()
    provincial_forest_addition: Value = ()
    provincial_forest_addition2: Value = ()
    provincial_forest_deletion: Value = ()
    provincial_forest_deletion2: Value = ()
    provincial_forest_exclusion: Value = ()
    provincial_forest_exclusion2: Value = ()
    forest_districts: Value = ()
    land_title_offices: Value = ()
    in_alr: str = ""
    nearest_indian_reserve: str = ""
    nearest_arch_site: str = ""
    arch_potential: Value = ()


@dataclass
class _Sheet:
    """A sheet being written, and the last row written on it."""

    sheet: Worksheet
    row: int = 1
    geomark_cell: Optional[str] = field(default=None)


def add_crown_land_status_sheet(book: Workbook, status: CrownLandStatus, *, index: Optional[int] = None) -> str:
    """Add the Crown Land Status sheet to a workbook.

    index is where the sheet goes among the workbook's sheets; the end by default.

    Returns the cell holding the Geomark value (e.g. "B28"). The Conflicts &
    Constraints sheet shows that value in its header, with a formula, so it has
    to know where the line landed: the lines above it take more rows when a
    value has several entries.
    """
    page = _Sheet(_new_sheet(book, CROWN_LAND_STATUS_SHEET_NAME, {"A": 30, "B": 50, "C": 25}, index))
    sheet = page.sheet

    # Title
    page.row = 2
    sheet.merge_cells("A2:B2")
    title = sheet.cell(page.row, TITLE_COLUMN)
    set_text(title, "Status Summary")
    title.font = Font(color=TEAL, size=14, name="Arial")
    title.alignment = Alignment(horizontal="center")

    _write_files_section(page, status)
    _write_applicant_section(page, status)
    _write_section(page, "Lands note: this information may be applied to all agency application types", [
        ("File Number", status.crown_file_number),
        ("DID Number", status.disposition_number),
        ("DID Received Date", status.received_dates),
        ("IP Number", ""),
        ("Parcel Number", status.parcel_numbers),
        ("Region", status.region),
        ("Type", status.tenure_type),
        ("Sub Type", status.tenure_subtype),
        ("Purpose", status.tenure_purpose),
        ("Sub Purpose", status.tenure_subpurpose),
        ("Assessment Area", status.assessment_areas),
        ("Regional District", status.regional_districts),
        ("Municipality", status.municipalities),
        ("Electoral District", status.electoral_districts),
        ("Provincial Forest", status.provincial_forest),
        ("Provincial Forest Addition", status.provincial_forest_addition),
        ("Provincial Forest Addition2", status.provincial_forest_addition2),
        ("Provincial Forest Deletion", status.provincial_forest_deletion),
        ("Provincial Forest Deletion2", status.provincial_forest_deletion2),
        ("Provincial Forest Exclusion", status.provincial_forest_exclusion),
        ("Provincial Forest Exclusion2", status.provincial_forest_exclusion2),
        ("Forest District", status.forest_districts),
        ("Land Title Office", status.land_title_offices),
        ("In Agricultural Land Reserve", status.in_alr),
        ("Nearest Indian Res", status.nearest_indian_reserve),
    ])
    _write_section(page, "Lands Adjudication Information", [
        ("Upland Parcel Fronts Body of Water", ""),
        ("Is Upland Titled", ""),
        ("Foreshore Parcel Adjoins Upland", ""),
        ("Nearest Arch Site within 25km", status.nearest_arch_site),
        ("Overview Assessment Potential", status.arch_potential),
    ])
    _write_section(page, "Mines  -  See status number at top of report", _blank_lines(
        "Mine Number", "Permit Number", "Mine Type", "Mine Name", "Mine Manager",
        "Inspector", "New Permit", "Crown", "Private", "License Number",
    ))
    _write_section(page, "Forests", _blank_lines(
        "License Number", "License Type", "Area", "Cubic Metres", "Client Number", "Forest Professional",
    ))
    _write_section(page, "Water", _blank_lines(
        "File Number", "Stream Name", "Purpose", "Authorization Type", "e-Licensing Report Attached",
    ))
    _write_comments_section(page)
    if status.region.strip().lower() == "omineca":
        _write_section(page, "Omineca Manual Entries  -  yes / no / unk / exist / prop / adj", _blank_lines(
            "Stream Crossings", "Within 30m of Waterbody", "New Access",
            "Bulk Sample (Mines)", "Underground Works (Mines)", "Waste Discharge",
        ))

    return page.geomark_cell


def add_status_of_conflict_sheet(
    book: Workbook,
    crown_file_number: str,
    tenures: Optional[Sequence[InactiveTenure]],
    *,
    index: Optional[int] = None,
) -> None:
    """Add the Status of Conflict sheet to a workbook.

    tenures  the inactive Crown land tenures on the AOI. An empty list means
             the AOI was checked and has none. None means it could not be
             checked - the sheet then says so, rather than looking clear.
    index    where the sheet goes among the workbook's sheets; the end by default.
    """
    sheet = _new_sheet(book, STATUS_OF_CONFLICT_SHEET_NAME, {"A": 20, "B": 60, "C": 10}, index)

    row = 3
    _write_line(sheet, row, "File:", crown_file_number)
    row += 2

    if tenures is None:
        _write_notice(sheet, row, NOT_EVALUATED_NOTICE)
        return
    if not tenures:
        _write_notice(sheet, row, NO_INACTIVE_NOTICE)
        return

    _write_notice(sheet, row, INACTIVE_ONLY_NOTICE)
    for tenure in tenures:
        row += 1
        set_text(sheet.cell(row, 1), "Record")
        status = sheet.cell(row, 2)
        set_text(status, "INACTIVE")
        status.font = Font(size=9)
        status.fill = INACTIVE_FILL
        status.alignment = Alignment(horizontal="center")
        set_text(sheet.cell(row, 3), "FLNR")

        first_detail_row = row + 1
        details = [
            ("Business Identifier:", f"Disp Trans SID: {tenure.disposition_id} FILE NUMBER: {tenure.file_number}"),
            ("DPR Registry Name:", "CROWN LANDS"),
            ("Interest Type:", tenure.interest_type),
            ("Name:", tenure.holders),
        ]
        for title, value in details:
            row += 1
            set_text(sheet.cell(row, 1), title)
            set_text(sheet.cell(row, 2), value)
        # The box goes round the record's details, under its "Record" line.
        draw_box(sheet, first_detail_row, row, 1, 3)
        row += 1


# ---------------------------------------------------------------------------
# Sections of the Crown Land Status sheet
# ---------------------------------------------------------------------------

def _write_files_section(page: _Sheet, status: CrownLandStatus) -> None:
    """The file, the agencies it is with, who ran the status, and the purpose note."""
    sheet = page.sheet
    page.row += 1
    first_row = page.row
    _write_line(sheet, page.row, "Files", status.crown_file_number)

    for title in (
        "Application Agency -> Mines",
        "Application Agency -> Lands",
        "Application Agency -> Water",
        "Application Agency -> Forests",
        "Application Received Date",
        "Completed by NRS / Date",
    ):
        page.row += 1
        _write_line(sheet, page.row, title, None)
    page.row += 1
    _write_line(sheet, page.row, "Status Run By / Date", f"{status.run_by}    -    {status.run_date.isoformat()}")

    page.row += 1
    sheet.merge_cells(start_row=page.row, start_column=1, end_row=page.row, end_column=2)
    _write_title(sheet.cell(page.row, TITLE_COLUMN), PURPOSE)
    sheet.row_dimensions[page.row].height = 115

    # Every second line is banded grey, and the box starts under the "Files" line.
    for row in range(first_row + 2, page.row + 1, 2):
        _fill_grey(sheet, row)
    draw_box(sheet, first_row + 1, page.row, 1, 2)


def _write_applicant_section(page: _Sheet, status: CrownLandStatus) -> None:
    """Who applied, then the application's area, location and parcels."""
    sheet = page.sheet
    page.row += 3
    for title, value in (("Applicant", status.applicant_name), ("Agent's Name", ""), ("Project Lead", "")):
        page.row += 1
        _write_line(sheet, page.row, title, value)

    area = status.tenure_area_ha
    if not isinstance(area, str) and area:
        area = f"{area[0]} hectares"

    _write_lines(page, [
        ("Company Incorporation No.", ""),
        ("ATS Project Number", ""),
        ("Application Area (ha)", area),
        ("Client Applied Area", ""),
        ("Dimensions", ""),
        ("Amendments Existing Area", ""),
        ("Amendments New Area", ""),
        ("Location", status.tenure_location),
        ("Map Sheet", status.mapsheets),
        ("Shapefile Source", ""),
        ("Geomark", ""),
        ("Legal Description", status.tenure_legal_description),
        ("PIN Intersects", status.pins),
        ("PIN Adjacent", status.pins_adjacent),
        ("PIN Right of Ways", status.pins_right_of_way),
        ("PIN Reverted or Acquired", ""),
        ("PID Number (if titled)", ""),
    ])


def _write_section(page: _Sheet, heading: str, lines: list[tuple[str, Value]]) -> None:
    """Write a section: its heading, two rows below what came before, then its lines in a box."""
    page.row += 2
    _write_title(page.sheet.cell(page.row, TITLE_COLUMN), heading)
    _write_lines(page, lines)


def _write_lines(page: _Sheet, lines: list[tuple[str, Value]]) -> None:
    """Write a block of lines under page.row, band every second one grey, and box the block.

    A line with several values takes one row per value, its title on the first.
    """
    sheet = page.sheet
    first_row = page.row + 1
    for count, (title, value) in enumerate(lines, start=1):
        page.row += 1
        line_first_row = page.row
        values = [value] if isinstance(value, str) else (list(value) or [""])

        _write_title(sheet.cell(page.row, TITLE_COLUMN), title)
        for position, text in enumerate(values):
            if position:
                page.row += 1
            _write_value(sheet.cell(page.row, VALUE_COLUMN), text)

        if title == "Geomark":
            page.geomark_cell = f"B{line_first_row}"
        if count % 2 == 0:
            for row in range(line_first_row, page.row + 1):
                _fill_grey(sheet, row)
    draw_box(sheet, first_row, page.row, 1, 2)


def _write_comments_section(page: _Sheet) -> None:
    """A tall empty box for comments, then the pointer to the Conflicts & Constraints tab."""
    sheet = page.sheet
    page.row += 2
    _write_title(sheet.cell(page.row, TITLE_COLUMN), "Additional Comments")

    page.row += 1
    sheet.merge_cells(start_row=page.row, start_column=1, end_row=page.row, end_column=2)
    sheet.row_dimensions[page.row].height = 95
    draw_box(sheet, page.row, page.row + 1, 1, 2)

    page.row += 2
    _write_notice(sheet, page.row, SEE_TAB_3)


def _blank_lines(*titles: str) -> list[tuple[str, Value]]:
    """Lines that are written with no value, for the business area to fill in."""
    return [(title, "") for title in titles]


# ---------------------------------------------------------------------------
# Writing cells
# ---------------------------------------------------------------------------

def _new_sheet(book: Workbook, name: str, widths: dict[str, float], index: Optional[int]) -> Worksheet:
    """Create a sheet with its column widths and the red disclaimer across the top."""
    sheet = book.create_sheet(name, index)
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.merge_cells("A1:C1")
    _write_notice(sheet, 1, DISCLAIMER)
    return sheet


def _write_line(sheet: Worksheet, row: int, title: str, value: Optional[str]) -> None:
    """Write one line: its title, and its value when it has one."""
    _write_title(sheet.cell(row, TITLE_COLUMN), title)
    if value is not None:
        _write_value(sheet.cell(row, VALUE_COLUMN), value)


def _write_title(cell, text: str) -> None:
    set_text(cell, text)
    cell.font = TITLE_FONT
    cell.alignment = WRAP


def _write_value(cell, text: str) -> None:
    set_text(cell, str(text))
    cell.font = VALUE_FONT
    cell.alignment = WRAP


def _write_notice(sheet: Worksheet, row: int, text: str) -> None:
    """Write a line of red text in the first column."""
    cell = sheet.cell(row, 1)
    set_text(cell, text)
    cell.font = Font(color=RED, size=12, name="Arial")


def _fill_grey(sheet: Worksheet, row: int) -> None:
    """Band one row grey, across the title and value columns."""
    for column in (TITLE_COLUMN, VALUE_COLUMN):
        sheet.cell(row, column).fill = GREY_FILL
