"""Report generation (SPEC §5 / §6 ``report.py``).

Emits a deterministic ``report.json`` (stable ordering + ids for golden snapshots) and a
human-readable ``report.html`` rendered in the **v1 dashboard format**: stat cards, the
13-category Compliance Audit Matrix, the Drawing Quality Scoreboard (weighted /100 score),
and a per-page breakdown with the annotated candidate raster and collapsible category cards.

The HTML keeps the legacy look while surfacing the new issue schema (``zone`` / ``cause`` /
``fix`` / ``ref_text`` -> ``cand_text``) inside each failed category's detail list. The
machine-readable ``report.json`` is the new SPEC §5 schema.
"""

from __future__ import annotations

import base64
import io
import json
import re
from datetime import datetime
from pathlib import Path

import fitz
from jinja2 import Template
from PIL import Image, ImageDraw, ImageFont

from .config import Config
from .detect import Defect

# Stable class ordering for deterministic output + box colors (RGB).
CLASS_ORDER = [
    "missing_text", "missing_annotation", "text_overlap",
    "text_misplacement", "font_glyph_corruption",
]
CLASS_COLOR = {
    "missing_text": (239, 68, 68),          # red
    "missing_annotation": (217, 70, 239),   # magenta
    "text_overlap": (249, 115, 22),         # orange
    "text_misplacement": (59, 130, 246),    # blue
    "font_glyph_corruption": (245, 158, 11),  # amber
}
_REPORT_MAX_DIM = 2200  # cap raster size in the HTML report


def _defect_sort_key(d: Defect):
    bbox = d.bbox_cand or d.bbox_ref or (0, 0, 0, 0)
    cls_rank = CLASS_ORDER.index(d.defect_class) if d.defect_class in CLASS_ORDER else 99
    return (d.page, round(bbox[1], 1), round(bbox[0], 1), cls_rank, d.cand_text or d.ref_text or "")


def build_report(defects: list[Defect], meta: dict) -> dict:
    ordered = sorted(defects, key=_defect_sort_key)
    records = []
    for idx, d in enumerate(ordered, start=1):
        records.append({
            "id": f"D-{idx:03d}",
            "page": d.page,
            "zone": d.zone,
            "class": d.defect_class,
            "severity": d.severity,
            "confidence": d.confidence,
            "status": d.status,
            "ref_text": d.ref_text,
            "cand_text": d.cand_text,
            "bbox_ref": [round(v, 2) for v in d.bbox_ref] if d.bbox_ref else None,
            "bbox_cand": [round(v, 2) for v in d.bbox_cand] if d.bbox_cand else None,
            "rendered_diff_score": d.rendered_diff_score,
            "cause": d.cause,
            "fix": d.fix,
            "message": d.message,
        })

    counts_by_class = {c: 0 for c in CLASS_ORDER}
    counts_by_status = {"defect": 0, "review": 0}
    for r in records:
        counts_by_class[r["class"]] = counts_by_class.get(r["class"], 0) + 1
        counts_by_status[r["status"]] = counts_by_status.get(r["status"], 0) + 1

    return {
        "meta": {
            **meta,
            "total_defects": len(records),
            "counts_by_class": counts_by_class,
            "counts_by_status": counts_by_status,
        },
        "defects": records,
    }


