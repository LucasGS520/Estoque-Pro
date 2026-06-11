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

import pandas as pd
import streamlit as st
from sqlalchemy.orm import joinedload

from core import tempo
from core.config import APP_BASE_URL
from core.database import get_session_factory
from core.models import ItemOrcamento, Orcamento
from core.ui import empty_state, fmt_brl, page_header, section_title, setup_page
from services.compras_service import get_periodos_com_consolidacao
from services.orcamento_service import (
    add_cotacao,
    cancelar_orcamento,
    criar_orcamento,
    criar_nova_versao,
    desescolher_cotacao,
    enviar_para_aprovacao,
    escolher_cotacao,
    get_lista_final_para_orcamento,
    get_orcamento_ativo,
    get_orcamentos_periodo,
    get_resumo,
    menor_cotacao,
    remover_cotacao,
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
    "APROVADO_PARCIAL": "Aprovado parcialmente", "DEVOLVIDO_REVISAO": "Devolvido para revisão",
    "REPROVADO": "Reprovado", "CANCELADO": "Cancelado",
}
_STATUS_ITEM_PT = {
    "SEM_COTACAO": "Sem cotação",
    "COM_COTACAO": "Com cotação",
    "APROVADO_DIRETOR": "Aprovado",
    "REPROVADO_DIRETOR": "Reprovado",
}
_STATUS_BADGE: dict[str, tuple[str, str]] = {
    "RASCUNHO":               ("#F4F4F5", "#737373"),
    "EM_COTACAO":             ("#DBEAFE", "#2563EB"),
    "PRONTO_PARA_APROVACAO":  ("#DCFCE7", "#16A34A"),
    "ENVIADO_APROVACAO":      ("#FEF3C7", "#B45309"),
    "APROVADO":               ("#DCFCE7", "#16A34A"),
    "APROVADO_PARCIAL":       ("#DCFCE7", "#16A34A"),
    "DEVOLVIDO_REVISAO":      ("#FEE2E2", "#DC2626"),
    "REPROVADO":              ("#FEE2E2", "#DC2626"),
    "CANCELADO":              ("#F4F4F5", "#737373"),
}


