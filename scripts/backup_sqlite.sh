#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/estoquepro/app}"
BACKUP_DIR="${BACKUP_DIR:-/opt/estoquepro/backups}"
DB_PATH="$APP_DIR/data/estoque.db"

mkdir -p "$BACKUP_DIR"

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "ERRO: sqlite3 nao esta instalado no host. Instale com: sudo apt install -y sqlite3" >&2
  exit 1
fi

if [ ! -f "$DB_PATH" ]; then
  echo "AVISO: banco nao encontrado em $DB_PATH. Backup ignorado."
  exit 0
fi

BACKUP_FILE="$BACKUP_DIR/estoque-$(date +%F_%H-%M-%S).db"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Mantem backups dos ultimos 30 dias.
find "$BACKUP_DIR" -type f -name 'estoque-*.db' -mtime +30 -delete

echo "Backup criado: $BACKUP_FILE"
