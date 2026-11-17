"""
Tests for the Conflicts & Constraints report writer.

Each test writes a workbook and reads it back with openpyxl, checking the cells
a person opening the file would see.
"""

from datetime import date
from pathlib import Path

import openpyxl
import pytest

from ast_engine.reporting.conflicts_report import (
    DatasetReport,
    PartOutcome,
    ReportHeader,
    summary_values,
    write_conflicts_report,
)

pytestmark = pytest.mark.unit

HEADER = ReportHeader(
    report_date=date(2026, 3, 31),
    region="Cariboo",
    aoi_name="TANTALIS 7410123/55/9",
    crown_file_number="7410123",
    disposition_number="55",
    parcel_number="9",
    registries=("one_status_common_datasets", "one_status_cariboo_specific"),
)

PARKS = DatasetReport(
    category="Critical Conflicts",
    name="Park and Protected Areas",
    datasource="WHSE_TANTALIS.TA_PARK_ECORES_PA_SVW",
    definition_query="PROTECTED_LANDS_CODE <> 'OI'",
    parts=(PartOutcome(feature_count=3, values=("Class A;Wells Gray Park", "Class B;Bowron Lake Park")),),
)


def _write(tmp_path: Path, datasets, header: ReportHeader = HEADER):
    path = write_conflicts_report(tmp_path / "report.xlsx", header, datasets)
    return openpyxl.load_workbook(path)


def _sheet(tmp_path: Path, datasets, header: ReportHeader = HEADER):
    return _write(tmp_path, datasets, header)["Conflicts & Constraints"]


def _column(sheet, letter: str) -> list[str]:
    """The filled cells of one column, top to bottom."""
    return [cell.value for cell in sheet[letter] if cell.value is not None]


def _row_of(sheet, value: str) -> int:
    """The row holding a value, wherever it is on the sheet."""
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value == value:
                return cell.row
    raise AssertionError(f"{value!r} is not on the sheet")


# --- Header and columns ------------------------------------------------------
def test_workbook_has_the_two_sheets(tmp_path):
    assert _write(tmp_path, [PARKS]).sheetnames == ["Conflicts & Constraints", "Data Sources"]


def test_header_carries_the_disclaimer_and_the_facts_of_the_status(tmp_path):
    sheet = _sheet(tmp_path, [PARKS])

    assert sheet["B1"].value == "INTERNAL PROVINCIAL GOVERNMENT USE ONLY"
    assert sheet["B1"].font.color.rgb == "00FF0000"
    assert [(sheet[f"B{row}"].value, sheet[f"C{row}"].value) for row in range(2, 7)] == [
        ("Date: ", "2026-03-31"),
        ("Region: ", "Cariboo"),
        ("Crown File Number: ", "7410123"),
        ("Disposition Number: ", "55"),
        ("Parcel Number: ", "9"),
    ]


def test_header_leaves_the_identifiers_blank_for_an_uploaded_aoi(tmp_path):
    header = ReportHeader(report_date=date(2026, 3, 31), region="Cariboo", aoi_name="Uploaded area of interest")

    sheet = _sheet(tmp_path, [PARKS], header)

    assert sheet["B4"].value == "Crown File Number: "
    assert sheet["C4"].value in ("", None)


def test_column_titles_and_widths_follow_the_fcbc_layout(tmp_path):
    sheet = _sheet(tmp_path, [PARKS])

    titles = [cell.value for cell in sheet[9]]
    assert titles[3:] == [
        "List conflicts",
        "Map",
        "Manual Entry of Contact information for Referrals",
        "Comprehensive Review Comments",
        "Conflict Overlap Snips",
        "Business Line Comments",
    ]
    assert sheet.column_dimensions["C"].width == 60
    assert sheet.column_dimensions["D"].width == 45
    # The titles stay in view while the datasets scroll.
    assert sheet.freeze_panes == "B10"


# --- What a dataset's row says -----------------------------------------------
def test_a_dataset_lists_its_values_starting_on_its_own_row(tmp_path):
    sheet = _sheet(tmp_path, [PARKS])
    row = _row_of(sheet, "Park and Protected Areas")

    assert sheet[f"B{row - 1}"].value == "Critical Conflicts"
    assert sheet[f"D{row}"].value == "Class A;Wells Gray Park"
    assert sheet[f"D{row + 1}"].value == "Class B;Bowron Lake Park"
    # The grey band runs across the dataset's rows, from column B to column I.
    for band_row in (row, row + 1):
        assert sheet[f"B{band_row}"].fill.start_color.rgb == "00E0E0E0"
        assert sheet[f"I{band_row}"].fill.start_color.rgb == "00E0E0E0"
    assert sheet[f"B{row + 2}"].fill.start_color.rgb != "00E0E0E0"


