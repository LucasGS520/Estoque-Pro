""" Serviços de análise de compras, solicitações e lista final de compras.

Conecta o motor puro de estoque (`core.engine`) aos modelos persistidos no
banco. As funções deste módulo leem itens ativos, escolhem cotações válidas,
registram solicitações de materiais, consolidam necessidades por período e
persistem o resultado em `snapshots_analise` (legado) e `itens_lista_compra`.
"""

import datetime

from core import tempo
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from core.engine import (
    AnalysisResult, AnalysisSummary, ItemRecord, SolicitacaoRecord, StockAnalyzer,
)
from core.models import CompraAvulsa, CicloSolicitacaoMaterial, CicloSolicitacaoSetor, Fornecedor, Item, ItemListaCompra, RevisaoMensal, SnapshotAnalise, SolicitacaoMaterial, SolicitacaoPedido
from core.schemas import SolicitacaoMaterialCreate, SolicitacaoPedidoCreate
from services.fornecedor_service import get_best_price, get_best_prices_bulk


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _item_to_record(item: Item, session: Session) -> ItemRecord:
    """Converte um `Item` ORM em `ItemRecord` para o motor de análise."""
    melhor_preco = get_best_price(session, item.id)

    revisao = (
        session.query(RevisaoMensal)
        .filter(RevisaoMensal.item_id == item.id)
        .order_by(RevisaoMensal.criado_em.desc())
        .first()
    )
    margem = None
    if (
        revisao
        and revisao.consumo_mediana_diario is not None
        and revisao.intervalo_mediano_dias is not None
    ):
        margem = revisao.consumo_mediana_diario * revisao.intervalo_mediano_dias

    return ItemRecord(
        item_id=item.id,
        nome=item.nome,
        categoria=item.categoria.nome,
        qtd_atual=item.estoque_atual,
        estoque_minimo=item.estoque_minimo_vigente,
        estoque_ideal=item.estoque_ideal_vigente,
        preco_unitario=melhor_preco.preco_unitario if melhor_preco else None,
        fornecedor_sugerido=melhor_preco.fornecedor.nome if melhor_preco else None,
        fornecedor_sugerido_id=melhor_preco.fornecedor_id if melhor_preco else None,
        margem_operacional=margem,
        consumo_mediana_diario=revisao.consumo_mediana_diario if revisao else None,
    )


# ---------------------------------------------------------------------------
# Funções legadas — mantidas intactas para compatibilidade com Orçamentos
# ---------------------------------------------------------------------------

def run_analysis(session: Session) -> tuple[list[AnalysisResult], AnalysisSummary]:
    """Executa análise de reposição sem solicitações e substitui o snapshot anterior."""
    itens = (
        session.query(Item)
        .options(joinedload(Item.categoria))
        .filter(Item.ativo == True)  # noqa: E712
        .all()
    )
    records = [_item_to_record(item, session) for item in itens]

    analyzer = StockAnalyzer()
    results = analyzer.run(records)
    summary = analyzer.summary(results)

    session.query(SnapshotAnalise).delete()
    for r in results:
        snap = SnapshotAnalise(
            item_id=r.item_id,
            status=r.status.value,
            quantidade_recomendar=r.quantidade_recomendar,
            valor_estimado=r.valor_estimado,
            fornecedor_sugerido_id=r.fornecedor_sugerido_id,
        )
        session.add(snap)
    session.commit()

    return results, summary


def get_latest_snapshot(session: Session) -> list[SnapshotAnalise]:
    """Retorna os snapshots atualmente persistidos, do mais recente ao antigo."""
    return (
        session.query(SnapshotAnalise)
        .options(joinedload(SnapshotAnalise.fornecedor_sugerido))
        .order_by(SnapshotAnalise.criado_em.desc())
        .all()
    )


def get_purchase_list(session: Session) -> list[SnapshotAnalise]:
    """Retorna snapshots que exigem compra ou atenção por estoque zerado."""
    return (
        session.query(SnapshotAnalise)
        .options(joinedload(SnapshotAnalise.fornecedor_sugerido))
        .filter(SnapshotAnalise.status.in_(["comprar", "zerado"]))
        .all()
    )


