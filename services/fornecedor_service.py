import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from core.models import Fornecedor, PrecoFornecedor, Item


def get_all_fornecedores(session: Session, apenas_ativos: bool = True) -> list[Fornecedor]:
    q = session.query(Fornecedor)
    if apenas_ativos:
        q = q.filter(Fornecedor.ativo == True)  # noqa: E712
    return q.order_by(Fornecedor.nome).all()


def get_fornecedor_by_id(session: Session, forn_id: int) -> Optional[Fornecedor]:
    return session.query(Fornecedor).filter_by(id=forn_id).first()


def add_preco(
    session: Session,
    item_id: int,
    fornecedor_id: int,
    preco_unitario: float,
    data_cotacao: datetime.date,
    validade_dias: int = 30,
) -> PrecoFornecedor:
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
    Retorna o melhor preço válido para um item.
    Prioridade: fornecedor preferencial; em seguida, menor preço; em seguida, mais recente.
    """
    hoje = datetime.date.today()
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


def get_precos_por_item(session: Session, item_id: int) -> list[PrecoFornecedor]:
    return (
        session.query(PrecoFornecedor)
        .filter_by(item_id=item_id, ativo=True)
        .order_by(PrecoFornecedor.data_cotacao.desc())
        .all()
    )


def create_fornecedor(
    session: Session,
    nome: str,
    contato_nome: Optional[str] = None,
    telefone: Optional[str] = None,
    email: Optional[str] = None,
    preferencial: bool = False,
    ativo: bool = True,
) -> Fornecedor:
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
