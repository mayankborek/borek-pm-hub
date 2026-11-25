"""A generated report as an A4 PDF (layout from the Figma "Task report.pdf"): heading, details
row (client, reporting period, prepared by), KPI tiles, status distribution, facts, expert
summary, tables, footer with project, date, audience and page."""

from datetime import date

from fpdf import FPDF

from app.project_reports.schemas import ReportContent
from app.tasks.pdf_export import DATE, printable

INDIGO = (13, 18, 64)
GREY = (92, 97, 120)
LINE = (226, 228, 236)


def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime(DATE)
    except ValueError:
        return iso


class _Pdf(FPDF):
    footer_text = ""

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=7)
        self.set_text_color(*GREY)
        width = self.w - self.l_margin - self.r_margin
        self.cell(width / 2, 5, printable(self.footer_text))
        self.cell(width / 2, 5, f"{self.page_no()} / {{nb}}", align="R")


def build_pdf(
    *,
    project_name: str,
    project_code: str,
    title: str,
    client_name: str | None,
    period: str,
    prepared_by: str,
    generated_on: date,
    audience: str,
    summary: str | None,
    content: ReportContent,
    date_columns: frozenset[str] = frozenset(
        {"Due", "Baseline", "Forecast", "Reached", "Raised", "Decided"}
    ),
) -> bytes:
    pdf = _Pdf(orientation="portrait", unit="mm", format="A4")
    pdf.footer_text = f"Borek Flow · {project_name}    {generated_on:{DATE}} · {audience}"
    pdf.set_title(printable(f"{project_name} - {title}"))
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", style="B", size=9)
    pdf.set_text_color(18, 79, 148)
    pdf.cell(
        width,
        5,
        printable(f"{project_name.upper()} / {project_code}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(*INDIGO)
    pdf.set_font("Helvetica", style="B", size=20)
    pdf.multi_cell(width, 10, printable(title))
    pdf.ln(2)

    # details row
    pdf.set_fill_color(243, 244, 248)
    third = width / 3
    labels = ("CLIENT", "REPORTING PERIOD", "PREPARED BY")
    values = (client_name or "Internal project", period, prepared_by)
    pdf.set_font("Helvetica", style="B", size=7)
    pdf.set_text_color(*GREY)
    for label in labels:
        pdf.cell(third, 5, label, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*INDIGO)
    for value in values:
        pdf.cell(third, 6, printable(value), fill=True)
    pdf.ln(9)

    if content.kpis:
        tile = width / len(content.kpis)
        pdf.set_draw_color(*LINE)
        y = pdf.get_y()
        for i, kpi in enumerate(content.kpis):
            x = pdf.l_margin + i * tile
            pdf.rect(x + 1, y, tile - 2, 18)
            pdf.set_xy(x + 3, y + 2)
            pdf.set_font("Helvetica", style="B", size=15)
            pdf.cell(tile - 6, 8, printable(kpi.value))
            pdf.set_xy(x + 3, y + 11)
            pdf.set_font("Helvetica", size=8)
            pdf.set_text_color(*GREY)
            pdf.cell(tile - 6, 5, printable(kpi.label))
            pdf.set_text_color(*INDIGO)
        pdf.set_xy(pdf.l_margin, y + 22)

    section = 0

    def heading(text: str) -> None:
        nonlocal section
        section += 1
        pdf.ln(3)
        pdf.set_font("Helvetica", style="B", size=11)
        pdf.set_text_color(*INDIGO)
        pdf.cell(width, 7, printable(f"{section:02d}  {text}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)

    if content.distribution:
        heading("Status distribution")
        top = max((d.count for d in content.distribution), default=0)
        bar_room = width - 70
        for item in content.distribution:
            pdf.cell(45, 6, printable(item.label))
            length = bar_room * item.count / top if top else 0
            y = pdf.get_y()
            if length:
                pdf.set_fill_color(69, 115, 219)
                pdf.rect(pdf.get_x(), y + 1.5, length, 3, style="F")
            pdf.set_x(pdf.l_margin + 45 + bar_room + 5)
            pdf.cell(20, 6, str(item.count), align="R", new_x="LMARGIN", new_y="NEXT")

    if content.facts:
        heading("Project status")
        for fact in content.facts:
            pdf.set_text_color(*GREY)
            pdf.cell(45, 6, printable(fact.label))
            pdf.set_text_color(*INDIGO)
            pdf.multi_cell(width - 45, 6, printable(fact.value or "-"))

    if summary:
        heading("Expert summary")
        pdf.multi_cell(width, 5, printable(summary))

    for table in content.tables:
        heading(table.heading)
        if not table.rows:
            pdf.set_text_color(*GREY)
            pdf.cell(width, 6, "Nothing in this reporting period.", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*INDIGO)
            continue
        first = width * (0.42 if len(table.columns) > 4 else 0.46)
        rest = (width - first) / (len(table.columns) - 1)
        widths = [first] + [rest] * (len(table.columns) - 1)
        pdf.set_font("Helvetica", style="B", size=8)
        pdf.set_fill_color(243, 244, 248)
        for column, w in zip(table.columns, widths, strict=True):
            pdf.cell(w, 7, printable(column), fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", size=8)
        for row in table.rows:
            for column, value, w in zip(table.columns, row, widths, strict=True):
                text = _day(value) if column in date_columns and value else value
                limit = int(w / 1.6)
                if len(text) > limit:
                    text = text[: limit - 1] + "..."
                pdf.cell(w, 6, printable(text), border="B")
            pdf.ln()
        if table.total_rows > len(table.rows):
            pdf.set_text_color(*GREY)
            pdf.cell(
                width,
                6,
                f"Showing {len(table.rows)} of {table.total_rows} rows.",
                new_x="LMARGIN",
                new_y="NEXT",
            )
            pdf.set_text_color(*INDIGO)
    return bytes(pdf.output())
