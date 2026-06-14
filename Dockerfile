# ---- Stage 1: build the Flutter web client (served same-origin by the API) ----
# The mobile client lives in a separate public repo. We build its web target here
# so famo.io.vn serves both the app (at /) and the API (at its routes) — one
# origin, so the browser client needs no CORS.
FROM ghcr.io/cirruslabs/flutter:stable AS web
WORKDIR /src
ARG API_BASE_URL=https://famo.io.vn
ARG GOOGLE_CLIENT_ID=692858320760-0n5vkifgkqjoktqigpsjrhr8jqphjdka.apps.googleusercontent.com
RUN git clone --depth 1 https://github.com/vodongha/family-budget-app.git .
# Platform folders aren't committed in that repo — generate web/, then build.
RUN flutter create . --platforms=web \
 && flutter pub get \
 && grep -q google-signin-client_id web/index.html \
    || sed -i "s#</head>#  <meta name=\"google-signin-client_id\" content=\"${GOOGLE_CLIENT_ID}\">\n</head>#" web/index.html
RUN flutter build web --release \
      --dart-define=API_BASE_URL=${API_BASE_URL} \
      --dart-define=GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}

# ---- Stage 2: Python API (python-oracledb thin mode needs NO Instant Client) ----
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

# The built Flutter web client, served by FastAPI at "/".
COPY --from=web /src/build/web ./web

EXPOSE 8000

# The entrypoint materialises the ADB wallet from secrets (Fly), then runs the
# process command below (or the per-process command from fly.toml / compose).
ENTRYPOINT ["./scripts/fly_entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
