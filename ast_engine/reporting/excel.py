"""Small helpers shared by the status report's sheet writers."""

from openpyxl.cell.cell import Cell
from openpyxl.styles.borders import Border, Side
from openpyxl.worksheet.worksheet import Worksheet

_THICK = Side(style="thick")


def set_text(cell: Cell, text: str) -> None:
    """Put text into a cell, as text.

    openpyxl stores a string that starts with "=" as a formula. Names and
    values on the status report come from datasets and from TANTALIS, so the
    cell is marked as holding a string after it is filled: what was read is
    shown, never run by Excel when the workbook is opened.
    """
    cell.value = text
    cell.data_type = "s"


def draw_box(sheet: Worksheet, first_row: int, last_row: int, first_column: int, last_column: int) -> None:
    """Draw a thick box round a block of cells.

    Only the cells on the edge of the block are touched, and each is given the
    sides it sits on.
    """
    for row in range(first_row, last_row + 1):
        for column in range(first_column, last_column + 1):
            sides = {}
            if row == first_row:
                sides["top"] = _THICK
            if row == last_row:
                sides["bottom"] = _THICK
            if column == first_column:
                sides["left"] = _THICK
            if column == last_column:
                sides["right"] = _THICK
            if sides:
                sheet.cell(row, column).border = Border(**sides)
