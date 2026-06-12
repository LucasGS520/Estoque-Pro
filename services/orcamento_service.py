"""Serviços para a camada de Orçamentos.

Gerencia o ciclo completo de orçamento a partir da Lista Final de Compras:
criação de snapshot, coleta de cotações, escolha de vencedor, envio para
aprovação do diretor e versionamento em caso de revisão.

A fonte de dados é sempre ItemListaCompra (incluir_na_lista_final=True) e
CompraAvulsa (incluir_na_lista_final=True) — nunca run_analysis() ou snapshots.
"""

import datetime
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload, selectinload

from core import tempo
from core.models import (
    CotacaoOrcamento,
    Fornecedor,
    ItemListaCompra,
    ItemOrcamento,
    Orcamento,
    CompraAvulsa,
    Item,
)

# ---------------------------------------------------------------------------
# Status válidos
# ---------------------------------------------------------------------------

STATUS_ORCAMENTO = (
    "RASCUNHO",
    "EM_COTACAO",
    "PRONTO_PARA_APROVACAO",
    "ENVIADO_APROVACAO",
    "APROVADO",
    "APROVADO_PARCIAL",
    "REVISAR",
    "DEVOLVIDO_REVISAO",
    "REPROVADO",
    "CANCELADO",
)

# Estados que permitem criação de novo orçamento para o mesmo período
_STATUS_ENCERRADO = {"APROVADO", "APROVADO_PARCIAL", "REPROVADO", "CANCELADO"}

# Estados que bloqueiam edição de cotações
_STATUS_BLOQUEADO = {"ENVIADO_APROVACAO", "APROVADO", "APROVADO_PARCIAL", "REPROVADO", "REVISAR"}


# ---------------------------------------------------------------------------
# Estrutura de resumo (não persiste — calculada sob demanda)
# ---------------------------------------------------------------------------

@dataclass
class ResumoOrcamento:
    total_itens: int = 0
    sem_cotacao: int = 0
    com_cotacao_sem_escolha: int = 0
    com_escolha: int = 0
    total_bruto: float = 0.0    # soma qty*unit-desc+outros das cotações escolhidas
    frete_total: float = 0.0    # soma de frete das cotações escolhidas
    total_geral: float = 0.0    # total_bruto + frete_total
    origens_distintas: int = 0  # quantidade de origens/fornecedores únicos


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _calcular_total(quantidade: int, preco_unitario: float, frete: float,
                    desconto: float, outros_custos: float) -> float:
    return round(quantidade * preco_unitario - desconto + outros_custos + frete, 2)


def _gerar_numero(session: Session, periodo: datetime.date) -> str:
    """Gera número sequencial ORC-YYYY-MM-NNN para o período."""
    existentes = (
        session.query(Orcamento.numero)
        .filter(Orcamento.periodo_referencia == periodo)
        .all()
    )
    max_seq = 0
    pattern = re.compile(r"ORC-\d{4}-\d{2}-(\d+)")
    for (num,) in existentes:
        m = pattern.match(num or "")
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"ORC-{periodo.year:04d}-{periodo.month:02d}-{max_seq + 1:03d}"


# ---------------------------------------------------------------------------
# Leitura da Lista Final
# ---------------------------------------------------------------------------

def get_lista_final_para_orcamento(session: Session, periodo: datetime.date) -> dict:
    """Retorna itens da Lista Final aprovados, separados por tipo.

    Returns:
        dict com chaves 'itens_estoque' (list[ItemListaCompra]) e
        'itens_avulsos' (list[CompraAvulsa]).
    """
    itens_estoque = (
        session.query(ItemListaCompra)
        .options(
            joinedload(ItemListaCompra.item).joinedload(Item.categoria),
        )
        .filter(
            and_(
                ItemListaCompra.periodo_referencia == periodo,
                ItemListaCompra.incluir_na_lista_final == True,  # noqa: E712
            )
        )
        .all()
    )
    itens_avulsos = (
        session.query(CompraAvulsa)
        .filter(
            and_(
                CompraAvulsa.periodo_referencia == periodo,
                CompraAvulsa.incluir_na_lista_final.is_(True),
            )
        )
        .order_by(CompraAvulsa.urgente.desc(), CompraAvulsa.criado_em)
        .all()
    )
    return {"itens_estoque": itens_estoque, "itens_avulsos": itens_avulsos}


# ---------------------------------------------------------------------------
# CRUD de Orçamento
# ---------------------------------------------------------------------------

