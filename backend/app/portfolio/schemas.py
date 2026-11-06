import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.common.enums import ProjectStatus, RagStatus
from app.finance.schemas import FinanceOut
from app.organisations.schemas import OrganisationBrief, PersonBrief
from app.projects.schemas import TaskSummary

PortfolioSort = Literal["code", "name", "target_end_date", "-code", "-name", "-target_end_date"]


class PortfolioProject(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: ProjectStatus
    start_date: date | None
    target_end_date: date | None
    client_organisation: OrganisationBrief | None
    leads: list[PersonBrief]
    member_count: int
    tasks: TaskSummary
    rag: RagStatus | None = Field(description="From the newest published status report.")
    rag_date: date | None = Field(description="The date of that report.")
    finance: FinanceOut | None = Field(description="Empty until money is entered.")


class PortfolioOut(BaseModel):
    items: list[PortfolioProject]
    total: int = Field(description="Projects matching the filters.")
    page: int
    page_size: int
    by_status: dict[str, int] = Field(description="Matching projects per status (all pages).")
    by_rag: dict[str, int] = Field(
        description="Matching projects per RAG, except cancelled ones; `none` = no report yet."
    )
    summary: TaskSummary = Field(description="Tasks of all matching projects except cancelled.")


class AccessProject(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    project_role: str = Field(description="project_lead, developer or account_manager.")
    source: str = Field(description="invitation, task_assignment or client_assignment.")


class AccessPerson(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    is_active: bool
    projects: list[AccessProject]


class AccessOverviewOut(BaseModel):
    items: list[AccessPerson]
    total: int
    page: int
    page_size: int
