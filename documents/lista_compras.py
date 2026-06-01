from pathlib import Path

import pandas as pd
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from documents.base_doc import criar_documento, adicionar_tabela, salvar_com_timestamp


def gerar_lista_compras(df: pd.DataFrame) -> Path:
    """
    Recebe um DataFrame com colunas:
    Item, Categoria, Atual, Mínimo, Ideal, Comprar, Fornecedor, Valor Est.
    """
    doc = criar_documento("Lista de Compras")

    categorias = df["Categoria"].unique() if "Categoria" in df.columns else ["Geral"]

    for cat in sorted(categorias):
        df_cat = df[df["Categoria"] == cat] if "Categoria" in df.columns else df
        if df_cat.empty:
            continue

        heading = doc.add_heading(cat, level=3)
        heading.runs[0].font.size = Pt(11)

        headers = ["Item", "Atual", "Mín.", "Ideal", "Comprar", "Fornecedor", "Valor Est."]
        rows = []
        for _, row in df_cat.iterrows():
            rows.append([
                row.get("Item", ""),
                row.get("Atual", ""),
                row.get("Mínimo", ""),
                row.get("Ideal", ""),
                row.get("Comprar", ""),
                row.get("Fornecedor", "—"),
                row.get("Valor Est.", "—"),
            ])

        adicionar_tabela(doc, headers, rows)
        doc.add_paragraph()

    # Total
    if "Valor Est." in df.columns:
        doc.add_paragraph()
        total_p = doc.add_paragraph()
        total_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = total_p.add_run("(valores aproximados com base nas últimas cotações válidas)")
        run.font.size = Pt(8)
        run.italic = True

    return salvar_com_timestamp(doc, "lista_compras")
