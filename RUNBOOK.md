# Runbook operativo — doc-parser

## Avvio

```bash
pip install -r requirements.txt
cp .env.example .env              # valorizza GEMINI_API_KEY / OPENROUTER_API_KEY
cp users.example.yaml users.yaml  # definisci gli utenti (vedi sotto)
streamlit run doc_parser/ui/app.py
```

Il worker in background parte automaticamente al primo avvio dell'app (una sola
volta per processo, `st.cache_resource` in `doc_parser/ui/context.py`) e sopravvive
alla chiusura dei singoli tab: le run restano in coda/in elaborazione anche se
nessun browser è collegato, finché il processo Streamlit resta attivo.

Per la CLI batch/coda YAML vedi la sezione "CLI" del `README.md`.

## Riavvio dopo modifica di `.env`

`Settings` (`doc_parser/settings.py`) è caricato una sola volta per processo
(`@lru_cache` su `get_settings()`) e il worker/repository sono a loro volta
cacheati da Streamlit (`@st.cache_resource`). **Le modifiche a `.env` non hanno
effetto a runtime**: serve riavviare il processo Streamlit (`Ctrl+C` e rilancio
di `streamlit run doc_parser/ui/app.py`, o riavvio del container/servizio).

Non serve invece riavviare per modifiche a:
- `users.yaml` — riletto a ogni tentativo di login;
- `models.yaml` — riletto a ogni run (nessuna cache);
- prompt e codice della pipeline, se si usa `streamlit run` con auto-reload
  attivo (Streamlit ricarica gli script Python ad ogni refresh pagina, ma
  non gli oggetti già cacheati con `@st.cache_resource`/`@lru_cache`).

Se il worker sembra bloccato o incoerente dopo un aggiornamento del codice,
il riavvio completo del processo è comunque la via più sicura: al riavvio,
`Worker.start()` richiama `_recover_stale_processing()` e rimette in coda
automaticamente qualunque run rimasta `Processing` da un'interruzione
precedente (nessun intervento manuale necessario sul database).

## Gestione utenti

Gli utenti vivono in `users.yaml` (gitignored, mai da committare), non nel
database delle run. Schema:

```yaml
users:
  - upn: utente@azienda.local
    display_name: Nome Cognome
    role: user        # o "admin" per l'accesso a Log tecnico
    password_hash: "$2b$12$..."
```

Per generare un nuovo hash bcrypt:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'nuova-password', bcrypt.gensalt()).decode())"
```

Per aggiungere, rimuovere o cambiare la password di un utente: modifica
`users.yaml` e basta — è riletto a ogni login, nessun riavvio necessario.
Per revocare l'accesso a un utente con sessione già aperta nel browser: la
rimozione da `users.yaml` impedisce nuovi login, ma non invalida
retroattivamente una sessione Streamlit già autenticata (`st.session_state`)
finché quel tab resta aperto — se serve la revoca immediata, riavvia il
processo (azzera tutte le sessioni).

## Dati e artefatti

Tutto lo stato applicativo vive sotto `data/` (gitignored):

```
data/
  runs.db              # SQLite: metadati di tutte le run (UI + CLI)
  inbox/                # file di input caricati (bytes grezzi)
  outputs/               # blob di output (JSON grezzo/finale, zip, TXT KB densa)
  screenshots/{run_id}/  # screenshot video / pagine PDF per run
  artifacts/{run_id}/    # procedura.txt, glossario.txt, rag_chunks.jsonl, html, log.txt
  runs_checkpoint.json   # checkpoint della coda CLI (YAML/batch), non della UI
```

Per azzerare completamente lo stato (run, log, costi): ferma il processo e
rimuovi `data/`. Per azzerare solo il checkpoint della CLI (rieseguire da capo
un batch/coda YAML senza toccare lo storico delle run): rimuovi
`data/runs_checkpoint.json`.

## Aggiornare `models.yaml`

I prezzi in `models.yaml` sono uno snapshot (data e fonte annotate nel file
stesso). Prima di aggiornarli, verificare gli ID e i prezzi correnti contro
l'endpoint `https://openrouter.ai/api/v1/models` (per i modelli
Anthropic/OpenAI instradati via OpenRouter) e il listino ufficiale Gemini
(`https://ai.google.dev/gemini-api/docs/pricing`, per i modelli Gemini
nativi) — non aggiornare i prezzi a memoria. Nessun riavvio necessario dopo
la modifica: il file è riletto a ogni run.

## Troubleshooting

| Sintomo | Causa probabile | Azione |
|---|---|---|
| `LibreOffice (soffice) non è installato` su run `.doc` | `soffice` mancante dal `PATH` | Installa LibreOffice (vedi devcontainer/README) |
| Screenshot mancanti nell'HTML/zip di una run video | `ffmpeg` mancante o video corrotto | Verifica `ffmpeg -version`; controlla `log.txt` nello zip per i warning di clamp-durata |
| Run bloccata su "In elaborazione" dopo un crash | Worker interrotto a metà run | Riavvia il processo: `_recover_stale_processing()` la rimette in coda automaticamente |
| Errore di connessione ai provider (`Connection error.` / `TransientProviderError`) | Rete non raggiungibile verso OpenRouter/Gemini (firewall, proxy, chiave API assente) | Verifica `GEMINI_API_KEY`/`OPENROUTER_API_KEY` in `.env` e la connettività di rete; la run viene ritentata secondo `RETRY_MAX_ATTEMPTS`/`RETRY_BACKOFF_SECONDS` prima di fallire |
| `Saldo OpenRouter insufficiente... (HTTP 402)` | Credito OpenRouter esaurito (il plugin `file-parser`, usato per i PDF nativi, richiede almeno $0.50 residui) | Ricarica il credito su `https://openrouter.ai/credits`; nessun retry automatico, l'errore è permanente per definizione |
| `Autenticazione Gemini rifiutata... ACCESS_TOKEN_TYPE_UNSUPPORTED (HTTP 401)` | La `GEMINI_API_KEY` è in formato `AQ.` (rilasciato ora da Google ad alcuni account) invece del classico `AIza...`. Le chiavi `AQ.` sono "authorization key" legate a un service account, non semplici API key: possono essere rifiutate sia dalla Files API sia da `generateContent` stesso, non solo per gli allegati grandi | Prima cosa da provare: `pip install -U google-genai` (assicurati di avere `google-genai>=2.12`, `pip show google-genai`) — versioni recenti dell'SDK gestiscono meglio le authorization key. Se persiste, non è risolvibile lato app: è una restrizione nota e ancora in corso lato Google (segnalata anche via `curl` grezzo, indipendente da qualunque SDK/libreria). Verifica il formato della chiave su `https://aistudio.google.com/apikey`; se possibile, rigenerane una in formato `AIza...`, oppure valuta di instradare i modelli Gemini tramite OpenRouter (che usa proprie credenziali Cloud) come alternativa |
| `FOUNDRY_ENDPOINT, FOUNDRY_API_KEY e FOUNDRY_DEPLOYMENT sono obbligatori` | `FoundryProvider` istanziato senza configurazione | Previsto: il provider è dormiente in v1, non è raggiungibile dal menu utente |
| Rielabora non disponibile per una run | La run non è video, non è `Done`, o manca il JSON grezzo | Il pulsante compare solo per run video completate con `raw_json_ref` valorizzato |
