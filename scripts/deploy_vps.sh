#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/estoquepro/app}"
BRANCH="${BRANCH:-main}"

cd "$APP_DIR"

if [ -x "scripts/backup_sqlite.sh" ]; then
  APP_DIR="$APP_DIR" BACKUP_DIR="/opt/estoquepro/backups" ./scripts/backup_sqlite.sh || true
else
  echo "AVISO: script de backup nao encontrado ou sem permissao de execucao. Continuando deploy."
fi

git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

mkdir -p data/uploads data/exports data/backups
sudo chown -R 1000:1000 data

docker compose build --pull
docker compose up -d
docker image prune -f

docker compose ps
