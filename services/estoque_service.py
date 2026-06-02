""" Serviços de consulta e manutenção do estoque.

Concentra regras de negócio para itens, categorias, movimentações e KPIs. As
funções de criação, atualização, exclusão e movimentação fazem `commit`; as
funções de consulta apenas leem dados.
"""

import datetime
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session, joinedload, selectinload

from core.models import Categoria, Fornecedor, Item, Movimentacao, Setor


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
    item.atualizado_em = datetime.datetime.utcnow()
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
    item.atualizado_em = datetime.datetime.utcnow()
    session.commit()
    session.refresh(item)
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
            selectinload(Item.movimentacoes),
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

        sem_limites = item.estoque_minimo == 0 and item.estoque_ideal == 0
        if item.estoque_atual == 0 and not sem_limites:
            status = "zerado"
        elif sem_limites:
            status = "sem_minimo"
        elif item.estoque_atual <= item.estoque_minimo:
            status = "comprar"
        else:
            status = "ok"

        rows.append({
            "id": item.id,
            "categoria": item.categoria.nome,
            "item": item.nome,
            "unidade": item.unidade,
            "atual": item.estoque_atual,
            "minimo": item.estoque_minimo,
            "ideal": item.estoque_ideal,
            "status": status,
            "ultima_mov_data": ultima_mov.criado_em if ultima_mov else None,
            "ultima_mov_tipo": ultima_mov.tipo if ultima_mov else None,
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
        .filter(Item.ativo == True, Item.estoque_minimo == 0, Item.estoque_ideal == 0)  # noqa: E712
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
    estoque_minimo: int = 0,
    estoque_ideal: int = 0,
    observacoes: Optional[str] = None,
    ativo: bool = True,
) -> Item:
    """Cria um item em uma categoria existente.

    Valida categoria e duplicidade por nome normalizado dentro da mesma
    categoria. Persiste com `commit` e retorna o item criado.
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

    item = Item(
        categoria_id=categoria_id,
        nome=nome.strip(),
        nome_normalizado=nome_norm,
        unidade=unidade,
        estoque_atual=estoque_atual,
        estoque_minimo=estoque_minimo,
        estoque_ideal=estoque_ideal,
        observacoes=observacoes,
        ativo=ativo,
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
    estoque_minimo: int,
    estoque_ideal: int,
    observacoes: Optional[str] = None,
    ativo: bool = True,
) -> Item:
    """Atualiza dados cadastrais de um item existente.

    Valida categoria, duplicidade de nome na categoria e persiste a alteração.
    Não altera o estoque atual; movimentações devem passar por
    `registrar_movimentacao`.
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
    item.estoque_minimo = estoque_minimo
    item.estoque_ideal = estoque_ideal
    item.observacoes = observacoes
    item.ativo = ativo
    item.atualizado_em = datetime.datetime.utcnow()
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


def delete_item(session: Session, item_id: int) -> None:
    """Remove permanentemente um item e registros dependentes em cascade."""
    item = session.query(Item).filter_by(id=item_id).first()
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    session.delete(item)
    session.commit()


def delete_categoria(session: Session, cat_id: int) -> None:
    """Remove uma categoria somente quando ela não possui itens vinculados."""
    cat = session.query(Categoria).filter_by(id=cat_id).first()
    if not cat:
        raise ValueError(f"Categoria {cat_id} não encontrada")

    tem_itens = session.query(Item).filter_by(categoria_id=cat_id).first()
    if tem_itens:
        raise ValueError(
            "Não é possível remover uma categoria que possui itens. "
            "Remova ou mova os itens antes de excluir a categoria."
        )

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
) -> Setor:
    """Cria um setor validando unicidade do nome (case-insensitive)."""
    nome_norm = _normalizar(nome)
    existentes = session.query(Setor).all()
    for s in existentes:
        if _normalizar(s.nome) == nome_norm:
            raise ValueError(f"Já existe um setor com o nome '{nome}'")

    setor = Setor(nome=nome.strip(), descricao=descricao)
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
) -> Setor:
    """Atualiza nome, descrição e status de atividade de um setor existente."""
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
    session.commit()
    session.refresh(setor)
    return setor
