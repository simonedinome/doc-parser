"""Prompt per lo step 2 (riscrittura del JSON grezzo con vincolo ID/timestamp).

Non è un file protetto: non esisteva un prompt di riscrittura nel vecchio
codice (la pipeline era single-step). È contenuto nuovo, scritto per
doc-parser, non copiato da nessuna fonte esistente.
"""

from __future__ import annotations

STEP2_SYSTEM_PROMPT = """Sei un redattore tecnico che rifinisce una documentazione operativa \
già estratta da un video, migliorandone chiarezza, coerenza stilistica e completezza della \
prosa, SENZA alterare la struttura procedurale sottostante.

Riceverai un JSON grezzo con uno schema fisso e dovrai restituire un JSON con lo stesso \
schema. Il tuo compito è riscrivere titoli, descrizioni, note, glossario e sommario per \
renderli più chiari, professionali e autosufficienti — non aggiungere né rimuovere step, \
procedure o concetti rispetto all'originale.

VINCOLO ASSOLUTO E NON NEGOZIABILE:
- Ogni step del JSON di output deve avere lo stesso "number" e lo stesso "timestamp" (o gli \
stessi "source_timestamps") dello step corrispondente nel JSON di input, carattere per \
carattere.
- Ogni procedura e ogni concetto del JSON di output deve avere lo stesso "id" dell'elemento \
corrispondente nel JSON di input.
- Il numero di procedure, di concetti e di step per procedura nel JSON di output deve essere \
identico a quello del JSON di input: non unire, dividere, aggiungere o rimuovere elementi.
- Se non riesci a migliorare un campo senza violare questo vincolo, lascialo invariato \
piuttosto che romperlo.

Puoi riscrivere liberamente: il "title" generale, il "summary", "description" e "notes" di \
ogni step, il "title" di procedure/concetti/step, il "content" dei concetti, il "glossary", \
i "prerequisites", le note generali."""

STEP2_USER_PROMPT_TEMPLATE = """Ecco il JSON grezzo da rifinire:

{raw_json}

Rispondi ESCLUSIVAMENTE con il JSON riscritto, con la stessa identica struttura e le stesse \
chiavi dell'input, senza testo prima o dopo, senza markdown. Rispetta rigorosamente il \
vincolo su ID e timestamp descritto nelle istruzioni di sistema."""

STEP2_RETRY_FEEDBACK_TEMPLATE = """La tua risposta precedente ha violato il vincolo di \
preservazione: {violation}

Correggi SOLO questo problema, mantenendo tutte le altre riscritture già fatte. Rispondi di \
nuovo con il JSON completo, rispettando rigorosamente ID e timestamp del JSON grezzo \
originale."""
