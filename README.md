# doc-parser

Web app Streamlit + CLI per trasformare video, PDF e documenti Office in documentazione
strutturata (procedure, glossario, chunk RAG) tramite LLM multi-provider.

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
token a snapshot (data e fonte annotate nel file). Aggiornare `models.yaml` per cambiare
il listino o i prezzi.
