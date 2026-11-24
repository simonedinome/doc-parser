"""Builder del TXT "Knowledge base" per la Data Library di Agentforce.

La Data Library ri-spezza ogni file in chunk (circa 512 token) e all'agente
arriva solo il chunk recuperato. Per questo il TXT è fatto di sezioni brevi e
autosufficienti: ogni sezione entro ``KB_SECTION_MAX_CHARS`` caratteri, con
un'intestazione che ripete tipo, titolo e argomento, senza rimandi ad altre
parti del file né dati di provenienza (fonti, timestamp, slide).
"""

from __future__ import annotations

import re

from doc_parser.output.strings import get_strings

# Circa 400 token: margine sotto i ~512 token dei chunk della Data Library.
# Da ritarare dopo aver visto l'anteprima dei chunk generati nell'org.
KB_SECTION_MAX_CHARS = 1500
SECTION_SEPARATOR = "=" * 40
_PART_RESERVE = 24  # spazio per " (parte 12 di 12)"
_MAX_HEADER_TITLE = 160
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


def _hard_split(text: str, budget: int) -> list[str]:
    pieces: list[str] = []
    while len(text) > budget:
        cut = text.rfind(" ", 0, budget)
        cut = cut if cut > budget // 2 else budget
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        pieces.append(text)
    return pieces


def _split_block(block: str, budget: int) -> list[str]:
    """Spezza un blocco troppo lungo su righe, poi frasi, poi parole."""
    if len(block) <= budget:
        return [block]
    pieces: list[str] = []
    for line in block.split("\n"):
        if len(line) <= budget:
            pieces.append(line)
            continue
        for sentence in _SENTENCE_END.split(line):
            pieces.extend(_hard_split(sentence, budget) if len(sentence) > budget else [sentence])
    return _pack(pieces, budget, joiner="\n")


def _pack(blocks: list[str], budget: int, joiner: str = "\n\n") -> list[str]:
    """Unisce i blocchi in parti di al massimo *budget* caratteri, senza
    spezzare un blocco che ci sta intero."""
    parts: list[str] = []
    current = ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        for piece in _split_block(block, budget) if len(block) > budget else [block]:
            candidate = f"{current}{joiner}{piece}" if current else piece
            if len(candidate) <= budget:
                current = candidate
            else:
                parts.append(current)
                current = piece
    if current:
        parts.append(current)
    return parts


class _Writer:
    def __init__(self, topic: str, language: str, max_chars: int) -> None:
        self.s = get_strings(language)
        self.topic = topic
        self.max_chars = max_chars
        self.sections: list[str] = []

    def _header(self, kind: str, title: str, part: str = "") -> str:
        title = title.strip()
        if len(title) > _MAX_HEADER_TITLE:
            title = title[: _MAX_HEADER_TITLE - 1].rstrip() + "…"
        label = f"{kind}: {title}" if title else kind
        return f"### {label}{part} | {self.s['kb_topic']}: {self.topic}"

    def add(self, kind: str, title: str, blocks: list[str]) -> None:
        budget = self.max_chars - len(self._header(kind, title)) - 2 - _PART_RESERVE
        parts = _pack(blocks, max(budget, 200))
        for k, body in enumerate(parts, 1):
            part = f" ({self.s['kb_part'].format(k=k, n=len(parts))})" if len(parts) > 1 else ""
            self.sections.append(f"{self._header(kind, title, part)}\n\n{body}")

    def text(self) -> str:
        return f"\n\n{SECTION_SEPARATOR}\n\n".join(self.sections) + "\n"


def build_kb_txt(data: dict, language: str = "it", max_chars: int = KB_SECTION_MAX_CHARS) -> str:
    """Costruisce il TXT KB dal JSON finale: panoramica, concetti, procedure,
    domande e risposte, glossario e note generali, in sezioni autosufficienti."""
    s = get_strings(language)
    title = (data.get("title") or "").strip()
    writer = _Writer(title or s["kb_untitled"], language, max_chars)

    overview = [title, data.get("summary", "") or ""]
    prerequisites = [p for p in data.get("prerequisites", []) or [] if str(p).strip()]
    if prerequisites:
        overview.append(f"{s['kb_prerequisites']}:\n" + "\n".join(f"- {p}" for p in prerequisites))
    writer.add(s["kb_overview"], "", overview)

    for con in data.get("concepts", []) or []:
        paragraphs = str(con.get("content", "")).split("\n\n")
        writer.add(s["kb_concept"], str(con.get("title", "")), paragraphs)

    for proc in data.get("procedures", []) or []:
        steps = []
        for step in proc.get("steps", []) or []:
            lines = [f"{s['kb_step']} {step.get('number', '')} — {step.get('title', '')}".strip(), str(step.get("description", ""))]
            if step.get("notes"):
                lines.append(f"{s['kb_step_notes']}: {step['notes']}")
            steps.append("\n".join(line for line in lines if line))
        writer.add(s["kb_procedure"], str(proc.get("title", "")), steps)

    for item in data.get("qa", []) or []:
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        writer.add(s["kb_qa"], question, [f"{s['kb_question']}: {question}\n{s['kb_answer']}: {answer}"])

    glossary = [
        f"{entry.get('term', '')}: {entry.get('definition', '')}"
        for entry in data.get("glossary", []) or []
        if entry.get("term")
    ]
    if glossary:
        writer.add(s["kb_glossary"], "", glossary)

    notes = [f"- {note}" for note in data.get("notes", []) or [] if str(note).strip()]
    if notes:
        writer.add(s["kb_notes"], "", notes)

    return writer.text()
