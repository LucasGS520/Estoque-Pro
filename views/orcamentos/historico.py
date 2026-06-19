"""Aba Histórico — página Orçamentos."""
import datetime

import streamlit as st
from sqlalchemy.orm import joinedload

from core.database import get_session_factory
from core.models import ItemOrcamento, Orcamento
from core.ui import empty_state, section_title
from documents.orcamento import gerar_documento_cotacao
from services.orcamento_service import deletar_orcamento, get_orcamentos_periodo


@st.cache_data(ttl=300)
def _bytes_docx_orcamento(orc_id: int) -> tuple[bytes, str]:
    """Gera DOCX do orçamento e retorna (bytes, nome_arquivo). Cache 5 min."""
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


def render(periodo: datetime.date, periodo_label: str) -> None:
    """Renderiza a aba Histórico."""
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        historico = get_orcamentos_periodo(session, periodo)
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

    section_title(f"Orçamentos — {periodo_label}")

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
