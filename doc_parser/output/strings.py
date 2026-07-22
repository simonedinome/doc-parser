"""Stringhe fisse dei template di output, IT/EN.

I builder ricevono la lingua come parametro e pescano da qui le etichette
fisse (intestazioni, label): i contenuti generati dal modello sono già
nella lingua scelta grazie alla direttiva applicata ai prompt
(doc_parser.pipeline.language), qui si copre solo il testo del template.
"""

from __future__ import annotations

_STRINGS = {
    "it": {
        "glossary_header": "GLOSSARIO",
        "no_glossary": "Nessun termine nel glossario.",
        "source_label": "Fonte",
        "generated_on": "Generato il",
        "summary_header": "SOMMARIO",
        "prerequisites_header": "PREREQUISITI",
        "no_prerequisites": "Nessun prerequisito.",
        "concepts_header": "CONCETTI",
        "concept_label": "CONCETTO",
        "procedure_label": "PROCEDURA",
        "step_label": "STEP",
        "notes_label": "Note",
        "general_notes_header": "NOTE GENERALI",
        "html_lang": "it",
        "html_default_title": "Documentazione",
        "html_prerequisites": "Prerequisiti",
        "html_glossary": "Glossario",
        "html_term": "Termine",
        "html_definition": "Definizione",
        "html_notes": "Note",
        "html_toc": "Indice",
        "html_concept_tag": "Concetto",
        "html_procedure_tag": "Procedura",
        "log_header": "LOG DI GENERAZIONE",
    },
    "en": {
        "glossary_header": "GLOSSARY",
        "no_glossary": "No terms in the glossary.",
        "source_label": "Source",
        "generated_on": "Generated on",
        "summary_header": "SUMMARY",
        "prerequisites_header": "PREREQUISITES",
        "no_prerequisites": "No prerequisites.",
        "concepts_header": "CONCEPTS",
        "concept_label": "CONCEPT",
        "procedure_label": "PROCEDURE",
        "step_label": "STEP",
        "notes_label": "Notes",
        "general_notes_header": "GENERAL NOTES",
        "html_lang": "en",
        "html_default_title": "Documentation",
        "html_prerequisites": "Prerequisites",
        "html_glossary": "Glossary",
        "html_term": "Term",
        "html_definition": "Definition",
        "html_notes": "Notes",
        "html_toc": "Table of contents",
        "html_concept_tag": "Concept",
        "html_procedure_tag": "Procedure",
        "log_header": "GENERATION LOG",
    },
}


def get_strings(language: str) -> dict[str, str]:
    if language not in _STRINGS:
        raise ValueError(f"Lingua non supportata: {language!r}")
    return _STRINGS[language]