def get_orcamento_ativo(session: Session, periodo: datetime.date) -> Optional[Orcamento]:
    """Retorna o orçamento ativo mais recente do período (maior versão, não encerrado)."""
    return (
        session.query(Orcamento)
        .options(
            joinedload(Orcamento.itens).joinedload(ItemOrcamento.cotacoes),
        )
        .filter(
            and_(
                Orcamento.periodo_referencia == periodo,
                Orcamento.status.notin_(_STATUS_ENCERRADO),
            )
        )
        .order_by(Orcamento.versao.desc())
        .first()
    )


def get_orcamentos_periodo(session: Session, periodo: datetime.date) -> list[Orcamento]:
    """Retorna todos os orçamentos do período, do mais recente ao mais antigo."""
    return (
        session.query(Orcamento)
        .filter(Orcamento.periodo_referencia == periodo)
        .order_by(Orcamento.versao.desc())
        .all()
    )


def get_todos_periodos_orcamento(session: Session) -> list[datetime.date]:
    """Retorna os períodos que já possuem algum orçamento, do mais recente ao mais antigo."""
    rows = (
        session.query(Orcamento.periodo_referencia)
        .distinct()
        .order_by(Orcamento.periodo_referencia.desc())
        .all()
    )
    return [r[0] for r in rows]


def get_orcamento_por_id(session: Session, orcamento_id: int) -> Optional[Orcamento]:
    """Carrega um orçamento pelo id, com itens e cotações."""
    return (
        session.query(Orcamento)
        .options(
            joinedload(Orcamento.itens).joinedload(ItemOrcamento.cotacoes),
        )
        .filter(Orcamento.id == orcamento_id)
        .first()
    )


def criar_orcamento(
    session: Session,
    periodo: datetime.date,
    responsavel: str,
) -> Orcamento:
    """Cria um orçamento a partir da Lista Final do período.

    Regras:
    - Exige pelo menos 1 item na Lista Final; levanta ValueError caso contrário.
    - Se já existir orçamento ativo (não encerrado), levanta ValueError com o id.
    - Cria snapshot dos itens: nome, categoria e quantidade são congelados.
    """
    lista = get_lista_final_para_orcamento(session, periodo)
    total = len(lista["itens_estoque"]) + len(lista["itens_avulsos"])
    if total == 0:
        raise ValueError(
            "Não há itens aprovados na Lista Final para este período. "
            "Aprove itens na aba de Compras antes de gerar o orçamento."
        )

    existente = get_orcamento_ativo(session, periodo)
    if existente:
        raise ValueError(
            f"Já existe um orçamento ativo para este período "
            f"(#{existente.numero} — {existente.status}). "
            f"id={existente.id}"
        )

    numero = _gerar_numero(session, periodo)
    _ultima_versao = (
        session.query(func.max(Orcamento.versao))
        .filter(Orcamento.periodo_referencia == periodo)
        .scalar() or 0
    )

    orc = Orcamento(
        periodo_referencia=periodo,
        numero=numero,
        versao=_ultima_versao + 1,
        status="RASCUNHO",
        responsavel=responsavel,
    )
    session.add(orc)
    session.flush()  # garante orc.id antes de criar os itens

    for il in lista["itens_estoque"]:
        qtd = il.quantidade_final_definida or il.quantidade_sugerida or 1
        cat = il.item.categoria.nome if il.item and il.item.categoria else ""
        session.add(ItemOrcamento(
            orcamento_id=orc.id,
            item_lista_id=il.id,
            nome_item=il.item.nome if il.item else f"Item #{il.item_id}",
            categoria_nome=cat,
            tipo="ESTOQUE",
            quantidade_lista=qtd,
            quantidade_orcada=qtd,
            status_item="SEM_COTACAO",
        ))

    for ca in lista["itens_avulsos"]:
        session.add(ItemOrcamento(
            orcamento_id=orc.id,
            compra_avulsa_id=ca.id,
            nome_item=ca.nome_item,
            categoria_nome="Compra Avulsa",
            tipo="AVULSA",
            quantidade_lista=ca.quantidade,
            quantidade_orcada=ca.quantidade,
            status_item="SEM_COTACAO",
        ))

    session.commit()
    session.refresh(orc)
    return orc


