"""Modelli pydantic condivisi da core, provider, storage, worker e UI."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    index: int
    title: str = ""
    text: str
    has_uncertainty: bool = False


class ParseResult(BaseModel):
    text: str
    tokens_in: int
    tokens_out: int
    tokens_total: int
    chunk_count: int
    uncertainty_count: int
    llm_duration_ms: int
    provider: str
    model_version: str
    prompt_version: str


class RunStatus(StrEnum):
    QUEUED = "Queued"
    PROCESSING = "Processing"
    DONE = "Done"
    FAILED = "Failed"
    REJECTED = "Rejected"
    DUPLICATE = "Duplicate"


ACTIVE_STATUSES = {RunStatus.QUEUED, RunStatus.PROCESSING}


def new_run_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunRecord(BaseModel):
    """Schema unico della run, valido per SQLite (v1) e Table Storage (v2)."""

    run_id: str = Field(default_factory=new_run_id)
    session_id: str = ""
    requester_upn: str = ""
    status: RunStatus = RunStatus.QUEUED
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    llm_duration_ms: int | None = None

    input_type: str = "pdf"
    content_type: str | None = None
    output_mode: str = "documentazione"
    language: str = "it"
    model_id: str | None = None
    parent_run_id: str | None = None

    input_filename: str = ""
    input_hash: str | None = None
    input_size_bytes: int | None = None
    input_pages: int | None = None
    input_path: str | None = None
    input_manifest_ref: str | None = None
    output_path: str | None = None
    output_size_bytes: int | None = None

    raw_json_ref: str | None = None
    final_json_ref: str | None = None
    screenshots_ref: str | None = None
    output_dir_ref: str | None = None
    zip_ref: str | None = None

    provider: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_total: int | None = None
    unit_price_in: float | None = None
    unit_price_out: float | None = None
    cost_eur: float | None = None

    step1_provider: str | None = None
    step1_model: str | None = None
    step1_tokens_in: int | None = None
    step1_tokens_out: int | None = None
    step1_cost_eur: float | None = None

    step2_provider: str | None = None
    step2_model: str | None = None
    step2_tokens_in: int | None = None
    step2_tokens_out: int | None = None
    step2_cost_eur: float | None = None

    chunk_count: int | None = None
    uncertainty_count: int | None = None
    retry_count: int = 0
    error_message: str | None = None
    notified: bool = False


FRIENDLY_COLUMNS = [
    "requester_upn",
    "input_filename",
    "output_path",
    "status",
    "created_at",
    "completed_at",
]


class User(BaseModel):
    upn: str
    display_name: str
    is_admin: bool = False
