"""End-to-end: coda YAML con una serie di formazione (due webinar, una
pillola, un PDF di slide) fino allo ZIP, e regressioni del percorso video."""

import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from doc_parser.cli.queue_runner import run_yaml_queue
from doc_parser.core.models import RunStatus
from doc_parser.settings import Settings
from doc_parser.storage.sqlite_repo import SqliteRepository
from doc_parser.tests.test_pipeline_consolidated import (
    OPENROUTER_MODEL,
    STEP1_MODEL,
    FnProvider,
    patch_providers,
    sample_pdf_bytes,
    step1_response,
    step2_echo,
)

_MODELS_FILE = Path(__file__).resolve().parent.parent.parent / "models.yaml"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", models_file=_MODELS_FILE, retry_max_attempts=1)


@pytest.fixture(autouse=True)
def no_ffmpeg(monkeypatch):
    def _fail(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr("doc_parser.pipeline.screenshots.subprocess.run", _fail)


def _series_consolidation() -> tuple[str, int, int]:
    return (
        json.dumps(
            {
                "title": "Manuale tariffe", "summary": "Gestione delle tariffe.", "prerequisites": ["Accesso al gestionale"],
                "concepts": [{"title": "Tariffe", "content": "Cosa sono.", "embedding_keywords": [], "merged_from": [], "slides": [3, 4]}],
                "procedures": [
                    {
                        "title": "Creare una tariffa",
                        "steps": [
                            {"title": "Aprire Tariffe", "description": "Navigare in Impostazioni > Tariffe.", "notes": "", "embedding_keywords": [],
                             "merged_from": ["v1/proc_001/1", "v2/proc_001/1", "v3/proc_001/1"], "slides": [2]},
                            {"title": "Salvare", "description": "Cliccare su Salva.", "notes": "", "embedding_keywords": [],
                             "merged_from": ["v1/proc_001/2", "v2/proc_001/2"]},
                        ],
                    }
                ],
                "glossary": [{"term": "Tariffa", "definition": "Prezzo"}],
                "notes": ["Domanda: si può duplicare una tariffa? / Risposta: sì, da Azioni > Duplica."],
                "conflicts": [
                    {"topic": "Nome del pulsante di salvataggio", "chosen": "v2/proc_001/2", "discarded": ["v1/proc_001/2"],
                     "reason": "La registrazione più recente mostra l'interfaccia aggiornata"},
                    {"topic": "Percorso del menu", "chosen": "v1/proc_001/1", "discarded": ["v3/proc_001/1", "pdf/2"],
                     "reason": "Il webinar ha priorità su pillola e slide"},
                ],
                "dropped": [{"ref": "v3/proc_001/2", "reason": "saluti"}],
                "skipped_slides": [{"slide": 1, "reason": "copertina"}],
            }
        ),
        5000,
        900,
    )


def test_yaml_series_produces_complete_zip(monkeypatch, tmp_path, settings) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for name in ("webinar_giugno.mp4", "webinar_luglio.mp4", "pillola_settembre.mp4"):
        (input_dir / name).write_bytes(f"video-{name}".encode())
    (input_dir / "slide.pdf").write_bytes(sample_pdf_bytes())
    runs_file = tmp_path / "runs.yaml"
    runs_file.write_text(
        yaml.safe_dump(
            {
                "settings": {"content_type": "video", "model_id": OPENROUTER_MODEL,
                             "output_artifacts": "html_standalone,html_folder,procedura,glossario,rag_chunks,pptx"},
                "runs": [
                    {
                        "name": "formazione-tariffe",
                        "inputs": [
                            {"source": "file", "order": 1, "path": str(input_dir / "webinar_giugno.mp4"), "kind": "webinar", "recorded_at": "2026-06-03"},
                            {"source": "file", "order": 2, "path": str(input_dir / "webinar_luglio.mp4"), "kind": "webinar", "recorded_at": "2026-07-08"},
                            {"source": "file", "order": 3, "path": str(input_dir / "pillola_settembre.mp4"), "kind": "pillola", "recorded_at": "2026-09-12"},
                            {"source": "file", "order": 4, "path": str(input_dir / "slide.pdf")},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    webinar = step1_response("W", [("Apri Tariffe", "00:10", [2]), ("Salva", "01:00", [])])
    pillola = step1_response("P", [("Apri Tariffe", "00:05", [2]), ("Saluti", "02:00", [])])
    step1 = FnProvider([webinar, webinar, pillola])
    chosen = FnProvider([_series_consolidation(), step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: chosen})

    checkpoint = run_yaml_queue(runs_file, settings, checkpoint_path=tmp_path / "checkpoint.json")

    assert checkpoint["completed_runs"] == ["formazione-tariffe"], checkpoint
    run = SqliteRepository(data_dir=settings.data_dir).list_runs()[0]
    assert run.status == RunStatus.DONE
    assert len(step1.calls) == 3 and len(chosen.calls) == 2
    zf = zipfile.ZipFile(io.BytesIO(Path(run.zip_ref).read_bytes()))
    names = set(zf.namelist())
    assert {
        "documentazione.html", "documentazione_standalone.html", "procedura.txt", "glossario.txt",
        "rag_chunks.jsonl", "presentazione_tutorial.pptx", "log.txt",
    } <= names
    log_txt = zf.read("log.txt").decode("utf-8")
    assert "== DISCORDANZE ==" in log_txt
    assert "Ordine di priorità: v2 > v1 > pdf > v3" in log_txt
    assert "Fonte tenuta: webinar_luglio.mp4 (webinar, registrato il 2026-07-08)" in log_txt
    assert "Fonte scartata: slide.pdf (slide) · slide 2" in log_txt
    assert "ATTENZIONE: fonte scartata più recente, verificare · Fonte scartata: pillola_settembre.mp4" in log_txt
    procedura = zf.read("procedura.txt").decode("utf-8")
    assert procedura.count("PROCEDURA ") == 1


def test_single_video_without_pdf_uses_two_step_path(monkeypatch, tmp_path, settings) -> None:
    video = tmp_path / "solo.mp4"
    video.write_bytes(b"video")
    runs_file = tmp_path / "runs.yaml"
    runs_file.write_text(
        yaml.safe_dump({"settings": {"content_type": "video", "model_id": OPENROUTER_MODEL},
                        "runs": [{"name": "singolo", "inputs": [{"source": "file", "path": str(video), "kind": "pillola"}]}]}),
        encoding="utf-8",
    )
    step1 = FnProvider([step1_response("V", [("Apri", "00:10", [])])])
    chosen = FnProvider([step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, OPENROUTER_MODEL: chosen})

    run_yaml_queue(runs_file, settings, checkpoint_path=tmp_path / "checkpoint.json")

    run = SqliteRepository(data_dir=settings.data_dir).list_runs()[0]
    assert run.status == RunStatus.DONE
    assert len(step1.calls) == 1 and len(chosen.calls) == 1  # nessuna chiamata di consolidamento
    assert run.consolidation_model is None and run.consolidation_cost_eur is None
    assert "source_slides" not in step1.calls[0][1]
    raw = json.loads(Path(run.raw_json_ref).read_bytes())
    assert "consolidation_log" not in raw
