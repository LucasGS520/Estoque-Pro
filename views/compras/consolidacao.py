"""Aba Consolidação — página Compras."""
import datetime

import pandas as pd
import streamlit as st

from core import tempo
from core.database import get_session_factory
from core.ui import empty_state, section_title
from documents.lista_compras import gerar_lista_compras
from services import notificacao_service
from services.ciclo_service import enviar_feedbacks_aprovacao, get_ciclo_por_periodo
from services.compras_service import (
    aprovar_item,
    atualizar_compra_avulsa,
    get_compras_avulsas_periodo,
    get_consolidacao_periodo,
    get_lista_final,
    listar_solicitacoes,
    remover_da_lista,
    resetar_quantidades_consolidacao,
)

_STATUS_LABEL = {
    "zerado":              "Zerado",
    "abaixo_minimo":       "Abaixo do Mínimo",
    "abaixo_ideal":        "Abaixo do Ideal",
    "ok":                  "OK",
    "sem_parametro":       "Sem Parâmetro",
    "comprar":             "Abaixo do Mínimo",
    "sem_minimo_definido": "Sem Parâmetro",
    "excesso":             "OK",
}


def render(
    periodo: datetime.date,
    periodo_label: str,
    periodo_tipo: str,
    itens_lista: list,
    avulsas_lista: list,
) -> None:
    """Renderiza a aba Consolidação."""
    SessionLocal = get_session_factory()

    with SessionLocal() as _cs_conso_ciclo:
        _ciclo_conso = get_ciclo_por_periodo(_cs_conso_ciclo, periodo)
        _ciclo_id = _ciclo_conso.id if _ciclo_conso else None

    if periodo_tipo == "futuro":
        empty_state(
            "🚫",
            "Período futuro",
            "Não é possível analisar ou visualizar consolidações de períodos futuros. "
            "Selecione o mês atual.",
        )
        st.stop()

    _consolidacao_readonly = (periodo_tipo == "passado")
    if _consolidacao_readonly:
        st.info("🔒 Período encerrado — visualização somente leitura.", icon="🔒")

    with SessionLocal() as _s_conso:
        _sols_conso = listar_solicitacoes(_s_conso, periodo)
    _n_sols_pendentes = sum(
        1 for s in _sols_conso if s.status in {
            "novo_item", "sem_parametros",
            "pendente_cadastro", "pendente_parametrizacao",
        }
    )

    # ── Tabela de consolidação ────────────────────────────────────────────────
    if not itens_lista:
        empty_state(
            "🔗",
            "Sem análise para este período",
            "Clique em 'Análise Mensal de Compras' para cruzar estoque e solicitações.",
        )
    else:
        para_compra     = [x for x in itens_lista if (x.quantidade_sugerida or 0) > 0]
        sem_param_conso = [x for x in itens_lista if x.status in {"sem_parametro", "sem_minimo_definido"}]
        avulsas_periodo = avulsas_lista

        if para_compra or avulsas_periodo:
            section_title("Itens para Decisão de Compra")
            _avisos_conso = []
            if sem_param_conso:
                _avisos_conso.append(f"{len(sem_param_conso)} item(ns) sem parâmetros")
            if _n_sols_pendentes:
                _avisos_conso.append(f"{_n_sols_pendentes} solicitação(ões) pendente(s)")
            if _avisos_conso:
                st.caption(
                    f"⚠️ {' · '.join(_avisos_conso)} — "
                    f"resolva em **Editar** ou **Solicitações e Pendências** e rode novamente a análise."
                )
            st.caption(
                "Edite 'Qtd Final' para compra, quando necessário. "
                "Marque 'Incluir na Lista' e clique em Salvar para aprovar."
                "O campo 'Motivo do Sistema' explica o raciocínio por trás da quantidade sugerida. "
            )

            rows_ed = []
            for x in para_compra:
                rows_ed.append({
                    "_id":  x.id,
                    "_tipo": "lista",
                    "Status": _STATUS_LABEL.get(x.status, x.status),
                    "Item": x.item.nome if x.item else "—",
                    "Estoque": x.estoque_atual_snap,
                    "Mín.": x.estoque_minimo_snap,
                    "Ideal": x.estoque_ideal_snap,
                    "Solicitado": x.total_solicitado,
                    "Qtd Sugerida": x.quantidade_sugerida,
                    "Qtd Final": (
                        x.quantidade_final_definida
                        if x.quantidade_final_definida is not None
                        else x.quantidade_sugerida
                    ),
                    "Incluir na Lista": x.incluir_na_lista_final,
                    "Motivo do Sistema": x.motivo_sugestao or "—",
                })
            for ca in avulsas_periodo:
                _motivo_av = (
                    f"Compra pontual aprovada"
                    f"{' · Urgente' if ca.urgente else ''}"
                    f" · Solicitante: {ca.solicitante}"
                )
                rows_ed.append({
                    "_id":  ca.id,
                    "_tipo": "avulsa",
                    "Status": "Compra Avulsa",
                    "Item": ca.nome_item,
                    "Estoque": float("nan"),
                    "Mín.": float("nan"),
                    "Ideal": float("nan"),
                    "Solicitado": ca.quantidade,
                    "Qtd Sugerida": float("nan"),
                    "Qtd Final": ca.quantidade,
                    "Incluir na Lista": ca.incluir_na_lista_final,
                    "Motivo do Sistema": _motivo_av,
                })

            _col_order = [
                "_id", "Status", "Item", "Estoque", "Mín.", "Ideal",
                "Solicitado", "Qtd Sugerida", "Qtd Final", "Incluir na Lista", "Motivo do Sistema",
            ]
            df_ed = pd.DataFrame(rows_ed)
            col_config = {
                "_id":              st.column_config.NumberColumn("ID", disabled=True),
                "_tipo":            None,
                "Status":           st.column_config.TextColumn("Status", disabled=True),
                "Item":             st.column_config.TextColumn("Item", disabled=True),
                "Estoque":          st.column_config.NumberColumn("Estoque", disabled=True),
                "Mín.":             st.column_config.NumberColumn("Mín.", disabled=True),
                "Ideal":            st.column_config.NumberColumn("Ideal", disabled=True),
                "Solicitado":       st.column_config.NumberColumn("Solicitado", disabled=True),
                "Qtd Sugerida":     st.column_config.NumberColumn("Qtd Sugerida", disabled=True),
                "Qtd Final":        st.column_config.NumberColumn(
                    "Qtd Final", min_value=1, step=1, required=True,
                    help="Quantidade a comprar — obrigatória e maior que zero.",
                ),
                "Incluir na Lista": st.column_config.CheckboxColumn("Incluir na Lista"),
                "Motivo do Sistema": st.column_config.TextColumn("Motivo do Sistema", disabled=True, width="large"),
            }
            _tem_qtd_manual = any(x.quantidade_final_definida is not None for x in itens_lista)

            if _consolidacao_readonly:
                st.dataframe(
                    df_ed,
                    column_config=col_config,
                    column_order=_col_order,
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                _col_btn1, _col_btn2, _col_btn3, _ = st.columns([1, 1.2, 1.5, 7.6])
                with _col_btn1:
                    if st.button("☑ Marcar Todos", key="btn_sel_tudo"):
                        st.session_state["consolidacao_sel_tudo"] = True
                with _col_btn2:
                    if st.button("☐ Desmarcar Todos", key="btn_limpar_sel"):
                        st.session_state["consolidacao_sel_tudo"] = False
                with _col_btn3:
                    if st.button(
                        "↺ Resetar Qtd",
                        key="btn_resetar_qtd",
                        disabled=not _tem_qtd_manual,
                        help="Reverte todas as Qtd Final editadas manualmente para a Qtd Sugerida.",
                    ):
                        st.session_state["consolidacao_confirmar_reset"] = True

                _sel_override = st.session_state.get("consolidacao_sel_tudo")
                if _sel_override is not None:
                    df_ed["Incluir na Lista"] = _sel_override

                edited_df = st.data_editor(
                    df_ed,
                    column_config=col_config,
                    column_order=_col_order,
                    hide_index=True,
                    use_container_width=True,
                    key="consolidacao_editor",
                )

                if st.session_state.get("consolidacao_confirmar_reset"):
                    st.warning(
                        "⚠️ Isso irá reverter **todas as Qtd Final editadas** para a Qtd Sugerida "
                        "e remover os itens da Lista Final. Confirma?",
                    )
                    _col_conf, _col_canc, _ = st.columns([1, 1, 8])
                    with _col_conf:
                        if st.button("Confirmar", type="primary", key="btn_confirmar_reset"):
                            with SessionLocal() as _s_reset:
                                _n_reset = resetar_quantidades_consolidacao(_s_reset, periodo)
                            st.session_state.pop("consolidacao_confirmar_reset", None)
                            st.session_state.pop("consolidacao_sel_tudo", None)
                            st.success(f"{_n_reset} item(ns) resetado(s) para a quantidade sugerida.")
                            st.rerun()
                    with _col_canc:
                        if st.button("Cancelar", key="btn_cancelar_reset"):
                            st.session_state.pop("consolidacao_confirmar_reset", None)
                            st.rerun()

            if not _consolidacao_readonly and st.button("Salvar Alterações", type="primary", key="salvar_consolidacao"):
                _itens_invalidos = []
                for _, row in edited_df.iterrows():
                    _qtd_invalida = pd.isna(row["Qtd Final"]) or int(row["Qtd Final"]) < 1
                    _exige_qtd = row["_tipo"] == "avulsa" or bool(row["Incluir na Lista"])
                    if _exige_qtd and _qtd_invalida:
                        _itens_invalidos.append(str(row["Item"]))
                if _itens_invalidos:
                    st.error(
                        f"**Nada foi salvo.** Corrija a Qtd Final de: {', '.join(_itens_invalidos)} — "
                        f"o valor é obrigatório e deve ser um número inteiro maior que zero."
                    )
                else:
                    try:
                        with SessionLocal() as _s:
                            ids_na_tabela = {int(r["_id"]) for _, r in edited_df.iterrows() if r["_tipo"] == "lista"}
                            for x in get_consolidacao_periodo(_s, periodo):
                                if x.id not in ids_na_tabela and x.incluir_na_lista_final:
                                    remover_da_lista(_s, x.id)
                            for _, row in edited_df.iterrows():
                                item_id   = int(row["_id"])
                                qtd_final = int(row["Qtd Final"]) if pd.notna(row["Qtd Final"]) else None
                                incluir   = bool(row["Incluir na Lista"])
                                if row["_tipo"] == "avulsa":
                                    atualizar_compra_avulsa(_s, item_id, quantidade=qtd_final, incluir_na_lista_final=incluir)
                                else:
                                    if incluir:
                                        aprovar_item(_s, item_id, qtd_final, None)
                                    else:
                                        remover_da_lista(_s, item_id)
                    except ValueError as _exc_salvar:
                        st.error(f"Não foi possível salvar: {_exc_salvar}")
                    else:
                        st.success("Alterações salvas com sucesso.")
                        st.session_state.pop("consolidacao_sel_tudo", None)
                        st.rerun()

        else:
            if sem_param_conso:
                st.warning(
                    f"**{len(sem_param_conso)} item(ns) sem parâmetros definidos** — o motor não pôde "
                    f"analisar a necessidade de compra destes itens.  \n"
                    f"Configure mínimo/ideal em **Estoque** e rode novamente a **Análise Mensal de Compras**.",
                    icon="⚠️",
                )
            elif _n_sols_pendentes:
                st.warning(
                    f"Estoque adequado para os itens analisados, mas há "
                    f"**{_n_sols_pendentes} solicitação(ões) pendente(s)** que não puderam ser processadas.  \n"
                    f"Resolva as pendências na aba **Solicitações e Pendências** e rode novamente "
                    f"a **Análise Mensal de Compras** para incluí-las.",
                    icon="⚠️",
                )
            else:
                empty_state("✅", "Todos os itens estão com estoque adequado para o período.")

    # ── Lista Final Aprovada ──────────────────────────────────────────────────
    st.divider()
    section_title("Lista Final Aprovada")

    with SessionLocal() as _s:
        lista_final   = get_lista_final(_s, periodo)
        avulsas_final = get_compras_avulsas_periodo(_s, periodo)
        lista_final_info = [
            {
                "item_nome":    x.item.nome if x.item else "—",
                "categoria":    x.item.categoria.nome if x.item and x.item.categoria else "—",
                "tipo":         "Estoque",
                "estoque_atual": x.estoque_atual_snap,
                "qtd_compra":   x.quantidade_final_definida or x.quantidade_sugerida,
            }
            for x in lista_final
        ] + [
            {
                "item_nome":    ca.nome_item,
                "categoria":    "—",
                "tipo":         "Compra Avulsa",
                "estoque_atual": None,
                "qtd_compra":   ca.quantidade,
            }
            for ca in avulsas_final
        ]

    if not lista_final_info:
        empty_state(
            "✅",
            "Lista final vazia",
            "Aprove itens acima marcando 'Incluir na Lista' e salvando.",
        )
    else:
        st.markdown(f"**{len(lista_final_info)} item(ns) aprovado(s) para orçamento — {periodo_label}**")
        rows_final = [
            {
                "Item":          info["item_nome"],
                "Categoria":     info["categoria"],
                "Tipo":          info["tipo"],
                "Estoque Atual": info["estoque_atual"],
                "Qtd Compra":    info["qtd_compra"],
            }
            for info in lista_final_info
        ]
        st.dataframe(pd.DataFrame(rows_final), use_container_width=True, hide_index=True)

        df_docx = pd.DataFrame([
            {
                "Item":          i["item_nome"],
                "Categoria":     i["categoria"],
                "Tipo":          i["tipo"],
                "Estoque Atual": i["estoque_atual"],
                "Qtd Compra":    i["qtd_compra"],
            }
            for i in lista_final_info
        ])
        caminho_docx = gerar_lista_compras(
            df_docx,
            periodo=periodo_label,
            data_geracao=tempo.hoje().strftime("%d/%m/%Y"),
        )
        with open(caminho_docx, "rb") as f:
            docx_bytes = f.read()
        st.download_button(
            "Baixar Lista de Compras (DOCX)",
            data=docx_bytes,
            file_name=f"lista_compras_{periodo_label}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_lista_final",
        )

        # ── Feedback de aprovação para os setores ─────────────────────────────
        if notificacao_service.credenciais_configuradas() and _ciclo_id:
            st.divider()
            section_title("Feedback aos Setores")
            st.caption(
                "Notifica cada setor via WhatsApp com o resumo dos itens aprovados e rejeitados do pedido."
            )

            with SessionLocal() as _sfb:
                _todas_fb = listar_solicitacoes(_sfb, periodo)
                _feedbacks: dict[int, dict] = {}
                for _sol in _todas_fb:
                    if _sol.setor_id is None or _sol.item_id is None:
                        continue
                    nome_item = _sol.item.nome if _sol.item else "—"
                    _entry = _feedbacks.setdefault(_sol.setor_id, {"aprovados": [], "rejeitados": []})
                    if _sol.status == "aprovada":
                        _entry["aprovados"].append(nome_item)
                    elif _sol.status == "rejeitada":
                        _entry["rejeitados"].append(nome_item)

            if _feedbacks:
                if st.button(
                    "📲 Enviar feedback aos setores",
                    key="btn_enviar_feedback",
                    type="primary",
                    help="Envia WhatsApp para cada setor com resumo dos itens aprovados e rejeitados.",
                ):
                    with SessionLocal() as _sfb2:
                        _res_fb = enviar_feedbacks_aprovacao(_sfb2, _ciclo_id, _feedbacks)
                    st.success(
                        f"Feedback enviado: ✅ {_res_fb['enviados']} setor(es) · "
                        f"❌ {_res_fb['falhas_api']} falhas · "
                        f"⚠️ {_res_fb['sem_whatsapp']} sem WhatsApp"
                    )
            else:
                st.caption("Nenhuma solicitação aprovada ou rejeitada encontrada para este período.")
