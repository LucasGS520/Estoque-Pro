import streamlit as st

from core.config import ADMIN_PASSWORD


def require_admin() -> None:
    if st.session_state.get("autenticado"):
        return

    if not ADMIN_PASSWORD:
        st.error("Variável ADMIN_PASSWORD não está configurada no arquivo .env")
        st.stop()

    _, col, _ = st.columns([2, 1, 2])
    with col:
        st.markdown("#### Acesso Administrativo")
        with st.form("_admin_login"):
            senha = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", use_container_width=True)

        if submit:
            if senha == ADMIN_PASSWORD:
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")

    st.stop()
