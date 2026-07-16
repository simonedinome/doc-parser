"""Pagina Log: proiezione friendly di tutte le run (stessa tabella, sola vista)."""

from __future__ import annotations

import streamlit as st

from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import friendly_row


def render() -> None:
    st.title("Log")
    st.caption("Tutte le richieste, vista sintetica.")
    _table()


@st.fragment(run_every="5s")
def _table() -> None:
    _, repo, _, _ = get_app_context()
    runs = repo.list_runs(limit=500)
    if not runs:
        st.info("Nessuna run registrata.")
        return
    st.dataframe(
        [friendly_row(run) for run in runs],
        use_container_width=True,
        hide_index=True,
    )
