"""Gerador DOCX para a aba Consumo × Reposição de Relatórios."""

import datetime
from pathlib import Path

import pandas as pd

from documents.base_doc import adicionar_tabela, criar_documento, salvar_com_timestamp


def gerar_relatorio_consumo(
    periodo_label: str,
    kpis: dict,
    df_timeline: pd.DataFrame,
) -> Path:
    doc = criar_documento("Relatório — Consumo × Reposição")

    # Período
    p = doc.add_paragraph(f"Período: {periodo_label}")
    p.runs[0].bold = True

    doc.add_paragraph()

    # KPIs
    doc.add_heading("Resumo do Período", level=3)
    adicionar_tabela(
        doc,
        headers=["Indicador", "Valor"],
        rows=[
            ("Total consumido (saídas)", kpis.get("total_saida", 0)),
            ("Total de entradas",        kpis.get("total_entrada", 0)),
            ("Saldo (entradas − saídas)", kpis.get("saldo", 0)),
            ("Item mais consumido",      kpis.get("item_mais_consumido", "—")),
            ("Setor com maior consumo",  kpis.get("setor_mais_consumiu", "—")),
        ],
        col_widths=[8.0, 8.0],
    )

    doc.add_paragraph()

    # Timeline mensal
    if not df_timeline.empty:
        doc.add_heading("Timeline Mensal", level=3)
        rows_tl = [
            (row["mes"], int(row["total_saida"]), int(row["total_entrada"]))
            for _, row in df_timeline.iterrows()
        ]
        adicionar_tabela(
            doc,
            headers=["Mês", "Saídas", "Entradas"],
            rows=rows_tl,
            col_widths=[5.5, 5.0, 5.0],
        )

    return salvar_com_timestamp(doc, "relatorio_consumo")
