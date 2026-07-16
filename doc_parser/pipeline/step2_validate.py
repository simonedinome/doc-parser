"""Validazione strutturale della risposta dello step 2.

Verifica che lo step 2 abbia preservato ID di procedure/concetti, numero e
timestamp degli step, e la cardinalità di procedure/concetti/step rispetto
al JSON grezzo di partenza.
"""

from __future__ import annotations


class Step2ValidationError(ValueError):
    """Il JSON riscritto dallo step 2 viola il vincolo di preservazione ID/timestamp."""


def _step_signature(step: dict) -> tuple:
    return (
        step.get("number"),
        step.get("timestamp", ""),
        tuple(step.get("source_timestamps", []) or []),
    )


def validate_step2_output(raw_data: dict, rewritten_data: dict) -> None:
    """Solleva Step2ValidationError se *rewritten_data* viola il vincolo."""
    for key in ("procedures", "concepts"):
        raw_items = raw_data.get(key, []) or []
        rewritten_items = rewritten_data.get(key, []) or []
        if len(raw_items) != len(rewritten_items):
            raise Step2ValidationError(
                f"Cardinalità di '{key}' cambiata: {len(raw_items)} -> {len(rewritten_items)}"
            )
        raw_ids = [item.get("id") for item in raw_items]
        rewritten_ids = [item.get("id") for item in rewritten_items]
        if raw_ids != rewritten_ids:
            raise Step2ValidationError(f"ID di '{key}' alterati: {raw_ids} -> {rewritten_ids}")

    raw_procs = raw_data.get("procedures", []) or []
    rewritten_procs = rewritten_data.get("procedures", []) or []
    for raw_proc, rewritten_proc in zip(raw_procs, rewritten_procs):
        raw_steps = raw_proc.get("steps", []) or []
        rewritten_steps = rewritten_proc.get("steps", []) or []
        if len(raw_steps) != len(rewritten_steps):
            raise Step2ValidationError(
                f"Cardinalità di step nella procedura '{raw_proc.get('id')}' cambiata: "
                f"{len(raw_steps)} -> {len(rewritten_steps)}"
            )
        for raw_step, rewritten_step in zip(raw_steps, rewritten_steps):
            if _step_signature(raw_step) != _step_signature(rewritten_step):
                raise Step2ValidationError(
                    f"Step {raw_step.get('number')} della procedura '{raw_proc.get('id')}' "
                    f"ha ID/timestamp alterati: {_step_signature(raw_step)} -> "
                    f"{_step_signature(rewritten_step)}"
                )
