"""FastAPI application for the local DocRunr public API."""

from __future__ import annotations

import json
import secrets
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from docrunr_runtime import (
    StorageBackend,
    create_storage,
    file_suffix_for_upload,
    input_relative_path,
    is_allowed_upload_suffix,
    job_payload_bytes,
    new_job_id,
    safe_client_filename,
)

from docrunr_api.broker import BrokerBridge
from docrunr_api.config import ApiSettings
from docrunr_api.models import (
    ApiErrorDto,
    ApiErrorEnvelopeDto,
    EmbeddingsData,
    EmbeddingsResponse,
    JobDto,
    JobListData,
    JobListResponse,
    JobResponse,
    JobResultData,
    JobResultResponse,
    JobState,
    LlmTransform,
    ProfilesData,
    ProfilesResponse,
    ResultAvailability,
    SubmitDocumentData,
    SubmitDocumentResponse,
)
from docrunr_api.profiles import LlmProfileClient, ProfilesUnavailable
from docrunr_api.repository import JobRepository

ERROR_RESPONSES = {
    400: {"model": ApiErrorEnvelopeDto, "description": "VALIDATION_ERROR"},
    401: {"model": ApiErrorEnvelopeDto, "description": "UNAUTHORIZED"},
    403: {"model": ApiErrorEnvelopeDto, "description": "FORBIDDEN"},
    404: {"model": ApiErrorEnvelopeDto, "description": "NOT_FOUND"},
    409: {"model": ApiErrorEnvelopeDto, "description": "JOB_NOT_READY"},
    413: {"model": ApiErrorEnvelopeDto, "description": "PAYLOAD_TOO_LARGE"},
    503: {"model": ApiErrorEnvelopeDto, "description": "Service unavailable"},
}


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def create_app(
    settings: ApiSettings | None = None,
    *,
    repository: JobRepository | None = None,
    broker: BrokerBridge | None = None,
    storage: StorageBackend | None = None,
    profiles: LlmProfileClient | None = None,
) -> FastAPI:
    cfg = settings or ApiSettings()
    repo = repository or JobRepository(cfg.api_db_path)
    store = storage or create_storage(cfg)
    bridge = broker or BrokerBridge(cfg, repo)
    profile_client = profiles or LlmProfileClient(cfg)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        repo.initialize()
        bridge.start()
        try:
            yield
        finally:
            bridge.stop()

    app = FastAPI(
        title="DocRunr Public API",
        description=(
            "Local API for document extraction and optional embedding generation. "
            "Use a Bearer token when API_KEY is configured."
        ),
        version="0.1.2",
        docs_url="/",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    security = HTTPBearer(auto_error=False, description="Optional local DocRunr API key")

    async def authorize(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    ) -> None:
        if not cfg.api_key:
            return
        if (
            credentials is None
            or credentials.scheme.casefold() != "bearer"
            or not secrets.compare_digest(credentials.credentials, cfg.api_key)
        ):
            raise ApiProblem(401, "UNAUTHORIZED", "Missing or invalid API key")

    @app.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem) -> JSONResponse:
        return _error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        message = str(first.get("msg", "Invalid request"))
        return _error_response(400, "VALIDATION_ERROR", message)

    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        ready = repo.healthy() and bridge.ready
        return JSONResponse(
            {"status": "ok" if ready else "degraded", "rabbitmq": bridge.ready},
            status_code=200 if ready else 503,
        )

    @app.post(
        "/api/v1/documents",
        response_model=SubmitDocumentResponse,
        status_code=201,
        responses={key: value for key, value in ERROR_RESPONSES.items() if key != 404},
        operation_id="PublicApiController_submitDocument",
        summary="Upload document",
        tags=["Documents"],
    )
    async def submit_document(
        file: Annotated[UploadFile, File(description="Document to process.")],
        llm_profile: Annotated[
            str | None,
            Form(description="Optional LiteLLM embedding profile."),
        ] = None,
        _authorized: Annotated[None, Depends(authorize)] = None,
    ) -> SubmitDocumentResponse:
        filename = safe_client_filename(file.filename or "unknown")
        suffix = file_suffix_for_upload(filename)
        if not suffix or not is_allowed_upload_suffix(suffix):
            raise ApiProblem(400, "VALIDATION_ERROR", "Unsupported or missing file extension")
        profile = (llm_profile or "").strip() or None
        if profile:
            try:
                allowed = await profile_client.list_profiles()
            except ProfilesUnavailable as exc:
                raise ApiProblem(503, "LITELLM_UNAVAILABLE", str(exc)) from exc
            if profile not in allowed:
                raise ApiProblem(400, "VALIDATION_ERROR", "Unknown llm_profile")

        job_id = new_job_id()
        source_path = input_relative_path(job_id, suffix)
        temp_path, size = await _stage_upload(file, cfg.api_max_upload_bytes, suffix)
        if size == 0:
            temp_path.unlink(missing_ok=True)
            raise ApiProblem(400, "VALIDATION_ERROR", "Empty file")
        try:
            store.write(temp_path, source_path)
        except Exception as exc:
            raise ApiProblem(503, "STORAGE_UNAVAILABLE", "Could not store upload") from exc
        finally:
            temp_path.unlink(missing_ok=True)

        body = job_payload_bytes(
            job_id,
            filename,
            source_path,
            llm_profile=profile or "",
        )
        try:
            repo.create_job(
                job_id=job_id,
                file_name=filename,
                file_size=size,
                content_type=file.content_type,
                source_path=source_path,
                priority=0,
                llm_profile=profile,
                body=body,
            )
        except Exception:
            store.delete(source_path)
            raise
        if not bridge.wait_published(job_id):
            raise ApiProblem(503, "QUEUE_UNAVAILABLE", "Job queue is unavailable")
        return SubmitDocumentResponse(data=SubmitDocumentData(job_id=job_id))

    @app.get(
        "/api/v1/jobs",
        response_model=JobListResponse,
        responses={key: ERROR_RESPONSES[key] for key in (400, 401, 403)},
        operation_id="PublicApiController_listJobs",
        summary="List jobs",
        tags=["Jobs"],
    )
    async def list_jobs(
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        state: JobState | None = None,
        _authorized: Annotated[None, Depends(authorize)] = None,
    ) -> JobListResponse:
        rows, has_more = repo.list_jobs(
            limit=limit,
            offset=offset,
            state=state.value if state else None,
        )
        return JobListResponse(
            data=JobListData(items=[_job_dto(row) for row in rows], has_more=has_more)
        )

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=JobResponse,
        responses={key: ERROR_RESPONSES[key] for key in (401, 403, 404)},
        operation_id="PublicApiController_getJob",
        summary="Get job",
        tags=["Jobs"],
    )
    async def get_job(
        job_id: str,
        _authorized: Annotated[None, Depends(authorize)] = None,
    ) -> JobResponse:
        row = repo.get_job(job_id)
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Job not found")
        return JobResponse(data=_job_dto(row))

    @app.get(
        "/api/v1/jobs/{job_id}/result",
        response_model=JobResultResponse,
        responses=ERROR_RESPONSES,
        operation_id="PublicApiController_getJobResult",
        summary="Download job result",
        tags=["Jobs"],
    )
    async def get_job_result(
        job_id: str,
        output_format: Annotated[
            Literal["json", "markdown", "embeddings"],
            Query(alias="format"),
        ] = "json",
        _authorized: Annotated[None, Depends(authorize)] = None,
    ) -> Any:
        row = repo.get_job(job_id)
        if row is None:
            raise ApiProblem(404, "NOT_FOUND", "Job not found")
        if output_format == "embeddings":
            path = row.get("llm_artifact_path")
        elif output_format == "markdown":
            path = row.get("markdown_path")
        else:
            path = row.get("chunks_path")
        if not path:
            raise ApiProblem(409, "JOB_NOT_READY", "Job result is not available yet")
        content = _read_artifact(store, str(path))
        if output_format == "markdown":
            return Response(content=content, media_type="text/markdown; charset=utf-8")
        try:
            parsed = json.loads(content)
        except ValueError as exc:
            raise ApiProblem(503, "STORAGE_UNAVAILABLE", "Stored result is invalid") from exc
        if output_format == "embeddings":
            return EmbeddingsResponse(data=EmbeddingsData(job_id=job_id, result=parsed))
        return JobResultResponse(
            data=JobResultData(job_id=job_id, state="succeeded", result=parsed)
        )

    @app.get(
        "/api/v1/llm/profiles",
        response_model=ProfilesResponse,
        responses={key: ERROR_RESPONSES[key] for key in (401, 403, 503)},
        operation_id="PublicLlmProfilesController_listProfiles",
        summary="List LLM profiles",
        tags=["LLM"],
    )
    async def list_profiles(
        _authorized: Annotated[None, Depends(authorize)] = None,
    ) -> ProfilesResponse:
        try:
            names = await profile_client.list_profiles()
        except ProfilesUnavailable as exc:
            raise ApiProblem(503, "LITELLM_UNAVAILABLE", str(exc)) from exc
        return ProfilesResponse(data=ProfilesData(profiles=names))

    return app


