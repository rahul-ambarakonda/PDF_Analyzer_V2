"""API endpoints.

Flow: ``POST /api/v1/compare`` validates + pairs the uploads, creates a job, hands the PDF bytes to
the background worker, and returns ``202`` immediately. The frontend polls ``GET .../jobs/{id}`` and,
once a pair is done, fetches its structured JSON (``.../pairs/{name}``) or the rendered HTML report
(``.../report/{name}``).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from .. import __version__
from ..config import Settings, get_settings
from ..errors import ApiError
from ..jobs.models import PairResult
from ..jobs.store import JobStore
from ..jobs.worker import ComparisonWorker
from .schemas import (
    CompareAccepted,
    HealthResponse,
    JobResponse,
    PairSummary,
)

router = APIRouter()


def _store(request: Request) -> JobStore:
    return request.app.state.store


def _worker(request: Request) -> ComparisonWorker:
    return request.app.state.worker


def _pdf_uploads(files: list[UploadFile]) -> dict[str, UploadFile]:
    """Keep PDFs only, keyed by basename (last writer wins, matching legacy behaviour)."""
    out: dict[str, UploadFile] = {}
    for f in files:
        if f.filename and f.filename.lower().endswith(".pdf"):
            out[os.path.basename(f.filename)] = f
    return out


@router.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(version=__version__, env=settings.env)


@router.post("/api/v1/compare", response_model=CompareAccepted, status_code=202, tags=["compare"])
async def compare(
    request: Request,
    reference: list[UploadFile] = File(..., description="Reference (correct) PDFs"),
    candidate: list[UploadFile] = File(..., description="Candidate (Creo) PDFs"),
) -> JSONResponse:
    settings: Settings = get_settings()
    store = _store(request)
    worker = _worker(request)

    if store.pending_count() >= settings.max_pending_jobs:
        raise ApiError(503, "Server busy; too many jobs in progress. Retry shortly.")

    ref_files = _pdf_uploads(reference)
    cand_files = _pdf_uploads(candidate)
    if not ref_files or not cand_files:
        raise ApiError(400, "Upload at least one reference PDF and one candidate PDF.")
    if (len(ref_files) > settings.max_files_per_side
            or len(cand_files) > settings.max_files_per_side):
        raise ApiError(400, f"Too many files (max {settings.max_files_per_side} per side).")

    matched = sorted(set(ref_files) & set(cand_files))
    if not matched:
        raise ApiError(400, "No filenames match between the reference and candidate sets.")
    if len(matched) > settings.max_pairs:
        raise ApiError(400, f"Too many matched pairs (max {settings.max_pairs}).")

    # Read bytes into memory, enforcing per-file and total size caps.
    pairs_bytes: dict[str, tuple[bytes, bytes]] = {}
    total = 0
    for name in matched:
        ref_bytes = await ref_files[name].read()
        cand_bytes = await cand_files[name].read()
        for blob in (ref_bytes, cand_bytes):
            if len(blob) > settings.max_file_bytes:
                raise ApiError(413, f"'{name}' exceeds the {settings.max_file_bytes}-byte limit.")
            total += len(blob)
        if total > settings.max_upload_bytes:
            raise ApiError(413, "Upload exceeds the total size limit.")
        pairs_bytes[name] = (ref_bytes, cand_bytes)

    job = store.create()
    for name in matched:
        job.pairs[name] = PairResult(name=name)
    job.unmatched_reference = sorted(set(ref_files) - set(cand_files))
    job.unmatched_candidate = sorted(set(cand_files) - set(ref_files))

    # Snapshot the accepted ("queued") response before handing off — the worker may start and
    # flip the status to "running" before this returns.
    body = CompareAccepted(
        job_id=job.id,
        status=job.status.value,
        pair_count=len(matched),
        unmatched_reference=job.unmatched_reference,
        unmatched_candidate=job.unmatched_candidate,
    ).model_dump()
    worker.submit(job, pairs_bytes)
    return JSONResponse(status_code=202, content=body)


@router.get("/api/v1/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
async def get_job(request: Request, job_id: str) -> JobResponse:
    job = _store(request).get(job_id)
    if job is None:
        raise ApiError(404, "Job not found or expired.")
    pairs = [
        PairSummary(**pr.summary(f"/api/v1/jobs/{job.id}/report/{pr.name}"))
        for pr in job.pairs.values()
    ]
    return JobResponse(
        job_id=job.id,
        status=job.status.value,
        created_at=job.created_at,
        updated_at=job.updated_at,
        pairs=pairs,
        unmatched_reference=job.unmatched_reference,
        unmatched_candidate=job.unmatched_candidate,
        error=job.error,
    )


@router.get("/api/v1/jobs/{job_id}/pairs/{name:path}", tags=["jobs"])
async def get_pair_report(request: Request, job_id: str, name: str) -> JSONResponse:
    pair = _lookup_pair(request, job_id, name)
    if pair.report is None:
        raise ApiError(409, "Report not ready yet.")
    return JSONResponse(content=pair.report)


@router.get("/api/v1/jobs/{job_id}/report/{name:path}", response_class=HTMLResponse, tags=["jobs"])
async def get_pair_html(request: Request, job_id: str, name: str) -> HTMLResponse:
    pair = _lookup_pair(request, job_id, name)
    if pair.report_html is None:
        raise ApiError(409, "Report not ready yet.")
    return HTMLResponse(content=pair.report_html)


def _lookup_pair(request: Request, job_id: str, name: str) -> PairResult:
    job = _store(request).get(job_id)
    if job is None:
        raise ApiError(404, "Job not found or expired.")
    pair = job.pairs.get(name)
    if pair is None:
        raise ApiError(404, "Pair not found in this job.")
    return pair
