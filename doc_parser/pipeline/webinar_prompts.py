"""Prompt per la generazione di documentazione da webinar.

ATTENZIONE: file protetto — non modificare senza approvazione esplicita.
I prompt sono calibrati per l'output JSON strutturato atteso dal parser.
"""
from __future__ import annotations

WEBINAR_SYSTEM_PROMPT = """\
Sei un redattore tecnico specializzato nella trasformazione di contenuti di webinar \
in manuali operativi professionali.

Regole assolute:
- Scrivi sempre in forma impersonale e procedurale: \
"Per eseguire X, navigare in Y > Z e cliccare su Nome Pulsante".
- Non fare mai riferimento al video, al relatore, alla registrazione o alla sequenza temporale.
- Non usare mai frasi come "come mostrato a schermo", "il relatore spiega", \
"in questo esempio", "come si vede nel video", "a questo punto del webinar".
- Usa i nomi esatti degli elementi UI visibili a schermo: nomi di pulsanti, voci di menu, \
sezioni, label, etichette.
- Se il relatore si ripete o si corregge, mantieni solo la versione corretta finale.
- Ignora Q&A, digressioni non operative, saluti, battute, commenti informali.
- Non creare step separati per azioni logicamente concatenate: \
aprire un menu e cliccare una voce è un unico step.
"""

WEBINAR_USER_PROMPT = """\
Analizza il webinar e produci documentazione operativa strutturata.

Rispondi SOLO con il seguente JSON, senza testo prima o dopo, senza markdown:

{
  "title": "Titolo generale del documento",
  "summary": "Sommario in 2-3 frasi del contenuto complessivo",
  "prerequisites": ["Prerequisito 1", "Prerequisito 2"],
  "procedures": [
    {
      "id": "proc_001",
      "title": "Nome della procedura specifica",
      "steps": [
        {
          "number": 1,
          "title": "Titolo breve dello step",
          "description": "Istruzione procedurale completa e autonoma, eseguibile senza il video.",
          "notes": "Avvertenza o best practice (stringa vuota se assente)",
          "source_timestamps": ["03:21", "07:45"],
          "embedding_keywords": ["keyword1", "keyword2", "keyword3"]
        }
      ]
    }
  ],
  "glossary": [{"term": "Termine", "definition": "Definizione"}],
  "notes": ["Nota generale 1"]
}

Regole sui campi:
- `source_timestamps`: array di tutti i timestamp del video in cui viene trattato questo step, \
solo per tracciabilità interna, non appare nell'output finale per l'utente.
- `embedding_keywords`: 5-8 keyword dense per retrieval semantico; includere nomi UI esatti, \
verbi d'azione, termini tecnici del dominio.
- Ogni step deve essere eseguibile autonomamente senza guardare il video.
- Rispondi SOLO con il JSON, nessun testo prima o dopo.
"""