def cancelar_orcamento(session: Session, orcamento_id: int) -> Orcamento:
    """Cancela um orçamento que ainda não foi enviado para aprovação."""
    orc = session.get(Orcamento, orcamento_id)
    if orc is None:
        raise ValueError(f"Orçamento {orcamento_id} não encontrado.")
    if orc.status in _STATUS_BLOQUEADO:
        raise ValueError(
            f"Orçamento com status '{orc.status}' não pode ser cancelado diretamente. "
            "Use a função de decisão do diretor."
        )
    orc.status = "CANCELADO"
    orc.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(orc)
    return orc


# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------

def _recarregar_item(session: Session, item_orc_id: int) -> ItemOrcamento:
    item = session.get(ItemOrcamento, item_orc_id)
    if item is None:
        raise ValueError(f"ItemOrcamento {item_orc_id} não encontrado.")
    return item


def _desmarcar_lista_item(session: Session, item_orc: ItemOrcamento) -> None:
    """Desmarca item da Lista Final — funciona para ESTOQUE e AVULSA."""
    if item_orc.item_lista_id:
        lista = session.get(ItemListaCompra, item_orc.item_lista_id)
        if lista:
            lista.incluir_na_lista_final = False
            lista.atualizado_em = tempo.agora()
    elif item_orc.tipo == "AVULSA" and item_orc.compra_avulsa_id:
        avulsa = session.get(CompraAvulsa, item_orc.compra_avulsa_id)
        if avulsa:
            avulsa.incluir_na_lista_final = False


def _verificar_editavel(orc: Orcamento):
    if orc.status in _STATUS_BLOQUEADO:
        raise ValueError(
            f"Orçamento com status '{orc.status}' está bloqueado para edição. "
            "Solicite revisão ou crie uma nova versão."
        )


def _atualizar_melhor_cotacao(session: Session, item_orc_id: int) -> None:
    """Define cotacao_escolhida_id como a cotação de menor total_calculado."""
    cotacoes = (
        session.query(CotacaoOrcamento)
        .filter(CotacaoOrcamento.item_orcamento_id == item_orc_id)
        .all()
    )
    item = session.get(ItemOrcamento, item_orc_id)
    if item is None:
        return
    item.cotacao_escolhida_id = min(cotacoes, key=lambda c: c.total_calculado).id if cotacoes else None


def add_cotacao(
    session: Session,
    item_orc_id: int,
    origem: str,
    preco_unitario: float,
    data_cotacao: datetime.date,
    frete: float = 0.0,
    desconto: float = 0.0,
    outros_custos: float = 0.0,
    link: Optional[str] = None,
    observacao: Optional[str] = None,
    fornecedor_id: Optional[int] = None,
) -> CotacaoOrcamento:
    """Registra nova cotação para um item do orçamento."""
    item = _recarregar_item(session, item_orc_id)
    orc = session.get(Orcamento, item.orcamento_id)
    _verificar_editavel(orc)

    if not origem or not origem.strip():
        raise ValueError("O campo 'origem' é obrigatório.")
    if preco_unitario <= 0:
        raise ValueError("O preço unitário deve ser maior que zero.")

    total = _calcular_total(item.quantidade_orcada, preco_unitario, frete, desconto, outros_custos)
    cotacao = CotacaoOrcamento(
        item_orcamento_id=item_orc_id,
        origem=origem.strip(),
        fornecedor_id=fornecedor_id,
        link=link,
        preco_unitario=preco_unitario,
        frete=frete,
        desconto=desconto,
        outros_custos=outros_custos,
        total_calculado=total,
        data_cotacao=data_cotacao,
        observacao=observacao,
    )
    session.add(cotacao)

    if item.status_item == "SEM_COTACAO":
        item.status_item = "COM_COTACAO"

    if orc.status == "RASCUNHO":
        orc.status = "EM_COTACAO"
        orc.atualizado_em = tempo.agora()

    session.flush()
    _atualizar_melhor_cotacao(session, item_orc_id)
    session.commit()
    session.refresh(cotacao)
    return cotacao


