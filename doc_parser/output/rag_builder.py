"""Builder dei chunk RAG (JSONL) dal JSON finale."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _source_stem(source_filename: str) -> str:
    return Path(source_filename).stem


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _glossary_terms_in_content(content: str, glossary: list[dict]) -> list[str]:
    """Termini del glossario presenti (case-insensitive) in *content*."""
    content_lower = content.lower()
    return [entry["term"] for entry in glossary if entry.get("term", "").lower() in content_lower]


def build_rag_jsonl(data: dict, source_filename: str) -> str:
    """Costruisce una stringa JSONL (un oggetto JSON per riga) per l'ingestion RAG.

    Chunk prodotti:
    - un chunk di sommario per l'intero documento
    - un chunk per concetto (se presenti)
    - un chunk per step (con procedure_id e procedure_title)
    - un chunk di glossario
    """
    stem = _source_stem(source_filename)
    processed_at = _iso_now()
    title = data.get("title", "")
    summary = data.get("summary", "")
    prerequisites: list[str] = data.get("prerequisites", [])
    procedures: list[dict] = data.get("procedures", [])
    glossary: list[dict] = data.get("glossary", [])

    concepts: list[dict] = data.get("concepts", [])
    chunks: list[dict] = []

    prereq_str = ", ".join(prerequisites)
    summary_content = summary
    if prereq_str:
        summary_content = f"{summary}\n\nPrerequisiti: {prereq_str}"

    chunks.append({
        "chunk_id": f"{stem}_summary",
        "source_filename": source_filename,
        "chunk_type": "summary",
        "processed_at": processed_at,
        "title": title,
        "content": summary_content,
        "embedding_text": f"{title} {summary} {prereq_str}".strip(),
    })

    for con in concepts:
        con_id: str = con.get("id", "con_001")
        con_title: str = con.get("title", "")
        con_content: str = con.get("content", "")
        embedding_keywords: list[str] = con.get("embedding_keywords", [])
        if not isinstance(embedding_keywords, list):
            embedding_keywords = []
        keywords_str = " ".join(embedding_keywords)
        chunks.append({
            "chunk_id": f"{stem}_con_{con_id}",
            "source_filename": source_filename,
            "chunk_type": "concept",
            "processed_at": processed_at,
            "title": title,
            "concept_id": con_id,
            "concept_title": con_title,
            "content": con_content,
            "embedding_keywords": embedding_keywords,
            "embedding_text": f"{title} {con_title} {con_content} {keywords_str}".strip(),
        })

    for proc in procedures:
        proc_id: str = proc.get("id", "proc_001")
        proc_title: str = proc.get("title", "")
        for step in proc.get("steps", []):
            number: int = step.get("number", 0)
            step_title: str = step.get("title", "")
            description: str = step.get("description", "")
            notes: str = step.get("notes", "") or ""
            embedding_keywords: list[str] = step.get("embedding_keywords", [])
            if not isinstance(embedding_keywords, list):
                embedding_keywords = []

            content = description
            if notes:
                content = f"{description}\n\n{notes}"

            glossary_terms = _glossary_terms_in_content(content, glossary)

            keywords_str = " ".join(embedding_keywords)
            glossary_str = " ".join(glossary_terms)
            embedding_text = (
                f"{title} {proc_title} step {number} {step_title} {content} "
                f"{keywords_str} {glossary_str}"
            ).strip()

            chunks.append({
                "chunk_id": f"{stem}_proc_{proc_id}_step_{number:03d}",
                "source_filename": source_filename,
                "chunk_type": "step",
                "processed_at": processed_at,
                "title": title,
                "procedure_id": proc_id,
                "procedure_title": proc_title,
                "step_number": number,
                "step_title": step_title,
                "content": content,
                "glossary_terms": glossary_terms,
                "embedding_keywords": embedding_keywords,
                "embedding_text": embedding_text,
            })

    glossary_lines = [f"{entry.get('term', '')}: {entry.get('definition', '')}" for entry in glossary]
    glossary_content = "\n".join(glossary_lines)
    chunks.append({
        "chunk_id": f"{stem}_glossary",
        "source_filename": source_filename,
        "chunk_type": "glossary",
        "processed_at": processed_at,
        "content": glossary_content,
        "embedding_text": glossary_content,
    })

    return "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks)
