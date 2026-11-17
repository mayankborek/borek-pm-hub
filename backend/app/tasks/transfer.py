"""CSV and XLSX export of tasks (S2-31, S2-32, BB-05). Pure functions: no database, no web layer.

The export file is also valid input for the import, so tasks can be moved between projects or
restored. Columns use Jira's names where Jira has an equivalent.
"""

import csv
import io
from collections.abc import Sequence

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from app.tasks.schemas import MAX_LABELS, TaskOut

BOM = "﻿"  # Excel needs it to show umlauts in a UTF-8 file
SEPARATOR = ";"  # German Excel opens comma files in one column (decision D8)

# Excel and Sheets run a cell that starts with one of these as a formula. A task title typed by
# anyone could then run on the PM's machine, so the export puts a ' in front.
_FORMULA_START = frozenset("=+-@\t\r")

EXPORT_COLUMNS = (
    "Issue key",
    "Project key",
    "Project name",
    "Summary",
    "Description",
    "Status",
    "Priority",
    "Assignee",
    "Assignee email",
    "Labels",
    "Start date",
    "Due date",
    "Estimate",
    "Estimate unit",
    "Created",
    "Updated",
    "Resolved",
)


def protect_cell(value: str) -> str:
    """Make a text cell safe to open in a spreadsheet."""
    return f"'{value}" if value and value[0] in _FORMULA_START else value


def unprotect_cell(value: str) -> str:
    """Undo `protect_cell` (import side): the ' counts only in front of a formula character."""
    return value[1:] if value[:1] == "'" and value[1:2] in _FORMULA_START else value


def _label_columns(tasks: Sequence[TaskOut]) -> int:
    """Jira writes one `Labels` column per label, so a file can have several with one name."""
    return max(1, min(MAX_LABELS, max((len(task.labels) for task in tasks), default=0)))


def build_table(tasks: Sequence[TaskOut]) -> list[list[str]]:
    """Header row plus one row per task, every cell made safe for spreadsheets. The same table
    goes into the CSV and the XLSX file, so both import the same way."""
    label_columns = _label_columns(tasks)
    header = list(EXPORT_COLUMNS)
    labels_at = header.index("Labels")
    header[labels_at : labels_at + 1] = ["Labels"] * label_columns
    table = [header]
    for task in tasks:
        row = [
            task.key,
            task.key.rsplit("-", 1)[0],
            task.project_name,
            task.title,
            task.description or "",
            task.status.name,
            task.priority.value,
            task.assignee.name if task.assignee else "",
            task.assignee.email if task.assignee else "",
            *(task.labels + [""] * label_columns)[:label_columns],
            task.start_date.isoformat() if task.start_date else "",
            task.due_date.isoformat() if task.due_date else "",
            str(task.estimate_value) if task.estimate_value is not None else "",
            task.estimate_unit or "",
            task.created_at.isoformat(timespec="seconds"),
            task.updated_at.isoformat(timespec="seconds"),
            task.completed_at.isoformat(timespec="seconds") if task.completed_at else "",
        ]
        table.append([protect_cell(cell) for cell in row])
    return table


def build_csv(tasks: Sequence[TaskOut]) -> bytes:
    """The export file: UTF-8 with BOM, semicolon separated, one header row."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=SEPARATOR, lineterminator="\r\n")
    writer.writerows(build_table(tasks))
    return (BOM + out.getvalue()).encode("utf-8")


def build_xlsx(tasks: Sequence[TaskOut]) -> bytes:
    """The same table as the CSV, as an Excel workbook with one sheet "Tasks". Every cell is
    text (dates in ISO form), so nothing is changed by Excel and the file imports again."""
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Tasks")
    for row in build_table(tasks):
        cells = []
        for value in row:
            cell = WriteOnlyCell(sheet, value=value or None)
            if value:
                # Text, never a formula: openpyxl would otherwise write "=..." as a formula.
                cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()
