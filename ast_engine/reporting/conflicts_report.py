"""
Conflicts & Constraints report: the status spreadsheet's list of what the AOI overlaps.

Writes an Excel workbook with two sheets:

    Conflicts & Constraints   every dataset the status checked, under its
                              category, with what the AOI overlaps in it
    Data Sources              where each dataset was read from, and its filter

This is "Tab 3" of the ArcGIS Pro Automated Status Tool (the spreadsheet its
universal_overlap_tool.py writes, in the Front Counter BC layout), carried over
cell for cell: the same columns and widths, fonts and colours, the grey band on
each dataset, and the thick box around each category.

For every dataset the sheet says one of four things:

    the values found      one line per different combination of the dataset's
                          report fields among the features found, sorted
    overlaps with this value   features were found, and the dataset names no
                               report fields to list
    No data to display    the dataset was checked and nothing was found
    Unsuccessful          the dataset could not be checked

"No data to display" and "Unsuccessful" are kept apart on purpose: the first is
an answer, the second is the lack of one.

What is different from the ArcGIS Pro tool's sheet:

  - the Geomark row of the header is only written in the full status report,
    where the Crown Land Status sheet it reads is in the same workbook;
  - an AOI kept as several parts (dissolve by fields / preserve features) gets
    one block of datasets per part, each under the part's name, where the tool
    wrote one block per value of its sub-report field;
  - a report value is written as plain text. The tool put an apostrophe in
    front of the first field's value;
  - the footer names the AOI, not the folder paths of the tool's input and
    output;
  - the Data Sources sheet lists the registries the datasets came from, where
    the tool listed its input spreadsheets.

Text from a dataset is always written as text, never as a formula: a value that
starts with "=" must not be run by Excel when the workbook is opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Sequence

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .excel import draw_box, set_text

CONFLICTS_SHEET_NAME = "Conflicts & Constraints"
DATA_SOURCES_SHEET_NAME = "Data Sources"

# Printed in red at the top of the sheet.
DISCLAIMER = "INTERNAL PROVINCIAL GOVERNMENT USE ONLY"

# What a dataset's row says when there are no values to list.
TEXT_UNSUCCESSFUL = "Unsuccessful"
TEXT_NO_DATA = "No data to display"
TEXT_OVERLAPS = "overlaps with this value"
# Written in place of a report field a feature has no value for.
TEXT_BLANK_FIELD = "blank field"

# The sheet's columns, as (title, width). The first three have no title: a
# margin, the category column and the dataset name column. The last four are
# left empty for the people working the file to fill in.
COLUMNS = (
    (" ", 1.5),
    ("  ", 18),
    ("   ", 60),
    ("List conflicts", 45),
    ("Map", 15),
    ("Manual Entry of Contact information for Referrals", 35),
    ("Comprehensive Review Comments", 35),
    ("Conflict Overlap Snips", 30),
    ("Business Line Comments", 23),
)
CATEGORY_COLUMN = "B"
DATASET_COLUMN = "C"
VALUE_COLUMN = "D"
MAP_COLUMN = "E"
# A dataset's grey band and a category's box run from the category column to
# the last column.
FIRST_BLOCK_COLUMN = 2
LAST_BLOCK_COLUMN = len(COLUMNS)

# Colours, as Excel writes them (RRGGBB).
BLACK = "000000"
RED = "FF0000"
BLUE = "0000FF"
TEAL = "008080"
ORANGE = "FF6600"
OLIVE = "808000"
LIGHT_BLUE = "3366FF"
PLUM = "993366"
DATASET_FILL = PatternFill(fill_type="solid", start_color="E0E0E0", end_color="E0E0E0")

FONT_NAME = "Arial"

# Archaeology datasets shared under an agreement. Each is flagged on the sheet
# with a link to the agreement.
RESTRICTED_DATASOURCES = frozenset({
    "WHSE_ARCHAEOLOGY.RAAD_AOA_PROVINCIAL",
    "WHSE_ARCHAEOLOGY.RAAD_INFORMED_CONTRIBUTORS_SV",
    "WHSE_ARCHAEOLOGY.RAAD_TFM_SITES_SVW",
})
RESTRICTED_NOTICE = "Archaeological Information Sharing Agreement (gov.bc.ca)"
RESTRICTED_NOTICE_URL = (
    "https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/"
    "natural-resource-use/archaeology/forms-publications/"
    "archaeological_information_sharing_agreement.pdf"
)


@dataclass(frozen=True)
class ReportHeader:
    """What the top of the sheet says about the status.

    report_date         the date the status was run.
    region              the natural resource region it was run for.
    crown_file_number / disposition_number / parcel_number
                        the TANTALIS identifiers; None for an uploaded AOI.
    aoi_name            what the AOI is called, for the footer.
    registries          the names of the registries the datasets came from.
    part_names          a name for each part of the AOI, in order. With one
                        part (the usual case) the name is not shown.
    overview_map_link   where the overview map is; None when no maps were made.
    """

    report_date: date
    region: str
    aoi_name: str
    crown_file_number: Optional[str] = None
    disposition_number: Optional[str] = None
    parcel_number: Optional[str] = None
    registries: tuple[str, ...] = ()
    part_names: tuple[str, ...] = ("",)
    overview_map_link: Optional[str] = None


@dataclass(frozen=True)
class PartOutcome:
    """What one dataset found for one part of the AOI.

    feature_count  how many features were found.
    values         the lines to list: one per different combination of the
                   dataset's report fields among those features. Empty when the
                   dataset names no report fields.
    """

    feature_count: int
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetReport:
    """One dataset's row on the sheet.

    category          the heading it is listed under.
    name              the dataset's name.
    datasource        the table or file it was read from.
    definition_query  its attribute filter, as authored; None if it has none.
    failed            True when the dataset could not be checked.
    parts             what it found for each part of the AOI, in the order of
                      ReportHeader.part_names. Empty when it failed.
    map_link          where the dataset's map is; None when it has no map.
    """

    category: str
    name: str
    datasource: str
    definition_query: Optional[str] = None
    failed: bool = False
    parts: tuple[PartOutcome, ...] = ()
    map_link: Optional[str] = None


def write_conflicts_report(
    path: str | Path,
    header: ReportHeader,
    datasets: Iterable[DatasetReport],
) -> Path:
    """Write the Conflicts & Constraints workbook and return its path.

    datasets are written in the order given, which is the order of the
    registries; a new category heading starts wherever the category changes.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    book = openpyxl.Workbook()
    # A new workbook comes with one empty sheet; the report's own sheets replace it.
    book.remove(book.active)
    add_conflicts_sheets(book, header, datasets)

    book.save(path)
    return path


