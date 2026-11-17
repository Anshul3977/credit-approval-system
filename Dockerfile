FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY data ./data
COPY scripts/start.sh /start.sh

RUN chmod 755 /start.sh \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/backend/staticfiles \
    && DJANGO_SECRET_KEY=collectstatic-placeholder DJANGO_DEBUG=false \
        python /app/backend/manage.py collectstatic --noinput \
    && chown -R appuser:appuser /app

WORKDIR /app/backend
USER appuser

EXPOSE 8000
ENTRYPOINT ["/start.sh"]
