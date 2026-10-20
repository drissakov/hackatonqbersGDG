FROM node:22-bookworm-slim AS frontend-build
WORKDIR /source
COPY . .
RUN test -f frontend/package.json && test -f frontend/package-lock.json || \
    (echo 'D01 input missing: frontend/package.json and package-lock.json are required; no fallback frontend is generated.' >&2; exit 1)
WORKDIR /source/frontend
RUN npm ci
ARG VITE_TWOGIS_MAP_KEY=""
RUN VITE_API_BASE_URL=/api VITE_TWOGIS_MAP_KEY="$VITE_TWOGIS_MAP_KEY" npm run build && \
    test -f dist/index.html

FROM python:3.12-slim-bookworm AS python-build
WORKDIR /build
COPY backend/requirements.txt backend/constraints.txt ./
RUN python -m pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production DEV_FIXTURE_MODE=false
WORKDIR /app
COPY --from=python-build /install /usr/local
COPY backend/app ./backend/app
COPY scripts ./scripts
COPY contracts ./contracts
COPY data/curated/poi-features.json ./data/curated/poi-features.json
COPY database/migrations ./database/migrations
COPY --from=frontend-build /source/frontend/dist ./frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=3)"
CMD ["python", "-m", "scripts.serve"]
