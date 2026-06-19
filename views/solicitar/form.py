"""Formulário público de solicitação de materiais — página Solicitar."""
import base64
import datetime

import streamlit as st

from core import tempo
from data.database import get_session_factory
from core.i18n import MESES_PT
from core.schemas import SolicitacaoMaterialCreate, SolicitacaoPedidoCreate
from core.ui import _CSS, _LOGO, section_title
from services.ciclo_service import get_ciclo_ativo, get_participante_por_token, marcar_setor_respondido
from services.compras_service import criar_pedido_solicitacao, get_pedidos_setor_periodo
from services.estoque_service import get_all_itens, get_setores
import services.push_service as push_service


def _opcoes_periodo() -> list[datetime.date]:
    hoje = tempo.hoje()
    proximo_mes = hoje.month % 12 + 1
    proximo_ano = hoje.year if hoje.month < 12 else hoje.year + 1
    return [
        datetime.date(hoje.year, hoje.month, 1),
        datetime.date(proximo_ano, proximo_mes, 1),
    ]


def _logo_base64() -> str | None:
    if _LOGO.exists():
        with open(_LOGO, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


def _limpar_chaves_item(idx: int) -> None:
    for i in range(idx, len(st.session_state.get("sol_itens", [])) + 1):
        for prefix in ("qtd_", "obs_", "urg_"):
            st.session_state.pop(f"{prefix}{i}", None)


def _exibir_link_invalido() -> None:
    st.markdown(
        "<div style='text-align:center;padding:48px 24px;'>"
        "<div style='font-size:48px;margin-bottom:16px;'>🔗</div>"
        "<h3 style='color:#111827;margin:0 0 8px;'>Link inválido</h3>"
        "<p style='color:#737373;font-size:15px;margin:0;'>Este link não é válido ou já expirou. "
        "Solicite um novo link ao responsável pelo setor de compras.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()


def render() -> None:
    """Renderiza o formulário público de solicitação de materiais."""
    SessionLocal = get_session_factory()

    # CSS global + ocultar sidebar
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        "<style>"
        "[data-testid='stSidebar']    { display: none !important; }"
        "[data-testid='collapsedControl'] { display: none !important; }"
        "</style>",
        unsafe_allow_html=True,
    )

    # ── Session state ──────────────────────────────────────────────────────────
    if "sol_itens" not in st.session_state:
        st.session_state["sol_itens"] = []
    if "sol_enviada" not in st.session_state:
        st.session_state["sol_enviada"] = False
    if "sol_sem_necessidade" not in st.session_state:
        st.session_state["sol_sem_necessidade"] = False
    if "sol_confirmar_segundo_envio" not in st.session_state:
        st.session_state["sol_confirmar_segundo_envio"] = False

    # ── Catálogo ───────────────────────────────────────────────────────────────
    with SessionLocal() as _s:
        _setores_raw = get_setores(_s)
        _itens_raw = get_all_itens(_s, apenas_ativos=True)
        setores = [(s.id, s.nome) for s in _setores_raw]
        catalogo = [
            {
                "id": i.id,
                "nome": i.nome,
                "categoria": i.categoria.nome,
                "unidade": i.unidade,
            }
            for i in _itens_raw
        ]

    categorias_disponiveis = ["Todas"] + sorted({i["categoria"] for i in catalogo})

    # ── Resolução de identidade ────────────────────────────────────────────────
    _token_param = st.query_params.get("token")

    if _token_param:
        with SessionLocal() as _stk:
            _part = get_participante_por_token(_stk, _token_param)
            if _part is None:
                _exibir_link_invalido()
            _ciclo_status  = _part.ciclo.status
            _ciclo_prazo   = _part.ciclo.prazo_resposta_em
            periodo_sel    = _part.ciclo.periodo_referencia
            _setor_fixo_id = _part.setor_id
            _ciclo_check   = _part.ciclo.id
    else:
        _setor_fixo_id = None
        with SessionLocal() as _stk:
            _ciclo_obj = get_ciclo_ativo(_stk)
            if _ciclo_obj is not None:
                _ciclo_status = _ciclo_obj.status
                _ciclo_prazo  = _ciclo_obj.prazo_resposta_em
                _ciclo_check  = _ciclo_obj.id
                periodo_sel   = _ciclo_obj.periodo_referencia
            else:
                _ciclo_status = None
                _ciclo_prazo  = None
                _ciclo_check  = None
                periodo_sel   = _opcoes_periodo()[0]

    _setor_fixo_nome = next((nome for sid, nome in setores if sid == _setor_fixo_id), None)
    periodo_label_sol = f"{MESES_PT[periodo_sel.month]}/{periodo_sel.year}"

    _agora = tempo.agora()
    _prazo_vencido = _ciclo_prazo is not None and _ciclo_prazo < _agora
    _formulario_bloqueado = _ciclo_status != "aberto" or _prazo_vencido

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    _logo_b64 = _logo_base64()
    _logo_tag = (
        f'<img src="data:image/png;base64,{_logo_b64}" '
        f'style="max-width:170px;max-height:64px;display:block;margin:0 auto;">'
        if _logo_b64
        else '<p style="color:#374151;font-size:26px;font-weight:700;text-align:center;margin:0;">📦 EstoquePro</p>'
    )

    st.markdown(
        f"<div style='background:#111827;border-radius:10px;padding:28px 32px;"
        f"text-align:center;margin-bottom:8px;'>"
        f"{_logo_tag}"
        f"<p style='color:rgba(235,235,235,0.65);font-size:13px;margin:8px 0 0;'>"
        f"</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h2 style='color:#111827;margin:16px 0 4px;'>Solicitação de Materiais</h2>"
        "<p style='color:#737373;font-size:15px;margin:0 0 20px;'>"
        "Preencha os campos abaixo e envie sua solicitação ao setor de compras.</p>",
        unsafe_allow_html=True,
    )

    # ── Gate — formulário bloqueado ────────────────────────────────────────────
    if _formulario_bloqueado:
        if _ciclo_status is None:
            _motivo  = "Nenhum ciclo de solicitações foi aberto para este período."
            _detalhe = f"As coletas de {periodo_label_sol} ainda não foram iniciadas."
        elif _ciclo_status == "encerrado":
            _motivo  = f"O ciclo de solicitações de {periodo_label_sol} foi encerrado."
            _detalhe = "O prazo para envio de solicitações deste período já foi concluído."
        else:
            _motivo  = f"O prazo de resposta do ciclo de {periodo_label_sol} expirou."
            _detalhe = "As solicitações deste período não estão mais sendo aceitas."

        st.markdown(
            f"<div style='text-align:center;padding:48px 24px;'>"
            f"<div style='font-size:48px;margin-bottom:16px;'>🔒</div>"
            f"<h3 style='color:#111827;margin:0 0 8px;'>Formulário indisponível</h3>"
            f"<p style='color:#737373;font-size:15px;margin:0 0 4px;'><strong>{_motivo}</strong></p>"
            f"<p style='color:#9e9e9e;font-size:14px;margin:0;'>{_detalhe}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.stop()

    # ── Gate — segunda submissão via token ─────────────────────────────────────
    _pedidos_anteriores: list = []
    if _setor_fixo_id is not None and _ciclo_check is not None:
        with SessionLocal() as _sp:
            _pedidos_anteriores = get_pedidos_setor_periodo(_sp, _setor_fixo_id, periodo_sel)

    _ja_enviou = len(_pedidos_anteriores) > 0

    if _ja_enviou and not st.session_state["sol_confirmar_segundo_envio"]:
        _ped_ant   = _pedidos_anteriores[-1]
        _data_ant  = _ped_ant.criado_em.strftime("%d/%m/%Y às %H:%M") if _ped_ant.criado_em else "—"
        _n_itens_ant = len(_ped_ant.itens) if _ped_ant.itens else 0
        _envios_txt  = f"{len(_pedidos_anteriores)}º envio" if len(_pedidos_anteriores) > 1 else "1 envio"

        st.warning(
            f"**Você já enviou uma solicitação para {periodo_label_sol}.**  \n"
            f"Último envio em {_data_ant} — {_n_itens_ant} {'item' if _n_itens_ant == 1 else 'itens'} solicitados ({_envios_txt} no total).  \n"
            f"Se precisar adicionar mais itens, um novo formulário será registrado separadamente.",
            icon="⚠️",
        )
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("Enviar mesmo assim", type="primary", use_container_width=True, key="btn_confirmar_segundo"):
                st.session_state["sol_confirmar_segundo_envio"] = True
                st.rerun()
        with _c2:
            if st.button("Cancelar", use_container_width=True, key="btn_cancelar_segundo"):
                st.stop()
        st.stop()

    # ── Telas de confirmação pós-ação ──────────────────────────────────────────
    if st.session_state["sol_sem_necessidade"]:
        st.success(
            f"**Registrado com sucesso.**  \n"
            f"Seu setor foi marcado sem solicitações para {periodo_label_sol}. Você pode fechar esta página."
        )
        st.stop()

    if st.session_state["sol_enviada"]:
        st.success(
            "**Solicitação enviada com sucesso!**  \n"
            "O setor de Compras receberá e processará os itens solicitados. "
            "Você pode fechar esta página ou enviar uma nova solicitação."
        )
        if st.button("Fazer nova solicitação", type="secondary"):
            st.session_state["sol_itens"] = []
            st.session_state["sol_enviada"] = False
            st.rerun()
        st.stop()

    # ── Seção 1 — Identificação ────────────────────────────────────────────────
    st.markdown("### 1. Identificação")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        if _setor_fixo_id is not None:
            st.markdown(
                f"**Setor**  \n"
                f"<span style='font-size:23px;font-weight:600;color:#111827;'>{_setor_fixo_nome}</span>"
                f"<br><span style='font-size:11px;color:#737373;'></span>",
                unsafe_allow_html=True,
            )
            setor_id = _setor_fixo_id
        else:
            setor_opts = {nome: sid for sid, nome in setores}
            setor_nome = st.selectbox(
                "Setor *",
                options=[nome for _, nome in setores],
                index=None,
                placeholder="Selecione o setor responsável...",
                key="sel_setor",
            )
            setor_id = setor_opts.get(setor_nome) if setor_nome else None

    with col2:
        solicitante = st.text_input("Nome do Solicitante *", placeholder="Nome completo", key="inp_solicitante")

    with col3:
        st.markdown(
            f"**Período de referência**  \n"
            f"<span style='font-size:23px;font-weight:600;color:#111827;'>{periodo_label_sol}</span>"
            f"<br><span style='font-size:11px;color:#737373;'></span>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Gate — segunda submissão via selectbox (setor sem URL param)
    if (
        setor_id is not None
        and _setor_fixo_id is None
        and _ciclo_check is not None
        and not st.session_state["sol_confirmar_segundo_envio"]
    ):
        with SessionLocal() as _sp_manual:
            _pedidos_man = get_pedidos_setor_periodo(_sp_manual, setor_id, periodo_sel)
        if _pedidos_man:
            _ped_m   = _pedidos_man[-1]
            _data_m  = _ped_m.criado_em.strftime("%d/%m/%Y às %H:%M") if _ped_m.criado_em else "—"
            _n_m     = len(_ped_m.itens) if _ped_m.itens else 0
            _envios_m = f"{len(_pedidos_man)}º envio" if len(_pedidos_man) > 1 else "1 envio"
            st.warning(
                f"**Você já enviou uma solicitação para {periodo_label_sol}.**  \n"
                f"Último envio em {_data_m} — {_n_m} {'item' if _n_m == 1 else 'itens'} solicitados ({_envios_m} no total).  \n"
                f"Se precisar adicionar mais itens, um novo formulário será registrado separadamente.",
                icon="⚠️",
            )
            _cm1, _cm2 = st.columns(2)
            with _cm1:
                if st.button("Enviar mesmo assim", type="primary", use_container_width=True, key="btn_confirmar_manual"):
                    st.session_state["sol_confirmar_segundo_envio"] = True
                    st.rerun()
            with _cm2:
                if st.button("Cancelar", use_container_width=True, key="btn_cancelar_manual"):
                    st.stop()
            st.stop()

    # ── Seção 2 — Adicionar Itens ──────────────────────────────────────────────
    st.markdown("### 2. Adicionar Itens")
    section_title("Filtros")
    col_busca, col_cat = st.columns([3, 1])

    with col_busca:
        busca = st.text_input(
            "Buscar por nome",
            placeholder="Digite parte do nome...",
            key="sol_busca",
        )
    with col_cat:
        cat_sel = st.selectbox(
            "Filtrar por categoria",
            options=categorias_disponiveis,
            key="sol_cat",
        )

    busca_lower = busca.strip().lower()
    itens_base = catalogo if cat_sel == "Todas" else [i for i in catalogo if i["categoria"] == cat_sel]
    itens_filtrados = (
        [i for i in itens_base if busca_lower in i["nome"].lower()]
        if busca_lower
        else itens_base
    )

    if itens_filtrados:
        n = len(itens_filtrados)
        st.caption(
            f"**{n}** {'item' if n == 1 else 'itens'}"
            + (f" em **{cat_sel}**" if cat_sel != "Todas" else "")
            + (f' — filtrado por "{busca.strip()}"' if busca_lower else "")
        )

        item_label_map = {
            f"{i['nome']}  ({i['categoria']} · {i['unidade']})": i
            for i in itens_filtrados
        }

        item_label_sel = st.selectbox(
            "Selecione o item *",
            options=list(item_label_map.keys()),
            placeholder="Selecione ou comece a digitar para buscar...",
            key="sol_item",
            label_visibility="collapsed",
        )
        item_sel = item_label_map.get(item_label_sel) if item_label_sel else None

        if item_sel:
            col_qtd, col_obs = st.columns([1, 3])
            with col_qtd:
                qtd_item = st.number_input(
                    "Quantidade *",
                    min_value=1,
                    value=1,
                    step=1,
                    key="sol_qtd",
                )
            with col_obs:
                obs_item = st.text_input(
                    "Observação (opcional)",
                    placeholder="Justificativa, urgência, especificação técnica...",
                    key="sol_obs",
                )

            if st.button("＋ Adicionar ao Pedido", type="primary", key="btn_add"):
                ja_existe = any(e["item_id"] == item_sel["id"] for e in st.session_state["sol_itens"])
                if ja_existe:
                    st.warning(
                        f"**{item_sel['nome']}** já foi adicionado. "
                        "Edite a quantidade e observação diretamente na seção de revisão abaixo."
                    )
                else:
                    st.session_state["sol_itens"].append({
                        "tipo": "Existente",
                        "item_id": item_sel["id"],
                        "nome": item_sel["nome"],
                        "categoria": item_sel["categoria"],
                        "unidade": item_sel["unidade"],
                        "quantidade": int(qtd_item),
                        "observacao": obs_item.strip() or None,
                        "urgente": False,
                    })
                    st.rerun()
    else:
        st.info(
            "Nenhum item encontrado com os filtros atuais. "
            "Tente outra categoria ou outro termo de busca. "
            "Se o material não existe no catálogo, use a seção **'Não encontrou o material?'** abaixo."
        )

    st.markdown("")

    # ── Seção 2b — Item novo ───────────────────────────────────────────────────
    st.markdown("#### Não encontrou o material?")
    with st.container(border=True):
        st.caption(
            "Use esta seção quando o material não existir no catálogo. "
            "O setor de Compras avaliará e cadastrará antes de incluir na lista final."
        )

        col_n1, col_n2 = st.columns([3, 1])
        with col_n1:
            nome_novo = st.text_input(
                "Nome do item *",
                placeholder="Descreva com clareza: marca, modelo, medida, especificação...",
                key="inp_novo_nome",
            )
        with col_n2:
            qtd_novo = st.number_input("Quantidade *", min_value=1, value=1, step=1, key="inp_novo_qtd")

        obs_novo = st.text_input(
            "Observação / Justificativa *",
            placeholder="Para que será usado? Há urgência? Referência de onde encontrar?",
            key="inp_novo_obs",
            help="Obrigatório para itens não cadastrados.",
        )

        if st.button("＋ Adicionar ao Pedido", type="primary", key="btn_add_novo"):
            if not nome_novo.strip():
                st.error("Informe o nome do item.")
            elif not obs_novo.strip():
                st.error("A justificativa é obrigatória para itens não cadastrados. Explique para que será usado e se há urgência.")
            else:
                st.session_state["sol_itens"].append({
                    "tipo": "Novo",
                    "item_id": None,
                    "nome": nome_novo.strip(),
                    "categoria": "Item Novo",
                    "unidade": "—",
                    "quantidade": int(qtd_novo),
                    "observacao": obs_novo.strip() or None,
                    "urgente": False,
                })
                st.rerun()

    st.markdown("---")

    # ── Seção 3 — Revisão e Envio ──────────────────────────────────────────────
    st.markdown("### 3. Revisão e Envio")

    itens_lista: list[dict] = st.session_state["sol_itens"]

    if not itens_lista:
        st.markdown(
            "<p style='color:#737373;font-size:14px;'>Nenhum item adicionado ainda. "
            "Use as seções acima para montar sua solicitação.</p>",
            unsafe_allow_html=True,
        )
    else:
        for idx, item in enumerate(itens_lista):
            with st.container(border=True):
                c_info, c_rm = st.columns([11, 1])
                with c_info:
                    if item["tipo"] == "Novo":
                        badge = (
                            "<span style='background:#F59E0B;color:#fff;font-size:11px;"
                            "font-weight:600;padding:2px 8px;border-radius:10px;margin-left:6px;'>Novo Item</span>"
                        )
                    else:
                        badge = (
                            "<span style='background:#3B82F6;color:#fff;font-size:11px;"
                            "font-weight:600;padding:2px 8px;border-radius:10px;margin-left:6px;'>Catálogo</span>"
                        )
                    st.markdown(
                        f"**{item['nome']}**{badge}"
                        f"<span style='color:#a0a0a0;font-size:12px;margin-left:8px;'>"
                        f"{item['categoria']} · {item['unidade']}</span>",
                        unsafe_allow_html=True,
                    )

                    col_qtd, col_obs, col_urg = st.columns([1, 5, 2])
                    with col_qtd:
                        st.number_input(
                            "Quantidade",
                            min_value=1,
                            value=item["quantidade"],
                            step=1,
                            key=f"qtd_{idx}",
                        )
                    with col_obs:
                        st.text_input(
                            "Observação",
                            value=item.get("observacao") or "",
                            placeholder="Justificativa, especificação técnica...",
                            key=f"obs_{idx}",
                        )
                    with col_urg:
                        st.markdown("<div style='padding-top:28px;'>", unsafe_allow_html=True)
                        st.checkbox(
                            "🔴 Urgente",
                            value=item.get("urgente", False),
                            key=f"urg_{idx}",
                            help="Marque se este item tem prioridade de atendimento",
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                with c_rm:
                    st.markdown("<div style='padding-top:28px;'>", unsafe_allow_html=True)
                    if st.button("✕", key=f"rm_{idx}", help="Remover item"):
                        _limpar_chaves_item(idx)
                        st.session_state["sol_itens"].pop(idx)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    identificacao_ok = bool(setor_id and solicitante.strip())
    if not identificacao_ok:
        st.warning("Preencha o **Setor** e o **Nome do Solicitante** na Seção 1 antes de enviar.")

    submitted = st.button(
        f"Enviar Solicitação ({len(itens_lista)} {'item' if len(itens_lista) == 1 else 'itens'})",
        disabled=not identificacao_ok or not itens_lista,
        type="primary",
        use_container_width=True,
        key="btn_enviar",
    )

    # Opção "sem necessidade"
    if setor_id is not None and _ciclo_check is not None:
        with SessionLocal() as _sv:
            _ja_tem_pedido = len(get_pedidos_setor_periodo(_sv, setor_id, periodo_sel)) > 0
        if not _ja_tem_pedido:
            st.markdown(
                "<div style='text-align:center;margin-top:8px;"
                "color:#9e9e9e;font-size:13px;'>ou</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Não tenho materiais a solicitar este mês",
                use_container_width=True,
                key="btn_sem_necessidade",
                help="Registra que seu setor não tem solicitações para este período.",
            ):
                try:
                    with SessionLocal() as _sn:
                        marcar_setor_respondido(_sn, _ciclo_check, setor_id, sem_solicitacao=True)
                except ValueError as _exc_sn:
                    st.warning(str(_exc_sn))
                else:
                    st.session_state["sol_sem_necessidade"] = True
                    st.rerun()

    # ── Envio ─────────────────────────────────────────────────────────────────
    if submitted:
        itens_sem_justificativa = [
            item["nome"]
            for idx, item in enumerate(itens_lista)
            if item.get("item_id") is None
            and not (st.session_state.get(f"obs_{idx}", item.get("observacao") or "")).strip()
        ]
        if itens_sem_justificativa:
            for nome_faltante in itens_sem_justificativa:
                st.error(f"Justificativa obrigatória para o item novo: **{nome_faltante}**. Preencha o campo 'Observação' na revisão acima.")
            submitted = False

    if submitted:
        itens_create = [
            SolicitacaoMaterialCreate(
                item_id=item["item_id"],
                nome_item_livre=item["nome"] if item["item_id"] is None else None,
                solicitante=solicitante.strip(),
                quantidade_solicitada=int(st.session_state.get(f"qtd_{idx}", item["quantidade"])),
                observacao=st.session_state.get(f"obs_{idx}", item.get("observacao") or "") or None,
                urgente=st.session_state.get(f"urg_{idx}", item.get("urgente", False)),
                periodo_referencia=periodo_sel,
            )
            for idx, item in enumerate(itens_lista)
        ]
        pedido_dados = SolicitacaoPedidoCreate(
            setor_id=setor_id,
            solicitante=solicitante.strip(),
            periodo_referencia=periodo_sel,
            itens=itens_create,
        )
        try:
            with SessionLocal() as _s:
                criar_pedido_solicitacao(_s, pedido_dados)
        except ValueError as _exc_envio:
            st.error(f"Não foi possível enviar a solicitação: {_exc_envio}")
        else:
            _nome_setor_push = next((nome for sid, nome in setores if sid == setor_id), "Setor")
            push_service.notificar_formulario_recebido(_nome_setor_push, periodo_label_sol)
            st.session_state["sol_enviada"] = True
            st.session_state["sol_confirmar_segundo_envio"] = False
            st.rerun()
