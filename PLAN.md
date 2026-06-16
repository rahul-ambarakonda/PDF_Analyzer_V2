# PLAN — Creo/CAD PDF Text-Fidelity Comparator

Build to `SPEC.md` (authoritative). This file tracks the implementation approach; SPEC.md wins
on any disagreement.

## What this is

A CLI that compares a **reference** drawing PDF against a **candidate** (Creo-exported) PDF and
reports text/annotation fidelity defects with near-100% recall and near-zero false positives.
Geometry is out of scope. Built greenfield in the `comparator/` package; the legacy `core/`
pipeline is reference only and is not extended.

## Defect classes

| class | trigger |
|---|---|
| `missing_text` | reference run unmatched after matching |
| `missing_annotation` | reference annotation *cluster* unmatched |
| `text_overlap` | two candidate runs overlap > `overlap_ratio_threshold` (intra-doc) |
| `text_misplacement` | matched run shifted > `position_tolerance_pts` after registration |
| `font_glyph_corruption` | matched run, normalized strings differ **AND** rendered region differs |

## Core principle (SPEC §3)

The rendered glyph is ground truth; the extracted string is a hint. A string mismatch becomes a
class-5 defect **only when the clip-rendered region also differs** (`render_compare.py`). Renders
the same → encoding/ToUnicode artifact → suppressed. A string-only test for class 5 is forbidden.

## Module map (`comparator/`)

- `cli.py` — `compare --reference --candidate --config --out`; exit code != 0 if any defect.
- `config.py` — load/validate `config.yaml`, dataclass, documented defaults.
- `extract.py` — PyMuPDF `get_text("rawdict")` → runs + chars; cluster into annotation units.
- `register.py` — frame/title-block → affine; parse zone grid from border labels; point→zone.
- `normalize.py` — symbol/format equivalence from config (½ Ø ° ±, trailing zeros…).
- `match.py` — scipy Hungarian ref↔candidate; cost = position + normalized edit distance.
- `render_compare.py` — clip-render bbox both PDFs, align, 1−SSIM diff (the §3 rule).
- `detect.py` — the 5 detectors → defect records.
- `report.py` — `report.json` + `report.html`.

## Issue JSON (SPEC §5 + requested `zone`/`cause`/`fix`)

```json
{ "id": "D-014", "page": 2, "zone": "C7", "class": "font_glyph_corruption",
  "severity": "high", "confidence": 0.97, "status": "defect",
  "ref_text": "1/2", "cand_text": "1#8",
  "bbox_ref": [..], "bbox_cand": [..], "rendered_diff_score": 0.41,
  "cause": "<templated>", "fix": "<templated>",
  "message": "Text '1/2' renders as '1#8' in candidate (zone C7)." }
```

`zone` = candidate drawing grid cell (rows A–M × cols 1–N), parsed per-sheet from the Creo border;
center-cell on spans; `"title-block"`/`null` outside the grid. `cause`/`fix` are per-class
templates in `config.yaml` with `{ref_text}`/`{cand_text}`/`{zone}` slots. Defects below
`confidence_threshold` get `status:"review"` instead of `"defect"`.

## Tests (SPEC §9)

`tests/fixtures.py` synthesizes a clean vector PDF in-code and injects each labelled defect class,
including the headline **encoding-only** case (break ToUnicode via pikepdf without changing the
rendering → must yield ZERO defects). Gates: recall ≥0.98/class, precision ≥0.99, encoding-only=0,
registration error < tolerance on an offset copy. Golden `report.json` snapshots.

## Build order (SPEC §10) — all slices, then hand over for manual testing

1. extract + render_compare + §3 rule.
2. register + zone parsing + misplacement.
3. text_overlap.
4. match + missing text/annotation + clustering.
5. report.json + HTML + cli + exit codes.
6. config externalization + normalize pass.

## Run

```
python -m comparator.cli --reference REF.pdf --candidate CAND.pdf --config config.yaml --out report/
pytest -q
```
