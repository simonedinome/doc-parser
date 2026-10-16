"""CLI: --resume di una run consolidata fallita e default dei flag invariati per il batch."""

from pathlib import Path

import pytest

from doc_parser.cli.config import GlobalSettings
from doc_parser.core.models import RunStatus
from doc_parser.storage.sqlite_repo import SqliteRepository
from doc_parser.tests.test_pipeline_consolidated import (
    OPENROUTER_MODEL,
    STEP1_MODEL,
    FnProvider,
    _failed_mother,
    consolidation_response,
    patch_providers,
    step2_echo,
)
from doc_parser.tests.test_pipeline_consolidated import no_ffmpeg  # noqa: F401  (fixture autouse)
from doc_parser.tests.test_pipeline_consolidated import repo, settings  # noqa: F401  (fixture)

SONNET_MODEL = "anthropic/claude-sonnet-5"


def _parse(argv):
    from doc_parser.cli.main import build_parser

    return build_parser().parse_args(argv)


def _main(argv, settings):
    from doc_parser.cli import main as cli_main

    return cli_main.main(argv, settings=settings)


def test_batch_without_flags_keeps_todays_defaults(tmp_path: Path) -> None:
    from doc_parser.cli.main import _build_batch_config

    config = _build_batch_config(_parse(["--input-dir", str(tmp_path)]))
    assert config.settings == GlobalSettings(
        content_type="video",
        model_id="anthropic/claude-haiku-4.5",
        language="it",
        output_mode="documentazione",
        output_artifacts="html_standalone,procedura,glossario,rag_chunks",
        parallel_runs=3,
        requester_upn="cli@local",
    )


def test_batch_explicit_flags_are_applied(tmp_path: Path) -> None:
    from doc_parser.cli.main import _build_batch_config

    args = _parse([
        "--input-dir", str(tmp_path), "--content-type", "documento", "--model", "openai/gpt-5.2", "--language", "en",
        "--output-mode", "kb_densa", "--output-artifacts", "procedura", "--parallel", "5", "--requester", "x@y",
    ])
    assert _build_batch_config(args).settings == GlobalSettings("documento", "openai/gpt-5.2", "en", "kb_densa", "procedura", 5, "x@y")


def test_help_shows_real_defaults_not_none() -> None:
    from doc_parser.cli.main import build_parser

    help_text = build_parser().format_help()
    assert "default: None" not in help_text
    for default in ("anthropic/claude-haiku-4.5", "documentazione", "cli@local", "html_standalone,procedura,glossario,rag_chunks"):
        assert default in help_text
    assert "--resume" in help_text


@pytest.mark.parametrize("other", [["--runs-file", "r.yaml"], ["--input-dir", "in"], ["--urls-file", "u.txt"]])
def test_resume_is_exclusive_with_batch_sources(other, settings) -> None:  # noqa: F811
    with pytest.raises(SystemExit, match="--resume"):
        _main(["--resume", "abc", *other], settings)


@pytest.mark.parametrize("flag", [["--requester", "x@y"], ["--parallel", "2"]])
def test_resume_rejects_flags_that_do_not_apply(flag, settings) -> None:  # noqa: F811
    with pytest.raises(SystemExit, match="non applicabile con --resume"):
        _main(["--resume", "abc", *flag], settings)


def test_resume_end_to_end_with_new_model(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    step1 = FnProvider([])
    sonnet = FnProvider([consolidation_response(), step2_echo()])
    patch_providers(monkeypatch, {STEP1_MODEL: step1, SONNET_MODEL: sonnet})

    child = _main(["--resume", mother.run_id, "--model", SONNET_MODEL], settings)

    assert child.status == RunStatus.DONE
    assert child.resume_of_run_id == mother.run_id
    assert child.model_id == SONNET_MODEL and child.step1_cost_eur == 0
    assert step1.calls == []
    assert (child.requester_upn, child.session_id) == (mother.requester_upn, mother.session_id)
    assert child.output_artifacts == mother.output_artifacts
    assert len(SqliteRepository(settings.data_dir).list_runs()) == 2


def test_resume_without_model_uses_mothers_and_output_artifacts_override(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    patch_providers(monkeypatch, {STEP1_MODEL: FnProvider([]), OPENROUTER_MODEL: FnProvider([consolidation_response(), step2_echo()])})

    child = _main(["--resume", mother.run_id, "--output-artifacts", "procedura,pptx"], settings)

    assert child.status == RunStatus.DONE
    assert child.model_id == OPENROUTER_MODEL
    assert child.output_artifacts == "procedura,pptx"


def test_resume_with_different_language_is_refused_before_creating_a_run(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    with pytest.raises(SystemExit, match="--language en"):
        _main(["--resume", mother.run_id, "--language", "en"], settings)
    assert len(SqliteRepository(settings.data_dir).list_runs()) == 1


def test_resume_with_same_language_is_allowed(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    patch_providers(monkeypatch, {STEP1_MODEL: FnProvider([]), OPENROUTER_MODEL: FnProvider([consolidation_response(), step2_echo()])})
    assert _main(["--resume", mother.run_id, "--language", "it"], settings).status == RunStatus.DONE


def test_resume_of_mother_not_failed_is_refused_before_creating_a_run(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    repo.update_run(mother.run_id, status=RunStatus.DONE)
    with pytest.raises(SystemExit, match="solo le run fallite"):
        _main(["--resume", mother.run_id], settings)
    assert len(SqliteRepository(settings.data_dir).list_runs()) == 1


def test_resume_unknown_model_is_refused(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    with pytest.raises(SystemExit, match="non presente in models.yaml"):
        _main(["--resume", mother.run_id, "--model", "modello-inventato"], settings)


def test_resume_failing_again_exits_non_zero(monkeypatch, repo, settings) -> None:  # noqa: F811
    mother = _failed_mother(monkeypatch, repo, settings)
    truncated = ('{"title": "troncato', 1, 1)
    patch_providers(monkeypatch, {OPENROUTER_MODEL: FnProvider([truncated] * (settings.retry_max_attempts + 1))})
    with pytest.raises(SystemExit) as exc:
        _main(["--resume", mother.run_id], settings)
    assert exc.value.code == 1
