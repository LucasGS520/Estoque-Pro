""" Configuração de banco de dados e sessões SQLAlchemy.

Expõe o `Base` declarativo dos modelos, cria o engine SQLite sob demanda e
fornece factories de sessão para telas, serviços e rotinas de migração.
"""

from sqlalchemy import create_engine
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


def init_db():
    """Cria as tabelas do banco caso elas ainda não existam."""
    from core import models  # noqa: F401 — registra todos os modelos no Base
    Base.metadata.create_all(get_engine())
