"""Reading a task CSV (a Jira export or our own export) for the import (S2-31).

Pure functions: no database, no web layer. The file is turned into `ImportRow`s plus a list of
rows that cannot be used and a list of warnings. Matching users and statuses, and saving, is the
job of `importer.py`.
"""

import csv
import io
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from pydantic import ValidationError

from app.common.enums import EstimateUnit, TaskPriority
from app.common.validation import MAX_DATE, MIN_DATE
from app.tasks.details_schemas import LinkIn
from app.tasks.schemas import MAX_DESCRIPTION, MAX_ESTIMATE_BY_UNIT, MAX_LABELS
from app.tasks.transfer import unprotect_cell

MAX_IMPORT_ROWS = 5_000
MAX_TITLE = 300
MAX_LABEL = 30
MAX_EXTERNAL_KEY = 50
MAX_ATTACHMENT_NAME = 255
MAX_FIELD_SIZE = 1_000_000  # csv's default (128 KB) is too small for a very long description
UNKNOWN_USER = "unknown user"
HOURS_PER_WEEK = 40  # Jira's default working week

# Account ids look like 712020:07260689-abea-45e8-a0f6-da6dbe233dbb
_MENTION = re.compile(r"\[~accountid:([^\]\s]+)\]")
_JIRA_DATE = re.compile(
    r"^(\d{1,2})[/-]([A-Za-z]{3})[/-](\d{2}|\d{4})"  # Excel may turn 12/Oct/26 into 12-Oct-26
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?)?$"
)
# German Excel writes dates as 12.10.2026 or 12.10.2026 11:31 (day first).
_DOTTED_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
_SEPARATORS = (";", ",", "\t")

# Jira's priority names (including its older ones) -> ours. Our own names match as they are.
_PRIORITIES = {
    "highest": TaskPriority.HIGHEST,
    "blocker": TaskPriority.HIGHEST,
    "critical": TaskPriority.HIGHEST,
    "high": TaskPriority.HIGH,
    "major": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "normal": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
    "minor": TaskPriority.LOW,
    "lowest": TaskPriority.LOWEST,
    "trivial": TaskPriority.LOWEST,
}

# Every column the import reads (headers are compared ignoring case). The rest is reported as
# ignored, so nothing disappears silently.
_USED_COLUMNS = frozenset(
    {
        "summary",
        "issue key",
        "project key",
        "description",
        "status",
        "status category",
        "priority",
        "assignee",
        "assignee id",
        "assignee email",
        "reporter",
        "reporter id",
        "creator",
        "creator id",
        "watchers",
        "watchers id",
        "issue type",
        "parent key",
        "parent summary",
        "labels",
        "start date",
        "custom field (start date)",
        "due date",
        "original estimate",
        "estimate",
        "estimate unit",
        "created",
        "resolved",
        "comment",
        "attachment",
    }
)


class ImportFileError(Exception):
    """The whole file cannot be used (not a CSV, no Summary column, too many rows ...)."""


@dataclass
class Issue:
    """A problem with one row. `row` is the spreadsheet row number (the header is row 1)."""

    row: int
    external_key: str | None
    field: str | None
    message: str


@dataclass
class ParsedComment:
    author: str
    when: datetime | None
    body: str


@dataclass
class ParsedAttachment:
    name: str
    url: str


@dataclass
class ImportRow:
    row: int
    external_key: str | None
    project_key: str | None
    title: str
    description: str | None
    status: str | None
    status_category: str | None
    priority: TaskPriority
    assignee: str | None
    assignee_email: str | None
    labels: list[str]
    start_date: date | None
    due_date: date | None
    estimate_value: int | None
    estimate_unit: EstimateUnit | None
    created_at: datetime | None
    resolved_at: datetime | None
    comments: list[ParsedComment] = field(default_factory=list)
    attachments: list[ParsedAttachment] = field(default_factory=list)


@dataclass
class ParsedFile:
    rows: list[ImportRow] = field(default_factory=list)
    failures: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    total_rows: int = 0
    ignored_columns: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)  # distinct project keys, in file order


Warn = Callable[[str, str], None]  # (column, message)


