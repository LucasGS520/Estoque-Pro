""" Geração do documento Word de orçamento preliminar.

Converte um `OrcamentoConsolidado` em `.docx`, agrupando itens por fornecedor,
calculando subtotais e destacando itens sem cotação válida.
"""

from pathlib import Path

from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from documents.base_doc import criar_documento, adicionar_tabela, salvar_com_timestamp
from services.orcamento_service import OrcamentoConsolidado


def gerar_orcamento(orcamento: OrcamentoConsolidado) -> Path:
    """Gera e salva o documento de orçamento preliminar de compras."""
    doc = criar_documento("Orçamento Preliminar de Compras")

    # Itens com preço — agrupados por fornecedor
    fornecedores_no_doc = {}
    for item in orcamento.itens_com_preco:
        forn = item.fornecedor or "Sem Fornecedor"
        if forn not in fornecedores_no_doc:
            fornecedores_no_doc[forn] = []
        fornecedores_no_doc[forn].append(item)

    for forn, itens in fornecedores_no_doc.items():
        doc.add_heading(f"Fornecedor: {forn}", level=3)
        headers = ["Item", "Categoria", "Qtd", "Preço Unit.", "Total", "Validade"]
        rows = [
            [
                i.nome,
                i.categoria,
                i.quantidade,
                f"R$ {i.preco_unitario:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                f"R$ {i.total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                i.validade_cotacao or "—",
            ]
            for i in itens
        ]
        adicionar_tabela(doc, headers, rows)

        subtotal = sum(i.total or 0 for i in itens)
        sub_p = doc.add_paragraph()
        sub_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        sub_run = sub_p.add_run(
            f"Subtotal {forn}: R$ {subtotal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        sub_run.bold = True
        sub_run.font.size = Pt(10)
        doc.add_paragraph()

    # Total geral
    total_p = doc.add_paragraph()
    total_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    total_run = total_p.add_run(
        f"TOTAL ESTIMADO: R$ {orcamento.total_estimado:,.2f}"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )
    total_run.bold = True
    total_run.font.size = Pt(12)

    # Itens sem preço
    if orcamento.itens_sem_preco:
        doc.add_paragraph()
        doc.add_heading("Itens sem Cotação (não incluídos no total)", level=3)
        headers_sp = ["Item", "Categoria", "Qtd"]
        rows_sp = [[i.nome, i.categoria, i.quantidade] for i in orcamento.itens_sem_preco]
        adicionar_tabela(doc, headers_sp, rows_sp)

    return salvar_com_timestamp(doc, "orcamento_preliminar")
