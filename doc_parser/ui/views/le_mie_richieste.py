"""Pagina Le mie richieste: run dell'utente, download e Rielabora."""

from __future__ import annotations

import streamlit as st

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.core.pricing import load_models_config
from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import (
    download_filename,
    friendly_row,
    has_active,
    input_download_entries,
    output_artifact_entries,
)


def render() -> None:
    _, repo, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None:
        st.stop()

    st.title("Le mie richieste")
    _table(user.upn)


@st.fragment(run_every="3s")
def _table(upn: str) -> None:
    settings, repo, _, _ = get_app_context()
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
        choice = st.selectbox("Scarica una run", list(options))
        run = options[choice]

        st.download_button(
            "Scarica output (zip completo)",
            data=repo.get_file(run.output_path),
            file_name=download_filename(run),
            key=f"dl_{run.run_id}",
        )

        artifacts = output_artifact_entries(run)
        if artifacts:
            with st.expander("Scarica singoli file di output"):
                for name, path in artifacts:
                    st.download_button(
                        name,
                        data=repo.get_file(path),
                        file_name=name,
                        key=f"dl_artifact_{run.run_id}_{name}",
                    )

        inputs = input_download_entries(repo, run)
        if inputs:
            with st.expander("Scarica file di input"):
                for name, ref in inputs:
                    st.download_button(
                        name,
                        data=repo.get_file(ref),
                        file_name=name,
                        key=f"dl_input_{run.run_id}_{name}",
                    )

    reworkable = [r for r in runs if r.input_type == "video" and r.status == RunStatus.DONE and r.raw_json_ref]
    if reworkable:
        st.divider()
        st.subheader("Rielabora")
        st.caption("Rigenera solo lo step 2 (riscrittura) con un altro modello, riusando il JSON grezzo e gli screenshot già estratti.")
        options = {f"{r.input_filename} — {r.run_id[:8]}": r for r in reworkable}
        choice = st.selectbox("Run video da rielaborare", list(options), key="rework_choice")
        source_run = options[choice]

        models = load_models_config(settings.models_file).models
        model_label = st.selectbox("Nuovo modello", [m.label for m in models], key="rework_model")
        model_id = next(m.id for m in models if m.label == model_label)

        if st.button("Avvia rielaborazione", key="rework_submit"):
            child = RunRecord(
                session_id=source_run.session_id,
                requester_upn=source_run.requester_upn,
                input_filename=source_run.input_filename,
                input_type="video",
                content_type=source_run.content_type,
                output_mode=source_run.output_mode,
                output_artifacts=source_run.output_artifacts,
                language=source_run.language,
                model_id=model_id,
                parent_run_id=source_run.run_id,
            )
            repo.create_run(child)
            st.success(f"Rielaborazione avviata: run {child.run_id[:8]}")
            st.rerun()
