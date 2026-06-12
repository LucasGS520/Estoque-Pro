"""Gerador DOCX para a aba Por Setor de Relatórios."""

from pathlib import Path

import pandas as pd

from documents.base_doc import adicionar_tabela, criar_documento, salvar_com_timestamp


def gerar_relatorio_setor(periodo_label: str, df_setor: pd.DataFrame) -> Path:
    doc = criar_documento("Relatório — Consumo por Setor")

    p = doc.add_paragraph(f"Período: {periodo_label}")
    p.runs[0].bold = True
    doc.add_paragraph()

    if df_setor.empty:
        doc.add_paragraph("Nenhuma movimentação registrada no período.")
    else:
        total = int(df_setor["total_saida"].sum())
        doc.add_heading("Resumo", level=3)
        adicionar_tabela(
            doc,
            headers=["Indicador", "Valor"],
            rows=[
                ("Total retirado", total),
                ("Setores com consumo", df_setor[df_setor["setor"] != "Sem setor"]["setor"].nunique()),
            ],
            col_widths=[9.0, 7.0],
        )
        doc.add_paragraph()

        doc.add_heading("Detalhamento por Setor", level=3)
        rows = [
            (row["setor"], int(row["total_saida"]), int(row["num_movimentacoes"]))
            for _, row in df_setor.iterrows()
        ]
        adicionar_tabela(
            doc,
            headers=["Setor", "Total Retirado", "Nº Movimentações"],
            rows=rows,
            col_widths=[7.0, 5.0, 4.0],
        )

    return salvar_com_timestamp(doc, "relatorio_setor")
