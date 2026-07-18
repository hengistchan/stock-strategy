FROM node:22-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
COPY backend/stock_strategy ./backend/stock_strategy
RUN cd frontend && npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STOCK_STRATEGY_PROJECT_ROOT=/app \
    OPEND_HOST=host.docker.internal \
    OPEND_PORT=11111
WORKDIR /app
COPY backend ./backend
COPY examples ./examples
COPY strategies ./strategies
COPY --from=frontend-builder /app/backend/stock_strategy/web_dist ./backend/stock_strategy/web_dist
RUN python -m pip install --no-cache-dir './backend[opend,web]'
EXPOSE 8000
CMD ["python", "-m", "stock_strategy.web", "--host", "0.0.0.0", "--port", "8000"]
