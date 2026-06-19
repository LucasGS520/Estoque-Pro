"""Caminhos e URL de persistencia usados pela aplicacao.

O pacote `data` contem codigo Python relacionado ao banco. Arquivos gerados em
runtime ficam em `storage/` para nao misturar artefatos locais com modulos.
"""

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = STORAGE_DIR / "estoque.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
EXPORTS_DIR = STORAGE_DIR / "exports"
UPLOADS_DIR = STORAGE_DIR / "uploads"

