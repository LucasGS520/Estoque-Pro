""" Lê o Excel de estoque com layout multi-painel (3 categorias lado a lado).

Estrutura da planilha:
  Linha 1 (idx 0): Título "CONTROLE DE MATERIAIS"
  Linha 2 (idx 1): Nomes das categorias nas colunas 0, 4, 8
  Linha 3 (idx 2): Sub-cabeçalhos: ITEM | ESTOQUE | SAIDA | ESTOQUE ATUAL (repetido 3×)
  Linha 4+ (idx 3+): Dados
"""

from pathlib import Path
from typing import Any

import openpyxl


def _cell_val(cell) -> Any:
    """Extrai e limpa o valor de uma célula do openpyxl."""
    if cell is None:
        return None
    v = cell.value
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


def _to_int(val) -> int | None:
    """Converte um valor para inteiro ou retorna `None` quando não for possível."""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_estoque(path: Path) -> tuple[list[dict], list[str]]:
    """
    Lê a planilha de estoque e retorna `(registros, erros)`.

    Cada registro:
    {
        "categoria": str,
        "nome": str,
        "estoque_entrada": int | None,
        "saida": int | None,
        "estoque_atual": int | None,
    }
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=False))
    if len(rows) < 4:
        return [], ["Planilha com menos de 4 linhas — formato inesperado"]

    # Linha 2 (idx 1): detectar categorias nas colunas 0, 4, 8
    header_row = rows[1]
    panel_starts = [0, 4, 8]
    categories: list[str] = []
    for col_idx in panel_starts:
        cell = header_row[col_idx] if col_idx < len(header_row) else None
        val = _cell_val(cell)
        categories.append(str(val).strip() if val else f"CATEGORIA_{col_idx}")

    registros: list[dict] = []
    erros: list[str] = []

    # Painéis: cada painel ocupa 4 colunas (ITEM, ESTOQUE, SAIDA, ESTOQUE ATUAL)
    for row_idx, row in enumerate(rows[3:], start=4):  # linha 4 em diante (1-based)
        for panel_num, (col_start, categoria) in enumerate(zip(panel_starts, categories)):
            cols = row[col_start: col_start + 4]

            nome_cell = cols[0] if len(cols) > 0 else None
            entrada_cell = cols[1] if len(cols) > 1 else None
            saida_cell = cols[2] if len(cols) > 2 else None
            atual_cell = cols[3] if len(cols) > 3 else None

            nome = _cell_val(nome_cell)
            if not nome:
                continue  # célula vazia — painel terminou antes

            estoque_atual = _to_int(_cell_val(atual_cell))
            estoque_entrada = _to_int(_cell_val(entrada_cell))
            saida = _to_int(_cell_val(saida_cell))

            # Se formula não resolveu (data_only=True falhou), tentar calcular
            if estoque_atual is None and estoque_entrada is not None and saida is not None:
                estoque_atual = estoque_entrada - saida

            registros.append({
                "categoria": categoria,
                "nome": str(nome),
                "estoque_entrada": estoque_entrada,
                "saida": saida,
                "estoque_atual": estoque_atual if estoque_atual is not None else 0,
            })

    return registros, erros


def parse_fornecedores(path: Path) -> tuple[list[dict], list[str]]:
    """
    Lê a planilha de fornecedores e retorna `(fornecedores, erros)`.

    FORNECEDORES.xlsx:
      Linha 1: Cabeçalho (FORNECEDORES | Contato | Telefone)
      Linha 2+: Dados
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], ["Planilha de fornecedores vazia"]

    fornecedores: list[dict] = []
    erros: list[str] = []

    # Pula linha de cabeçalho (linha 1, idx 0)
    for row_idx, row in enumerate(rows[1:], start=2):
        nome = str(row[0]).strip() if row[0] else None
        contato = str(row[1]).strip() if len(row) > 1 and row[1] else None
        telefone = str(row[2]).strip() if len(row) > 2 and row[2] else None

        if not nome:
            continue

        fornecedores.append({
            "nome": nome,
            "contato_nome": contato,
            "telefone": telefone,
        })

    return fornecedores, erros
