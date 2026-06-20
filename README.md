# KaneCLI TestPilot

**Stronger tests for open source.** Point it at any GitHub project and it forks the repo,
learns how the app works, generates *only* meaningful end-to-end tests, **proves each one in a
real browser** via the [Kane CLI](https://www.testmuai.com/kane-cli/) verification loop, and
opens a pull request — with a Kane-powered CI workflow included.

What lands in the PR is **proven, not guessed**: every test is driven through a live browser and
must produce an observable result, so flaky or hallucinated tests are dropped before they ship.

## How it works — the 8-phase pipeline

| Phase | Does |
|---|---|
| **P1 — Fork & clone** | Forks the repo to your profile (or clones in place if you own it) |
| **P2 — Repo intelligence** | Reads the codebase to understand routes, components, behaviors |
| **P3 — Existing-test inventory** | Finds current tests, so new ones fill gaps instead of duplicating |
| **P4 — Candidate scenarios** | Proposes scenarios (broad for greenfield repos, gap-filling otherwise) |
| **P5 — Meaningfulness gate** | Drops weak/false-green candidates (intent match + assertion quality) |
| **P6 — Agent ⇄ Kane loop** | Kane drives the live app in a browser to verify each scenario for real |
| **P7 — Kane CI workflow** | Commits a GitHub Actions workflow that re-verifies the suite with Kane |
| **P8 — Commit & open PR** | Commits the verified suite and opens the pull request |

**Two modes:** *Auto* (verify every meaningful scenario and open a PR, hands-off) or
*Human-in-the-loop* (review the proposed scenarios and pick which ones Kane verifies).

## Layout

```
backend/   FastAPI orchestrator — run state machine, WebSocket events, phases, services
frontend/  Next.js + Tailwind UI — dark mode by default, live run view, loop stream
```

## Run it locally (two terminals)

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DEMO_MODE=true by default
uvicorn app.main:app --port 8000
```

**Frontend**
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                    # http://localhost:3000
```

Open http://localhost:3000, start a run, and watch the pipeline + agent⇄Kane loop stream live.
`DEMO_MODE=true` simulates the phases (no credentials needed) so you can see the UI immediately.

## Going live (`DEMO_MODE=false`)

Set the real credentials in `backend/.env`:

| Var | Purpose |
|---|---|
| `GITHUB_TOKEN` | PAT with `repo` + `workflow` scope — fork, clone, push, open PR |
| `LT_USERNAME`, `LT_ACCESS_KEY` | LambdaTest / Kane authentication |
| `ANTHROPIC_API_KEY` | Scenario proposal + test synthesis/repair |
| `KANE_CLOUD` | `false` = local headless Chrome · `true` = run on the LambdaTest grid (no local Chrome) |

Locally, `kane-cli` and `gh` use your logged-in profiles unless these are set. See
`backend/.env.example` for the full list (test style, concurrency, workspace dir).

### Kane execution modes
- **Local headless** (`KANE_CLOUD=false`) — Kane launches Chrome on the host over CDP ports
  9222–9230, so concurrency caps at ~8. Best for local development.
- **Cloud grid** (`KANE_CLOUD=true`) — Kane connects to the LambdaTest grid via a Playwright
  `ws-endpoint`; the browser runs remotely, so **no Chrome is needed on the host** and each run
  gets a session URL with video/console/network. This is the mode used for hosting.

## Deployment

See **[DEPLOY.md](./DEPLOY.md)** — a one-click Render Blueprint ([`render.yaml`](./render.yaml))
deploys the Dockerized API (cloud-grid Kane, no Chrome) plus the Next.js frontend.
