"""Job + result data structures held entirely in memory.

A ``Job`` owns one or more ``PairResult`` objects (one per matched reference/candidate filename).
Heavy payloads — the rendered ``report_html`` string and the structured ``report`` dict — live on
the ``PairResult`` and are evicted with the job (see ``store.py``) to bound memory on a small box.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PairStatus(str, Enum):
    PENDING = "pending"
    CLEAN = "clean"
    DEFECT = "defect"
    ERROR = "error"


@dataclass
class PairResult:
    name: str
    status: PairStatus = PairStatus.PENDING
    total_defects: int = 0
    defect: int = 0
    review: int = 0
    quality_score: Optional[int] = None  # category-weighted /100
    error: Optional[str] = None
    # Heavy, in-memory only; not serialized in list responses.
    report: Optional[dict] = None          # build_report() dict
    report_html: Optional[str] = None      # self-contained HTML (images inlined)

    def summary(self, report_url: Optional[str]) -> dict:
        data = {
            "name": self.name,
            "status": self.status.value,
            "total_defects": self.total_defects,
            "defect": self.defect,
            "review": self.review,
            "quality_score": self.quality_score,
        }
        if self.error:
            data["error"] = self.error
        if report_url and self.report_html is not None:
            data["report_url"] = report_url
        return data


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    pairs: dict[str, PairResult] = field(default_factory=dict)
    unmatched_reference: list[str] = field(default_factory=list)
    unmatched_candidate: list[str] = field(default_factory=list)
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)

    def touch(self) -> None:
        self.updated_at = time.time()