def get_painel_reposicao(session: Session) -> list[AnalysisResult]:
    """Retorna análise pura de estoque (sem solicitações) para o Painel de Reposição.

    Calculado em memória — sempre reflete o estado atual do estoque, sem precisar
    de um botão de atualização. Não altera nenhuma tabela persistida.
    """
    itens = (
        session.query(Item)
        .options(joinedload(Item.categoria))
        .filter(Item.ativo == True)  # noqa: E712
        .all()
    )
    records = [_item_to_record(item, session) for item in itens]
    analyzer = StockAnalyzer()
    return analyzer.run_puro(records)


# ---------------------------------------------------------------------------
# Solicitações de materiais
# ---------------------------------------------------------------------------

def criar_solicitacao(
    session: Session, dados: SolicitacaoMaterialCreate
) -> SolicitacaoMaterial:
    """Registra uma nova solicitação de compra para um período."""
    sol = SolicitacaoMaterial(
        item_id=dados.item_id,
        nome_item_livre=dados.nome_item_livre,
        setor_id=dados.setor_id,
        solicitante=dados.solicitante,
        quantidade_solicitada=dados.quantidade_solicitada,
        observacao=dados.observacao,
        urgente=dados.urgente,
        periodo_referencia=dados.periodo_referencia,
        status="pendente",
    )
    session.add(sol)
    session.commit()
    session.refresh(sol)
    return sol


def criar_pedido_solicitacao(
    session: Session, dados: SolicitacaoPedidoCreate
) -> SolicitacaoPedido:
    """Cria o cabeçalho do pedido e todos os itens em uma única transação.

    Exige um ciclo de solicitações aberto e dentro do prazo para o período —
    mesma regra do formulário (Solicitar), agora garantida na camada de
    serviço. O ciclo_id do pedido vem do ciclo encontrado, não do chamador.
    Levanta ValueError quando não há ciclo, o ciclo está encerrado ou o
    prazo de resposta expirou.
    """
    ciclo = (
        session.query(CicloSolicitacaoMaterial)
        .filter(CicloSolicitacaoMaterial.periodo_referencia == dados.periodo_referencia)
        .order_by(CicloSolicitacaoMaterial.criado_em.desc())
        .first()
    )
    if ciclo is None:
        raise ValueError(
            "Nenhum ciclo de solicitações foi aberto para este período."
        )
    if ciclo.status != "aberto":
        raise ValueError(
            "O ciclo de solicitações deste período já foi encerrado. "
            "Procure o setor de Compras."
        )
    if ciclo.prazo_resposta_em is not None and ciclo.prazo_resposta_em < tempo.agora():
        raise ValueError(
            "O prazo de resposta do ciclo deste período expirou. "
            "Procure o setor de Compras."
        )

    pedido = SolicitacaoPedido(
        setor_id=dados.setor_id,
        solicitante=dados.solicitante,
        periodo_referencia=dados.periodo_referencia,
        ciclo_id=ciclo.id,
        status="enviado",
    )
    session.add(pedido)
    session.flush()  # gera pedido.id sem commitar

    for item in dados.itens:
        sol = SolicitacaoMaterial(
            item_id=item.item_id,
            nome_item_livre=item.nome_item_livre,
            setor_id=dados.setor_id,
            solicitante=dados.solicitante,
            quantidade_solicitada=item.quantidade_solicitada,
            observacao=item.observacao,
            urgente=item.urgente,
            periodo_referencia=dados.periodo_referencia,
            status="pendente",
            pedido_id=pedido.id,
        )
        session.add(sol)

    # Marca o setor como respondido no ciclo, dentro da mesma transação
    if dados.setor_id is not None:
        participante = (
            session.query(CicloSolicitacaoSetor)
            .filter_by(ciclo_id=ciclo.id, setor_id=dados.setor_id)
            .first()
        )
        if participante:
            participante.status = "respondido"
            participante.respondido_em = tempo.agora()

    session.commit()
    session.refresh(pedido)
    return pedido


