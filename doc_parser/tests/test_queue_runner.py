import json
import threading
from pathlib import Path

import pytest

from doc_parser.cli.config import GlobalSettings, InputSource, RunConfig, RunsConfig
from doc_parser.cli.queue_runner import run_queue
from doc_parser.providers.base import BaseProvider
from doc_parser.settings import Settings
from doc_parser.storage.sqlite_repo import SqliteRepository

_MODELS_FILE = Path(__file__).resolve().parent.parent.parent / "models.yaml"
STEP1_MODEL = "gemini-3.1-pro-preview"
GEMINI_LITE_MODEL = "gemini-2.5-flash-lite"


class ScriptedProvider(BaseProvider):
    name = "scripted"

    def __init__(self, responses: list[tuple[str, int, int]]) -> None:
        self._responses = list(responses)
        self._lock = threading.Lock()
        self.calls: list = []

    def generate(self, system_prompt, user_prompt, attachments=None):
        with self._lock:
            self.calls.append((system_prompt, user_prompt, attachments or []))
            if not self._responses:
                raise AssertionError("Nessuna risposta scriptata rimasta")
            return self._responses.pop(0)


def _patch_providers(monkeypatch, by_model: dict[str, ScriptedProvider]) -> None:
    def _fake(model_id, settings):
        return by_model[model_id]

    monkeypatch.setattr("doc_parser.pipeline.core.get_provider_for_model", _fake)


def _video_response(title: str = "Titolo") -> str:
    return json.dumps(
        {
            "title": title,
            "summary": "Sommario",
            "prerequisites": [],
            "procedures": [
                {
                    "id": "proc_001",
                    "title": "P1",
                    "steps": [{"number": 1, "timestamp": "00:05", "title": "S1", "description": "d", "notes": "", "embedding_keywords": []}],
                }
            ],
            "glossary": [],
            "notes": [],
        }
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data", models_file=_MODELS_FILE, retry_max_attempts=1)


def _video_file(tmp_path: Path, name: str = "video.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"video-bytes-fittizi")
    return path


def test_run_queue_processes_single_pass_gemini_run(monkeypatch, tmp_path, settings) -> None:
    video = _video_file(tmp_path)
    config = RunsConfig(
        settings=GlobalSettings(content_type="video", model_id=GEMINI_LITE_MODEL, parallel_runs=2),
        runs=[RunConfig(name="run1", inputs=[InputSource(source="file", path=str(video))])],
    )
    provider = ScriptedProvider([(_video_response(), 100, 10)])
    _patch_providers(monkeypatch, {GEMINI_LITE_MODEL: provider})

    checkpoint = run_queue(config, settings, checkpoint_path=tmp_path / "checkpoint.json")

    assert checkpoint["completed_runs"] == ["run1"]
    assert checkpoint["failed_runs"] == {}
    repo = SqliteRepository(data_dir=settings.data_dir)
    runs = repo.list_runs()
    assert len(runs) == 1
    assert runs[0].zip_ref is not None


def test_run_queue_resumes_and_skips_completed(monkeypatch, tmp_path, settings) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(json.dumps({"completed_runs": ["run1"], "failed_runs": {}}), encoding="utf-8")

    video = _video_file(tmp_path)
    config = RunsConfig(
        settings=GlobalSettings(content_type="video", model_id=GEMINI_LITE_MODEL),
        runs=[RunConfig(name="run1", inputs=[InputSource(source="file", path=str(video))])],
    )
    # nessun provider scriptato: se venisse chiamato il test fallirebbe con KeyError
    _patch_providers(monkeypatch, {})

    checkpoint = run_queue(config, settings, checkpoint_path=checkpoint_path)
    assert checkpoint["completed_runs"] == ["run1"]


def test_run_queue_marks_failed_on_missing_file(monkeypatch, tmp_path, settings) -> None:
    config = RunsConfig(
        settings=GlobalSettings(content_type="video", model_id=GEMINI_LITE_MODEL),
        runs=[RunConfig(name="run-assente", inputs=[InputSource(source="file", path=str(tmp_path / "assente.mp4"))])],
    )
    _patch_providers(monkeypatch, {})

    checkpoint = run_queue(config, settings, checkpoint_path=tmp_path / "checkpoint.json")

    assert "run-assente" in checkpoint["failed_runs"]
    assert checkpoint["completed_runs"] == []


def test_run_queue_two_step_video_uses_fixed_step1_and_chosen_step2(monkeypatch, tmp_path, settings) -> None:
    video = _video_file(tmp_path)
    config = RunsConfig(
        settings=GlobalSettings(content_type="video", model_id="anthropic/claude-haiku-4.5"),
        runs=[RunConfig(name="run1", inputs=[InputSource(source="file", path=str(video))])],
    )
    step1 = ScriptedProvider([(_video_response("Grezzo"), 100, 10)])
    rewritten = {
        "title": "Rifinito", "summary": "S", "prerequisites": [],
        "procedures": [{"id": "proc_001", "title": "P", "steps": [{"number": 1, "timestamp": "00:05", "title": "S1", "description": "d"}]}],
        "glossary": [], "notes": [],
    }
    step2 = ScriptedProvider([(json.dumps(rewritten), 50, 20)])
    _patch_providers(monkeypatch, {STEP1_MODEL: step1, "anthropic/claude-haiku-4.5": step2})

    checkpoint = run_queue(config, settings, checkpoint_path=tmp_path / "checkpoint.json")

    assert checkpoint["completed_runs"] == ["run1"]
    repo = SqliteRepository(data_dir=settings.data_dir)
    run = repo.list_runs()[0]
    assert run.step1_model == STEP1_MODEL
    assert run.step2_model == "anthropic/claude-haiku-4.5"


def test_run_queue_multiple_runs_in_parallel(monkeypatch, tmp_path, settings) -> None:
    video_a = _video_file(tmp_path, "a.mp4")
    video_b = _video_file(tmp_path, "b.mp4")
    config = RunsConfig(
        settings=GlobalSettings(content_type="video", model_id=GEMINI_LITE_MODEL, parallel_runs=2),
        runs=[
            RunConfig(name="run-a", inputs=[InputSource(source="file", path=str(video_a))]),
            RunConfig(name="run-b", inputs=[InputSource(source="file", path=str(video_b))]),
        ],
    )
    provider = ScriptedProvider([(_video_response("A"), 10, 5), (_video_response("B"), 10, 5)])
    _patch_providers(monkeypatch, {GEMINI_LITE_MODEL: provider})

    checkpoint = run_queue(config, settings, checkpoint_path=tmp_path / "checkpoint.json")

    assert set(checkpoint["completed_runs"]) == {"run-a", "run-b"}
