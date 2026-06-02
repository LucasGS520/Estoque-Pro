"""Migração: adiciona tabela `setores` e colunas `setor_id`/`retirado_por` em `movimentacoes`.

Seguro para executar mais de uma vez — verifica existência antes de criar.

Uso:
    python -m migration.migrate_setor
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import inspect, text

from core.database import get_session_factory, init_db


def _coluna_existe(conn, tabela: str, coluna: str) -> bool:
    result = conn.execute(text(f"PRAGMA table_info({tabela})"))
    return any(row[1] == coluna for row in result)


def _tabela_existe(conn, tabela: str) -> bool:
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": tabela},
    )
    return result.fetchone() is not None


def run() -> None:
    init_db()
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        conn = session.connection()

        if not _tabela_existe(conn, "setores"):
            conn.execute(text("""
                CREATE TABLE setores (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome      VARCHAR(100) NOT NULL UNIQUE,
                    descricao TEXT,
                    ativo     BOOLEAN NOT NULL DEFAULT 1,
                    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("  [OK] Tabela 'setores' criada.")
        else:
            print("  [--] Tabela 'setores' já existe, ignorando.")

        if not _coluna_existe(conn, "movimentacoes", "setor_id"):
            conn.execute(text(
                "ALTER TABLE movimentacoes ADD COLUMN setor_id INTEGER REFERENCES setores(id)"
            ))
            print("  [OK] Coluna 'setor_id' adicionada em 'movimentacoes'.")
        else:
            print("  [--] Coluna 'setor_id' já existe, ignorando.")

        if not _coluna_existe(conn, "movimentacoes", "retirado_por"):
            conn.execute(text(
                "ALTER TABLE movimentacoes ADD COLUMN retirado_por VARCHAR(200)"
            ))
            print("  [OK] Coluna 'retirado_por' adicionada em 'movimentacoes'.")
        else:
            print("  [--] Coluna 'retirado_por' já existe, ignorando.")

        session.commit()
        print("\nMigração concluída com sucesso.")


if __name__ == "__main__":
    run()
