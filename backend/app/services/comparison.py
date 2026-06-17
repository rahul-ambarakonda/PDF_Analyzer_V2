"""Bridge between the in-memory job worker and the comparator pipeline.

The pipeline (``comparator.pipeline``) reads/writes files, so each pair is materialised into a
short-lived temp directory, compared, then read back into memory and the directory deleted. After
this returns, nothing for the pair remains on disk — the report dict + HTML string are held by the
job store in RAM (matches the "results in memory" requirement).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from comparator.config import Config
from comparator.pipeline import run_comparison, write_reports


def compare_pair(reference_pdf: bytes, candidate_pdf: bytes, config: Config) -> tuple[dict, str]:
    """Compare one reference/candidate PDF pair.

    Returns ``(report_dict, report_html)`` where ``report_dict`` is the structured
    ``build_report`` output and ``report_html`` is the self-contained (image-inlined) HTML page.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="comparator_pair_"))
    try:
        ref_path = work_dir / "reference.pdf"
        cand_path = work_dir / "candidate.pdf"
        ref_path.write_bytes(reference_pdf)
        cand_path.write_bytes(candidate_pdf)

        report = run_comparison(str(ref_path), str(cand_path), config)
        _, html_path = write_reports(report, str(cand_path), config, work_dir)
        report_html = html_path.read_text(encoding="utf-8")
        return report, report_html
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
