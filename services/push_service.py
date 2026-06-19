"""Push notifications internas via ntfy (opcional).

Encapsula toda comunicação com o servidor ntfy. Sem dependência de
Streamlit ou banco de dados. Falha graciosamente sem credenciais.

Variáveis de ambiente (core/config.py):
    NTFY_SERVER  — URL do servidor ntfy (ex: https://ntfy.sh ou instância própria)
    NTFY_TOPIC   — tópico assinado no app    (ex: estoque-alertas)
    NTFY_TOKEN   — token de publicação       (gerado via ntfy token add)

Prioridades ntfy: 1=min  2=low  3=default  4=high  5=max/urgent
"""

import logging
from typing import Optional

import requests

from core.config import NTFY_SERVER, NTFY_TOPIC, NTFY_TOKEN

logger = logging.getLogger(__name__)

_TIMEOUT = 5  # segundos — não bloqueia o fluxo principal em caso de lentidão


def configurado() -> bool:
    """Retorna True se as variáveis mínimas estão definidas."""
    return bool(NTFY_TOPIC and NTFY_TOKEN)


def enviar(
    titulo: str,
    mensagem: str,
    prioridade: int = 3,
    tags: Optional[list[str]] = None,
    link: Optional[str] = None,
) -> bool:
    """Publica uma notificação no tópico ntfy configurado.

    Retorna True em caso de sucesso, False em qualquer falha (sem exceção).
    """
    if not configurado():
        return False

    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
    headers = {
        "Authorization": f"Bearer {NTFY_TOKEN}",
        "Title": titulo.encode("utf-8").decode("latin-1", errors="replace"),
        "Priority": str(prioridade),
        "Content-Type": "text/plain; charset=utf-8",
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if link:
        headers["Click"] = link

    try:
        resp = requests.post(url, data=mensagem.encode("utf-8"), headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("push_service: falha ao enviar notificação ntfy: %s", exc)
        return False


# ── Helpers semânticos por evento ─────────────────────────────────────────────

def notificar_formulario_recebido(setor_nome: str, periodo_label: str) -> bool:
    """Evento: setor enviou formulário de solicitação de materiais."""
    return enviar(
        titulo="Formulário recebido",
        mensagem=f"{setor_nome} enviou as solicitações do período {periodo_label}. Acesse Análise de Compras para triagem.",
        prioridade=4,
        tags=["clipboard"],
    )


def notificar_decisao_orcamento(
    numero_orcamento: str, status: str, periodo_label: str
) -> bool:
    """Evento: diretor registrou decisão de aprovação/reprovação/devolução."""
    _status_label = {
        "APROVADO":           "Aprovado",
        "APROVADO_PARCIAL":   "Aprovado parcialmente",
        "DEVOLVIDO_REVISAO":  "Devolvido para revisão",
        "REPROVADO":          "Reprovado",
    }.get(status, status)

    _emoji_tag = {
        "APROVADO":           "white_check_mark",
        "APROVADO_PARCIAL":   "ballot_box_with_check",
        "DEVOLVIDO_REVISAO":  "arrows_counterclockwise",
        "REPROVADO":          "x",
    }.get(status, "bell")

    return enviar(
        titulo=f"Orçamento {_status_label.lower()}",
        mensagem=f"{numero_orcamento} — {_status_label}. Período: {periodo_label}. Acesse Orçamentos para ver a decisão do diretor.",
        prioridade=5 if status == "DEVOLVIDO_REVISAO" else 4,
        tags=[_emoji_tag],
    )


def notificar_estoque_zerado(item_nome: str) -> bool:
    """Evento: movimentação de saída causou estoque_atual = 0."""
    return enviar(
        titulo="Estoque zerado",
        mensagem=f"{item_nome} chegou a zero unidades. Verifique a necessidade de reposição urgente.",
        prioridade=5,
        tags=["rotating_light"],
    )


def notificar_estoque_abaixo_minimo(
    item_nome: str, qtd_atual: float, qtd_minima: float
) -> bool:
    """Evento: movimentação de saída fez estoque_atual cair abaixo do mínimo."""
    return enviar(
        titulo="Abaixo do mínimo",
        mensagem=f"{item_nome}: estoque atual {qtd_atual:.0f} (mínimo {qtd_minima:.0f}). Considere abrir pedido de reposição.",
        prioridade=4,
        tags=["warning"],
    )
