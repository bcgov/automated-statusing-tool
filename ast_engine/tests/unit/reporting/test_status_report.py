"""Tests for assembling the status report workbook from its tabs."""

from datetime import date

import openpyxl
import pytest

from ast_engine.reporting.conflicts_report import DatasetReport, PartOutcome, ReportHeader
from ast_engine.reporting.crown_land_status import CrownLandStatus
from ast_engine.reporting.status_report import write_status_report

pytestmark = pytest.mark.unit

HEADER = ReportHeader(report_date=date(2026, 3, 31), region="Cariboo", aoi_name="AOI", crown_file_number="7410123")
DATASET = DatasetReport(category="Critical Conflicts", name="Parks", datasource="A.B", parts=(PartOutcome(0),))


def _write(tmp_path, status: CrownLandStatus):
    path = write_status_report(
        tmp_path / "out" / "status-report.xlsx",
        header=HEADER,
        datasets=[DATASET],
        crown_land_status=status,
        inactive_tenures=[],
    )
    return openpyxl.load_workbook(path)


def test_report_has_the_tabs_in_the_order_the_status_is_read(tmp_path):
    book = _write(tmp_path, CrownLandStatus(run_date=date(2026, 3, 31), crown_file_number="7410123"))

    assert book.sheetnames == ["Crown Land Status", "Status of Conflict", "Conflicts & Constraints", "Data Sources"]
    assert book["Status of Conflict"]["B3"].value == "7410123"
    assert "Parks" in [cell.value for cell in book["Conflicts & Constraints"]["C"]]


def test_conflicts_tab_repeats_the_geomark_typed_into_the_first_tab(tmp_path):
    book = _write(tmp_path, CrownLandStatus(run_date=date(2026, 3, 31)))
    sheet = book["Conflicts & Constraints"]

    assert sheet["B7"].value == "Geomark: "
    assert sheet["C7"].value == """=IF('Crown Land Status'!B28=0,"",'Crown Land Status'!B28)"""
    assert book["Crown Land Status"]["A28"].value == "Geomark"


def test_the_geomark_formula_follows_the_line_when_it_moves(tmp_path):
    """Two mapsheets push the Geomark line down a row."""
    status = CrownLandStatus(run_date=date(2026, 3, 31), mapsheets=("092P.045", "092P.046"))

    book = _write(tmp_path, status)

    assert "'Crown Land Status'!B29" in book["Conflicts & Constraints"]["C7"].value
    assert book["Crown Land Status"]["A29"].value == "Geomark"


def test_a_report_without_tab3_has_the_first_two_tabs_only(tmp_path):
    path = write_status_report(
        tmp_path / "status-report.xlsx",
        header=HEADER,
        datasets=[DATASET],
        crown_land_status=CrownLandStatus(run_date=date(2026, 3, 31), crown_file_number="7410123"),
        inactive_tenures=[],
        include_conflicts=False,
    )

    assert openpyxl.load_workbook(path).sheetnames == ["Crown Land Status", "Status of Conflict"]
