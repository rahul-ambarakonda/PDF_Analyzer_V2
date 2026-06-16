# 🔍 Creo/CAD PDF Text-Fidelity Comparator

Compares a **reference** drawing PDF (legacy CAD export) against a **candidate** drawing PDF
(Creo export) and reports every text/annotation fidelity defect with near-100% recall and
near-zero false positives. It validates *text and annotation fidelity only* — geometry is out
of scope. Runs fully offline. Built to [`SPEC.md`](SPEC.md) (the authoritative spec).

## Defect classes

| Class | Meaning |
|---|---|
| `missing_text` | A text run present in the reference is absent from the candidate. |
| `missing_annotation` | An annotation cluster (note / GD&T frame / leader+text) is absent. |
| `text_overlap` | Two candidate labels collide (bbox intersection beyond threshold). |
| `text_misplacement` | A matched run is shifted beyond tolerance after page registration. |
| `font_glyph_corruption` | A matched run *renders* differently (e.g. `1/2` → `1#8`). |

### Core principle (SPEC §3)

The **rendered glyph is ground truth; the extracted string is only a hint.** A string mismatch
is escalated to a `font_glyph_corruption` defect *only when the clip-rendered region also
differs*. If the candidate renders correctly but extracts wrong text (a broken ToUnicode /
encoding artifact), it is **suppressed** — not flagged. A string-only comparison is never the
sole test.

## Install

```bash
python -m venv venv && source venv/bin/activate     # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python -m comparator.cli \
  --reference REF.pdf --candidate CAND.pdf \
  --config config.yaml --out report/
```

Outputs `report/report.json` (machine-readable, SPEC §5 schema) and `report/report.html` — the
v1 dashboard: stat cards, the **13-category Compliance Audit Matrix**, the **Drawing Quality
Scoreboard** (category-weighted score out of 100), and a per-page breakdown with the annotated
candidate raster and collapsible category cards (each failed category lists its issues with
`zone` / `ref→cand` text / `cause` / `fix`). The process exits non-zero if any defect has
`status == "defect"` (for CI gating).

### Audit categories & quality score

Every defect is bucketed into one of 13 audit categories (`Dimensions & Tolerances`,
`Notes & Annotations`, `Title Block`, `Symbols & Standards`, `Conversion Integrity`, …) by
class + location + content. The page score starts at 100 and subtracts each **failed
category's** weight (not per issue), matching v1. Geometry-only categories
(`Views & Geometry`, `Scale & Proportion`, `Visual Quality`, `Styling & Layers`) have no
text-fidelity detector behind them and therefore stay PASS — this tool audits text/annotation
fidelity, not geometry.

### Browser UI (folder batch)

```bash
python -m comparator.web        # then open http://127.0.0.1:5000
```

Pick a **reference folder** and a **candidate folder**; PDFs are paired by filename, every pair
is compared, and a summary table links to each pair's report. Unmatched filenames are listed as
warnings. Host/port/config via `COMPARATOR_HOST` / `COMPARATOR_PORT` / `COMPARATOR_CONFIG`.

### Issue record schema

```json
{ "id": "D-014", "page": 2, "zone": "C7", "class": "font_glyph_corruption",
  "severity": "high", "confidence": 0.97, "status": "defect",
  "ref_text": "1/2", "cand_text": "1#8",
  "bbox_ref": [..], "bbox_cand": [..], "rendered_diff_score": 0.41,
  "cause": "...", "fix": "...", "message": "..." }
```

`zone` is the candidate drawing-grid cell (rows × columns, e.g. `C7`), parsed per-sheet from
the Creo border labels. `cause`/`fix` are per-class templates. Defects below
`confidence_threshold` get `status: "review"` instead of `"defect"`.

## Multi-view sheets (drawings placed differently)

A sheet often holds several drawing views, and a candidate (Creo) export may lay a view out at
a different position than the reference. The comparator handles this by **per-view
registration**: sequential RANSAC fits one local affine per consistently-moving group of text
anchors, so a relocated *view* is matched and absorbed (not flagged), while a single label that
shifted *relative to its own view* is still reported as `text_misplacement`. A view earns its
own transform only with ≥ `registration_min_view_anchors` matching anchors, so a lone moved run
never masquerades as a moved view. Disable with `registration_multi_view: false` for one global
affine. See `register.py`.

## Configuration

All tolerances, symbol equivalences, ignore-regions, and cause/fix templates live in
[`config.yaml`](config.yaml) (SPEC §7) — no magic numbers in code. Key knobs:
`position_tolerance_pts`, `overlap_ratio_threshold`, `pixel_diff_threshold`,
`confidence_threshold`, `render_dpi`, `symbol_equivalences`.

## Tests

```bash
pytest -q
# headline false-positive gate (renders fine, extracts wrong => zero defects):
pytest tests/test_acceptance.py::test_encoding_only_zero_defects
```

`tests/fixtures.py` synthesizes a clean vector PDF in code and injects each defect class with
known labels — including the encoding-only case (ToUnicode broken via pikepdf, rendering
unchanged). Gates: recall ≥ 0.98/class, precision ≥ 0.99, encoding-only = 0, registration error
< tolerance on an offset copy, plus a committed golden snapshot.

## Module map (`comparator/`)

`cli.py` · `config.py` · `extract.py` · `register.py` (affine + zone grid) · `normalize.py` ·
`match.py` (Hungarian) · `render_compare.py` (the §3 rule) · `detect.py` · `report.py`.

---

> **Legacy:** the earlier pixel-diff drawing-QA tool (`main.py` + `core/`) remains in the repo
> for reference. It diffs geometry and is *not* part of this comparator.