# --- reading the file -------------------------------------------------------------------------


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM), else Windows-1252 as Excel on Windows saves it."""
    if not data.strip():
        raise ImportFileError("The file is empty.")
    if b"\x00" in data[:8192] or data[:2] == b"PK" or data[:4] == b"%PDF":
        raise ImportFileError("This is not a CSV text file. Export the tasks as CSV and try again.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError:
            return data.decode("latin-1")


def detect_separator(text: str) -> str:
    """The separator that appears most often in the header line (Jira: comma, our export and
    German Excel: semicolon, some tools: tab)."""
    header = text.split("\n", 1)[0]
    best = max(_SEPARATORS, key=lambda separator: header.count(separator))
    return best if header.count(best) else ","


def _norm(header: str) -> str:
    return " ".join(header.strip().casefold().split())


def read_table(text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """The header and the data rows as (spreadsheet row number, cells). Blank rows are dropped."""
    csv.field_size_limit(MAX_FIELD_SIZE)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=detect_separator(text))
    header: list[str] | None = None
    rows: list[tuple[int, list[str]]] = []
    try:
        for number, cells in enumerate(reader, start=1):
            if header is None:
                header = cells
            elif any(cell.strip() for cell in cells):
                if len(rows) >= MAX_IMPORT_ROWS:
                    raise ImportFileError(
                        f"The file has more than {MAX_IMPORT_ROWS} tasks. Split it and import "
                        "it in parts."
                    )
                rows.append((number, cells))
    except csv.Error as error:
        raise ImportFileError(f"The file could not be read as CSV: {error}") from None
    if header is None:
        raise ImportFileError("The file is empty.")
    return header, rows


class _Row:
    """One record, read by column name. A name can match several columns (Labels, Comment)."""

    def __init__(self, cells: list[str], index: dict[str, list[int]]) -> None:
        self._cells = cells
        self._index = index

    def cell(self, position: int) -> str:
        return self._cells[position].strip() if position < len(self._cells) else ""

    def all(self, name: str) -> list[str]:
        values = (self.cell(position) for position in self._index.get(name, ()))
        return [unprotect_cell(value) for value in values if value]

    def first(self, *names: str) -> str | None:
        """The first non-empty value of the first of these columns that has one."""
        for name in names:
            values = self.all(name)
            if values:
                return values[0]
        return None

    def pairs(self, name: str, id_name: str) -> list[tuple[str, str]]:
        """(name, id) from two column groups that belong together (Watchers, Watchers Id)."""
        positions = zip(self._index.get(name, ()), self._index.get(id_name, ()), strict=False)
        return [(self.cell(a), self.cell(b)) for a, b in positions if self.cell(a) and self.cell(b)]


# --- cleaning and converting values -----------------------------------------------------------


def clean_line(value: str) -> str:
    """One line of text: control characters removed, line breaks and tabs become spaces."""
    spaced = "".join(" " if char in "\r\n\t" else char for char in value)
    return " ".join(
        "".join(c for c in spaced if unicodedata.category(c) not in ("Cc", "Cs")).split()
    )


def clean_block(value: str) -> str:
    """Text with line breaks: control characters removed, Windows line breaks unified."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    kept = (c for c in value if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cs"))
    return "".join(kept).strip()


def replace_mentions(value: str, names: dict[str, str]) -> str:
    """`[~accountid:ID]` -> `@Name` (`@unknown user` when the file never names that account)."""
    return _MENTION.sub(lambda match: "@" + names.get(match.group(1), UNKNOWN_USER), value)


