"""Punto di ingresso condiviso della pipeline di elaborazione.

Invocato dal worker in background e dalla CLI: guardrail, dedup, parsing
(step 1/2 per i video, step unico per gli altri formati) e persistenza degli
artefatti (JSON grezzo/finale, screenshot) vivono qui, cosicché CLI e UI
Streamlit condividano lo stesso motore.

Gli artefatti finali (procedura.txt/glossario.txt/rag_chunks.jsonl/html/zip)
sono costruiti da doc_parser.output a partire dal JSON finale, sempre in
questo modulo: la modalità "documentazione" produce lo ZIP completo, la
modalità "KB densa" il TXT a chunk assemblato da doc_parser.core.assembler.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_parser.core import assembler, kb_densa_prompts
from doc_parser.core.errors import GuardrailRejection
from doc_parser.core.models import RunRecord, RunStatus, utcnow
from doc_parser.core.pricing import compute_cost, get_model, load_models_config
from doc_parser.ingestion import guardrails
from doc_parser.ingestion.extract import LOCAL_EXTRACTION_KINDS, extract_text
from doc_parser.ingestion.mime import mime_type_for
from doc_parser.output.assembly import build_output_zip
from doc_parser.output.logger import Logger
from doc_parser.pipeline import consolidation, merger, parser, screenshots
from doc_parser.pipeline.inputs import InputFile, load_inputs
from doc_parser.pipeline.language import apply_language_directive
from doc_parser.pipeline.profiles import resolve_profile_prompts
from doc_parser.pipeline.slides_addendum import apply_slides_addendum, slides_attachments
from doc_parser.pipeline.step2_prompts import (
    STEP2_RETRY_FEEDBACK_TEMPLATE,
    STEP2_SYSTEM_PROMPT,
    STEP2_USER_PROMPT_TEMPLATE,
)
from doc_parser.pipeline.step2_validate import Step2ValidationError, validate_step2_output
from doc_parser.providers import get_provider_for_model
from doc_parser.providers.base import Attachment
from doc_parser.settings import Settings
from doc_parser.storage.base import Repository
from doc_parser.worker.processor import finalize_run

_VIDEO_CONTENT_TYPES = {"video", "screencast"}


def process_run(run: RunRecord, repo: Repository, settings: Settings) -> None:
    if run.parent_run_id:
        _process_elaborate_only(run, repo, settings)
        return

    input_files = _load_input_files(run, repo)
    if not input_files:
        raise GuardrailRejection("File di input mancante")

    total_size = sum(len(data) for _, data in input_files)
    guardrails.check_size(total_size, settings.max_upload_mb)

    if len(input_files) == 1 and _reuse_if_duplicate(run, repo, input_files[0][1]):
        return

    if run.input_type == "video":
        _process_video(run, repo, settings, input_files)
    elif run.input_type == "image":
        _process_images(run, repo, settings, input_files)
    else:
        _process_document(run, repo, settings, input_files)


def _reuse_if_duplicate(run: RunRecord, repo: Repository, data: bytes) -> bool:
    """Se un file identico è già stato elaborato con la stessa configurazione
    (modello, lingua, output_mode, content_type, output_artifacts), riusa l'output
    esistente senza una nuova chiamata LLM. Ritorna True se la run è stata
    gestita come duplicato (già finalizzata come DUPLICATE).

    Il dedup si applica solo alle run a file singolo: le run multi-file
    (merge video, immagini multiple) e le run elaborate_only non vi rientrano.
    """
    input_hash = guardrails.sha256_hash(data)
    repo.update_run(run.run_id, input_hash=input_hash)

    duplicate = repo.find_done_by_hash(input_hash)
    if duplicate is None or not _same_configuration(run, duplicate):
        return False

    repo.update_run(
        run.run_id,
        input_pages=duplicate.input_pages,
        raw_json_ref=duplicate.raw_json_ref,
        final_json_ref=duplicate.final_json_ref,
        screenshots_ref=duplicate.screenshots_ref,
        output_dir_ref=duplicate.output_dir_ref,
        zip_ref=duplicate.zip_ref,
        output_path=duplicate.output_path,
        output_size_bytes=duplicate.output_size_bytes,
        chunk_count=duplicate.chunk_count,
        uncertainty_count=duplicate.uncertainty_count,
        tokens_in=0,
        tokens_out=0,
        tokens_total=0,
        cost_eur=0.0,
        error_message=f"Duplicato della run {duplicate.run_id}",
    )
    finalize_run(repo, run.run_id, RunStatus.DUPLICATE, run.started_at)
    return True


def _same_configuration(run: RunRecord, duplicate: RunRecord) -> bool:
    return (
        run.model_id == duplicate.model_id
        and run.language == duplicate.language
        and run.output_mode == duplicate.output_mode
        and run.content_type == duplicate.content_type
        and run.output_artifacts == duplicate.output_artifacts
    )


# --- Caricamento input ---


def _load_input_files(run: RunRecord, repo: Repository) -> list[tuple[str, bytes]]:
    if run.input_manifest_ref:
        manifest = json.loads(repo.get_file(run.input_manifest_ref).decode("utf-8"))
        return [(entry["filename"], repo.get_file(entry["path_ref"])) for entry in manifest]
    if run.input_path:
        return [(run.input_filename, repo.get_file(run.input_path))]
    return []


def _screenshots_output_dir(settings: Settings, run_id: str) -> Path:
    output_dir = settings.data_dir / "screenshots" / run_id
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _reconstruct_screenshot_map(
    screenshots_dir: Path | None, procedures: list[dict]
) -> dict[tuple[str, int], Path | None]:
    """Ricostruisce {(proc_id, step_number): path} dai file su disco.

    Gli screenshot (video o pagine PDF) sono sempre nominati
    ``{proc_id}_step_{numero:03d}.png``: non serve propagare la mappa
    attraverso tutta la pipeline, basta rileggerla a fine elaborazione.
    """
    mapping: dict[tuple[str, int], Path | None] = {}
    if screenshots_dir is None:
        return mapping
    for proc in procedures:
        proc_id = proc.get("id")
        for step in proc.get("steps", []):
            num = step.get("number")
            path = screenshots_dir / f"{proc_id}_step_{num:03d}.png"
            mapping[(proc_id, num)] = path if path.exists() else None
    return mapping


def _build_and_persist_output(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    final_data: dict,
    source_filename: str,
    screenshots_dir: Path | None,
) -> None:
    """Costruisce gli artefatti "Documentazione operativa" dal JSON finale e
    li persiste (cartella + zip). Non usato dalla modalità KB densa, che
    produce già il proprio TXT direttamente in _process_kb_densa."""
    screenshot_map = _reconstruct_screenshot_map(screenshots_dir, final_data.get("procedures", []))
    log = Logger()
    log.log("INFO", f"Run {run.run_id} completata")
    output_artifacts = run.output_artifacts.split(",") if run.output_artifacts else []
    files, zip_bytes = build_output_zip(
        final_data, source_filename, run.language, output_artifacts, screenshot_map, screenshots_dir, log
    )

    artifacts_dir = settings.data_dir / "artifacts" / run.run_id
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (artifacts_dir / name).write_bytes(content)

    zip_ref = repo.save_output_file(run.run_id, "run.zip", zip_bytes)
    repo.update_run(
        run.run_id,
        output_dir_ref=str(artifacts_dir),
        zip_ref=zip_ref,
        output_path=zip_ref,
        output_size_bytes=len(zip_bytes),
    )


# --- Percorso video (two-step) ---


def _process_video(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    input_files: list[tuple[str, bytes]],
) -> None:
    content_type = run.content_type or "video"
    if content_type not in _VIDEO_CONTENT_TYPES:
        raise GuardrailRejection(f"Tipo di contenuto video non valido: {content_type!r}")

    if content_type == "video" and len(input_files) >= 2:
        _process_video_consolidated(run, repo, settings, input_files)
        return

    for filename, _ in input_files:
        kind = guardrails.classify_extension(filename)
        if kind != "video":
            raise GuardrailRejection(f"'{filename}' non è un video ({kind})")

    system_prompt, user_prompt = resolve_profile_prompts(content_type)
    system_prompt = apply_language_directive(system_prompt, run.language)

    chosen_model = get_model(settings.models_file, run.model_id) if run.model_id else None
    single_pass_gemini = chosen_model is not None and chosen_model.backend == "gemini"
    step1_model_id = run.model_id if single_pass_gemini else _step1_video_model(settings)
    step1_provider = get_provider_for_model(step1_model_id, settings)

    results: list[tuple[dict, str]] = []
    tokens_in_total = tokens_out_total = 0
    warnings: list[str] = []
    screenshots_dir = _screenshots_output_dir(settings, run.run_id)

    with TemporaryDirectory(prefix="doc_parser_video_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        video_paths: list[Path] = []
        for filename, data in input_files:
            video_path = tmp_path / filename
            video_path.write_bytes(data)
            video_paths.append(video_path)

            attachment = Attachment(data=data, mime_type=mime_type_for(filename), filename=filename)
            raw_text, tokens_in, tokens_out = step1_provider.generate(
                system_prompt, user_prompt, [attachment]
            )
            tokens_in_total += tokens_in
            tokens_out_total += tokens_out
            data_dict = parser.parse_response(raw_text, content_type)
            results.append((data_dict, filename))

        merged = (
            merger.merge_run_results(results, run.input_filename or "run")
            if len(results) > 1
            else results[0][0]
        )

        offset = 0
        for (data_dict, _), video_path in zip(results, video_paths):
            n_procs = len(data_dict.get("procedures", []))
            procedures_slice = merged.get("procedures", [])[offset : offset + n_procs]
            offset += n_procs
            screenshots.extract_screenshots(
                video_path,
                procedures_slice,
                screenshots_dir,
                warn=warnings.append,
            )

    raw_json_bytes = json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8")
    raw_json_ref = repo.save_output_file(run.run_id, "raw.json", raw_json_bytes)

    step1_snapshot = compute_cost(step1_model_id, tokens_in_total, tokens_out_total, settings.models_file)
    repo.update_run(
        run.run_id,
        raw_json_ref=raw_json_ref,
        screenshots_ref=str(screenshots_dir),
        step1_provider=step1_provider.name,
        step1_model=step1_model_id,
        step1_tokens_in=tokens_in_total,
        step1_tokens_out=tokens_out_total,
        step1_cost_eur=step1_snapshot.cost_eur if step1_snapshot else None,
        error_message="; ".join(warnings) if warnings else None,
    )

    step1_cost = step1_snapshot.cost_eur if step1_snapshot else 0.0
    _finish_video_run(
        run, repo, settings, merged, raw_json_ref, single_pass_gemini, screenshots_dir,
        tokens_in_total, tokens_out_total, step1_cost,
    )


def _finish_video_run(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    raw_data: dict,
    raw_json_ref: str,
    single_pass_gemini: bool,
    screenshots_dir: Path | None,
    prior_tokens_in: int,
    prior_tokens_out: int,
    prior_cost: float,
) -> None:
    """Step 2 (saltato con un Gemini scelto), totali della run, artefatti.

    I totali sommano le fasi già eseguite (*prior_*) e lo step 2.
    """
    if single_pass_gemini:
        final_data = raw_data
        final_json_ref = raw_json_ref
        step2_fields: dict = {}
    else:
        final_data, step2_tokens_in, step2_tokens_out, retry_count = _run_step2(raw_data, run, settings)
        final_json_bytes = json.dumps(final_data, ensure_ascii=False, indent=2).encode("utf-8")
        final_json_ref = repo.save_output_file(run.run_id, "final.json", final_json_bytes)
        step2_snapshot = compute_cost(run.model_id, step2_tokens_in, step2_tokens_out, settings.models_file)
        step2_fields = dict(
            step2_provider=get_provider_for_model(run.model_id, settings).name,
            step2_model=run.model_id,
            step2_tokens_in=step2_tokens_in,
            step2_tokens_out=step2_tokens_out,
            step2_cost_eur=step2_snapshot.cost_eur if step2_snapshot else None,
            retry_count=retry_count,
        )

    total_tokens_in = prior_tokens_in + step2_fields.get("step2_tokens_in", 0)
    total_tokens_out = prior_tokens_out + step2_fields.get("step2_tokens_out", 0)
    total_cost = prior_cost + (step2_fields.get("step2_cost_eur") or 0.0)

    repo.update_run(
        run.run_id,
        final_json_ref=final_json_ref,
        tokens_in=total_tokens_in,
        tokens_out=total_tokens_out,
        tokens_total=total_tokens_in + total_tokens_out,
        cost_eur=round(total_cost, 6),
        **step2_fields,
    )
    _build_and_persist_output(run, repo, settings, final_data, run.input_filename or "run", screenshots_dir)
    finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)


# --- Percorso video consolidato (più video e/o PDF di slide) ---


def _process_video_consolidated(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    input_files: list[tuple[str, bytes]],
) -> None:
    """Step 1 per ogni video (con il PDF di slide e l'addendum), consolidamento
    in un unico JSON senza ripetizioni, immagini, step 2, artefatti.

    Costi e token si registrano dopo ogni fase, così anche una run fallita
    al consolidamento o allo step 2 conta quanto ha già speso.
    """
    inputs = load_inputs(run, repo, preloaded=[data for _, data in input_files])
    videos = [i for i in inputs if i.role == "video"]
    slides_inputs = [i for i in inputs if i.role == "slides"]
    if len(slides_inputs) > 1:
        raise GuardrailRejection("Puoi caricare al massimo un PDF di slide per run: tieni solo il deck della formazione.")
    if not videos:
        raise GuardrailRejection("Serve almeno un video: il PDF di slide si usa solo insieme ai video della stessa formazione.")
    for video in videos:
        kind = guardrails.classify_extension(video.filename)
        if kind != "video":
            raise GuardrailRejection(f"'{video.filename}' non è un video ({kind})")
    slides = slides_inputs[0] if slides_inputs else None
    slide_count = guardrails.check_slides_pdf(slides.data, settings.max_pages) if slides else 0
    if slides:
        repo.update_run(run.run_id, input_pages=slide_count)

    chosen_model = get_model(settings.models_file, run.model_id) if run.model_id else None
    single_pass_gemini = chosen_model is not None and chosen_model.backend == "gemini"
    step1_model_id = run.model_id if single_pass_gemini else _step1_video_model(settings)
    step1_provider = get_provider_for_model(step1_model_id, settings)
    screenshots_dir = _screenshots_output_dir(settings, run.run_id)
    image_warnings: list[str] = []

    with TemporaryDirectory(prefix="doc_parser_video_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        video_paths: dict[str, Path] = {}
        step1_results: list[tuple[InputFile, dict]] = []
        step1_tokens_in = step1_tokens_out = 0
        for video in videos:
            video_path = tmp_path / f"{video.input_id}_{video.filename}"
            video_path.write_bytes(video.data)
            video_paths[video.input_id] = video_path

            system_prompt, user_prompt, attachments = _step1_request("video", run.language, video, slides)
            raw_text, tokens_in, tokens_out = step1_provider.generate(system_prompt, user_prompt, attachments)
            step1_tokens_in += tokens_in
            step1_tokens_out += tokens_out
            data_dict = consolidation.normalize_step1(parser.parse_response(raw_text, "video"))
            repo.save_output_file(
                run.run_id,
                f"step1_{video.input_id}.json",
                json.dumps(data_dict, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            step1_results.append((video, data_dict))

        step1_snapshot = compute_cost(step1_model_id, step1_tokens_in, step1_tokens_out, settings.models_file)
        step1_cost = step1_snapshot.cost_eur if step1_snapshot else 0.0
        repo.update_run(
            run.run_id,
            step1_provider=step1_provider.name,
            step1_model=step1_model_id,
            step1_tokens_in=step1_tokens_in,
            step1_tokens_out=step1_tokens_out,
            step1_cost_eur=step1_snapshot.cost_eur if step1_snapshot else None,
        )
        _record_running_totals(repo, run.run_id, step1_tokens_in, step1_tokens_out, step1_cost)

        index = consolidation.build_index(step1_results, slides, slide_count)
        consolidation_provider = get_provider_for_model(run.model_id, settings)
        try:
            consolidated, cons_tokens_in, cons_tokens_out, _ = consolidation.consolidate(
                consolidation_provider, index, run.language, settings.retry_max_attempts + 1
            )
        except consolidation.ConsolidationValidationError as exc:
            _record_consolidation(
                repo, run, settings, exc.tokens_in, exc.tokens_out, step1_tokens_in, step1_tokens_out, step1_cost
            )
            raise
        prior_tokens_in, prior_tokens_out, prior_cost = _record_consolidation(
            repo, run, settings, cons_tokens_in, cons_tokens_out, step1_tokens_in, step1_tokens_out, step1_cost
        )

    raw_json_bytes = json.dumps(consolidated, ensure_ascii=False, indent=2).encode("utf-8")
    raw_json_ref = repo.save_output_file(run.run_id, "raw.json", raw_json_bytes)
    repo.update_run(
        run.run_id,
        raw_json_ref=raw_json_ref,
        screenshots_ref=str(screenshots_dir),
        error_message="; ".join(image_warnings) if image_warnings else None,
    )

    _finish_video_run(
        run, repo, settings, consolidated, raw_json_ref, single_pass_gemini, screenshots_dir,
        prior_tokens_in, prior_tokens_out, prior_cost,
    )


def _record_consolidation(
    repo: Repository,
    run: RunRecord,
    settings: Settings,
    tokens_in: int,
    tokens_out: int,
    step1_tokens_in: int,
    step1_tokens_out: int,
    step1_cost: float,
) -> tuple[int, int, float]:
    """Registra costi e token del consolidamento e i totali aggiornati;
    ritorna i totali (token in, token out, costo) fino a questa fase."""
    snapshot = compute_cost(run.model_id, tokens_in, tokens_out, settings.models_file)
    repo.update_run(
        run.run_id,
        consolidation_model=run.model_id,
        consolidation_tokens_in=tokens_in,
        consolidation_tokens_out=tokens_out,
        consolidation_cost_eur=snapshot.cost_eur if snapshot else None,
    )
    totals = (
        step1_tokens_in + tokens_in,
        step1_tokens_out + tokens_out,
        step1_cost + (snapshot.cost_eur if snapshot else 0.0),
    )
    _record_running_totals(repo, run.run_id, *totals)
    return totals


def _record_running_totals(repo: Repository, run_id: str, tokens_in: int, tokens_out: int, cost: float) -> None:
    repo.update_run(
        run_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_total=tokens_in + tokens_out,
        cost_eur=round(cost, 6),
    )


def _step1_request(
    content_type: str,
    language: str,
    video: InputFile,
    slides: InputFile | None,
) -> tuple[str, str, list[Attachment]]:
    """Prompt e allegati di una chiamata di step 1 su un video della run.

    Con il PDF di slide: addendum appeso ai prompt protetti (mai modificati)
    e PDF allegato accanto al video. La direttiva di lingua resta l'ultima
    istruzione di sistema, come nel percorso a video singolo.
    """
    system_prompt, user_prompt = resolve_profile_prompts(content_type)
    attachments = [Attachment(data=video.data, mime_type=mime_type_for(video.filename), filename=video.filename)]
    if slides is not None:
        system_prompt, user_prompt = apply_slides_addendum(system_prompt, user_prompt)
        attachments.extend(slides_attachments(slides.filename, slides.data))
    return apply_language_directive(system_prompt, language), user_prompt, attachments


def _step1_video_model(settings: Settings) -> str:
    return load_models_config(settings.models_file).step1_video_model


def _run_step2(
    raw_data: dict,
    run: RunRecord,
    settings: Settings,
) -> tuple[dict, int, int, int]:
    """Esegue lo step 2 con retry-con-feedback in caso di violazione del vincolo.

    Ritorna (dati_riscritti, tokens_in_totali, tokens_out_totali, retry_count).
    Solleva Step2ValidationError se il vincolo è violato anche dopo i retry
    (la run viene marcata FAILED dal worker; il grezzo resta persistito).
    """
    provider = get_provider_for_model(run.model_id, settings)
    system_prompt = apply_language_directive(STEP2_SYSTEM_PROMPT, run.language)
    raw_json_str = json.dumps(raw_data, ensure_ascii=False, indent=2)
    user_prompt = STEP2_USER_PROMPT_TEMPLATE.format(raw_json=raw_json_str)

    tokens_in_total = tokens_out_total = 0
    last_error: Exception | None = None
    max_attempts = settings.retry_max_attempts + 1
    for attempt in range(max_attempts):
        raw_text, tokens_in, tokens_out = provider.generate(system_prompt, user_prompt)
        tokens_in_total += tokens_in
        tokens_out_total += tokens_out
        try:
            rewritten = parser.load_json_response(raw_text)
            validate_step2_output(raw_data, rewritten)
            return rewritten, tokens_in_total, tokens_out_total, attempt
        except (ValueError, Step2ValidationError) as exc:
            last_error = exc
            user_prompt = STEP2_RETRY_FEEDBACK_TEMPLATE.format(violation=str(exc))

    raise Step2ValidationError(
        f"Lo step 2 non ha rispettato il vincolo ID/timestamp dopo {max_attempts} tentativi: {last_error}"
    )


# --- Percorso non-video (single-step) ---


def _process_document(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    input_files: list[tuple[str, bytes]],
) -> None:
    if run.output_mode == "kb_densa":
        filename, data = input_files[0]
        kind = guardrails.classify_extension(filename)
        attachments: list[Attachment] = []
        extracted_text: str | None = None
        if kind == "pdf":
            pages = guardrails.inspect_pdf(data, settings.max_pages)
            repo.update_run(run.run_id, input_pages=pages)
            attachments = [Attachment(data=data, mime_type="application/pdf", filename=filename)]
        elif kind in LOCAL_EXTRACTION_KINDS:
            extracted_text = extract_text(kind, data, settings.xlsx_max_rows_per_sheet)
        else:
            raise GuardrailRejection(f"Formato non gestito nel percorso documento: {kind!r}")
        _process_kb_densa(run, repo, settings, attachments, extracted_text)
        return

    content_type = run.content_type or "documento"
    if content_type == "manuale":
        for filename, _ in input_files:
            if guardrails.classify_extension(filename) != "pdf":
                raise GuardrailRejection("Il profilo 'manuale' accetta solo PDF")

    provider = get_provider_for_model(run.model_id, settings)
    system_prompt, user_prompt_base = resolve_profile_prompts(content_type)
    system_prompt = apply_language_directive(system_prompt, run.language)

    results: list[tuple[dict, str]] = []
    tokens_in_total = tokens_out_total = 0
    total_pages = 0
    pdf_files: list[tuple[Path, str]] = []

    with TemporaryDirectory(prefix="doc_parser_doc_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for filename, data in input_files:
            kind = guardrails.classify_extension(filename)
            attachments: list[Attachment] = []
            user_prompt = user_prompt_base

            if kind == "pdf":
                pages = guardrails.inspect_pdf(data, settings.max_pages)
                total_pages += pages
                attachments = [Attachment(data=data, mime_type="application/pdf", filename=filename)]
                pdf_path = tmp_path / filename
                pdf_path.write_bytes(data)
                pdf_files.append((pdf_path, filename))
            elif kind in LOCAL_EXTRACTION_KINDS:
                extracted_text = extract_text(kind, data, settings.xlsx_max_rows_per_sheet)
                user_prompt = f"{user_prompt}\n\n--- CONTENUTO DEL DOCUMENTO ---\n\n{extracted_text}"
            else:
                raise GuardrailRejection(f"Formato non gestito nel percorso documento: {kind!r}")

            raw_text, tokens_in, tokens_out = provider.generate(system_prompt, user_prompt, attachments)
            tokens_in_total += tokens_in
            tokens_out_total += tokens_out
            results.append((parser.parse_response(raw_text, content_type), filename))

        merged = (
            merger.merge_run_results(results, run.input_filename or "run")
            if len(results) > 1
            else results[0][0]
        )

        screenshots_dir: Path | None = None
        if pdf_files:
            screenshots_dir = _screenshots_output_dir(settings, run.run_id)
            offset = 0
            pdf_iter = iter(pdf_files)
            for data_dict, filename in results:
                n_procs = len(data_dict.get("procedures", []))
                procedures_slice = merged.get("procedures", [])[offset : offset + n_procs]
                offset += n_procs
                if guardrails.classify_extension(filename) == "pdf":
                    pdf_path, _ = next(pdf_iter)
                    screenshots.extract_pdf_pages(pdf_path, procedures_slice, screenshots_dir)

    if total_pages:
        repo.update_run(run.run_id, input_pages=total_pages)
    if screenshots_dir is not None:
        repo.update_run(run.run_id, screenshots_ref=str(screenshots_dir))

    output_filename = run.input_filename or results[0][1]
    _finalize_single_step(
        run, repo, settings, provider, merged, tokens_in_total, tokens_out_total, output_filename, screenshots_dir
    )


def _process_images(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    input_files: list[tuple[str, bytes]],
) -> None:
    for filename, _ in input_files:
        kind = guardrails.classify_extension(filename)
        if kind != "image":
            raise GuardrailRejection(f"'{filename}' non è un'immagine ({kind})")

    attachments = [
        Attachment(data=data, mime_type=mime_type_for(filename), filename=filename)
        for filename, data in input_files
    ]
    system_prompt, user_prompt = resolve_profile_prompts("documento")
    system_prompt = apply_language_directive(system_prompt, run.language)

    provider = get_provider_for_model(run.model_id, settings)
    raw_text, tokens_in, tokens_out = provider.generate(system_prompt, user_prompt, attachments)
    data_dict = parser.parse_response(raw_text, "documento")

    source_filename = run.input_filename or input_files[0][0]
    _finalize_single_step(run, repo, settings, provider, data_dict, tokens_in, tokens_out, source_filename, None)


def _finalize_single_step(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    provider,
    data_dict: dict,
    tokens_in: int,
    tokens_out: int,
    source_filename: str,
    screenshots_dir: Path | None,
) -> None:
    final_json_bytes = json.dumps(data_dict, ensure_ascii=False, indent=2).encode("utf-8")
    final_json_ref = repo.save_output_file(run.run_id, "final.json", final_json_bytes)

    snapshot = compute_cost(run.model_id, tokens_in, tokens_out, settings.models_file)
    repo.update_run(
        run.run_id,
        raw_json_ref=final_json_ref,
        final_json_ref=final_json_ref,
        provider=provider.name,
        model_version=run.model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_total=tokens_in + tokens_out,
        unit_price_in=snapshot.unit_price_in if snapshot else None,
        unit_price_out=snapshot.unit_price_out if snapshot else None,
        cost_eur=snapshot.cost_eur if snapshot else None,
    )
    _build_and_persist_output(run, repo, settings, data_dict, source_filename, screenshots_dir)
    finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)


# --- Modalità output KB densa (non-video) ---


def _process_kb_densa(
    run: RunRecord,
    repo: Repository,
    settings: Settings,
    attachments: list[Attachment],
    extracted_text: str | None,
) -> None:
    system_prompt = apply_language_directive(kb_densa_prompts.SYSTEM_PROMPT, run.language)
    user_prompt = kb_densa_prompts.USER_PROMPT
    if extracted_text is not None:
        user_prompt = f"{user_prompt}\n\n--- CONTENUTO DEL DOCUMENTO ---\n\n{extracted_text}"

    provider = get_provider_for_model(run.model_id, settings)
    raw_text, tokens_in, tokens_out = provider.generate(system_prompt, user_prompt, attachments)
    try:
        chunks = assembler.extract_chunks(raw_text)
    except assembler.ModelResponseError as exc:
        raise ValueError(str(exc)) from exc

    txt = assembler.assemble_txt(chunks, run.input_filename, utcnow())
    output_bytes = txt.encode("utf-8")
    output_name = Path(run.input_filename).stem + ".txt"
    output_path = repo.save_output_file(run.run_id, output_name, output_bytes)

    snapshot = compute_cost(run.model_id, tokens_in, tokens_out, settings.models_file)
    repo.update_run(
        run.run_id,
        output_path=output_path,
        output_size_bytes=len(output_bytes),
        provider=provider.name,
        model_version=run.model_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_total=tokens_in + tokens_out,
        unit_price_in=snapshot.unit_price_in if snapshot else None,
        unit_price_out=snapshot.unit_price_out if snapshot else None,
        cost_eur=snapshot.cost_eur if snapshot else None,
        chunk_count=len(chunks),
        uncertainty_count=assembler.count_uncertainty(chunks),
    )
    finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)


# --- Rielabora (job elaborate_only sulle run figlie) ---


def _process_elaborate_only(run: RunRecord, repo: Repository, settings: Settings) -> None:
    parent = repo.get_run(run.parent_run_id) if run.parent_run_id else None
    if parent is None or not parent.raw_json_ref:
        raise GuardrailRejection(
            "Run madre non trovata o priva di JSON grezzo: impossibile rielaborare"
        )
    try:
        raw_bytes = repo.get_file(parent.raw_json_ref)
    except (FileNotFoundError, OSError) as exc:
        raise GuardrailRejection(
            f"Artefatti della run madre non trovati su disco: {exc}"
        ) from exc
    raw_data = json.loads(raw_bytes.decode("utf-8"))

    repo.update_run(
        run.run_id,
        input_filename=parent.input_filename,
        content_type=parent.content_type,
        raw_json_ref=parent.raw_json_ref,
        screenshots_ref=parent.screenshots_ref,
    )

    final_data, tokens_in, tokens_out, retry_count = _run_step2(raw_data, run, settings)
    final_json_bytes = json.dumps(final_data, ensure_ascii=False, indent=2).encode("utf-8")
    final_json_ref = repo.save_output_file(run.run_id, "final.json", final_json_bytes)

    snapshot = compute_cost(run.model_id, tokens_in, tokens_out, settings.models_file)
    repo.update_run(
        run.run_id,
        final_json_ref=final_json_ref,
        step2_provider=get_provider_for_model(run.model_id, settings).name,
        step2_model=run.model_id,
        step2_tokens_in=tokens_in,
        step2_tokens_out=tokens_out,
        step2_cost_eur=snapshot.cost_eur if snapshot else None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_total=tokens_in + tokens_out,
        cost_eur=snapshot.cost_eur if snapshot else 0.0,
        retry_count=retry_count,
    )
    screenshots_dir = Path(parent.screenshots_ref) if parent.screenshots_ref else None
    _build_and_persist_output(
        run, repo, settings, final_data, parent.input_filename or "run", screenshots_dir
    )
    finalize_run(repo, run.run_id, RunStatus.DONE, run.started_at)
