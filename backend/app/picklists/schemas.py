import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.validation import clean_text


def _value(value: str | None) -> str | None:
    return None if value is None else clean_text(value, label="Value")


class PicklistValueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=100)

    _clean = field_validator("value")(_value)


class PicklistValueUpdate(BaseModel):
    """Send `version` plus what changes. `is_active: false` hides the value from new choices;
    what was saved with it stays."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    value: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=1, le=10_000)
    is_active: bool | None = None

    _clean = field_validator("value")(_value)

    @model_validator(mode="after")
    def _not_null(self) -> Self:
        for field in ("value", "position", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        return self


class PicklistValueOut(BaseModel):
    id: uuid.UUID | None = Field(description="Null on protected lists.")
    value: str
    position: int
    is_active: bool
    version: int | None


class PicklistOut(BaseModel):
    key: str
    label: str
    protected: bool = Field(description="Workflow values from the system; cannot be changed.")
    values: list[PicklistValueOut]
