# KaneCLI TestPilot — API image.
# Runs FastAPI + kane-cli in CLOUD mode (KANE_CLOUD=true): the browser runs on
# the LambdaTest grid, so NO Chromium/Playwright browsers are needed here — the
# image stays small and the CDP-port concurrency ceiling disappears.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps:
#   git  → clone / commit / push the generated suite
#   gh   → fork the repo + open the PR (reads GITHUB_TOKEN/GH_TOKEN from env)
#   node → run kane-cli (installed globally from npm)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl git ca-certificates gnupg \
 && mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && npm install -g @testmuai/kane-cli playwright \
 && rm -rf /var/lib/apt/lists/*

# In a container there's no `gh auth login` keyring, so `git push` to the fork
# would have no credentials. This helper feeds the runtime GITHUB_TOKEN to git
# over https. ($GITHUB_TOKEN is expanded by git at push time, not at build.)
RUN git config --global credential.helper \
      '!f() { echo username=x-access-token; echo "password=$GITHUB_TOKEN"; }; f' \
 && git config --global user.name  "Kane TestPilot" \
 && git config --global user.email "testpilot@users.noreply.github.com"

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY backend/ ./

# Safe production defaults (overridable via Render env vars).
ENV PORT=8000 \
    DEMO_MODE=false \
    KANE_CLOUD=true \
    WORKSPACE_DIR=/tmp/workspaces

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