async def _stage_upload(file: UploadFile, limit: int, suffix: str) -> tuple[Path, int]:
    size = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as staged:
        path = Path(staged.name)
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                path.unlink(missing_ok=True)
                raise ApiProblem(413, "PAYLOAD_TOO_LARGE", "Upload exceeds configured size limit")
            staged.write(chunk)
    return path, size


def _read_artifact(storage: StorageBackend, path: str) -> bytes:
    try:
        local = storage.read(path)
        return local.read_bytes()
    except FileNotFoundError as exc:
        raise ApiProblem(409, "JOB_NOT_READY", "Job result is not available yet") from exc
    finally:
        if "local" in locals():
            storage.cleanup(local)


def _job_dto(row: dict[str, Any]) -> JobDto:
    profile = row.get("llm_profile")
    llm = None
    if profile:
        llm = LlmTransform(
            profile=str(profile),
            state=row.get("llm_state") or "queued",
            provider=row.get("llm_provider"),
            artifact_available=bool(row.get("llm_artifact_path")),
            chunk_count=row.get("llm_chunk_count"),
            vector_count=row.get("llm_vector_count"),
            error_message=row.get("llm_error_message"),
            completed_at=row.get("llm_completed_at"),
        )
    return JobDto(
        job_id=row["job_id"],
        state=row["state"],
        file_name=row["file_name"],
        file_size=row.get("file_size"),
        content_type=row.get("content_type"),
        tokens_used=row.get("tokens_used"),
        chars_used=row.get("chars_used"),
        chunk_count=row.get("chunk_count"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        error_message=row.get("error_message"),
        result=ResultAvailability(available=bool(row.get("chunks_path"))),
        llm_transform=llm,
    )


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    envelope = ApiErrorEnvelopeDto(error=ApiErrorDto(code=code, message=message, status=status))
    return JSONResponse(envelope.model_dump(), status_code=status)
