"""A published status report as a PDF, for the client portal download."""

from fpdf import FPDF

from app.client.schemas import ClientReportOut
from app.tasks.pdf_export import DATE, printable

HEALTH_LABEL = {"on_track": "On track", "at_risk": "At risk", "off_track": "Off track"}


class _ReportPdf(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=7)
        self.set_text_color(110)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def build_report_pdf(report: ClientReportOut) -> bytes:
    pdf = _ReportPdf(orientation="portrait", unit="mm", format="A4")
    pdf.set_title(printable(f"{report.project_name} - {report.title}"))
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", style="B", size=16)
    pdf.multi_cell(width, 8, printable(report.project_name))
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(width, 6, printable(report.title))
    pdf.ln(2)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(90)
    published = f"Published {report.published_at:{DATE}}"
    if report.published_by:
        published += f" by {report.published_by.name} ({report.published_by.role})"
    progress = f" Progress: {report.progress}%." if report.progress is not None else ""
    pdf.multi_cell(
        width,
        5,
        printable(f"Borek Solutions Group. Health: {HEALTH_LABEL[report.health]}.{progress}"),
    )
    pdf.multi_cell(width, 5, printable(f"{published}."))
    pdf.set_text_color(0)

    for heading, text in (
        ("Summary", report.summary),
        ("Achievements", report.achievements),
        ("Next steps", report.next_steps),
        ("Risks", report.risks),
    ):
        if not text:
            continue
        pdf.ln(4)
        pdf.set_font("Helvetica", style="B", size=11)
        pdf.multi_cell(width, 6, heading)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(width, 5, printable(text))
    return bytes(pdf.output())
