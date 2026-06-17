# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **Creo/CAD PDF text-fidelity comparator**: it compares a *reference* drawing PDF against a
*candidate* (Creo-exported) PDF and reports text/annotation fidelity defects. Geometry comparison
is **out of scope**. It is 100% offline and rule-based (PyMuPDF + scikit-image + scipy — **no model
calls**, no OpenCV).

The repo is a **monorepo**. Everything currently lives under `backend/`; a `frontend/` will be
added as a sibling. There is no top-level `SPEC.md`, `main.py`, or `core/` package — earlier
versions of this file referenced those; they are gone.

```
backend/
├── app/            # FastAPI service (the production API layer)
│   ├── main.py         # create_app() factory; lifespan builds the job store + worker
│   ├── config.py       # pydantic-settings Settings (env vars, APP_ prefix)
│   ├── logging.py      # structured JSON logging + X-Request-ID middleware
│   ├── errors.py       # ApiError + handlers → uniform {error, detail, request_id}
│   ├── api/            # routes.py (endpoints) + schemas.py (pydantic responses)
│   ├── jobs/           # models.py, store.py (in-memory, evicting), worker.py (ThreadPoolExecutor)
│   └── services/       # comparison.py — bridges the worker to the comparator pipeline
├── comparator/     # the comparison engine (the heart; see below)
└── config.yaml     # externalized tolerances / symbol equivalences / cause-fix templates
```

## Running

All commands run from `backend/`.

```bash
cd backend
python -m venv venv && source venv/bin/activate     # repo already has a venv/ at the root
pip install -r requirements.txt

uvicorn app.main:app --reload                        # http://127.0.0.1:8000 (OpenAPI at /docs)
```

The comparator's report renderer (PIL `ImageFont`) uses the DejaVu fonts when present; install
`fonts-dejavu-core` on the host for faithful glyph rendering.

## The comparator engine (`backend/comparator/`)

Single shared entry point: `pipeline.run_comparison(reference, candidate, config) -> report dict`,
and `pipeline.write_reports(...)` to persist `report.json` + `report.html`. Per-page detection is
`detect.analyze_page(...)`. Module roles:

- `extract.py` — pull text runs (with bboxes, fonts) from each page.
- `register.py` — **per-view registration**: sequential RANSAC fits one local affine per
  consistently-moving group of text anchors, so a relocated *view* is absorbed (not flagged) while
  a label moved *relative to its view* still trips `text_misplacement`. A view needs
  ≥ `registration_min_view_anchors` anchors to earn its own transform (`registration_multi_view:
  false` falls back to one global affine).
- `match.py` — pairs reference↔candidate runs with the scipy **Hungarian** assignment
  (`linear_sum_assignment`), cost = position + string-edit distance.
- `normalize.py` — `Normalizer` applies `symbol_equivalences`, trailing-zero/decimal/whitespace
  rules from config before string comparison.
- `render_compare.py` — **the core rule: the rendered glyph is ground truth.** A string mismatch
  escalates to `font_glyph_corruption` *only if the clip-rendered region also differs*. A
  candidate that renders correctly but extracts wrong text (broken ToUnicode / encoding artifact)
  is **suppressed**. A string-only comparison is never the sole test — do not weaken this.
- `detect.py` — produces the five defect classes: `missing_text`, `missing_annotation`,
  `text_overlap`, `text_misplacement`, `font_glyph_corruption`.
- `report.py` — `build_report` (the JSON dict + meta/counts), `render_html` (one Jinja2 string
  template; comparison images base64-inlined so the page is self-contained), `has_defects`.
- `config.py` — `Config.load(path)` typed config from `config.yaml`.

**Two taxonomies — do not conflate.** Each defect has a `class` (the five strings above).
Separately, defects are bucketed into 13 **audit categories**, and the page quality score (/100)
subtracts each *failed category's* weight (not per-issue). Geometry-only categories have no
detector and stay PASS by design.

## The API layer (`backend/app/`) — key invariants

- **Async, in-memory job model.** `POST /api/v1/compare` validates + pairs uploads by filename,
  creates a job, hands the PDF bytes to a `ThreadPoolExecutor` worker (`jobs/worker.py`), and
  returns **202 `{job_id}`**. Clients poll `GET /api/v1/jobs/{id}`; reports are fetched per pair as
  JSON (`/pairs/{name}`) or self-contained HTML (`/report/{name}`).
- **Results live in memory only** (`jobs/store.py`), with TTL + max-count eviction to bound memory.
  No S3/DB by design.
- **Single Uvicorn worker, single instance — required, not incidental.** The job store is
  process-local, so it must not be sharded across processes. Do **not** add Uvicorn workers or a
  second instance without first externalizing state (Redis for jobs, S3 for artifacts). CPU scales
  via `APP_WORKER_CONCURRENCY` (threads — the CV code releases the GIL). See
  `backend/README.md` "Scaling boundary".
- The worker calls `services/comparison.py`, which writes the uploaded bytes to a short-lived temp
  dir, runs the pipeline, reads `report.json` + `report.html` back into memory, and deletes the
  dir. After it returns, nothing for the pair is on disk.

## Conventions

- **Engine tuning** lives in `config.yaml` (tolerances in **PDF points** for text;
  `pixel_diff_threshold` etc. in normalized pixel space). **Operational** settings (CORS, upload
  limits, worker concurrency, job TTL/cap) are env vars with the `APP_` prefix — see
  `app/config.py` and `.env.example`. Keep magic numbers out of code.
- Deploy target is a single EC2 t2/t3.small (~2 GB). Defaults (worker concurrency, upload caps)
  in `app/config.py` are sized for that box; run with a single Uvicorn worker (the job store is
  in-process memory).
- When touching registration/affine code, preserve the degeneracy/fallback guards (a lone moved
  run must never masquerade as a moved view).
