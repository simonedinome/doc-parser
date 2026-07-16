"""Pagina Elabora: upload PDF -> run Queued -> stato live -> download.

Port minimale Fase 1 (solo PDF, come nel progetto sorgente): multi-upload,
URL, tipo contenuto, modalità output, scelta modello e lingua arrivano in
Fase 6, quando la pipeline (Fase 4) sarà pronta a consumarli.
"""

from __future__ import annotations

import streamlit as st

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import ACTIVE, badge, fmt_dt


def render() -> None:
    settings, repo, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None:
        st.stop()

    st.title("Elabora un PDF")
    st.caption(
        f"Massimo {settings.max_pages} pagine / {settings.max_upload_mb} MB. "
        "L'elaborazione avviene in background: puoi chiudere il tab e "
        "ritrovare la run in «Le mie richieste»."
    )

    uploaded = st.file_uploader("Documento PDF", type=["pdf"])
    if uploaded is not None and st.button("Avvia elaborazione", type="primary"):
        data = uploaded.getvalue()
        run = RunRecord(
            session_id=auth.get_session_id(),
            requester_upn=user.upn,
            input_filename=uploaded.name,
            input_size_bytes=len(data),
        )
        run.input_path = repo.save_input_file(run.run_id, uploaded.name, data)
        repo.create_run(run)
        st.session_state["last_run_id"] = run.run_id

    run_id = st.session_state.get("last_run_id")
    if run_id:
        st.divider()
        _live_status(run_id)


@st.fragment(run_every="2s")
def _live_status(run_id: str) -> None:
    _, repo, _, _ = get_app_context()
    run = repo.get_run(run_id)
    if run is None:
        st.warning("Run non trovata")
        return

    st.subheader(f"Run {run.run_id[:8]} — {run.input_filename}")
    st.markdown(f"**Stato:** {badge(run.status)}")

    if run.status in ACTIVE:
        st.progress(0.33 if run.status == RunStatus.QUEUED else 0.66)
        return

    left, right = st.columns(2)
    left.metric("Creata", fmt_dt(run.created_at))
    right.metric("Completata", fmt_dt(run.completed_at))

    if run.status in (RunStatus.FAILED, RunStatus.REJECTED):
        st.error(run.error_message or "Errore non specificato")
        return

    if run.status == RunStatus.DUPLICATE:
        st.info("Documento già elaborato in precedenza: output riutilizzato senza nuova analisi.")

    if run.output_path:
        st.download_button(
            "Scarica TXT",
            data=repo.get_file(run.output_path),
            file_name=f"{run.input_filename.rsplit('.', 1)[0]}.txt",
            mime="text/plain",
            type="primary",
        )
        if run.status == RunStatus.DONE:
            st.caption(
                f"Chunk: {run.chunk_count} | Incertezze: {run.uncertainty_count} | "
                f"Pagine: {run.input_pages}"
            )
