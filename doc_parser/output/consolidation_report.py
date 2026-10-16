"""Sezioni del log.txt per le run consolidate: fonti, discordanze risolte,
contenuti scartati, slide non incluse e avvisi.

Tutto viene dal JSON finale (``source_inputs`` e ``consolidation_log``, che
il codice calcola e lo step 2 non tocca): per le run senza consolidamento
non produce righe e il log resta quello di sempre.
"""

from __future__ import annotations

from doc_parser.output.strings import get_strings


def _kind(kind: str | None, s: dict[str, str]) -> str:
    return s.get(f"kind_{kind}", kind or "")


def _source_label(ref: dict, s: dict[str, str]) -> str:
    """Es. "webinar.mp4 (webinar, registrato il 2026-06-03) · 00:10, 05:00"."""
    if ref.get("slide") is not None:
        return f"{ref.get('filename', '')} ({_kind('slide', s)}) · {s['report_slide']} {ref['slide']}"
    date = f"{s['report_recorded']} {ref['recorded_at']}" if ref.get("recorded_at") else s["report_no_date"]
    label = f"{ref.get('filename', '')} ({_kind(ref.get('kind'), s)}, {date})"
    timestamps = ", ".join(ref.get("timestamps") or [])
    if timestamps:
        label += f" · {timestamps}"
    if ref.get("step_title"):
        label += f" · «{ref['step_title']}»"
    return label


def _is_more_recent(discarded: dict, chosen: dict) -> bool:
    return bool(discarded.get("recorded_at") and chosen.get("recorded_at") and discarded["recorded_at"] > chosen["recorded_at"])


def build_consolidation_lines(data: dict, language: str) -> list[str]:
    log = data.get("consolidation_log")
    if not log:
        return []
    s = get_strings(language)
    lines: list[str] = []

    def section(title: str) -> None:
        lines.extend(["", f"== {title} =="])

    section(s["report_sources"])
    for source in data.get("source_inputs", []):
        if source.get("role") == "slides":
            lines.append(
                f"- {source['input_id']} · {_kind('slide', s)} · {source['filename']} · {source.get('pages', '?')} {s['report_pages']}"
            )
        else:
            date = f"{s['report_recorded']} {source['recorded_at']}" if source.get("recorded_at") else s["report_no_date"]
            lines.append(f"- {source['input_id']} · {_kind(source.get('kind'), s)} · {date} · {source['filename']}")
    if log.get("priority_order"):
        lines.append(f"{s['report_priority']}: {' > '.join(log['priority_order'])}")

    section(s["report_conflicts"])
    conflicts = log.get("conflicts", [])
    if not conflicts:
        lines.append(s["report_no_conflicts"])
    for conflict in conflicts:
        chosen = conflict["chosen"]
        lines.append(f"- {s['report_topic']}: {conflict.get('topic', '')}")
        lines.append(f"  {s['report_kept']}: {_source_label(chosen, s)}")
        for discarded in conflict.get("discarded", []):
            prefix = f"{s['report_recency_warning']} · " if _is_more_recent(discarded, chosen) else ""
            lines.append(f"  {prefix}{s['report_discarded']}: {_source_label(discarded, s)}")
        if conflict.get("reason"):
            lines.append(f"  {s['report_reason']}: {conflict['reason']}")

    section(s["report_dropped"])
    dropped = log.get("dropped", [])
    if not dropped:
        lines.append(s["report_no_dropped"])
    for item in dropped:
        reason = f": {item['reason']}" if item.get("reason") else ""
        lines.append(f"- {_source_label(item, s)}{reason}")

    section(s["report_slides"])
    skipped = log.get("skipped_slides", [])
    uncovered = log.get("uncovered_slides", [])
    if not skipped and not uncovered:
        lines.append(s["report_no_slides"])
    for item in skipped:
        lines.append(f"- {s['report_slide'].capitalize()} {item['slide']}: {item.get('reason', '')}")
    for number in uncovered:
        lines.append(f"- {s['report_slide'].capitalize()} {number}: {s['report_uncovered_slide']}")

    section(s["report_warnings"])
    warnings = log.get("warnings", [])
    if not warnings:
        lines.append(s["report_no_warnings"])
    lines.extend(f"- {warning}" for warning in warnings)
    return lines
