""" Serviços de fornecedores e cotações de preço.

Reúne consultas e operações de manutenção de fornecedores. As funções que
criam, atualizam, excluem ou adicionam preço persistem as alterações com
`commit`; as consultas apenas leem dados.
"""

import datetime

from core import tempo
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from core.models import Fornecedor, PrecoFornecedor, Item


def get_all_fornecedores(session: Session, apenas_ativos: bool = True) -> list[Fornecedor]:
    """Lista fornecedores, opcionalmente restringindo aos ativos."""
    q = session.query(Fornecedor)
    if apenas_ativos:
        q = q.filter(Fornecedor.ativo == True)  # noqa: E712
    return q.order_by(Fornecedor.nome).all()


def get_fornecedor_by_id(session: Session, forn_id: int) -> Optional[Fornecedor]:
    """Busca um fornecedor pelo ID ou retorna `None` quando não existir."""
    return session.query(Fornecedor).filter_by(id=forn_id).first()


def add_preco(
    session: Session,
    item_id: int,
    fornecedor_id: int,
    preco_unitario: float,
    data_cotacao: datetime.date,
    validade_dias: int = 30,
) -> PrecoFornecedor:
    """Cadastra uma cotação para um item e fornecedor.

    Persiste a cotação com `commit` e retorna o registro criado.
    """
    preco = PrecoFornecedor(
        item_id=item_id,
        fornecedor_id=fornecedor_id,
        preco_unitario=preco_unitario,
        data_cotacao=data_cotacao,
        validade_dias=validade_dias,
        ativo=True,
    )
    session.add(preco)
    session.commit()
    session.refresh(preco)
    return preco


def get_best_price(session: Session, item_id: int) -> Optional[PrecoFornecedor]:
    """
    Retorna a melhor cotação válida para um item.

    Considera apenas preços ativos, fornecedores ativos e cotações dentro da
    validade. Se houver fornecedor preferencial válido, ele tem prioridade; em
    seguida vence o menor preço.
    """
    hoje = tempo.hoje()
    precos = (
        session.query(PrecoFornecedor)
        .options(joinedload(PrecoFornecedor.fornecedor))
        .filter(
            PrecoFornecedor.item_id == item_id,
            PrecoFornecedor.ativo == True,  # noqa: E712
        )
        .all()
    )

    validos = [
        p for p in precos
        if p.fornecedor.ativo
        and (p.data_cotacao + datetime.timedelta(days=p.validade_dias)) >= hoje
    ]

    if not validos:
        return None

    # Preferencial primeiro, depois menor preço
    preferenciais = [p for p in validos if p.fornecedor.preferencial]
    candidatos = preferenciais if preferenciais else validos
    return min(candidatos, key=lambda p: p.preco_unitario)


def get_best_prices_bulk(
    session: Session, item_ids: list[int]
) -> dict[int, Optional[PrecoFornecedor]]:
    """Retorna o melhor preço para cada item em uma única query (sem N+1).

    Mesma regra de get_best_price(): preferencial=True tem prioridade;
    fallback para menor preço válido entre cotações ativas e dentro do prazo.
    """
    if not item_ids:
        return {}

    hoje = tempo.hoje()
    precos = (
        session.query(PrecoFornecedor)
        .options(joinedload(PrecoFornecedor.fornecedor))
        .filter(
            PrecoFornecedor.item_id.in_(item_ids),
            PrecoFornecedor.ativo == True,  # noqa: E712
        )
        .all()
    )

    por_item: dict[int, list[PrecoFornecedor]] = {}
    for p in precos:
        if (
            p.fornecedor
            and p.fornecedor.ativo
            and (p.data_cotacao + datetime.timedelta(days=p.validade_dias)) >= hoje
        ):
            por_item.setdefault(p.item_id, []).append(p)

    resultado: dict[int, Optional[PrecoFornecedor]] = {i: None for i in item_ids}
    for item_id, lista in por_item.items():
        preferenciais = [p for p in lista if p.fornecedor.preferencial]
        candidatos = preferenciais if preferenciais else lista
        resultado[item_id] = min(candidatos, key=lambda p: p.preco_unitario)

    return resultado


