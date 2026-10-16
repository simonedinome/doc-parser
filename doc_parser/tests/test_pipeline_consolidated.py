"""Percorso video consolidato: più video (webinar/pillola) e PDF di slide."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from doc_parser.core.models import RunRecord, RunStatus
from doc_parser.core.pricing import compute_cost
from doc_parser.pipeline.consolidation import ConsolidationValidationError
from doc_parser.pipeline.core import process_run
from doc_parser.pipeline.inputs import describe_inputs, save_manifest
from doc_parser.providers.base import BaseProvider
from doc_parser.settings import Settings
from doc_parser.storage.sqlite_repo import SqliteRepository

_MODELS_FILE = Path(__file__).resolve().parent.parent.parent / "models.yaml"
STEP1_MODEL = "gemini-3.1-pro-preview"
OPENROUTER_MODEL = "anthropic/claude-haiku-4.5"
GEMINI_LITE_MODEL = "gemini-2.5-flash-lite"

_STEP2_PREFIX = "Ecco il JSON grezzo da rifinire:\n\n"
_STEP2_SUFFIX = "\n\nRispondi ESCLUSIVAMENTE"


class FnProvider(BaseProvider):
    """Provider di test: ogni risposta è una tupla o una funzione (system, user) -> tupla."""

    name = "scripted"

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, list]] = []

    def generate(self, system_prompt, user_prompt, attachments=None):
        self.calls.append((system_prompt, user_prompt, attachments or []))
        if not self._responses:
            raise AssertionError("Nessuna risposta scriptata rimasta")
        response = self._responses.pop(0)
        return response(system_prompt, user_prompt) if callable(response) else response


def step2_echo(title: str = "Manuale rifinito"):
    """Risposta di step 2 che riscrive solo il titolo del JSON ricevuto."""

    def _respond(system_prompt, user_prompt):
        raw = user_prompt[len(_STEP2_PREFIX) : user_prompt.index(_STEP2_SUFFIX)]
        data = json.loads(raw)
        data["title"] = title
        return json.dumps(data), 500, 400

    return _respond


def patch_providers(monkeypatch, by_model: dict[str, BaseProvider]) -> None:
    monkeypatch.setattr("doc_parser.pipeline.core.get_provider_for_model", lambda model_id, settings: by_model[model_id])


def sample_pdf_bytes(pages: int = 4) -> bytes:
    import fitz

    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Slide {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def consolidated_run(
    repo: SqliteRepository,
    model_id: str,
    videos=(("webinar.mp4", "webinar", "2026-06-03"), ("pillola.mp4", "pillola", "2026-09-12")),
    with_pdf: bool = True,
    language: str = "it",
    output_artifacts: str = "html_standalone,procedura,glossario,rag_chunks",
) -> RunRecord:
    run = RunRecord(
        session_id="s1", requester_upn="utente@demo.local", input_filename="serie", input_type="video",
        content_type="video", model_id=model_id, language=language, output_artifacts=output_artifacts,
    )
    items = list(videos) + ([("deck.pdf", None, None)] if with_pdf else [])
    datas = [f"video-{name}".encode() for name, _, _ in videos] + ([sample_pdf_bytes()] if with_pdf else [])
    run.input_manifest_ref = save_manifest(repo, run.run_id, describe_inputs(items), datas)
    return repo.create_run(run)


def step1_response(title: str, steps: list[tuple[str, str, list[int]]], notes=()) -> tuple[str, int, int]:
    """JSON di step 1 con una procedura: steps = [(titolo, timestamp, slide)]."""
    return (
        json.dumps(
            {
                "title": title, "summary": "Sommario", "prerequisites": ["Accesso al gestionale"],
                "procedures": [
                    {
                        "id": "proc_001", "title": "Creare una tariffa",
                        "steps": [
                            {"number": i, "title": t, "description": f"Descrizione {t}", "notes": "",
                             "source_timestamps": [ts], "source_slides": slides, "embedding_keywords": [t]}
                            for i, (t, ts, slides) in enumerate(steps, 1)
                        ],
                    }
                ],
                "glossary": [{"term": "Tariffa", "definition": "Prezzo"}],
                "notes": list(notes),
            }
        ),
        1000,
        200,
    )


WEBINAR_STEP1 = step1_response("Webinar", [("Apri Tariffe", "00:10", [2]), ("Salva", "01:00", [])])
PILLOLA_STEP1 = step1_response("Pillola", [("Apri Tariffe", "00:05", [2]), ("Verifica", "00:30", [3])])


def consolidation_response(conflicts=None) -> tuple[str, int, int]:
    return (
        json.dumps(
            {
                "title": "Manuale tariffe", "summary": "Gestione delle tariffe.", "prerequisites": ["Accesso al gestionale"],
                "concepts": [{"title": "Tariffe", "content": "Cosa sono le tariffe.", "embedding_keywords": ["tariffa"], "merged_from": [], "slides": [4]}],
                "procedures": [
                    {
                        "title": "Creare una tariffa",
                        "steps": [
                            {"title": "Aprire Tariffe", "description": "Navigare in Impostazioni > Tariffe.", "notes": "",
                             "embedding_keywords": ["tariffe"], "merged_from": ["v1/proc_001/1", "v2/proc_001/1"], "slides": [2]},
                            {"merged_from": ["v1/proc_001/2"]},
                            {"merged_from": ["v2/proc_001/2"]},
                        ],
                    }
                ],
                "glossary": [{"term": "Tariffa", "definition": "Prezzo"}],
                "notes": [],
                "conflicts": conflicts
                if conflicts is not None
                else [{"topic": "Nome del menu", "chosen": "v1/proc_001/1", "discarded": ["v2/proc_001/1"], "reason": "Il webinar è la fonte principale"}],
                "dropped": [],
                "skipped_slides": [{"slide": 1, "reason": "copertina"}],
            }
        ),
        3000,
        800,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", models_file=_MODELS_FILE, retry_max_attempts=2)


@pytest.fixture
def repo(settings: Settings) -> SqliteRepository:
    return SqliteRepository(data_dir=settings.data_dir)


@pytest.fixture(autouse=True)
def no_ffmpeg(monkeypatch):
    """Nessun ffmpeg reale nei test: ogni estrazione da video fallisce."""

    def _fail(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr("doc_parser.pipeline.screenshots.subprocess.run", _fail)


def test_two_videos_and_pdf_are_consolidated_with_costs_per_phase(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL)
    step1 = FnProvider([WEBINAR_STEP1, PILLOLA_STEP1])
    chosen = FnProvider([consolidation_response(), step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: chosen})

    process_run(run, repo, settings)

    updated = repo.get_run(run.run_id)
    assert updated.status == RunStatus.DONE
    assert len(step1.calls) == 2 and len(chosen.calls) == 2  # 2 step 1, 1 consolidamento, 1 step 2
    for _, _, attachments in step1.calls:
        assert [a.mime_type for a in attachments] == ["video/mp4", "application/pdf"]
    assert [a.mime_type for a in chosen.calls[0][2]] == ["application/pdf"]

    final = json.loads(repo.get_file(updated.final_json_ref))
    assert final["title"] == "Manuale rifinito"
    procedures = final["procedures"]
    assert len(procedures) == 1  # "Creare una tariffa" dei due video unita una volta sola
    assert [s["title"] for s in procedures[0]["steps"]] == ["Aprire Tariffe", "Salva", "Verifica"]

    raw = json.loads(repo.get_file(updated.raw_json_ref))
    assert raw["consolidation_log"]["conflicts"][0]["chosen"]["filename"] == "webinar.mp4"
    assert updated.input_pages == 4

    outputs = settings.data_dir / "outputs"
    assert (outputs / f"{run.run_id}_step1_v1.json").exists()
    assert (outputs / f"{run.run_id}_step1_v2.json").exists()

    step1_cost = compute_cost(STEP1_MODEL, 2000, 400, settings.models_file).cost_eur
    cons_cost = compute_cost(OPENROUTER_MODEL, 3000, 800, settings.models_file).cost_eur
    step2_cost = compute_cost(OPENROUTER_MODEL, 500, 400, settings.models_file).cost_eur
    assert updated.step1_cost_eur == pytest.approx(step1_cost)
    assert updated.consolidation_model == OPENROUTER_MODEL
    assert updated.consolidation_cost_eur == pytest.approx(cons_cost)
    assert updated.step2_cost_eur == pytest.approx(step2_cost)
    assert updated.cost_eur == pytest.approx(step1_cost + cons_cost + step2_cost)
    assert updated.tokens_in == 2000 + 3000 + 500 and updated.tokens_out == 400 + 800 + 400


def test_two_videos_without_pdf_are_consolidated(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL, with_pdf=False)
    no_slides_webinar = step1_response("W", [("Apri Tariffe", "00:10", []), ("Salva", "01:00", [])])
    no_slides_pillola = step1_response("P", [("Apri Tariffe", "00:05", []), ("Verifica", "00:30", [])])
    response = json.loads(consolidation_response()[0])
    response["concepts"] = []
    response["procedures"][0]["steps"][0]["slides"] = []
    response["skipped_slides"] = []
    step1 = FnProvider([no_slides_webinar, no_slides_pillola])
    chosen = FnProvider([(json.dumps(response), 10, 10), step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: chosen})

    process_run(run, repo, settings)

    assert repo.get_run(run.run_id).status == RunStatus.DONE
    assert all(len(attachments) == 1 for _, _, attachments in step1.calls)
    assert "source_slides" not in step1.calls[0][1]  # niente addendum senza PDF
    assert chosen.calls[0][2] == []


def test_single_video_with_pdf_is_consolidated(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL, videos=(("webinar.mp4", "webinar", None),))
    response = json.loads(consolidation_response(conflicts=[])[0])
    steps = response["procedures"][0]["steps"]
    steps[0]["merged_from"] = ["v1/proc_001/1"]
    del steps[2]
    response["concepts"][0]["slides"] = [3, 4]  # senza la pillola la slide 3 va coperta dal concetto
    step1 = FnProvider([WEBINAR_STEP1])
    chosen = FnProvider([(json.dumps(response), 10, 10), step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: chosen})

    process_run(run, repo, settings)

    assert repo.get_run(run.run_id).status == RunStatus.DONE
    assert len(step1.calls) == 1 and len(chosen.calls) == 2


def test_gemini_model_consolidates_without_step2(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, GEMINI_LITE_MODEL)
    gemini = FnProvider([WEBINAR_STEP1, PILLOLA_STEP1, consolidation_response()])
    patch_providers(monkeypatch, {GEMINI_LITE_MODEL: gemini, STEP1_MODEL: FnProvider([])})

    process_run(run, repo, settings)

    updated = repo.get_run(run.run_id)
    assert updated.status == RunStatus.DONE
    assert len(gemini.calls) == 3
    assert updated.step1_model == GEMINI_LITE_MODEL and updated.consolidation_model == GEMINI_LITE_MODEL
    assert updated.step2_model is None
    assert updated.final_json_ref == updated.raw_json_ref


def test_failed_consolidation_keeps_step1_and_records_spent_costs(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL)
    attempts = settings.retry_max_attempts + 1
    step1 = FnProvider([WEBINAR_STEP1, PILLOLA_STEP1])
    chosen = FnProvider([('{"title": "troncato', 100, 50)] * attempts)
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: chosen})

    with pytest.raises(ConsolidationValidationError, match="troncata"):
        process_run(run, repo, settings)

    updated = repo.get_run(run.run_id)
    assert (settings.data_dir / "outputs" / f"{run.run_id}_step1_v1.json").exists()
    assert updated.consolidation_tokens_in == 100 * attempts
    step1_cost = compute_cost(STEP1_MODEL, 2000, 400, settings.models_file).cost_eur
    cons_cost = compute_cost(OPENROUTER_MODEL, 100 * attempts, 50 * attempts, settings.models_file).cost_eur
    assert updated.cost_eur == pytest.approx(step1_cost + cons_cost)


def test_two_pdfs_in_manifest_are_rejected(monkeypatch, repo, settings) -> None:
    from doc_parser.core.errors import GuardrailRejection

    run = RunRecord(session_id="s1", requester_upn="u@x", input_filename="serie", input_type="video", content_type="video", model_id=OPENROUTER_MODEL)
    descriptors = describe_inputs([("a.mp4", None, None), ("s1.pdf", None, None)])
    descriptors.append({"filename": "s2.pdf", "input_id": "pdf2", "role": "slides"})
    run.input_manifest_ref = save_manifest(repo, run.run_id, descriptors, [b"v", sample_pdf_bytes(), sample_pdf_bytes()])
    repo.create_run(run)
    patch_providers(monkeypatch, {})

    with pytest.raises(GuardrailRejection, match="massimo un PDF"):
        process_run(run, repo, settings)


def test_zip_of_consolidated_run_contains_artifacts(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL)
    patch_providers(
        monkeypatch,
        {STEP1_MODEL: FnProvider([WEBINAR_STEP1, PILLOLA_STEP1]), OPENROUTER_MODEL: FnProvider([consolidation_response(), step2_echo()])},
    )

    process_run(run, repo, settings)

    names = set(zipfile.ZipFile(io.BytesIO(repo.get_file(repo.get_run(run.run_id).zip_ref))).namelist())
    assert {"procedura.txt", "glossario.txt", "rag_chunks.jsonl", "documentazione_standalone.html", "log.txt"} <= names


def test_images_fall_back_to_slides_and_reach_the_zip(monkeypatch, repo, settings) -> None:
    run = consolidated_run(repo, OPENROUTER_MODEL, output_artifacts="html_folder")
    patch_providers(
        monkeypatch,
        {STEP1_MODEL: FnProvider([WEBINAR_STEP1, PILLOLA_STEP1]), OPENROUTER_MODEL: FnProvider([consolidation_response(), step2_echo()])},
    )

    process_run(run, repo, settings)

    updated = repo.get_run(run.run_id)
    zf = zipfile.ZipFile(io.BytesIO(repo.get_file(updated.zip_ref)))
    names = set(zf.namelist())
    # step 1 (slide 2) e step 3 (slide 3 dalla pillola): ffmpeg assente, ripiego sulla slide
    assert {"screenshots/proc_001_step_001.png", "screenshots/proc_001_step_003.png", "screenshots/con_001_slide.png"} <= names
    assert "screenshots/proc_001_step_002.png" not in names  # nessuna slide e nessun fotogramma
    html = zf.read("documentazione.html").decode("utf-8")
    assert 'src="screenshots/con_001_slide.png"' in html
