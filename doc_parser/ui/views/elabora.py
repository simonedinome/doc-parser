"""Pagina Elabora: upload multiplo/URL, tipo contenuto, modello, lingua, output.

Tutte le opzioni sono visibili a tutti gli utenti. Lo step 1 video resta
sempre non selezionabile (modello fisso o il Gemini scelto quando lo
step 2 verrebbe saltato): la scelta qui riguarda lo step 2 / il percorso
single-step, coerentemente con doc_parser.pipeline.core.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.core.pricing import load_models_config
from doc_parser.ingestion import guardrails
from doc_parser.ingestion.downloader import download_url
from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import ACTIVE, badge, download_filename, fmt_dt

_LANGUAGE_LABELS = {"it": "Italiano", "en": "English"}
_VIDEO_CONTENT_TYPE = "hybrid"
_ARTIFACT_OPTIONS = [
    ("html_standalone", "Documentazione HTML standalone (un file, immagini incorporate)"),
    ("html_folder", "Documentazione HTML con cartella (screenshot separati)"),
    ("procedura", "Procedura (procedura.txt)"),
    ("glossario", "Glossario (glossario.txt)"),
    ("rag_chunks", "Chunk RAG (rag_chunks.jsonl)"),
]
_DEFAULT_ARTIFACTS = {"html_standalone", "procedura", "glossario", "rag_chunks"}


def render() -> None:
    settings, repo, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None:
        st.stop()

    st.title("Elabora")
    st.caption(
        f"Massimo {settings.max_upload_mb} MB totali per richiesta. "
        "L'elaborazione avviene in background: puoi chiudere il tab e "
        "ritrovare la run in «Le mie richieste»."
    )

    content_choice = st.selectbox("Tipo di contenuto", ["Documento", "Video"])
    is_video = content_choice == "Video"

    uploaded = st.file_uploader("File", accept_multiple_files=True)
    url_text = st.text_area("Oppure URL (uno per riga)", placeholder="https://esempio.com/video.mp4")

    processing_mode_label = st.radio(
        "Modalità di elaborazione",
        ["Processa di gruppo", "Processa singolarmente"],
        help=(
            'Processa di gruppo: "singolo output per tutti i file in input" — i file caricati '
            "vengono uniti in un'unica documentazione.\n\n"
            'Processa singolarmente: "output per ciascun file in input" — ogni file/URL genera '
            "una run ed un export separati."
        ),
    )
    process_as_group = processing_mode_label == "Processa di gruppo"

    models = load_models_config(settings.models_file).models
    model_label = st.selectbox("Modello", [m.label for m in models])
    model_id = next(m.id for m in models if m.label == model_label)

    language_label = st.selectbox("Lingua output", list(_LANGUAGE_LABELS.values()))
    language = next(k for k, v in _LANGUAGE_LABELS.items() if v == language_label)

    st.caption("File da avere in output")
    selected_artifacts: list[str] = []
    for key, label in _ARTIFACT_OPTIONS:
        if st.checkbox(label, value=key in _DEFAULT_ARTIFACTS, key=f"artifact_{key}"):
            selected_artifacts.append(key)

    if st.button("Avvia elaborazione", type="primary"):
        if not selected_artifacts:
            st.error("Seleziona almeno un file da avere in output.")
        else:
            _submit(
                repo,
                settings,
                user,
                auth.get_session_id(),
                uploaded or [],
                url_text,
                is_video,
                process_as_group,
                model_id,
                language,
                selected_artifacts,
            )

    run_id = st.session_state.get("last_run_id")
    if run_id:
        st.divider()
        _live_status(run_id)


def _submit(
    repo,
    settings,
    user,
    session_id: str,
    uploaded,
    url_text: str,
    is_video: bool,
    process_as_group: bool,
    model_id: str,
    language: str,
    output_artifacts: list[str],
) -> None:
    files: list[tuple[str, bytes]] = [(f.name, f.getvalue()) for f in uploaded]

    urls = [line.strip() for line in url_text.splitlines() if line.strip()]
    if urls:
        with TemporaryDirectory(prefix="doc_parser_url_") as tmp_dir:
            for url in urls:
                try:
                    path = download_url(url, Path(tmp_dir))
                    files.append((path.name, path.read_bytes()))
                except Exception as exc:
                    st.error(f"Impossibile scaricare {url}: {exc}")
                    return

    if not files:
        st.error("Carica almeno un file o inserisci almeno un URL.")
        return

    try:
        input_type = guardrails.resolve_input_type(is_video, [f[0] for f in files])
    except Exception as exc:
        st.error(str(exc))
        return

    total_size = sum(len(data) for _, data in files)
    try:
        guardrails.check_size(total_size, settings.max_upload_mb)
    except Exception as exc:
        st.error(str(exc))
        return

    groups = [files] if process_as_group else [[f] for f in files]
    output_artifacts_csv = ",".join(output_artifacts)

    last_run_id = None
    for group in groups:
        run = RunRecord(
            session_id=session_id,
            requester_upn=user.upn,
            input_filename=group[0][0] if len(group) == 1 else f"{len(group)} file",
            input_type=input_type,
            content_type=_VIDEO_CONTENT_TYPE if is_video else None,
            output_mode="documentazione",
            output_artifacts=output_artifacts_csv,
            language=language,
            model_id=model_id,
        )
        if len(group) == 1:
            filename, data = group[0]
            run.input_size_bytes = len(data)
            run.input_path = repo.save_input_file(run.run_id, filename, data)
        else:
            manifest = []
            for filename, data in group:
                ref = repo.save_input_file(run.run_id, filename, data)
                manifest.append({"filename": filename, "path_ref": ref})
            run.input_size_bytes = sum(len(data) for _, data in group)
            run.input_manifest_ref = repo.save_input_file(
                run.run_id, "manifest.json", json.dumps(manifest).encode("utf-8")
            )
        repo.create_run(run)
        last_run_id = run.run_id

    st.session_state["last_run_id"] = last_run_id
    if len(groups) > 1:
        st.success(f"{len(groups)} run create (elaborazione singola per file).")


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
            "Scarica",
            data=repo.get_file(run.output_path),
            file_name=download_filename(run),
            type="primary",
        )
        if run.status == RunStatus.DONE:
            cost_bits = []
            if run.cost_eur is not None:
                cost_bits.append(f"Costo: {run.cost_eur:.4f} EUR")
            if run.chunk_count is not None:
                cost_bits.append(f"Chunk: {run.chunk_count} | Incertezze: {run.uncertainty_count}")
            if cost_bits:
                st.caption(" | ".join(cost_bits))