def listar_solicitacoes(
    session: Session,
    periodo: datetime.date,
    setor_id: Optional[int] = None,
) -> list[SolicitacaoMaterial]:
    """Lista solicitações de um período, com eager load de item e setor."""
    q = (
        session.query(SolicitacaoMaterial)
        .options(
            joinedload(SolicitacaoMaterial.item).joinedload(Item.categoria),
            joinedload(SolicitacaoMaterial.setor),
        )
        .filter(SolicitacaoMaterial.periodo_referencia == periodo)
    )
    if setor_id is not None:
        q = q.filter(SolicitacaoMaterial.setor_id == setor_id)
    return q.order_by(SolicitacaoMaterial.urgente.desc(), SolicitacaoMaterial.criado_em.desc()).all()


def deletar_solicitacao(session: Session, sol_id: int) -> None:
    """Remove uma solicitação de compra e suas compras avulsas associadas.

    Se for a última solicitação do pedido, remove também o cabeçalho
    (SolicitacaoPedido) para não deixar pedidos órfãos sem itens.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol:
        pedido_id = sol.pedido_id
        session.query(CompraAvulsa).filter(CompraAvulsa.solicitacao_id == sol_id).delete()
        session.delete(sol)
        session.flush()
        if pedido_id is not None:
            restantes = (
                session.query(SolicitacaoMaterial)
                .filter(SolicitacaoMaterial.pedido_id == pedido_id)
                .count()
            )
            if restantes == 0:
                pedido = session.get(SolicitacaoPedido, pedido_id)
                if pedido:
                    session.delete(pedido)
        session.commit()


def aprovar_solicitacao(session: Session, sol_id: int) -> SolicitacaoMaterial:
    """Marca a solicitação como aprovada pelo responsável (status → 'aprovada').

    Apenas solicitações com status 'validada' podem ser aprovadas.
    Solicitações aprovadas entram na próxima consolidação de período.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    if sol.status != "validada":
        raise ValueError(
            f"Só é possível aprovar solicitações com status 'validada'. "
            f"Status atual: '{sol.status}'"
        )
    sol.status = "aprovada"
    session.commit()
    session.refresh(sol)
    return sol


def rejeitar_solicitacao(session: Session, sol_id: int) -> SolicitacaoMaterial:
    """Marca a solicitação como rejeitada pelo responsável (status → 'rejeitada').

    Solicitações rejeitadas não entram na consolidação de período.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    sol.status = "rejeitada"
    session.commit()
    session.refresh(sol)
    return sol


def revertir_solicitacao(session: Session, sol_id: int) -> SolicitacaoMaterial:
    """Reverte uma solicitação aprovada ou rejeitada de volta para 'validada'.

    Permite desfazer uma aprovação ou rejeição antes da consolidação ser executada.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    if sol.status not in {"aprovada", "rejeitada"}:
        raise ValueError(
            f"Só é possível reverter solicitações com status 'aprovada' ou 'rejeitada'. "
            f"Status atual: '{sol.status}'"
        )
    sol.status = "validada"
    session.commit()
    session.refresh(sol)
    return sol


