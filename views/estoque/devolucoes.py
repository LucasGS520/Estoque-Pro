"""Aba Devoluções — página Estoque."""
import pandas as pd
import streamlit as st

from data.database import get_session_factory
from core.ui import section_title
from services import estoque_service
from services.estoque_service import descartar_devolucao, get_devolucoes, registrar_devolucao, reintegrar_devolucao


def render() -> None:
    """Renderiza a aba Devoluções."""
    SessionLocal = get_session_factory()
    _dev_v = st.session_state.get("_dev_v", 0)

    with SessionLocal() as session:
        categorias_dev = estoque_service.get_categorias(session)
        setores_dev = estoque_service.get_setores(session)
        pendentes = get_devolucoes(session, status="pendente")

    cat_opcoes_dev = {c.nome: c.id for c in categorias_dev}
    setor_opcoes_dev = {s.nome: s.id for s in setores_dev}

    section_title("Selecionar item de Devolução")

    if not cat_opcoes_dev:
        st.info("Nenhuma categoria cadastrada. Cadastre categorias na aba Editar antes de registrar devoluções.")
    else:
        cat_dev = st.selectbox(
            "Categoria", list(cat_opcoes_dev.keys()),
            index=None, placeholder="Selecione uma categoria de devolução...",
            key=f"dev_cat_{_dev_v}",
        )

        if cat_dev is None:
            st.info("Selecione uma categoria para continuar.")
        else:
            with SessionLocal() as session:
                itens_dev = estoque_service.get_all_itens(session, categoria_id=cat_opcoes_dev[cat_dev])
            item_opcoes_dev = {i.nome: i.id for i in itens_dev}
            item_estoque_dev = {i.id: (i.estoque_atual, i.unidade) for i in itens_dev}

            if not item_opcoes_dev:
                st.info("Nenhum item cadastrado nesta categoria.")
            else:
                item_dev_sel = st.selectbox(
                    "Item", list(item_opcoes_dev.keys()),
                    index=None, placeholder="Selecione um item para devolver...",
                    key=f"dev_item_{_dev_v}",
                )

                if item_dev_sel is None:
                    st.info("Selecione um item para continuar.")
                else:
                    item_dev_id = item_opcoes_dev[item_dev_sel]
                    estoque_dev, unidade_dev = item_estoque_dev.get(item_dev_id, (0, "un"))
                    st.info(f"Estoque atual: **{estoque_dev} {unidade_dev}**")

                    section_title("Dados da devolução")
                    qtd_dev = st.number_input("Quantidade", min_value=1, value=1, key=f"dev_qtd_{_dev_v}")

                    if not setor_opcoes_dev:
                        st.warning("Nenhum setor cadastrado. Cadastre um setor na aba Editar > Setores antes de registrar devoluções.")
                    else:
                        setor_dev_sel = st.selectbox(
                            "Setor que devolveu *", list(setor_opcoes_dev.keys()), key=f"dev_setor_{_dev_v}"
                        )
                        setor_dev_id = setor_opcoes_dev[setor_dev_sel]

                    motivo_dev = st.text_input("Motivo (opcional)", key=f"dev_motivo_{_dev_v}")

                    if st.button("Registrar devolução", key="btn_registrar_dev", type="primary", use_container_width=True):
                        if not setor_opcoes_dev:
                            st.error("Cadastre e selecione um setor para registrar uma devolução.")
                        else:
                            try:
                                with st.spinner("Registrando..."):
                                    with SessionLocal() as session:
                                        registrar_devolucao(
                                            session,
                                            item_id=item_dev_id,
                                            quantidade=int(qtd_dev),
                                            setor_id=setor_dev_id,
                                            motivo=motivo_dev or None,
                                        )
                                st.session_state["_dev_v"] = _dev_v + 1
                                st.session_state["_fb"] = (
                                    "success",
                                    f"Devolução de **{item_dev_sel}** registrada e aguardando processamento.",
                                )
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

    # ── Tabela de devoluções pendentes (sempre visível) ───────────────────────
    st.divider()
    section_title(f"Itens Devolvidos — {len(pendentes)} pendente(s)")

    if not pendentes:
        st.info("Nenhuma devolução pendente no momento.")
    else:
        df_pendentes = pd.DataFrame([
            {
                "Categoria": dev.item.categoria.nome if (dev.item and dev.item.categoria) else "-",
                "Item": dev.item.nome if dev.item else "(item removido)",
                "Und.": dev.item.unidade if dev.item else "-",
                "Qtd. Devolvida": dev.quantidade,
                "Setor": dev.setor.nome if dev.setor else "-",
                "Data": dev.criado_em.strftime("%d/%m/%Y %H:%M") if dev.criado_em else "-",
                "Motivo": dev.motivo or "-",
            }
            for dev in pendentes
        ])
        st.dataframe(df_pendentes, use_container_width=True, hide_index=True)

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        section_title("Processar Devolução")

        opcoes_proc = {
            f"{d.item.nome if d.item else '(item removido)'} — {d.quantidade} {d.item.unidade if d.item else '?'} ({d.setor.nome if d.setor else '-'})": d.id
            for d in pendentes
        }
        sel_proc = st.selectbox(
            "Selecionar devolução para processar",
            list(opcoes_proc.keys()),
            index=None,
            placeholder="Escolha uma devolução...",
            key="dev_sel_proc",
        )

        col_reint, col_desc = st.columns(2)
        with col_reint:
            if st.button(
                "Reintegrar ao Estoque",
                disabled=not sel_proc,
                use_container_width=True,
                type="primary",
                key="btn_reintegrar",
            ):
                try:
                    with st.spinner("Reintegrando..."):
                        with SessionLocal() as session:
                            reintegrar_devolucao(session, devolucao_id=opcoes_proc[sel_proc])
                    st.session_state["_fb"] = ("success", "Item reintegrado ao estoque com entrada registrada.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        with col_desc:
            if st.button(
                "Descartar",
                disabled=not sel_proc,
                use_container_width=True,
                key="btn_descartar_dev",
            ):
                try:
                    with st.spinner("Descartando..."):
                        with SessionLocal() as session:
                            descartar_devolucao(session, devolucao_id=opcoes_proc[sel_proc])
                    st.session_state["_fb"] = ("success", "Devolução descartada — item não retorna ao estoque.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
