"""Configurazione della coda YAML multi-run: parallelismo, checkpoint, nuovi
parametri (modello, lingua, output_mode) sul core condiviso con la UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from doc_parser.pipeline.profiles import CONTENT_TYPES


@dataclass
class InputSource:
    source: str  # "file" | "url"
    order: int = 0
    path: str | None = None
    url: str | None = None


@dataclass
class RunSettings:
    content_type: str | None = None
    model_id: str | None = None
    language: str | None = None
    output_mode: str | None = None
    output_artifacts: str | None = None


@dataclass
class RunConfig:
    name: str
    inputs: list[InputSource]
    settings: RunSettings = field(default_factory=RunSettings)


@dataclass
class GlobalSettings:
    content_type: str = "video"
    model_id: str = "anthropic/claude-haiku-4.5"
    language: str = "it"
    output_mode: str = "documentazione"
    output_artifacts: str = "html_standalone,procedura,glossario,rag_chunks"
    parallel_runs: int = 3
    requester_upn: str = "cli@local"


@dataclass
class RunsConfig:
    settings: GlobalSettings
    runs: list[RunConfig]


def resolve_run_settings(global_settings: GlobalSettings, run_settings: RunSettings) -> dict:
    """Merge delle impostazioni globali con gli override per-run."""
    return {
        "content_type": run_settings.content_type or global_settings.content_type,
        "model_id": run_settings.model_id or global_settings.model_id,
        "language": run_settings.language or global_settings.language,
        "output_mode": run_settings.output_mode or global_settings.output_mode,
        "output_artifacts": run_settings.output_artifacts or global_settings.output_artifacts,
    }


def load_runs_config(path: Path) -> RunsConfig:
    """Carica e valida un file YAML di coda run."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    raw_settings = raw.get("settings", {}) or {}
    global_settings = GlobalSettings(
        content_type=raw_settings.get("content_type", "video"),
        model_id=raw_settings.get("model_id", "anthropic/claude-haiku-4.5"),
        language=raw_settings.get("language", "it"),
        output_mode=raw_settings.get("output_mode", "documentazione"),
        output_artifacts=raw_settings.get(
            "output_artifacts", "html_standalone,procedura,glossario,rag_chunks"
        ),
        parallel_runs=raw_settings.get("parallel_runs", 3),
        requester_upn=raw_settings.get("requester_upn", "cli@local"),
    )
    _validate_content_type(global_settings.content_type, "settings")

    runs: list[RunConfig] = []
    for raw_run in raw.get("runs", []):
        name = raw_run.get("name")
        if not name:
            raise ValueError("Ogni run deve avere un campo 'name'.")

        inputs: list[InputSource] = []
        for raw_input in raw_run.get("inputs", raw_run.get("videos", [])):
            source = raw_input.get("source")
            if source not in ("file", "url"):
                raise ValueError(
                    f"Run '{name}': 'source' deve essere 'file' o 'url', trovato: {source!r}"
                )
            order = raw_input.get("order", 0)
            path = raw_input.get("path")
            url = raw_input.get("url")
            if source == "file" and not path:
                raise ValueError(f"Run '{name}': source='file' richiede il campo 'path'.")
            if source == "url" and not url:
                raise ValueError(f"Run '{name}': source='url' richiede il campo 'url'.")
            inputs.append(InputSource(source=source, order=order, path=path, url=url))

        if not inputs:
            raise ValueError(f"Run '{name}': la lista 'inputs' non può essere vuota.")

        raw_run_settings = raw_run.get("settings", {}) or {}
        run_settings = RunSettings(
            content_type=raw_run_settings.get("content_type"),
            model_id=raw_run_settings.get("model_id"),
            language=raw_run_settings.get("language"),
            output_mode=raw_run_settings.get("output_mode"),
            output_artifacts=raw_run_settings.get("output_artifacts"),
        )
        if run_settings.content_type is not None:
            _validate_content_type(run_settings.content_type, f"run '{name}'")

        runs.append(
            RunConfig(
                name=name,
                inputs=sorted(inputs, key=lambda i: i.order),
                settings=run_settings,
            )
        )

    return RunsConfig(settings=global_settings, runs=runs)


def _validate_content_type(content_type: str, where: str) -> None:
    if content_type not in CONTENT_TYPES:
        raise ValueError(
            f"Tipo di contenuto non valido in {where}: {content_type!r} "
            f"(atteso uno tra {CONTENT_TYPES})"
        )
