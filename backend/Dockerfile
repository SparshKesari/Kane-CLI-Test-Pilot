# KaneCLI TestPilot — API image (thin).
# In production the API only DISPATCHES a GitHub Actions job (which runs the
# pipeline) and RELAYS its events to the browser. It does not run kane-cli, gh,
# git or Chrome — so this image is just Python + FastAPI. Tiny + fast + low RAM.
#
# (Local in-process execution, LOCAL_EXECUTION=true, needs the full toolchain —
#  use the backend dev setup in README.md, not this image.)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY backend/ ./

ENV PORT=8000 \
    DEMO_MODE=false \
    LOCAL_EXECUTION=false

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
