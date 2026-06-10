"""Serviço de notificações via WhatsApp (Meta Cloud API).

Encapsula toda a comunicação com a API da Meta para envio de mensagens
usando templates pré-aprovados. Sem dependência de Streamlit ou banco de dados.

Credenciais são lidas de core/config.py, que por sua vez lê variáveis de ambiente:
    WA_ACCESS_TOKEN     — token permanente do System User (Meta Business Suite)
    WA_PHONE_NUMBER_ID  — ID do número no WhatsApp Business (≠ número de telefone)
    WA_TEMPLATE_NAME    — nome do template aprovado (padrão: form_solicitacoes_materiais)
    WA_TEMPLATE_LANG    — código de idioma do template (padrão: pt_BR)
"""

import re
from dataclasses import dataclass
from typing import Optional

import requests

from core.config import (
    WA_ACCESS_TOKEN,
    WA_PHONE_NUMBER_ID,
    WA_TEMPLATE_ENCERRAM,
    WA_TEMPLATE_FEEDBACK,
    WA_TEMPLATE_LANG,
    WA_TEMPLATE_LEMBRETE,
    WA_TEMPLATE_NAME,
    WA_TEMPLATE_PRAZO,
)

_META_API_URL = "https://graph.facebook.com/v19.0"


@dataclass
class ResultadoEnvio:
    sucesso: bool
    wamid: Optional[str]       # ID da mensagem no WhatsApp (para rastreamento futuro)
    motivo_falha: Optional[str]


def credenciais_configuradas() -> bool:
    """Retorna True se as credenciais da Meta API estão definidas."""
    return bool(WA_ACCESS_TOKEN and WA_PHONE_NUMBER_ID)


def _normalizar_numero(whatsapp: str) -> str:
    """Normaliza o número para o formato E.164 esperado pela Meta API (55XXXXXXXXXXX)."""
    digitos = re.sub(r"\D", "", whatsapp)
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    return digitos


def enviar_formulario(
    whatsapp: str,
    periodo_label: str,
    setor_nome: str,
    prazo_label: str,
    link: str,
) -> ResultadoEnvio:
    """Envia o formulário de solicitação para um setor via template WhatsApp.

    Template esperado (4 variáveis no corpo, na ordem):
        {{1}} = período (ex: "Junho/2026")
        {{2}} = nome do setor (ex: "Manutenção")
        {{3}} = prazo (ex: "07/06/2026")
        {{4}} = link do formulário

    Retorna ResultadoEnvio com sucesso=True e wamid preenchido em caso de êxito,
    ou sucesso=False e motivo_falha descritivo em caso de erro.
    """
    if not credenciais_configuradas():
        return ResultadoEnvio(
            sucesso=False,
            wamid=None,
            motivo_falha="credenciais_nao_configuradas",
        )

    numero = _normalizar_numero(whatsapp)

    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": WA_TEMPLATE_NAME,
            "language": {"code": WA_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": periodo_label},
                        {"type": "text", "text": setor_nome},
                        {"type": "text", "text": prazo_label},
                        {"type": "text", "text": link},
                    ],
                }
            ],
        },
    }

    try:
        response = requests.post(
            f"{_META_API_URL}/{WA_PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {WA_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except requests.exceptions.Timeout:
        return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha="api_error:timeout")
    except requests.exceptions.RequestException as exc:
        return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha=f"api_error:{exc}")

    if response.status_code == 200:
        data = response.json()
        messages = data.get("messages", [])
        wamid = messages[0].get("id") if messages else None
        return ResultadoEnvio(sucesso=True, wamid=wamid, motivo_falha=None)

    # Erro retornado pela API
    try:
        erro = response.json().get("error", {})
        codigo = erro.get("code", response.status_code)
        mensagem = erro.get("message", response.text[:120])
        motivo = f"api_error:{codigo} — {mensagem}"
    except Exception:
        motivo = f"api_error:{response.status_code}"

    return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha=motivo)


def _enviar_template(
    whatsapp: str,
    template_name: str,
    parametros: list[str],
) -> ResultadoEnvio:
    """Função base: envia qualquer template WhatsApp com lista de parâmetros de corpo."""
    if not credenciais_configuradas():
        return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha="credenciais_nao_configuradas")

    numero = _normalizar_numero(whatsapp)
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": WA_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parametros],
                }
            ],
        },
    }
    try:
        response = requests.post(
            f"{_META_API_URL}/{WA_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WA_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
    except requests.exceptions.Timeout:
        return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha="api_error:timeout")
    except requests.exceptions.RequestException as exc:
        return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha=f"api_error:{exc}")

    if response.status_code == 200:
        data = response.json()
        messages = data.get("messages", [])
        wamid = messages[0].get("id") if messages else None
        return ResultadoEnvio(sucesso=True, wamid=wamid, motivo_falha=None)

    try:
        erro = response.json().get("error", {})
        motivo = f"api_error:{erro.get('code', response.status_code)} — {erro.get('message', response.text[:120])}"
    except Exception:
        motivo = f"api_error:{response.status_code}"
    return ResultadoEnvio(sucesso=False, wamid=None, motivo_falha=motivo)


def enviar_lembrete(
    whatsapp: str,
    periodo_label: str,
    setor_nome: str,
    prazo_label: str,
) -> ResultadoEnvio:
    """Lembrete D+2: setor pendente ainda não enviou a solicitação.

    Template esperado (3 variáveis): período, setor, prazo.
    """
    return _enviar_template(whatsapp, WA_TEMPLATE_LEMBRETE, [periodo_label, setor_nome, prazo_label])


def enviar_aviso_prazo_proximo(
    whatsapp: str,
    periodo_label: str,
    setor_nome: str,
    prazo_label: str,
) -> ResultadoEnvio:
    """Aviso de prazo próximo: 1 dia antes do deadline para setores ainda pendentes.

    Template esperado (3 variáveis): período, setor, prazo.
    """
    return _enviar_template(whatsapp, WA_TEMPLATE_PRAZO, [periodo_label, setor_nome, prazo_label])


def enviar_aviso_encerramento(
    whatsapp: str,
    periodo_label: str,
    setor_nome: str,
) -> ResultadoEnvio:
    """Notifica setor que o ciclo foi encerrado sem resposta dele.

    Template esperado (2 variáveis): período, setor.
    """
    return _enviar_template(whatsapp, WA_TEMPLATE_ENCERRAM, [periodo_label, setor_nome])


def enviar_feedback_aprovacao(
    whatsapp: str,
    setor_nome: str,
    periodo_label: str,
    itens_aprovados: list[str],
    itens_rejeitados: list[str],
) -> ResultadoEnvio:
    """Feedback pós-consolidação: resumo de itens aprovados e rejeitados para o setor.

    Template esperado (4 variáveis): setor, período, lista de aprovados, lista de rejeitados.
    Listas são formatadas como texto separado por vírgula.
    """
    aprovados_txt  = ", ".join(itens_aprovados)  if itens_aprovados  else "nenhum"
    rejeitados_txt = ", ".join(itens_rejeitados) if itens_rejeitados else "nenhum"
    return _enviar_template(
        whatsapp, WA_TEMPLATE_FEEDBACK,
        [setor_nome, periodo_label, aprovados_txt, rejeitados_txt],
    )
