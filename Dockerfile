# Two-stage build: UI with Node, then a slim Python runtime serving API + UI on one port.
FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY config/ config/
COPY data/ data/
COPY scripts/ scripts/
COPY --from=ui /ui/dist frontend/dist
RUN useradd --create-home appuser && mkdir -p runtime && chown appuser runtime
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.api:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
