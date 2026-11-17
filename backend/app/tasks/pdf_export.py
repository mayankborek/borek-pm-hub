"""PDF export of tasks (BB-05): a readable task list to view, print or send. Not for import:
moving tasks between systems is what the CSV and XLSX files are for.

Same tasks as the CSV and XLSX for the same scope, because the router passes the same list.
"""

from collections.abc import Sequence
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.tasks.schemas import TaskOut

# The built-in PDF fonts cover Windows-1252 (German, French, ..., the euro sign, curly quotes).
# Anything else (emoji, other scripts) is shown as "?" instead of failing the export.
ENCODING = "windows-1252"

DATE = "%d.%m.%Y"  # how the team writes dates in documents (the API stays ISO)
COLUMNS = ("Key", "Title", "Status", "Priority", "Assignee", "Labels", "Start", "Due", "Estimate")
# Millimetres on landscape A4 (297 mm wide, 10 mm margins: 277 mm for the table).
WIDTHS = (18, 79, 26, 18, 34, 38, 20, 20, 24)


def printable(text: str) -> str:
    return text.encode(ENCODING, errors="replace").decode(ENCODING)


def _estimate(task: TaskOut) -> str:
    if task.estimate_value is None or task.estimate_unit is None:
        return ""
    unit = str(task.estimate_unit)
    return f"{task.estimate_value} {unit[:-1] if task.estimate_value == 1 else unit}"


def task_row(task: TaskOut) -> list[str]:
    return [
        task.key,
        task.title,
        task.status.name,
        task.priority.value.capitalize(),
        task.assignee.name if task.assignee else "",
        ", ".join(task.labels),
        task.start_date.strftime(DATE) if task.start_date else "",
        task.due_date.strftime(DATE) if task.due_date else "",
        _estimate(task),
    ]


class _TaskListPdf(FPDF):
    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("Helvetica", size=7)
        self.set_text_color(110)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def build_pdf(
    tasks: Sequence[TaskOut],
    *,
    title: str,
    filters: Sequence[str],
    exported_at: datetime,
    compress: bool = True,
) -> bytes:
    """Landscape A4: a heading (what, when, which filters, how many), then one row per task.
    Long cells wrap; the column headings repeat on every page."""
    pdf = _TaskListPdf(orientation="L", unit="mm", format="A4")
    pdf.core_fonts_encoding = ENCODING
    pdf.set_compression(compress)
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_title(printable(f"Tasks: {title}"))
    pdf.set_creator("Borek PM Hub")
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, printable(f"Tasks: {title}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(80)
    count = f"{len(tasks)} task" + ("" if len(tasks) == 1 else "s")
    stamp = exported_at.strftime("%d.%m.%Y %H:%M UTC")
    pdf.cell(0, 5, printable(f"Exported {stamp}  |  {count}"), new_x="LMARGIN", new_y="NEXT")
    scope = "; ".join(filters) if filters else "none (all tasks in scope)"
    pdf.multi_cell(0, 5, printable(f"Filters: {scope}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(2)

    pdf.set_font("Helvetica", size=8)
    if not tasks:
        pdf.cell(0, 6, "No tasks match these filters.")
        return bytes(pdf.output())
    with pdf.table(
        col_widths=WIDTHS,
        width=sum(WIDTHS),
        line_height=4.5,
        headings_style=FontFace(emphasis="BOLD", fill_color=(235, 235, 235)),
        repeat_headings=1,
        text_align="LEFT",
    ) as table:
        heading = table.row()
        for name in COLUMNS:
            heading.cell(name)
        for task in tasks:
            row = table.row()
            for value in task_row(task):
                row.cell(printable(value))
    return bytes(pdf.output())
