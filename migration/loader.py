""" Carrega dados transformados no SQLite com upsert seguro.

Este módulo recebe dados já normalizados pelos transformers, cria ou atualiza
registros no banco e registra cada execução na tabela `importacoes`.
"""

import json
import datetime

from core import tempo

from sqlalchemy.orm import Session

from core.models import Categoria, Item, Fornecedor, Importacao


def carregar_itens(
    session: Session,
    itens: list[dict],
    arquivo_origem: str,
    avisos: list[str],
) -> dict:
    """
    Insere ou atualiza itens no banco e grava log de importação.

    Regra de upsert:
    - Se item com mesmo (nome_normalizado, categoria) já existe: atualiza estoque_atual.
      Não sobrescreve estoque_minimo/ideal caso já tenham sido definidos pelo usuário.
    - Se não existe: insere novo com estoque_minimo=0 e estoque_ideal=0.

    Retorna um dict com contagens e detalhes de erros/avisos. Faz `commit` ao
    final da carga.
    """
    ok = 0
    erros: list[str] = list(avisos)

    # Cache de categorias para evitar N queries
    cat_cache: dict[str, Categoria] = {}

    for item_data in itens:
        try:
            cat_nome = item_data["categoria"]
            if cat_nome not in cat_cache:
                cat = session.query(Categoria).filter_by(nome=cat_nome).first()
                if not cat:
                    cat = Categoria(nome=cat_nome)
                    session.add(cat)
                    session.flush()
                cat_cache[cat_nome] = cat
            cat = cat_cache[cat_nome]

            existing = (
                session.query(Item)
                .filter_by(nome_normalizado=item_data["nome_normalizado"], categoria_id=cat.id)
                .first()
            )
            if existing:
                existing.estoque_atual = item_data["estoque_atual"]
                existing.atualizado_em = tempo.agora()
            else:
                novo = Item(
                    categoria_id=cat.id,
                    nome=item_data["nome"],
                    nome_normalizado=item_data["nome_normalizado"],
                    unidade=item_data.get("unidade", "un"),
                    estoque_atual=item_data["estoque_atual"],
                    estoque_minimo=0,
                    estoque_ideal=0,
                )
                session.add(novo)
            ok += 1
        except Exception as exc:
            erros.append(f"Erro ao inserir '{item_data.get('nome')}': {exc}")

    log = Importacao(
        arquivo_origem=arquivo_origem,
        tipo="estoque",
        total_linhas=len(itens) + len(avisos),
        linhas_ok=ok,
        linhas_erro=len(erros),
        erros_json=json.dumps(erros, ensure_ascii=False) if erros else None,
    )
    session.add(log)
    session.commit()

    return {"ok": ok, "erros": len(erros), "detalhes": erros}


def carregar_fornecedores(
    session: Session,
    fornecedores: list[dict],
    arquivo_origem: str,
) -> dict:
    """
    Insere ou atualiza fornecedores e grava log de importação.

    O upsert é feito por nome exato do fornecedor. Retorna contagens e detalhes
    de erro, fazendo `commit` ao final.
    """
    ok = 0
    erros: list[str] = []

    for forn_data in fornecedores:
        try:
            existing = session.query(Fornecedor).filter_by(nome=forn_data["nome"]).first()
            if existing:
                existing.contato_nome = forn_data.get("contato_nome") or existing.contato_nome
                existing.telefone = forn_data.get("telefone") or existing.telefone
            else:
                novo = Fornecedor(
                    nome=forn_data["nome"],
                    contato_nome=forn_data.get("contato_nome"),
                    telefone=forn_data.get("telefone"),
                )
                session.add(novo)
            ok += 1
        except Exception as exc:
            erros.append(f"Erro ao inserir fornecedor '{forn_data.get('nome')}': {exc}")

    log = Importacao(
        arquivo_origem=arquivo_origem,
        tipo="fornecedores",
        total_linhas=len(fornecedores),
        linhas_ok=ok,
        linhas_erro=len(erros),
        erros_json=json.dumps(erros, ensure_ascii=False) if erros else None,
    )
    session.add(log)
    session.commit()

    return {"ok": ok, "erros": len(erros), "detalhes": erros}
