"""Thread-safe in-memory job store with TTL + max-count eviction.

This is the single source of truth for job state and is intentionally process-local: it works
because the API runs as one Uvicorn worker. Scaling to multiple processes/instances requires a
shared store (Redis) and shared artifact storage (S3) — see README "Scaling".

Eviction keeps the box from OOMing on accumulated base64-inlined HTML reports: terminal jobs older
than ``ttl_seconds`` are dropped, and the store never retains more than ``max_jobs`` (oldest
terminal jobs go first).
"""

from __future__ import annotations

import threading
import time
import uuid

from .models import Job, JobStatus


class JobStore:
    def __init__(self, ttl_seconds: int, max_jobs: int) -> None:
        self._ttl = ttl_seconds
        self._max = max_jobs
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(id=uuid.uuid4().hex[:16])
        with self._lock:
            self._jobs[job.id] = job
            self._evict_locked()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._evict_locked()
            return self._jobs.get(job_id)

    def pending_count(self) -> int:
        with self._lock:
            return sum(
                1 for j in self._jobs.values()
                if j.status in (JobStatus.QUEUED, JobStatus.RUNNING)
            )

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    # --- internal ---
    def _evict_locked(self) -> None:
        now = time.time()
        # 1. TTL: drop terminal jobs whose results have aged out.
        expired = [
            jid for jid, job in self._jobs.items()
            if job.is_terminal and (now - job.updated_at) > self._ttl
        ]
        for jid in expired:
            del self._jobs[jid]
        # 2. Hard cap: if still over the limit, drop oldest terminal jobs first.
        if len(self._jobs) > self._max:
            terminal = sorted(
                (j for j in self._jobs.values() if j.is_terminal),
                key=lambda j: j.updated_at,
            )
            for job in terminal:
                if len(self._jobs) <= self._max:
                    break
                del self._jobs[job.id]
