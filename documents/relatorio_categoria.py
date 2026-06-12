"""Gerador DOCX para a aba Por Categoria de Relatórios."""

from pathlib import Path

import pandas as pd

from documents.base_doc import adicionar_tabela, criar_documento, salvar_com_timestamp


def gerar_relatorio_categoria(periodo_label: str, df_cat: pd.DataFrame) -> Path:
    doc = criar_documento("Relatório — Consumo por Categoria")

    p = doc.add_paragraph(f"Período: {periodo_label}")
    p.runs[0].bold = True
    doc.add_paragraph()

    if df_cat.empty:
        doc.add_paragraph("Nenhuma movimentação registrada no período.")
    else:
        doc.add_heading("Consumo por Categoria", level=3)
        rows = [
            (row["categoria"], int(row["total_saida"]))
            for _, row in df_cat.iterrows()
        ]
        adicionar_tabela(
            doc,
            headers=["Categoria", "Total Consumido"],
            rows=rows,
            col_widths=[10.0, 6.0],
        )

    return salvar_com_timestamp(doc, "relatorio_categoria")
