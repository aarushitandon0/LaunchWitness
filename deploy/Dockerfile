# Build context: repo root (see deploy/docker-compose.yml).

# --- 1) Build the React frontend ---
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2) FastAPI app (serves API, internal endpoints, built frontend, seller sites) ---
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
# Claude fixture mode (CLAUDE_MODE=fixture) reads saved responses from here.
COPY backend/tests/fixtures ./tests/fixtures
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 lw && mkdir -p /app/backend/data && chown lw /app/backend/data
USER lw
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
# Only Caddy can reach this port (it is not published), so trusting forwarded headers is safe.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