def parse_datetime(raw: str | None) -> datetime | None:
    """Jira's `12/Oct/26 11:31 AM`, or ISO. The file has no time zone: it is read as UTC."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        match = _JIRA_DATE.match(raw)
        if match:
            day, month_name, year, hour, minute, second, meridiem = match.groups()
            month = _MONTHS.get(month_name.lower())
            if month is None:
                return None
            hours = int(hour or 0)
            if meridiem:
                if not 1 <= hours <= 12:
                    return None
                hours = hours % 12 + (12 if meridiem.lower() == "pm" else 0)
            full_year = int(year) + (2000 if len(year) == 2 else 0)
            return datetime(
                full_year, month, int(day), hours, int(minute or 0), int(second or 0), tzinfo=UTC
            )
        dotted = _DOTTED_DATE.match(raw)
        if dotted:
            d, mo, y, h, mi, s = dotted.groups()
            return datetime(
                int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0), tzinfo=UTC
            )
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _day(raw: str | None, label: str, warn: Warn) -> date | None:
    """A date column: unreadable or out-of-range values are dropped with a warning."""
    if not raw:
        return None
    moment = parse_datetime(raw)
    if moment is None or not MIN_DATE <= moment.date() <= MAX_DATE:
        warn(label, f"The date '{raw[:30]}' is not valid; left empty.")
        return None
    return moment.date()


def estimate_from_seconds(seconds: int) -> tuple[tuple[int, EstimateUnit] | None, str | None]:
    """Jira's estimate in seconds -> (value, unit) within our caps, plus a warning when the
    number had to change. Whole hours if possible, else minutes, else weeks (rounded up)."""
    minutes = -(-seconds // 60)
    if minutes <= 0:
        return None, None
    if minutes % 60 == 0:
        hours = minutes // 60
        if hours <= MAX_ESTIMATE_BY_UNIT[EstimateUnit.HOURS]:
            return (hours, EstimateUnit.HOURS), None
        text, weeks = f"{hours} hours", -(-hours // HOURS_PER_WEEK)
    else:
        if minutes <= MAX_ESTIMATE_BY_UNIT[EstimateUnit.MINUTES]:
            return (minutes, EstimateUnit.MINUTES), None
        text, weeks = f"{minutes} minutes", -(-minutes // (HOURS_PER_WEEK * 60))
    if weeks <= MAX_ESTIMATE_BY_UNIT[EstimateUnit.WEEKS]:
        return (weeks, EstimateUnit.WEEKS), f"Estimate of {text} was rounded up to {weeks} weeks."
    return None, f"Estimate of {text} is above the limit; left empty."


def _estimate(row: _Row, warn: Warn) -> tuple[int | None, EstimateUnit | None]:
    """Our own `Estimate` + `Estimate unit`, or Jira's `Original estimate` in seconds."""
    own_value, own_unit = row.first("estimate"), row.first("estimate unit")
    if own_value or own_unit:
        try:
            unit = EstimateUnit((own_unit or "").strip().lower())
            value = int(own_value or "")
        except ValueError:
            warn("Estimate", "The estimate could not be read; left empty.")
            return None, None
        if not 0 < value <= MAX_ESTIMATE_BY_UNIT[unit]:
            warn(
                "Estimate",
                f"The estimate is out of range (1-{MAX_ESTIMATE_BY_UNIT[unit]} {unit.value}); "
                "left empty.",
            )
            return None, None
        return value, unit
    jira = row.first("original estimate")
    if not jira:
        return None, None
    if not jira.isdigit():
        warn("Estimate", f"The estimate '{jira[:30]}' could not be read; left empty.")
        return None, None
    converted, note = estimate_from_seconds(int(jira))
    if note:
        warn("Estimate", note)
    return converted if converted else (None, None)


def _priority(row: _Row, warn: Warn) -> TaskPriority:
    raw = row.first("priority")
    if not raw:
        return TaskPriority.MEDIUM
    found = _PRIORITIES.get(_norm(raw))
    if found is None:
        warn("Priority", f"Priority '{raw[:30]}' is unknown; set to medium.")
        return TaskPriority.MEDIUM
    return found


def _labels(row: _Row, warn: Warn) -> list[str]:
    raw = row.all("labels")
    issue_type = row.first("issue type")
    if issue_type and _norm(issue_type) != "task":  # nearly every Jira issue is a Task
        raw.append(issue_type)
    labels: list[str] = []
    seen: set[str] = set()
    for value in raw:
        label = clean_line(value)
        if len(label) > MAX_LABEL:
            label = label[:MAX_LABEL].rstrip()
            warn("Labels", f"The label '{label}' was cut to {MAX_LABEL} characters.")
        if label and label.casefold() not in seen:
            seen.add(label.casefold())
            labels.append(label)
    if len(labels) > MAX_LABELS:
        warn("Labels", f"Only the first {MAX_LABELS} labels were kept.")
        labels = labels[:MAX_LABELS]
    return labels


def _parse_comment(raw: str, names: dict[str, str]) -> ParsedComment | None:
    """Jira writes a comment as `date;account id;text` (the text may contain semicolons)."""
    parts = raw.split(";", 2)
    when = parse_datetime(parts[0]) if len(parts) == 3 else None
    if when is not None:
        author, body = names.get(parts[1].strip(), UNKNOWN_USER), parts[2]
    else:
        author, body = UNKNOWN_USER, raw
    body = clean_block(replace_mentions(body, names))
    return ParsedComment(author=author, when=when, body=body) if body else None


def _parse_attachment(raw: str) -> ParsedAttachment | None:
    """Jira writes an attachment as `date;id;file name;url`. Only http(s) links are kept."""
    parts = raw.split(";", 3)
    if len(parts) != 4:
        return None
    try:
        url = LinkIn(url=parts[3]).url
    except ValidationError:
        return None
    name = clean_line(parts[2])[:MAX_ATTACHMENT_NAME] or "attachment"
    return ParsedAttachment(name=name, url=url)


def _collect_names(row: _Row, names: dict[str, str]) -> None:
    """Learn account id -> display name from the columns that carry both."""
    for column in ("assignee", "reporter", "creator"):
        name, account = row.first(column), row.first(f"{column} id")
        if name and account:
            names[account] = clean_line(name)
    for name, account in row.pairs("watchers", "watchers id"):
        names[account] = clean_line(name)


