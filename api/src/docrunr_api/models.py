"""Public API response models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class JobState(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApiErrorDto(BaseModel):
    code: str
    message: str
    status: int


class ApiErrorEnvelopeDto(BaseModel):
    error: ApiErrorDto


class SubmitDocumentData(BaseModel):
    job_id: str
    state: Literal["queued"] = "queued"


class SubmitDocumentResponse(BaseModel):
    data: SubmitDocumentData


class ResultAvailability(BaseModel):
    available: bool


class LlmTransform(BaseModel):
    requested: Literal[True] = True
    profile: str
    state: Literal["queued", "succeeded", "failed"]
    provider: str | None = None
    artifact_available: bool
    chunk_count: int | None = None
    vector_count: int | None = None
    error_message: str | None = None
    completed_at: datetime | None = None


class JobDto(BaseModel):
    job_id: str
    state: JobState
    file_name: str
    file_size: int | None = None
    content_type: str | None = None
    tokens_used: int | None = None
    chars_used: int | None = None
    chunk_count: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result: ResultAvailability
    llm_transform: LlmTransform | None = None


class JobResponse(BaseModel):
    data: JobDto


class JobListData(BaseModel):
    items: list[JobDto]
    has_more: bool


class JobListResponse(BaseModel):
    data: JobListData


class JobResultData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_id: str
    state: Literal["succeeded"] = "succeeded"
    result: dict[str, Any]


class JobResultResponse(BaseModel):
    data: JobResultData


class EmbeddingsData(BaseModel):
    job_id: str
    result: dict[str, Any]


class EmbeddingsResponse(BaseModel):
    data: EmbeddingsData


class ProfilesData(BaseModel):
    profiles: list[str]


class ProfilesResponse(BaseModel):
    data: ProfilesData
