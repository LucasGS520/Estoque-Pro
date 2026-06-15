"""Tela da camada de Orçamentos.

Gerencia o ciclo de cotação, comparação e aprovação a partir da Lista Final
de Compras aprovada na camada anterior (Compras). Não recalcula análise de
estoque — a fonte é sempre ItemListaCompra.incluir_na_lista_final + CompraAvulsa.

Abas e responsabilidades:
  Painel    — visão de gestão: métricas, tabela de itens (read-only), ações globais
              (criar orçamento, enviar para aprovação, gerar documento). Oferece
              atalho de navegação para a aba Cotações por item selecionado.
  Cotações  — entrada de dados: autossuficiente. Selectbox para escolher o item;
              adicionar/escolher/remover cotações sem depender do Painel.
  Histórico — auditoria: orçamentos anteriores do período e download de documentos.
"""

import datetime
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from core import tempo
from core.config import APP_BASE_URL
from core.database import get_session_factory
from core.models import CotacaoOrcamento, ItemListaCompra, ItemOrcamento, Orcamento
from core.ui import empty_state, fmt_brl, page_header, section_title, setup_page
from services.compras_service import get_periodos_com_consolidacao
from services.estoque_service import atualizar_fornecedores_item
from services.fornecedor_service import create_fornecedor, get_all_fornecedores
from services.notificacao_service import cotacao_configurada, enviar_solicitacao_cotacao
from services.orcamento_service import (
    add_cotacao,
    editar_cotacao,
    cancelar_orcamento,
    criar_orcamento,
    criar_nova_versao,
    deletar_orcamento,
    enviar_para_aprovacao,
    formatar_telefone_wame,
    gerar_mensagem_aprovacao,
    gerar_mensagem_whatsapp,
    get_fornecedores_para_item_orcamento,
    get_fornecedores_para_solicitacao,
    get_itens_aprovados,
    get_lista_final_para_orcamento,
    get_orcamento_ativo,
    get_orcamentos_periodo,
    get_resumo,
    get_solicitacoes_enviadas,
    marcar_solicitacao_respondida,
    menor_cotacao,
    registrar_solicitacao_enviada,
    remover_cotacao,
    remover_item_reprovado,
    sincronizar_com_lista_final,
)
from documents.orcamento import gerar_documento_cotacao

setup_page("Orçamentos", "💰")
page_header("Orçamentos", subtitle="Cotação, comparação e aprovação da compra a partir da Lista Final.")

SessionLocal = get_session_factory()


@st.cache_data(ttl=300)
def _bytes_docx_orcamento(orc_id: int) -> tuple[bytes, str]:
    """Gera o DOCX do orçamento e retorna (bytes, nome_do_arquivo). Cache 5 min."""
    _sf = get_session_factory()
    with _sf() as _sess:
        _orc = (
            _sess.query(Orcamento)
            .options(joinedload(Orcamento.itens).joinedload(ItemOrcamento.cotacoes))
            .filter(Orcamento.id == orc_id)
            .first()
        )
        _path = gerar_documento_cotacao(_orc)
    with open(_path, "rb") as _f:
        return _f.read(), _path.name


