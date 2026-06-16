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
from .report import build_report, render_html, write_json


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
        return build_report(defects, meta)
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