def _description(row: _Row, names: dict[str, str], warn: Warn) -> str | None:
    """The text plus a footer for what has no field of its own (reporter, Jira parent)."""
    footer: list[str] = []
    reporter = row.first("reporter")
    if reporter:
        footer.append(f"Reporter in Jira: {clean_line(reporter)}")
    parent = " ".join(
        part for part in (row.first("parent key"), row.first("parent summary")) if part
    )
    if parent:
        footer.append(f"Jira parent: {clean_line(parent)}")
    suffix = ("\n\n---\n" + "\n".join(footer)) if footer else ""
    body = clean_block(replace_mentions(row.first("description") or "", names))
    if len(body) + len(suffix) > MAX_DESCRIPTION:
        body = body[: max(0, MAX_DESCRIPTION - len(suffix) - 1)].rstrip() + "…"
        warn("Description", f"The description was cut to {MAX_DESCRIPTION} characters.")
    return (body + suffix).strip() or None


def _build_row(number: int, row: _Row, names: dict[str, str], parsed: ParsedFile) -> None:
    key = clean_line(row.first("issue key") or "") or None

    def warn(column: str, message: str) -> None:
        parsed.warnings.append(Issue(number, key, column, message))

    def fail(column: str, message: str) -> None:
        parsed.failures.append(Issue(number, key, column, message))

    title = clean_line(replace_mentions(row.first("summary") or "", names))
    if not title:
        fail("Summary", "Title is required.")
        return
    if key and len(key) > MAX_EXTERNAL_KEY:
        fail("Issue key", f"The issue key is longer than {MAX_EXTERNAL_KEY} characters.")
        return
    if len(title) > MAX_TITLE:
        title = title[: MAX_TITLE - 1].rstrip() + "…"
        warn("Summary", f"The title was cut to {MAX_TITLE} characters.")

    start = _day(row.first("start date", "custom field (start date)"), "Start date", warn)
    due = _day(row.first("due date"), "Due date", warn)
    if start and due and due < start:
        warn("Due date", "The due date is before the start date; left empty.")
        due = None
    value, unit = _estimate(row, warn)

    created = parse_datetime(row.first("created"))
    if row.first("created") and (created is None or not MIN_DATE <= created.date() <= MAX_DATE):
        warn("Created", "The creation date is not valid; today is used.")
        created = None
    resolved = parse_datetime(row.first("resolved"))
    if resolved is not None and not MIN_DATE <= resolved.date() <= MAX_DATE:
        resolved = None

    comments = [c for raw in row.all("comment") if (c := _parse_comment(raw, names))]
    attachments: list[ParsedAttachment] = []
    for raw in row.all("attachment"):
        attachment = _parse_attachment(raw)
        if attachment is None:
            warn("Attachment", "An attachment link could not be read and was skipped.")
        else:
            attachments.append(attachment)

    assignee, email = row.first("assignee"), row.first("assignee email")
    if email is None and assignee and "@" in assignee:
        assignee, email = None, assignee
    project_key = clean_line(row.first("project key") or "") or None
    if project_key and project_key not in parsed.projects:
        parsed.projects.append(project_key)

    parsed.rows.append(
        ImportRow(
            row=number,
            external_key=key,
            project_key=project_key,
            title=title,
            description=_description(row, names, warn),
            status=clean_line(row.first("status") or "") or None,
            status_category=clean_line(row.first("status category") or "") or None,
            priority=_priority(row, warn),
            assignee=clean_line(assignee) if assignee else None,
            assignee_email=clean_line(email).lower() if email else None,
            labels=_labels(row, warn),
            start_date=start,
            due_date=due,
            estimate_value=value,
            estimate_unit=unit,
            created_at=created,
            resolved_at=resolved,
            comments=comments,
            attachments=attachments,
        )
    )


def parse_file(data: bytes, file_name: str | None = None) -> ParsedFile:
    """Read a Jira CSV export or our own export. Raises ImportFileError when the file as a
    whole cannot be used; rows that cannot be used are listed in `failures`."""
    if file_name is not None and not file_name.lower().endswith(".csv"):
        raise ImportFileError("Only .csv files can be imported.")
    header, records = read_table(decode_text(data))
    index: dict[str, list[int]] = {}
    for position, name in enumerate(header):
        index.setdefault(_norm(name), []).append(position)
    if "summary" not in index:
        raise ImportFileError(
            "The file has no 'Summary' column. In Jira, set the language to English and "
            "export with Export > CSV (all fields)."
        )
    rows = [(number, _Row(cells, index)) for number, cells in records]
    names: dict[str, str] = {}
    for _, row in rows:  # first pass: a comment can mention someone named only in a later row
        _collect_names(row, names)

    parsed = ParsedFile(total_rows=len(rows))
    parsed.ignored_columns = list(
        dict.fromkeys(
            name.strip() for name in header if name.strip() and _norm(name) not in _USED_COLUMNS
        )
    )
    for number, row in rows:
        _build_row(number, row, names, parsed)
    return parsed
