FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# MVP: API and the reliable queue worker share this container. May be disabled for a dedicated worker.
ENV CHANNEL_WORKER_ENABLED=true
ENV WORKER_CONCURRENCY=1
ENV WORKER_POLL_INTERVAL_S=1

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
