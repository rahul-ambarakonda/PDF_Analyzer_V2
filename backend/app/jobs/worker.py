"""Background worker that runs comparison jobs off the request thread.

CV work is CPU-bound but releases the GIL (numpy/scikit-image/PyMuPDF call into native code), so a
``ThreadPoolExecutor`` gives real parallelism without the memory cost of extra processes — the right
trade-off on a ~2 GB box. ``worker_concurrency`` defaults to 1; raise it on hosts with more vCPUs.

Each job's pair payloads (the uploaded PDF bytes) are passed in and released as soon as the pair is
processed, so only in-flight bytes sit in memory.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from comparator.config import Config

from ..services.comparison import compare_pair
from .models import Job, JobStatus, PairStatus
from .store import JobStore

log = logging.getLogger("app.worker")

# name -> (reference_bytes, candidate_bytes)
PairBytes = dict[str, tuple[bytes, bytes]]


class ComparisonWorker:
    def __init__(self, store: JobStore, config: Config, concurrency: int) -> None:
        self._store = store
        self._config = config
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, concurrency), thread_name_prefix="cmp")

    def submit(self, job: Job, pairs: PairBytes) -> None:
        self._executor.submit(self._run, job.id, pairs)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --- internal ---
    def _run(self, job_id: str, pairs: PairBytes) -> None:
        job = self._store.get(job_id)
        if job is None:  # evicted before it ran
            return
        with job.lock:
            job.status = JobStatus.RUNNING
            job.touch()
        try:
            for name, (ref_bytes, cand_bytes) in pairs.items():
                self._run_pair(job, name, ref_bytes, cand_bytes)
            with job.lock:
                job.status = JobStatus.COMPLETED
                job.touch()
        except Exception as exc:  # pragma: no cover - defensive; pair errors are caught below
            log.exception("job failed", extra={"extra_fields": {"job_id": job_id}})
            with job.lock:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.touch()

    def _run_pair(self, job: Job, name: str, ref_bytes: bytes, cand_bytes: bytes) -> None:
        pair = job.pairs[name]
        try:
            report, html = compare_pair(ref_bytes, cand_bytes, self._config)
            meta = report["meta"]
            counts = meta["counts_by_status"]
            pair.report = report
            pair.report_html = html
            pair.total_defects = meta["total_defects"]
            pair.defect = counts.get("defect", 0)
            pair.review = counts.get("review", 0)
            pair.quality_score = meta.get("quality_score")
            pair.status = PairStatus.DEFECT if pair.defect else PairStatus.CLEAN
        except Exception as exc:
            log.exception(
                "pair comparison failed",
                extra={"extra_fields": {"job_id": job.id, "pair": name}})
            pair.status = PairStatus.ERROR
            pair.error = str(exc)
        finally:
            job.touch()