def editar_cotacao(
    session: Session,
    cotacao_id: int,
    origem: Optional[str] = None,
    preco_unitario: Optional[float] = None,
    frete: Optional[float] = None,
    desconto: Optional[float] = None,
    outros_custos: Optional[float] = None,
    link: Optional[str] = None,
    observacao: Optional[str] = None,
    data_cotacao: Optional[datetime.date] = None,
) -> CotacaoOrcamento:
    """Atualiza campos de uma cotação e recalcula o total."""
    cot = session.get(CotacaoOrcamento, cotacao_id)
    if cot is None:
        raise ValueError(f"CotacaoOrcamento {cotacao_id} não encontrada.")
    item = session.get(ItemOrcamento, cot.item_orcamento_id)
    orc = session.get(Orcamento, item.orcamento_id)
    _verificar_editavel(orc)

    if origem is not None:
        cot.origem = origem.strip()
    if preco_unitario is not None:
        cot.preco_unitario = preco_unitario
    if frete is not None:
        cot.frete = frete
    if desconto is not None:
        cot.desconto = desconto
    if outros_custos is not None:
        cot.outros_custos = outros_custos
    if link is not None:
        cot.link = link
    if observacao is not None:
        cot.observacao = observacao
    if data_cotacao is not None:
        cot.data_cotacao = data_cotacao

    cot.total_calculado = _calcular_total(
        item.quantidade_orcada,
        cot.preco_unitario,
        cot.frete,
        cot.desconto,
        cot.outros_custos,
    )
    _atualizar_melhor_cotacao(session, cot.item_orcamento_id)
    session.commit()
    session.refresh(cot)
    return cot


def remover_cotacao(session: Session, cotacao_id: int) -> None:
    """Remove uma cotação. Se era a escolhida, limpa cotacao_escolhida_id do item."""
    cot = session.get(CotacaoOrcamento, cotacao_id)
    if cot is None:
        raise ValueError(f"CotacaoOrcamento {cotacao_id} não encontrada.")
    item = session.get(ItemOrcamento, cot.item_orcamento_id)
    orc = session.get(Orcamento, item.orcamento_id)
    _verificar_editavel(orc)

    session.delete(cot)
    session.flush()

    # Reavalia status e melhor cotação
    restantes = (
        session.query(CotacaoOrcamento)
        .filter(CotacaoOrcamento.item_orcamento_id == item.id)
        .count()
    )
    if restantes == 0:
        item.status_item = "SEM_COTACAO"
        item.cotacao_escolhida_id = None
    else:
        item.status_item = "COM_COTACAO"
        _atualizar_melhor_cotacao(session, item.id)

    session.commit()


def escolher_cotacao(session: Session, item_orc_id: int, cotacao_id: int) -> ItemOrcamento:
    """Define a cotação vencedora de um item.

    A escolha é sempre explícita — o sistema nunca define automaticamente.
    """
    item = _recarregar_item(session, item_orc_id)
    orc = session.get(Orcamento, item.orcamento_id)
    _verificar_editavel(orc)

    cot = session.get(CotacaoOrcamento, cotacao_id)
    if cot is None or cot.item_orcamento_id != item_orc_id:
        raise ValueError("Cotação não pertence a este item.")

    item.cotacao_escolhida_id = cotacao_id
    item.status_item = "COM_COTACAO"
    session.commit()
    session.refresh(item)
    return item


def desescolher_cotacao(session: Session, item_orc_id: int) -> ItemOrcamento:
    """Remove a escolha de cotação de um item (volta para COM_COTACAO)."""
    item = _recarregar_item(session, item_orc_id)
    orc = session.get(Orcamento, item.orcamento_id)
    _verificar_editavel(orc)
    item.cotacao_escolhida_id = None
    session.commit()
    session.refresh(item)
    return item


def atualizar_quantidade_orcada(
    session: Session,
    item_orc_id: int,
    nova_quantidade: int,
    motivo: str,
) -> ItemOrcamento:
    """Altera a quantidade orçada com obrigatoriedade de motivo."""
    item = _recarregar_item(session, item_orc_id)
    orc = session.get(Orcamento, item.orcamento_id)
    _verificar_editavel(orc)

    if nova_quantidade < 1:
        raise ValueError("Quantidade orçada deve ser >= 1.")
    if not motivo or not motivo.strip():
        raise ValueError("Informe o motivo da alteração de quantidade.")

    item.quantidade_orcada = nova_quantidade
    item.motivo_alteracao_qtd = motivo.strip()

    # Recalcula todos os totais das cotações deste item
    for cot in item.cotacoes:
        cot.total_calculado = _calcular_total(
            nova_quantidade, cot.preco_unitario, cot.frete, cot.desconto, cot.outros_custos
        )

    _atualizar_melhor_cotacao(session, item_orc_id)
    session.commit()
    session.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Resumo e status derivado
# ---------------------------------------------------------------------------

