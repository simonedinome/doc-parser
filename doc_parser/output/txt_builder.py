"""Builder testuali (procedura.txt, glossario.txt) dal JSON finale."""

from __future__ import annotations

from datetime import date

from doc_parser.output.strings import get_strings


def build_glossario(data: dict, language: str = "it") -> str:
    """Costruisce il file di testo del glossario dal JSON finale."""
    s = get_strings(language)
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(s["glossary_header"])
    lines.append("=" * 60)
    lines.append("")

    glossary = data.get("glossary", [])
    if not glossary:
        lines.append(s["no_glossary"])
    else:
        for entry in glossary:
            term = entry.get("term", "")
            definition = entry.get("definition", "")
            lines.append(f"  {term}")
            lines.append(f"    {definition}")
            lines.append("")

    return "\n".join(lines)


def build_procedura(data: dict, source_filename: str, language: str = "it") -> str:
    """Costruisce il file di testo della procedura dal JSON finale.

    Itera su ``procedures[]`` (ed eventuali ``concepts[]``) e produce un
    output pulito, senza caratteri decorativi, adatto anche a tokenizer.
    """
    s = get_strings(language)
    title: str = data.get("title", "")
    summary: str = data.get("summary", "")
    prerequisites: list[str] = data.get("prerequisites", [])
    procedures: list[dict] = data.get("procedures", [])
    notes: list[str] = data.get("notes", [])

    today = date.today().isoformat()

    lines: list[str] = []

    lines.append(title)
    lines.append(f"{s['source_label']}: {source_filename}")
    lines.append(f"{s['generated_on']}: {today}")
    lines.append("=" * 18)
    lines.append("")

    lines.append(s["summary_header"])
    lines.append(summary)
    lines.append("")

    lines.append(s["prerequisites_header"])
    if prerequisites:
        for i, prereq in enumerate(prerequisites, 1):
            lines.append(f"{i}. {prereq}")
    else:
        lines.append(s["no_prerequisites"])
    lines.append("")

    concepts: list[dict] = data.get("concepts", [])
    if concepts:
        lines.append(s["concepts_header"])
        lines.append("=" * 18)
        lines.append("")
        for con_idx, con in enumerate(concepts, 1):
            con_title: str = con.get("title", "")
            con_content: str = con.get("content", "")
            lines.append(f"{s['concept_label']} {con_idx} — {con_title}")
            lines.append(con_content)
            lines.append("")

    for proc_idx, proc in enumerate(procedures, 1):
        proc_title: str = proc.get("title", "")
        steps: list[dict] = proc.get("steps", [])

        lines.append(f"{s['procedure_label']} {proc_idx} — {proc_title}")
        lines.append("=" * 18)
        lines.append("")

        for step in steps:
            number: int = step.get("number", 0)
            step_title: str = step.get("title", "")
            description: str = step.get("description", "")
            step_notes: str = step.get("notes", "") or ""

            lines.append(f"{s['step_label']} {number} — {step_title}")
            lines.append(description)
            if step_notes:
                lines.append(f"{s['notes_label']}: {step_notes}")
            lines.append("")

    if notes:
        lines.append(s["general_notes_header"])
        for i, note in enumerate(notes, 1):
            lines.append(f"{i}. {note}")
        lines.append("")

    return "\n".join(lines)
