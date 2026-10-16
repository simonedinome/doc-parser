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
                result[key] = _render_page(doc, page_num, out_path)
    finally:
        doc.close()

    return result


def _render_page(doc, page_num: int, out_path: Path) -> Path | None:
    """Renderizza la pagina *page_num* (da 1) di un documento PyMuPDF aperto."""
    import fitz  # PyMuPDF

    try:
        page = doc[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        pix.save(str(out_path))
        return out_path if out_path.exists() else None
    except Exception:
        return None


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

            out_path = output_dir / f"{proc_id}_step_{num:03d}.png"
            result[key] = _grab_frame(video_path, ts, seconds, duration, out_path, f"step {num} di {proc_id}", warn)

    return result


def _grab_frame(
    video_path: Path,
    ts: str,
    seconds: float,
    duration: float | None,
    out_path: Path,
    label: str,
    warn: Callable[[str], None] | None,
) -> Path | None:
    """Estrae con ffmpeg il fotogramma a *seconds*; se oltre la durata del
    video lo clampa a fine video e lo segnala via *warn*."""
    if duration is not None and seconds > duration:
        clamped = max(0.0, duration - 0.5)
        if warn is not None:
            warn(
                f"Timestamp {ts} ({label}) oltre la durata del "
                f"video ({duration:.1f}s): clampato a {clamped:.1f}s"
            )
        seconds = clamped

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
        return out_path if out_path.exists() else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def extract_step_images(
    data: dict,
    video_paths: dict[str, Path],
    slides_pdf: Path | None,
    output_dir: Path,
    warn: Callable[[str], None] | None = None,
) -> dict[tuple[str, int], str | None]:
    """Immagini del JSON consolidato, dalla provenienza calcolata dal codice.

    Immagine principale di ogni step (``{proc}_step_{n:03d}.png``), primo
    candidato riuscito in quest'ordine: fotogramma di un webinar (dal più
    autorevole, cioè il più recente), prima slide, fotogramma di una pillola.
    Immagini secondarie: ``{proc}_step_{n:03d}_slide.png`` se lo step ha slide
    e l'immagine principale non è già una slide; ``{con_id}_slide.png`` per i
    concetti con slide.

    Ritorna ``{(proc_id, numero): "video" | "slide" | None}``, l'origine
    dell'immagine principale.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[str, float | None] = {}
    doc = _open_pdf(slides_pdf)

    def frame(source: dict, out_path: Path, label: str) -> Path | None:
        video_path = video_paths.get(source["input_id"])
        timestamps = source.get("timestamps") or []
        if video_path is None or not timestamps:
            return None
        try:
            seconds = _timestamp_to_seconds(timestamps[0])
        except ValueError:
            return None
        if source["input_id"] not in durations:
            durations[source["input_id"]] = video_duration_seconds(video_path)
        label = f"{label}, {source['filename']}"
        return _grab_frame(video_path, timestamps[0], seconds, durations[source["input_id"]], out_path, label, warn)

    def slide(number: int, out_path: Path) -> Path | None:
        if doc is None or not 1 <= number <= len(doc):
            return None
        return _render_page(doc, number, out_path)

    origins: dict[tuple[str, int], str | None] = {}
    try:
        for proc in data.get("procedures", []):
            for step in proc.get("steps", []):
                proc_id, num = proc["id"], step["number"]
                label = f"step {num} di {proc_id}"
                main_path = output_dir / f"{proc_id}_step_{num:03d}.png"
                sources = step.get("sources", []) or []
                slides = step.get("source_slides", []) or []
                candidates = (
                    [("video", s) for s in sources if s.get("kind") != "pillola"]
                    + [("slide", n) for n in slides[:1]]
                    + [("video", s) for s in sources if s.get("kind") == "pillola"]
                )
                origin = None
                for kind, candidate in candidates:
                    done = frame(candidate, main_path, label) if kind == "video" else slide(candidate, main_path)
                    if done is not None:
                        origin = kind
                        break
                if origin is None:
                    main_path.unlink(missing_ok=True)  # niente file parziali di estrazioni fallite
                origins[(proc_id, num)] = origin
                if slides and origin != "slide":
                    slide(slides[0], output_dir / f"{proc_id}_step_{num:03d}_slide.png")
        for con in data.get("concepts", []):
            slides = con.get("source_slides", []) or []
            if slides:
                slide(slides[0], output_dir / f"{con['id']}_slide.png")
    finally:
        if doc is not None:
            doc.close()
    return origins


def _open_pdf(pdf_path: Path | None):
    if pdf_path is None:
        return None
    try:
        import fitz  # PyMuPDF

        return fitz.open(str(pdf_path))
    except Exception:
        return None