def get_resumo(session: Session, orcamento: Orcamento) -> ResumoOrcamento:
    """Calcula resumo financeiro e de progresso do orçamento."""
    # Força carregamento das cotações se necessário
    itens = (
        session.query(ItemOrcamento)
        .options(joinedload(ItemOrcamento.cotacoes))
        .filter(ItemOrcamento.orcamento_id == orcamento.id)
        .all()
    )

    resumo = ResumoOrcamento(total_itens=len(itens))
    origens: set[str] = set()

    for item in itens:
        if not item.cotacoes:
            resumo.sem_cotacao += 1
        elif item.cotacao_escolhida_id is None:
            resumo.com_cotacao_sem_escolha += 1
        else:
            resumo.com_escolha += 1
            cot_escolhida = next(
                (c for c in item.cotacoes if c.id == item.cotacao_escolhida_id), None
            )
            if cot_escolhida:
                bruto = _calcular_total(
                    item.quantidade_orcada,
                    cot_escolhida.preco_unitario,
                    0,  # frete fora do bruto
                    cot_escolhida.desconto,
                    cot_escolhida.outros_custos,
                )
                resumo.total_bruto += bruto
                resumo.frete_total += cot_escolhida.frete
                resumo.total_geral += cot_escolhida.total_calculado
                origens.add(cot_escolhida.origem)

    resumo.total_bruto = round(resumo.total_bruto, 2)
    resumo.frete_total = round(resumo.frete_total, 2)
    resumo.total_geral = round(resumo.total_geral, 2)
    resumo.origens_distintas = len(origens)
    return resumo


def menor_cotacao(item: ItemOrcamento) -> Optional[CotacaoOrcamento]:
    """Retorna a cotação de menor total_calculado do item (sugestão, não decisão)."""
    if not item.cotacoes:
        return None
    return min(item.cotacoes, key=lambda c: c.total_calculado)


# ---------------------------------------------------------------------------
# Envio para aprovação
# ---------------------------------------------------------------------------

def enviar_para_aprovacao(session: Session, orcamento_id: int) -> Orcamento:
    """Congela o orçamento e o marca como ENVIADO_APROVACAO.

    Exige que todos os itens tenham cotação escolhida ou estejam marcados como
    REPROVADO_DIRETOR (item removido antes do envio). Itens SEM_COTACAO ou
    COM_COTACAO sem escolha bloqueiam o envio.
    """
    orc = get_orcamento_por_id(session, orcamento_id)
    if orc is None:
        raise ValueError(f"Orçamento {orcamento_id} não encontrado.")
    if orc.status in _STATUS_BLOQUEADO:
        raise ValueError(f"Orçamento já está com status '{orc.status}'.")

    itens = (
        session.query(ItemOrcamento)
        .options(joinedload(ItemOrcamento.cotacoes))
        .filter(ItemOrcamento.orcamento_id == orcamento_id)
        .all()
    )

    pendentes = [i.nome_item for i in itens if i.status_item == "SEM_COTACAO"]
    if pendentes:
        lista = ", ".join(pendentes[:5])
        raise ValueError(
            f"Os seguintes itens ainda não possuem cotações registradas: {lista}."
        )

    orc.status = "ENVIADO_APROVACAO"
    orc.enviado_em = tempo.agora()
    orc.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(orc)
    return orc


# ---------------------------------------------------------------------------
# Decisão do diretor
# ---------------------------------------------------------------------------

