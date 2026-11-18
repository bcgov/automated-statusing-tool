"""
Tests for the Crown Land Status and Status of Conflict sheet writers.

Each test writes the sheet into a workbook in memory and checks the cells a
person opening the file would see.
"""

from datetime import date

import openpyxl
import pytest

from ast_engine.core.data_adapters.oracle.tantalis_status import InactiveTenure
from ast_engine.reporting.crown_land_status import (
    CrownLandStatus,
    add_crown_land_status_sheet,
    add_status_of_conflict_sheet,
)

pytestmark = pytest.mark.unit

STATUS = CrownLandStatus(
    run_date=date(2026, 3, 31),
    run_by="Alice",
    crown_file_number="7410123",
    disposition_number="55",
    region="Cariboo",
    applicant_name="ACME GRAVEL LTD.",
    received_dates=("2026-01-15",),
    tenure_area_ha=("12.5",),
    tenure_type=("LICENCE",),
    parcel_numbers=("987654",),
    mapsheets=("092P.045", "092P.046"),
    pins=("1234 - DISTRICT LOT 1", "5678 - DISTRICT LOT 2", "9012 - DISTRICT LOT 3"),
    regional_districts=("Cariboo Regional District",),
    in_alr="No",
    nearest_indian_reserve="CANIM LAKE 1 - CANIM LAKE | 12.3 km(s)",
    nearest_arch_site="3.4 (km) - EkRj-1",
    arch_potential=("High",),
)


def _status_sheet(status: CrownLandStatus = STATUS):
    book = openpyxl.Workbook()
    geomark_cell = add_crown_land_status_sheet(book, status)
    return book["Crown Land Status"], geomark_cell


def _row_of(sheet, title: str, start: int = 1) -> int:
    """The first row at or after `start` whose column A holds a title."""
    for row in range(start, sheet.max_row + 1):
        if sheet.cell(row, 1).value == title:
            return row
    raise AssertionError(f"{title!r} is not in column A")


def _value(sheet, title: str, start: int = 1) -> str:
    return sheet.cell(_row_of(sheet, title, start), 2).value


# --- Crown Land Status -------------------------------------------------------
def test_sheet_opens_with_the_disclaimer_and_the_title():
    sheet, _ = _status_sheet()

    assert sheet["A1"].value == "This product contains sensitive information.  INTERNAL GOVERNMENT USE ONLY"
    assert sheet["A1"].font.color.rgb == "00FF0000"
    assert sheet["A2"].value == "Status Summary"
    assert sheet.column_dimensions["A"].width == 30
    assert sheet.column_dimensions["B"].width == 50


def test_files_section_names_the_file_and_who_ran_the_status():
    sheet, _ = _status_sheet()

    assert (sheet["A3"].value, sheet["B3"].value) == ("Files", "7410123")
    assert [sheet.cell(row, 1).value for row in range(4, 11)] == [
        "Application Agency -> Mines",
        "Application Agency -> Lands",
        "Application Agency -> Water",
        "Application Agency -> Forests",
        "Application Received Date",
        "Completed by NRS / Date",
        "Status Run By / Date",
    ]
    assert sheet["B10"].value == "Alice    -    2026-03-31"
    assert sheet["A11"].value.startswith("Purpose: The purpose of this status summary")
    assert sheet.row_dimensions[11].height == 115


def test_applicant_section_lists_the_applicant_and_the_application():
    sheet, _ = _status_sheet()

    assert (sheet["A15"].value, sheet["B15"].value) == ("Applicant", "ACME GRAVEL LTD.")
    assert [sheet.cell(row, 1).value for row in (16, 17, 18)] == [
        "Agent's Name", "Project Lead", "Company Incorporation No.",
    ]
    assert _value(sheet, "Application Area (ha)") == "12.5 hectares"


def test_a_value_with_several_entries_takes_a_row_each():
    sheet, _ = _status_sheet()
    row = _row_of(sheet, "PIN Intersects")

    assert [sheet.cell(row + offset, 2).value for offset in range(3)] == [
        "1234 - DISTRICT LOT 1", "5678 - DISTRICT LOT 2", "9012 - DISTRICT LOT 3",
    ]
    # The title is on the first row only, and the next line follows the last entry.
    assert sheet.cell(row + 1, 1).value is None
    assert sheet.cell(row + 3, 1).value == "PIN Adjacent"


