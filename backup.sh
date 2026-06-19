#!/bin/bash
# Backup diário do banco SQLite. Executar do diretório raiz do projeto.
# Cron sugerido (crontab -e):
#   0 2 * * * cd /caminho/do/projeto && ./backup.sh >> /var/log/estoque-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STORAGE_DIR="$SCRIPT_DIR/storage"
BACKUP_DIR="$STORAGE_DIR/backups"
DB="$STORAGE_DIR/estoque.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB" ]; then
    echo "[$TIMESTAMP] AVISO: banco de dados não encontrado em $DB"
    exit 0
fi

cp "$DB" "$BACKUP_DIR/estoque_$TIMESTAMP.db"
echo "[$TIMESTAMP] Backup criado: estoque_$TIMESTAMP.db"

# Manter apenas os últimos 30 backups
EXCESSO=$(ls -t "$BACKUP_DIR"/estoque_*.db 2>/dev/null | tail -n +31)
if [ -n "$EXCESSO" ]; then
    echo "$EXCESSO" | xargs rm -f
    echo "[$TIMESTAMP] Backups antigos removidos."
fi
