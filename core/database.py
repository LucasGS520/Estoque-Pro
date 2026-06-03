""" Configuração de banco de dados e sessões SQLAlchemy.

Expõe o `Base` declarativo dos modelos, cria o engine SQLite sob demanda e
fornece factories de sessão para telas, serviços e rotinas de migração.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import DATABASE_URL, DATA_DIR

Base = declarative_base()

_engine = None


def get_engine():
    """Retorna o engine SQLAlchemy configurado para o SQLite local.

    Cria a pasta de dados quando necessário e mantém um engine singleton por
    processo. `check_same_thread=False` evita conflito com o ciclo do Streamlit.
    """
    global _engine
    if _engine is None:
        DATA_DIR.mkdir(exist_ok=True)
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory():
    """Cria uma factory de sessões vinculada ao engine da aplicação."""
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def run_schema_migrations(engine):
    """Adiciona colunas novas à tabela itens sem destruir dados existentes.

    Idempotente: ignora erros de "duplicate column name" do SQLite.
    Após adicionar as colunas, copia valores legados de estoque_minimo/ideal
    para os campos manuais/vigentes dos itens que já tinham valores definidos.
    """
    new_columns = [
        "ALTER TABLE itens ADD COLUMN estoque_minimo_sugerido INTEGER",
        "ALTER TABLE itens ADD COLUMN estoque_ideal_sugerido INTEGER",
        "ALTER TABLE itens ADD COLUMN estoque_minimo_manual INTEGER",
        "ALTER TABLE itens ADD COLUMN estoque_ideal_manual INTEGER",
        "ALTER TABLE itens ADD COLUMN data_definicao_minimo_manual DATETIME",
        "ALTER TABLE itens ADD COLUMN data_definicao_ideal_manual DATETIME",
        "ALTER TABLE itens ADD COLUMN estoque_minimo_vigente INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE itens ADD COLUMN estoque_ideal_vigente INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE itens ADD COLUMN origem_minimo VARCHAR(20)",
        "ALTER TABLE itens ADD COLUMN origem_ideal VARCHAR(20)",
    ]
    with engine.connect() as conn:
        for stmt in new_columns:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                # Coluna já existe — ignorar
                conn.rollback()

        # Migração de dados: trata estoque_minimo/ideal legados como valores manuais.
        # Só migra linhas onde estoque_minimo_vigente ainda está zerado E estoque_minimo > 0.
        conn.execute(text("""
            UPDATE itens
            SET
                estoque_minimo_manual   = estoque_minimo,
                estoque_ideal_manual    = estoque_ideal,
                estoque_minimo_vigente  = estoque_minimo,
                estoque_ideal_vigente   = estoque_ideal,
                origem_minimo           = 'Manual',
                origem_ideal            = 'Manual'
            WHERE estoque_minimo > 0
              AND (estoque_minimo_vigente IS NULL OR estoque_minimo_vigente = 0)
        """))
        conn.commit()

        # Garante unicidade de revisões por item/período: remove duplicatas mantendo
        # o registro mais antigo por (item_id, periodo_descricao), depois cria índice.
        conn.execute(text("""
            DELETE FROM revisoes_mensais
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM revisoes_mensais
                GROUP BY item_id, periodo_descricao
            )
        """))
        conn.commit()
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_revisao_item_periodo "
            "ON revisoes_mensais (item_id, periodo_descricao)"
        ))
        conn.commit()


def init_db():
    """Cria as tabelas do banco caso elas ainda não existam e executa migrações de schema."""
    from core import models  # noqa: F401 — registra todos os modelos no Base
    engine = get_engine()
    Base.metadata.create_all(engine)
    run_schema_migrations(engine)
