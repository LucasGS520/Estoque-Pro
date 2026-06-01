import datetime
from pathlib import Path
from typing import Sequence

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from core.config import EXPORTS_DIR


def criar_documento(titulo: str) -> Document:
    doc = Document()

    # Margens
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Cabeçalho
    cabecalho = doc.add_heading("RH DFeB — Controle de Estoque", level=1)
    cabecalho.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in cabecalho.runs:
        run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)

    # Título do documento
    titulo_p = doc.add_heading(titulo, level=2)
    titulo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Data
    data_p = doc.add_paragraph(
        f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    data_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    data_p.runs[0].font.size = Pt(9)
    data_p.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph()  # espaço
    return doc


def adicionar_tabela(
    doc: Document,
    headers: Sequence[str],
    rows: Sequence[Sequence],
    col_widths: Sequence[float] | None = None,
) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"

    # Cabeçalho
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = str(h)
        run = hdr[i].paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(9)
        _set_cell_bg(hdr[i], "1E40AF")
        hdr[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Dados
    for idx, row_data in enumerate(rows):
        row_cells = table.add_row().cells
        bg = "EFF6FF" if idx % 2 == 0 else "FFFFFF"
        for j, val in enumerate(row_data):
            row_cells[j].text = str(val) if val is not None else "—"
            row_cells[j].paragraphs[0].runs[0].font.size = Pt(9)
            _set_cell_bg(row_cells[j], bg)

    # Larguras opcionais
    if col_widths:
        for row in table.rows:
            for j, cell in enumerate(row.cells):
                if j < len(col_widths):
                    cell.width = Cm(col_widths[j])


def _set_cell_bg(cell, hex_color: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def salvar_com_timestamp(doc: Document, prefixo: str) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{prefixo}_{datetime.datetime.now().strftime('%Y_%m_%d_%H%M')}.docx"
    path = EXPORTS_DIR / nome
    doc.save(str(path))
    return path
