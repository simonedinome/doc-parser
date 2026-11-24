"""Builder HTML (standalone e folder) dal JSON finale."""

from __future__ import annotations

import base64
from pathlib import Path

from doc_parser.output.strings import get_strings

_CSS = """\
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem;
    background: #f8f9fa;
    color: #212529;
    line-height: 1.6;
}
h1 {
    color: #1a73e8;
    border-bottom: 3px solid #1a73e8;
    padding-bottom: 0.5rem;
}
h2 {
    color: #1a73e8;
    margin-top: 2rem;
}
h3 {
    color: #333;
}
.summary {
    background: #e8f0fe;
    border-left: 4px solid #1a73e8;
    padding: 1rem 1.5rem;
    margin: 1.5rem 0;
    border-radius: 0 8px 8px 0;
}
.toc {
    background: #fff;
    border: 1px solid #dadce0;
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin: 1.5rem 0;
}
.toc ul {
    margin: 0.5rem 0 0 0;
    padding-left: 1.25rem;
}
.toc a {
    color: #1a73e8;
    text-decoration: none;
}
.toc a:hover {
    text-decoration: underline;
}
.concept-section {
    background: #f0f4ff;
    border-left: 4px solid #5c6bc0;
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.5rem;
    margin: 1.5rem 0;
}
.concept-section h2 {
    color: #3949ab;
    margin-top: 0;
}
.procedure-section {
    margin-top: 2.5rem;
}
.step {
    background: #fff;
    border: 1px solid #dadce0;
    border-radius: 8px;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.step-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
}
.step-number {
    background: #1a73e8;
    color: #fff;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    font-size: 0.9rem;
    flex-shrink: 0;
}
.step img {
    max-width: 100%;
    border-radius: 6px;
    margin-top: 0.75rem;
    border: 1px solid #dadce0;
}
.step-images {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    align-items: start;
}
.step-images figure,
.concept-image {
    margin: 0;
}
.concept-image img {
    max-width: 100%;
    border-radius: 6px;
    margin-top: 0.75rem;
    border: 1px solid #dadce0;
}
figcaption {
    font-size: 0.85rem;
    color: #5f6368;
    margin-top: 0.25rem;
}
@media (max-width: 700px) {
    .step-images {
        grid-template-columns: 1fr;
    }
}
.step .notes {
    background: #fff8e1;
    border-left: 3px solid #f9a825;
    padding: 0.5rem 1rem;
    margin-top: 0.75rem;
    border-radius: 0 6px 6px 0;
    font-size: 0.9rem;
}
.prerequisites {
    background: #fce8e6;
    border-left: 4px solid #d93025;
    padding: 1rem 1.5rem;
    border-radius: 0 8px 8px 0;
    margin: 1rem 0;
}
.prerequisites ul {
    margin: 0.5rem 0 0 0;
    padding-left: 1.25rem;
}
.glossary-table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}
.glossary-table th,
.glossary-table td {
    border: 1px solid #dadce0;
    padding: 0.6rem 1rem;
    text-align: left;
}
.glossary-table th {
    background: #1a73e8;
    color: #fff;
}
.glossary-table tr:nth-child(even) {
    background: #f1f3f4;
}
.notes-section {
    background: #e6f4ea;
    border-left: 4px solid #34a853;
    padding: 1rem 1.5rem;
    border-radius: 0 8px 8px 0;
    margin: 1rem 0;
}
"""


def _image_src(path: Path | None, standalone: bool) -> str | None:
    """``src`` di un'immagine: percorso relativo ``screenshots/`` per l'HTML
    con cartella, base64 incorporato per lo standalone."""
    if path is None:
        return None
    if not standalone:
        return f"screenshots/{path.name}"
    if not path.exists():
        return None
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"


def _slide_caption(item: dict, s: dict[str, str]) -> str:
    slides = item.get("source_slides") or []
    return s["html_slide_caption"].format(n=slides[0]) if slides else ""


def _render_step(
    step: dict,
    proc_id: str,
    screenshot_map: dict[tuple[str, int], Path | None],
    slide_map: dict[tuple[str, int], Path],
    standalone: bool,
    s: dict[str, str],
) -> str:
    num = step["number"]
    title = step.get("title", "")
    desc = step.get("description", "")
    note = step.get("notes", "")
    main_src = _image_src(screenshot_map.get((proc_id, num)), standalone)
    slide_src = _image_src(slide_map.get((proc_id, num)), standalone)
    img_html = ""
    if main_src and slide_src:
        img_html = f"""<div class="step-images">
    <figure><img src="{main_src}" alt="Step {num}"></figure>
    <figure><img src="{slide_src}" alt="{_slide_caption(step, s)}"><figcaption>{_slide_caption(step, s)}</figcaption></figure>
  </div>"""
    elif main_src or slide_src:
        img_html = f'<img src="{main_src or slide_src}" alt="Step {num}">'
    note_html = f'<div class="notes">{note}</div>' if note else ""
    return f"""
<div class="step">
  <div class="step-header">
    <div class="step-number">{num}</div>
    <h3>{title}</h3>
  </div>
  <p>{desc}</p>
  {img_html}
  {note_html}
</div>"""


