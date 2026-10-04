FROM python:3.12-slim

ARG APP_COMMIT_SHA=unknown
ENV APP_COMMIT_SHA=${APP_COMMIT_SHA}
LABEL org.opencontainers.image.revision=${APP_COMMIT_SHA}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/docker-entrypoint.sh scripts/deploy_radar.sh

ENTRYPOINT ["scripts/docker-entrypoint.sh"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
