"""Serviço de revisão mensal e gestão de valores manuais de estoque mínimo/ideal.

Orquestra o motor de cálculo (core/calculos.py), persiste sugestões na tabela
revisoes_mensais e mantém os campos vigentes sincronizados na tabela itens.
"""

import datetime

from core import tempo
from typing import Optional

from sqlalchemy.orm import Session

from sqlalchemy import func

from core.calculos import calcular_revisao_item, calcular_janela
from core.models import Item, Movimentacao, RevisaoMensal


def _get_movimentacoes_periodo(
    session: Session,
    item_id: int,
    inicio: datetime.date,
    fim: datetime.date,
) -> tuple[list[tuple[datetime.date, int]], list[tuple[datetime.date, int]]]:
    """Retorna (saidas, entradas) do item no intervalo [inicio, fim]."""
    inicio_dt = datetime.datetime.combine(inicio, datetime.time.min)
    fim_dt = datetime.datetime.combine(fim, datetime.time.max)

    movs = (
        session.query(Movimentacao)
        .filter(
            Movimentacao.item_id == item_id,
            Movimentacao.criado_em >= inicio_dt,
            Movimentacao.criado_em <= fim_dt,
        )
        .all()
    )

    saidas = [(m.criado_em.date(), m.quantidade) for m in movs if m.tipo == "saida"]
    entradas = [(m.criado_em.date(), m.quantidade) for m in movs if m.tipo == "entrada"]
    return saidas, entradas


def executar_revisao_mensal(
    session: Session,
    item_id: Optional[int] = None,
) -> dict:
    """Executa a revisão mensal para todos os itens ativos (ou somente item_id).

    Para cada item:
    - Calcula sugestões a partir dos últimos 3 meses fechados.
    - Atualiza estoque_minimo_sugerido / estoque_ideal_sugerido.
    - Atualiza vigente/origem apenas se não há valor manual definido.
    - Cria um registro RevisaoMensal com métricas e status de confiabilidade.

    Retorna dict com totais: processados, atualizados, sem_historico.
    """
    hoje = tempo.hoje()
    data_ref = hoje.replace(day=1)  # 1º do mês corrente
    inicio, fim = calcular_janela(data_ref)

    q = session.query(Item).filter(Item.ativo == True)  # noqa: E712
    if item_id is not None:
        q = q.filter(Item.id == item_id)
    itens = q.all()

    processados = 0
    atualizados = 0
    sem_historico = 0

    periodo_desc = data_ref.strftime("%B/%Y").capitalize()
    # Garante nome do mês em português via mapeamento simples
    _meses_pt = {
        "January": "Janeiro", "February": "Fevereiro", "March": "Março",
        "April": "Abril", "May": "Maio", "June": "Junho",
        "July": "Julho", "August": "Agosto", "September": "Setembro",
        "October": "Outubro", "November": "Novembro", "December": "Dezembro",
    }
    mes_en = data_ref.strftime("%B")
    periodo_desc = f"{_meses_pt.get(mes_en, mes_en)}/{data_ref.year}"

    for item in itens:
        processados += 1

        # Consulta a data da primeira movimentação comercial do item (entrada ou saída)
        # para que o motor adapte a janela ao histórico disponível.
        # Filtra por tipo para não distorcer a janela caso novos tipos sejam adicionados.
        primeira_mov_dt = (
            session.query(func.min(Movimentacao.criado_em))
            .filter(
                Movimentacao.item_id == item.id,
                Movimentacao.tipo.in_(["entrada", "saida"]),
            )
            .scalar()
        )
        data_primeira_mov = primeira_mov_dt.date() if primeira_mov_dt else None

        saidas, entradas = _get_movimentacoes_periodo(session, item.id, inicio, fim)
        resultado = calcular_revisao_item(
            saidas, entradas, data_ref,
            data_primeira_mov=data_primeira_mov,
        )

        # Sempre atualiza sugestões automáticas
        item.estoque_minimo_sugerido = resultado.minimo_sugerido
        item.estoque_ideal_sugerido = resultado.ideal_sugerido

        # Atualiza vigente apenas quando não há manual definido
        if item.estoque_minimo_manual is None:
            item.estoque_minimo_vigente = resultado.minimo_sugerido or 0
            item.origem_minimo = "Automático" if resultado.minimo_sugerido is not None else None

        if item.estoque_ideal_manual is None:
            item.estoque_ideal_vigente = resultado.ideal_sugerido or 0
            item.origem_ideal = "Automático" if resultado.ideal_sugerido is not None else None

        # Início real da janela: usa efetivo quando o item tem histórico curto
        inicio_analise = resultado.data_inicio_efetiva or inicio

        # Registra revisão
        revisao = RevisaoMensal(
            item_id=item.id,
            periodo_descricao=periodo_desc,
            data_inicio_analise=datetime.datetime.combine(inicio_analise, datetime.time.min),
            data_fim_analise=datetime.datetime.combine(fim, datetime.time.max),
            consumo_mediana_diario=resultado.consumo_mediana_diario,
            consumo_p75_diario=resultado.consumo_p75_diario,
            intervalo_mediano_dias=resultado.intervalo_mediano_dias,
            intervalo_p90_dias=resultado.intervalo_p90_dias,
            minimo_sugerido=resultado.minimo_sugerido,
            ideal_sugerido=resultado.ideal_sugerido,
            status_confiabilidade=resultado.status_confiabilidade,
        )
        session.add(revisao)

        if resultado.status_confiabilidade == "historico_insuficiente":
            sem_historico += 1
        elif resultado.minimo_sugerido is not None:
            atualizados += 1

    session.commit()
    return {"processados": processados, "atualizados": atualizados, "sem_historico": sem_historico}


