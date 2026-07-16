"""Estrazione screenshot dai video (ffmpeg) e dalle pagine PDF (PyMuPDF)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable


def _parse_page_ref(ts: str) -> int | None:
    """Interpreta un riferimento pagina tipo "Pagina 3", "Page 3" o "3"."""
    ts = ts.strip()
    try:
        return int(ts)
    except ValueError:
        pass
    m = re.search(r"\d+", ts)
    return int(m.group()) if m else None


def _step_timestamp(step: dict) -> str:
    """Timestamp più adatto per lo step: campo flat ``timestamp`` o primo di
    ``source_timestamps`` (webinar/hybrid)."""
    ts = step.get("timestamp", "")
    if ts:
        return ts
    src = step.get("source_timestamps")
    if isinstance(src, list) and src:
        return src[0]
    return ""


def extract_pdf_pages(
    pdf_path: Path,
    procedures: list[dict],
    output_dir: Path,
) -> dict[tuple[str, int], Path | None]:
    """Renderizza la pagina PDF corrispondente a ogni step.

    Ritorna la mappa ``{(proc_id, step_number): path_o_None}``.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {
            (proc["id"], step["number"]): None
            for proc in procedures
            for step in proc.get("steps", [])
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[tuple[str, int], Path | None] = {}

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return {
            (proc["id"], step["number"]): None
            for proc in procedures
            for step in proc.get("steps", [])
        }

    try:
        for proc in procedures:
            proc_id = proc["id"]
            for step in proc.get("steps", []):
                num: int = step["number"]
                key = (proc_id, num)
                ts = _step_timestamp(step)
                page_num = _parse_page_ref(ts)

                if page_num is None or page_num < 1 or page_num > len(doc):
                    result[key] = None
                    continue

                out_path = output_dir / f"{proc_id}_step_{num:03d}.png"
                try:
                    page = doc[page_num - 1]
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)
                    pix.save(str(out_path))
                    result[key] = out_path if out_path.exists() else None
                except Exception:
                    result[key] = None
    finally:
        doc.close()

    return result


def _timestamp_to_seconds(ts: str) -> float:
    """Converte un timestamp ``MM:SS`` o ``HH:MM:SS`` in secondi."""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"Formato timestamp non valido: {ts!r}")


def video_duration_seconds(video_path: Path) -> float | None:
    """Durata del video in secondi via ffprobe, None se non determinabile."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, check=True, timeout=30, text=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None


def extract_screenshots(
    video_path: Path,
    procedures: list[dict],
    output_dir: Path,
    warn: Callable[[str], None] | None = None,
) -> dict[tuple[str, int], Path | None]:
    """Estrae uno screenshot dal video per ogni timestamp di step.

    Se il timestamp supera la durata del video, viene clampato a fine video
    e la clamp è segnalata tramite *warn* (edge case: timestamp oltre durata).
    Ritorna la mappa ``{(proc_id, step_number): path_o_None}``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[tuple[str, int], Path | None] = {}
    duration = video_duration_seconds(video_path)

    for proc in procedures:
        proc_id = proc["id"]
        for step in proc.get("steps", []):
            num: int = step["number"]
            key = (proc_id, num)
            ts = _step_timestamp(step)

            if not ts:
                result[key] = None
                continue

            try:
                seconds = _timestamp_to_seconds(ts)
            except ValueError:
                result[key] = None
                continue

            if duration is not None and seconds > duration:
                clamped = max(0.0, duration - 0.5)
                if warn is not None:
                    warn(
                        f"Timestamp {ts} (step {num} di {proc_id}) oltre la durata del "
                        f"video ({duration:.1f}s): clampato a {clamped:.1f}s"
                    )
                seconds = clamped

            out_path = output_dir / f"{proc_id}_step_{num:03d}.png"
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(seconds),
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(out_path),
            ]

            try:
                subprocess.run(cmd, capture_output=True, check=True, timeout=30)
                result[key] = out_path if out_path.exists() else None
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                result[key] = None

    return result
