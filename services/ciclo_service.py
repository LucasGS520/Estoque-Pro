"""Serviços de gestão do Ciclo Mensal de Solicitações de Materiais."""

import datetime

from core import tempo
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from core.models import (
    CicloSolicitacaoMaterial,
    CicloSolicitacaoSetor,
    CompraAvulsa,
    SolicitacaoMaterial,
    SolicitacaoPedido,
)
from services.estoque_service import get_setores

_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


@dataclass
class CicloAberturaResult:
    """Resultado da abertura de um ciclo, incluindo estatísticas de envio."""
    ciclo: CicloSolicitacaoMaterial
    enviados: int
    falhas_api: int
    sem_whatsapp: int


def _periodo_label(data: datetime.date) -> str:
    return f"{_MESES_PT[data.month]}/{data.year}"


def _enviar_e_registrar(
    session: Session,
    participante: CicloSolicitacaoSetor,
    setor,
    periodo_referencia: datetime.date,
    prazo_resposta_em: Optional[datetime.datetime],
):
    """Envia notificação WhatsApp para um participante e persiste o resultado no objeto.

    Não faz commit — o chamador é responsável por commitar após processar todos os participantes.
    """
    from services import notificacao_service
    from core.ui import gerar_link_formulario

    if not setor.whatsapp:
        participante.falha_envio = True
        participante.motivo_falha = "sem_whatsapp"
        return

    periodo_label = _periodo_label(periodo_referencia)
    prazo_label = (
        prazo_resposta_em.strftime("%d/%m/%Y")
        if prazo_resposta_em
        else "Em breve"
    )
    link = gerar_link_formulario(setor.id)

    resultado = notificacao_service.enviar_formulario(
        whatsapp=setor.whatsapp,
        periodo_label=periodo_label,
        setor_nome=setor.nome,
        prazo_label=prazo_label,
        link=link,
    )

    if resultado.sucesso:
        participante.envio_notificado_em = tempo.agora()
        participante.falha_envio = False
        participante.motivo_falha = None
    else:
        participante.falha_envio = True
        participante.motivo_falha = resultado.motivo_falha


def abrir_ciclo(
    session: Session,
    periodo_referencia: datetime.date,
    prazo_resposta_em: Optional[datetime.datetime] = None,
) -> CicloAberturaResult:
    """Abre um novo ciclo, cria um registro por setor ativo e envia as notificações.

    Levanta ValueError se já existir um ciclo aberto para o mesmo período.
    Retorna CicloAberturaResult com o ciclo e contagens de envio.
    """
    existente = (
        session.query(CicloSolicitacaoMaterial)
        .filter(
            CicloSolicitacaoMaterial.periodo_referencia == periodo_referencia,
            CicloSolicitacaoMaterial.status == "aberto",
        )
        .first()
    )
    if existente:
        raise ValueError(
            f"Já existe um ciclo aberto para o período {periodo_referencia.strftime('%m/%Y')}."
        )

    ciclo = CicloSolicitacaoMaterial(
        periodo_referencia=periodo_referencia,
        abertura_em=tempo.agora(),
        prazo_resposta_em=prazo_resposta_em,
        status="aberto",
    )
    session.add(ciclo)
    session.flush()  # gera ciclo.id sem commitar

    setores_ativos = get_setores(session, apenas_ativos=True)
    participantes = []
    for setor in setores_ativos:
        participante = CicloSolicitacaoSetor(
            ciclo_id=ciclo.id,
            setor_id=setor.id,
            status="pendente",
        )
        session.add(participante)
        session.flush()
        participantes.append((participante, setor))

    # Envia notificações e registra resultado em cada participante
    enviados = falhas_api = sem_whatsapp = 0
    for participante, setor in participantes:
        _enviar_e_registrar(session, participante, setor, periodo_referencia, prazo_resposta_em)
        if not participante.falha_envio:
            enviados += 1
        elif participante.motivo_falha == "sem_whatsapp":
            sem_whatsapp += 1
        else:
            falhas_api += 1

    session.commit()
    session.refresh(ciclo)
    return CicloAberturaResult(
        ciclo=ciclo,
        enviados=enviados,
        falhas_api=falhas_api,
        sem_whatsapp=sem_whatsapp,
    )