def _render_procedures(
    procedures: list[dict],
    screenshot_map: dict[tuple[str, int], Path | None],
    slide_map: dict[tuple[str, int], Path],
    standalone: bool,
    s: dict[str, str],
) -> str:
    parts: list[str] = []
    for proc in procedures:
        proc_id = proc.get("id", "proc_001")
        proc_title = proc.get("title", "")
        steps_html = "\n".join(
            _render_step(step, proc_id, screenshot_map, slide_map, standalone, s) for step in proc.get("steps", [])
        )
        parts.append(f"""
<div class="procedure-section" id="{proc_id}">
  <h2>{proc_title}</h2>
  {steps_html}
</div>""")
    return "\n".join(parts)


def _render_concepts(
    concepts: list[dict], concept_image_map: dict[str, Path], standalone: bool, s: dict[str, str]
) -> str:
    parts: list[str] = []
    for con in concepts:
        con_id = con.get("id", "con_001")
        con_title = con.get("title", "")
        con_content = con.get("content", "")
        src = _image_src(concept_image_map.get(con_id), standalone)
        caption = _slide_caption(con, s)
        img_html = (
            f'<figure class="concept-image"><img src="{src}" alt="{caption}"><figcaption>{caption}</figcaption></figure>'
            if src
            else ""
        )
        parts.append(f"""
<div class="concept-section" id="{con_id}">
  <h2>{con_title}</h2>
  <p>{con_content}</p>
  {img_html}
</div>""")
    return "\n".join(parts)


def _render_toc(data: dict, s: dict[str, str]) -> str:
    concepts = data.get("concepts", [])
    procedures = data.get("procedures", [])
    if not concepts and not procedures:
        return ""
    has_both = bool(concepts) and bool(procedures)
    items: list[str] = []
    for con in concepts:
        label = f"[{s['html_concept_tag']}] {con.get('title', '')}" if has_both else con.get("title", "")
        items.append(f'    <li><a href="#{con.get("id", "con_001")}">{label}</a></li>')
    for proc in procedures:
        label = f"[{s['html_procedure_tag']}] {proc.get('title', '')}" if has_both else proc.get("title", "")
        items.append(f'    <li><a href="#{proc.get("id", "proc_001")}">{label}</a></li>')
    items_html = "\n".join(items)
    return f"""
<div class="toc">
  <strong>{s['html_toc']}</strong>
  <ul>
{items_html}
  </ul>
</div>"""


def _render_html(data: dict, procedures_html: str, concepts_html: str, language: str) -> str:
    s = get_strings(language)
    title = data.get("title", s["html_default_title"])
    summary = data.get("summary", "")
    prerequisites = data.get("prerequisites", [])
    glossary = data.get("glossary", [])
    notes = data.get("notes", [])

    toc_html = _render_toc(data, s)

    prereq_items = "\n".join(f"    <li>{p}</li>" for p in prerequisites)
    prereq_html = f"""
<div class="prerequisites">
  <h2>{s['html_prerequisites']}</h2>
  <ul>
{prereq_items}
  </ul>
</div>""" if prerequisites else ""

    glossary_rows = "\n".join(
        f'    <tr><td><strong>{g["term"]}</strong></td><td>{g["definition"]}</td></tr>'
        for g in glossary
    )
    glossary_html = f"""
<h2>{s['html_glossary']}</h2>
<table class="glossary-table">
  <thead><tr><th>{s['html_term']}</th><th>{s['html_definition']}</th></tr></thead>
  <tbody>
{glossary_rows}
  </tbody>
</table>""" if glossary else ""

    notes_items = "\n".join(f"  <li>{n}</li>" for n in notes)
    notes_html = f"""
<div class="notes-section">
  <h2>{s['html_notes']}</h2>
  <ul>
{notes_items}
  </ul>
</div>""" if notes else ""

    return f"""<!DOCTYPE html>
<html lang="{s['html_lang']}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>{title}</h1>
  <div class="summary">{summary}</div>
  {prereq_html}
  {toc_html}
  {concepts_html}
  {procedures_html}
  {glossary_html}
  {notes_html}
</body>
</html>"""


def build_html_folder(
    data: dict,
    screenshot_map: dict[tuple[str, int], Path | None],
    language: str = "it",
    slide_map: dict[tuple[str, int], Path] | None = None,
    concept_image_map: dict[str, Path] | None = None,
) -> str:
    """HTML con percorsi immagine relativi ``screenshots/``."""
    s = get_strings(language)
    concepts_html = _render_concepts(data.get("concepts", []), concept_image_map or {}, False, s)
    procedures_html = _render_procedures(data.get("procedures", []), screenshot_map, slide_map or {}, False, s)
    return _render_html(data, procedures_html, concepts_html, language)


def build_html_standalone(
    data: dict,
    screenshot_map: dict[tuple[str, int], Path | None],
    language: str = "it",
    slide_map: dict[tuple[str, int], Path] | None = None,
    concept_image_map: dict[str, Path] | None = None,
) -> str:
    """Un unico file HTML autonomo con immagini embedded in base64."""
    s = get_strings(language)
    concepts_html = _render_concepts(data.get("concepts", []), concept_image_map or {}, True, s)
    procedures_html = _render_procedures(data.get("procedures", []), screenshot_map, slide_map or {}, True, s)
    return _render_html(data, procedures_html, concepts_html, language)
