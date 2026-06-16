# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ SPEC.md is authoritative — and the current code does not yet match it

`SPEC.md` is the declared source of truth ("Build to it. Where this file and your own assumptions disagree, this file wins"). It specifies a **Creo/CAD PDF *text-fidelity* comparator** that is a substantial redesign of what currently exists. Before doing spec-driven work, read `SPEC.md` in full. Key divergences between spec and the present code:

| Topic | SPEC.md target | Current code |
|---|---|---|
| Scope | Text/annotation fidelity **only**; geometry explicitly out of scope | Also does pixel-level geometry diffing (`GEOMETRIC_DIFFERENCE`) |
| Module layout | `extract.py`, `register.py`, `match.py`, `render_compare.py`, `detect.py`, `normalize.py`, `report.py`, `cli.py` | `main.py` + `core/{pdf_utils,qa_agent,image_utils,report}.py` |
| Matching | scipy Hungarian, cost = position + string-edit | Greedy nearest-match on exact string equality (`compare_text_elements`) |
| Class 5 rule | "Rendered glyph is ground truth" — escalate a text mismatch to a defect **only if the rendered region also differs** (suppresses encoding-only artifacts). A string-only test is forbidden. | Not implemented |
| Config | `config.yaml` with externalized tolerances + `symbol_equivalences` | Python constants in `config.py`; no symbol normalization |
| Tests | pytest + synthetic defect-injection fixtures, recall/precision acceptance gates | **No tests exist** |
| CLI | `compare --reference … --candidate … --config … --out …`, non-zero exit on defect | `python main.py --ref … --review …`, no exit-code semantics |

Treat spec work as building new modules toward `SPEC.md` §6/§10, not patching the existing pipeline. SPEC.md §11 requires entering plan mode and producing a `PLAN.md` before writing code, building in the §10 slice order, and stopping for review after each slice.

## Running the current tool

```bash
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

python main.py                                      # compares all matching filenames in Input_PDFs/ vs Creo_PDFs/
python main.py --ref Input_PDFs/X.pdf --review Creo_PDFs/X.pdf   # single pair
python main.py --dpi 300 --out output               # defaults shown
```

Pairs are matched by **identical filename** across the two directories. Output lands in `output/` (gitignored): `report.html` + `report.json` globally, plus per-drawing `comparisons/<name>.{png,pdf,json}`. There is no build/lint/test step — it is a single-command CLI.

## Current architecture (the existing pipeline)

Despite README artifacts implying an LLM ("Llama/Ollama" references were in deleted docs), the tool is **100% offline rule-based** — PyMuPDF + OpenCV + geometry, no model calls.

Data flow: `main.py` orchestrates per page → `core/pdf_utils.py` extracts → `core/qa_agent.analyze_page()` does all detection → `core/image_utils.py` annotates → `core/report.py` renders HTML.

**`core/qa_agent.py` is the heart.** Two concepts dominate it:

1. **Dual coordinate systems, maintained in parallel everywhere.** PDF points (72 DPI, from PyMuPDF) and rendered pixels (at `--dpi`). `compute_alignment()` produces a `DrawingAlignment` carrying *two* affine transforms per region — `M_pdf` and `M_pixel`. Text logic works in PDF points; pixel-diff logic works in pixels. When editing alignment/mapping code, keep both spaces consistent. Note rendering caps the long edge at 4000px (`pdf_to_images`), so effective DPI can be below the requested value — alignment recomputes actual DPI from image-vs-page-size ratios rather than trusting the flag.

2. **Hybrid local/global registration** (because SolidWorks/SolidEdge and Creo lay views out differently). `compute_alignment()`: masks out text → SIFT+FLANN feature matches on clean geometry → global RANSAC affine → segments the sheet into drawing **views** (threshold/dilate/contours) → fits a **per-view local affine**, falling back to global when a view's transform is degenerate (`is_valid_transform`). `DrawingAlignment` then maps points/bboxes ref↔review, picking the containing view via `_find_best_view`.

Detection layers, all merged in `analyze_page()`:
- `compare_text_elements()` → `MISSING_ANNOTATION`, `TEXT_MISPLACEMENT`, `TEXT_OVERLAP` (text-vs-text via SAT polygon overlap with parallel-dimension-stack suppression; text-vs-geometry via a spatial line grid).
- `detect_geometric_differences()` → `GEOMETRIC_DIFFERENCE`: warps the reference into review space **per-view via a Voronoi distance-transform partition**, dilation-tolerant pixel diff, border masking, dual-threshold by text proximity, then **coalesces** noisy per-view/sheet diffs into summary issues.
- Page-size and per-view scale checks → `LAYOUT_MISMATCH`, `SCALE_DISCREPANCY`.

**Two parallel taxonomies — do not conflate them.** Raw issues carry a `type` (the 6 strings above, used for box colors in `image_utils`). Separately, `classify_issue()` buckets every issue into one of **13 audit categories** (`CATEGORIES_LIST`) using location heuristics + regex. The **quality score (/100)** is computed from failed *categories* weighted by `CATEGORY_WEIGHTS` — not from issue counts. This score/category logic is duplicated in three places (`analyze_page`, `main.py` doc-level aggregation, `report.py` fallback); keep them in sync if you change weights.

`core/report.py` holds the entire HTML/CSS/JS dashboard as one Jinja2 string template; comparison images are base64-inlined to avoid browser CORS/tainted-canvas errors during the client-side PDF export.

## Conventions

- Tolerances/thresholds live in `config.py` (`TEXT_DISTANCE_TOLERANCE`, `MAX_MISPLACEMENT_SHIFT`, `IMAGE_DIFF_THRESHOLD`, `MIN_DIFF_CONTOUR_AREA`) and are expressed in **PDF points** for text, **pixels** for image diffs — check which space a constant belongs to before tuning.
- All extracted text/drawing coordinates are pre-rotated to user-visible orientation via `page.rotation_matrix` in `pdf_utils.py`; downstream code assumes unrotated/visible coordinates.
- Affine math is hand-rolled (`M[0,0]*x + M[0,1]*y + M[0,2]`) and guarded against overflow/degeneracy — preserve the clamping and `is_valid_transform`/fallback patterns when touching mapping code.
