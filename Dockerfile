# Card Generator: AI-made language flashcards, saved to Anki through anki-manager.

FROM node:26-alpine AS frontend
WORKDIR /app
RUN npm install -g pnpm@11
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/card_generator ./card_generator
RUN pip install --no-cache-dir .
COPY --from=frontend /app/dist /app/static
ENV CARD_GENERATOR_STATIC=/app/static \
    CARD_GENERATOR_DATA=/data \
    HOME=/tmp \
    PYTHONUNBUFFERED=1
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "card_generator.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
