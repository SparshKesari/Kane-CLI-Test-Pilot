# Deploying KaneCLI TestPilot

## Architecture: the pipeline runs in GitHub Actions

The heavy work (clone → propose → verify with Kane → commit → PR) runs in a
**GitHub Actions job** (`.github/workflows/pipeline.yml`), which has 7GB RAM and
free unlimited minutes on a public repo. The hosted services are thin:

| Service | Role | Hosting |
|---|---|---|
| `kane-testpilot-api` (Docker, Python) | **Dispatches** a CI job per run and **relays** its events to the browser. Tiny RAM. | Render **free** |
| Frontend (Next.js) | The UI | **Vercel** (instant, no cold start) |
| GitHub Actions job | Runs the actual P1–P8 pipeline; streams events back to the API | GitHub (free) |

```
Browser ──WS──> API ──workflow_dispatch──> GitHub Actions job (7GB, free)
   ▲             ▲                                  │
   └── live ─────┴──── POST /ingest (events+snapshot) ┘
                       GET  /control (selection/abort)
```

## 1. Add GitHub Actions secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `TESTPILOT_GH_TOKEN` | GitHub PAT with `repo` + `workflow` scope (fork/clone/push/PR) |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `LT_USERNAME` | LambdaTest username |
| `LT_ACCESS_KEY` | LambdaTest access key |
| `INGEST_SECRET` | any long random string — **must match** the API's `INGEST_SECRET` |

> `pipeline.yml` must be on the **default branch** (`main`) for `workflow_dispatch`
> to be callable. Merge this branch (or push the workflow to `main`) before runs work.

## 2. Deploy the API on Render (Blueprint)
Render → **New → Blueprint** → pick the repo. It reads `render.yaml` and creates
the **`kane-testpilot-api`** service (free). Fill the prompted `sync: false` values:

| Key | Value |
|---|---|
| `GITHUB_TOKEN` | a PAT with `repo` + `workflow` (to dispatch the job) |
| `INGEST_SECRET` | the **same** random string as the GitHub secret above |
| `PUBLIC_BASE_URL` | this API's own URL, e.g. `https://kane-testpilot-api.onrender.com` |
| `FRONTEND_ORIGIN` | the Vercel URL, e.g. `https://kane-cli-test-pilot.vercel.app` |

(`RUNNER_REPO`, `RUNNER_REF`, `LOCAL_EXECUTION=false`, `DEMO_MODE=false` are preset in `render.yaml`.)

## 3. Deploy the frontend on Vercel
Vercel → **Add New → Project** → import the repo, then:
- **Root Directory:** `frontend`
- **Framework:** Next.js (auto-detected)
- **Env var:** `NEXT_PUBLIC_API` = the API URL (e.g. `https://kane-testpilot-api.onrender.com`)
- Deploy → you get a `…vercel.app` URL (the API's CORS already allows `*.vercel.app`).

> `NEXT_PUBLIC_API` is baked at build time — if you change it, redeploy the Vercel
> project. The API host is interchangeable (it's a plain Docker image); to move it,
> update `PUBLIC_BASE_URL` (on the API), `NEXT_PUBLIC_API` (Vercel), and the CORS
> regex in `main.py` if the new host isn't `*.onrender.com` / `*.vercel.app`.

## 3. Verify
1. API health: `https://<api>.onrender.com/api/health` → `{"ok":true,"demo_mode":false,"local_execution":false}`
2. Open the web URL, start a run.
3. Watch it: the API dispatches the workflow (see the run under the repo's
   **Actions** tab) and the UI streams events live as the job reports back.

## Notes
- **Free tier is fine now** — the API only relays, so 512MB is plenty. The
  *compute* lives in CI (7GB). Cold starts only add a one-time wake delay; the
  CI job retries its callbacks so no events are lost.
- **Local dev** still runs in-process: set `LOCAL_EXECUTION=true` in `backend/.env`
  (the default) and run backend + frontend as in the README.
- **State** is in-memory snapshots; an API restart drops history, but the CI job
  keeps running and still opens the PR.
