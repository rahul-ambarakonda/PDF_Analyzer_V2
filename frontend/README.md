# Creo PDF Text-Fidelity Comparator — Frontend

React + TypeScript (Vite) SPA for the comparator API. Pick a **reference** folder and a **Creo**
folder of PDFs; the app uploads them, polls the async comparison job, and renders an aggregated
report with a per-file results table linking to each pair's self-contained HTML report.

## Stack

- **React 18 + TypeScript (strict)** + **Vite 5**
- **TanStack Query v5** — server state + the job polling loop
- **Zod** — runtime-validates every API response (types via `z.infer`)
- **ESLint (flat) + Prettier**

## Develop

```bash
npm install
npm run dev          # http://localhost:5173  (proxies /api → http://localhost:8000)
```

Run the backend alongside it: `cd ../backend && uvicorn app.main:app --port 8000`.

| Script | Purpose |
|---|---|
| `npm run dev` | Vite dev server (HMR) with `/api` proxied to the backend |
| `npm run build` | Type-check (`tsc -b`) + production build to `dist/` |
| `npm run preview` | Serve the built `dist/` locally |
| `npm run typecheck` / `lint` / `format` | Quality gates |

## Configuration

Client env vars (prefix `VITE_`, see `.env.example`):

- `VITE_API_BASE_URL` — backend base URL. **Empty = same-origin** (recommended: behind CloudFront
  or one reverse proxy that routes `/api/*` to the backend). Set an absolute URL only for a
  cross-origin API (then add the SPA origin to the backend's `APP_CORS_ALLOW_ORIGINS`).
- `VITE_DEV_API_TARGET` — dev-only proxy target (default `http://localhost:8000`).

## Architecture

```
src/
├── lib/
│   ├── api/client.ts      # typed fetch wrapper → ApiError + Zod-validated payloads
│   ├── api/comparison.ts  # startComparison() / getJob() / reportHtmlUrl()
│   ├── schemas.ts         # Zod schemas mirroring backend/app/api/schemas.py
│   ├── report.ts          # JobResponse → aggregated ReportModel
│   └── format.ts          # presentation + folder-input helpers
├── hooks/                 # useStartComparison (mutation), useJob (polling query)
├── features/comparison/   # ComparisonWorkspace + Source/Report/Table components
├── components/ui/          # presentational primitives (Modal, Spinner, StatusPill, FormatSelect)
└── providers/QueryProvider.tsx
```

Flow: `POST /api/v1/compare` (multipart) → `useJob` polls `GET /api/v1/jobs/{id}` every 1.5 s until
terminal → `buildReportModel` aggregates `job.pairs` → table rows link to
`/api/v1/jobs/{id}/report/{name}`.

## Deploy (S3 + CloudFront)

1. `npm run build` → upload `dist/` to an S3 bucket.
2. CloudFront distribution:
   - **Default behavior** → the S3 bucket; SPA fallback (map 403/404 to `/index.html`, 200).
   - **`/api/*` behavior** → the backend origin (EC2/ALB). Same-origin ⇒ no CORS, no
     `VITE_API_BASE_URL` needed.
   - Cache `/assets/*` long (immutable, fingerprinted); don't cache `index.html`.

Self-hosted alternative: serve the built `dist/` from any static web server (nginx/Caddy/etc.) with
an SPA history fallback to `/index.html`, and route `/api/*` to the backend.
