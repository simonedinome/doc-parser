"""Modelli disponibili e costi per run, letti da models.yaml (EUR, snapshot)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    label: str
    family: str
    backend: str
    price_input_eur_per_1m: float
    price_output_eur_per_1m: float
    native_file_input: bool = True


class ModelsConfig(BaseModel):
    pricing_snapshot_date: str
    usd_eur_rate: float
    step1_video_model: str
    models: list[ModelInfo]


def load_models_config(models_file: str | Path) -> ModelsConfig:
    data = yaml.safe_load(Path(models_file).read_text(encoding="utf-8"))
    return ModelsConfig(**data)


def get_model(models_file: str | Path, model_id: str) -> ModelInfo | None:
    config = load_models_config(str(models_file))
    for model in config.models:
        if model.id == model_id:
            return model
    return None


class CostSnapshot(BaseModel):
    cost_eur: float
    unit_price_in: float
    unit_price_out: float


def compute_cost(
    model_id: str,
    tokens_in: int,
    tokens_out: int,
    models_file: str | Path,
) -> CostSnapshot | None:
    model = get_model(models_file, model_id)
    if model is None:
        return None
    cost = (
        tokens_in * model.price_input_eur_per_1m + tokens_out * model.price_output_eur_per_1m
    ) / 1_000_000
    return CostSnapshot(
        cost_eur=round(cost, 6),
        unit_price_in=model.price_input_eur_per_1m,
        unit_price_out=model.price_output_eur_per_1m,
    )