def encerrar_ciclo(session: Session, ciclo_id: int) -> CicloSolicitacaoMaterial:
    """Encerra um ciclo aberto e envia notificação de encerramento para setores pendentes."""
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")
    ciclo.status = "encerrado"
    ciclo.encerrado_em = tempo.agora()
    session.commit()
    # Notifica automaticamente os setores que não responderam
    enviar_notificacoes_encerramento(session, ciclo_id)
    return ciclo


def prorrogar_ciclo(
    session: Session,
    ciclo_id: int,
    novo_prazo: datetime.datetime,
) -> CicloSolicitacaoMaterial:
    """Atualiza o prazo de resposta de um ciclo."""
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")
    ciclo.prazo_resposta_em = novo_prazo
    session.commit()
    return ciclo


def get_ciclo_por_periodo(
    session: Session, periodo: datetime.date
) -> Optional[CicloSolicitacaoMaterial]:
    """Retorna o ciclo (qualquer status) para o período exato, ou None."""
    return (
        session.query(CicloSolicitacaoMaterial)
        .options(joinedload(CicloSolicitacaoMaterial.participantes).joinedload(CicloSolicitacaoSetor.setor))
        .filter(CicloSolicitacaoMaterial.periodo_referencia == periodo)
        .order_by(CicloSolicitacaoMaterial.criado_em.desc())
        .first()
    )


def reabrir_ciclo(session: Session, ciclo_id: int) -> CicloSolicitacaoMaterial:
    """Reabre um ciclo encerrado, voltando o status para 'aberto'."""
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")
    if ciclo.status != "encerrado":
        raise ValueError("Apenas ciclos encerrados podem ser reabertos.")
    ciclo.status = "aberto"
    ciclo.encerrado_em = None
    session.commit()
    return ciclo


def deletar_ciclo(session: Session, ciclo_id: int) -> dict:
    """Remove o ciclo e todos os dados vinculados a ele (reset completo).

    Exclui: participantes do ciclo, formulários submetidos (pedidos + itens de
    solicitação + compras avulsas). Retorna contagens do que foi removido.
    """
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")

    # IDs dos pedidos vinculados a este ciclo
    pedido_ids = [
        r[0]
        for r in session.query(SolicitacaoPedido.id)
        .filter(SolicitacaoPedido.ciclo_id == ciclo_id)
        .all()
    ]

    n_solicitacoes = 0
    if pedido_ids:
        # IDs de solicitações dos pedidos para limpar compras avulsas primeiro
        sol_ids = [
            r[0]
            for r in session.query(SolicitacaoMaterial.id)
            .filter(SolicitacaoMaterial.pedido_id.in_(pedido_ids))
            .all()
        ]
        if sol_ids:
            session.query(CompraAvulsa).filter(
                CompraAvulsa.solicitacao_id.in_(sol_ids)
            ).delete(synchronize_session=False)
            n_solicitacoes = (
                session.query(SolicitacaoMaterial)
                .filter(SolicitacaoMaterial.pedido_id.in_(pedido_ids))
                .delete(synchronize_session=False)
            )
        session.query(SolicitacaoPedido).filter(
            SolicitacaoPedido.id.in_(pedido_ids)
        ).delete(synchronize_session=False)

    session.query(CicloSolicitacaoSetor).filter_by(ciclo_id=ciclo_id).delete()
    session.delete(ciclo)
    session.commit()

    return {
        "formularios": len(pedido_ids),
        "solicitacoes": n_solicitacoes,
    }


def adicionar_setor_ao_ciclo(
    session: Session,
    ciclo_id: int,
    setor_id: int,
) -> CicloSolicitacaoSetor:
    """Adiciona um setor que não estava no ciclo como participante pendente e envia notificação.

    Lança ValueError se o setor já estiver no ciclo ou se o ciclo não estiver aberto.
    """
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo or ciclo.status != "aberto":
        raise ValueError("O ciclo não está aberto.")
    existente = (
        session.query(CicloSolicitacaoSetor)
        .filter_by(ciclo_id=ciclo_id, setor_id=setor_id)
        .first()
    )
    if existente:
        raise ValueError("Este setor já está incluído no ciclo.")

    from core.models import Setor
    setor = session.get(Setor, setor_id)

    participante = CicloSolicitacaoSetor(
        ciclo_id=ciclo_id,
        setor_id=setor_id,
        status="pendente",
    )
    session.add(participante)
    session.flush()

    _enviar_e_registrar(session, participante, setor, ciclo.periodo_referencia, ciclo.prazo_resposta_em)

    session.commit()
    session.refresh(participante)
    return participante