@pytest.mark.parametrize(
    "dataset, expected",
    [
        (DatasetReport(category="C", name="D", datasource="A.B", failed=True), "Unsuccessful"),
        (DatasetReport(category="C", name="D", datasource="A.B", parts=(PartOutcome(0),)), "No data to display"),
        (DatasetReport(category="C", name="D", datasource="A.B", parts=(PartOutcome(4),)), "overlaps with this value"),
    ],
)
def test_a_dataset_with_no_values_says_why(tmp_path, dataset, expected):
    """Could not be checked, checked and found nothing, and found something but
    names no fields to list, are three different answers."""
    sheet = _sheet(tmp_path, [dataset])

    assert sheet[f"D{_row_of(sheet, 'D')}"].value == expected


def test_unsuccessful_is_written_in_red(tmp_path):
    sheet = _sheet(tmp_path, [DatasetReport(category="C", name="D", datasource="A.B", failed=True)])

    assert sheet[f"D{_row_of(sheet, 'D')}"].font.color.rgb == "00FF0000"


def test_a_dataset_links_to_its_map(tmp_path):
    dataset = DatasetReport(
        category="C", name="D", datasource="A.B", parts=(PartOutcome(1),), map_link="maps/common__D.html",
    )
    header = ReportHeader(
        report_date=date(2026, 3, 31), region="Cariboo", aoi_name="AOI", overview_map_link="maps/00overview.html",
    )

    sheet = _sheet(tmp_path, [dataset], header)

    map_cell = sheet[f"E{_row_of(sheet, 'D')}"]
    assert map_cell.value == "View Map"
    assert map_cell.hyperlink.target == "maps/common__D.html"
    assert sheet["D2"].value == "Overview Map"
    assert sheet["D2"].hyperlink.target == "maps/00overview.html"


def test_a_restricted_archaeology_dataset_is_flagged_with_the_sharing_agreement(tmp_path):
    dataset = DatasetReport(
        category="Critical Conflicts",
        name="Archaeology Sites",
        datasource="WHSE_ARCHAEOLOGY.RAAD_TFM_SITES_SVW",
        parts=(PartOutcome(0),),
    )

    sheet = _sheet(tmp_path, [dataset])
    row = _row_of(sheet, "Archaeology Sites")

    notice = sheet[f"C{row - 1}"]
    assert notice.value == "Archaeological Information Sharing Agreement (gov.bc.ca)"
    assert notice.hyperlink.target.startswith("https://www2.gov.bc.ca/")


def test_text_from_a_dataset_is_never_written_as_a_formula(tmp_path):
    """A name or a value that starts with "=" would be run by Excel as a formula
    when the workbook is opened."""
    dataset = DatasetReport(
        category="=1+1",
        name='=HYPERLINK("http://example.com","click")',
        datasource="A.B",
        definition_query="=2+2",
        parts=(PartOutcome(1, values=("=cmd|' /C calc'!A0",)),),
    )

    book = _write(tmp_path, [dataset])
    sheet = book["Conflicts & Constraints"]
    row = _row_of(sheet, dataset.name)

    sources = book["Data Sources"]
    query_cell = sources[f"B{_row_of(sources, '=2+2')}"]
    for cell in (sheet[f"B{row - 1}"], sheet[f"C{row}"], sheet[f"D{row}"], query_cell):
        assert cell.data_type == "s"
    assert sheet[f"D{row}"].value == "=cmd|' /C calc'!A0"


# --- Categories --------------------------------------------------------------
def _dataset(category: str, name: str) -> DatasetReport:
    return DatasetReport(category=category, name=name, datasource="A.B", parts=(PartOutcome(0),))


def test_datasets_are_listed_under_their_categories_in_order(tmp_path):
    datasets = [
        _dataset("Critical Conflicts", "Indian Reserves"),
        _dataset("Critical Conflicts", "National Park"),
        _dataset("Land Interests", "Crown Tenures"),
    ]

    sheet = _sheet(tmp_path, datasets)

    # Below the header and the column titles, column B holds the categories and
    # column C the datasets (then the footer).
    assert _column(sheet, "B")[7:] == ["Critical Conflicts", "Land Interests"]
    assert _column(sheet, "C")[6:9] == ["Indian Reserves", "National Park", "Crown Tenures"]
    assert _row_of(sheet, "Critical Conflicts") < _row_of(sheet, "National Park") < _row_of(sheet, "Land Interests")