# ===========================================================================
# ABA PAINEL
# ===========================================================================
if tab_sel == "Painel":
    with SessionLocal() as session:
        orc = get_orcamento_ativo(session, periodo)
        lista_final = get_lista_final_para_orcamento(session, periodo)
        n_lista = len(lista_final["itens_estoque"]) + len(lista_final["itens_avulsos"])

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

        with SessionLocal() as session:
            resumo = get_resumo(session, orc)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de itens", resumo.total_itens)
        c2.metric("Com cotação escolhida", resumo.com_escolha)
        c3.metric("Sem cotação", resumo.sem_cotacao)
        c4.metric("Total estimado", fmt_brl(resumo.total_geral))

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        # ── Tabela de itens (read-only) ──────────────────────────────────────
        section_title("Itens do Orçamento")

        with SessionLocal() as session:
            itens_orc = (
                session.query(ItemOrcamento)
                .options(joinedload(ItemOrcamento.cotacoes))
                .filter(ItemOrcamento.orcamento_id == orc.id)
                .order_by(ItemOrcamento.categoria_nome, ItemOrcamento.nome_item)
                .all()
            )
            rows_tabela = []
            for item in itens_orc:
                cot_esc = next((c for c in item.cotacoes if c.id == item.cotacao_escolhida_id), None)
                cot_menor = menor_cotacao(item)
                rows_tabela.append({
                    "Item": item.nome_item,
                    "Categoria": item.categoria_nome,
                    "Qtd": item.quantidade_orcada,
                    "Tipo": "Avulsa" if item.tipo == "AVULSA" else "Estoque",
                    "Cotações": len(item.cotacoes),
                    "Melhor valor": fmt_brl(cot_menor.total_calculado) if cot_menor else "—",
                    "Escolhida": cot_esc.origem if cot_esc else "—",
                    "Status": _STATUS_ITEM_PT.get(item.status_item, item.status_item),
                })

        if rows_tabela:
            st.dataframe(
                pd.DataFrame(rows_tabela),
                use_container_width=True,
                hide_index=True,
            )

        is_bloqueado = orc.status in {"ENVIADO_APROVACAO", "APROVADO", "APROVADO_PARCIAL", "REPROVADO"}

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

        # Link para o diretor
        if orc.status == "ENVIADO_APROVACAO":
            link_aprov = f"{APP_BASE_URL}/Aprovacao_Orcamento?id={orc.id}"
            st.info(
                f"Orçamento aguardando aprovação. Envie o link ao diretor:  \n**{link_aprov}**",
                icon="🔗",
            )

        # Criar nova versão após devolução
        if orc.status == "DEVOLVIDO_REVISAO":
            if st.button(
                f"Criar nova versão (v{orc.versao + 1})",
                type="primary",
                key="btn_nova_versao",
            ):
                try:
                    with SessionLocal() as session:
                        nova = criar_nova_versao(session, orc.id)
                    st.success(f"Nova versão criada: **{nova.numero} v{nova.versao}**.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e), icon="⚠️")


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
            _opcoes_cot: dict[str, int] = {
                f"{i.nome_item} ({i.categoria_nome})": i.id
                for i in itens_cot
            }
            _orc_status = orc.status
            _orc_id = orc.id
        else:
            _opcoes_cot = {}
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

    is_bloqueado = _orc_status in {"ENVIADO_APROVACAO", "APROVADO", "APROVADO_PARCIAL", "REPROVADO"}

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

    # ── Carrega item e cotações ──────────────────────────────────────────────
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
        item_cotacao_escolhida_id = item.cotacao_escolhida_id if item else None

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

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Cotações registradas ─────────────────────────────────────────────────
    if cotacoes:
        section_title(f"Cotações registradas ({len(cotacoes)})")

        for cot in sorted(cotacoes, key=lambda c: c.total_calculado):
            is_menor = cot_min and cot.id == cot_min.id
            is_escolhida = cot.id == item_cotacao_escolhida_id
            bg_cor = "#f0fdf4" if is_escolhida else ("#fffbeb" if is_menor else "#fafafa")
            badge = ""
            if is_escolhida:
                badge = (
                    " <span style='background:#dcfce7;color:#16a34a;padding:1px 6px;"
                    "border-radius:4px;font-size:11px;font-weight:600;'>ESCOLHIDA</span>"
                )
            elif is_menor:
                badge = (
                    " <span style='background:#fef9c3;color:#854d0e;padding:1px 6px;"
                    "border-radius:4px;font-size:11px;'>menor preço</span>"
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
                col_esc, col_rem = st.columns([2, 1])
                with col_esc:
                    if is_escolhida:
                        if st.button("Remover escolha", key=f"deses_{cot.id}", use_container_width=True):
                            with SessionLocal() as session:
                                desescolher_cotacao(session, item_sel_id)
                            st.rerun()
                    else:
                        if st.button(
                            "Escolher esta cotação",
                            key=f"esc_{cot.id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            with SessionLocal() as session:
                                escolher_cotacao(session, item_sel_id, cot.id)
                            st.rerun()
                with col_rem:
                    if st.button("Remover", key=f"rem_{cot.id}", use_container_width=True):
                        with SessionLocal() as session:
                            remover_cotacao(session, cot.id)
                        st.rerun()

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    else:
        st.info("Nenhuma cotação registrada para este item ainda.", icon="ℹ️")

    # ── Formulário de nova cotação ───────────────────────────────────────────
    # Usa widgets soltos (sem st.form) para que Enter não dispare o salvamento.
    # O formulário é resetado via versão incremental no session_state.
    if not is_bloqueado:
        section_title("Registrar nova cotação")

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

        c1, c2 = st.columns(2)
        with c1:
            origem = st.text_input(
                "Origem / Fornecedor *",
                placeholder="Ex: Mercado Livre, Fornecedor X",
                key=f"cot_origem_{item_sel_id}_{_fv}",
            )
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

        if st.button("Salvar cotação", type="primary", key=f"btn_salvar_cot_{item_sel_id}_{_fv}"):
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
                        )
                    # Incrementa versão do formulário → limpa todos os campos no rerun
                    st.session_state[f"cot_fv_{item_sel_id}"] = _fv + 1
                    st.success("Cotação salva.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e), icon="⚠️")


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
        "DEVOLVIDO_REVISAO": "Devolvido", "REPROVADO": "Reprovado", "CANCELADO": "Cancelado",
    }

    for orc_h in historico:
        with st.expander(
            f"{orc_h.numero}  ·  v{orc_h.versao}  ·  "
            f"{_STATUS_PT_HIST.get(orc_h.status, orc_h.status)}"
            f"  ·  Responsável: {orc_h.responsavel}",
            expanded=(orc_h.versao == historico[0].versao),
        ):
            col_inf, col_btn = st.columns([3, 1])
            with col_inf:
                st.markdown(
                    f"**Criado em:** {orc_h.criado_em.strftime('%d/%m/%Y %H:%M')}  \n"
                    f"**Itens:** {n_itens_map.get(orc_h.id, 0)}"
                    + (f"  \n**Enviado em:** {orc_h.enviado_em.strftime('%d/%m/%Y %H:%M')}" if orc_h.enviado_em else "")
                    + (f"  \n**Decidido em:** {orc_h.decidido_em.strftime('%d/%m/%Y %H:%M')}" if orc_h.decidido_em else "")
                    + (f"  \n**Obs diretor:** {orc_h.observacao_diretor}" if orc_h.observacao_diretor else ""),
                )
            with col_btn:
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