def add_conflicts_sheets(
    book: openpyxl.Workbook,
    header: ReportHeader,
    datasets: Iterable[DatasetReport],
    *,
    geomark_reference: Optional[str] = None,
) -> None:
    """Add the Conflicts & Constraints and Data Sources sheets to a workbook.

    geomark_reference  the cell on another sheet of the workbook that holds the
                       Geomark, e.g. "'Crown Land Status'!B28". When given, the
                       header shows that cell's value in a Geomark row.
    """
    datasets = list(datasets)

    sheet = book.create_sheet(CONFLICTS_SHEET_NAME)
    sheet.merge_cells("B1:D1")

    row = _write_header(sheet, header, geomark_reference)
    row = _write_column_titles(sheet, row)
    for part_index, part_name in enumerate(header.part_names):
        if len(header.part_names) > 1:
            # One block of datasets per AOI part, under the part's name.
            row += 1
            _write_text(sheet[f"{CATEGORY_COLUMN}{row}"], part_name, color=TEAL, size=12)
        row = _write_datasets(sheet, row, datasets, part_index)
    _write_footer(sheet, row, header)

    _write_data_sources(book.create_sheet(DATA_SOURCES_SHEET_NAME), header, datasets)


def summary_values(feature_properties: Iterable[dict], fields: Sequence[str]) -> tuple[str, ...]:
    """Turn the features a dataset found into the lines listed for it.

    Each feature gives one line: the values of its report fields, in order,
    joined with ";". A field the feature has no value for reads "blank field".
    Features that give the same line are listed once, and the lines are sorted,
    so the sheet shows what kinds of thing the AOI overlaps rather than every
    feature.

    feature_properties  one dict of field values per feature found.
    fields              the dataset's report fields, in order.

    Returns no lines when the dataset names no report fields.
    """
    if not fields:
        return ()
    lines = {
        ";".join(_format_value(properties.get(field)) for field in fields)
        for properties in feature_properties
    }
    return tuple(sorted(lines))