def vincular_item_existente(
    session: Session, sol_id: int, item_id: int
) -> SolicitacaoMaterial:
    """Vincula uma solicitação 'novo_item' a um item já existente no estoque.

    Reclassifica automaticamente: 'aprovada' se o item tiver mínimo e ideal
    vigentes > 0, ou 'sem_parametros' caso contrário.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    sol.item_id = item_id
    session.flush()
    item = session.get(Item, item_id)
    tem_params = (
        item is not None
        and (item.estoque_minimo_vigente or 0) > 0
        and (item.estoque_ideal_vigente or 0) > 0
    )
    sol.status = "aprovada" if tem_params else "sem_parametros"
    session.commit()
    session.refresh(sol)
    return sol


def criar_item_e_vincular(
    session: Session,
    sol_id: int,
    *,
    categoria_id: int,
    nome: str,
    unidade: str = "un",
    estoque_atual: int = 0,
    minimo: Optional[int] = None,
    ideal: Optional[int] = None,
    observacoes: Optional[str] = None,
    ativo: bool = True,
    fornecedor_ids: Optional[list[int]] = None,
) -> SolicitacaoMaterial:
    """Cria um novo item de estoque e vincula à solicitação.

    Se mínimo e ideal forem definidos (> 0), a solicitação é automaticamente
    aprovada. Caso contrário, fica como 'sem_parametros'.
    """
    from services.estoque_service import atualizar_fornecedores_item, create_item  # lazy — evita import circular
    item = create_item(
        session, categoria_id, nome, unidade,
        estoque_atual, minimo, ideal, observacoes, ativo,
    )
    if fornecedor_ids:
        atualizar_fornecedores_item(session, item.id, fornecedor_ids)
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    sol.item_id = item.id
    tem_params = (minimo or 0) > 0 and (ideal or 0) > 0
    if tem_params:
        sol.status = "aprovada"
    else:
        sol.status = "sem_parametros"
    session.commit()
    session.refresh(sol)
    return sol


def registrar_compra_avulsa(
    session: Session,
    sol_id: int,
    nome_item: Optional[str] = None,
    unidade: str = "un",
    quantidade: Optional[int] = None,
    urgente: Optional[bool] = None,
    observacao: Optional[str] = None,
    incluir_na_lista_final: bool = True,
) -> CompraAvulsa:
    """Resolve uma solicitação 'novo_item' como compra avulsa (sem cadastro no estoque).

    Cria um registro em CompraAvulsa e marca a solicitação como
    'compra_avulsa_aprovada', removendo-a da fila de pendências.
    Os parâmetros nome_item, unidade, quantidade e urgente sobrescrevem os dados
    da solicitação original se fornecidos.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    ca = CompraAvulsa(
        solicitacao_id=sol.id,
        periodo_referencia=sol.periodo_referencia,
        nome_item=nome_item if nome_item is not None else (sol.nome_item_livre or ""),
        unidade=unidade,
        quantidade=quantidade if quantidade is not None else sol.quantidade_solicitada,
        setor_id=sol.setor_id,
        solicitante=sol.solicitante,
        observacao=observacao if observacao is not None else sol.observacao,
        urgente=urgente if urgente is not None else sol.urgente,
        incluir_na_lista_final=incluir_na_lista_final,
    )
    session.add(ca)
    sol.status = "compra_avulsa_aprovada"
    session.commit()
    session.refresh(ca)
    return ca


def desfazer_compra_avulsa(session: Session, sol_id: int) -> SolicitacaoMaterial:
    """Desfaz uma compra avulsa: remove o registro CompraAvulsa e reverte a
    solicitação para 'novo_item', permitindo nova resolução.
    """
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol is None:
        raise ValueError(f"Solicitação {sol_id} não encontrada")
    if sol.status != "compra_avulsa_aprovada":
        raise ValueError(
            f"Só é possível desfazer solicitações com status 'compra_avulsa_aprovada'. "
            f"Status atual: '{sol.status}'"
        )
    session.query(CompraAvulsa).filter(CompraAvulsa.solicitacao_id == sol_id).delete()
    sol.status = "novo_item"
    session.commit()
    session.refresh(sol)
    return sol


def aplicar_parametros_e_reclassificar(
    session: Session,
    item_id: int,
    minimo: int,
    ideal: int,
    periodo: datetime.date,
) -> int:
    """Define mínimo/ideal manual para o item e aprova todas as solicitações
    'sem_parametros' do mesmo item+período.

    Retorna a quantidade de solicitações aprovadas.
    """
    from services.calculos_service import aplicar_minimo_ideal_manual
    aplicar_minimo_ideal_manual(session, item_id, minimo, ideal)
    afetadas = (
        session.query(SolicitacaoMaterial)
        .filter(
            SolicitacaoMaterial.item_id == item_id,
            SolicitacaoMaterial.periodo_referencia == periodo,
            SolicitacaoMaterial.status == "sem_parametros",
        )
        .all()
    )
    for sol in afetadas:
        sol.status = "aprovada"
    session.commit()
    return len(afetadas)


def get_compras_avulsas_periodo(
    session: Session, periodo: datetime.date
) -> list[CompraAvulsa]:
    """Retorna compras avulsas do período marcadas para incluir na lista final."""
    return (
        session.query(CompraAvulsa)
        .options(joinedload(CompraAvulsa.setor))
        .filter(
            CompraAvulsa.periodo_referencia == periodo,
            CompraAvulsa.incluir_na_lista_final.is_(True),
        )
        .order_by(CompraAvulsa.urgente.desc(), CompraAvulsa.criado_em)
        .all()
    )


