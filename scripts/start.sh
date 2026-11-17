#!/bin/sh
# Boot path for Docker and for a native Render Python service.
# Free Render web services cannot run a worker or a pre-deploy command, so
# migrate (and, unless skipped, the sample ingest) happen here before the
# process binds to $PORT.
set -eu

if [ -f /app/backend/manage.py ]; then
  cd /app/backend
elif [ -f backend/manage.py ]; then
  cd backend
elif [ ! -f manage.py ]; then
  echo "manage.py not found" >&2
  exit 1
fi

attempt=0
until python manage.py migrate --noinput; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 15 ]; then
    echo "migrate failed" >&2
    exit 1
  fi
  sleep 2
done

# `command:` in docker-compose replaces the container command. The worker
# passes `celery ...` and must not also seed or start gunicorn.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

python manage.py ingest_data

port="${PORT:-8000}"
debug=$(printf '%s' "${DJANGO_DEBUG:-false}" | tr '[:upper:]' '[:lower:]')
case "$debug" in
  true|1|yes|on)
    exec python manage.py runserver "0.0.0.0:${port}"
    ;;
esac

workers="${WEB_CONCURRENCY:-1}"
exec gunicorn credit_system.wsgi:application \
  --bind "0.0.0.0:${port}" \
  --workers "$workers" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
