#!/usr/bin/env bash
# Plumo dev commands for Linux and macOS. Same commands as dev.cmd on Windows.
#
#   ./dev.sh setup    create .venv, install dependencies, copy .env
#   ./dev.sh db       start PostgreSQL in Docker (docker compose service "db")
#   ./dev.sh db-stop  stop PostgreSQL
#   ./dev.sh seed     apply migrations and load the demo business
#   ./dev.sh run      start the API on http://127.0.0.1:8000/docs
#   ./dev.sh worker   start the channel worker (Telegram/Instagram replies), separate terminal
#   ./dev.sh operator create --email a@b.kg --business "Demo Realty"   dashboard sign-in
#   ./dev.sh demo     chat with the agent in the terminal
#   ./dev.sh test     run all tests
#   ./dev.sh eval     live 10-turn dialog with the real model
#   ./dev.sh lint     ruff: syntax errors, undefined names, unused imports
#   ./dev.sh voice    live ElevenLabs TTS/STT check in phone quality (spends credits)
#   ./dev.sh bench    compare models on 55 sales scenarios (spends credits, ~$1.6)
#   ./dev.sh up       db + seed + run
#
# PYTHON=python3.12 ./dev.sh setup picks a specific interpreter.

set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
export PYTHONIOENCODING=utf-8

usage() {
    echo "Usage: ./dev.sh <setup|db|db-stop|seed|run|worker|operator|demo|test|eval|lint|voice|bench|up>"
    echo "  first time:  ./dev.sh setup"
    echo "  every day:   ./dev.sh up      (then open http://127.0.0.1:8000/docs)"
    exit 1
}

cmd="${1:-}"
[ -z "$cmd" ] && usage
shift

if [ "$cmd" != "setup" ] && [ ! -x "$PY" ]; then
    echo ".venv not found. Run: ./dev.sh setup"
    exit 1
fi

case "$cmd" in
    setup)
        if [ ! -x "$PY" ]; then
            "${PYTHON:-python3}" -m venv .venv || {
                echo "Python 3.12+ with venv not found. Install it or set PYTHON=python3.12"
                exit 1
            }
        fi
        "$PY" -m pip install --upgrade pip
        "$PY" -m pip install -e ".[dev]"
        if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
        echo
        echo "Ready. Next: ./dev.sh up"
        ;;
    db)
        docker compose up -d --wait db
        ;;
    db-stop)
        docker compose stop db
        ;;
    seed)
        "$PY" -m app.seed
        ;;
    run)
        echo "Swagger: http://127.0.0.1:8000/docs"
        exec "$PY" -m uvicorn app.main:app --reload
        ;;
    worker)
        echo "Channel worker: Ctrl+C to stop. Unfinished jobs continue after a restart."
        exec "$PY" -m app.worker
        ;;
    operator) exec "$PY" -m app.operators "$@" ;;
    demo) exec "$PY" -m app.demo --interactive ;;
    test) exec "$PY" -m pytest "$@" ;;
    lint) exec "$PY" -m ruff check src tests alembic ;;
    bench) exec "$PY" -m app.bench "$@" ;;
    voice) exec "$PY" -m app.voice_probe "$@" ;;
    eval) exec "$PY" -m app.eval_live "$@" ;;
    up)
        "$0" db
        "$0" seed
        exec "$0" run
        ;;
    *) usage ;;
esac
