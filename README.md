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
  video, percorso single-step per i formati non video, KB densa, Rielabora.
  Invocato sia dal worker in background (UI) sia dalla CLI: nessuna logica di
  elaborazione duplicata tra i due entrypoint.
- `doc_parser/providers/` — Gemini (API nativa) e OpenRouter (Claude/GPT),
  interfaccia comune `BaseProvider.generate()`.
- `doc_parser/output/` — builder degli artefatti finali (procedura.txt,
  glossario.txt, rag_chunks.jsonl, html, zip), sempre a partire dal JSON finale.
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
python -m doc_parser.cli --input-dir ./input --content-type doc --model anthropic/claude-haiku-4.5

# Batch da lista URL (un URL per riga, righe con # ignorate)
python -m doc_parser.cli --urls-file urls.txt --content-type screencast

# Coda YAML: run con parametri diversi, merge multi-video, resume automatico
python -m doc_parser.cli --runs-file runs.yaml
```

Vedi `runs.example.yaml` per lo schema completo della coda YAML (impostazioni globali,
override per-run, merge multi-video, modalità KB densa). Il checkpoint
(`data/runs_checkpoint.json`) permette di riprendere un batch interrotto senza
rielaborare le run già completate — cancellalo per ripartire da zero.

```bash
python -m doc_parser.cli --help
```

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
