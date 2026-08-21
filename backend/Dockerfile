FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate
RUN pnpm install --frozen-lockfile

COPY frontend /app/frontend
RUN pnpm build


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY backend/requirements.runtime.lock.txt /tmp/requirements.runtime.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.runtime.lock.txt

COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
COPY backend /app/backend
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
