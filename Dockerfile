# Python 3.12 slim — python-oracledb thin mode needs NO Oracle Instant Client.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN chmod +x ./scripts/fly_entrypoint.sh

EXPOSE 8000

# The entrypoint materialises the ADB wallet from secrets (Fly), then runs the
# process command below (or the per-process command from fly.toml / compose).
ENTRYPOINT ["./scripts/fly_entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
