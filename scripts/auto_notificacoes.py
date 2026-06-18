"""Script de notificações automáticas para execução via cron na VPS.

Deve ser rodado uma vez por dia (recomendado às 9h) via docker exec:

    docker exec estoque-dfeb python /app/scripts/auto_notificacoes.py

O script verifica todos os ciclos de solicitação abertos e dispara:
  - Lembrete D+2: se o ciclo tem 2+ dias de abertura e o setor não recebeu lembrete
  - Aviso de prazo: se o prazo vence amanhã e o setor não recebeu este aviso

Toda lógica de deduplicação (não reenviar para quem já recebeu) está nos serviços
existentes — este script apenas os orquestra fora do contexto Streamlit.
"""

import sys
import datetime
import logging
from pathlib import Path

# Garante que o diretório raiz do projeto está no sys.path,
# permitindo importar os módulos do projeto normalmente.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_session_factory, init_db
from core.models import CicloSolicitacaoMaterial
from core import tempo
from services.ciclo_service import enviar_lembretes_pendentes, enviar_avisos_prazo_proximo

# Log vai para stdout (capturado pelo cron via redirecionamento) e para arquivo em data/
LOG_FILE = PROJECT_ROOT / "data" / "cron_notificacoes.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def _dias_aberto(ciclo: CicloSolicitacaoMaterial) -> int:
    """Dias corridos desde a abertura do ciclo (inclusive hoje)."""
    abertura = ciclo.abertura_em.date() if ciclo.abertura_em else None
    if not abertura:
        return 0
    return (tempo.hoje() - abertura).days


def _prazo_amanha(ciclo: CicloSolicitacaoMaterial) -> bool:
    """Retorna True se o prazo do ciclo é amanhã."""
    if not ciclo.prazo_resposta_em:
        return False
    prazo = ciclo.prazo_resposta_em.date() if hasattr(ciclo.prazo_resposta_em, "date") else ciclo.prazo_resposta_em
    return (prazo - tempo.hoje()).days == 1


def main() -> None:
    log.info("=== Iniciando verificação de notificações automáticas ===")

    init_db()
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        ciclos_abertos = (
            session.query(CicloSolicitacaoMaterial)
            .filter(CicloSolicitacaoMaterial.status == "aberto")
            .all()
        )

        if not ciclos_abertos:
            log.info("Nenhum ciclo aberto encontrado. Nada a fazer.")
            return

        log.info(f"{len(ciclos_abertos)} ciclo(s) aberto(s) encontrado(s).")

        for ciclo in ciclos_abertos:
            periodo = ciclo.periodo_referencia.strftime("%m/%Y") if ciclo.periodo_referencia else f"id={ciclo.id}"
            dias = _dias_aberto(ciclo)
            log.info(f"Ciclo {periodo} — {dias} dia(s) aberto, prazo: {ciclo.prazo_resposta_em}")

            # --- Lembrete D+2 ---
            if dias >= 2:
                try:
                    resultado = enviar_lembretes_pendentes(session, ciclo.id)
                    log.info(
                        f"  Lembrete D+2 ({periodo}): enviados={resultado['enviados']}, "
                        f"falhas_api={resultado['falhas_api']}, sem_whatsapp={resultado['sem_whatsapp']}"
                    )
                except Exception as exc:
                    log.error(f"  Erro ao enviar lembretes D+2 para ciclo {periodo}: {exc}")
            else:
                log.info(f"  Lembrete D+2 ({periodo}): ciclo com {dias} dia(s) — ainda não elegível (mínimo 2 dias).")

            # --- Aviso de prazo próximo ---
            if _prazo_amanha(ciclo):
                try:
                    resultado = enviar_avisos_prazo_proximo(session, ciclo.id)
                    log.info(
                        f"  Aviso de prazo ({periodo}): enviados={resultado['enviados']}, "
                        f"falhas_api={resultado['falhas_api']}, sem_whatsapp={resultado['sem_whatsapp']}"
                    )
                except Exception as exc:
                    log.error(f"  Erro ao enviar avisos de prazo para ciclo {periodo}: {exc}")
            else:
                log.info(f"  Aviso de prazo ({periodo}): prazo não é amanhã — nada a enviar.")

    log.info("=== Verificação concluída ===")


if __name__ == "__main__":
    main()