def aplicar_minimo_ideal_manual(
    session: Session,
    item_id: int,
    minimo: int,
    ideal: int,
) -> Item:
    """Define valores manuais de mínimo e ideal para um item.

    Os vigentes passam a usar estes valores e a origem é marcada como "Manual".
    O sistema continua calculando os sugeridos automáticos na próxima revisão.
    """
    item = session.query(Item).filter(Item.id == item_id).one()
    agora = tempo.agora()

    item.estoque_minimo_manual = minimo
    item.estoque_ideal_manual = ideal
    item.data_definicao_minimo_manual = agora
    item.data_definicao_ideal_manual = agora
    item.estoque_minimo_vigente = minimo
    item.estoque_ideal_vigente = ideal
    item.origem_minimo = "Manual"
    item.origem_ideal = "Manual"

    session.commit()
    session.refresh(item)
    return item


def remover_manual(session: Session, item_id: int) -> Item:
    """Remove os valores manuais e reverte o vigente para o sugerido automático."""
    item = session.query(Item).filter(Item.id == item_id).one()

    item.estoque_minimo_manual = None
    item.estoque_ideal_manual = None
    item.data_definicao_minimo_manual = None
    item.data_definicao_ideal_manual = None
    item.estoque_minimo_vigente = item.estoque_minimo_sugerido or 0
    item.estoque_ideal_vigente = item.estoque_ideal_sugerido or 0
    item.origem_minimo = "Automático" if item.estoque_minimo_sugerido is not None else None
    item.origem_ideal = "Automático" if item.estoque_ideal_sugerido is not None else None

    session.commit()
    session.refresh(item)
    return item


def get_revisoes_item(
    session: Session,
    item_id: int,
    limit: int = 12,
) -> list[RevisaoMensal]:
    """Retorna as últimas revisões mensais de um item, da mais recente para a mais antiga."""
    return (
        session.query(RevisaoMensal)
        .filter(RevisaoMensal.item_id == item_id)
        .order_by(RevisaoMensal.criado_em.desc())
        .limit(limit)
        .all()
    )


def get_ultima_revisao_global(session: Session) -> Optional[datetime.datetime]:
    """Retorna o datetime da revisão mais recente registrada no sistema (qualquer item)."""
    resultado = session.query(func.max(RevisaoMensal.criado_em)).scalar()
    return resultado
