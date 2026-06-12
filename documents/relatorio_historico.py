"""Gerador DOCX para a aba Histórico de Movimentações de Relatórios."""

from pathlib import Path

import pandas as pd

from documents.base_doc import adicionar_tabela, criar_documento, salvar_com_timestamp


def gerar_relatorio_historico(periodo_label: str, df_hist: pd.DataFrame) -> Path:
    doc = criar_documento("Relatório — Histórico de Movimentações")

    p = doc.add_paragraph(f"Período: {periodo_label}  ·  {len(df_hist)} registros")
    p.runs[0].bold = True
    doc.add_paragraph()

    if df_hist.empty:
        doc.add_paragraph("Nenhuma movimentação encontrada no período.")
    else:
        # Colunas presentes dependem dos filtros aplicados
        col_map = {
            "data": "Data", "item": "Item", "tipo": "Tipo",
            "setor": "Setor", "quantidade": "Qtd.",
            "qtd_anterior": "Anterior", "qtd_nova": "Nova",
            "motivo": "Motivo", "retirado_por": "Retirado por",
        }
        cols_disp = [c for c in col_map if c in df_hist.columns]
        headers = [col_map[c] for c in cols_disp]
        rows = [
            tuple(str(row[c]) if row[c] is not None else "—" for c in cols_disp)
            for _, row in df_hist.iterrows()
        ]
        adicionar_tabela(doc, headers=headers, rows=rows)

    return salvar_com_timestamp(doc, "relatorio_historico")
