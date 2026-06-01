""" Constantes de caminho e URL usadas pela aplicação.

Centraliza diretórios operacionais, arquivo SQLite e pastas de exportação para
evitar caminhos duplicados entre app, serviços, documentos e migração.
"""

from pathlib import Path

# Raiz do projeto, calculada de forma relativa para funcionar no app e em CLI.
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "estoque.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
EXPORTS_DIR = DATA_DIR / "exports"
UPLOADS_DIR = DATA_DIR / "uploads"
DOCS_DIR = BASE_DIR / "docs"
