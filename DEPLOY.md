# Deploying KaneCLI TestPilot

## Architecture: the pipeline runs in GitHub Actions

The heavy work (clone → propose → verify with Kane → commit → PR) runs in a
**GitHub Actions job** (`.github/workflows/pipeline.yml`), which has 7GB RAM and
free unlimited minutes on a public repo. The hosted services are thin:

| Service | Role | Hosting |
|---|---|---|
| `kane-testpilot-api` (Docker, Python) | **Dispatches** a CI job per run and **relays** its events to the browser. Tiny RAM. | Render **free** |
| `kane-testpilot-web` (Next.js) | The UI | Render **free** |
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

## 2. Deploy on Render (Blueprint)
Render → **New → Blueprint** → pick the repo. It reads `render.yaml` and creates
both services (both **free**). Fill the prompted `sync: false` values:

**`kane-testpilot-api`**
| Key | Value |
|---|---|
| `GITHUB_TOKEN` | a PAT with `actions:write` + `workflow` (to dispatch the job) |
| `INGEST_SECRET` | the **same** random string as the GitHub secret above |
| `PUBLIC_BASE_URL` | this API's own URL, e.g. `https://kane-testpilot-api.onrender.com` |
| `FRONTEND_ORIGIN` | the web URL, e.g. `https://kane-testpilot-web.onrender.com` |

(`RUNNER_REPO`, `RUNNER_REF`, `LOCAL_EXECUTION=false`, `DEMO_MODE=false` are preset in `render.yaml`.)

**`kane-testpilot-web`**
| Key | Value |
|---|---|
| `NEXT_PUBLIC_API` | the API URL, e.g. `https://kane-testpilot-api.onrender.com` |

> If Render appends a suffix to a service name, copy the real URLs from the
> dashboard, update `PUBLIC_BASE_URL` / `FRONTEND_ORIGIN` / `NEXT_PUBLIC_API`,
> and redeploy the **web** service with **Clear build cache** (NEXT_PUBLIC_* is
> baked at build time).

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
