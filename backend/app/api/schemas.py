"""Pydantic response models — the stable contract consumed by the frontend."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    env: str


class PairSummary(BaseModel):
    name: str
    status: str                      # pending | clean | defect | error
    total_defects: int = 0
    defect: int = 0
    review: int = 0
    quality_score: Optional[int] = None  # category-weighted /100
    error: Optional[str] = None
    report_url: Optional[str] = None  # present once an HTML report exists


class CompareAccepted(BaseModel):
    job_id: str
    status: str                      # queued
    pair_count: int
    unmatched_reference: list[str] = []
    unmatched_candidate: list[str] = []


class JobResponse(BaseModel):
    job_id: str
    status: str                      # queued | running | completed | failed
    created_at: float
    updated_at: float
    pairs: list[PairSummary] = []
    unmatched_reference: list[str] = []
    unmatched_candidate: list[str] = []
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
