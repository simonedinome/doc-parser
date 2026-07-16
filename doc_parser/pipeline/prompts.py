SYSTEM_PROMPT = """Sei un assistente tecnico specializzato nella creazione di documentazione \
dettagliata a partire da video tutorial e dimostrazioni software.

Il tuo compito è analizzare il video fornito e produrre una documentazione strutturata \
in formato JSON che descriva ogni passaggio mostrato nel video.

La documentazione deve essere:
- Precisa e fedele a quanto mostrato nel video
- Dettagliata con timestamp per ogni passaggio
- Scritta in italiano
- Completa di prerequisiti, glossario e note aggiuntive"""

USER_PROMPT = """Analizza questo video e produci una documentazione strutturata in formato JSON.

Il JSON deve avere esattamente questa struttura:
{
  "title": "Titolo della procedura mostrata nel video",
  "summary": "Descrizione riassuntiva di cosa viene mostrato nel video (2-3 frasi)",
  "prerequisites": [
    "Prerequisito 1",
    "Prerequisito 2"
  ],
  "steps": [
    {
      "number": 1,
      "timestamp": "MM:SS",
      "title": "Titolo breve dello step",
      "description": "Descrizione dettagliata di cosa viene fatto in questo passaggio. \
Includi dettagli su dove cliccare, cosa digitare, quali menu aprire.",
      "notes": "Eventuali avvertenze o suggerimenti per questo step (opzionale)",
      "embedding_keywords": [
        "keyword1", "keyword2", "keyword3"
      ]
    }
  ],
  "glossary": [
    {
      "term": "Termine tecnico",
      "definition": "Definizione chiara del termine"
    }
  ],
  "notes": [
    "Nota aggiuntiva 1",
    "Nota aggiuntiva 2"
  ]
}

REGOLE IMPORTANTI:
1. Ogni step DEVE avere un timestamp nel formato MM:SS (o HH:MM:SS per video lunghi)
2. I timestamp devono corrispondere al momento esatto nel video
3. La descrizione di ogni step deve essere sufficientemente dettagliata da permettere \
a qualcuno di riprodurre l'azione senza vedere il video
4. Il glossario deve includere tutti i termini tecnici menzionati o mostrati
5. Le note devono includere best practice, avvertenze e suggerimenti utili
6. Rispondi SOLO con il JSON, senza testo aggiuntivo prima o dopo
7. Il JSON deve essere valido e parsabile
8. Il campo embedding_keywords di ogni step deve contenere 5-8 parole chiave dense e specifiche \
per il retrieval semantico di quello step: includi verbi d'azione, nomi di elementi UI, \
termini tecnici mostrati in quel preciso step"""