def registrar_decisao_diretor(
    session: Session,
    orcamento_id: int,
    decisao: str,
    observacao_diretor: Optional[str] = None,
    itens_reprovados: Optional[list[int]] = None,
    itens_revisao: Optional[list[int]] = None,
) -> Orcamento:
    """Registra a decisão do diretor sobre o orçamento.

    Args:
        decisao: 'APROVADO' | 'APROVADO_PARCIAL' | 'DEVOLVIDO_REVISAO' | 'REPROVADO'
        itens_reprovados: ids de ItemOrcamento reprovados definitivamente (para APROVADO_PARCIAL)
        itens_revisao: ids de ItemOrcamento que precisam de nova cotação (para APROVADO_PARCIAL)
    """
    orc = get_orcamento_por_id(session, orcamento_id)
    if orc is None:
        raise ValueError(f"Orçamento {orcamento_id} não encontrado.")
    if orc.status != "ENVIADO_APROVACAO":
        raise ValueError(
            f"Só é possível registrar decisão em orçamentos com status "
            f"ENVIADO_APROVACAO. Status atual: '{orc.status}'."
        )

    decisoes_validas = {"APROVADO", "APROVADO_PARCIAL", "DEVOLVIDO_REVISAO", "REPROVADO"}
    if decisao not in decisoes_validas:
        raise ValueError(f"Decisão '{decisao}' inválida. Use: {decisoes_validas}")

    orc.observacao_diretor = observacao_diretor
    orc.decidido_em = tempo.agora()
    orc.atualizado_em = tempo.agora()

    if decisao == "APROVADO":
        orc.status = "APROVADO"
        for item in orc.itens:
            if item.status_item not in ("REPROVADO_DIRETOR",):
                item.status_item = "APROVADO_DIRETOR"

    elif decisao == "APROVADO_PARCIAL":
        reprovados_set = set(itens_reprovados or [])
        revisao_set = set(itens_revisao or [])
        for item in orc.itens:
            if item.id in reprovados_set:
                item.status_item = "REPROVADO_DIRETOR"
            elif item.id in revisao_set:
                item.status_item = "REVISAO_DIRETOR"
            elif item.status_item not in ("REPROVADO_DIRETOR", "REVISAO_DIRETOR"):
                item.status_item = "APROVADO_DIRETOR"
        # Itens com revisão → status REVISAR (ativo); só reprovados → APROVADO_PARCIAL (encerrado)
        orc.status = "REVISAR" if revisao_set else "APROVADO_PARCIAL"
        # Auto-remove REPROVADO_DIRETOR da Lista Final em ambos os casos
        for item in orc.itens:
            if item.status_item == "REPROVADO_DIRETOR":
                _desmarcar_lista_item(session, item)

    elif decisao == "REPROVADO":
        orc.status = "REPROVADO"
        # Auto-remove TODOS os itens da Lista Final
        for item in orc.itens:
            _desmarcar_lista_item(session, item)

    else:
        orc.status = decisao  # DEVOLVIDO_REVISAO e outros legados

    session.commit()
    session.refresh(orc)
    return orc


def criar_nova_versao(session: Session, orcamento_id: int) -> Orcamento:
    """Cria versão nova a partir de um orçamento DEVOLVIDO_REVISAO.

    Clona todos os itens; mantém cotações dos itens aprovados e limpa as
    cotações dos itens com status REPROVADO_DIRETOR (precisam de nova cotação).
    A versão anterior permanece bloqueada para auditoria.
    """
    orc_anterior = get_orcamento_por_id(session, orcamento_id)
    if orc_anterior is None:
        raise ValueError(f"Orçamento {orcamento_id} não encontrado.")
    _ACEITA_NOVA_VERSAO = {"DEVOLVIDO_REVISAO", "REVISAR"}
    if orc_anterior.status not in _ACEITA_NOVA_VERSAO:
        raise ValueError(
            f"Só é possível criar nova versão a partir de: {_ACEITA_NOVA_VERSAO}. "
            f"Status atual: '{orc_anterior.status}'."
        )

    nova_versao = orc_anterior.versao + 1

    if orc_anterior.status == "REVISAR":
        _obs_dir = orc_anterior.observacao_diretor or ""
        _obs_geral = (
            f"[Revisão v{orc_anterior.versao}] "
            + (f"Obs. do diretor: {_obs_dir}" if _obs_dir else "Revisão solicitada pelo diretor.")
        )
    else:
        _obs_geral = orc_anterior.observacao_geral

    nova = Orcamento(
        periodo_referencia=orc_anterior.periodo_referencia,
        numero=orc_anterior.numero,
        versao=nova_versao,
        status="EM_COTACAO",
        responsavel=orc_anterior.responsavel,
        observacao_geral=_obs_geral,
    )
    session.add(nova)
    session.flush()

    # REVISAR: copiar apenas itens que precisam de revisão (aprovados já estão resolvidos)
    # DEVOLVIDO_REVISAO: copiar todos os itens
    itens_a_copiar = (
        [i for i in orc_anterior.itens if i.status_item == "REVISAO_DIRETOR"]
        if orc_anterior.status == "REVISAR"
        else orc_anterior.itens
    )

    for item_ant in itens_a_copiar:
        novo_item = ItemOrcamento(
            orcamento_id=nova.id,
            item_lista_id=item_ant.item_lista_id,
            compra_avulsa_id=item_ant.compra_avulsa_id,
            nome_item=item_ant.nome_item,
            categoria_nome=item_ant.categoria_nome,
            tipo=item_ant.tipo,
            quantidade_lista=item_ant.quantidade_lista,
            quantidade_orcada=item_ant.quantidade_orcada,
            motivo_alteracao_qtd=item_ant.motivo_alteracao_qtd,
            status_item="SEM_COTACAO" if item_ant.status_item == "REPROVADO_DIRETOR" else "COM_COTACAO",
        )
        session.add(novo_item)
        session.flush()

        # Cotações a copiar:
        # - REPROVADO_DIRETOR: nenhuma
        # - REVISAO_DIRETOR: melhor cotação (ponto de partida)
        # - demais: todas
        if item_ant.status_item == "REPROVADO_DIRETOR":
            cots_a_copiar = []
        elif item_ant.status_item == "REVISAO_DIRETOR":
            cots_a_copiar = (
                [min(item_ant.cotacoes, key=lambda c: c.total_calculado)]
                if item_ant.cotacoes else []
            )
        else:
            cots_a_copiar = item_ant.cotacoes

        for cot in cots_a_copiar:
            nova_cot = CotacaoOrcamento(
                item_orcamento_id=novo_item.id,
                origem=cot.origem,
                fornecedor_id=cot.fornecedor_id,
                link=cot.link,
                preco_unitario=cot.preco_unitario,
                frete=cot.frete,
                desconto=cot.desconto,
                outros_custos=cot.outros_custos,
                total_calculado=cot.total_calculado,
                data_cotacao=cot.data_cotacao,
                observacao=cot.observacao,
            )
            session.add(nova_cot)
            session.flush()
            _atualizar_melhor_cotacao(session, novo_item.id)

    # Arquivar a versão anterior: fica visível no Histórico como "Substituído (v{nova})"
    orc_anterior.status = "CANCELADO"
    orc_anterior.atualizado_em = tempo.agora()

    session.commit()
    session.refresh(nova)
    return nova


