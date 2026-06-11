""" Helpers base para geração de documentos Word.

Fornece criação de documento com identidade do sistema, tabelas padronizadas e
salvamento em `EXPORTS_DIR`. As funções aqui são reutilizadas pelos documentos
de lista de compras e orçamento.
"""

import io

from core import tempo
from pathlib import Path
from typing import Sequence

from PIL import Image as _PILImage
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from core.config import EXPORTS_DIR

_LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo_dfeb.png"

# Cores do sistema: preto, branco, vermelho
_COR_VERMELHO  = RGBColor(0xCC, 0x00, 0x00)
_COR_PRETO     = RGBColor(0x1A, 0x1A, 0x1A)
_COR_CINZA     = RGBColor(0x64, 0x74, 0x8B)
_HEX_HEADER    = "1A1A1A"   # preto — fundo do cabeçalho da tabela
_HEX_ROW_PAR   = "F5F5F5"  # cinza claro — linha par
_HEX_ROW_IMPAR = "FFFFFF"  # branco — linha ímpar

# Dimensões A4 e margens padrão (em cm)
_PAPER_WIDTH_CM  = 21.0
_MARGIN_LEFT_CM  = 2.5
_MARGIN_RIGHT_CM = 2.5
_TWIPS_PER_CM    = 566.929


def criar_documento(titulo: str) -> Document:
    """Cria um documento Word com identidade visual do sistema."""
    doc = Document()

    # Margens: topo zero para o header encostar na borda superior do papel;
    # lados normais — o header usa indentação negativa para ultrapassá-los.
    for section in doc.sections:
        section.top_margin    = Cm(0)
        section.bottom_margin = Cm(2)
        section.left_margin   = Cm(_MARGIN_LEFT_CM)
        section.right_margin  = Cm(_MARGIN_RIGHT_CM)

    # ── Header preto ponta a ponta ──────────────────────────────────────────
    hdr_tbl = doc.add_table(rows=1, cols=1)
    _remove_table_borders(hdr_tbl)
    _set_table_full_width(hdr_tbl)
    hdr_cell = hdr_tbl.rows[0].cells[0]
    _set_cell_bg(hdr_cell, "1A1A1A")
    _set_cell_margins(hdr_cell, top=220, bottom=160, left=360, right=360)

    logo_para = hdr_cell.paragraphs[0]
    logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if _LOGO_PATH.exists():
        buf = io.BytesIO()
        img = _PILImage.open(_LOGO_PATH).convert("RGBA")
        bg  = _PILImage.new("RGBA", img.size, (26, 26, 26, 255))
        _PILImage.alpha_composite(bg, img).convert("RGB").save(buf, format="PNG")
        buf.seek(0)
        logo_para.add_run().add_picture(buf, height=Cm(1.6))

    # ── Título e data (dentro das margens normais) ──────────────────────────
    doc.add_paragraph()  # espaço após o header

    titulo_p = doc.add_heading(titulo, level=2)
    titulo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in titulo_p.runs:
        run.font.color.rgb = _COR_PRETO

    data_p = doc.add_paragraph(
        f"Gerado em: {tempo.agora().strftime('%d/%m/%Y %H:%M')}"
    )
    data_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    data_p.runs[0].font.size = Pt(9)
    data_p.runs[0].font.color.rgb = _COR_CINZA

    doc.add_paragraph()
    return doc


def adicionar_tabela(
    doc: Document,
    headers: Sequence[str],
    rows: Sequence[Sequence],
    col_widths: Sequence[float] | None = None,
) -> None:
    """Adiciona uma tabela ao documento com a identidade visual do sistema."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"

    # Cabeçalho — fundo vermelho, texto branco
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = str(h)
        run = hdr[i].paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _set_cell_bg(hdr[i], _HEX_HEADER)

    # Dados — alternância cinza claro / branco
    for idx, row_data in enumerate(rows):
        row_cells = table.add_row().cells
        bg = _HEX_ROW_PAR if idx % 2 == 0 else _HEX_ROW_IMPAR
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


# ── Helpers privados ─────────────────────────────────────────────────────────

def _set_cell_bg(cell, hex_color: str) -> None:
    """Aplica cor de fundo hexadecimal a uma célula de tabela Word."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _set_cell_margins(cell, top=0, bottom=0, left=0, right=0) -> None:
    """Define padding interno de uma célula (valores em twips, 1 cm ≈ 567)."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for side, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        tcMar.append(el)
    tcPr.append(tcMar)


def _remove_table_borders(table) -> None:
    """Remove todas as bordas visíveis de uma tabela."""
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _set_table_full_width(table) -> None:
    """Estende a tabela para cobrir toda a largura do papel A4.

    Usa indentação negativa para ultrapassar a margem esquerda e define
    largura explícita igual à largura total do papel (21 cm).
    """
    paper_w = int(_PAPER_WIDTH_CM * _TWIPS_PER_CM)
    left_tw = int(_MARGIN_LEFT_CM  * _TWIPS_PER_CM)

    tbl   = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)

    for tag in ("w:tblW", "w:tblInd"):
        existing = tblPr.find(qn(tag))
        if existing is not None:
            tblPr.remove(existing)

    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), str(paper_w))
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    tblInd = OxmlElement("w:tblInd")
    tblInd.set(qn("w:w"), str(-left_tw))
    tblInd.set(qn("w:type"), "dxa")
    tblPr.append(tblInd)


def salvar_com_timestamp(doc: Document, prefixo: str) -> Path:
    """Salva o documento em `EXPORTS_DIR` com timestamp no nome do arquivo."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{prefixo}_{tempo.agora().strftime('%Y_%m_%d_%H%M')}.docx"
    path = EXPORTS_DIR / nome
    doc.save(str(path))
    return path
