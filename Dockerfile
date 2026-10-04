FROM python:3.12-slim

ARG APP_COMMIT_SHA=unknown
LABEL org.opencontainers.image.revision=${APP_COMMIT_SHA}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN printf '%s\n' "${APP_COMMIT_SHA}" > /app/.build-revision

RUN chmod +x scripts/docker-entrypoint.sh scripts/deploy_radar.sh

ENTRYPOINT ["scripts/docker-entrypoint.sh"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