def test_every_second_line_is_banded_grey_across_all_its_rows():
    sheet, _ = _status_sheet()

    def grey(row: int) -> bool:
        return sheet.cell(row, 1).fill.fgColor.rgb == "00E6E6E6" and sheet.cell(row, 2).fill.fgColor.rgb == "00E6E6E6"

    first = _row_of(sheet, "Company Incorporation No.")
    assert not grey(first)
    assert grey(first + 1)  # ATS Project Number, the second line
    # "PIN Intersects" is the 13th line: not banded, on any of its three rows.
    pins = _row_of(sheet, "PIN Intersects")
    assert not any(grey(pins + offset) for offset in range(3))
    # "PIN Adjacent" is the 14th: banded.
    assert grey(pins + 3)


def test_geomark_cell_is_reported_where_the_line_landed():
    """The Map Sheet line above it takes two rows here, so Geomark is one row
    lower than on a status with a single mapsheet."""
    sheet, geomark_cell = _status_sheet()

    assert geomark_cell == f"B{_row_of(sheet, 'Geomark')}" == "B29"
    _, single = _status_sheet(CrownLandStatus(run_date=date(2026, 3, 31)))
    assert single == "B28"


def test_lands_section_reports_what_the_aoi_falls_in():
    sheet, _ = _status_sheet()
    lands = _row_of(sheet, "Lands note: this information may be applied to all agency application types")

    assert _value(sheet, "File Number", lands) == "7410123"
    assert _value(sheet, "DID Number", lands) == "55"
    assert _value(sheet, "DID Received Date", lands) == "2026-01-15"
    assert _value(sheet, "Parcel Number", lands) == "987654"
    assert _value(sheet, "Region", lands) == "Cariboo"
    assert _value(sheet, "Type", lands) == "LICENCE"
    assert _value(sheet, "Regional District", lands) == "Cariboo Regional District"
    assert _value(sheet, "In Agricultural Land Reserve", lands) == "No"
    assert _value(sheet, "Nearest Indian Res", lands) == "CANIM LAKE 1 - CANIM LAKE | 12.3 km(s)"


def test_provincial_forest_exclusion_has_both_its_lines():
    """The ArcGIS Pro tool listed the title twice, so one value replaced the other."""
    status = CrownLandStatus(
        run_date=date(2026, 3, 31),
        provincial_forest_exclusion=("Exclusion - Park",),
        provincial_forest_exclusion2=("42",),
    )

    sheet, _ = _status_sheet(status)

    assert _value(sheet, "Provincial Forest Exclusion") == "Exclusion - Park"
    assert _value(sheet, "Provincial Forest Exclusion2") == "42"


def test_adjudication_section_reports_archaeology():
    sheet, _ = _status_sheet()

    assert _value(sheet, "Nearest Arch Site within 25km") == "3.4 (km) - EkRj-1"
    assert _value(sheet, "Overview Assessment Potential") == "High"


def test_sections_follow_in_order_each_in_a_box():
    sheet, _ = _status_sheet()
    headings = [
        "Lands note: this information may be applied to all agency application types",
        "Lands Adjudication Information",
        "Mines  -  See status number at top of report",
        "Forests",
        "Water",
        "Additional Comments",
    ]

    rows = [_row_of(sheet, heading) for heading in headings]

    assert rows == sorted(rows)
    # A section's box starts on the line under its heading and ends on its last line.
    forests = _row_of(sheet, "Forests")
    assert sheet.cell(forests + 1, 1).border.top.style == "thick"
    assert sheet.cell(forests + 6, 2).border.bottom.style == "thick"
    assert sheet.cell(forests + 7, 1).value is None


def test_blank_lines_are_left_for_the_business_areas_to_fill_in():
    sheet, _ = _status_sheet()
    mines = _row_of(sheet, "Mines  -  See status number at top of report")

    assert [sheet.cell(mines + offset, 1).value for offset in range(1, 11)] == [
        "Mine Number", "Permit Number", "Mine Type", "Mine Name", "Mine Manager",
        "Inspector", "New Permit", "Crown", "Private", "License Number",
    ]
    assert all(sheet.cell(mines + offset, 2).value in ("", None) for offset in range(1, 11))


