"""Merge di risultati multi-video in un unico documento per la run."""

from __future__ import annotations


def merge_run_results(results: list[tuple[dict, str]], run_name: str) -> dict:
    """Unisce più dict di risultato (uno per video) in un documento unificato.

    Parameters
    ----------
    results:
        Lista di tuple (data_dict, nome_video) in ordine crescente di ``order``.
    run_name:
        Titolo di fallback se nessun video ne fornisce uno.
    """
    title = run_name
    for data, _ in results:
        candidate = data.get("title", "")
        if candidate:
            title = candidate
            break

    summaries = [data.get("summary", "") for data, _ in results if data.get("summary")]
    summary = " \n".join(summaries)

    seen_prereqs: set[str] = set()
    prerequisites: list[str] = []
    for data, _ in results:
        for p in data.get("prerequisites", []):
            key = p.lower()
            if key not in seen_prereqs:
                seen_prereqs.add(key)
                prerequisites.append(p)

    seen_concept_titles: set[str] = set()
    all_concepts: list[dict] = []
    con_global_idx = 1
    for data, _ in results:
        for con in data.get("concepts", []):
            key = con.get("title", "").lower()
            if key not in seen_concept_titles:
                seen_concept_titles.add(key)
                new_con = dict(con)
                new_con["id"] = f"con_{con_global_idx:03d}"
                con_global_idx += 1
                all_concepts.append(new_con)

    all_procedures: list[dict] = []
    global_idx = 1
    for data, _ in results:
        for proc in data.get("procedures", []):
            new_proc = dict(proc)
            new_proc["id"] = f"proc_{global_idx:03d}"
            global_idx += 1
            all_procedures.append(new_proc)

    seen_terms: set[str] = set()
    glossary: list[dict] = []
    for data, _ in results:
        for entry in data.get("glossary", []):
            key = entry.get("term", "").lower()
            if key not in seen_terms:
                seen_terms.add(key)
                glossary.append(entry)

    seen_notes: set[str] = set()
    notes: list[str] = []
    for data, _ in results:
        for n in data.get("notes", []):
            if n not in seen_notes:
                seen_notes.add(n)
                notes.append(n)

    merged: dict = {
        "title": title,
        "summary": summary,
        "prerequisites": prerequisites,
        "procedures": all_procedures,
        "glossary": glossary,
        "notes": notes,
    }
    if all_concepts:
        merged["concepts"] = all_concepts
    return merged
