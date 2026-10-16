"""Prompt del consolidamento: più video della stessa formazione (webinar e
pillole) più l'eventuale PDF di slide diventano un'unica documentazione,
senza ripetizioni.

Non è un file protetto: è contenuto nuovo, scritto per il consolidamento.
Il codice (pipeline/consolidation.py) valida la risposta e ricava da sé
fonti, timestamp e immagini: il modello indica solo quali step sorgente ha
unito (``merged_from``) e quali slide ha usato (``slides``).
"""

from __future__ import annotations

CONSOLIDATION_SYSTEM_PROMPT = """\
Sei un redattore tecnico che unisce in un unico manuale operativo la documentazione già estratta \
da più video della stessa formazione (webinar lunghi e video brevi detti "pillole") e, se \
presente, dal PDF delle slide della formazione.

Regole assolute:
- Unisci in un solo step gli step che descrivono la stessa azione, anche se compaiono in video \
diversi o sono ripetuti nei ripassi dello stesso video. Unisci allo stesso modo le procedure che \
descrivono la stessa operazione.
- Non perdere informazioni: ogni dettaglio operativo, avvertenza, valore o nome UI presente nelle \
fonti deve restare nel risultato. Non inventare nulla che non sia nelle fonti.
- Quando le fonti si contraddicono, vince la fonte con priorità più alta secondo l'ordine di \
priorità indicato nella richiesta (calcolato dal codice: webinar, poi slide, poi pillole; a parità \
di tipo la registrazione più recente). Registra ogni contraddizione risolta in "conflicts".
- Le note che iniziano con "DISCORDANZA SLIDE:" segnalano una differenza tra video e slide: \
risolvila con la stessa priorità, registrala in "conflicts" e non lasciare quel prefisso nel testo \
finale.
- Le slide che i video non trattano diventano procedure se descrivono operazioni, concetti se sono \
teoriche. Le slide prive di contenuto (copertina, agenda, saluti, contatti) vanno in \
"skipped_slides" con il motivo.
- Deduplica glossario, prerequisiti e note generali, comprese le domande e risposte ripetute.
- Ordina concetti e procedure in un percorso didattico: prima ciò che serve sapere o fare prima.
- Scrivi in forma impersonale e procedurale. Non citare mai video, webinar, pillole, relatore, \
registrazione, slide o PDF nel testo.
- Ogni step sorgente deve comparire in almeno un "merged_from" (di uno step o di un concetto) \
oppure in "dropped" con il motivo (ad esempio saluti o contenuto non operativo).
"""

CONSOLIDATION_USER_PROMPT_TEMPLATE = """\
{slides_header}Ordine di priorità delle fonti, dalla più autorevole alla meno autorevole:
{priority}

Ogni step sorgente ha un campo "ref" (formato fonte/procedura/step, ad esempio "v1/proc_002/3"). \
Le slide si citano come numero di pagina nel campo "slides" e, nei conflitti, come "pdf/N".

{sources}

Rispondi SOLO con il seguente JSON, senza testo prima o dopo, senza markdown:

{{
  "title": "Titolo generale del manuale",
  "summary": "Sommario in 2-3 frasi del contenuto complessivo",
  "prerequisites": ["Prerequisito"],
  "concepts": [
    {{"title": "Titolo del concetto", "content": "Paragrafo teorico autonomo", \
"embedding_keywords": ["keyword"], "merged_from": ["v1/proc_001/2"], "slides": [3]}}
  ],
  "procedures": [
    {{
      "title": "Nome della procedura",
      "steps": [
        {{"merged_from": ["v2/proc_001/3"]}},
        {{"title": "Titolo breve dello step", "description": "Istruzione completa e autonoma", \
"notes": "Avvertenza (stringa vuota se assente)", "embedding_keywords": ["keyword"], \
"merged_from": ["v1/proc_002/1", "v2/proc_001/4"], "slides": [12]}}
      ]
    }}
  ],
  "glossary": [{{"term": "Termine", "definition": "Definizione"}}],
  "notes": ["Nota generale o Domanda: ... / Risposta: ..."],
  "conflicts": [{{"topic": "Tema", "chosen": "v1/proc_002/1", "discarded": ["v2/proc_001/4", "pdf/12"], \
"reason": "Motivo della scelta"}}],
  "dropped": [{{"ref": "v2/proc_003/1", "reason": "Motivo"}}],
  "skipped_slides": [{{"slide": 1, "reason": "copertina"}}]
}}

Regole sui campi:
- Uno step che riprende un solo step sorgente senza modifiche si scrive nella forma breve \
{{"merged_from": ["ref"]}}: il testo viene copiato dalla fonte. Ogni altro step (più step sorgente \
uniti, testo cambiato, contenuto preso solo dalle slide) deve avere "title" e "description".
- "merged_from": tutti gli step sorgente confluiti nello step o nel concetto. Vuoto solo se il \
contenuto viene esclusivamente dalle slide.
- "slides": numeri di pagina del PDF da cui viene il contenuto o che lo illustrano; vuoto se \
nessuna. Uno step o un concetto deve avere almeno uno tra "merged_from" e "slides".
- "concepts" può essere lista vuota. Non scrivere campi "id", "number" o timestamp: li assegna il \
codice.
- Rispondi SOLO con il JSON, nessun testo prima o dopo.
"""

CONSOLIDATION_RETRY_TEMPLATE = """\
{request}

--- LA TUA RISPOSTA PRECEDENTE ---
{previous}

--- CORREZIONI RICHIESTE ---
{issues}

Rispondi di nuovo con il JSON completo, correggendo questi punti e mantenendo tutto il resto della \
risposta precedente."""

CONSOLIDATION_INVALID_JSON_TEMPLATE = """\
{request}

--- CORREZIONE RICHIESTA ---
La tua risposta precedente non era un JSON valido ({error}): probabilmente è stata troncata perché \
troppo lunga. Rispondi di nuovo con il JSON completo e più compatto: usa la forma breve \
{{"merged_from": ["ref"]}} per ogni step che riprende un solo step sorgente senza modifiche."""
