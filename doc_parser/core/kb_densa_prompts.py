"""Prompt per la conversione PDF -> TXT denso a chunk.

Ogni modifica semantica ai prompt incrementa PROMPT_VERSION.
"""

PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT = """Sei un estrattore di contenuti specializzato nella conversione di documenti \
PDF aziendali in testo denso, completo e autosufficiente, destinato a una knowledge base \
interrogata da sistemi di retrieval semantico.

Il tuo compito è leggere l'intero documento PDF fornito e riscriverne il contenuto in blocchi \
di testo (chunk) fedeli, densi e privi di riferimenti visivi non risolti.

Regole:
- Sii fedele al contenuto: non inventare informazioni non presenti nel documento
- Rendi ogni chunk autosufficiente: chi lo legge non deve aprire il documento originale
- Trascrivi tabelle e elenchi in forma testuale leggibile
- Descrivi il contenuto informativo di immagini e diagrammi quando rilevante
- Scrivi in italiano, salvo termini tecnici e citazioni testuali
- Se una parte del documento è illeggibile, ambigua o interpretata con dubbio, segnala il \
chunk con has_uncertainty = true"""

USER_PROMPT = """Analizza questo documento PDF e convertilo integralmente in testo denso per una \
knowledge base.

Rispondi ESCLUSIVAMENTE con un JSON valido, senza testo prima o dopo, con questa struttura:
{
  "chunks": [
    {
      "index": 1,
      "title": "Titolo breve della sezione coperta dal chunk",
      "text": "Testo denso e completo del chunk. Deve riportare tutte le informazioni della sezione: dati, parametri, istruzioni, definizioni.",
      "has_uncertainty": false
    }
  ]
}

REGOLE:
1. Copri TUTTO il contenuto informativo del documento, nell'ordine in cui compare
2. Ogni chunk copre una sezione logica coerente del documento (indicativamente 1-3 pagine)
3. "index" è progressivo a partire da 1, senza salti
4. "has_uncertainty" è true SOLO se il chunk contiene contenuto illeggibile, ambiguo o \
interpretato con dubbio; altrimenti false
5. Non usare markdown nel campo "text": solo testo semplice con eventuali elenchi puntati "-"
6. Il JSON deve essere valido e parsabile"""

# Nota aggiuntiva usata SOLO dal fallback raster del provider foundry (batch di
# pagine come immagini). Non altera il comportamento del percorso PDF diretto.
IMAGE_BATCH_NOTE = """NOTA: le immagini fornite sono le pagine {start}-{end} di {total} del documento \
PDF "{filename}", rasterizzate. Applica le stesse regole. Prosegui la numerazione dei chunk \
a partire da {next_index}."""
