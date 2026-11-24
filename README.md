# doc-parser

Trasforma webinar, serie di video con slide, PDF e documenti Office in
documentazione strutturata e in un **TXT Knowledge base** pronto per la Data
Library di un agente **Agentforce**: concetti, procedure passo passo, domande e
risposte complete, glossario.

Si usa da una **web app** (Streamlit) o dalla **riga di comando** con una coda
di run in YAML. Entrambe usano lo stesso motore e gli stessi modelli LLM
(Gemini, Claude e GPT via OpenRouter).

## Avvio rapido

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env && cp users.example.yaml users.yaml
```

```bash
streamlit run doc_parser/ui/app.py
```

Servono anche `ffmpeg` e, per i `.doc`, LibreOffice. Le chiavi API vanno in
`.env`.

Dalla riga di comando, con una coda di run in `runs.yaml`:

```bash
python -m doc_parser.cli --runs-file runs.yaml
```

Le run già completate (o i file già elaborati con le stesse impostazioni) non
vengono rifatte. Per rifarle da capo aggiungi `--force`: la nuova elaborazione
va in una cartella nuova e quella precedente resta intatta.

```bash
python -m doc_parser.cli --runs-file runs.yaml --force
```

## Documentazione

| Documento | Per chi | Cosa contiene |
|---|---|---|
| [`istruzioni.md`](istruzioni.md) | Chi usa il progetto | Guida completa: installazione, web app, riga di comando, casi tipici, Knowledge base per Agentforce, problemi comuni, note per chi lo mantiene |
| [`RUNBOOK.md`](RUNBOOK.md) | Chi gestisce l'installazione | Riavvii, utenti, dati su disco, migrazioni, troubleshooting dettagliato |
| [`runs.example.yaml`](runs.example.yaml) | Chi usa la riga di comando | Esempi commentati della coda di run |
