from pathlib import Path

import yaml

from doc_parser.core.pricing import compute_cost, get_model, load_models_config


def _write_models(tmp_path: Path) -> Path:
    config = {
        "pricing_snapshot_date": "2026-07-16",
        "usd_eur_rate": 0.87,
        "step1_video_model": "gemini-3.1-pro-preview",
        "models": [
            {
                "id": "gemini-2.5-flash-lite",
                "label": "Gemini 2.5 Flash Lite",
                "family": "gemini",
                "backend": "gemini",
                "price_input_eur_per_1m": 0.087,
                "price_output_eur_per_1m": 0.348,
                "native_file_input": True,
            },
            {
                "id": "anthropic/claude-haiku-4.5",
                "label": "Claude Haiku 4.5",
                "family": "anthropic",
                "backend": "openrouter",
                "price_input_eur_per_1m": 0.87,
                "price_output_eur_per_1m": 4.35,
                "native_file_input": True,
            },
        ],
    }
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_load_models_config(tmp_path: Path) -> None:
    config = load_models_config(_write_models(tmp_path))
    assert config.step1_video_model == "gemini-3.1-pro-preview"
    assert len(config.models) == 2


def test_get_model_found_and_missing(tmp_path: Path) -> None:
    path = _write_models(tmp_path)
    assert get_model(path, "gemini-2.5-flash-lite") is not None
    assert get_model(path, "modello-inesistente") is None


def test_compute_cost_with_snapshot(tmp_path: Path) -> None:
    path = _write_models(tmp_path)
    snapshot = compute_cost("gemini-2.5-flash-lite", 1_000_000, 100_000, path)
    assert snapshot is not None
    assert snapshot.cost_eur == round(0.087 + 0.0348, 6)
    assert snapshot.unit_price_in == 0.087
    assert snapshot.unit_price_out == 0.348


def test_compute_cost_zero_tokens(tmp_path: Path) -> None:
    path = _write_models(tmp_path)
    snapshot = compute_cost("gemini-2.5-flash-lite", 0, 0, path)
    assert snapshot is not None
    assert snapshot.cost_eur == 0.0


def test_compute_cost_unknown_model_returns_none(tmp_path: Path) -> None:
    path = _write_models(tmp_path)
    assert compute_cost("modello-inesistente", 100, 100, path) is None


def test_repo_models_yaml_covers_all_nine_models() -> None:
    models_file = Path(__file__).resolve().parent.parent.parent / "models.yaml"
    config = load_models_config(models_file)
    assert len(config.models) == 9
    for model in config.models:
        snapshot = compute_cost(model.id, 1000, 1000, models_file)
        assert snapshot is not None and snapshot.cost_eur > 0
    assert get_model(models_file, config.step1_video_model) is not None
