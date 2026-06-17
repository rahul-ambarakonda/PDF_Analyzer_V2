"""Comparison pipeline shared by the CLI and the web UI.

Keeps a single code path: ``run_comparison`` produces the report dict for one PDF pair;
``write_reports`` persists ``report.json`` + ``report.html``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import fitz

from .config import Config
from .detect import analyze_page
from .normalize import Normalizer
from .render_compare import RenderComparer
from .report import build_report, page_quality_score, render_html, write_json


def run_comparison(reference: str, candidate: str, config: Config) -> dict:
    """Compare a single reference/candidate PDF pair and return the report dict."""
    normalizer = Normalizer(config)
    comparer = RenderComparer(config)
    ref_doc = fitz.open(reference)
    cand_doc = fitz.open(candidate)
    try:
        page_count = min(len(ref_doc), len(cand_doc))
        defects = []
        for i in range(page_count):
            defects.extend(analyze_page(
                i + 1, ref_doc[i], cand_doc[i], normalizer, comparer, config))
        meta = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reference": Path(reference).name,
            "candidate": Path(candidate).name,
            "pages_compared": page_count,
            "page_count_mismatch": len(ref_doc) != len(cand_doc),
        }
        report = build_report(defects, meta)
        # Category-weighted quality score, averaged across compared pages (reuses the same
        # scoring as the HTML scoreboard so the JSON/API and HTML never diverge).
        page_scores = []
        for i in range(page_count):
            rect = cand_doc[i].rect
            page_records = [d for d in report["defects"] if d["page"] == i + 1]
            page_scores.append(page_quality_score(page_records, rect.width, rect.height))
        report["meta"]["quality_score"] = (
            round(sum(page_scores) / len(page_scores)) if page_scores else 100)
        return report
    finally:
        ref_doc.close()
        cand_doc.close()


def write_reports(report: dict, candidate: str, config: Config, out_dir: str | Path) -> tuple[Path, Path]:
    """Write report.json + report.html into ``out_dir``; return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report.json"
    html_path = out / "report.html"
    write_json(report, json_path)
    cand_doc = fitz.open(candidate)
    try:
        render_html(report, cand_doc, html_path, config)
    finally:
        cand_doc.close()
    return json_path, html_path