# ── CSS: st.radio como abas ───────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stRadio"] [role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    gap: 0 !important;
    flex-wrap: nowrap !important;
    border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;
    padding-bottom: 0 !important;
    margin-bottom: 0.75rem !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label {
    display: flex !important;
    align-items: center !important;
    padding: 0.4rem 1.1rem 0.55rem 1.1rem !important;
    margin: 0 0 -1px 0 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    cursor: pointer !important;
    color: rgba(49, 51, 63, 0.6) !important;
    font-size: 0.875rem !important;
    font-weight: 400 !important;
    white-space: nowrap !important;
    transition: color 0.15s !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label [data-baseweb="radio"],
[data-testid="stRadio"] [role="radiogroup"] > label input[type="radio"] {
    display: none !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
    border-bottom: 2px solid rgb(255, 75, 75) !important;
    color: rgb(255, 75, 75) !important;
    font-weight: 600 !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label:hover {
    color: rgba(49, 51, 63, 0.85) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Seleção de período ────────────────────────────────────────────────────────
_MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

with SessionLocal() as _s:
    _periodos_lista = get_periodos_com_consolidacao(_s)

if not _periodos_lista:
    empty_state(
        "🛒",
        "Sem dados de compras",
        "Execute a consolidação em Análise de Compras e aprove itens na Lista Final primeiro.",
    )
    st.stop()

_periodo_opcoes = {
    f"{_MESES_PT[p.month]}/{p.year}": p for p in _periodos_lista
}
_periodo_label = st.selectbox(
    "Período",
    list(_periodo_opcoes.keys()),
    key="orc_periodo_sel",
    label_visibility="collapsed",
)
periodo: datetime.date = _periodo_opcoes[_periodo_label]

# ── Abas — orc_tab_nav permite navegação programática sem violar restrição do Streamlit ──
_TAB_OPTIONS = ["Painel", "Cotações", "Histórico"]
_nav_request = st.session_state.pop("orc_tab_nav", None)
_tab_index = _TAB_OPTIONS.index(_nav_request) if _nav_request in _TAB_OPTIONS else 0

tab_sel = st.radio(
    "Navegação",
    _TAB_OPTIONS,
    key="orc_tab",
    horizontal=True,
    label_visibility="collapsed",
    index=_tab_index,
)

# Constantes de status compartilhadas entre abas
_STATUS_PT = {
    "RASCUNHO": "Rascunho", "EM_COTACAO": "Em cotação",
    "PRONTO_PARA_APROVACAO": "Pronto para aprovação",
    "ENVIADO_APROVACAO": "Aguardando aprovação", "APROVADO": "Aprovado",
    "APROVADO_PARCIAL": "Aprovado parcialmente", "REVISAR": "Revisão solicitada",
    "DEVOLVIDO_REVISAO": "Devolvido para revisão",
    "REPROVADO": "Reprovado", "CANCELADO": "Cancelado",
}
_STATUS_ITEM_PT = {
    "SEM_COTACAO":       "Sem cotação",
    "COM_COTACAO":       "Com cotação",
    "APROVADO_DIRETOR":  "✅ Aprovado",
    "REPROVADO_DIRETOR": "❌ Reprovado",
    "REVISAO_DIRETOR":   "🔄 Revisão solicitada",
}
_STATUS_BADGE: dict[str, tuple[str, str]] = {
    "RASCUNHO":               ("#F4F4F5", "#737373"),
    "EM_COTACAO":             ("#DBEAFE", "#2563EB"),
    "PRONTO_PARA_APROVACAO":  ("#DCFCE7", "#16A34A"),
    "ENVIADO_APROVACAO":      ("#FEF3C7", "#B45309"),
    "APROVADO":               ("#DCFCE7", "#16A34A"),
    "APROVADO_PARCIAL":       ("#DCFCE7", "#16A34A"),
    "REVISAR":                ("#FEF3C7", "#B45309"),
    "DEVOLVIDO_REVISAO":      ("#FEE2E2", "#DC2626"),
    "REPROVADO":              ("#FEE2E2", "#DC2626"),
    "CANCELADO":              ("#F4F4F5", "#737373"),
}


@st.dialog("Fornecedor", width="large")
def _modal_adicionar_fornecedor(item_orc_id: int) -> None:
    _aba_forn = st.radio(
        "aba_forn",
        ["Criar novo fornecedor", "Vincular fornecedor existente", "Fornecedor temporário"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"aba_forn_{item_orc_id}",
    )
    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # ── Criar novo fornecedor ─────────────────────────────────────────────
    if _aba_forn == "Criar novo fornecedor":
        nome = st.text_input("Nome *", key=f"md_forn_nome_{item_orc_id}")
        _mc1, _mc2 = st.columns(2)
        contato = _mc1.text_input("Contato", key=f"md_forn_contato_{item_orc_id}")
        telefone = _mc2.text_input("Telefone", key=f"md_forn_tel_{item_orc_id}")
        email = st.text_input("E-mail", key=f"md_forn_email_{item_orc_id}")
        website = st.text_input(
            "Website",
            placeholder="https://www.site.com.br ou https://lista.mercadolivre.com.br/{query}",
            help="Use `{query}` no URL para pesquisa automática pelo nome do item",
            key=f"md_forn_website_{item_orc_id}",
        )
        _mp1, _mp2 = st.columns(2)
        preferencial = _mp1.checkbox("Preferencial", key=f"md_forn_pref_{item_orc_id}")
        ativo = _mp2.checkbox("Ativo", value=True, key=f"md_forn_ativo_{item_orc_id}")

        _erros = []
        if not nome.strip():
            _erros.append("Nome é obrigatório.")

        if _erros:
            for e in _erros:
                st.warning(e, icon="⚠️")

        if st.button(
            "Cadastrar e vincular",
            type="primary",
            disabled=bool(_erros),
            key=f"md_forn_salvar_{item_orc_id}",
            use_container_width=True,
        ):
            try:
                with SessionLocal() as session:
                    novo_forn = create_fornecedor(
                        session,
                        nome=nome.strip(),
                        contato_nome=contato.strip() or None,
                        telefone=telefone.strip() or None,
                        email=email.strip() or None,
                        website=website.strip() or None,
                        preferencial=preferencial,
                        ativo=ativo,
                    )
                    item_orc = session.query(ItemOrcamento).filter_by(id=item_orc_id).first()
                    lista = session.query(ItemListaCompra).filter_by(id=item_orc.item_lista_id).first()
                    existentes = get_fornecedores_para_item_orcamento(session, item_orc_id)
                    ids_atuais = [f.id for f in existentes]
                    atualizar_fornecedores_item(session, lista.item_id, ids_atuais + [novo_forn.id])
                st.success(f"Fornecedor **{nome.strip()}** cadastrado e vinculado.")
                st.session_state[f"_novo_forn_nome_{item_orc_id}"] = nome.strip()
                st.rerun()
            except ValueError as e:
                st.error(str(e), icon="⚠️")

    # ── Vincular fornecedor existente ─────────────────────────────────────
    elif _aba_forn == "Vincular fornecedor existente":
        with SessionLocal() as _s:
            _todos = get_all_fornecedores(_s)
            _existentes = get_fornecedores_para_item_orcamento(_s, item_orc_id)

        _ids_vinculados = {f.id for f in _existentes}
        _disponiveis = [f for f in _todos if f.id not in _ids_vinculados]

        if not _disponiveis:
            st.info("Todos os fornecedores ativos já estão vinculados a este item.", icon="ℹ️")
        else:
            _opcoes = {f.nome: f.id for f in _disponiveis}
            _selecionados = st.multiselect(
                "Selecione os fornecedores",
                list(_opcoes.keys()),
                key=f"md_vincular_forn_{item_orc_id}",
            )
            if st.button(
                f"Vincular {len(_selecionados)} fornecedor(es)" if _selecionados else "Selecione ao menos um",
                type="primary",
                disabled=not _selecionados,
                key=f"md_vincular_btn_{item_orc_id}",
                use_container_width=True,
            ):
                try:
                    with SessionLocal() as session:
                        item_orc = session.query(ItemOrcamento).filter_by(id=item_orc_id).first()
                        lista = session.query(ItemListaCompra).filter_by(id=item_orc.item_lista_id).first()
                        ids_novos = [_opcoes[n] for n in _selecionados]
                        atualizar_fornecedores_item(
                            session, lista.item_id, list(_ids_vinculados) + ids_novos,
                        )
                    st.success(", ".join(f"**{n}**" for n in _selecionados) + " vinculado(s) com sucesso.")
                    if len(_selecionados) == 1:
                        st.session_state[f"_novo_forn_nome_{item_orc_id}"] = _selecionados[0]
                    st.rerun()
                except Exception as e:
                    st.error(str(e), icon="⚠️")

    # ── Fornecedor temporário ─────────────────────────────────────────────
    elif _aba_forn == "Fornecedor temporário":
        st.info(
            "Use para cotações de fornecedores que não precisam ser cadastrados no sistema. "
            "O nome será usado apenas nesta cotação.",
            icon="ℹ️",
        )
        temp_nome = st.text_input(
            "Nome / Origem *",
            placeholder="Ex: Mercado Livre, Atacadão, site externo",
            key=f"md_forn_temp_{item_orc_id}",
        )
        if not temp_nome.strip():
            st.warning("Informe o nome ou origem.", icon="⚠️")
        elif st.button(
            "Usar para esta cotação",
            type="primary",
            key=f"md_forn_temp_usar_{item_orc_id}",
            use_container_width=True,
        ):
            st.session_state[f"cot_forn_temp_active_{item_orc_id}"] = temp_nome.strip()
            st.rerun()


@st.dialog("Editar cotação", width="large")
def _modal_editar_cotacao(cotacao_id: int) -> None:
    with SessionLocal() as _s:
        cot = _s.get(CotacaoOrcamento, cotacao_id)
        if cot is None:
            st.error("Cotação não encontrada.")
            return
        _origem = cot.origem
        _preco  = cot.preco_unitario
        _frete  = cot.frete or 0.0
        _desc   = cot.desconto or 0.0
        _outros = cot.outros_custos or 0.0
        _link   = cot.link or ""
        _obs    = cot.observacao or ""
        _data   = cot.data_cotacao

    def _fmt_br(v: float) -> str:
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _parse_brl(s: str) -> float | None:
        s = s.strip().replace("R$", "").replace(" ", "")
        if not s:
            return None
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    c1, c2 = st.columns(2)
    with c1:
        origem_edit = st.text_input(
            "Origem / Fornecedor *", value=_origem, key=f"ec_orig_{cotacao_id}",
        )
        link_edit = st.text_input(
            "Link do produto (opcional)", value=_link, key=f"ec_link_{cotacao_id}",
        )
    with c2:
        preco_edit = st.text_input(
            "Preço unitário (R$) *", value=_fmt_br(_preco), key=f"ec_preco_{cotacao_id}",
            help="Apenas números, ponto e vírgula. Ex: 1.250,90",
        )
        data_edit = st.date_input(
            "Data da cotação *", value=_data, key=f"ec_data_{cotacao_id}",
        )

    c3, c4, c5 = st.columns(3)
    with c3:
        frete_edit = st.text_input("Frete (R$)", value=_fmt_br(_frete), key=f"ec_frete_{cotacao_id}")
    with c4:
        desc_edit = st.text_input("Desconto (R$)", value=_fmt_br(_desc), key=f"ec_desc_{cotacao_id}")
    with c5:
        outros_edit = st.text_input("Outros custos (R$)", value=_fmt_br(_outros), key=f"ec_outros_{cotacao_id}")

    obs_edit = st.text_area(
        "Observação (opcional)", value=_obs, height=60, key=f"ec_obs_{cotacao_id}",
    )

    if st.button(
        "Salvar alterações", type="primary",
        key=f"ec_salvar_{cotacao_id}", use_container_width=True,
    ):
        preco_v  = _parse_brl(preco_edit or "")
        frete_v  = _parse_brl(frete_edit or "") or 0.0
        desc_v   = _parse_brl(desc_edit or "") or 0.0
        outros_v = _parse_brl(outros_edit or "") or 0.0
        if not origem_edit.strip():
            st.error("O campo 'Origem / Fornecedor' é obrigatório.", icon="⚠️")
        elif preco_v is None or preco_v <= 0:
            st.error("Preço unitário inválido ou zero. Use o formato R$ 1.250,90.", icon="⚠️")
        else:
            try:
                with SessionLocal() as session:
                    editar_cotacao(
                        session, cotacao_id,
                        origem=origem_edit.strip(),
                        preco_unitario=preco_v,
                        frete=frete_v,
                        desconto=desc_v,
                        outros_custos=outros_v,
                        link=link_edit.strip() or None,
                        observacao=obs_edit.strip() or None,
                        data_cotacao=data_edit,
                    )
                st.rerun()
            except ValueError as e:
                st.error(str(e), icon="⚠️")


@st.dialog("Orçamento aprovado — Resumo para Compra", width="large")
def _dialog_resumo_compra(orc_enc: Orcamento) -> None:
    """Exibe resumo de compra agrupado por fornecedor para o orçamento aprovado."""
    with SessionLocal() as _s:
        _itens = get_itens_aprovados(_s, orc_enc.id)

    if not _itens:
        st.warning("Nenhum item aprovado encontrado para este orçamento.")
        return

    _grupos: dict[str, list] = {}
    _total_geral = 0.0
    for _item in sorted(_itens, key=lambda i: (i.categoria_nome or "", i.nome_item)):
        _cot = menor_cotacao(_item)
        _forn = _cot.origem if _cot else "Sem fornecedor"
        _grupos.setdefault(_forn, [])
        _total_item = _cot.total_calculado if _cot else 0.0
        _total_geral += _total_item
        _grupos[_forn].append({
            "Item": _item.nome_item,
            "Categoria": _item.categoria_nome or "—",
            "Qtd": _item.quantidade_orcada,
            "Unitário": fmt_brl(_cot.preco_unitario) if _cot else "—",
            "Frete": fmt_brl(_cot.frete) if _cot and _cot.frete else "—",
            "Total": fmt_brl(_total_item),
        })

    st.caption(
        f"{orc_enc.numero} v{orc_enc.versao} · "
        f"{len(_itens)} item(ns) aprovado(s) · "
        f"{len(_grupos)} fornecedor(es)"
    )

    for _forn, _rows in _grupos.items():
        st.markdown(f"#### 🏪 {_forn}")
        st.dataframe(pd.DataFrame(_rows), hide_index=True, use_container_width=True)

    st.divider()
    st.markdown(
        f"<p style='text-align:right;font-size:16px;font-weight:700;margin:0;'>"
        f"Total geral: {fmt_brl(_total_geral)}</p>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    try:
        _docx_bytes_compra, _docx_name_compra = _bytes_docx_orcamento(orc_enc.id)
        st.download_button(
            "Baixar Orçamento (DOCX)",
            data=_docx_bytes_compra,
            file_name=_docx_name_compra,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            key="btn_download_docx_compra",
        )
    except Exception as _e:
        st.error(f"Erro ao gerar documento: {_e}", icon="⚠️")


# ===========================================================================
# ABA PAINEL
# ===========================================================================
if tab_sel == "Painel":
    with SessionLocal() as session:
        _orc_pre = get_orcamento_ativo(session, periodo)
        _sync_result = {"adicionados": 0, "removidos": 0, "atualizados": 0}
        if _orc_pre and _orc_pre.status in ("RASCUNHO", "EM_COTACAO"):
            _sync_result = sincronizar_com_lista_final(session, _orc_pre.id)
        orc = get_orcamento_ativo(session, periodo)
        lista_final = get_lista_final_para_orcamento(session, periodo)
        n_lista = len(lista_final["itens_estoque"]) + len(lista_final["itens_avulsos"])

    if any(_sync_result.values()):
        _partes: list[str] = []
        if _sync_result["adicionados"]:
            n = _sync_result["adicionados"]
            _partes.append(f"+{n} item{'ns' if n > 1 else ''} adicionado{'s' if n > 1 else ''}")
        if _sync_result["removidos"]:
            n = _sync_result["removidos"]
            _partes.append(f"{n} removido{'s' if n > 1 else ''}")
        if _sync_result["atualizados"]:
            n = _sync_result["atualizados"]
            _partes.append(f"{n} quantidade{'s atualizada' if n > 1 else ' atualizada'}")
        st.toast(f"Orçamento sincronizado com a Lista Final — {', '.join(_partes)}", icon="🔄")

    # ── Sem Lista Final ─────────────────────────────────────────────────────
    if n_lista == 0:
        empty_state(
            "📋",
            "Sem Lista Final aprovada",
            "Aprove itens na aba Lista Final da camada de Compras para poder gerar o orçamento.",
        )
        st.stop()

    # ── Sem orçamento ativo — formulário de criação ─────────────────────────
    if orc is None:
        # Card de conclusão: mostra o último orçamento encerrado do período, se houver
        with SessionLocal() as _s_enc:
            _ultimo_encerrado = (
                _s_enc.query(Orcamento)
                .filter(
                    Orcamento.periodo_referencia == periodo,
                    Orcamento.status.in_({"APROVADO", "APROVADO_PARCIAL", "REPROVADO"}),
                )
                .order_by(Orcamento.versao.desc())
                .first()
            )
        if _ultimo_encerrado:
            _cfg_enc = {
                "APROVADO": ("#DCFCE7", "#16A34A", "✅", "Orçamento aprovado integralmente.",
                             "Todos os itens foram aprovados e estão no Orçamento Final, aguardando compra."),
                "APROVADO_PARCIAL": ("#FEF3C7", "#B45309", "✅", "Orçamento aprovado parcialmente.",
                                     "Itens aprovados estão no Orçamento Final. Itens reprovados foram removidos automaticamente."),
                "REPROVADO": ("#FEE2E2", "#DC2626", "❌", "Orçamento reprovado.",
                              "Todos os itens foram reprovados e removidos do Orçamento automaticamente."),
            }.get(_ultimo_encerrado.status, ("#F4F4F5", "#737373", "ℹ️", "Ciclo encerrado.", ""))
            _bg_enc, _fg_enc, _icon_enc, _titulo_enc, _detalhe_enc = _cfg_enc
            _data_dec_enc = (
                _ultimo_encerrado.decidido_em.strftime("%d/%m/%Y %H:%M")
                if _ultimo_encerrado.decidido_em else "—"
            )
            st.markdown(
                f"<div style='background:{_bg_enc};border-radius:8px;padding:16px 20px;margin-bottom:12px;'>"
                f"<p style='color:{_fg_enc};font-size:16px;font-weight:700;margin:0 0 4px;'>"
                f"{_icon_enc} {_titulo_enc}</p>"
                f"<p style='color:#444;margin:0 0 4px;'>{_detalhe_enc}</p>"
                f"<p style='color:#737373;font-size:12px;margin:0;'>"
                f"{_ultimo_encerrado.numero} v{_ultimo_encerrado.versao} · Decidido em: {_data_dec_enc}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if _ultimo_encerrado.status in ("APROVADO", "APROVADO_PARCIAL"):
                if st.button(
                    "Orçamento aprovado para compra",
                    type="primary",
                    use_container_width=True,
                    key="btn_ver_compra",
                ):
                    _dialog_resumo_compra(_ultimo_encerrado)
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        st.info(
            f"**Lista Final disponível — {_periodo_label}**  \n"
            f"{n_lista} item(ns) aprovado(s) para orçamento.",
            icon="📋",
        )
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        section_title("Criar Orçamento")

        with st.form("form_criar_orc"):
            responsavel = st.text_input(
                "Responsável pelo orçamento",
                placeholder="Nome do responsável",
                key="orc_responsavel",
            )
            submit_criar = st.form_submit_button(
                "Gerar Orçamento", type="primary", use_container_width=True
            )

        if submit_criar:
            if not responsavel.strip():
                st.error("Informe o nome do responsável.", icon="⚠️")
            else:
                try:
                    with SessionLocal() as session:
                        novo_orc = criar_orcamento(session, periodo, responsavel.strip())
                    st.success(f"Orçamento **{novo_orc.numero}** criado com {n_lista} item(ns).")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e), icon="⚠️")

    # ── Orçamento ativo — painel de gestão ──────────────────────────────────
    else:
        bg, fg = _STATUS_BADGE.get(orc.status, ("#F4F4F5", "#737373"))
        status_label = _STATUS_PT.get(orc.status, orc.status)

        st.markdown(
            f"<span style='background:{bg};color:{fg};padding:3px 10px;border-radius:5px;"
            f"font-size:13px;font-weight:600;'>{status_label}</span>"
            f"&nbsp;&nbsp;<span style='color:#737373;font-size:13px;'>"
            f"{orc.numero} · v{orc.versao} · Responsável: {orc.responsavel}</span>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        # Carregar resumo e itens uma única vez para todo o bloco
        with SessionLocal() as session:
            resumo = get_resumo(session, orc)
            itens_orc = (
                session.query(ItemOrcamento)
                .options(joinedload(ItemOrcamento.cotacoes))
                .filter(ItemOrcamento.orcamento_id == orc.id)
                .order_by(ItemOrcamento.categoria_nome, ItemOrcamento.nome_item)
                .all()
            )
            rows_tabela = []
            for item in itens_orc:
                cot_menor = menor_cotacao(item)
                rows_tabela.append({
                    "Item": item.nome_item,
                    "Categoria": item.categoria_nome,
                    "Qtd": item.quantidade_orcada,
                    "Tipo": "Avulsa" if item.tipo == "AVULSA" else "Estoque",
                    "Cotações": len(item.cotacoes),
                    "Melhor valor": fmt_brl(cot_menor.total_calculado) if cot_menor else "—",
                    "Fornecedor": cot_menor.origem if cot_menor else "—",
                    "Status": _STATUS_ITEM_PT.get(item.status_item, item.status_item),
                })

        is_bloqueado = orc.status in {"ENVIADO_APROVACAO", "APROVADO", "APROVADO_PARCIAL", "REPROVADO", "REVISAR"}

        # ── Feedback contextual pós-decisão + ação (ANTES das métricas) ─────
        def _btn_nova_versao():
            if st.button(
                f"Criar novo orçamento (v{orc.versao + 1})",
                type="primary",
                key="btn_nova_versao",
            ):
                try:
                    with SessionLocal() as _s:
                        nova = criar_nova_versao(_s, orc.id)
                    st.success(f"Nova versão criada: **{nova.numero} v{nova.versao}**.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e), icon="⚠️")

        if orc.status == "REVISAR":
            _n_revisao   = sum(1 for i in itens_orc if i.status_item == "REVISAO_DIRETOR")
            _n_aprovados = sum(1 for i in itens_orc if i.status_item == "APROVADO_DIRETOR")
            _n_reprovados = sum(1 for i in itens_orc if i.status_item == "REPROVADO_DIRETOR")
            _msg_rev = (
                f"**{_n_revisao} item(ns) precisam de novas cotações.** "
                f"{_n_aprovados} item(ns) aprovados serão mantidos bloqueados na nova versão"
                + (f" · {_n_reprovados} reprovado(s) removido(s) da lista" if _n_reprovados else "")
                + "."
            )
            if orc.decidido_em:
                _msg_rev += f"  \n_Decisão em: {orc.decidido_em.strftime('%d/%m/%Y %H:%M')}_"
            if orc.observacao_diretor:
                _msg_rev += f"  \n**Obs. do diretor:** {orc.observacao_diretor}"
            st.warning(_msg_rev, icon="🔄")
            _btn_nova_versao()
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        elif orc.status == "DEVOLVIDO_REVISAO":
            st.warning(
                "O diretor devolveu o orçamento para revisão geral. "
                "Crie uma nova versão para re-cotar todos os itens.",
                icon="↩️",
            )
            _btn_nova_versao()
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        elif (
            orc.status in ("EM_COTACAO", "RASCUNHO")
            and orc.observacao_geral
            and ("[Revisão" in orc.observacao_geral or "[Devolvido" in orc.observacao_geral)
        ):
            _is_devolvido = "[Devolvido" in orc.observacao_geral
            _ctx = (
                orc.observacao_geral
                .replace("[Revisão v", "Esta versão foi criada a partir da revisão da v")
                .replace("[Devolvido v", "Esta versão foi criada a partir da v")
            )
            if _is_devolvido:
                _detalhe = "_O orçamento foi devolvido integralmente pelo diretor. Itens aprovados estão bloqueados com suas cotações; os demais precisam de novas cotações._"
            else:
                _detalhe = "_Itens com status 'Sem cotação' precisam de novas cotações. Itens aprovados estão bloqueados com as cotações anteriores._"
            st.info(f"↩️ {_ctx}  \n{_detalhe}")
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        # ── Métricas ─────────────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de itens", resumo.total_itens)
        c2.metric("Com cotação escolhida", resumo.com_escolha)
        c3.metric("Sem cotação", resumo.sem_cotacao)
        c4.metric("Total estimado", fmt_brl(resumo.total_geral))

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        # ── Tabela de itens (read-only) ──────────────────────────────────────
        section_title("Itens do Orçamento")

        if rows_tabela:
            st.dataframe(
                pd.DataFrame(rows_tabela),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        # ── Ações globais ────────────────────────────────────────────────────
        if not is_bloqueado:
            pode_enviar = resumo.sem_cotacao == 0 and resumo.com_cotacao_sem_escolha == 0
            col_env, col_can = st.columns([3, 1])

            with col_env:
                if st.button(
                    "Enviar para Aprovação",
                    type="primary",
                    disabled=not pode_enviar,
                    use_container_width=True,
                    key="btn_enviar_aprov",
                    help=None if pode_enviar else "Todos os itens precisam ter cotação escolhida.",
                ):
                    try:
                        with SessionLocal() as session:
                            enviar_para_aprovacao(session, orc.id)
                        st.success("Orçamento enviado para aprovação.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e), icon="⚠️")

            with col_can:
                if st.button("Cancelar", use_container_width=True, key="btn_cancelar_orc"):
                    try:
                        with SessionLocal() as session:
                            cancelar_orcamento(session, orc.id)
                        st.success("Orçamento cancelado.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e), icon="⚠️")

        if orc.status == "ENVIADO_APROVACAO":
            _link_aprov = f"{APP_BASE_URL}/Aprovacao_Orcamento?id={orc.id}"
            _msg_aprov = gerar_mensagem_aprovacao(orc, _periodo_label, _link_aprov)
            _wame_aprov = f"https://wa.me/?text={quote_plus(_msg_aprov)}"
            st.info(
                "Orçamento aguardando aprovação. Compartilhe o link com o responsável pela decisão.",
                icon="🔗",
            )
            st.link_button("📱 Enviar via WhatsApp", _wame_aprov, use_container_width=False)
            st.caption("Link direto para aprovação:")
            st.code(_link_aprov, language=None)


# ===========================================================================
# ABA COTAÇÕES — autossuficiente, não depende de vir do Painel
# ===========================================================================
elif tab_sel == "Cotações":
    with SessionLocal() as session:
        orc = get_orcamento_ativo(session, periodo)
        if orc is not None:
            itens_cot = (
                session.query(ItemOrcamento)
                .filter(ItemOrcamento.orcamento_id == orc.id)
                .order_by(ItemOrcamento.categoria_nome, ItemOrcamento.nome_item)
                .all()
            )
            cotacao_counts: dict[int, int] = {
                row[0]: row[1]
                for row in session.query(ItemOrcamento.id, func.count(CotacaoOrcamento.id))
                .outerjoin(CotacaoOrcamento)
                .filter(ItemOrcamento.orcamento_id == orc.id)
                .group_by(ItemOrcamento.id)
                .all()
            }
            _itens_pendentes = [i for i in itens_cot if cotacao_counts.get(i.id, 0) == 0]
            _itens_cotados = [i for i in itens_cot if cotacao_counts.get(i.id, 0) > 0]
            _opcoes_cot: dict[str, int] = {}
            for i in _itens_pendentes:
                _opcoes_cot[f"⚠ {i.nome_item} ({i.categoria_nome})"] = i.id
            for i in _itens_cotados:
                n = cotacao_counts[i.id]
                _opcoes_cot[f"✓ {i.nome_item} ({i.categoria_nome}) — {n} {'cotação' if n == 1 else 'cotações'}"] = i.id
            _total_itens = len(itens_cot)
            _com_cotacao = len(_itens_cotados)
            _orc_status = orc.status
            _orc_id = orc.id
        else:
            _opcoes_cot = {}
            _total_itens = 0
            _com_cotacao = 0
            _orc_status = None
            _orc_id = None

    if orc is None:
        empty_state(
            "📋",
            "Nenhum orçamento ativo",
            "Crie o orçamento na aba Painel para começar a registrar cotações.",
        )
        st.stop()

    if not _opcoes_cot:
        empty_state("📦", "Orçamento sem itens", "O orçamento não possui itens cadastrados.")
        st.stop()

    is_bloqueado = _orc_status in {"ENVIADO_APROVACAO", "APROVADO", "APROVADO_PARCIAL", "REPROVADO", "REVISAR"}

    # ── Seletor de item ──────────────────────────────────────────────────────
    # Pré-seleciona o item vindo do Painel (se houver); senão usa o primeiro.
    _item_id_pre = st.session_state.get("orc_item_id")
    _item_labels = list(_opcoes_cot.keys())

    _idx_pre = 0
    if _item_id_pre is not None:
        for idx, (lbl, iid) in enumerate(_opcoes_cot.items()):
            if iid == _item_id_pre:
                _idx_pre = idx
                break

    st.progress(_com_cotacao / _total_itens if _total_itens else 0)
    st.caption(f"{_com_cotacao} de {_total_itens} {'item' if _total_itens == 1 else 'itens'} com cotação registrada")

    item_sel_label = st.selectbox(
        "Item",
        _item_labels,
        index=_idx_pre,
        key="orc_item_sel_cot",
        label_visibility="visible",
    )
    item_sel_id = _opcoes_cot[item_sel_label]

    # Atualiza session_state para manter consistência com Painel
    st.session_state["orc_item_id"] = item_sel_id

    # ── Carrega item, cotações e fornecedores vinculados ────────────────────
    with SessionLocal() as session:
        item = (
            session.query(ItemOrcamento)
            .options(joinedload(ItemOrcamento.cotacoes))
            .filter(ItemOrcamento.id == item_sel_id)
            .first()
        )
        cotacoes = list(item.cotacoes) if item else []
        cot_min = menor_cotacao(item) if item else None
        item_tipo = item.tipo if item else "ESTOQUE"
        item_nome = item.nome_item if item else "—"
        item_qtd = item.quantidade_orcada if item else 0
        item_status = item.status_item if item else "SEM_COTACAO"
        item_lista_id = item.item_lista_id if item else None
        item_compra_avulsa_id = item.compra_avulsa_id if item else None
        fornecedores_vinculados = get_fornecedores_para_item_orcamento(session, item_sel_id)

    tipo_str = "Compra Avulsa" if item_tipo == "AVULSA" else "Estoque"
    st.markdown(
        f"<span style='font-size:15px;font-weight:600;'>{item_nome}</span>"
        f"&nbsp;&nbsp;<span style='color:#737373;font-size:13px;'>"
        f"{tipo_str} · Qtd: {item_qtd}</span>",
        unsafe_allow_html=True,
    )

    if is_bloqueado:
        st.warning(
            f"Orçamento com status **{_STATUS_PT.get(_orc_status, _orc_status)}** — "
            "edição de cotações bloqueada.",
            icon="🔒",
        )

    # ── Bloco pós-decisão do diretor ─────────────────────────────────────────
    if item_status == "APROVADO_DIRETOR":
        st.success("Item aprovado pelo diretor. Nenhuma ação adicional necessária.")

    elif item_status == "REVISAO_DIRETOR":
        st.warning(
            "O diretor solicitou revisão das cotações deste item. "
            "Crie uma nova versão do orçamento no **Painel** para refazer a cotação. "
            "A melhor cotação atual será mantida como referência.",
            icon="🔄",
        )

    elif item_status == "REPROVADO_DIRETOR":
        # Verifica se já foi removido da Lista Final
        _ja_removido = False
        if item_tipo == "ESTOQUE" and item_lista_id:
            with SessionLocal() as _s:
                _lista = _s.get(ItemListaCompra, item_lista_id)
                _ja_removido = _lista is not None and not _lista.incluir_na_lista_final
        elif item_tipo == "AVULSA" and item_compra_avulsa_id:
            from core.models import CompraAvulsa
            with SessionLocal() as _s:
                _avulsa = _s.get(CompraAvulsa, item_compra_avulsa_id)
                _ja_removido = _avulsa is not None and not _avulsa.incluir_na_lista_final

        if _ja_removido:
            st.info("Item removido da Lista Final de Compras.", icon="✅")
        else:
            st.error("Este item foi reprovado pelo diretor.", icon="❌")
            if st.button(
                "Remover da Lista Final",
                key=f"rm_lista_{item_sel_id}",
                type="primary",
                help="Desmarca este item da Lista Final de Compras — ele não será comprado neste período.",
            ):
                try:
                    with SessionLocal() as session:
                        remover_item_reprovado(session, item_sel_id)
                    st.success("Item removido da Lista Final de Compras.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e), icon="⚠️")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Sites de pesquisa (por item selecionado) ──────────────────────────────
    _forn_com_website = [f for f in fornecedores_vinculados if f.website]

    if _forn_com_website:
        with st.expander("🔍 Pesquisar preços", expanded=False):
            _btn_cols = st.columns(min(len(_forn_com_website), 4))
            for _bi, _fweb in enumerate(_forn_com_website):
                _url = _fweb.website
                if "{query}" in _url:
                    _url = _url.replace("{query}", quote_plus(item_nome))
                with _btn_cols[_bi % 4]:
                    st.link_button(f"🔗 {_fweb.nome}", _url, use_container_width=True)

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # ── Cotações registradas ─────────────────────────────────────────────────
    if cotacoes:
        section_title(f"Cotações registradas ({len(cotacoes)})")

        for cot in sorted(cotacoes, key=lambda c: c.total_calculado):
            is_melhor = cot_min and cot.id == cot_min.id
            bg_cor = "#f0fdf4" if is_melhor else "#fafafa"
            badge = (
                " <span style='background:#dcfce7;color:#16a34a;padding:1px 6px;"
                "border-radius:4px;font-size:11px;font-weight:600;'>★ Melhor Preço</span>"
                if is_melhor else ""
            )

            st.markdown(
                f"<div style='background:{bg_cor};border-radius:6px;padding:10px 14px;margin-bottom:6px;'>"
                f"<b>{cot.origem}</b>{badge}  &nbsp;|&nbsp;"
                f"Unit: <b>{fmt_brl(cot.preco_unitario)}</b>  &nbsp;|&nbsp;"
                f"Frete: {fmt_brl(cot.frete) if cot.frete else '—'}  &nbsp;|&nbsp;"
                f"<b>Total: {fmt_brl(cot.total_calculado)}</b>"
                + (f"  |  Data: {cot.data_cotacao.strftime('%d/%m/%Y')}" if cot.data_cotacao else "")
                + "</div>",
                unsafe_allow_html=True,
            )

            if not is_bloqueado:
                _bc1, _bc2 = st.columns(2)
                with _bc1:
                    if st.button("Editar", key=f"edit_{cot.id}", use_container_width=True):
                        _modal_editar_cotacao(cot.id)
                with _bc2:
                    if st.button("Remover", key=f"rem_{cot.id}", use_container_width=True):
                        with SessionLocal() as session:
                            remover_cotacao(session, cot.id)
                        st.rerun()

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    else:
        st.info("Nenhuma cotação registrada para este item ainda.", icon="ℹ️")

    # ── Formulário de nova cotação ───────────────────────────────────────────
    # O formulário fica atrás de um botão "+ Nova cotação" para evitar que a
    # tela fique sempre com campos em branco. Limite de 5 cotações por item.
    # O estado de abertura usa chave por item_sel_id — ao trocar de item o
    # formulário fecha automaticamente (nova chave começa como False).
    _MAX_COTACOES = 5
    _form_key = f"cot_form_open_{item_sel_id}"

    if not is_bloqueado:
        if len(cotacoes) >= _MAX_COTACOES:
            st.info(f"Limite de {_MAX_COTACOES} cotações por item atingido.", icon="ℹ️")
        elif not st.session_state.get(_form_key, False):
            if st.button("+ Nova cotação", key=f"btn_nova_cot_{item_sel_id}"):
                st.session_state[_form_key] = True
                st.rerun()

    if not is_bloqueado and st.session_state.get(_form_key, False):
        section_title("Nova cotação")

        def _parse_brl(s: str) -> float | None:
            """Converte string BR (ex: '1.250,90') para float. Retorna None se inválido."""
            s = s.strip().replace("R$", "").replace(" ", "")
            if not s:
                return None
            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            try:
                return float(s)
            except ValueError:
                return None

        _fv = st.session_state.get(f"cot_fv_{item_sel_id}", 0)

        def _sanitize_numeric_br(key: str) -> None:
            """Remove do session_state qualquer caractere que não seja dígito, vírgula ou ponto."""
            if key in st.session_state:
                val = str(st.session_state[key])
                clean = "".join(c for c in val if c.isdigit() or c in ",.")
                if clean != val:
                    st.session_state[key] = clean

        _k_preco = f"cot_preco_{item_sel_id}_{_fv}"
        _k_frete = f"cot_frete_{item_sel_id}_{_fv}"
        _k_desc  = f"cot_desc_{item_sel_id}_{_fv}"
        _k_outr  = f"cot_outros_{item_sel_id}_{_fv}"

        _sanitize_numeric_br(_k_preco)
        _sanitize_numeric_br(_k_frete)
        _sanitize_numeric_br(_k_desc)
        _sanitize_numeric_br(_k_outr)

        _forn_id_sel = None
        _temp_ativo_key = f"cot_forn_temp_active_{item_sel_id}"
        _temp_nome_ativo = st.session_state.get(_temp_ativo_key)

        c1, c2 = st.columns(2)
        with c1:
            if _temp_nome_ativo:
                st.selectbox(
                    "Origem / Fornecedor *",
                    [_temp_nome_ativo],
                    disabled=True,
                    help="Fornecedor temporário — não cadastrado no sistema",
                    key=f"cot_forn_temp_display_{item_sel_id}_{_fv}",
                )
                if st.button("Alterar", key=f"cot_forn_temp_alterar_{item_sel_id}_{_fv}"):
                    del st.session_state[_temp_ativo_key]
                    st.rerun()
                origem = _temp_nome_ativo
            elif fornecedores_vinculados:
                _forn_names = [f.nome for f in fornecedores_vinculados]
                _key_forn_sel = f"cot_forn_sel_{item_sel_id}_{_fv}"
                _pre_sel_forn = st.session_state.pop(f"_novo_forn_nome_{item_sel_id}", None)
                if _pre_sel_forn and _pre_sel_forn in _forn_names:
                    st.session_state[_key_forn_sel] = _pre_sel_forn
                _sel_forn = st.selectbox(
                    "Origem / Fornecedor *",
                    _forn_names,
                    key=_key_forn_sel,
                )
                origem = _sel_forn
                _forn_obj = next((f for f in fornecedores_vinculados if f.nome == _sel_forn), None)
                _forn_id_sel = _forn_obj.id if _forn_obj else None
                if st.button(
                    "➕ Cadastrar novo fornecedor",
                    key=f"btn_add_forn_{item_sel_id}_{_fv}",
                    help="Cadastra um novo fornecedor e vincula a este item",
                ):
                    _modal_adicionar_fornecedor(item_sel_id)
            else:
                origem = st.text_input(
                    "Origem / Fornecedor *",
                    placeholder="Ex: Mercado Livre, Fornecedor X",
                    key=f"cot_origem_{item_sel_id}_{_fv}",
                )
                if item_tipo != "AVULSA":
                    if st.button(
                        "➕ Cadastrar novo fornecedor",
                        key=f"btn_add_forn_{item_sel_id}_{_fv}",
                        help="Cadastra um novo fornecedor e vincula a este item",
                    ):
                        _modal_adicionar_fornecedor(item_sel_id)
            link = st.text_input(
                "Link do produto (opcional)",
                placeholder="https://...",
                key=f"cot_link_{item_sel_id}_{_fv}",
            )
        with c2:
            preco_unit_str = st.text_input(
                "Preço unitário (R$) *",
                placeholder="Ex: 1.250,90",
                key=_k_preco,
                help="Apenas números, ponto e vírgula. Ex: 1.250,90",
            )
            data_cot = st.date_input(
                "Data da cotação *",
                value=tempo.hoje(),
                key=f"cot_data_{item_sel_id}_{_fv}",
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            frete_str = st.text_input(
                "Frete (R$)",
                placeholder="0,00",
                key=_k_frete,
            )
        with c4:
            desconto_str = st.text_input(
                "Desconto (R$)",
                placeholder="0,00",
                key=_k_desc,
            )
        with c5:
            outros_str = st.text_input(
                "Outros custos (R$)",
                placeholder="0,00",
                key=_k_outr,
            )

        obs_cot = st.text_area(
            "Observação (opcional)",
            height=60,
            key=f"cot_obs_{item_sel_id}_{_fv}",
        )

        col_salvar, col_cancelar = st.columns([3, 1])
        with col_salvar:
            if st.button("Salvar cotação", type="primary", key=f"btn_salvar_cot_{item_sel_id}_{_fv}", use_container_width=True):
                preco_unit = _parse_brl(preco_unit_str or "")
                frete     = _parse_brl(frete_str or "") or 0.0
                desconto  = _parse_brl(desconto_str or "") or 0.0
                outros    = _parse_brl(outros_str or "") or 0.0

                if not origem.strip():
                    st.error("O campo 'Origem / Fornecedor' é obrigatório.", icon="⚠️")
                elif preco_unit is None or preco_unit <= 0:
                    st.error(
                        "Preço unitário inválido ou zero. Use o formato R$ 1.250,90.",
                        icon="⚠️",
                    )
                else:
                    try:
                        with SessionLocal() as session:
                            add_cotacao(
                                session,
                                item_orc_id=item_sel_id,
                                origem=origem.strip(),
                                preco_unitario=preco_unit,
                                data_cotacao=data_cot,
                                frete=frete,
                                desconto=desconto,
                                outros_custos=outros,
                                link=link.strip() if link.strip() else None,
                                observacao=obs_cot.strip() if obs_cot.strip() else None,
                                fornecedor_id=_forn_id_sel,
                            )
                        st.session_state[f"cot_fv_{item_sel_id}"] = _fv + 1
                        st.session_state[_form_key] = False
                        st.session_state.pop(f"cot_forn_temp_active_{item_sel_id}", None)
                        st.success("Cotação salva.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e), icon="⚠️")
        with col_cancelar:
            if st.button("Cancelar", key=f"btn_cancelar_cot_{item_sel_id}", use_container_width=True):
                st.session_state[_form_key] = False
                st.session_state.pop(f"cot_forn_temp_active_{item_sel_id}", None)
                st.rerun()

    # ── Solicitação a fornecedores (visão global por fornecedor) ──────────────
    st.divider()
    section_title("Solicitação a fornecedores")

    _periodo_label_sol = periodo.strftime("%B/%Y").capitalize()

    with SessionLocal() as _s_sol:
        _grupos_sol = get_fornecedores_para_solicitacao(_s_sol, _orc_id)
        _sols_list_sol = get_solicitacoes_enviadas(_s_sol, _orc_id)

    _sols_by_forn_sol: dict = {}
    for _s_entry in _sols_list_sol:
        if _s_entry.fornecedor_id not in _sols_by_forn_sol:
            _sols_by_forn_sol[_s_entry.fornecedor_id] = _s_entry

    # Exibe apenas fornecedores com contato disponível (WhatsApp)
    _grupos_com_contato = {k: v for k, v in _grupos_sol.items() if v["tem_whatsapp"]}

    if not _grupos_com_contato:
        st.caption("Nenhum fornecedor vinculado com WhatsApp nos itens do orçamento atual.")
    else:
        _prazo_sol = st.date_input(
            "Prazo para resposta",
            value=tempo.hoje() + datetime.timedelta(days=3),
            min_value=tempo.hoje(),
            key=f"sol_prazo_{_orc_id}",
            format="DD/MM/YYYY",
        )

        for _forn_id_sol, _grupo_sol in _grupos_com_contato.items():
            _forn_sol = _grupo_sol["fornecedor"]
            _itens_sol = _grupo_sol["itens"]
            _sol_ex_sol = _sols_by_forn_sol.get(_forn_id_sol)
            _flash_key = f"sol_flash_{_orc_id}_{_forn_id_sol}"
            _flash_sol = st.session_state.pop(_flash_key, None)

            with st.container(border=True):
                _hcol1, _hcol2 = st.columns([3, 1])
                _hcol1.markdown(f"**{_forn_sol.nome}**")
                _hcol2.caption("📱 WhatsApp disponível")

                # Status da última solicitação (feedback persistente)
                if _sol_ex_sol:
                    _dt_sol = _sol_ex_sol.enviado_em.strftime("%d/%m/%Y") if _sol_ex_sol.enviado_em else "?"
                    if _sol_ex_sol.status == "RESPONDIDO":
                        st.success(f"Respondida — solicitação enviada em {_dt_sol}", icon="✅")
                    else:
                        _scol1, _scol2 = st.columns([4, 1])
                        _scol1.warning(f"Aguardando resposta — enviada em {_dt_sol}", icon="⏳")
                        if _scol2.button("✓ Respondida", key=f"sol_resp_{_sol_ex_sol.id}", use_container_width=True):
                            with SessionLocal() as _s_resp_sol:
                                marcar_solicitacao_respondida(_s_resp_sol, _sol_ex_sol.id)
                            st.rerun()

                # Flash após envio via API
                if _flash_sol:
                    if _flash_sol[0] == "success":
                        st.success(_flash_sol[1])
                    else:
                        st.error(_flash_sol[1])

                st.markdown("<div style='height:2px;'></div>", unsafe_allow_html=True)

                _sel_todos_sol = st.checkbox(
                    "Selecionar todos",
                    key=f"sol_all_{_orc_id}_{_forn_id_sol}",
                )
                _selecionados_sol: list = []
                if _sel_todos_sol:
                    _selecionados_sol = list(_itens_sol)
                    for _it_sol in _itens_sol:
                        st.markdown(
                            f"<span style='font-size:13px;color:#444;'>☑ {_it_sol.nome_item}"
                            f" — {_it_sol.quantidade_orcada} un</span>",
                            unsafe_allow_html=True,
                        )
                else:
                    for _it_sol in _itens_sol:
                        if st.checkbox(
                            f"{_it_sol.nome_item} — {_it_sol.quantidade_orcada} un",
                            key=f"sol_item_{_orc_id}_{_forn_id_sol}_{_it_sol.id}",
                        ):
                            _selecionados_sol.append(_it_sol)

                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

                _col_wame, _col_api = st.columns(2)

                if _selecionados_sol:
                    _msg_sol = gerar_mensagem_whatsapp(
                        _forn_sol.nome, _selecionados_sol, _periodo_label_sol, _prazo_sol
                    )
                    _tel_sol = formatar_telefone_wame(_forn_sol.telefone)
                    _wame_url = f"https://wa.me/{_tel_sol}?text={quote_plus(_msg_sol)}"
                    _col_wame.link_button("📱 Abrir WhatsApp", _wame_url, use_container_width=True)

                if cotacao_configurada() and _selecionados_sol and not is_bloqueado:
                    if _col_api.button(
                        "⚡ Enviar via API",
                        key=f"sol_api_{_orc_id}_{_forn_id_sol}",
                        use_container_width=True,
                    ):
                        _itens_txt_sol = [f"{i.nome_item} — {i.quantidade_orcada} un" for i in _selecionados_sol]
                        _res_sol = enviar_solicitacao_cotacao(
                            _forn_sol.telefone,
                            _forn_sol.nome,
                            _periodo_label_sol,
                            _itens_txt_sol,
                            _prazo_sol.strftime("%d/%m/%Y"),
                        )
                        with SessionLocal() as _s_reg_sol:
                            registrar_solicitacao_enviada(
                                _s_reg_sol, _orc_id, _forn_id_sol, _selecionados_sol,
                                _prazo_sol, _res_sol.wamid if _res_sol.sucesso else None,
                            )
                        if _res_sol.sucesso:
                            st.session_state[_flash_key] = ("success", f"✓ Mensagem enviada para {_forn_sol.nome}.")
                        else:
                            st.session_state[_flash_key] = ("error", f"Falha ao enviar para {_forn_sol.nome}: {_res_sol.motivo_falha}")
                        st.rerun()


# ===========================================================================
# ABA HISTÓRICO
# ===========================================================================
elif tab_sel == "Histórico":
    with SessionLocal() as session:
        historico = get_orcamentos_periodo(session, periodo)
        # Contagem de itens calculada dentro da sessão para evitar DetachedInstanceError
        n_itens_map: dict[int, int] = {
            orc_h.id: session.query(ItemOrcamento)
                             .filter(ItemOrcamento.orcamento_id == orc_h.id)
                             .count()
            for orc_h in historico
        }

    if not historico:
        empty_state(
            "📂",
            "Sem orçamentos para este período",
            "Crie o primeiro orçamento na aba Painel.",
        )
        st.stop()

    section_title(f"Orçamentos — {_periodo_label}")

    _STATUS_PT_HIST = {
        "RASCUNHO": "Rascunho", "EM_COTACAO": "Em cotação",
        "PRONTO_PARA_APROVACAO": "Pronto", "ENVIADO_APROVACAO": "Aguard. aprovação",
        "APROVADO": "Aprovado", "APROVADO_PARCIAL": "Aprovado parcial",
        "REVISAR": "Revisão solicitada", "DEVOLVIDO_REVISAO": "Devolvido",
        "REPROVADO": "Reprovado", "CANCELADO": "Cancelado",
    }

    for orc_h in historico:
        _h_status_label = _STATUS_PT_HIST.get(orc_h.status, orc_h.status)
        if orc_h.status == "CANCELADO":
            _proxima_versao = next(
                (h.versao for h in historico if h.numero == orc_h.numero and h.versao > orc_h.versao),
                None,
            )
            if _proxima_versao:
                _h_status_label = f"Substituído (v{_proxima_versao})"
        with st.expander(
            f"{orc_h.numero}  ·  v{orc_h.versao}  ·  "
            f"{_h_status_label}"
            f"  ·  Responsável: {orc_h.responsavel}",
            expanded=(orc_h.versao == historico[0].versao),
        ):
            col_inf, col_dl, col_del = st.columns([3, 1, 1])
            with col_inf:
                st.markdown(
                    f"**Criado em:** {orc_h.criado_em.strftime('%d/%m/%Y %H:%M')}  \n"
                    f"**Itens:** {n_itens_map.get(orc_h.id, 0)}"
                    + (f"  \n**Enviado em:** {orc_h.enviado_em.strftime('%d/%m/%Y %H:%M')}" if orc_h.enviado_em else "")
                    + (f"  \n**Decidido em:** {orc_h.decidido_em.strftime('%d/%m/%Y %H:%M')}" if orc_h.decidido_em else "")
                    + (f"  \n**Obs diretor:** {orc_h.observacao_diretor}" if orc_h.observacao_diretor else ""),
                )
            with col_dl:
                try:
                    _docx_bytes, _docx_name = _bytes_docx_orcamento(orc_h.id)
                    st.download_button(
                        "Baixar Orçamento (DOCX)",
                        data=_docx_bytes,
                        file_name=_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key=f"dl_{orc_h.id}",
                    )
                except Exception as _e:
                    st.error(f"Erro ao gerar documento: {_e}", icon="⚠️")
            with col_del:
                if st.button("Excluir Orçamento", key=f"del_orc_{orc_h.id}", use_container_width=True):
                    st.session_state[f"confirm_del_{orc_h.id}"] = True
                if st.session_state.get(f"confirm_del_{orc_h.id}"):
                    st.error("Exclusão permanente. Confirma?", icon="⚠️")
                    if st.button("Sim, excluir", key=f"confirm_yes_{orc_h.id}", type="primary", use_container_width=True):
                        try:
                            with SessionLocal() as _sess:
                                deletar_orcamento(_sess, orc_h.id)
                            st.session_state.pop(f"confirm_del_{orc_h.id}", None)
                            st.success("Orçamento excluído.")
                            st.rerun()
                        except ValueError as _e:
                            st.error(str(_e), icon="⚠️")
                    if st.button("Cancelar", key=f"confirm_no_{orc_h.id}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_{orc_h.id}", None)
                        st.rerun()
