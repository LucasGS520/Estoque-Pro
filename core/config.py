""" Constantes de caminho e URL usadas pela aplicação.

Centraliza diretórios operacionais, arquivo SQLite e pastas de exportação para
evitar caminhos duplicados entre app, serviços, documentos e migração.
"""

import os
from pathlib import Path

# Raiz do projeto, calculada de forma relativa para funcionar no app e em CLI.
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "estoque.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
EXPORTS_DIR = DATA_DIR / "exports"
UPLOADS_DIR = DATA_DIR / "uploads"
DOCS_DIR = BASE_DIR / "docs"

# URL pública da aplicação — usada para gerar links dos formulários enviados aos setores.
# Configurar via variável de ambiente APP_BASE_URL ao fazer deploy.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501").rstrip("/")

# Meta WhatsApp Cloud API — configurar via variáveis de ambiente (não commitar tokens).
WA_ACCESS_TOKEN       = os.getenv("WA_ACCESS_TOKEN", "")
WA_PHONE_NUMBER_ID    = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_TEMPLATE_NAME      = os.getenv("WA_TEMPLATE_NAME",      "form_solicitacoes_materiais")
WA_TEMPLATE_LEMBRETE  = os.getenv("WA_TEMPLATE_LEMBRETE",  "lembrete_solicitacao_materiais")
WA_TEMPLATE_PRAZO     = os.getenv("WA_TEMPLATE_PRAZO",     "aviso_prazo_solicitacao")
WA_TEMPLATE_ENCERRAM  = os.getenv("WA_TEMPLATE_ENCERRAM",  "encerramento_ciclo_materiais")
WA_TEMPLATE_FEEDBACK  = os.getenv("WA_TEMPLATE_FEEDBACK",  "feedback_solicitacao_materiais")
WA_TEMPLATE_COTACAO   = os.getenv("WA_TEMPLATE_COTACAO",   "")  # template de solicitação de cotação a fornecedores
WA_TEMPLATE_LANG      = os.getenv("WA_TEMPLATE_LANG", "pt_BR")
