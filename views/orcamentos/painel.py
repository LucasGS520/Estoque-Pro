"""Aba Painel — página Orçamentos."""
import datetime
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from sqlalchemy.orm import joinedload

from core.config import APP_BASE_URL
from data.database import get_session_factory
from data.models import ItemOrcamento, Orcamento
from core.ui import empty_state, fmt_brl, section_title
from services.orcamento_service import (
    cancelar_orcamento,
    criar_nova_versao,
    criar_orcamento,
    enviar_para_aprovacao,
    gerar_mensagem_aprovacao,
    get_itens_aprovados,
    get_lista_final_para_orcamento,
    get_orcamento_ativo,
    get_resumo,
    menor_cotacao,
    sincronizar_com_lista_final,
)
from views.orcamentos.historico import _bytes_docx_orcamento

_STATUS_PT: dict[str, str] = {
    "RASCUNHO": "Rascunho", "EM_COTACAO": "Em cotação",
    "PRONTO_PARA_APROVACAO": "Pronto para aprovação",
    "ENVIADO_APROVACAO": "Aguardando aprovação", "APROVADO": "Aprovado",
    "APROVADO_PARCIAL": "Aprovado parcialmente", "REVISAR": "Revisão solicitada",
    "DEVOLVIDO_REVISAO": "Devolvido para revisão",
    "REPROVADO": "Reprovado", "CANCELADO": "Cancelado",
}
_STATUS_ITEM_PT: dict[str, str] = {
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


@st.dialog("Orçamento aprovado — Resumo para Compra", width="large")
def _dialog_resumo_compra(orc_enc: Orcamento) -> None:
    """Exibe resumo de compra agrupado por fornecedor para o orçamento aprovado."""
    SessionLocal = get_session_factory()
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


def render(periodo: datetime.date, periodo_label: str) -> None:
    """Renderiza a aba Painel."""
    SessionLocal = get_session_factory()

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

    if n_lista == 0:
        empty_state(
            "📋",
            "Sem Lista Final aprovada",
            "Aprove itens na aba Lista Final da camada de Compras para poder gerar o orçamento.",
        )
        st.stop()

    # ── Sem orçamento ativo — formulário de criação ─────────────────────────
    if orc is None:
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
            f"**Lista Final disponível — {periodo_label}**  \n"
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
        return

    # ── Orçamento ativo — painel de gestão ───────────────────────────────────
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

    def _btn_nova_versao():
        if st.button(f"Criar novo orçamento (v{orc.versao + 1})", type="primary", key="btn_nova_versao"):
            try:
                with SessionLocal() as _s:
                    nova = criar_nova_versao(_s, orc.id)
                st.success(f"Nova versão criada: **{nova.numero} v{nova.versao}**.")
                st.rerun()
            except ValueError as e:
                st.error(str(e), icon="⚠️")

    if orc.status == "REVISAR":
        _n_revisao    = sum(1 for i in itens_orc if i.status_item == "REVISAO_DIRETOR")
        _n_aprovados  = sum(1 for i in itens_orc if i.status_item == "APROVADO_DIRETOR")
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
        _detalhe = (
            "_O orçamento foi devolvido integralmente pelo diretor. Itens aprovados estão bloqueados com suas cotações; os demais precisam de novas cotações._"
            if _is_devolvido else
            "_Itens com status 'Sem cotação' precisam de novas cotações. Itens aprovados estão bloqueados com as cotações anteriores._"
        )
        st.info(f"↩️ {_ctx}  \n{_detalhe}")
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # ── Métricas ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de itens", resumo.total_itens)
    c2.metric("Com cotação escolhida", resumo.com_escolha)
    c3.metric("Sem cotação", resumo.sem_cotacao)
    c4.metric("Total estimado", fmt_brl(resumo.total_geral))
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    section_title("Itens do Orçamento")
    if rows_tabela:
        st.dataframe(pd.DataFrame(rows_tabela), use_container_width=True, hide_index=True)
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── Ações globais ─────────────────────────────────────────────────────────
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
        _link_aprov = f"{APP_BASE_URL}/Aprovacao_Orcamento?token={orc.token_aprovacao}"
        _msg_aprov = gerar_mensagem_aprovacao(orc, periodo_label, _link_aprov)
        _wame_aprov = f"https://wa.me/?text={quote_plus(_msg_aprov)}"
        st.info(
            "Orçamento aguardando aprovação. Compartilhe o link com o responsável pela decisão.",
            icon="🔗",
        )
        st.link_button("Enviar via WhatsApp", _wame_aprov, use_container_width=False)
        st.caption("Link da Aprovação de Orçamento:")
        st.code(_link_aprov, language=None)
