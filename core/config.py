from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "estoque.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
EXPORTS_DIR = DATA_DIR / "exports"
UPLOADS_DIR = DATA_DIR / "uploads"
DOCS_DIR = BASE_DIR / "docs"
