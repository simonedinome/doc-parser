# doc-parser

Web app Streamlit + CLI per trasformare video, PDF e documenti Office (docx, doc
legacy, xlsx, csv, txt, immagini) in documentazione strutturata (procedure,
glossario, chunk RAG) tramite LLM multi-provider (Gemini nativo, OpenRouter).

## Prerequisiti

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) installato e disponibile in `PATH` (estrazione screenshot dai video)
- [LibreOffice](https://www.libreoffice.org/) (`soffice` in `PATH`) per l'estrazione testo dai file `.doc` legacy

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # valorizza le chiavi API
cp users.example.yaml users.yaml
```

## Avvio

```bash
streamlit run doc_parser/ui/app.py
```

Per la gestione operativa (riavvio dopo modifica `.env`, gestione utenti, reset
dati, troubleshooting) vedi [`RUNBOOK.md`](RUNBOOK.md).

## Architettura in breve

- `doc_parser/pipeline/core.py` — motore condiviso: guardrail, dedup, step 1/2
  video, consolidamento delle serie di video (`pipeline/consolidation.py`),
  percorso single-step per i formati non video, KB densa, Rielabora.
  Invocato sia dal worker in background (UI) sia dalla CLI: nessuna logica di
  elaborazione duplicata tra i due entrypoint.
- `doc_parser/providers/` — Gemini (API nativa) e OpenRouter (Claude/GPT),
  interfaccia comune `BaseProvider.generate()`.
- `doc_parser/output/` — builder degli artefatti finali (procedura.txt,
  glossario.txt, rag_chunks.jsonl, html, pptx, log, zip), sempre a partire dal
  JSON finale.
- `doc_parser/storage/`, `doc_parser/worker/`, `doc_parser/auth/` — persistenza
  SQLite, worker in background, autenticazione password/bcrypt.
- `doc_parser/ui/` — pagine Streamlit (Elabora, Le mie richieste, Log, Log tecnico).
- `doc_parser/cli/` — CLI batch e coda YAML, secondo entrypoint sullo stesso motore.

## CLI

CLI e UI Streamlit condividono lo stesso motore (`doc_parser.pipeline.core`): le run
create dalla CLI sono visibili anche in Log/Log tecnico e usano lo stesso `data/` e lo
stesso `models.yaml`.

```bash
# Batch su cartella: un export per file, in parallelo
python -m doc_parser.cli --input-dir ./input --content-type documento --model anthropic/claude-haiku-4.5

# Batch da lista URL (un URL per riga, righe con # ignorate)
python -m doc_parser.cli --urls-file urls.txt --content-type video

# Coda YAML: run con parametri diversi, merge multi-video, resume automatico
python -m doc_parser.cli --runs-file runs.yaml
```

Vedi `runs.example.yaml` per lo schema completo della coda YAML (impostazioni globali,
override per-run, serie di video consolidate, modalità KB densa). Il checkpoint
(`data/runs_checkpoint.json`) permette di riprendere un batch interrotto senza
rielaborare le run già completate — cancellalo per ripartire da zero.

```bash
python -m doc_parser.cli --help
```

## Serie di video con slide (content_type `video`)

Una run `video` accetta più video della stessa formazione, ciascuno etichettato
`webinar` o `pillola` con data di registrazione facoltativa, più al massimo un PDF
di slide. Con almeno due fonti (più video, oppure video + PDF) la pipeline:

1. esegue lo step 1 su ogni video, con il PDF allegato e un addendum ai prompt
   protetti che chiede i numeri di slide (`source_slides`) e segnala le discordanze;
2. consolida i JSON in un'unica documentazione senza ripetizioni, con il modello
   scelto; le discordanze si risolvono con la priorità webinar > slide > pillola
   (a parità di tipo vince la registrazione più recente);
3. ricava dal codice fonti, timestamp e immagini di ogni step (fotogramma del
   webinar, slide o fotogramma della pillola);
4. riscrive con lo step 2 (saltato se il modello scelto è un Gemini).

Il video singolo senza PDF e lo `screencast` legacy seguono il percorso di sempre.

```yaml
runs:
  - name: formazione-gestionale
    inputs:
      - {source: file, order: 1, path: input/webinar_giugno.mp4, kind: webinar, recorded_at: 2026-06-03}
      - {source: file, order: 2, path: input/pillola_settembre.mp4, kind: pillola, recorded_at: 2026-09-12}
      - {source: file, order: 3, path: input/slide_formazione.pdf}
    settings:
      content_type: video
      output_artifacts: html_standalone,procedura,glossario,rag_chunks,pptx
```

Output in più rispetto alle altre run:

- `presentazione_tutorial.pptx` (artefatto `pptx`, solo run video): presentazione
  16:9 da proiettare, una slide per concetto e per step; testo completo e fonte di
  ogni step nelle note del relatore;
- `log.txt` con le sezioni FONTI, DISCORDANZE (fonte tenuta e scartate con file,
  tipo, data, timestamp o slide, motivo; `ATTENZIONE` se è stata scartata una fonte
  più recente), CONTENUTI SCARTATI, SLIDE NON INCLUSE e AVVISI;
- nell'HTML, la slide accanto allo screenshot dello step e la slide dei concetti.

I costi della run sommano step 1, consolidamento (colonne `consolidation_*`) e step 2.

## Configurazione modelli

I modelli LLM disponibili in UI e CLI sono definiti in `models.yaml`, con prezzi EUR/1M
token a snapshot (data e fonte annotate nel file). Prima di modificare il listino,
verifica ID e prezzi correnti contro l'endpoint OpenRouter `/api/v1/models` e il
listino ufficiale Gemini — non aggiornarli a memoria. Nessun riavvio necessario dopo
la modifica: il file è riletto a ogni run.

## Test

```bash
pytest doc_parser/tests/
```
