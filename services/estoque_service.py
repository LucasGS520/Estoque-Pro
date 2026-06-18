""" Serviços de consulta e manutenção do estoque.

Concentra regras de negócio para itens, categorias, movimentações e KPIs. As
funções de criação, atualização, exclusão e movimentação fazem `commit`; as
funções de consulta apenas leem dados.
"""

import datetime

from core import tempo
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session, joinedload, selectinload

from core.models import (
    Categoria,
    CicloSolicitacaoMaterial,
    CicloSolicitacaoSetor,
    DevolucaoMaterial,
    Fornecedor,
    Item,
    Movimentacao,
    Setor,
    SolicitacaoMaterial,
)
from core.ui import limpar_telefone
import services.push_service as push_service


def _normalizar(texto: str) -> str:
    """Normaliza texto para comparação sem acentos, caixa ou espaços extras."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return " ".join(nfkd.encode("ascii", "ignore").decode().lower().split())


def get_all_itens(
    session: Session,
    categoria_id: Optional[int] = None,
    apenas_ativos: bool = True,
) -> list[Item]:
    """Lista itens com categoria carregada, filtrando por categoria e atividade."""
    q = session.query(Item).options(joinedload(Item.categoria))
    if apenas_ativos:
        q = q.filter(Item.ativo == True)  # noqa: E712
    if categoria_id is not None:
        q = q.filter(Item.categoria_id == categoria_id)
    return q.order_by(Item.categoria_id, Item.nome).all()


def get_item_by_id(session: Session, item_id: int) -> Optional[Item]:
    """Busca um item pelo ID ou retorna `None` quando não existir."""
    return session.query(Item).filter_by(id=item_id).first()


def get_categorias(session: Session) -> list[Categoria]:
    """Lista todas as categorias em ordem alfabética."""
    return session.query(Categoria).order_by(Categoria.nome).all()


def update_limites(
    session: Session,
    item_id: int,
    estoque_minimo: int,
    estoque_ideal: int,
    unidade: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> Item:
    """Atualiza limites, unidade e observações de um item existente.

    Persiste a alteração com `commit` e retorna o item atualizado. Lança
    `ValueError` quando o item não existe.
    """
    item = session.query(Item).filter_by(id=item_id).first()
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    item.estoque_minimo = estoque_minimo
    item.estoque_ideal = estoque_ideal
    if unidade:
        item.unidade = unidade
    if observacoes is not None:
        item.observacoes = observacoes
    item.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(item)
    return item


def registrar_movimentacao(
    session: Session,
    item_id: int,
    tipo: str,
    quantidade: int,
    motivo: Optional[str] = None,
    operador: Optional[str] = None,
    retirado_por: Optional[str] = None,
    setor_id: Optional[int] = None,
) -> Item:
    """Registra entrada ou saída e atualiza o saldo atual do item.

    Regras:
    - `saida` exige `setor_id` e não permite retirar mais do que o disponível.
    - `entrada` não exige setor.
    """
    item = session.query(Item).filter_by(id=item_id).first()
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")

    if tipo not in ("entrada", "saida"):
        raise ValueError(f"Tipo de movimentação inválido: '{tipo}'. Use 'entrada' ou 'saida'.")

    if tipo == "saida":
        if setor_id is None:
            raise ValueError("Setor é obrigatório para registrar uma saída.")
        if quantidade > item.estoque_atual:
            raise ValueError(
                f"Quantidade insuficiente: {item.estoque_atual} {item.unidade} disponível(is), "
                f"tentou retirar {quantidade}."
            )

    qtd_anterior = item.estoque_atual
    nova_qtd = qtd_anterior + quantidade if tipo == "entrada" else qtd_anterior - quantidade

    mov = Movimentacao(
        item_id=item_id,
        tipo=tipo,
        quantidade=quantidade,
        quantidade_anterior=qtd_anterior,
        quantidade_nova=nova_qtd,
        motivo=motivo,
        operador=operador,
        retirado_por=retirado_por or operador,
        setor_id=setor_id,
    )
    session.add(mov)

    item.estoque_atual = nova_qtd
    item.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(item)

    # Notifica o responsável quando uma saída provoca mudança para status crítico (edge trigger)
    if tipo == "saida":
        _minimo = item.estoque_minimo_vigente or 0
        if nova_qtd <= 0 and qtd_anterior > 0:
            push_service.notificar_estoque_zerado(item.nome)
        elif _minimo > 0 and nova_qtd < _minimo and qtd_anterior >= _minimo:
            push_service.notificar_estoque_abaixo_minimo(item.nome, nova_qtd, _minimo)

    return item


def get_historico_movimentacoes(
    session: Session,
    item_id: Optional[int] = None,
    tipo: Optional[str] = None,
    limit: int = 200,
) -> list[Movimentacao]:
    """Consulta o histórico de movimentações com filtros opcionais."""
    q = session.query(Movimentacao)
    if item_id:
        q = q.filter(Movimentacao.item_id == item_id)
    if tipo:
        q = q.filter(Movimentacao.tipo == tipo)
    return q.order_by(Movimentacao.criado_em.desc()).limit(limit).all()


def get_tabela_mestre(
    session: Session,
    categoria_id: Optional[int] = None,
    apenas_ativos: bool = True,
) -> list[dict]:
    """Retorna visão consolidada por item para a tabela mestre de visualização.

    Cada dict contém campos de cadastro do item, última movimentação, lista de
    fornecedores com preço ativo e status operacional calculado com as mesmas
    regras do motor de análise.
    """
    q = (
        session.query(Item)
        .options(
            joinedload(Item.categoria),
            selectinload(Item.movimentacoes).selectinload(Movimentacao.setor),
            selectinload(Item.fornecedores_associados),
        )
    )
    if apenas_ativos:
        q = q.filter(Item.ativo == True)  # noqa: E712
    if categoria_id is not None:
        q = q.filter(Item.categoria_id == categoria_id)
    itens = q.order_by(Item.categoria_id, Item.nome).all()

    rows = []
    for item in itens:
        ultima_mov = max(item.movimentacoes, key=lambda m: m.criado_em, default=None)

        nomes_forn = [f.nome for f in item.fornecedores_associados]

        minimo_v = item.estoque_minimo_vigente
        ideal_v = item.estoque_ideal_vigente
        sem_limites = minimo_v == 0 and ideal_v == 0
        if sem_limites:
            status = "sem_parametro"
        elif item.estoque_atual == 0:
            status = "zerado"
        elif item.estoque_atual <= minimo_v:
            status = "abaixo_minimo"
        elif item.estoque_atual <= ideal_v:
            status = "abaixo_ideal"
        else:
            status = "ok"

        rows.append({
            "id": item.id,
            "categoria": item.categoria.nome,
            "item": item.nome,
            "unidade": item.unidade,
            "atual": item.estoque_atual,
            "minimo": minimo_v,
            "ideal": ideal_v,
            "minimo_sugerido": item.estoque_minimo_sugerido,
            "ideal_sugerido": item.estoque_ideal_sugerido,
            "origem_minimo": item.origem_minimo,
            "origem_ideal": item.origem_ideal,
            "status": status,
            "ultima_mov_data": ultima_mov.criado_em if ultima_mov else None,
            "ultima_mov_tipo": ultima_mov.tipo if ultima_mov else None,
            "ultima_mov_quantidade": ultima_mov.quantidade if ultima_mov else None,
            "ultima_mov_setor": ultima_mov.setor.nome if ultima_mov and ultima_mov.setor else None,
            "fornecedores": ", ".join(nomes_forn) if nomes_forn else "-",
            "observacoes": item.observacoes or "",
        })

    return rows


def atualizar_fornecedores_item(
    session: Session,
    item_id: int,
    fornecedor_ids: list[int],
) -> None:
    """Substitui os fornecedores associados ao item pela lista de IDs fornecida."""
    item = (
        session.query(Item)
        .options(selectinload(Item.fornecedores_associados))
        .filter_by(id=item_id)
        .first()
    )
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    item.fornecedores_associados = (
        session.query(Fornecedor).filter(Fornecedor.id.in_(fornecedor_ids)).all()
        if fornecedor_ids else []
    )
    session.commit()


def get_kpis_basicos(session: Session) -> dict:
    """Calcula indicadores simples de cadastro de itens e limites definidos."""
    total = session.query(Item).filter(Item.ativo == True).count()  # noqa: E712
    sem_minimo = (
        session.query(Item)
        .filter(Item.ativo == True, Item.estoque_minimo_vigente == 0, Item.estoque_ideal_vigente == 0)  # noqa: E712
        .count()
    )
    return {
        "total_itens": total,
        "itens_sem_minimo_definido": sem_minimo,
        "itens_com_minimo": total - sem_minimo,
    }


def create_item(
    session: Session,
    categoria_id: int,
    nome: str,
    unidade: str = "un",
    estoque_atual: int = 0,
    estoque_minimo_manual: Optional[int] = None,
    estoque_ideal_manual: Optional[int] = None,
    observacoes: Optional[str] = None,
    ativo: bool = True,
) -> Item:
    """Cria um item em uma categoria existente.

    Valida categoria e duplicidade por nome normalizado dentro da mesma
    categoria. Persiste com `commit` e retorna o item criado.

    Se estoque_minimo_manual/estoque_ideal_manual forem fornecidos (> 0), os
    vigentes são inicializados como manuais. Caso contrário, aguardam revisão
    automática.
    """
    cat = session.query(Categoria).filter_by(id=categoria_id).first()
    if not cat:
        raise ValueError(f"Categoria {categoria_id} não encontrada")

    nome_norm = _normalizar(nome)
    duplicado = (
        session.query(Item)
        .filter_by(nome_normalizado=nome_norm, categoria_id=categoria_id)
        .first()
    )
    if duplicado:
        raise ValueError(f"Já existe um item com o nome '{nome}' nessa categoria")

    agora = tempo.agora()
    tem_manual_min = estoque_minimo_manual is not None and estoque_minimo_manual > 0
    tem_manual_ideal = estoque_ideal_manual is not None and estoque_ideal_manual > 0

    item = Item(
        categoria_id=categoria_id,
        nome=nome.strip(),
        nome_normalizado=nome_norm,
        unidade=unidade,
        estoque_atual=estoque_atual,
        estoque_minimo=estoque_minimo_manual or 0,   # campo legado
        estoque_ideal=estoque_ideal_manual or 0,      # campo legado
        observacoes=observacoes,
        ativo=ativo,
        estoque_minimo_manual=estoque_minimo_manual if tem_manual_min else None,
        estoque_ideal_manual=estoque_ideal_manual if tem_manual_ideal else None,
        data_definicao_minimo_manual=agora if tem_manual_min else None,
        data_definicao_ideal_manual=agora if tem_manual_ideal else None,
        estoque_minimo_vigente=estoque_minimo_manual if tem_manual_min else 0,
        estoque_ideal_vigente=estoque_ideal_manual if tem_manual_ideal else 0,
        origem_minimo="Manual" if tem_manual_min else None,
        origem_ideal="Manual" if tem_manual_ideal else None,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def update_item_completo(
    session: Session,
    item_id: int,
    categoria_id: int,
    nome: str,
    unidade: str,
    observacoes: Optional[str] = None,
    ativo: bool = True,
) -> Item:
    """Atualiza dados cadastrais de um item existente.

    Valida categoria, duplicidade de nome na categoria e persiste a alteração.
    Não altera estoque atual nem mínimo/ideal — esses são gerenciados via
    `registrar_movimentacao` e `aplicar_minimo_ideal_manual` respectivamente.
    """
    item = session.query(Item).filter_by(id=item_id).first()
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")

    cat = session.query(Categoria).filter_by(id=categoria_id).first()
    if not cat:
        raise ValueError(f"Categoria {categoria_id} não encontrada")

    nome_norm = _normalizar(nome)
    duplicado = (
        session.query(Item)
        .filter(
            Item.nome_normalizado == nome_norm,
            Item.categoria_id == categoria_id,
            Item.id != item_id,
        )
        .first()
    )
    if duplicado:
        raise ValueError(f"Já existe outro item com o nome '{nome}' nessa categoria")

    item.categoria_id = categoria_id
    item.nome = nome.strip()
    item.nome_normalizado = nome_norm
    item.unidade = unidade
    item.observacoes = observacoes
    item.ativo = ativo
    item.atualizado_em = tempo.agora()
    session.commit()
    session.refresh(item)
    return item


def create_categoria(
    session: Session,
    nome: str,
    descricao: Optional[str] = None,
) -> Categoria:
    """Cria uma categoria validando duplicidade por nome normalizado."""
    nome_norm = _normalizar(nome)
    existente = session.query(Categoria).all()
    for c in existente:
        if _normalizar(c.nome) == nome_norm:
            raise ValueError(f"Já existe uma categoria com o nome '{nome}'")

    cat = Categoria(nome=nome.strip(), descricao=descricao)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def update_categoria(
    session: Session,
    cat_id: int,
    nome: str,
    descricao: Optional[str] = None,
) -> Categoria:
    """Atualiza nome e descrição de uma categoria existente."""
    cat = session.query(Categoria).filter_by(id=cat_id).first()
    if not cat:
        raise ValueError(f"Categoria {cat_id} não encontrada")

    nome_norm = _normalizar(nome)
    duplicado = session.query(Categoria).filter(
        Categoria.id != cat_id
    ).all()
    for c in duplicado:
        if _normalizar(c.nome) == nome_norm:
            raise ValueError(f"Já existe outra categoria com o nome '{nome}'")

    cat.nome = nome.strip()
    cat.descricao = descricao
    session.commit()
    session.refresh(cat)
    return cat


_STATUS_SOLICITACAO_ATIVOS = {"pendente", "validada", "novo_item", "sem_parametros"}


def _verificar_solicitacoes_ativas(session: Session, item_id: int) -> None:
    """Lança ValueError se o item tiver solicitações pendentes de revisão."""
    n = (
        session.query(SolicitacaoMaterial)
        .filter(
            SolicitacaoMaterial.item_id == item_id,
            SolicitacaoMaterial.status.in_(_STATUS_SOLICITACAO_ATIVOS),
        )
        .count()
    )
    if n > 0:
        raise ValueError(
            f"Este item possui {n} solicitação(ões) pendente(s) de revisão. "
            "Resolva ou rejeite as solicitações antes de remover o item."
        )


def delete_item(session: Session, item_id: int) -> None:
    """Remove permanentemente um item e registros dependentes em cascade."""
    item = session.query(Item).filter_by(id=item_id).first()
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    _verificar_solicitacoes_ativas(session, item_id)
    session.delete(item)
    session.commit()


def count_itens_categoria(session: Session, cat_id: int) -> int:
    return session.query(Item).filter_by(categoria_id=cat_id).count()


def delete_categoria(session: Session, cat_id: int) -> None:
    """Remove uma categoria e todos os itens vinculados a ela (cascade)."""
    cat = session.query(Categoria).filter_by(id=cat_id).first()
    if not cat:
        raise ValueError(f"Categoria {cat_id} não encontrada")

    itens = session.query(Item).filter_by(categoria_id=cat_id).all()
    for item in itens:
        _verificar_solicitacoes_ativas(session, item.id)
    for item in itens:
        session.delete(item)

    session.delete(cat)
    session.commit()


# ---------------------------------------------------------------------------
# Setores
# ---------------------------------------------------------------------------

def get_setores(session: Session, apenas_ativos: bool = True) -> list[Setor]:
    """Lista setores em ordem alfabética."""
    q = session.query(Setor)
    if apenas_ativos:
        q = q.filter(Setor.ativo == True)  # noqa: E712
    return q.order_by(Setor.nome).all()


def criar_setor(
    session: Session,
    nome: str,
    descricao: Optional[str] = None,
    whatsapp: Optional[str] = None,
) -> Setor:
    """Cria um setor validando unicidade do nome (case-insensitive)."""
    nome_norm = _normalizar(nome)
    existentes = session.query(Setor).all()
    for s in existentes:
        if _normalizar(s.nome) == nome_norm:
            raise ValueError(f"Já existe um setor com o nome '{nome}'")

    setor = Setor(nome=nome.strip(), descricao=descricao, whatsapp=limpar_telefone(whatsapp))
    session.add(setor)
    session.commit()
    session.refresh(setor)
    return setor


def atualizar_setor(
    session: Session,
    setor_id: int,
    nome: str,
    descricao: Optional[str] = None,
    ativo: bool = True,
    whatsapp: Optional[str] = None,
) -> Setor:
    """Atualiza nome, descrição, WhatsApp e status de atividade de um setor existente."""
    setor = session.query(Setor).filter_by(id=setor_id).first()
    if not setor:
        raise ValueError(f"Setor {setor_id} não encontrado")

    nome_norm = _normalizar(nome)
    duplicado = session.query(Setor).filter(Setor.id != setor_id).all()
    for s in duplicado:
        if _normalizar(s.nome) == nome_norm:
            raise ValueError(f"Já existe outro setor com o nome '{nome}'")

    setor.nome = nome.strip()
    setor.descricao = descricao
    setor.ativo = ativo
    setor.whatsapp = limpar_telefone(whatsapp)
    session.commit()
    session.refresh(setor)

    if not ativo:
        participacoes = (
            session.query(CicloSolicitacaoSetor)
            .join(CicloSolicitacaoMaterial)
            .filter(
                CicloSolicitacaoSetor.setor_id == setor_id,
                CicloSolicitacaoSetor.status == "pendente",
                CicloSolicitacaoMaterial.status == "aberto",
            )
            .all()
        )
        for p in participacoes:
            p.status = "sem_solicitacao"
            p.respondido_em = tempo.agora()
        if participacoes:
            session.commit()

    return setor


def delete_setor(session: Session, setor_id: int, force: bool = False) -> int:
    """Remove um setor. Se force=True, desvincula movimentações antes de deletar.
    Retorna o número de movimentações desvinculadas."""
    setor = session.get(Setor, setor_id)
    if not setor:
        raise ValueError(f"Setor {setor_id} não encontrado")

    ciclos_ativos = (
        session.query(CicloSolicitacaoSetor)
        .join(CicloSolicitacaoMaterial)
        .filter(
            CicloSolicitacaoSetor.setor_id == setor_id,
            CicloSolicitacaoMaterial.status == "aberto",
        )
        .count()
    )
    if ciclos_ativos > 0:
        raise ValueError(
            "Este setor está participando de um ciclo de solicitações em aberto. "
            "Encerre o ciclo ou desative o setor antes de removê-lo."
        )

    mov_count = len(setor.movimentacoes)
    if mov_count > 0 and not force:
        raise ValueError(
            f"Este setor possui {mov_count} movimentação(ões) vinculada(s). "
            "Desative-o em vez de remover, ou use remoção forçada."
        )
    if force:
        for mov in setor.movimentacoes:
            mov.setor_id = None
    session.delete(setor)
    session.commit()
    return mov_count


# ---------------------------------------------------------------------------
# Devoluções de material
# ---------------------------------------------------------------------------

def registrar_devolucao(
    session: Session,
    item_id: int,
    quantidade: int,
    setor_id: Optional[int] = None,
    motivo: Optional[str] = None,
) -> DevolucaoMaterial:
    """Registra uma devolução pendente. NÃO altera estoque_atual."""
    if quantidade <= 0:
        raise ValueError("Quantidade deve ser maior que zero.")
    item = session.get(Item, item_id)
    if not item:
        raise ValueError(f"Item {item_id} não encontrado.")
    dev = DevolucaoMaterial(
        item_id=item_id,
        setor_id=setor_id,
        quantidade=quantidade,
        motivo=motivo,
        status="pendente",
        criado_em=tempo.agora(),
    )
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return dev


def get_devolucoes(
    session: Session,
    status: Optional[str] = None,
) -> list[DevolucaoMaterial]:
    """Lista devoluções, opcionalmente filtradas por status."""
    q = (
        session.query(DevolucaoMaterial)
        .options(
            joinedload(DevolucaoMaterial.item).joinedload(Item.categoria),
            joinedload(DevolucaoMaterial.setor),
        )
        .order_by(DevolucaoMaterial.criado_em.desc())
    )
    if status:
        q = q.filter(DevolucaoMaterial.status == status)
    return q.all()


def reintegrar_devolucao(session: Session, devolucao_id: int) -> Item:
    """Reintegra devolução ao estoque: cria Entrada e marca devolução como 'reintegrada'."""
    dev = session.get(DevolucaoMaterial, devolucao_id)
    if not dev:
        raise ValueError(f"Devolução {devolucao_id} não encontrada.")
    if dev.status != "pendente":
        raise ValueError(f"Só devoluções pendentes podem ser reintegradas. Status atual: '{dev.status}'.")
    item = registrar_movimentacao(
        session=session,
        item_id=dev.item_id,
        tipo="entrada",
        quantidade=dev.quantidade,
        motivo=f"Reintegração de devolução #{dev.id}" + (f" — {dev.motivo}" if dev.motivo else ""),
        setor_id=dev.setor_id,
    )
    dev.status = "reintegrada"
    dev.processado_em = tempo.agora()
    session.commit()
    return item


def descartar_devolucao(session: Session, devolucao_id: int) -> DevolucaoMaterial:
    """Marca devolução como descartada. NÃO altera estoque_atual."""
    dev = session.get(DevolucaoMaterial, devolucao_id)
    if not dev:
        raise ValueError(f"Devolução {devolucao_id} não encontrada.")
    if dev.status != "pendente":
        raise ValueError(f"Só devoluções pendentes podem ser descartadas. Status atual: '{dev.status}'.")
    dev.status = "descartada"
    dev.processado_em = tempo.agora()
    session.commit()
    session.refresh(dev)
    return dev