def reenviar_notificacao_setor(
    session: Session,
    ciclo_id: int,
    setor_id: int,
) -> CicloSolicitacaoSetor:
    """Reenvia a notificação WhatsApp para um setor já participante do ciclo.

    Atualiza envio_notificado_em / falha_envio / motivo_falha com o novo resultado.
    Lança ValueError se o participante não for encontrado ou o ciclo não estiver aberto.
    """
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo or ciclo.status != "aberto":
        raise ValueError("O ciclo não está aberto.")

    participante = (
        session.query(CicloSolicitacaoSetor)
        .filter_by(ciclo_id=ciclo_id, setor_id=setor_id)
        .first()
    )
    if not participante:
        raise ValueError("Participante não encontrado no ciclo.")

    from core.models import Setor
    setor = session.get(Setor, setor_id)

    _enviar_e_registrar(session, participante, setor, ciclo.periodo_referencia, ciclo.prazo_resposta_em)

    session.commit()
    session.refresh(participante)
    return participante


def get_ciclo_ativo(session: Session) -> Optional[CicloSolicitacaoMaterial]:
    """Retorna o ciclo com status 'aberto' mais recente, ou None."""
    return (
        session.query(CicloSolicitacaoMaterial)
        .options(joinedload(CicloSolicitacaoMaterial.participantes).joinedload(CicloSolicitacaoSetor.setor))
        .filter(CicloSolicitacaoMaterial.status == "aberto")
        .order_by(CicloSolicitacaoMaterial.criado_em.desc())
        .first()
    )


def get_ciclos(session: Session) -> list[CicloSolicitacaoMaterial]:
    """Retorna todos os ciclos ordenados por data de criação decrescente."""
    return (
        session.query(CicloSolicitacaoMaterial)
        .options(joinedload(CicloSolicitacaoMaterial.participantes))
        .order_by(CicloSolicitacaoMaterial.criado_em.desc())
        .all()
    )


def _periodo_label_ciclo(ciclo: CicloSolicitacaoMaterial) -> str:
    return _periodo_label(ciclo.periodo_referencia)


def _prazo_label_ciclo(ciclo: CicloSolicitacaoMaterial) -> str:
    return ciclo.prazo_resposta_em.strftime("%d/%m/%Y") if ciclo.prazo_resposta_em else "Em breve"


def _participantes_pendentes(session: Session, ciclo_id: int) -> list[CicloSolicitacaoSetor]:
    return (
        session.query(CicloSolicitacaoSetor)
        .options(joinedload(CicloSolicitacaoSetor.setor))
        .filter_by(ciclo_id=ciclo_id, status="pendente")
        .all()
    )


def _resultado_envio(enviados: int, falhas_api: int, sem_whatsapp: int) -> dict:
    return {"enviados": enviados, "falhas_api": falhas_api, "sem_whatsapp": sem_whatsapp}


def enviar_lembretes_pendentes(session: Session, ciclo_id: int) -> dict:
    """Envia lembrete (D+2) a todos os setores ainda pendentes que ainda não receberam lembrete.

    Retorna contagens: {enviados, falhas_api, sem_whatsapp}.
    """
    from services import notificacao_service

    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")

    periodo_label = _periodo_label_ciclo(ciclo)
    prazo_label   = _prazo_label_ciclo(ciclo)
    enviados = falhas_api = sem_whatsapp = 0

    for p in _participantes_pendentes(session, ciclo_id):
        if p.notificacao_lembrete_d2_em is not None:
            continue  # já enviado
        setor = p.setor
        if not setor or not setor.whatsapp:
            sem_whatsapp += 1
            continue
        res = notificacao_service.enviar_lembrete(setor.whatsapp, periodo_label, setor.nome, prazo_label)
        if res.sucesso:
            p.notificacao_lembrete_d2_em = tempo.agora()
            enviados += 1
        else:
            falhas_api += 1

    session.commit()
    return _resultado_envio(enviados, falhas_api, sem_whatsapp)