def get_precos_por_item(session: Session, item_id: int) -> list[PrecoFornecedor]:
    """Lista cotações ativas de um item da mais recente para a mais antiga."""
    return (
        session.query(PrecoFornecedor)
        .options(joinedload(PrecoFornecedor.fornecedor))
        .filter_by(item_id=item_id, ativo=True)
        .order_by(PrecoFornecedor.data_cotacao.desc())
        .all()
    )


def remover_preco(session: Session, preco_id: int) -> None:
    """Remove permanentemente um registro de cotação de preço."""
    preco = session.query(PrecoFornecedor).filter_by(id=preco_id).first()
    if not preco:
        raise ValueError(f"Registro de preço {preco_id} não encontrado")
    session.delete(preco)
    session.commit()


def create_fornecedor(
    session: Session,
    nome: str,
    contato_nome: Optional[str] = None,
    telefone: Optional[str] = None,
    email: Optional[str] = None,
    preferencial: bool = False,
    ativo: bool = True,
) -> Fornecedor:
    """Cria fornecedor validando duplicidade exata de nome."""
    existente = session.query(Fornecedor).filter_by(nome=nome.strip()).first()
    if existente:
        raise ValueError(f"Já existe um fornecedor com o nome '{nome}'")

    forn = Fornecedor(
        nome=nome.strip(),
        contato_nome=contato_nome or None,
        telefone=telefone or None,
        email=email or None,
        preferencial=preferencial,
        ativo=ativo,
    )
    session.add(forn)
    session.commit()
    session.refresh(forn)
    return forn


def delete_fornecedor(session: Session, forn_id: int) -> None:
    """Remove fornecedor, suas cotações e referências em snapshots."""
    forn = session.query(Fornecedor).filter_by(id=forn_id).first()
    if not forn:
        raise ValueError(f"Fornecedor {forn_id} não encontrado")

    # Remove preços vinculados (FK sem cascade no modelo)
    session.query(PrecoFornecedor).filter_by(fornecedor_id=forn_id).delete()

    # Nulifica referências em snapshots de análise
    from core.models import SnapshotAnalise
    session.query(SnapshotAnalise).filter_by(fornecedor_sugerido_id=forn_id).update(
        {"fornecedor_sugerido_id": None}
    )

    # Nulifica FK em cotações de orçamento (preserva o campo origem/texto)
    from core.models import CotacaoOrcamento
    session.query(CotacaoOrcamento).filter_by(fornecedor_id=forn_id).update(
        {"fornecedor_id": None}
    )

    session.delete(forn)
    session.commit()


def update_fornecedor(
    session: Session,
    forn_id: int,
    nome: str,
    contato_nome: Optional[str] = None,
    telefone: Optional[str] = None,
    email: Optional[str] = None,
    preferencial: bool = False,
    ativo: bool = True,
) -> Fornecedor:
    """Atualiza dados cadastrais de fornecedor existente."""
    forn = session.query(Fornecedor).filter_by(id=forn_id).first()
    if not forn:
        raise ValueError(f"Fornecedor {forn_id} não encontrado")

    duplicado = (
        session.query(Fornecedor)
        .filter(Fornecedor.nome == nome.strip(), Fornecedor.id != forn_id)
        .first()
    )
    if duplicado:
        raise ValueError(f"Já existe outro fornecedor com o nome '{nome}'")

    forn.nome = nome.strip()
    forn.contato_nome = contato_nome or None
    forn.telefone = telefone or None
    forn.email = email or None
    forn.preferencial = preferencial
    forn.ativo = ativo
    session.commit()
    session.refresh(forn)
    return forn