def write_json(report: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")


def has_defects(report: dict) -> bool:
    return report["meta"]["counts_by_status"].get("defect", 0) > 0


# --------------------------------------------------------------------------- #
# 13-category audit taxonomy (legacy v1) + weighted quality score
# --------------------------------------------------------------------------- #
CATEGORIES_LIST = [
    "Drawing Layout",
    "Views & Geometry",
    "Dimensions & Tolerances",
    "Notes & Annotations",
    "Title Block",
    "Revision History",
    "BOM / Tables",
    "Symbols & Standards",
    "Styling & Layers",
    "Scale & Proportion",
    "Visual Quality",
    "Conversion Integrity",
    "Compliance Rules",
]
CATEGORY_WEIGHTS = {
    "Drawing Layout": 10,
    "Views & Geometry": 15,
    "Dimensions & Tolerances": 15,
    "Notes & Annotations": 10,
    "Title Block": 10,
    "Revision History": 5,
    "BOM / Tables": 10,
    "Symbols & Standards": 5,
    "Styling & Layers": 5,
    "Scale & Proportion": 5,
    "Visual Quality": 5,
    "Conversion Integrity": 3,
    "Compliance Rules": 2,
}

_TITLE_KW = ["MATERIAL", "WEIGHT", "SCALE", "UNIT", "DRAWN", "CHECKED", "APPROVED",
             "FINISH", "COATING", "PART NO", "ASSY", "SIZE", "TITLE", "DWG"]
_BOM_KW = ["QTY", "PART NUMBER", "DESCRIPTION", "ITEM", "FERRULE", "HOSE",
           "WELDED PIPE", "ACTUATOR", "LIST"]
_REV_KW = ["REV", "REVISION", "ZONE", "DATE", "HISTORY"]
_SYMBOL_RE = re.compile(r"[Øø⌀φф°±¼½¾]|\bDIA\b|\bDEG\b|\bRAD\b|GD&T|\bSYMBOL\b")
_DIM_RE = re.compile(r"(\d+/\d+|\d+\.\d+|\b\d+\b|±|ø|DIA|MM|INCH|DEG|RAD|°|UNITS)")


def classify_issue(record: dict, page_w: float, page_h: float) -> str:
    """Bucket a defect into one of the 13 audit categories (legacy v1 taxonomy), using the
    new defect schema (``class`` + ``zone`` + text + candidate bbox location)."""
    cls = record.get("class")
    combined = (f"{record.get('message', '')} {record.get('ref_text') or ''} "
                f"{record.get('cand_text') or ''}").upper()

    if cls == "text_overlap":
        return "Visual Quality"
    if cls == "font_glyph_corruption":
        return "Symbols & Standards" if _SYMBOL_RE.search(combined) else "Conversion Integrity"

    # missing_text / missing_annotation / text_misplacement -> location + content heuristics.
    if record.get("zone") == "title-block":
        return "Title Block"
    bbox = record.get("bbox_cand") or record.get("bbox_ref") or [0.0, 0.0, 0.0, 0.0]
    nx0 = bbox[0] / max(1.0, page_w)
    ny0 = bbox[1] / max(1.0, page_h)
    ny1 = bbox[3] / max(1.0, page_h)

    if nx0 > 0.7 and ny1 < 0.35 and any(k in combined for k in _REV_KW):
        return "Revision History"
    if nx0 > 0.65 and ny0 > 0.65 and any(k in combined for k in _TITLE_KW):
        return "Title Block"
    if (nx0 > 0.6 or "BOM" in combined or "TABLE" in combined) and any(k in combined for k in _BOM_KW):
        return "BOM / Tables"
    if _DIM_RE.search(combined) or "DIMENSION" in combined or "TOLERANCE" in combined:
        return "Dimensions & Tolerances"
    if cls == "missing_annotation":
        return "Notes & Annotations"
    if any(k in combined for k in ("NOTE", "BALLOON", "CALLOUT")):
        return "Notes & Annotations"
    if len([w for w in combined.split() if w.isalpha()]) > 1:
        return "Notes & Annotations"
    return "Visual Quality"


def page_quality_score(records: list[dict], page_w: float, page_h: float) -> int:
    """Category-weighted quality score in [0, 100] for one page's defect records.

    Starts at 100 and subtracts each *failed category's* weight (a category fails if any defect
    classifies into it) — the single source of truth shared by the HTML scoreboard
    (``_build_page``) and the JSON/API aggregate (``pipeline.run_comparison``)."""
    failed = {classify_issue(rec, page_w, page_h) for rec in records}
    score = 100 - sum(CATEGORY_WEIGHTS.get(name, 0) for name in failed)
    return max(0, score)


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
def _render_page_png(page: fitz.Page, records: list[dict], dpi: int) -> str:
    w, h = page.rect.width, page.rect.height
    zoom = dpi / 72.0
    if max(w, h) * zoom > _REPORT_MAX_DIM:
        zoom = _REPORT_MAX_DIM / max(w, h)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(12, int(14 * zoom)))
    except Exception:
        font = ImageFont.load_default()

    for r in records:
        bbox = r["bbox_cand"] or r["bbox_ref"]
        if not bbox:
            continue
        color = CLASS_COLOR.get(r["class"], (128, 128, 128))
        x0, y0, x1, y1 = (v * zoom for v in bbox)
        draw.rectangle([x0, y0, x1, y1], outline=color, width=max(2, int(2 * zoom)))
        label = r["id"]
        ly = max(0, y0 - max(12, int(14 * zoom)) - 2)
        draw.text((x0, ly), label, fill=color, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Engineering drawing QA compliance audit report: Reference vs Creo review">
  <title>Engineering Drawing QA Compliance Report</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-color: #0b0f19;
      --panel-bg: #141b2d;
      --panel-border: #243049;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --primary: #6366f1;
      --primary-glow: rgba(99, 102, 241, 0.15);
      --color-high: #ef4444;
      --color-high-bg: rgba(239, 68, 68, 0.1);
      --color-medium: #f59e0b;
      --color-medium-bg: rgba(245, 158, 11, 0.1);
      --color-low: #3b82f6;
      --color-low-bg: rgba(59, 130, 246, 0.1);
      --color-clean: #10b981;
      --color-clean-bg: rgba(16, 185, 129, 0.1);
    }
    html[data-theme="light"] {
      --bg-color: #f8fafc;
      --panel-bg: #ffffff;
      --panel-border: #e2e8f0;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --primary: #4f46e5;
      --primary-glow: rgba(79, 70, 229, 0.1);
      --color-high: #dc2626;
      --color-high-bg: rgba(220, 38, 38, 0.08);
      --color-medium: #d97706;
      --color-medium-bg: rgba(217, 119, 6, 0.08);
      --color-low: #2563eb;
      --color-low-bg: rgba(37, 99, 235, 0.08);
      --color-clean: #16a34a;
      --color-clean-bg: rgba(22, 163, 74, 0.08);
    }
    html[data-theme="light"] header {
      background: linear-gradient(135deg, #e0e7ff 0%, #f8fafc 100%);
      border-color: #cbd5e1;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    }
    html[data-theme="light"] header h1 {
      background: linear-gradient(to right, #4f46e5, #7c3aed);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    html[data-theme="light"] header p { color: #475569; }
    html[data-theme="light"] header .meta-grid { color: #64748b; }
    html[data-theme="light"] header .meta-item strong { color: #0f172a; }
    html[data-theme="light"] .header-actions { border-top-color: #cbd5e1; }
    html[data-theme="light"] .download-note { color: #64748b; }
    html[data-theme="light"] .section-title { color: #1e293b; }
    html[data-theme="light"] .summary-text {
      background-color: #f1f5f9; border-color: #cbd5e1; color: #334155;
    }
    html[data-theme="light"] .category-card { background-color: #ffffff; }
    html[data-theme="light"] .category-card:hover { background-color: #f1f5f9; }
    html[data-theme="light"] .category-card-details { border-top-color: #e2e8f0; }
    html[data-theme="light"] .category-card-details li { color: #334155; }
    html[data-theme="light"] .audit-summary-table td { border-bottom: 1px solid #f1f5f9; }
    html[data-theme="light"] .breakdown-title { color: #4f46e5 !important; }
    html[data-theme="light"] .click-hint { color: #94a3b8; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: var(--bg-color);
      color: var(--text-main);
      padding: 40px 24px;
      line-height: 1.5;
      transition: background-color 0.2s ease, color 0.2s ease;
    }
    .container { max-width: 1400px; margin: 0 auto; }
    header {
      background: linear-gradient(135deg, #1e1b4b 0%, #141b2d 100%);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      padding: 32px 40px;
      margin-bottom: 32px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
      position: relative;
      overflow: hidden;
    }
    header::before {
      content: '';
      position: absolute;
      top: -50%; right: -10%;
      width: 400px; height: 400px;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%);
      pointer-events: none;
    }
    header h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 2.25rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(to right, #a5b4fc, #e0e7ff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
      display: flex; align-items: center; gap: 12px;
    }
    header p { color: var(--text-muted); font-size: 1rem; font-weight: 400; }
    .header-actions {
      display: flex; align-items: center; justify-content: space-between;
      gap: 16px; flex-wrap: wrap; margin-top: 20px; padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
    }
    header .meta-grid {
      display: flex; flex-wrap: wrap; gap: 24px;
      font-size: 0.875rem; color: var(--text-muted);
    }
    header .meta-item { display: flex; align-items: center; gap: 8px; }
    header .meta-item strong { color: var(--text-main); }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px; margin-bottom: 40px;
    }
    .stat-card {
      background-color: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 14px; padding: 24px; text-align: center;
      transition: transform 0.3s ease, box-shadow 0.3s ease;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    html[data-theme="light"] .stat-card,
    html[data-theme="light"] .audit-summary-panel,
    html[data-theme="light"] .page-section,
    html[data-theme="light"] .category-card,
    html[data-theme="light"] header { box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06); }
    .stat-card:hover { transform: translateY(-4px); box-shadow: 0 8px 25px rgba(99, 102, 241, 0.1); }
    .stat-card .num {
      font-family: 'Outfit', sans-serif; font-size: 2.75rem;
      font-weight: 700; line-height: 1.2; margin-bottom: 4px;
    }
    .stat-card .label {
      font-size: 0.8rem; font-weight: 600; text-transform: uppercase;
      letter-spacing: 1px; color: var(--text-muted);
    }
    .stat-card.high .num { color: var(--color-high); }
    .stat-card.medium .num { color: var(--color-medium); }
    .stat-card.low .num { color: var(--color-low); }
    .stat-card.clean .num { color: var(--color-clean); }
    .stat-card.bad .num { color: var(--color-high); }
    .section-title {
      font-family: 'Outfit', sans-serif; font-size: 1.5rem; font-weight: 700;
      margin-bottom: 24px; color: #e0e7ff;
      border-left: 4px solid var(--primary); padding-left: 12px;
    }
    .audit-summary-panel {
      background-color: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 14px; padding: 24px; margin-bottom: 40px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    .audit-summary-table {
      width: 100%; border-collapse: collapse; text-align: left; font-size: 0.95rem;
    }
    .audit-summary-table th {
      padding: 12px; border-bottom: 2px solid var(--panel-border);
      color: var(--text-muted); font-weight: 600; text-transform: uppercase;
      font-size: 0.75rem; letter-spacing: 0.5px;
    }
    .audit-summary-table td { padding: 14px 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
    .audit-summary-table tr:last-child td { border-bottom: none; }
    .cat-name-cell { font-weight: 600; color: var(--text-main); }
    .failed-row { background-color: rgba(239, 68, 68, 0.01); }
    .passed-row { background-color: rgba(16, 185, 129, 0.01); }
    .failures-cell { color: var(--text-muted); font-weight: 500; }
    .page-section {
      background-color: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 16px; margin-bottom: 32px; overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    .page-header {
      padding: 20px 28px; font-size: 1.15rem; font-weight: 600;
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--panel-border);
    }
    .page-header.bad { background: linear-gradient(to right, rgba(239, 68, 68, 0.05), transparent); }
    .page-header.ok { background: linear-gradient(to right, rgba(16, 185, 129, 0.05), transparent); }
    .status-pill {
      font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
      padding: 6px 14px; border-radius: 50px; letter-spacing: 0.5px;
    }
    .status-pill.bad { background-color: var(--color-high-bg); color: var(--color-high); border: 1px solid rgba(239, 68, 68, 0.2); }
    .status-pill.ok { background-color: var(--color-clean-bg); color: var(--color-clean); border: 1px solid rgba(16, 185, 129, 0.2); }
    .comparison-container {
      position: relative; background-color: rgba(26, 34, 53, 0.98);
      padding: 10px; border-bottom: 1px solid var(--panel-border); overflow: hidden;
    }
    html[data-theme="light"] .comparison-container { background-color: #eef2ff; }
    .comparison-img {
      width: 100%; height: auto; display: block; border-radius: 8px;
      box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    .page-body { padding: 28px; }
    .summary-text {
      background-color: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.05);
      padding: 16px 20px; border-radius: 10px; margin-bottom: 24px;
      font-size: 0.95rem; color: #d1d5db; font-style: italic;
    }
    .categories-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px; margin-bottom: 28px;
    }
    .category-card {
      background-color: rgba(255, 255, 255, 0.015);
      border: 1px solid var(--panel-border);
      border-radius: 10px; padding: 16px; cursor: pointer;
      transition: background-color 0.2s, border-color 0.2s, transform 0.2s;
    }
    .category-card:hover { background-color: rgba(255, 255, 255, 0.035); transform: translateY(-2px); }
    .category-card.passed { border-left: 5px solid var(--color-clean); }
    .category-card.failed { border-left: 5px solid var(--color-high); background-color: rgba(239, 68, 68, 0.01); }
    .category-card.failed .category-card-details { display: block; }
    .category-card-header { display: flex; justify-content: space-between; align-items: center; }
    .category-card-name { font-weight: 700; font-size: 0.95rem; color: var(--text-main); }
    .category-card-status {
      font-size: 0.72rem; font-weight: 800; padding: 3px 8px; border-radius: 4px;
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .category-card-status.passed { background-color: var(--color-clean-bg); color: var(--color-clean); }
    .category-card-status.failed { background-color: var(--color-high-bg); color: var(--color-high); }
    .category-card-details {
      margin-top: 12px; padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 0.8rem; color: var(--text-muted); display: none;
    }
    .category-card-details ul { list-style-type: square; margin-left: 16px; }
    .category-card-details li { margin-bottom: 10px; color: #e5e7eb; line-height: 1.45; }
    .click-hint {
      display: block; font-size: 0.68rem; color: var(--text-muted);
      margin-top: 8px; text-align: right; font-style: italic;
    }
    .score-badge {
      font-size: 0.78rem; font-weight: 700; padding: 6px 14px; border-radius: 50px;
      letter-spacing: 0.5px; display: inline-flex; align-items: center;
    }
    .score-badge.good { background-color: rgba(16, 185, 129, 0.1); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.2); }
    .score-badge.avg { background-color: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2); }
    .score-badge.poor { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); }
    html[data-theme="light"] .score-badge.good { background-color: rgba(22, 163, 74, 0.08); color: #16a34a; border-color: rgba(22, 163, 74, 0.15); }
    html[data-theme="light"] .score-badge.avg { background-color: rgba(217, 119, 6, 0.08); color: #d97706; border-color: rgba(217, 119, 6, 0.15); }
    html[data-theme="light"] .score-badge.poor { background-color: rgba(220, 38, 38, 0.08); color: #dc2626; border-color: rgba(220, 38, 38, 0.15); }
    .score-bar-bg { width: 100px; height: 8px; background-color: var(--panel-border); border-radius: 4px; overflow: hidden; }
    .no-issues-msg { padding: 12px 0; color: var(--color-clean); font-weight: 600; display: flex; align-items: center; gap: 8px; }
    .kv-ref { color: var(--color-high); }
    .download-btn {
      appearance: none; border: 1px solid rgba(99, 102, 241, 0.45);
      background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color: #fff;
      border-radius: 999px; padding: 12px 18px; font-weight: 700; font-size: 0.92rem;
      cursor: pointer; box-shadow: 0 10px 24px rgba(79, 70, 229, 0.28);
      transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
    }
    .download-btn:hover { transform: translateY(-1px); box-shadow: 0 14px 28px rgba(79, 70, 229, 0.34); }
    .download-btn:active { transform: translateY(0); opacity: 0.92; }
    .download-btn:disabled { cursor: wait; opacity: 0.7; }
    .download-note { color: var(--text-muted); font-size: 0.82rem; }
    .pdf-status { color: #c7d2fe; font-size: 0.82rem; min-height: 1em; }
    html[data-theme="light"] .pdf-status { color: #4f46e5; }
    .pdf-exporting .header-actions,
    .pdf-exporting .download-btn,
    .pdf-exporting .download-note,
    .pdf-exporting .pdf-status { display: none !important; }
    @media print {
      .header-actions, .download-btn, .download-note, .pdf-status { display: none !important; }
    }
  </style>
</head>
<body>
  <div class="container">

    <header>
      <h1>🔍 Engineering Drawing QA Compliance Report</h1>
      <p>Automated text &amp; annotation fidelity audit between reference drawings and Creo review drawings.</p>

      <div class="meta-grid">
        <div class="meta-item">📅 Generated: <strong>{{ generated_at }}</strong></div>
        <div class="meta-item">📐 Reference: <strong>{{ reference }}</strong></div>
        <div class="meta-item">📄 Candidate: <strong>{{ candidate }}</strong></div>
        <div class="meta-item">🗂️ Total Pages Analyzed: <strong>{{ total_pages }}</strong></div>
        <div class="meta-item">⚠️ Total Issues Flagged: <strong>{{ total_issues }}</strong></div>
      </div>

      <div class="header-actions">
        <div class="download-note">Download a PDF copy of this report from the current page.</div>
        <div>
          <button id="downloadPdfBtn" class="download-btn" type="button">Download PDF</button>
          <div id="pdfStatus" class="pdf-status" aria-live="polite"></div>
        </div>
      </div>
    </header>

    <!-- Stats Dashboard -->
    <div class="stats-grid">
      <div class="stat-card high"><div class="num">{{ high_count }}</div><div class="label">High Severity</div></div>
      <div class="stat-card medium"><div class="num">{{ medium_count }}</div><div class="label">Medium Severity</div></div>
      <div class="stat-card low"><div class="num">{{ low_count }}</div><div class="label">Low Severity</div></div>
      <div class="stat-card clean"><div class="num">{{ ok_pages }}</div><div class="label">Clean Pages</div></div>
      <div class="stat-card bad"><div class="num">{{ bad_pages }}</div><div class="label">Pages with Issues</div></div>
    </div>

    <!-- Global Audit Summary Grid -->
    <div class="section-title">Compliance Audit Matrix (13 Categories Summary)</div>
    <div class="audit-summary-panel">
      <table class="audit-summary-table">
        <thead>
          <tr>
            <th>Audit Category</th>
            <th>Compliance Status</th>
            <th>Failures (Pages Affected)</th>
          </tr>
        </thead>
        <tbody>
          {% for cat_name, cat_data in global_categories.items() %}
          <tr class="{{ 'failed-row' if cat_data.status == 'FAIL' else 'passed-row' }}">
            <td class="cat-name-cell">{{ cat_name }}</td>
            <td>
              <span class="status-pill {{ 'bad' if cat_data.status == 'FAIL' else 'ok' }}">
                {{ cat_data.status }}
              </span>
            </td>
            <td class="failures-cell">{{ cat_data.failed_count }} page(s) failed</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Drawing Quality Scoreboard Section -->
    <div class="section-title">Drawing Quality Scoreboard</div>
    <div class="audit-summary-panel">
      <table class="audit-summary-table">
        <thead>
          <tr>
            <th>Drawing Page</th>
            <th>Compliance Status</th>
            <th>Quality Score</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {% for page in pages | sort(attribute='score', reverse=true) %}
          <tr class="{{ 'passed-row' if page.score >= 80 else 'failed-row' }}">
            <td class="cat-name-cell">Page {{ page.page }}</td>
            <td>
              <span class="status-pill {{ 'ok' if page.status == 'PASS' else 'bad' }}">
                {{ page.status }}
              </span>
            </td>
            <td>
              <div style="display: flex; align-items: center; gap: 10px;">
                <div class="score-bar-bg">
                  <div style="width: {{ page.score }}%; height: 100%; background-color: {{ '#10b981' if page.score >= 80 else '#f59e0b' if page.score >= 50 else '#ef4444' }};"></div>
                </div>
                <strong style="color: {{ '#10b981' if page.score >= 80 else '#f59e0b' if page.score >= 50 else '#ef4444' }}; font-size: 1.1rem; min-width: 60px; text-align: right;">{{ page.score }}/100</strong>
              </div>
            </td>
            <td>
              <a href="#page-{{ page.index }}" style="color: var(--primary); text-decoration: none; font-weight: 700; font-size: 0.85rem;">View Details →</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="section-title">Page Breakdown Analysis</div>

    {% for page in pages %}
    <div class="page-section" id="page-{{ page.index }}">
      <div class="page-header {{ 'bad' if page.page_has_issues else 'ok' }}">
        <span>Page {{ page.page }}</span>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="score-badge {{ 'good' if page.score >= 80 else 'avg' if page.score >= 50 else 'poor' }}">
            Score: {{ page.score }}/100
          </span>
          <span class="status-pill {{ 'bad' if page.page_has_issues else 'ok' }}">
            {{ page.status }} - {{ page.issues|length }} issue(s) detected
          </span>
        </div>
      </div>

      {% if page.comparison_image %}
      <div class="comparison-container">
        <img class="comparison-img" src="{{ page.comparison_image }}" alt="Page {{ page.page }} Creo Drawing with highlighting">
      </div>
      {% endif %}

      <div class="page-body">
        {% if page.summary %}
        <div class="summary-text">{{ page.summary }}</div>
        {% endif %}

        <div class="breakdown-title" style="margin-bottom: 12px; font-weight:700; font-size:1rem; color: #a5b4fc;">Audit Categories Breakdown:</div>

        <div class="categories-grid">
          {% for cat in page.categories_report %}
          <div class="category-card {{ 'failed' if cat.status == 'FAIL' else 'passed' }} {{ 'expanded' if cat.status == 'FAIL' else '' }}" onclick="toggleDetails(this)">
            <div class="category-card-header">
              <span class="category-card-name">{{ cat.name }}</span>
              <span class="category-card-status {{ 'failed' if cat.status == 'FAIL' else 'passed' }}">{{ cat.status }}</span>
            </div>
            {% if cat.issues %}
            <div class="category-card-details" style="display: {{ 'block' if cat.status == 'FAIL' else 'none' }};">
              <ul>
                {% for iss in cat.issues %}
                <li>
                  <strong>{{ iss.id }}</strong> — {{ iss.message }}
                  {% if iss.zone %}<span style="opacity:.75;"> [Zone {{ iss.zone }}]</span>{% endif %}
                  {% if iss.ref_text or iss.cand_text %}<div style="margin-top:3px;">Text: <span class="kv-ref">{{ iss.ref_text or '—' }}</span>{% if iss.cand_text %} → <strong>{{ iss.cand_text }}</strong>{% endif %}</div>{% endif %}
                  {% if iss.cause %}<div style="margin-top:3px;"><em>Cause:</em> {{ iss.cause }}</div>{% endif %}
                  {% if iss.fix %}<div style="margin-top:3px;"><em>Fix:</em> {{ iss.fix }}</div>{% endif %}
                </li>
                {% endfor %}
              </ul>
            </div>
            <span class="click-hint">{{ 'Click to hide details' if cat.status == 'FAIL' else 'Click to show details' }}</span>
            {% endif %}
          </div>
          {% endfor %}
        </div>

        {% if not page.page_has_issues %}
        <div class="no-issues-msg">
          ✨ Perfect Match! All 13 compliance categories passed.
        </div>
        {% endif %}
      </div>
    </div>
    {% endfor %}

  </div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
  <script>
    function toggleDetails(card) {
      const details = card.querySelector('.category-card-details');
      const hint = card.querySelector('.click-hint');
      if (!details) return;
      const isVisible = details.style.display === 'block';
      details.style.display = isVisible ? 'none' : 'block';
      card.classList.toggle('expanded', !isVisible);
      if (hint) { hint.innerText = isVisible ? 'Click to show details' : 'Click to hide details'; }
    }

    function syncFailedCards(root) {
      root.querySelectorAll('.category-card.failed').forEach((card) => {
        const details = card.querySelector('.category-card-details');
        const hint = card.querySelector('.click-hint');
        if (details) { details.style.display = 'block'; }
        card.classList.add('expanded');
        if (hint) { hint.innerText = 'Click to hide details'; }
      });
    }

    document.addEventListener('DOMContentLoaded', () => {
      const root = document.querySelector('.container');
      const downloadBtn = document.getElementById('downloadPdfBtn');
      const pdfStatus = document.getElementById('pdfStatus');

      if (root) { syncFailedCards(root); }

      if (downloadBtn) {
        downloadBtn.addEventListener('click', async () => {
          const reportRoot = document.querySelector('.container');
          if (!reportRoot) {
            if (pdfStatus) { pdfStatus.textContent = 'PDF export is unavailable in this browser.'; }
            return;
          }
          if (typeof html2pdf === 'undefined') {
            if (pdfStatus) { pdfStatus.textContent = 'PDF library did not load. Opening print dialog instead.'; }
            window.print();
            return;
          }
          reportRoot.classList.add('pdf-exporting');
          syncFailedCards(reportRoot);
          downloadBtn.disabled = true;
          if (pdfStatus) { pdfStatus.textContent = 'Rendering report for download...'; }
          try {
            await html2pdf().set({
              margin: 10,
              filename: 'engineering-drawing-qa-report.pdf',
              image: { type: 'jpeg', quality: 0.98 },
              html2canvas: {
                scale: 2, useCORS: true, allowTaint: true, scrollY: 0,
                onclone: (clonedDoc) => {
                  clonedDoc.documentElement.dataset.theme = 'light';
                  clonedDoc.documentElement.classList.add('pdf-exporting');
                  const clonedRoot = clonedDoc.querySelector('.container');
                  if (clonedRoot) { syncFailedCards(clonedRoot); }
                  ['downloadPdfBtn', 'pdfStatus'].forEach((id) => {
                    const el = clonedDoc.getElementById(id); if (el) el.remove();
                  });
                  const clonedNote = clonedDoc.querySelector('.download-note');
                  if (clonedNote) clonedNote.remove();
                }
              },
              jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
            }).from(reportRoot).save();
            if (pdfStatus) { pdfStatus.textContent = 'PDF download started.'; }
          } catch (error) {
            console.error('PDF export failed:', error);
            if (pdfStatus) { pdfStatus.textContent = 'PDF export failed. Please try again.'; }
          } finally {
            downloadBtn.disabled = false;
            reportRoot.classList.remove('pdf-exporting');
            setTimeout(() => {
              if (pdfStatus && pdfStatus.textContent === 'PDF download started.') { pdfStatus.textContent = ''; }
            }, 3000);
          }
        });
      }
    });
  </script>
</body>
</html>""")


def _build_page(num: int, page: fitz.Page, records: list[dict],
                global_categories: dict, dpi: int) -> dict:
    """Assemble one v1-format page entry: 13-category report, weighted score, summary, image."""
    pw, ph = page.rect.width, page.rect.height
    cat_map: dict[str, list[dict]] = {name: [] for name in CATEGORIES_LIST}
    for rec in records:
        cat_map[classify_issue(rec, pw, ph)].append(rec)

    categories_report = []
    for name in CATEGORIES_LIST:
        issues = cat_map[name]
        status = "FAIL" if issues else "PASS"
        if status == "FAIL":
            global_categories[name]["failed_count"] += 1
            global_categories[name]["status"] = "FAIL"
        categories_report.append({
            "name": name,
            "status": status,
            "issues": [{
                "id": i["id"], "message": i["message"], "zone": i.get("zone"),
                "ref_text": i.get("ref_text"), "cand_text": i.get("cand_text"),
                "cause": i.get("cause"), "fix": i.get("fix"),
                "severity": i.get("severity"), "status": i.get("status"),
            } for i in issues],
        })
    score = page_quality_score(records, pw, ph)

    page_has_issues = bool(records)
    failed = [c["name"] for c in categories_report if c["status"] == "FAIL"]
    if page_has_issues:
        noun = "discrepancy" if len(records) == 1 else "discrepancies"
        summary = (f"Page {num} has {len(records)} identified {noun}. "
                   f"Failed categories: {', '.join(failed)}.")
    else:
        summary = f"Page {num} matches the reference drawing in all audit categories."

    png = _render_page_png(page, records, dpi)
    return {
        "index": num,
        "page": num,
        "page_has_issues": page_has_issues,
        "status": "FAIL" if page_has_issues else "PASS",
        "score": score,
        "summary": summary,
        "comparison_image": f"data:image/png;base64,{png}",
        "categories_report": categories_report,
        "issues": records,
    }


def render_html(report: dict, cand_doc: fitz.Document, output_path: str | Path, config: Config) -> None:
    by_page: dict[int, list[dict]] = {}
    for r in report["defects"]:
        by_page.setdefault(r["page"], []).append(r)

    global_categories = {name: {"failed_count": 0, "status": "PASS"} for name in CATEGORIES_LIST}
    pages = [
        _build_page(num, cand_doc[num - 1], by_page.get(num, []), global_categories, config.render_dpi)
        for num in range(1, len(cand_doc) + 1)
    ]

    sev = {"high": 0, "medium": 0, "low": 0}
    for r in report["defects"]:
        s = str(r.get("severity", "")).lower()
        if s in sev:
            sev[s] += 1

    m = report["meta"]
    html = HTML_TEMPLATE.render(
        pages=pages,
        generated_at=m.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        reference=m.get("reference", "—"),
        candidate=m.get("candidate", "—"),
        total_pages=len(cand_doc),
        total_issues=m.get("total_defects", len(report["defects"])),
        high_count=sev["high"], medium_count=sev["medium"], low_count=sev["low"],
        ok_pages=sum(1 for p in pages if not p["page_has_issues"]),
        bad_pages=sum(1 for p in pages if p["page_has_issues"]),
        global_categories=global_categories,
    )
    Path(output_path).write_text(html, encoding="utf-8")
