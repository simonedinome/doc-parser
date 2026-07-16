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

```bash
python -m doc_parser.cli --help
```

## Configurazione modelli

I modelli LLM disponibili in UI e CLI sono definiti in `models.yaml`, con prezzi EUR/1M
token a snapshot (data e fonte annotate nel file). Aggiornare `models.yaml` per cambiare
il listino o i prezzi.