def test_sheet_ends_by_pointing_to_the_conflicts_tab():
    sheet, _ = _status_sheet()
    comments = _row_of(sheet, "Additional Comments")

    assert sheet.row_dimensions[comments + 1].height == 95
    assert sheet.cell(comments + 3, 1).value == "SEE TAB 3  CONFLICTS & CONSTRAINTS FOR COMPLETE STATUS"


@pytest.mark.parametrize("region, expected", [("Omineca", True), ("omineca", True), ("Cariboo", False)])
def test_omineca_gets_its_own_section(region, expected):
    sheet, _ = _status_sheet(CrownLandStatus(run_date=date(2026, 3, 31), region=region))
    titles = [sheet.cell(row, 1).value for row in range(1, sheet.max_row + 1)]

    assert ("Omineca Manual Entries  -  yes / no / unk / exist / prop / adj" in titles) is expected
    assert ("Stream Crossings" in titles) is expected


def test_text_from_tantalis_is_never_written_as_a_formula():
    status = CrownLandStatus(run_date=date(2026, 3, 31), applicant_name="=1+1", pins=("=2+2",))

    sheet, _ = _status_sheet(status)

    assert sheet["B15"].value == "=1+1" and sheet["B15"].data_type == "s"
    pins = sheet.cell(_row_of(sheet, "PIN Intersects"), 2)
    assert pins.value == "=2+2" and pins.data_type == "s"


# --- Status of Conflict ------------------------------------------------------
def _conflict_sheet(tenures):
    book = openpyxl.Workbook()
    add_status_of_conflict_sheet(book, "7410123", tenures)
    return book["Status of Conflict"]


TENURES = [
    InactiveTenure(disposition_id=900, file_number="7400001", interest_type="QUARRYING LICENCE",
                   holders="Old Holder Ltd. / Sam Lee"),
    InactiveTenure(disposition_id=800, file_number="7400002", interest_type="AGRICULTURE LEASE", holders="Pat Roy"),
]


def test_conflict_sheet_names_the_file():
    sheet = _conflict_sheet([])

    assert sheet["A1"].value == "This product contains sensitive information.  INTERNAL GOVERNMENT USE ONLY"
    assert (sheet["A3"].value, sheet["B3"].value) == ("File:", "7410123")
    assert sheet.column_dimensions["B"].width == 60


def test_each_inactive_tenure_is_a_record_with_its_details_boxed():
    sheet = _conflict_sheet(TENURES)

    assert sheet["A5"].value == "'Status of Conflict' only evaluates against inactive crown land tenures."
    assert [sheet.cell(6, column).value for column in (1, 2, 3)] == ["Record", "INACTIVE", "FLNR"]
    assert sheet["B6"].fill.fgColor.rgb == "00FFFF00"
    assert [(sheet.cell(row, 1).value, sheet.cell(row, 2).value) for row in range(7, 11)] == [
        ("Business Identifier:", "Disp Trans SID: 900 FILE NUMBER: 7400001"),
        ("DPR Registry Name:", "CROWN LANDS"),
        ("Interest Type:", "QUARRYING LICENCE"),
        ("Name:", "Old Holder Ltd. / Sam Lee"),
    ]
    assert sheet["A7"].border.top.style == "thick"
    assert sheet["C10"].border.bottom.style == "thick"
    # The next record starts after one empty row.
    assert sheet["A11"].value is None
    assert sheet["A12"].value == "Record"
    assert sheet["B13"].value == "Disp Trans SID: 800 FILE NUMBER: 7400002"


def test_an_aoi_with_no_inactive_tenures_says_so():
    sheet = _conflict_sheet([])

    assert sheet["A5"].value == (
        "'Status of Conflict' only evaluates against inactive crown land tenures. "
        "No inactive crown land tenures reported."
    )


def test_an_aoi_that_could_not_be_checked_does_not_look_clear():
    """None is "could not be read" - a different answer from "has none"."""
    sheet = _conflict_sheet(None)

    assert sheet["A5"].value.startswith("ERROR: The AST was unable to evaluate the AOI")
    assert "No inactive crown land tenures reported" not in sheet["A5"].value