def get_todas_avulsas_periodo(
    session: Session, periodo: datetime.date
) -> list[CompraAvulsa]:
    """Retorna todas as compras avulsas do período (sem filtro de incluir_na_lista_final).

    Usada na tabela de consolidação para permitir que o gestor decida quais incluir.
    """
    return (
        session.query(CompraAvulsa)
        .options(joinedload(CompraAvulsa.setor))
        .filter(CompraAvulsa.periodo_referencia == periodo)
        .order_by(CompraAvulsa.urgente.desc(), CompraAvulsa.criado_em)
        .all()
    )


def atualizar_compra_avulsa(
    session: Session,
    ca_id: int,
    quantidade: Optional[int] = None,
    incluir_na_lista_final: Optional[bool] = None,
) -> CompraAvulsa:
    """Atualiza quantidade e/ou flag incluir_na_lista_final de uma compra avulsa.

    Quantidade, quando informada, deve ser >= 1.
    """
    ca = session.get(CompraAvulsa, ca_id)
    if ca is None:
        raise ValueError(f"Compra avulsa {ca_id} não encontrada")
    if quantidade is not None:
        if quantidade < 1:
            raise ValueError(
                "Quantidade da compra avulsa deve ser um número inteiro maior que zero."
            )
        ca.quantidade = quantidade
    if incluir_na_lista_final is not None:
        ca.incluir_na_lista_final = incluir_na_lista_final
    session.commit()
    return ca


def classificar_solicitacoes_periodo(
    session: Session, periodo: datetime.date
) -> dict[str, int]:
    """Classifica/reclassifica solicitações pendentes e não validadas do período.

    - item_id ausente (nome livre)                        → "novo_item"
    - item_id presente + tem mínimo e ideal               → "validada"
    - item_id presente + falta mínimo ou ideal (ou ambos) → "sem_parametros"
    - "novo_item" com item_id preenchido (vinculação manual) → reclassificado acima

    Retorna contagens por status: {validadas, novo_item, sem_parametros}.
    """
    pendentes = (
        session.query(SolicitacaoMaterial)
        .filter(
            SolicitacaoMaterial.periodo_referencia == periodo,
            SolicitacaoMaterial.status.in_([
                # "aprovada" e "rejeitada" são intencionalmente omitidas:
                # decisão humana já tomada, não deve ser sobrescrita.
                "pendente", "sem_parametros", "novo_item",
                "pendente_parametrizacao", "pendente_cadastro",  # legado
            ]),
        )
        .all()
    )

    contagens: dict[str, int] = {"validadas": 0, "novo_item": 0, "sem_parametros": 0}

    for sol in pendentes:
        if sol.item_id is None:
            sol.status = "novo_item"
            contagens["novo_item"] += 1
        else:
            item = session.get(Item, sol.item_id)
            tem_minimo = item is not None and (item.estoque_minimo_vigente or 0) > 0
            tem_ideal  = item is not None and (item.estoque_ideal_vigente or 0) > 0
            if tem_minimo and tem_ideal:
                sol.status = "validada"
                contagens["validadas"] += 1
            else:
                sol.status = "sem_parametros"
                contagens["sem_parametros"] += 1

    session.commit()
    return contagens


# ---------------------------------------------------------------------------
# Consolidação do período
# ---------------------------------------------------------------------------

