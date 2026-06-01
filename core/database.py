from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import DATABASE_URL, DATA_DIR

Base = declarative_base()

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        DATA_DIR.mkdir(exist_ok=True)
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def init_db():
    from core import models  # noqa: F401 — registra todos os modelos no Base
    Base.metadata.create_all(get_engine())