def enviar_avisos_prazo_proximo(session: Session, ciclo_id: int) -> dict:
    """Envia aviso de prazo próximo a setores pendentes que ainda não receberam este aviso.

    Retorna contagens: {enviados, falhas_api, sem_whatsapp}.
    """
    from services import notificacao_service

    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")

    periodo_label = _periodo_label_ciclo(ciclo)
    prazo_label   = _prazo_label_ciclo(ciclo)
    enviados = falhas_api = sem_whatsapp = 0

    for p in _participantes_pendentes(session, ciclo_id):
        if p.notificacao_prazo_proximo_em is not None:
            continue
        setor = p.setor
        if not setor or not setor.whatsapp:
            sem_whatsapp += 1
            continue
        res = notificacao_service.enviar_aviso_prazo_proximo(setor.whatsapp, periodo_label, setor.nome, prazo_label)
        if res.sucesso:
            p.notificacao_prazo_proximo_em = tempo.agora()
            enviados += 1
        else:
            falhas_api += 1

    session.commit()
    return _resultado_envio(enviados, falhas_api, sem_whatsapp)


def enviar_notificacoes_encerramento(session: Session, ciclo_id: int) -> dict:
    """Notifica setores pendentes que o ciclo foi encerrado sem resposta deles.

    Chamado automaticamente por encerrar_ciclo(). Retorna contagens.
    """
    from services import notificacao_service

    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        return _resultado_envio(0, 0, 0)

    periodo_label = _periodo_label_ciclo(ciclo)
    enviados = falhas_api = sem_whatsapp = 0

    for p in _participantes_pendentes(session, ciclo_id):
        if p.notificacao_encerramento_em is not None:
            continue
        setor = p.setor
        if not setor or not setor.whatsapp:
            sem_whatsapp += 1
            continue
        res = notificacao_service.enviar_aviso_encerramento(setor.whatsapp, periodo_label, setor.nome)
        if res.sucesso:
            p.notificacao_encerramento_em = tempo.agora()
            enviados += 1
        else:
            falhas_api += 1

    session.commit()
    return _resultado_envio(enviados, falhas_api, sem_whatsapp)


def enviar_feedbacks_aprovacao(
    session: Session,
    ciclo_id: int,
    feedbacks: "dict[int, dict]",
) -> dict:
    """Envia feedback de aprovação para cada setor indicado.

    `feedbacks` é um dict {setor_id: {"aprovados": [...], "rejeitados": [...]}}.
    Retorna contagens: {enviados, falhas_api, sem_whatsapp}.
    """
    from services import notificacao_service
    from core.models import Setor

    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")

    periodo_label = _periodo_label_ciclo(ciclo)
    enviados = falhas_api = sem_whatsapp = 0

    for setor_id, dados in feedbacks.items():
        participante = (
            session.query(CicloSolicitacaoSetor)
            .options(joinedload(CicloSolicitacaoSetor.setor))
            .filter_by(ciclo_id=ciclo_id, setor_id=setor_id)
            .first()
        )
        setor = session.get(Setor, setor_id)
        if not setor or not setor.whatsapp:
            sem_whatsapp += 1
            continue
        res = notificacao_service.enviar_feedback_aprovacao(
            setor.whatsapp,
            setor.nome,
            periodo_label,
            dados.get("aprovados", []),
            dados.get("rejeitados", []),
        )
        if res.sucesso:
            if participante:
                participante.notificacao_feedback_em = tempo.agora()
            enviados += 1
        else:
            falhas_api += 1

    session.commit()
    return _resultado_envio(enviados, falhas_api, sem_whatsapp)


def marcar_setor_respondido(
    session: Session,
    ciclo_id: int,
    setor_id: int,
    sem_solicitacao: bool = False,
) -> Optional[CicloSolicitacaoSetor]:
    """Marca o registro de participação do setor como respondido ou sem solicitação.

    Levanta ValueError ao tentar marcar 'sem_solicitacao' quando o setor já
    enviou pedidos neste ciclo — o status 'respondido' não pode ser sobrescrito.
    """
    participante = (
        session.query(CicloSolicitacaoSetor)
        .filter_by(ciclo_id=ciclo_id, setor_id=setor_id)
        .first()
    )
    if not participante:
        return None
    if sem_solicitacao:
        tem_pedidos = (
            session.query(SolicitacaoPedido.id)
            .filter_by(ciclo_id=ciclo_id, setor_id=setor_id)
            .first()
            is not None
        )
        if tem_pedidos:
            raise ValueError(
                "O setor já enviou solicitações neste ciclo — "
                "não é possível marcá-lo como 'sem necessidade'."
            )
    participante.status = "sem_solicitacao" if sem_solicitacao else "respondido"
    participante.respondido_em = tempo.agora()
    session.commit()
    return participante
