"""Shared input checks. Every free-text field and paging parameter goes through these."""

import unicodedata
from datetime import date
from typing import Annotated

from fastapi import Query

MAX_PAGE = 100_000
MAX_PAGE_SIZE = 200
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)

PageParam = Annotated[int, Query(ge=1, le=MAX_PAGE)]
PageSizeParam = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]

_ALLOWED_CONTROL = {"\n", "\r", "\t"}


def has_control_chars(value: str, *, multiline: bool = False) -> bool:
    """True for NUL and other control characters (Postgres rejects NUL with a 500)."""
    for char in value:
        if unicodedata.category(char) in ("Cc", "Cs") and not (
            multiline and char in _ALLOWED_CONTROL
        ):
            return True
    return False


def clean_text(value: str, *, label: str = "Value", multiline: bool = False) -> str:
    """Strip, reject blank text and control characters."""
    value = value.strip()
    if not value:
        raise ValueError(f"{label} is required.")
    if has_control_chars(value, multiline=multiline):
        raise ValueError(f"{label} contains characters that are not allowed.")
    return value


def clean_optional_text(
    value: str | None, *, max_length: int, label: str = "Value", multiline: bool = True
) -> str | None:
    """Like clean_text, but blank becomes None and the length is checked after stripping."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if has_control_chars(value, multiline=multiline):
        raise ValueError(f"{label} contains characters that are not allowed.")
    if len(value) > max_length:
        raise ValueError(f"{label} can have at most {max_length} characters.")
    return value


def check_date(value: date | None, label: str) -> date | None:
    if value is not None and not MIN_DATE <= value <= MAX_DATE:
        raise ValueError(f"{label} must be between {MIN_DATE.year} and {MAX_DATE.year}.")
    return value


def like_escape(text: str) -> str:
    """Make %, _ and the escape character itself literal in a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
