"""Serviços de gestão do Ciclo Mensal de Solicitações de Materiais."""

import datetime
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


def abrir_ciclo(
    session: Session,
    periodo_referencia: datetime.date,
    prazo_resposta_em: Optional[datetime.datetime] = None,
) -> CicloSolicitacaoMaterial:
    """Abre um novo ciclo e cria um registro por setor ativo.

    Levanta ValueError se já existir um ciclo aberto para o mesmo período.
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
        abertura_em=datetime.datetime.utcnow(),
        prazo_resposta_em=prazo_resposta_em,
        status="aberto",
    )
    session.add(ciclo)
    session.flush()  # gera ciclo.id sem commitar

    setores_ativos = get_setores(session, apenas_ativos=True)
    for setor in setores_ativos:
        participante = CicloSolicitacaoSetor(
            ciclo_id=ciclo.id,
            setor_id=setor.id,
            status="pendente",
        )
        session.add(participante)

    session.commit()
    session.refresh(ciclo)
    return ciclo


def encerrar_ciclo(session: Session, ciclo_id: int) -> CicloSolicitacaoMaterial:
    """Encerra um ciclo aberto."""
    ciclo = session.query(CicloSolicitacaoMaterial).filter_by(id=ciclo_id).first()
    if not ciclo:
        raise ValueError(f"Ciclo {ciclo_id} não encontrado.")
    ciclo.status = "encerrado"
    ciclo.encerrado_em = datetime.datetime.utcnow()
    session.commit()
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
    """Adiciona um setor que não estava no ciclo como participante pendente.

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
    participante = CicloSolicitacaoSetor(
        ciclo_id=ciclo_id,
        setor_id=setor_id,
        status="pendente",
    )
    session.add(participante)
    session.commit()
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


def marcar_setor_respondido(
    session: Session,
    ciclo_id: int,
    setor_id: int,
    sem_solicitacao: bool = False,
) -> Optional[CicloSolicitacaoSetor]:
    """Marca o registro de participação do setor como respondido ou sem solicitação."""
    participante = (
        session.query(CicloSolicitacaoSetor)
        .filter_by(ciclo_id=ciclo_id, setor_id=setor_id)
        .first()
    )
    if not participante:
        return None
    participante.status = "sem_solicitacao" if sem_solicitacao else "respondido"
    participante.respondido_em = datetime.datetime.utcnow()
    session.commit()
    return participante