def consolidar_periodo(
    session: Session, periodo: datetime.date
) -> tuple[list[AnalysisResult], AnalysisSummary]:
    """Cruza estoque real com solicitações do período e persiste ItemListaCompra.

    Preserva `quantidade_final_definida`, `motivo` e `incluir_na_lista_final` de
    registros que o responsável já editou manualmente (quantidade_final_definida
    não nula). Para os demais, reescreve com o novo valor sugerido.
    """
    # Carrega itens ativos com categorias e melhores preços
    itens = (
        session.query(Item)
        .options(joinedload(Item.categoria))
        .filter(Item.ativo == True)  # noqa: E712
        .all()
    )

    # Carrega e agrupa somente solicitações aprovadas pelo responsável
    solicitacoes = (
        session.query(SolicitacaoMaterial)
        .options(joinedload(SolicitacaoMaterial.setor))
        .filter(
            SolicitacaoMaterial.periodo_referencia == periodo,
            SolicitacaoMaterial.status == "aprovada",
        )
        .all()
    )
    sols_por_item: dict[int, list[SolicitacaoRecord]] = {}
    for sol in solicitacoes:
        if sol.item_id is None:
            continue
        setor_nome = sol.setor.nome if sol.setor else (sol.solicitante or "—")
        rec = SolicitacaoRecord(
            setor=setor_nome,
            solicitante=sol.solicitante,
            quantidade=sol.quantidade_solicitada,
        )
        sols_por_item.setdefault(sol.item_id, []).append(rec)

    # Carrega melhores preços e consumos em bulk (evita N+1)
    ids_itens = [i.id for i in itens]
    melhores_precos = get_best_prices_bulk(session, ids_itens)
    # Revisão mais recente por item (order desc + setdefault mantém só a primeira)
    revisoes_por_item: dict[int, RevisaoMensal] = {}
    for r in (
        session.query(RevisaoMensal)
        .filter(RevisaoMensal.item_id.in_(ids_itens))
        .order_by(RevisaoMensal.item_id, RevisaoMensal.criado_em.desc())
        .all()
    ):
        revisoes_por_item.setdefault(r.item_id, r)

    # Monta ItemRecords com solicitações, preços e consumo
    records: list[ItemRecord] = []
    for item in itens:
        melhor_preco = melhores_precos.get(item.id)
        revisao = revisoes_por_item.get(item.id)
        margem = None
        if (
            revisao
            and revisao.consumo_mediana_diario is not None
            and revisao.intervalo_mediano_dias is not None
        ):
            margem = revisao.consumo_mediana_diario * revisao.intervalo_mediano_dias
        rec = ItemRecord(
            item_id=item.id,
            nome=item.nome,
            categoria=item.categoria.nome,
            qtd_atual=item.estoque_atual,
            estoque_minimo=item.estoque_minimo_vigente,
            estoque_ideal=item.estoque_ideal_vigente,
            preco_unitario=melhor_preco.preco_unitario if melhor_preco else None,
            fornecedor_sugerido=melhor_preco.fornecedor.nome if melhor_preco else None,
            fornecedor_sugerido_id=melhor_preco.fornecedor_id if melhor_preco else None,
            margem_operacional=margem,
            consumo_mediana_diario=revisao.consumo_mediana_diario if revisao else None,
            solicitations=sols_por_item.get(item.id, []),
        )
        records.append(rec)

    analyzer = StockAnalyzer()
    results = analyzer.run_consolidado(records)
    summary = analyzer.summary(results)

    # Upsert em ItemListaCompra
    existentes: dict[int, ItemListaCompra] = {
        e.item_id: e
        for e in session.query(ItemListaCompra)
        .filter(ItemListaCompra.periodo_referencia == periodo)
        .all()
    }

    for r in results:
        editado_manualmente = (
            r.item_id in existentes
            and existentes[r.item_id].quantidade_final_definida is not None
        )

        if r.item_id in existentes:
            lista = existentes[r.item_id]
            lista.status = r.status.value
            lista.estoque_atual_snap = r.qtd_atual
            lista.estoque_minimo_snap = r.estoque_minimo
            lista.estoque_ideal_snap = r.estoque_ideal
            lista.total_solicitado = r.total_solicitado
            lista.quantidade_sugerida = r.quantidade_recomendar
            lista.motivo_sugestao = r.motivo_sugestao
            lista.valor_estimado = r.valor_estimado
            lista.fornecedor_sugerido_id = r.fornecedor_sugerido_id
            lista.atualizado_em = tempo.agora()
            # Preserva decisões manuais se já foram registradas
            if not editado_manualmente:
                lista.quantidade_final_definida = None
                lista.observacao = None
                lista.incluir_na_lista_final = False
        else:
            lista = ItemListaCompra(
                item_id=r.item_id,
                periodo_referencia=periodo,
                status=r.status.value,
                estoque_atual_snap=r.qtd_atual,
                estoque_minimo_snap=r.estoque_minimo,
                estoque_ideal_snap=r.estoque_ideal,
                total_solicitado=r.total_solicitado,
                quantidade_sugerida=r.quantidade_recomendar,
                motivo_sugestao=r.motivo_sugestao,
                valor_estimado=r.valor_estimado,
                fornecedor_sugerido_id=r.fornecedor_sugerido_id,
            )
            session.add(lista)

    session.commit()
    return results, summary


