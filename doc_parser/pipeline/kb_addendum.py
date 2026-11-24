"""Addendum ai prompt di step 1 quando la run produce il TXT "Knowledge base".

Non modifica i prompt protetti (pipeline/video_prompts.py, manuale_prompts.py):
il testo viene appeso prima della direttiva di lingua, come l'addendum delle
slide, e solo se l'artefatto ``kb`` è tra quelli richiesti. Le run senza KB
mandano al modello esattamente gli stessi prompt di prima.
"""

from __future__ import annotations

KB_ARTIFACT = "kb"
KB_MARKER = "kb_extraction"

KB_SYSTEM_ADDENDUM = """\
Questa documentazione alimenta anche una knowledge base interrogata da un assistente AI. \
Le istruzioni seguenti prevalgono su quelle precedenti in caso di conflitto:
- Le spiegazioni teoriche NON sono digressioni da ignorare: tutto ciò che spiega cos'è qualcosa, \
a cosa serve, come funziona, perché si fa in un certo modo, le regole, i vincoli, le eccezioni e \
gli esempi va riportato nel campo "concepts", in paragrafi completi e autonomi.
- Le domande e risposte (Q&A) vanno riportate per intero nel campo "qa", non nelle note: la \
domanda riformulata in modo chiaro e autonomo, la risposta completa con tutti i dettagli dati. \
Includi ogni Q&A con informazioni utili; escludi solo quelle prive di contenuto (saluti, problemi \
audio, domande senza risposta).
- Non citare mai video, webinar, relatore, registrazione, slide o documento nel testo di concetti e Q&A."""

_CONCEPTS_FIELD = """\
  "concepts": [
    {"id": "con_001", "title": "Titolo del concetto", "content": "Paragrafo completo e autonomo", \
"embedding_keywords": ["keyword1", "keyword2"]}
  ],"""

_QA_FIELD = """\
  "qa": [
    {"question": "Domanda completa e autonoma", "answer": "Risposta completa"}
  ]"""

_USER_ADDENDUM_TEMPLATE = """\
Aggiungi al JSON, allo stesso livello di "procedures", {fields_label}:
{{
{fields}
}}
{rules}"""


def apply_kb_addendum(system_prompt: str, user_prompt: str, content_type: str) -> tuple[str, str]:
    """Appende l'addendum KB ai prompt di step 1 (system e user).

    Il profilo ``manuale`` ha già ``concepts`` nello schema protetto: gli si
    chiede solo ``qa``.
    """
    if content_type == "manuale":
        fields_label = 'il campo "qa"'
        fields = _QA_FIELD
        rules = '- "qa" può essere lista vuota se il contenuto non ha domande e risposte.'
    else:
        fields_label = 'i campi "concepts" e "qa"'
        fields = f"{_CONCEPTS_FIELD}\n{_QA_FIELD}"
        rules = (
            '- "concepts" e "qa" possono essere liste vuote se il contenuto non ne ha.\n'
            '- "id" dei concetti progressivo: con_001, con_002, ...'
        )
    user_addendum = _USER_ADDENDUM_TEMPLATE.format(fields_label=fields_label, fields=fields, rules=rules)
    return f"{system_prompt}\n\n{KB_SYSTEM_ADDENDUM}", f"{user_prompt}\n\n{user_addendum}"


def kb_requested(output_artifacts: str | None) -> bool:
    """True se la run chiede l'artefatto KB (``output_artifacts`` in CSV)."""
    return KB_ARTIFACT in [a.strip() for a in (output_artifacts or "").split(",")]


def mark_kb_extraction(data: dict) -> dict:
    """Segna un JSON di step 1 come estratto con l'addendum KB (lo mette il codice, non il modello)."""
    data[KB_MARKER] = True
    return data


def has_kb_extraction(data: dict) -> bool:
    return data.get(KB_MARKER) is True
