# Agentic Test Factory — MVP

Paste a GitHub repo → it's forked to your profile, the app understands it, generates only
meaningful tests through an **agent ⇄ Kane verification loop**, and opens a PR.

This MVP runs the full pipeline UI end-to-end in **DEMO mode** (no credentials needed) so you
can see the agent loop self-correct live. Flip `DEMO_MODE=false` to wire real fork/clone +
Kane + Claude.

See `../ARCHITECTURE.md` for the full design (8 phases, meaningfulness gate, MCP wiring).

## Layout

```
backend/   FastAPI orchestrator — run state machine, WebSocket events, phases, services
frontend/  Next.js + Tailwind — modern Claude-style UI, live run view, loop stream
```

## Run it (two terminals)

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DEMO_MODE=true by default
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                    # http://localhost:3000
```

Open http://localhost:3000, click **Start run**, and watch the pipeline + agent⇄Kane loop stream.

## Going live (DEMO_MODE=false)

Set in `backend/.env`:
- `GITHUB_TOKEN` — repo scope (fork/clone/PR). `gh` CLI must be installed.
- `LT_USERNAME`, `LT_ACCESS_KEY` — Kane + HyperExecute.
- `ANTHROPIC_API_KEY` — agent synthesis/repair.

The live path is wired in `backend/app/runner.py::_run_live` and the `services/` modules.

## MVP scope

Implemented: P1 fork/clone · P2 repo intel · P3 existing-test inventory · P4 scenarios ·
P6 agent⇄Kane loop · P8 commit + PR · live WebSocket streaming.
Deferred to v1 (see ARCHITECTURE.md): P5 meaningfulness gate (full), P7 HyperExecute
regression, Postgres persistence, AUT auto-provisioning.
