"""PDF export of the person access matrix (Administrator handoff 09): the same people, order
and fields as the matrix, one row per person with their projects."""

from collections.abc import Sequence
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.portfolio.schemas import AccessPerson
from app.tasks.pdf_export import ENCODING, printable

COLUMNS = ("Name", "Email", "Role", "Active", "Projects")
# Millimetres on landscape A4 (277 mm for the table).
WIDTHS = (45, 62, 30, 14, 126)
ROLE_LABELS = {
    "pm": "Project Manager",
    "developer": "Developer",
    "manager": "Manager",
    "account_manager": "Account Manager",
    "admin": "Administrator",
    "client": "Client contact",
}
PROJECT_ROLES = {
    "project_lead": "lead",
    "developer": "member",
    "account_manager": "account manager",
    "client_contact": "client contact",
}


def person_row(person: AccessPerson) -> list[str]:
    projects = "; ".join(
        f"{p.project_code} {p.project_name} ({PROJECT_ROLES.get(p.project_role, p.project_role)})"
        for p in person.projects
    )
    return [
        person.name,
        person.email,
        ROLE_LABELS.get(person.role, person.role),
        "yes" if person.is_active else "no",
        projects,
    ]


class _AccessPdf(FPDF):
    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("Helvetica", size=7)
        self.set_text_color(110)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def build_access_pdf(
    people: Sequence[AccessPerson], *, filters: Sequence[str], exported_at: datetime
) -> bytes:
    pdf = _AccessPdf(orientation="L", unit="mm", format="A4")
    pdf.core_fonts_encoding = ENCODING
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_title("Person access")
    pdf.set_creator("Borek PM Hub")
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Person access", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(80)
    count = f"{len(people)} " + ("person" if len(people) == 1 else "people")
    stamp = exported_at.strftime("%d.%m.%Y %H:%M UTC")
    pdf.cell(0, 5, printable(f"Exported {stamp}  |  {count}"), new_x="LMARGIN", new_y="NEXT")
    scope = "; ".join(filters) if filters else "none (everyone in scope)"
    pdf.multi_cell(0, 5, printable(f"Filters: {scope}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(2)

    pdf.set_font("Helvetica", size=8)
    if not people:
        pdf.cell(0, 6, "No people match these filters.")
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
        for person in people:
            row = table.row()
            for value in person_row(person):
                row.cell(printable(value))
    return bytes(pdf.output())
