"""Pagina Log: proiezione friendly di tutte le run (stessa tabella, sola vista)."""

from __future__ import annotations

import streamlit as st

from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import cost_summary_windows, friendly_row


def render() -> None:
    st.title("Log")
    st.caption("Tutte le richieste, vista sintetica.")
    _cost_summary()
    _table()


@st.fragment(run_every="10s")
def _cost_summary() -> None:
    _, repo, _, _ = get_app_context()
    st.subheader("Riepilogo costi per utente")
    for idx, (label, rows) in enumerate(cost_summary_windows(repo)):
        with st.expander(label, expanded=(idx == 0)):
            if rows:
                st.dataframe(
                    [
                        {
                            "Utente": r["group_key"],
                            "Run": r["run_count"],
                            "Token": r["tokens_total"],
                            "Costo (EUR)": f"{r['cost_eur']:.4f}",
                        }
                        for r in rows
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Nessuna run nel periodo.")
    st.divider()


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
