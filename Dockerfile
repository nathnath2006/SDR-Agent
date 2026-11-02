# Image unique : front compilé (Node) servi par l'API Python.
#   docker build -t tamtam-agent .
#   docker run -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" -v "$PWD/outputs:/app/outputs" tamtam-agent
# Sur Cloud Run, le port vient de $PORT et les données d'un bucket monté (TAMTAM_STORE).

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TAMTAM_ROOT=/app PORT=8000 TAMTAM_MODELS=/app/models
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[api,anthropic,gemini]"
# Modèle sémantique intégré à l'image : pas de téléchargement au démarrage.
RUN python -c "from tamtam_agent.semantic import preload; preload()"
COPY --from=web /web/dist web/dist
RUN mkdir -p data outputs
EXPOSE 8000
CMD ["sh", "-c", "exec tamtam-agent serve --host 0.0.0.0 --port ${PORT}"]
