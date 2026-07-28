"""Entry point della web app Streamlit.

Avvio (dalla root del repo):
    streamlit run doc_parser/ui/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from doc_parser.ui.context import get_app_context
from doc_parser.ui.views import elabora, guida, le_mie_richieste, log, log_tecnico


def main() -> None:
    st.set_page_config(page_title="doc-parser", page_icon="📄", layout="wide")
    _, _, auth, _ = get_app_context()

    user = auth.get_current_user()
    if user is None:
        auth.login_form()
        st.stop()

    with st.sidebar:
        st.markdown(f"**{user.display_name}**")
        st.caption(user.upn + (" · admin" if user.is_admin else ""))
        if st.button("Esci"):
            auth.logout()
            st.rerun()

    pages = [
        st.Page(elabora.render, title="Elabora", icon="📄", url_path="elabora", default=True),
        st.Page(
            le_mie_richieste.render,
            title="Le mie richieste",
            icon="📋",
            url_path="le-mie-richieste",
        ),
        st.Page(log.render, title="Log", icon="🗂️", url_path="log"),
        st.Page(guida.render, title="Guida", icon="❓", url_path="guida"),
    ]
    if user.is_admin:
        pages.append(
            st.Page(log_tecnico.render, title="Log tecnico", icon="🛠️", url_path="log-tecnico")
        )

    st.navigation(pages).run()


main()
