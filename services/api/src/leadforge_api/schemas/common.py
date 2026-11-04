from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000


class ApiModel(BaseModel):
    """Base for response models: built from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    """Base for request bodies: unknown fields (e.g. organization_id) are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Page size")] = 25,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET, description="Rows to skip")] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody = Field(...)