# ---------------------------------------------------------------------------
# Saída aprovada para compra
# ---------------------------------------------------------------------------

def get_itens_aprovados(session: Session, orcamento_id: int) -> list[ItemOrcamento]:
    """Retorna itens com status APROVADO_DIRETOR e cotação escolhida.

    Essa lista representa a saída final da camada de Orçamentos.
    """
    return (
        session.query(ItemOrcamento)
        .options(joinedload(ItemOrcamento.cotacoes))
        .filter(
            and_(
                ItemOrcamento.orcamento_id == orcamento_id,
                ItemOrcamento.status_item == "APROVADO_DIRETOR",
            )
        )
        .all()
    )


def remover_item_reprovado(session: Session, item_orc_id: int) -> None:
    """Desmarca da Lista Final o item reprovado pelo diretor.

    Para ESTOQUE: seta incluir_na_lista_final = False em ItemListaCompra.
    Para AVULSA:  seta incluir_na_lista_final = False em CompraAvulsa.
    O registro de ItemOrcamento é mantido para auditoria.
    """
    item = session.get(ItemOrcamento, item_orc_id)
    if item is None:
        raise ValueError(f"ItemOrcamento {item_orc_id} não encontrado.")
    if item.status_item != "REPROVADO_DIRETOR":
        raise ValueError("Só é possível remover itens com status REPROVADO_DIRETOR.")

    if item.tipo == "ESTOQUE" and item.item_lista_id:
        lista = session.get(ItemListaCompra, item.item_lista_id)
        if lista:
            lista.incluir_na_lista_final = False
            lista.atualizado_em = tempo.agora()

    elif item.tipo == "AVULSA" and item.compra_avulsa_id:
        avulsa = session.get(CompraAvulsa, item.compra_avulsa_id)
        if avulsa:
            avulsa.incluir_na_lista_final = False

    session.commit()


def deletar_orcamento(session: Session, orc_id: int) -> None:
    """Remove permanentemente um orçamento e todos os seus itens e cotações (cascade).

    Não permite deletar orçamentos ativos em edição (RASCUNHO, EM_COTACAO, ENVIADO_APROVACAO).
    """
    orc = session.get(Orcamento, orc_id)
    if orc is None:
        raise ValueError(f"Orçamento {orc_id} não encontrado.")
    _DELETAVEIS = {"APROVADO", "APROVADO_PARCIAL", "REPROVADO", "CANCELADO", "DEVOLVIDO_REVISAO", "REVISAR"}
    if orc.status not in _DELETAVEIS:
        raise ValueError(
            f"Não é possível excluir orçamento com status '{orc.status}'. Cancele-o primeiro."
        )
    session.delete(orc)
    session.commit()


