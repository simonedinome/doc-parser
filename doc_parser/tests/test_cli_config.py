from pathlib import Path

import pytest
import yaml

from doc_parser.cli.config import GlobalSettings, RunSettings, load_runs_config, resolve_run_settings


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "runs.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_runs_config_defaults_and_overrides(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        {
            "settings": {"content_type": "video", "model_id": "openai/gpt-5.2", "parallel_runs": 5},
            "runs": [
                {
                    "name": "run1",
                    "inputs": [{"source": "file", "path": "a.mp4", "order": 2}, {"source": "file", "path": "b.mp4", "order": 1}],
                },
                {
                    "name": "run2",
                    "inputs": [{"source": "url", "url": "https://example.com/v.mp4"}],
                    "settings": {"content_type": "documento", "output_mode": "kb_densa"},
                },
            ],
        },
    )
    config = load_runs_config(path)
    assert config.settings.content_type == "video"
    assert config.settings.model_id == "openai/gpt-5.2"
    assert config.settings.parallel_runs == 5
    assert len(config.runs) == 2

    run1 = config.runs[0]
    assert [i.path for i in run1.inputs] == ["b.mp4", "a.mp4"]  # ordinati per 'order'

    run2 = config.runs[1]
    assert run2.settings.content_type == "documento"
    assert run2.settings.output_mode == "kb_densa"


def test_load_runs_config_missing_name_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"inputs": [{"source": "file", "path": "a.mp4"}]}]})
    with pytest.raises(ValueError, match="campo 'name'"):
        load_runs_config(path)


def test_load_runs_config_empty_inputs_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"name": "r1", "inputs": []}]})
    with pytest.raises(ValueError, match="non può essere vuota"):
        load_runs_config(path)


def test_load_runs_config_invalid_source_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"name": "r1", "inputs": [{"source": "ftp", "path": "a"}]}]})
    with pytest.raises(ValueError, match="'file' o 'url'"):
        load_runs_config(path)


def test_load_runs_config_file_source_requires_path(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"name": "r1", "inputs": [{"source": "file"}]}]})
    with pytest.raises(ValueError, match="richiede il campo 'path'"):
        load_runs_config(path)


def test_load_runs_config_invalid_content_type_raises(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        {"settings": {"content_type": "pdf"}, "runs": [{"name": "r1", "inputs": [{"source": "file", "path": "a.pdf"}]}]},
    )
    with pytest.raises(ValueError, match="non valido"):
        load_runs_config(path)


def test_load_runs_config_accepts_legacy_videos_key(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"name": "r1", "videos": [{"source": "file", "path": "a.mp4"}]}]})
    config = load_runs_config(path)
    assert config.runs[0].inputs[0].path == "a.mp4"


def test_resolve_run_settings_merges_with_global_fallback() -> None:
    global_settings = GlobalSettings(
        content_type="video",
        model_id="m1",
        language="it",
        output_mode="documentazione",
        output_artifacts="html_standalone,procedura,glossario,rag_chunks",
    )
    run_settings = RunSettings(model_id="m2")
    effective = resolve_run_settings(global_settings, run_settings)
    assert effective["model_id"] == "m2"
    assert effective["content_type"] == "video"


def test_load_runs_config_reads_kind_and_recorded_at(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        {
            "runs": [
                {
                    "name": "serie",
                    "inputs": [
                        {"source": "file", "path": "w.mp4", "kind": "webinar", "recorded_at": "2026-06-03"},
                        {"source": "file", "path": "p.mp4", "kind": "pillola"},
                        {"source": "file", "path": "s.pdf"},
                    ],
                }
            ]
        },
    )
    inputs = load_runs_config(path).runs[0].inputs
    assert [(i.kind, i.recorded_at) for i in inputs] == [("webinar", "2026-06-03"), ("pillola", None), (None, None)]


def test_load_runs_config_accepts_unquoted_yaml_date(tmp_path: Path) -> None:
    path = tmp_path / "runs.yaml"
    path.write_text(
        "runs:\n  - name: r1\n    inputs:\n      - source: file\n        path: a.mp4\n        recorded_at: 2026-06-03\n",
        encoding="utf-8",
    )
    assert load_runs_config(path).runs[0].inputs[0].recorded_at == "2026-06-03"


def test_load_runs_config_invalid_kind_names_the_run(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"name": "serie-x", "inputs": [{"source": "file", "path": "a.mp4", "kind": "corso"}]}]})
    with pytest.raises(ValueError, match="Run 'serie-x'.*Tipo di video non valido"):
        load_runs_config(path)


def test_load_runs_config_invalid_date_names_the_run(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, {"runs": [{"name": "serie-y", "inputs": [{"source": "file", "path": "a.mp4", "recorded_at": "03/06/2026"}]}]})
    with pytest.raises(ValueError, match="Run 'serie-y'.*Data di registrazione non valida"):
        load_runs_config(path)


def test_runs_example_yaml_loads_with_series_example() -> None:
    example = Path(__file__).resolve().parent.parent.parent / "runs.example.yaml"
    config = load_runs_config(example)
    serie = next(r for r in config.runs if r.name == "formazione-gestionale")
    assert [i.kind for i in serie.inputs] == ["webinar", "webinar", "pillola", None]
    assert serie.inputs[0].recorded_at == "2026-06-03"
    assert "pptx" in serie.settings.output_artifacts