def test_each_category_sits_in_its_own_thick_box(tmp_path):
    datasets = [_dataset("Critical Conflicts", "Indian Reserves"), _dataset("Land Interests", "Crown Tenures")]

    sheet = _sheet(tmp_path, datasets)
    top = _row_of(sheet, "Critical Conflicts")
    bottom = _row_of(sheet, "Indian Reserves") + 1  # the blank row under the last dataset

    assert sheet[f"B{top}"].border.top.style == "thick"
    assert sheet[f"B{top}"].border.left.style == "thick"
    assert sheet[f"I{top}"].border.right.style == "thick"
    assert sheet[f"B{bottom}"].border.bottom.style == "thick"
    assert sheet[f"I{bottom}"].border.bottom.style == "thick"
    # The next category starts its own box, two rows further down.
    assert _row_of(sheet, "Land Interests") == bottom + 3
    assert sheet[f"B{bottom + 3}"].border.top.style == "thick"


def test_footer_names_the_aoi(tmp_path):
    sheet = _sheet(tmp_path, [PARKS])

    assert _column(sheet, "C")[-1] == "input:  TANTALIS 7410123/55/9"


# --- An AOI in several parts -------------------------------------------------
def test_an_aoi_in_parts_gets_one_block_of_datasets_per_part(tmp_path):
    header = ReportHeader(
        report_date=date(2026, 3, 31), region="Cariboo", aoi_name="AOI", part_names=("BLOCK = A", "BLOCK = B"),
    )
    dataset = DatasetReport(
        category="Critical Conflicts",
        name="Parks",
        datasource="A.B",
        parts=(PartOutcome(1, values=("Class A",)), PartOutcome(0)),
    )

    sheet = _sheet(tmp_path, [dataset], header)

    block_a, block_b = _row_of(sheet, "BLOCK = A"), _row_of(sheet, "BLOCK = B")
    values = {cell.row: cell.value for cell in sheet["D"] if cell.value and cell.row > block_a}
    assert [value for row, value in values.items() if row < block_b] == ["Class A"]
    assert [value for row, value in values.items() if row > block_b] == ["No data to display"]


def test_a_single_part_is_not_named(tmp_path):
    header = ReportHeader(report_date=date(2026, 3, 31), region="Cariboo", aoi_name="AOI", part_names=("Part 1",))

    sheet = _sheet(tmp_path, [PARKS], header)

    assert "Part 1" not in [cell.value for row in sheet.iter_rows() for cell in row]


# --- The Data Sources sheet --------------------------------------------------
def test_data_sources_lists_the_registries_then_each_source_and_filter(tmp_path):
    file_dataset = DatasetReport(
        category="C", name="Local", datasource=r"\\server\share\data.gdb\layer", parts=(PartOutcome(0),),
    )

    sheet = _write(tmp_path, [PARKS, file_dataset])["Data Sources"]

    assert _column(sheet, "A") == [
        "Registries:",
        "one_status_common_datasets",
        "one_status_cariboo_specific",
        "Data Sources",
        "WHSE_TANTALIS.TA_PARK_ECORES_PA_SVW",
        r"\\server\share\data.gdb\layer",
    ]
    assert _column(sheet, "B") == ["Definition Query", "PROTECTED_LANDS_CODE <> 'OI'"]
    # A file source and a BCGW table are written in different colours.
    assert sheet["A8"].font.color.rgb != sheet["A9"].font.color.rgb


# --- The lines listed for a dataset ------------------------------------------
def test_summary_values_lists_each_combination_once_sorted():
    features = [
        {"CLASS": "B", "NAME": "Bowron"},
        {"CLASS": "A", "NAME": "Wells Gray"},
        {"CLASS": "B", "NAME": "Bowron"},
    ]

    assert summary_values(features, ["CLASS", "NAME"]) == ("A;Wells Gray", "B;Bowron")


def test_summary_values_marks_a_missing_value_and_trims_whole_numbers():
    features = [{"ID": 5.0}, {"ID": 2.5, "NAME": "x"}, {"ID": 7, "NAME": ""}]

    assert summary_values(features, ["ID", "NAME"]) == ("2.5;x", "5;blank field", "7;blank field")


def test_summary_values_is_empty_without_report_fields():
    assert summary_values([{"A": 1}], []) == ()