# ---------------------------------------------------------------------------
# Gestão da Lista Final
# ---------------------------------------------------------------------------

def get_consolidacao_periodo(
    session: Session, periodo: datetime.date
) -> list[ItemListaCompra]:
    """Retorna todos os itens consolidados de um período, ordenados por status."""
    _STATUS_SORT = {
        "zerado": 0, "abaixo_minimo": 1, "abaixo_ideal": 2, "sem_parametro": 3, "ok": 4,
        # Legado (registros anteriores à migração)
        "comprar": 1, "sem_minimo_definido": 3, "excesso": 4,
    }
    items = (
        session.query(ItemListaCompra)
        .options(
            joinedload(ItemListaCompra.item).joinedload(Item.categoria),
            joinedload(ItemListaCompra.fornecedor_sugerido),
        )
        .filter(ItemListaCompra.periodo_referencia == periodo)
        .all()
    )
    items.sort(key=lambda x: (
        _STATUS_SORT.get(x.status, 9),
        x.item.categoria.nome if x.item and x.item.categoria else "",
        x.item.nome if x.item else "",
    ))
    return items


def get_lista_final(
    session: Session, periodo: datetime.date
) -> list[ItemListaCompra]:
    """Retorna apenas os itens aprovados para orçamento no período."""
    return (
        session.query(ItemListaCompra)
        .options(
            joinedload(ItemListaCompra.item).joinedload(Item.categoria),
            joinedload(ItemListaCompra.fornecedor_sugerido),
        )
        .filter(
            and_(
                ItemListaCompra.periodo_referencia == periodo,
                ItemListaCompra.incluir_na_lista_final == True,  # noqa: E712
            )
        )
        .all()
    )


def aprovar_item(
    session: Session,
    lista_id: int,
    qtd_final: int,
    observacao: Optional[str] = None,
) -> ItemListaCompra:
    """Aprova um item para a lista final com quantidade e observação definidas.

    A quantidade final é obrigatória e deve ser >= 1 — item aprovado para a
    lista final nunca pode ficar com quantidade nula ou zerada.
    """
    if qtd_final is None or qtd_final < 1:
        raise ValueError(
            "Quantidade final deve ser um número inteiro maior que zero."
        )
    lista = session.get(ItemListaCompra, lista_id)
    if lista is None:
        raise ValueError(f"ItemListaCompra {lista_id} não encontrado")
    lista.quantidade_final_definida = qtd_final
    lista.observacao = observacao
    lista.incluir_na_lista_final = True
    lista.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(lista)
    return lista


def remover_da_lista(session: Session, lista_id: int) -> ItemListaCompra:
    """Remove um item da lista final (mantém o registro, apenas desmarca a flag)."""
    lista = session.get(ItemListaCompra, lista_id)
    if lista is None:
        raise ValueError(f"ItemListaCompra {lista_id} não encontrado")
    lista.incluir_na_lista_final = False
    lista.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(lista)
    return lista


def get_pedidos_setor_periodo(
    session: Session,
    setor_id: int,
    periodo: datetime.date,
) -> list[SolicitacaoPedido]:
    """Retorna os pedidos enviados por um setor em um período, do mais recente ao mais antigo."""
    return (
        session.query(SolicitacaoPedido)
        .options(joinedload(SolicitacaoPedido.itens))
        .filter(
            SolicitacaoPedido.setor_id == setor_id,
            SolicitacaoPedido.periodo_referencia == periodo,
        )
        .order_by(SolicitacaoPedido.criado_em.asc())
        .all()
    )


def get_periodos_com_consolidacao(session: Session) -> list[datetime.date]:
    """Retorna os períodos que já possuem consolidação registrada."""
    rows = (
        session.query(ItemListaCompra.periodo_referencia)
        .distinct()
        .order_by(ItemListaCompra.periodo_referencia.desc())
        .all()
    )
    return [r[0] for r in rows]
