"""Pagina Le mie richieste: run dell'utente con auto-refresh sulle attive."""

from __future__ import annotations

import streamlit as st

from doc_parser.core.models import RunStatus
from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import friendly_row, has_active, output_name


def render() -> None:
    _, repo, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None:
        st.stop()

    st.title("Le mie richieste")
    _table(user.upn)


@st.fragment(run_every="3s")
def _table(upn: str) -> None:
    _, repo, _, _ = get_app_context()
    runs = repo.list_runs(requester_upn=upn)
    if not runs:
        st.info("Nessuna richiesta: carica un documento dalla pagina «Elabora».")
        return

    if not has_active(runs):
        st.caption("Nessuna run attiva")

    st.dataframe(
        [friendly_row(run) for run in runs],
        use_container_width=True,
        hide_index=True,
    )

    downloadable = [r for r in runs if r.output_path and r.status in (RunStatus.DONE, RunStatus.DUPLICATE)]
    if downloadable:
        options = {f"{r.input_filename} — {r.run_id[:8]}": r for r in downloadable}
        choice = st.selectbox("Scarica un output", list(options))
        run = options[choice]
        st.download_button(
            "Scarica TXT",
            data=repo.get_file(run.output_path),
            file_name=output_name(run),
            mime="text/plain",
            key=f"dl_{run.run_id}",
        )
