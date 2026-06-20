# Deploying KaneCLI TestPilot to Render

Two services, defined in [`render.yaml`](./render.yaml):

| Service | Type | What it runs |
|---|---|---|
| `kane-testpilot-api` | Docker | FastAPI + `kane-cli` in **cloud-grid mode** (browser runs on LambdaTest — no Chrome in the container) |
| `kane-testpilot-web` | Node | The Next.js frontend |

## 1. Push the deploy files

`render.yaml`, `backend/Dockerfile`, and `.dockerignore` must be on GitHub:

```bash
git add render.yaml backend/Dockerfile .dockerignore backend/app/main.py DEPLOY.md
git commit -m "chore: add Render deployment (cloud-grid kane)"
git push
```

## 2. Create the services

Render → **New** → **Blueprint** → pick `SparshKesari/Kane-CLI-Test-Pilot`.
Render reads `render.yaml` and creates both services. You'll be prompted for the
values marked `sync: false`:

**API (`kane-testpilot-api`)**
- `GITHUB_TOKEN` — a **Personal Access Token** with `repo` + `workflow` scope.
  (The container has no `gh login`, so it authenticates entirely via this token.)
- `ANTHROPIC_API_KEY`, `LT_USERNAME`, `LT_ACCESS_KEY` — your keys.
- `FRONTEND_ORIGIN` — the web URL, e.g. `https://kane-testpilot-web.onrender.com`.

**Web (`kane-testpilot-web`)**
- `NEXT_PUBLIC_API` — the API URL, e.g. `https://kane-testpilot-api.onrender.com`.
  (Baked in at build time; the WebSocket URL is derived from it automatically.)

> The two URLs reference each other. Render assigns
> `https://<service-name>.onrender.com` when the name is free. If a name was taken
> and Render added a suffix, copy the **actual** URLs from the dashboard, update
> `NEXT_PUBLIC_API` / `FRONTEND_ORIGIN`, then **Manual Deploy → Clear build cache
> & deploy** the web service (so the new API URL is re-baked).

## 3. Verify

- API health: `https://<api>.onrender.com/api/health` → `{"ok": true, "demo_mode": false}`
- Open the web URL, start a run against a known-good public app, watch the live loop.

## Notes
- **Cloud-grid validation:** most local testing was headless-local. Confirm one
  real run verifies on the grid (returns an LT session URL). If `--agent` +
  `--ws-endpoint` misbehaves, that's the thing to debug first.
- **Concurrency:** the local ~8 CDP-port ceiling is gone; the real cap is your
  LambdaTest parallel-session plan. Tune `KANE_CONCURRENCY` to match.
- **Access:** there's no login. BYOC isn't wired up, so the API runs on the keys
  you set above — anyone with the URL spends them. Add HTTP Basic Auth at the
  edge or keep the URL private if that matters.
- **State** is in-memory; a redeploy/restart clears run history (PRs already
  opened are unaffected).