def sincronizar_com_lista_final(session: Session, orc_id: int) -> dict:
    """Sincroniza ItemOrcamento com o estado atual da Lista Final.

    Compara os itens do orçamento com a Lista Final vigente e:
    - Adiciona itens novos (presentes na lista, ausentes no orçamento)
    - Remove itens excluídos (presentes no orçamento, ausentes na lista) junto
      com suas CotacaoOrcamento filhas
    - Atualiza quantidade_lista quando houver divergência

    Retorna {"adicionados": n, "removidos": n, "atualizados": n}.
    No-op se o orçamento não estiver em RASCUNHO ou EM_COTACAO.
    """
    orc = session.get(Orcamento, orc_id)
    if orc is None or orc.status not in ("RASCUNHO", "EM_COTACAO"):
        return {"adicionados": 0, "removidos": 0, "atualizados": 0}

    lista = get_lista_final_para_orcamento(session, orc.periodo_referencia)
    ids_lista_estoque = {il.id for il in lista["itens_estoque"]}
    ids_lista_avulso = {ca.id for ca in lista["itens_avulsos"]}

    itens_orc = session.query(ItemOrcamento).filter_by(orcamento_id=orc_id).all()
    orc_por_lista = {io.item_lista_id: io for io in itens_orc if io.tipo == "ESTOQUE" and io.item_lista_id}
    orc_por_avulso = {io.compra_avulsa_id: io for io in itens_orc if io.tipo == "AVULSA" and io.compra_avulsa_id}

    adicionados = removidos = atualizados = 0

    # Removidos — estão no orçamento mas não mais na Lista Final
    for io in itens_orc:
        excluir = (
            (io.tipo == "ESTOQUE" and io.item_lista_id not in ids_lista_estoque) or
            (io.tipo == "AVULSA" and io.compra_avulsa_id not in ids_lista_avulso)
        )
        if excluir:
            io.cotacao_escolhida_id = None
            session.flush()
            session.query(CotacaoOrcamento).filter_by(item_orcamento_id=io.id).delete()
            session.delete(io)
            removidos += 1

    session.flush()

    # Novos e atualizados — estoque
    for il in lista["itens_estoque"]:
        qtd = il.quantidade_final_definida or il.quantidade_sugerida or 1
        if il.id not in orc_por_lista:
            cat = il.item.categoria.nome if il.item and il.item.categoria else ""
            session.add(ItemOrcamento(
                orcamento_id=orc_id,
                item_lista_id=il.id,
                nome_item=il.item.nome if il.item else f"Item #{il.item_id}",
                categoria_nome=cat,
                tipo="ESTOQUE",
                quantidade_lista=qtd,
                quantidade_orcada=qtd,
                status_item="SEM_COTACAO",
            ))
            adicionados += 1
        else:
            io = orc_por_lista[il.id]
            if io.quantidade_lista != qtd:
                io.quantidade_lista = qtd
                atualizados += 1

    # Novos e atualizados — avulsos
    for ca in lista["itens_avulsos"]:
        if ca.id not in orc_por_avulso:
            session.add(ItemOrcamento(
                orcamento_id=orc_id,
                compra_avulsa_id=ca.id,
                nome_item=ca.nome_item,
                categoria_nome="Compra Avulsa",
                tipo="AVULSA",
                quantidade_lista=ca.quantidade,
                quantidade_orcada=ca.quantidade,
                status_item="SEM_COTACAO",
            ))
            adicionados += 1
        else:
            io = orc_por_avulso[ca.id]
            if io.quantidade_lista != ca.quantidade:
                io.quantidade_lista = ca.quantidade
                atualizados += 1

    if adicionados or removidos or atualizados:
        orc.atualizado_em = tempo.agora()
        session.commit()

    return {"adicionados": adicionados, "removidos": removidos, "atualizados": atualizados}


def get_fornecedores_para_item_orcamento(
    session: Session, item_orc_id: int
) -> list[Fornecedor]:
    """Retorna fornecedores vinculados ao item de estoque do ItemOrcamento.

    Segue a cadeia: ItemOrcamento → ItemListaCompra → Item → fornecedores_associados.
    Retorna [] para CompraAvulsa (tipo AVULSA) pois não há associação prévia.
    """
    item = session.query(ItemOrcamento).filter_by(id=item_orc_id).first()
    if not item or item.tipo == "AVULSA" or not item.item_lista_id:
        return []
    lista = session.query(ItemListaCompra).filter_by(id=item.item_lista_id).first()
    if not lista or not lista.item_id:
        return []
    estoque_item = (
        session.query(Item)
        .options(selectinload(Item.fornecedores_associados))
        .filter_by(id=lista.item_id)
        .first()
    )
    return list(estoque_item.fornecedores_associados) if estoque_item else []
