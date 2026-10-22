#!/bin/sh
set -eu

# Free instances have an ephemeral filesystem, so migrate on every start.
python manage.py migrate --noinput
exec gunicorn documind.wsgi:application \
    --bind "0.0.0.0:${PORT:-10000}" \
    --workers 1 --threads 2 --timeout 180 \
    --access-logfile - --error-logfile -
