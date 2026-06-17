# PDF Text-Fidelity Comparator — Backend

Production FastAPI service that compares a **reference** drawing PDF against a **candidate**
(Creo-exported) PDF and reports text/annotation fidelity defects. The comparison engine lives in
the `comparator/` package (offline, rule-based: PyMuPDF + scikit-image + scipy — no model calls).

This service wraps that engine in an async JSON API: uploads are paired by filename, compared by a
background worker, and results (structured JSON + a self-contained HTML report) are held **in
memory** and fetched by a frontend.

```
backend/
├── app/            # FastAPI service (config, logging, jobs, api, services)
├── comparator/     # comparison engine
├── config.yaml     # comparator algorithm tuning (externalized)
└── .env.example    # operational settings (APP_* env vars)
```

## Quick start (local)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload              # http://127.0.0.1:8000  (docs at /docs)
```

The report renderer uses the DejaVu fonts when present — install `fonts-dejavu-core` on the host
for faithful glyph rendering.

## API

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness/readiness — `{status, version, env}`. |
| `POST /api/v1/compare` | Multipart upload: repeated `reference` + `candidate` PDF fields. Pairs by filename, enqueues a job, returns **202** `{job_id, status, pair_count, unmatched_*}`. |
| `GET /api/v1/jobs/{job_id}` | Job status + per-pair summaries (poll this). |
| `GET /api/v1/jobs/{job_id}/pairs/{name}` | Structured report JSON for one pair. |
| `GET /api/v1/jobs/{job_id}/report/{name}` | Rendered, self-contained **HTML report** for one pair. |

Job `status`: `queued → running → completed` (or `failed`). Each pair has its own status
(`pending`/`clean`/`defect`/`error`); a single bad pair does not fail the whole job. Errors return a
uniform `{error, detail, request_id}` body, and every response carries an `X-Request-ID`.

Example:

```bash
curl -s -X POST http://localhost:8000/api/v1/compare \
  -F "reference=@ref/A.pdf" -F "candidate=@cand/A.pdf"          # -> {"job_id": "...", ...}
curl -s http://localhost:8000/api/v1/jobs/<job_id>              # poll until "completed"
curl -s http://localhost:8000/api/v1/jobs/<job_id>/report/A.pdf # open the HTML report
```

## Configuration

Operational settings are environment variables with the `APP_` prefix (see `.env.example` and
`app/config.py`): CORS origins, upload limits, worker concurrency, job TTL/cap. Comparator
*algorithm* tuning stays in `config.yaml`.

## Deploy on EC2 (t2/t3.small)

Run directly with a process manager on the instance:

```bash
# on the box: install python3 + fonts-dejavu-core, then
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open security-group inbound TCP **8000** (or front it with nginx/ALB on 80/443). Use a systemd unit
(or `tmux`/`screen` for a quick start) to keep it running, and verify with
`curl http://<public-ip>:8000/health`. Keep **one worker** (see Scaling boundary).

## Scaling boundary (by design)

State (jobs, reports) lives in the API process's memory, so the service runs as a **single Uvicorn
worker** on a **single instance**. This is intentional for the current target. To scale horizontally
later: move job state to **Redis** and report artifacts to **S3**, then run multiple workers/instances
behind a load balancer. CPU throughput on one box scales via `APP_WORKER_CONCURRENCY` (CV threads).

## Not included (future work)

Durable storage (S3/DB), authentication, TLS termination, and the frontend (added as a
sibling `frontend/`).
