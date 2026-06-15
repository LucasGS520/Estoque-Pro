"""Gerador DOCX para a aba Por Item de Relatórios."""

from pathlib import Path

import pandas as pd

from documents.base_doc import adicionar_tabela, criar_documento, salvar_com_timestamp


def gerar_relatorio_item(
    periodo_label: str,
    df_item: pd.DataFrame,
    setor_label: str = "Todos os setores",
) -> Path:
    doc = criar_documento("Relatório — Consumo por Item")

    p = doc.add_paragraph(f"Período: {periodo_label}  ·  Setor: {setor_label}")
    p.runs[0].bold = True
    doc.add_paragraph()

    if df_item.empty:
        doc.add_paragraph("Nenhuma movimentação registrada no período.")
    else:
        doc.add_heading("Top Itens por Consumo", level=3)
        include_setor = setor_label != "Todos os setores" and "setor" in df_item.columns
        headers = ["Item", "Categoria", "Total Retirado", "Nº Movimentações"]
        col_w   = [6.0, 4.5, 3.5, 3.5]
        if include_setor:
            headers.insert(2, "Setor")
            col_w.insert(2, 3.5)

        rows = []
        for _, row in df_item.iterrows():
            r = [row["item"], row["categoria"], int(row["total_saida"]), int(row["num_movimentacoes"])]
            if include_setor:
                r.insert(2, row.get("setor", "—"))
            rows.append(tuple(r))

        adicionar_tabela(doc, headers=headers, rows=rows, col_widths=col_w)

    return salvar_com_timestamp(doc, "relatorio_item")