def _format_value(value: object) -> str:
    """A field value as it is listed: text, with whole numbers shown without ".0"."""
    if value is None or value == "":
        return TEXT_BLANK_FIELD
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# ---------------------------------------------------------------------------
# The Conflicts & Constraints sheet
# ---------------------------------------------------------------------------

def _write_header(sheet: Worksheet, header: ReportHeader, geomark_reference: Optional[str] = None) -> int:
    """Write the disclaimer and the facts about the status. Returns the row
    the column titles go on."""
    _write_text(sheet["B1"], DISCLAIMER, color=RED, size=12)

    first_row = 2
    row = first_row
    facts = {
        "Date: ": header.report_date.isoformat(),
        "Region: ": header.region,
        "Crown File Number: ": header.crown_file_number or "",
        "Disposition Number: ": header.disposition_number or "",
        "Parcel Number: ": header.parcel_number or "",
    }
    for label, value in facts.items():
        for column, text in ((CATEGORY_COLUMN, label), (DATASET_COLUMN, value)):
            cell = sheet[f"{column}{row}"]
            _write_text(cell, text, size=10)
            cell.alignment = Alignment(horizontal="justify")
        row += 1

    if geomark_reference:
        # The one formula on the sheet, built here from a cell reference, not
        # from anything read from a dataset. It shows the Geomark someone types
        # into the Crown Land Status tab, and stays blank until they do.
        for column, value in (
            (CATEGORY_COLUMN, "Geomark: "),
            (DATASET_COLUMN, f'=IF({geomark_reference}=0,"",{geomark_reference})'),
        ):
            cell = sheet[f"{column}{row}"]
            cell.value = value
            cell.font = Font(color=BLACK, size=10, name=FONT_NAME)
            cell.alignment = Alignment(horizontal="justify")
        row += 1

    # The overview map sits beside the first header row.
    if header.overview_map_link:
        _write_link(sheet[f"{VALUE_COLUMN}{first_row}"], "Overview Map", header.overview_map_link)

    # Two blank rows between the header and the column titles.
    return row + 2


def _write_column_titles(sheet: Worksheet, row: int) -> int:
    """Write the column titles, set the column widths, and keep the titles in
    view while the sheet is scrolled. Returns the row the titles are on."""
    for index, (title, width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row, index, title)
        cell.font = Font(size=14, bold=True, italic=True)
        cell.alignment = Alignment(wrapText=True)
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = f"B{row + 1}"
    return row


def _write_datasets(sheet: Worksheet, row: int, datasets: list[DatasetReport], part_index: int) -> int:
    """Write every dataset for one part of the AOI, category by category.

    row is the last row written. Returns the row after the last category's box.
    """
    current_category: Optional[str] = None
    box_start = row + 2

    for dataset in datasets:
        if dataset.category != current_category:
            if current_category is not None:
                # Close the box round the category that has just ended.
                _draw_box(sheet, box_start, row)
                row += 2
            box_start = row + 1
            row += 1
            _write_text(sheet[f"{CATEGORY_COLUMN}{row}"], dataset.category, size=14, bold=True)
            current_category = dataset.category

        row += 1
        row = _write_dataset(sheet, row, dataset, part_index)

    if current_category is not None:
        _draw_box(sheet, box_start, row)
    return row + 1


