# 🔍 Creo/CAD PDF Text-Fidelity Comparator

Compares a **reference** drawing PDF (legacy CAD export) against a **candidate** drawing PDF
(Creo export) and reports every text/annotation fidelity defect with near-100% recall and
near-zero false positives. It validates *text and annotation fidelity only* — geometry is out of
scope. Runs fully offline (PyMuPDF + scikit-image + scipy; no model calls).

## Repository layout

This is a monorepo with a production HTTP API and a React/TypeScript web UI that drives it.

```
.
├── backend/          # FastAPI service + the comparison engine — see backend/README.md
│   ├── app/          #   async-job JSON API (upload → job → poll → report)
│   ├── comparator/   #   the comparison engine (extract/register/match/render_compare/detect/report)
│   └── config.yaml   #   externalized tolerances / symbol equivalences / cause-fix templates
└── frontend/         # React 18 + TypeScript (Vite) SPA — see frontend/README.md
    └── src/          #   TanStack Query + Zod; uploads folders, polls the job, renders the report
```

**Backend** — run/test/configure/deploy: see [`backend/README.md`](backend/README.md):

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000  (OpenAPI docs at /docs)
```

The API accepts reference + candidate PDFs (paired by filename), runs each pair through a
background worker, and returns a structured JSON report plus a self-contained HTML report per pair.

**Frontend** — see [`frontend/README.md`](frontend/README.md):

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173  (proxies /api → :8000)
```

Pick a reference folder and a Creo folder; the SPA uploads them, polls the comparison job, and
shows an aggregated report with a per-file table linking to each pair's HTML report. Deploy target
is S3 + CloudFront (static `dist/`), with CloudFront routing `/api/*` to the backend origin.

## Defect classes

| Class | Meaning |
|---|---|
| `missing_text` | A text run present in the reference is absent from the candidate. |
| `missing_annotation` | An annotation cluster (note / GD&T frame / leader+text) is absent. |
| `text_overlap` | Two candidate labels collide (bbox intersection beyond threshold). |
| `text_misplacement` | A matched run is shifted beyond tolerance after page registration. |
| `font_glyph_corruption` | A matched run *renders* differently (e.g. `1/2` → `1#8`). |

### Core principle

The **rendered glyph is ground truth; the extracted string is only a hint.** A string mismatch is
escalated to a `font_glyph_corruption` defect *only when the clip-rendered region also differs*.
If the candidate renders correctly but extracts wrong text (a broken ToUnicode / encoding
artifact), it is **suppressed** — not flagged. A string-only comparison is never the sole test.

### Audit categories & quality score

Every defect is bucketed into one of 13 audit categories (`Dimensions & Tolerances`,
`Notes & Annotations`, `Title Block`, `Symbols & Standards`, `Conversion Integrity`, …) by class +
location + content. The page score starts at 100 and subtracts each **failed category's** weight
(not per issue). Geometry-only categories (`Views & Geometry`, `Scale & Proportion`,
`Visual Quality`, `Styling & Layers`) have no text-fidelity detector behind them and therefore stay
PASS — this tool audits text/annotation fidelity, not geometry.

### Issue record schema

```json
{ "id": "D-014", "page": 2, "zone": "C7", "class": "font_glyph_corruption",
  "severity": "high", "confidence": 0.97, "status": "defect",
  "ref_text": "1/2", "cand_text": "1#8",
  "bbox_ref": [..], "bbox_cand": [..], "rendered_diff_score": 0.41,
  "cause": "...", "fix": "...", "message": "..." }
```

`zone` is the candidate drawing-grid cell (rows × columns, e.g. `C7`), parsed per-sheet from the
Creo border labels. `cause`/`fix` are per-class templates. Defects below `confidence_threshold`
get `status: "review"` instead of `"defect"`.

## Multi-view sheets (drawings placed differently)

A sheet often holds several drawing views, and a candidate (Creo) export may lay a view out at a
different position than the reference. The comparator handles this by **per-view registration**:
sequential RANSAC fits one local affine per consistently-moving group of text anchors, so a
relocated *view* is matched and absorbed (not flagged), while a single label that shifted
*relative to its own view* is still reported as `text_misplacement`. A view earns its own transform
only with ≥ `registration_min_view_anchors` matching anchors, so a lone moved run never
masquerades as a moved view. Disable with `registration_multi_view: false` for one global affine.
See `backend/comparator/register.py`.

## Configuration

All tolerances, symbol equivalences, ignore-regions, and cause/fix templates live in
[`backend/config.yaml`](backend/config.yaml) — no magic numbers in code. Key knobs:
`position_tolerance_pts`, `overlap_ratio_threshold`, `pixel_diff_threshold`,
`confidence_threshold`, `render_dpi`, `symbol_equivalences`. Operational settings (CORS, upload
limits, worker concurrency, job TTL) are environment variables — see `backend/.env.example`.

## Module map (`backend/comparator/`)

`config.py` · `extract.py` · `register.py` (affine + zone grid) · `normalize.py` ·
`match.py` (Hungarian) · `render_compare.py` (the rendered-glyph rule) · `detect.py` ·
`report.py` · `pipeline.py` (the shared entry point used by the API).
