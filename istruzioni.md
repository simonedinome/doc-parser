# Istruzioni d'uso — doc-parser

Questa guida spiega, passo per passo, come trasformare un webinar o un PDF in
un file di testo da dare in pasto all'agente **Agentforce** (la sua
*knowledge base*), e come ottenere gli altri formati: HTML, procedure,
glossario, presentazione.

Indice:

1. [A cosa serve](#1-a-cosa-serve)
2. [Installazione](#2-installazione)
3. [Usare la web app](#3-usare-la-web-app)
4. [Usare la riga di comando](#4-usare-la-riga-di-comando)
5. [Tre casi tipici](#5-tre-casi-tipici)
6. [Dove trovare i file](#6-dove-trovare-i-file)
7. [Caricare il TXT in Agentforce](#7-caricare-il-txt-in-agentforce)
8. [Quando una run fallisce](#8-quando-una-run-fallisce)
9. [Problemi comuni](#9-problemi-comuni)
10. [Per chi mantiene il progetto](#10-per-chi-mantiene-il-progetto)

---

## 1. A cosa serve

Dai al programma uno di questi materiali:

1. **un webinar** (o un video breve, una «pillola»);
2. **una serie** di video della stessa formazione, con o senza il PDF delle slide;
3. **un PDF** o un documento (`.docx`, `.doc`, `.xlsx`, `.csv`, `.txt`, immagini).

Il programma lo fa leggere a un modello di intelligenza artificiale e ti
restituisce, a scelta:

| File | A cosa serve |
|---|---|
| `<nome-run>_<data>_<ora>.txt` (**Knowledge base**) | Da caricare nella Data Library di Agentforce: concetti, procedure, domande e risposte complete, glossario |
| `documentazione_standalone.html` | Manuale da leggere nel browser, con le immagini |
| `procedura.txt`, `glossario.txt` | Procedure e glossario in testo semplice |
| `rag_chunks.jsonl` | Pezzi di testo per un motore di ricerca interno |
| `presentazione_tutorial.pptx` | Presentazione da proiettare (solo video) |
| `log.txt` | Cosa è successo durante l'elaborazione: fonti, discordanze, avvisi |

Ogni elaborazione si chiama **run**. Una run produce un solo export, anche
quando le dai più video.

---

## 2. Installazione

Serve una volta sola, su ogni computer o server.

**Cosa ti serve prima:**

1. Python 3.11 o più recente.
2. [ffmpeg](https://ffmpeg.org/), per le immagini dei video. Verifica con `ffmpeg -version`.
3. [LibreOffice](https://www.libreoffice.org/), solo se elabori file `.doc` vecchi.
4. Le chiavi API di Gemini e di OpenRouter.

**Passi:**

1. Installa le librerie:

   ```bash
   pip install -r requirements.txt
   ```

2. Crea il file delle chiavi e compilalo (`GEMINI_API_KEY`, `OPENROUTER_API_KEY`):

   ```bash
   cp .env.example .env
   ```

3. Crea il file degli utenti della web app (le istruzioni per le password sono
   dentro il file e in `RUNBOOK.md`, sezione «Gestione utenti»):

   ```bash
   cp users.example.yaml users.yaml
   ```

Se cambi `.env` dopo l'avvio, riavvia la web app: le chiavi si leggono solo
all'avvio.

---

## 3. Usare la web app

**Avvio:**

```bash
streamlit run doc_parser/ui/app.py
```

Si apre il browser: accedi con un utente di `users.yaml`.

**Elaborare un contenuto** (pagina **Elabora**):

1. **Tipo di contenuto**: *Video* per webinar e pillole, *Manuale* per i PDF con
   spiegazioni e procedure, *Documento* per gli altri file.
2. **Carica i file** oppure incolla gli URL (uno per riga).
3. **Modalità**: *Processa di gruppo* per avere un solo export da più file (ad
   esempio una serie di video con le slide); *Processa singolarmente* per un
   export per ogni file.
4. Per i video in gruppo, indica per ciascuno se è un *Webinar* o una *Pillola*
   e, se la sai, la data di registrazione.
5. **Modello** e **lingua** dell'output.
6. **File da avere in output**: spunta **Knowledge base per Agentforce** se il
   risultato va all'agente, più gli altri formati che ti servono.
7. Premi **Avvia elaborazione**. Puoi chiudere la pagina: la run continua.

**Scaricare il risultato** (pagina **Le mie richieste**): scegli la run
completata e premi **Scarica** per lo ZIP, oppure apri *Scarica singoli file di
output* per prendere solo il TXT.

La pagina **Guida** dentro la web app riassume gli stessi passi.

---

## 4. Usare la riga di comando

Comoda per elaborare molti contenuti di fila, anche di notte. Le run create così
compaiono anche nella web app.

**Il modo consigliato** è scrivere una *coda* in un file `runs.yaml`, partendo
dall'esempio:

```bash
cp runs.example.yaml runs.yaml
```

Struttura minima:

```yaml
settings:                 # valori validi per tutte le run
  content_type: video
  model_id: anthropic/claude-haiku-4.5
  language: it
  output_artifacts: html_standalone,procedura,glossario,kb
  parallel_runs: 3

runs:
  - name: formazione-gestionale        # diventa il nome di cartella e TXT
    inputs:
      - {source: file, path: input/webinar_giugno.mp4, kind: webinar, recorded_at: 2026-06-03}
      - {source: file, path: input/slide_formazione.pdf}
```

Poi avvia:

```bash
python -m doc_parser.cli --runs-file runs.yaml
```

Cosa aspettarti a schermo:

1. `Avvio N run con al massimo 3 worker paralleli.`
2. Poi **silenzio** per tutta la durata della run (anche molti minuti per un
   webinar lungo): è normale, il programma scrive solo alla fine.
3. `Run 'formazione-gestionale' completata (done).` oppure `fallita: …`
4. `Completate: N, Fallite: M`.

Se interrompi la coda, al riavvio riparte dalle run non ancora completate (il
promemoria è in `data/runs_checkpoint.json`).

### Rifare una run già fatta: `--force`

Senza istruzioni particolari il programma evita di rifare lavoro già fatto, e
quindi di pagarlo due volte:

1. le run della coda già **completate** vengono saltate;
2. un file **identico** a uno già elaborato con le stesse impostazioni (modello,
   lingua, tipo di contenuto, file di output) non viene riletto: la run risulta
   «duplicato» e riusa il risultato precedente.

Se invece vuoi una nuova elaborazione (ad esempio perché è cambiato il prompt o
vuoi confrontare due risultati), aggiungi `--force`:

```bash
python -m doc_parser.cli --runs-file runs.yaml --force
```

Con `--force`:

1. tutte le run della coda vengono rifatte, anche quelle già completate o
   duplicate;
2. ogni run nuova va in una **cartella nuova** (`nome-run_data_ora`, con `_2` se
   è lo stesso minuto): la cartella precedente **resta intatta**, niente viene
   sovrascritto;
3. la run costa come una run nuova.

`--force` vale anche con `--input-dir` e `--urls-file`. Non si usa con
`--resume`, che crea già sempre una run nuova.

**Valori di `output_artifacts`** (separati da virgola): `kb`, `html_standalone`,
`html_folder`, `procedura`, `glossario`, `rag_chunks`, `pptx` (solo video).

**Altri comandi utili:**

```bash
python -m doc_parser.cli --input-dir ./input --content-type manuale --output-artifacts kb
```

```bash
python -m doc_parser.cli --help
```

Il primo elabora ogni file di una cartella, uno per run. Il secondo elenca tutte
le opzioni.

---

## 5. Tre casi tipici

### Un webinar singolo

Web app: tipo **Video**, carica il file, spunta **Knowledge base per Agentforce**.

Coda YAML:

```yaml
runs:
  - name: webinar-fatturazione
    inputs:
      - {source: file, path: input/webinar_fatturazione.mp4}
    settings:
      content_type: video
      output_artifacts: kb,html_standalone
```

### Una serie di video con le slide

Più video della stessa formazione (webinar e pillole) e al massimo un PDF di
slide diventano un solo export, senza ripetizioni. Se le fonti si
contraddicono vince il webinar, poi le slide, poi le pillole; a parità vince la
registrazione più recente. Le scelte fatte sono elencate nel `log.txt`.

Web app: tipo **Video**, *Processa di gruppo*, carica video e PDF, etichetta ogni
video, spunta **Knowledge base per Agentforce**.

Coda YAML:

```yaml
runs:
  - name: formazione-gestionale
    inputs:
      - {source: file, order: 1, path: input/webinar_giugno.mp4, kind: webinar, recorded_at: 2026-06-03}
      - {source: file, order: 2, path: input/pillola_settembre.mp4, kind: pillola, recorded_at: 2026-09-12}
      - {source: file, order: 3, path: input/slide_formazione.pdf}
    settings:
      content_type: video
      output_artifacts: kb,html_standalone,pptx
```

### Un PDF

Per un manuale che alterna spiegazioni e procedure usa il tipo **Manuale**: è
quello che distingue meglio concetti e passi operativi.

```yaml
runs:
  - name: manuale-prodotto
    inputs:
      - {source: file, path: input/manuale_prodotto.pdf}
    settings:
      content_type: manuale
      output_artifacts: kb
```

---

## 6. Dove trovare i file

Ogni run completata ha la sua cartella in `data/artifacts/`, con il nome della
run e la data e ora di avvio:

```
data/artifacts/formazione-gestionale_2026-11-24_0854/
  formazione-gestionale_2026-11-24_0854.txt   ← Knowledge base per Agentforce
  documentazione_standalone.html
  procedura.txt
  log.txt
```

Il nome della run è il `name` della coda YAML, oppure il nome del file caricato,
oppure (per le serie caricate dalla web app) il titolo del documento. Ogni
elaborazione, comprese quelle forzate con `--force`, ha la sua cartella: se rifai
la stessa run nello stesso minuto, la cartella nuova prende `_2`, `_3`…. Le
versioni precedenti non vengono mai cancellate.

Lo stesso contenuto è anche nello ZIP scaricabile dalla web app.

---

## 7. Caricare il TXT in Agentforce

**Com'è fatto il file.** Agentforce non legge il file tutto insieme: lo spezza in
pezzi di circa 300–400 parole e all'agente arriva solo il pezzo che risponde
alla domanda. Per questo il TXT è diviso in sezioni brevi, e ognuna si capisce
anche da sola:

```
### Concetto: Nota di credito | Argomento: Fatturazione elettronica

La nota di credito è il documento che storna, in tutto o in parte, una fattura…

========================================

### Domanda e risposta: Si può annullare una fattura già inviata? | Argomento: Fatturazione elettronica

Domanda: Si può annullare una fattura già inviata?
Risposta: No. Una fattura accettata dal Sistema di Interscambio non si annulla…
```

Ordine delle sezioni: panoramica, concetti, procedure (quelle lunghe in più
parti), domande e risposte, glossario, note generali.

**Caricamento:**

1. In Salesforce apri **Setup** e cerca «Agentforce Data Library» nella ricerca
   rapida.
2. Apri la libreria collegata all'agente e carica il file `.txt` (limite 4 MB per
   file e 1.000 file per libreria).
3. Quando la libreria ha finito l'indicizzazione, guarda l'anteprima dei pezzi
   generati e fai all'agente 3–5 domande di prova sul contenuto.
4. Quando rifai una run sullo stesso argomento, elimina dalla libreria il file
   della versione precedente e carica il nuovo: il nome contiene la data, così
   distingui le versioni.

Se nell'anteprima vedi sezioni tagliate a metà, segnalalo a chi mantiene il
progetto: la lunghezza delle sezioni si regola con un solo valore (vedi il
capitolo 10).

**Costi.** Con la Knowledge base selezionata il modello estrae anche le
spiegazioni teoriche e le domande e risposte per intero, quindi la run costa un
po' di più. Le run senza Knowledge base costano e si comportano come prima.

---

## 8. Quando una run fallisce

1. **Leggi il motivo**: nella web app, pagine *Le mie richieste* o *Log tecnico*;
   da riga di comando, la riga `Run '…' fallita: …`.
2. **Serie di video fallita al consolidamento** (ad esempio «step sorgente non
   coperti» o «JSON non valido … troncata»): riprendila con un modello più capace
   senza ripagare la lettura dei video:

   ```bash
   python -m doc_parser.cli --resume <run_id> --model anthropic/claude-sonnet-5
   ```

   L'ID della run è nel *Log tecnico*. Se la ripresa chiede la Knowledge base e
   la run originale non l'aveva, i video vengono riletti da capo.
3. **Rielabora** (web app): riscrive una run video completata con un altro
   modello, senza rileggere il video. Per ottenere la Knowledge base la run
   originale deve averla già: altrimenti rifai la run completa con la casella
   spuntata.

---

## 9. Problemi comuni

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| `warning: The fitz API is deprecated…` | Avviso innocuo della libreria PDF | Nulla: la run prosegue |
| Nessun messaggio per molti minuti dopo `Avvio … run` | La run sta lavorando: la riga di comando scrive solo alla fine | Aspetta |
| `Nessuna run da eseguire (tutte già completate)` | Le run della coda sono già nel checkpoint | Aggiungi `--force` per rifarle in una cartella nuova |
| La run risulta «duplicato» e non chiama il modello | Lo stesso file è già stato elaborato con le stesse impostazioni | Aggiungi `--force` se vuoi comunque una nuova elaborazione |
| Il TXT non contiene i concetti o le domande e risposte | La run non aveva la Knowledge base selezionata | Rifai la run con `kb` negli output |
| `Rielabora rifiutata: … non ha estratto concetti …` | Si è chiesta la Knowledge base rielaborando una run fatta senza | Rifai la run completa con `kb` |
| `PDF di slide … oltre il limite di 50 MB` | PDF troppo grande | Comprimi il PDF o togli le slide inutili |
| `Saldo OpenRouter insufficiente` | Credito esaurito | Ricarica il credito OpenRouter |
| Immagini mancanti nell'HTML di un video | `ffmpeg` non installato | Installa ffmpeg |

L'elenco completo è in `RUNBOOK.md`, sezione «Troubleshooting».

---

## 10. Per chi mantiene il progetto

### Architettura

- `doc_parser/pipeline/core.py`: motore condiviso da web app e riga di comando.
  Guardrail, deduplica, step 1 (lettura del contenuto), consolidamento delle
  serie (`pipeline/consolidation.py`), step 2 (riscrittura), Rielabora e ripresa.
- `doc_parser/pipeline/kb_addendum.py`: istruzioni aggiunte allo step 1 solo nelle
  run con `kb`, per estrarre concetti e domande e risposte complete. I prompt
  protetti (`video_prompts.py`, `manuale_prompts.py`) non si modificano: si
  aggiunge testo in coda, come per le slide (`slides_addendum.py`).
- `doc_parser/providers/`: Gemini (API nativa) e OpenRouter, interfaccia comune
  `BaseProvider.generate()`.
- `doc_parser/output/`: builder dei file, sempre a partire dal JSON finale.
  `kb_builder.py` scrive il TXT Knowledge base (la lunghezza massima delle
  sezioni è `KB_SECTION_MAX_CHARS`); `naming.py` decide i nomi di cartelle e TXT.
- `doc_parser/storage/`, `worker/`, `auth/`: database SQLite, elaborazione in
  background, accesso con password.
- `doc_parser/ui/` e `doc_parser/cli/`: i due punti di ingresso.

La vecchia modalità `output_mode: kb_densa` (PDF → TXT a blocchi, solo da riga
di comando) è ancora disponibile; per Agentforce usa l'artefatto `kb`, che ha lo
stesso formato per video e PDF.

### Modelli e prezzi

I modelli disponibili sono in `models.yaml`, con i prezzi in EUR per milione di
token. Prima di cambiarli verifica ID e prezzi correnti sull'endpoint OpenRouter
`/api/v1/models` e sul listino ufficiale Gemini. Il file si rilegge a ogni run,
senza riavvio.

### Test

```bash
pytest doc_parser/tests/
```