def _write_dataset(sheet: Worksheet, row: int, dataset: DatasetReport, part_index: int) -> int:
    """Write one dataset: its name, the link to its map, and what it found.

    The first thing found goes on the dataset's own row and the rest on the rows
    below, all in the grey band. Returns the first row after the dataset.
    """
    if _datasource_name(dataset.datasource) in RESTRICTED_DATASOURCES:
        notice_cell = sheet[f"{DATASET_COLUMN}{row}"]
        _write_link(notice_cell, RESTRICTED_NOTICE, RESTRICTED_NOTICE_URL, color=ORANGE, size=8, bold=True)
        notice_cell.alignment = Alignment(wrapText=True)
        row += 1

    name_cell = sheet[f"{DATASET_COLUMN}{row}"]
    _write_text(name_cell, dataset.name, size=10, bold=True)
    name_cell.alignment = Alignment(wrapText=True)

    if dataset.map_link:
        _write_link(sheet[f"{MAP_COLUMN}{row}"], "View Map", dataset.map_link)

    if dataset.failed:
        lines, font = [TEXT_UNSUCCESSFUL], dict(color=RED, size=8, bold=True)
    else:
        outcome = dataset.parts[part_index]
        if outcome.feature_count == 0:
            lines, font = [TEXT_NO_DATA], dict(color=BLACK, size=8, bold=True)
        elif not outcome.values:
            lines, font = [TEXT_OVERLAPS], dict(color=BLUE, size=8)
        else:
            lines, font = list(outcome.values), dict(color=BLUE, size=8)

    for line in lines:
        cell = sheet[f"{VALUE_COLUMN}{row}"]
        _write_text(cell, line, **font)
        cell.alignment = Alignment(wrapText=True)
        for column in range(FIRST_BLOCK_COLUMN, LAST_BLOCK_COLUMN + 1):
            sheet.cell(row, column).fill = DATASET_FILL
        row += 1
    return row


def _write_footer(sheet: Worksheet, row: int, header: ReportHeader) -> None:
    """Write what the status was run on, under the last category."""
    _write_text(sheet[f"{DATASET_COLUMN}{row}"], f"input:  {header.aoi_name}", size=10)


def _draw_box(sheet: Worksheet, first_row: int, last_row: int) -> None:
    """Draw a thick box round a category: its heading and all its datasets."""
    draw_box(sheet, first_row, last_row, FIRST_BLOCK_COLUMN, LAST_BLOCK_COLUMN)


# ---------------------------------------------------------------------------
# The Data Sources sheet
# ---------------------------------------------------------------------------

def _write_data_sources(sheet: Worksheet, header: ReportHeader, datasets: list[DatasetReport]) -> None:
    """List the registries the status used, then each dataset's source and filter.

    A file source is written in a different colour from a BCGW table, so the
    two can be told apart at a glance.
    """
    sheet.column_dimensions["A"].width = 55
    sheet.column_dimensions["B"].width = 30

    row = 2
    _write_text(sheet[f"A{row}"], "Registries:", size=10, bold=True)
    row += 1
    for registry in header.registries:
        _write_text(sheet[f"A{row}"], registry, size=7)
        sheet.merge_cells(f"A{row}:B{row}")
        row += 1
    row += 2

    for column, title in (("A", "Data Sources"), ("B", "Definition Query")):
        cell = sheet[f"{column}{row}"]
        _write_text(cell, title, size=10, bold=True)
        cell.alignment = Alignment(wrapText=True)
    row += 1

    for dataset in datasets:
        source_cell = sheet[f"A{row}"]
        colour = LIGHT_BLUE if _is_file_source(dataset.datasource) else OLIVE
        _write_text(source_cell, dataset.datasource, color=colour, size=7)
        source_cell.alignment = Alignment(wrapText=True)

        query_cell = sheet[f"B{row}"]
        _write_text(query_cell, dataset.definition_query or "", color=PLUM, size=6)
        query_cell.alignment = Alignment(wrapText=True)
        row += 1


def _is_file_source(datasource: str) -> bool:
    """True for a file path, False for a BCGW table (SCHEMA.TABLE)."""
    return "/" in datasource or "\\" in datasource


def _datasource_name(datasource: str) -> str:
    """The last part of a datasource: the table name, or the file or layer name."""
    return re.split(r"[\\/]+", datasource.strip().rstrip("\\/"))[-1]


# ---------------------------------------------------------------------------
# Writing a cell
# ---------------------------------------------------------------------------

def _write_text(
    cell: Cell,
    text: str,
    *,
    color: str = BLACK,
    size: int = 10,
    bold: bool = False,
) -> None:
    """Write text into a cell, as text (see set_text), in the sheet's font."""
    set_text(cell, text)
    cell.font = Font(color=color, size=size, name=FONT_NAME, bold=bold)


def _write_link(
    cell: Cell,
    text: str,
    target: str,
    *,
    color: str = BLUE,
    size: int = 10,
    bold: bool = False,
) -> None:
    """Write a hyperlink into a cell."""
    cell.hyperlink = target
    _write_text(cell, text, color=color, size=size, bold=bold)
