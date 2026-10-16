# Piano — doc-parser: export unico video + slide, deduplica tra video, PPT tutorial

Branch di partenza: `claude/streamlit-guide-section-c7zbcu` (commit `da567c3`). Branch di lavoro: `feat/video-pdf-consolidamento`. Stima totale: circa 17 ore e 30 minuti di lavoro. Percorsi: i moduli sono relativi a `doc_parser/`; `requirements.txt`, `runs.example.yaml`, `README.md` e `RUNBOOK.md` stanno nella radice del repo.

## Come usare questo file

1. Copia il file in `docs/plans/video-pdf-consolidamento.md` sul branch di lavoro.
2. In Claude Code incolla: «Leggi docs/plans/video-pdf-consolidamento.md ed esegui i task in ordine, uno alla volta. Dopo ogni task esegui `pytest doc_parser/tests/`, fai un commit e spunta la casella nel file. Fermati e chiedimi conferma prima di toccare un file protetto, o se un criterio di accettazione non è raggiungibile.»
3. Se in Claude Code hai il plugin agent-skills, puoi lanciare `/agent-skills:build` su questo file invece del prompt al punto 2.

## Obiettivo (intento confermato il 15/10/2026)

Una run `video` accetta uno o più video, ciascuno etichettato webinar o pillola e con data di registrazione facoltativa, più al massimo un PDF di slide. Ne esce un unico export consolidato: procedure e nozioni complete e non ripetute, comprese le slide che i video non trattano. Le discordanze si risolvono con la priorità webinar > slide > pillola e finiscono nel `log.txt` della run, con fonti e date. Tra gli output si aggiunge un PPT tutorial a layout neutro, pensato per un formatore che lo proietta agli hotel.

## Vincoli non negoziabili

1. Prompt protetti. `pipeline/video_prompts.py` e `pipeline/manuale_prompts.py` non si modificano. L'addendum per le slide vive in un modulo nuovo; Simone lo ha approvato il 15/10/2026. La bozza del testo è nella sezione "Contratti dati" e va confermata in review.
2. Unica fonte. Il JSON finale resta l'unica fonte di tutti gli output: HTML, TXT, RAG, PPT e log.
3. Validazione step 2 invariata. `pipeline/step2_validate.py` non cambia: il consolidamento avviene prima dello step 2.
4. Nessuna regressione. Questi percorsi si comportano come oggi e i 228 test esistenti restano verdi:
   1. video singolo senza PDF;
   2. `screencast` (legacy);
   3. documento, manuale, immagini e KB densa;
   4. Rielabora;
   5. dedup per hash.
5. Repo pubblico. Niente video, PDF o JSON reali del cliente nei commit o nei fixture di test. I file del task 1 restano in locale.

## Decisioni prese

Sono prese per far partire il lavoro. Si possono cambiare fino all'avvio del task che le implementa.

1. Quando si consolida. Solo per le run `video` con almeno due fonti: due o più video, oppure video + PDF. Il video singolo senza PDF e `screencast` usano il percorso attuale.
2. Modello del consolidamento. È il modello scelto in UI o CLI (lo stesso dello step 2), con il PDF allegato.
3. Priorità. Webinar > slide > pillola. A parità di tipo vince la registrazione più recente; se la data manca, vince l'ultima in ordine di caricamento. La regola di parità è una proposta di Claude, non una richiesta di Simone (resa totale dall'emendamento 2).
4. Provenienza calcolata dal codice. Video, timestamp e slide di ogni step li ricava il codice dai riferimenti `merged_from`. Il modello indica solo quali step sorgente ha unito, così fonti e immagini non possono essere inventate.
5. Step 2 senza provenienza. I campi di provenienza vengono tolti prima dello step 2 e riattaccati dopo, per ID procedura e numero step. Lo stesso vale per Rielabora.
6. PPT. La checkbox `pptx` è spenta di default ed è disponibile solo per le run video. La fonte di ogni step va nelle note del relatore, non sulla slide.
7. Costi. I costi del consolidamento vanno in colonne dedicate della tabella `runs`, con migrazione automatica dei DB esistenti. Senza migrazione, `create_run` fallirebbe sui `runs.db` già esistenti, perché `_init_schema` usa `CREATE TABLE IF NOT EXISTS` e non aggiunge colonne.

## Contratti dati

### Manifest degli input: nuovi campi facoltativi

```json
[
  {"filename": "webinar_giugno.mp4", "path_ref": "...", "input_id": "v1", "role": "video", "kind": "webinar", "recorded_at": "2026-06-03"},
  {"filename": "pillola_settembre.mp4", "path_ref": "...", "input_id": "v2", "role": "video", "kind": "pillola", "recorded_at": "2026-09-12"},
  {"filename": "slide.pdf", "path_ref": "...", "input_id": "pdf", "role": "slides"}
]
```

Retrocompatibilità: se una voce non ha i nuovi campi, `role` si ricava dall'estensione, `kind` vale `webinar` e `input_id` viene assegnato in ordine (`v1`, `v2`, …).

### Step 1 con PDF: addendum (bozza da confermare)

Si appende ai prompt protetti, come fa oggi `apply_language_directive`, e solo quando il PDF è presente.

```text
[SYSTEM]
Insieme al video ricevi il PDF delle slide della stessa formazione.
Usa le slide solo per rendere esatti nomi di pulsanti, menu, campi, valori e termini che nel video sono poco leggibili o pronunciati in modo ambiguo.
Se slide e video riportano informazioni diverse, documenta ciò che mostra il video e segnala la differenza nel campo "notes" dello step, iniziando con "DISCORDANZA SLIDE:".
Non creare procedure o step da slide che il video non tratta.

[USER]
Aggiungi a ogni step il campo "source_slides": array dei numeri di pagina del PDF (da 1) delle slide mostrate o direttamente collegate a quello step; array vuoto se nessuna è pertinente.
```

Lo step 1 non risolve le discordanze, le segnala soltanto. Così il consolidamento può applicare la priorità e scriverle nel log. Questo vale anche per le pillole, dove la slide deve vincere.

### Consolidamento: input al modello

1. Il PDF arriva come allegato, con `input_id` `pdf` e numeri di slide uguali ai numeri di pagina.
2. Per ogni video c'è un'intestazione `=== FONTE v1 · webinar · registrato il 2026-06-03 · webinar_giugno.mp4 ===`, seguita dal suo JSON di step 1. Il codice aggiunge a ogni step il campo `"ref": "v1/proc_002/3"` prima dell'invio.

### Consolidamento: output del modello

```json
{
  "title": "...", "summary": "...", "prerequisites": ["..."],
  "concepts": [
    {"title": "...", "content": "...", "embedding_keywords": ["..."], "merged_from": [], "slides": [3]}
  ],
  "procedures": [
    {"title": "...", "steps": [
      {"merged_from": ["v2/proc_001/3"]},
      {"title": "...", "description": "...", "notes": "", "embedding_keywords": ["..."],
       "merged_from": ["v1/proc_002/1", "v2/proc_001/4"], "slides": [12]}
    ]}
  ],
  "glossary": [{"term": "...", "definition": "..."}],
  "notes": ["..."],
  "conflicts": [{"topic": "...", "chosen": "v1/proc_002/1", "discarded": ["v2/proc_001/4", "pdf/12"], "reason": "..."}],
  "dropped": [{"ref": "v2/proc_003/1", "reason": "saluti, nessun contenuto operativo"}],
  "skipped_slides": [{"slide": 1, "reason": "copertina"}]
}
```

Uno step con un solo riferimento e nessun testo viene copiato dalla fonte. Questo riduce i token in uscita e il rischio di perdere dettagli.

### Regole di validazione (codice, `pipeline/consolidation.py`)

Errori bloccanti. Il codice riprova con un messaggio di feedback e con lo stesso numero di tentativi di `_run_step2` (`retry_max_attempts` + 1); poi la run va in FAILED e i JSON di step 1 restano salvati.

1. Il JSON non è valido o mancano `title`, `summary`, `prerequisites`, `procedures`, `glossary` o `notes`. Il messaggio d'errore deve citare la possibile risposta troncata: serie troppo lunga per il modello scelto.
2. Un riferimento in `merged_from`, `chosen`, `discarded` o `dropped` non esiste. Per i riferimenti `pdf/N`, N deve essere un numero di pagina valido.
3. Copertura. Uno step sorgente non compare in nessun `merged_from` e nemmeno in `dropped`.
4. Tracciabilità. Uno step o un concetto ha sia `merged_from` sia `slides` vuoti.
5. Uno step con due o più riferimenti, oppure con zero riferimenti, non ha `title` e `description`.

Errori non bloccanti. Il codice chiede la correzione nei tentativi rimasti; se non arriva, prosegue e scrive un avviso nel log.

1. Un conflitto in cui `chosen` ha priorità più bassa di una voce in `discarded`.
2. Slide che non compaiono in nessuno step o concetto e nemmeno in `skipped_slides`.
3. Testo finale che contiene ancora `DISCORDANZA SLIDE:`.
4. Slide fuori dall'intervallo valido: vengono rimosse dal codice.

### JSON consolidato arricchito (diventa `raw.json`, base anche per Rielabora)

1. ID deterministici: `proc_001`… e `con_001`…, step numerati da 1 in ogni procedura.
2. Per ogni step e concetto:
   1. `sources`: `[{"input_id","filename","kind","recorded_at","timestamps"}]`, ricavato dai riferimenti;
   2. `source_slides`: unione delle `slides` e delle `source_slides` degli step sorgente;
   3. `merged_from`: conservato per tracciabilità.
3. Top level: `source_inputs` (descrittori degli input) e `consolidation_log`. Quest'ultimo contiene `conflicts`, risolti con nome file, tipo e data, poi `dropped`, `skipped_slides`, `uncovered_slides` e `warnings`.

## Task

1. [ ] Task 1 — Spike con le chiavi reali · 45 min · dipende da: nessuno · **eseguito da Simone in locale**
   1. Scrivi uno script locale, da non committare, che chiama `GeminiProvider.generate` con `VIDEO_SYSTEM_PROMPT` e `VIDEO_USER_PROMPT` più la bozza di addendum. Allega un video vero di 2–5 minuti e il suo PDF.
   2. Lo spike è superato se:
      1. la risposta arriva senza errori API;
      2. `parser.parse_response(raw, "video")` va a buon fine;
      3. almeno uno step ha `source_slides` coerente con la slide mostrata nel video.
   3. Misura la dimensione reale degli output con `SELECT input_filename, step1_tokens_out FROM runs WHERE input_type='video' ORDER BY step1_tokens_out DESC LIMIT 10` sul `runs.db` in uso. Serve a stimare quanto sarà lungo l'output del consolidamento per una serie.
   4. Se Gemini rifiuta video e PDF nella stessa chiamata, ripiega sulle pagine del PDF allegate come PNG renderizzati con PyMuPDF e aggiorna il task 6. Riporta l'esito nella descrizione della PR.
2. [x] Task 2 — Branch e baseline · 15 min · dipende da: nessuno
   1. Crea `feat/video-pdf-consolidamento` da `claude/streamlit-guide-section-c7zbcu`.
   2. Aggiungi `python-pptx>=1.0.2` a `requirements.txt`.
   3. Accettazione: `pip install -r requirements.txt` funziona e `pytest doc_parser/tests/` dà 228 test passati.
3. [x] Task 3 — Migrazione DB e colonne dei costi di consolidamento · 45 min · dipende da: 2
   1. In `core/models.py`, `RunRecord` riceve `consolidation_model`, `consolidation_tokens_in`, `consolidation_tokens_out` e `consolidation_cost_eur`, tutti facoltativi.
   2. In `storage/sqlite_repo.py`, `_init_schema` legge `PRAGMA table_info(runs)` e lancia `ALTER TABLE runs ADD COLUMN` per ogni colonna mancante, con il tipo da `_column_type`.
   3. In `ui/format.py`, `friendly_row` riceve la colonna "Costo consolidamento (EUR)".
   4. Test: un `runs.db` creato con lo schema vecchio viene aperto da `SqliteRepository`; `create_run` funziona e i nuovi campi fanno il giro completo di scrittura e lettura.
4. [x] Task 4 — Modello degli input: guardrail, manifest, loader · 1 h · dipende da: 2
   1. In `ingestion/guardrails.py`:
      1. `resolve_input_type(is_video, filenames, allow_slides_pdf=False)` accetta al massimo un PDF, ma solo se `allow_slides_pdf` è vero. Il chiamante lo passa vero solo per il content type `video`.
      2. Serve sempre almeno un video. I messaggi d'errore sono in italiano e dicono cosa fare.
      3. Nuova `check_slides_pdf(data, max_pages)`: usa `inspect_pdf` e applica un tetto di 50 MB, il limite di Gemini per i PDF.
   2. Nuovo modulo `pipeline/inputs.py` con il dataclass `InputFile(filename, data, input_id, role, kind, recorded_at)` e `load_inputs(run, repo)`. `load_inputs` legge il manifest con i default di retrocompatibilità. `_load_input_files` resta per gli altri percorsi.
   3. Test:
      1. video + PDF accettati;
      2. due PDF rifiutati;
      3. solo PDF rifiutato;
      4. PDF con `allow_slides_pdf=False` rifiutato;
      5. PDF da 51 MB rifiutato;
      6. manifest vecchio letto con i valori di default.
5. [x] Task 5 — CLI: etichette e date nella coda YAML · 45 min · dipende da: 4
   1. In `cli/config.py`, `InputSource` riceve `kind` (`webinar` o `pillola`) e `recorded_at` (data ISO). Un valore non valido produce un `ValueError` che nomina la run.
   2. In `cli/queue_runner.py`, il manifest viene scritto con i metadati e `allow_slides_pdf` vale vero se il content type effettivo è `video`.
   3. In `runs.example.yaml` aggiungi l'esempio 4: due webinar, una pillola e un PDF di slide in una sola run.
   4. In `cli/main.py`, l'help di `--output-artifacts` elenca anche `pptx`.
   5. Test: kind non valido, data non valida, esempio YAML caricato correttamente, manifest scritto con i metadati.
6. [ ] Task 6 — Step 1 con PDF · 1 h · dipende da: 1, 4
   1. Nuovo modulo `pipeline/slides_addendum.py` con `apply_slides_addendum(system, user)` e il testo approvato.
   2. Nel nuovo percorso consolidato, ogni chiamata di step 1 riceve video + PDF e l'addendum. Il modello di step 1 segue la logica attuale di `_process_video`: `step1_video_model`, oppure il Gemini scelto se `single_pass_gemini`.
   3. In `pipeline/parser.py`, normalizza `source_slides` in una lista di interi, come già si fa per `source_pages`.
   4. Test:
      1. con il PDF, ogni chiamata ha 2 allegati (video e `application/pdf`) e `VIDEO_SYSTEM_PROMPT` è un prefisso intatto del prompt di sistema;
      2. senza PDF non c'è addendum;
      3. `git diff --stat` non tocca `video_prompts.py` né `manuale_prompts.py`.
7. [ ] Task 7 — Consolidamento · 3 h 30 min · dipende da: 3, 6
   1. Nuovi moduli:
      1. `pipeline/consolidation_prompts.py`, con un prompt nuovo e non protetto. Regole essenziali:
         1. unire gli step che descrivono la stessa azione, anche se ripetuti nei ripassi;
         2. non perdere né inventare informazioni;
         3. applicare la priorità con la regola di parità;
         4. trasformare le slide non trattate in procedure se operative, in concetti se teoriche;
         5. deduplicare glossario, prerequisiti e note, comprese le Q&A ripetute;
         6. ordinare il materiale in un percorso didattico;
         7. scrivere in stile impersonale, senza citare video, relatore o slide.
      2. `pipeline/consolidation.py`, con `build_request`, `validate` (le regole della sezione "Contratti dati"), `enrich` e `ConsolidationValidationError`.
   2. In `pipeline/core.py`, `_process_video` instrada su `_process_video_consolidated` quando il content type è `video` e ci sono almeno due fonti. La sequenza è:
      1. step 1 per ogni video, salvato come `step1_v{n}.json`;
      2. consolidamento con retry e feedback;
      3. arricchimento e salvataggio come `raw.json`;
      4. immagini (task 8);
      5. step 2 (task 9), saltato se `single_pass_gemini`;
      6. output. Il costo totale è step 1 + consolidamento + step 2.
   3. Test unitari su `consolidation.py`:
      1. riferimento sconosciuto;
      2. step sorgente non coperto;
      3. step non tracciabile;
      4. copia del testo per gli step a riferimento singolo;
      5. priorità violata, prima con feedback e poi con avviso;
      6. slide fuori intervallo;
      7. slide non coperte;
      8. ID deterministici;
      9. `sources` con tipo, data e timestamp corretti.
   4. Test di pipeline con `ScriptedProvider`, due video e un PDF:
      1. 2 chiamate di step 1, 1 di consolidamento e 1 di step 2;
      2. nessuna procedura duplicata;
      3. costi per fase valorizzati.
8. [ ] Task 8 — Immagini per step e concetto · 1 h 30 min · dipende da: 7
   1. In `pipeline/screenshots.py`, nuova `extract_step_images(...)` che riusa ffmpeg e PyMuPDF. L'immagine principale `{proc}_step_{n:03d}.png` si cerca in questo ordine:
      1. timestamp di un webinar, dal più recente;
      2. prima slide;
      3. timestamp di una pillola. Se un'estrazione fallisce si passa al candidato successivo.
   2. Immagini secondarie:
      1. `{proc}_step_{n:03d}_slide.png`, solo se lo step ha slide e l'immagine principale non è già una slide;
      2. `{con_id}_slide.png` per i concetti che hanno slide.
   3. In `pipeline/core.py`, accanto a `_reconstruct_screenshot_map`, aggiungi le ricostruzioni per nome delle mappe slide e concetti, così Rielabora le ritrova.
   4. In `output/html_builder.py`, la slide compare accanto allo screenshot (griglia a 2 colonne che si impila su schermi stretti), con didascalia "Slide N" in IT/EN. I concetti mostrano la propria slide.
   5. Test con `subprocess` mockato e un PDF generato al volo:
      1. il webinar vince sulla pillola;
      2. la slide viene usata se manca il webinar;
      3. la pillola viene usata per ultima;
      4. un'estrazione fallita passa al candidato successivo;
      5. l'HTML contiene due immagini quando ci sono entrambe.
9. [ ] Task 9 — Step 2 e Rielabora con provenienza · 45 min · dipende da: 7
   1. In `_run_step2` di `pipeline/core.py`, prima della chiamata si tolgono:
      1. a livello di step e concetto: `sources`, `source_slides`, `merged_from` e `slides`;
      2. al top level: `source_inputs` e `consolidation_log`. Dopo la validazione si riattaccano per ID e numero. Copre anche Rielabora.
   2. Test:
      1. il prompt dello step 2 non contiene `merged_from` né `consolidation_log`;
      2. `final.json` ha la provenienza riattaccata;
      3. la Rielabora di una run consolidata mantiene log, provenienza e immagini.
10. [ ] Task 10 — `log.txt` con le discordanze · 45 min · dipende da: 7
    1. Nuovo modulo `output/consolidation_report.py` con `build_consolidation_lines(data, language)`, chiamato in `_build_and_persist_output` e aggiunto alle righe del `Logger`. Il `log.txt` esiste già in ogni zip. Le sezioni sono:
       1. FONTI;
       2. DISCORDANZE (tema, fonte tenuta, fonti scartate con file, tipo, data e timestamp o slide, motivo);
       3. CONTENUTI SCARTATI;
       4. SLIDE NON INCLUSE;
       5. AVVISI.
    2. Se una fonte scartata è più recente di quella tenuta, la riga inizia con `ATTENZIONE: fonte scartata più recente, verificare`.
    3. Le etichette vanno in `output/strings.py`, in IT e EN.
    4. Test: rendering di conflitti, avviso di recenza, etichette EN, log invariato per le run senza consolidamento.
11. [ ] Task 11 — PPT tutorial · 2 h 30 min · dipende da: 8
    1. Nuovo modulo `output/pptx_builder.py` con `build_pptx(data, screenshot_map, concept_image_map, language) -> bytes`. In `output/assembly.py`, la chiave `pptx` produce `presentazione_tutorial.pptx`. `_build_and_persist_output` toglie `pptx` dagli artefatti delle run non video e scrive un avviso nel log.
    2. Layout:
       1. formato 16:9 (13,333 × 7,5 pollici), layout vuoto, sfondo bianco;
       2. testo `#212529`, accento `#1a73e8` (lo stesso dell'HTML), testo secondario `#5f6368`.
    3. Sequenza delle slide:
       1. Copertina: titolo e sommario troncato.
       2. Agenda: concetti e procedure, 10 voci per slide.
       3. Prerequisiti.
       4. Sezione Concetti: una slide per concetto, con l'immagine della slide se c'è, altrimenti il testo. Il testo completo va nelle note.
       5. Una slide di sezione per ogni procedura ("Procedura i di N", titolo, numero di step). Poi una slide per step:
          1. titolo `Step k/n · titolo`;
          2. immagine grande adattata all'area di 12,3 × 5,6 pollici senza deformarla;
          3. se lo step non ha immagine, la descrizione sulla slide;
          4. note del relatore con descrizione, note e fonte (file, tipo, data, timestamp, slide).
       6. Glossario: 8 termini per slide.
       7. Domande e risposte e note generali: 6 per slide.
    4. Nessun tetto alla lunghezza. Il testo troppo lungo sulla slide si tronca con "…" e resta completo nelle note.
    5. Test, riaprendo il file con python-pptx:
       1. il numero di slide corrisponde alla struttura attesa;
       2. ogni slide step ha note con la descrizione;
       3. ogni step con immagine ha 1 immagine;
       4. uno step senza immagine mostra il testo;
       5. le etichette EN sono corrette;
       6. lo zip contiene il PPT solo se richiesto.
12. [ ] Task 12 — UI Elabora e Guida · 1 h 30 min · dipende da: 4, 11
    1. In `ui/views/elabora.py`, con content type Video:
       1. per ogni video, caricato o da URL, compaiono un selettore Webinar/Pillola (default Webinar) e `st.date_input` facoltativo con `value=None`;
       2. il manifest viene scritto con i metadati;
       3. se c'è un PDF e la modalità è "Processa singolarmente", compare l'errore «Per usare un PDF di slide scegli "Processa di gruppo"»;
       4. la checkbox PPT compare solo per Video ed è spenta di default.
    2. Estrai la costruzione del manifest in una funzione pura, così si può testare.
    3. In `ui/views/guida.py`, aggiungi una sezione su etichette, PDF di slide, priorità, log delle discordanze e PPT.
    4. Test: con `AppTest`, la checkbox PPT appare con Video e non con Documento; test unitario della funzione del manifest.
13. [ ] Task 13 — Test end-to-end e regressioni · 1 h · dipende da: 5, 9, 10, 11, 12
    1. Coda YAML con due webinar, una pillola e un PDF, provider mockati. Lo zip contiene HTML, procedura, glossario, RAG, PPT e `log.txt`, e il log ha la sezione DISCORDANZE.
    2. Video singolo senza PDF: esattamente 1 chiamata di step 1 e 1 di step 2, nessuna di consolidamento.
    3. `screencast` con più file: merge come oggi (il test esistente resta invariato).
    4. Modello Gemini con consolidamento: niente step 2.
    5. Accettazione: tutti i test verdi.
14. [ ] Task 14 — Documentazione · 30 min · dipende da: 13
    1. `README.md`: esempio YAML con video, PDF ed etichette; nuovi output (PPT, sezioni del log).
    2. `RUNBOOK.md`: migrazione automatica del DB; nuovi errori del consolidamento e cosa fare.
15. [ ] Task 15 — Collaudo con una serie reale (Simone) · 1 h · dipende da: 14
    1. Fai girare, in locale e senza commit, due webinar, una pillola e il deck.
    2. Verifica questi cinque punti:
       1. nessuna procedura ripetuta nell'HTML;
       2. ogni discordanza nel log è verificabile aprendo il video al timestamp indicato;
       3. il PPT si apre in PowerPoint, sezioni e note sono corrette e le immagini sono leggibili proiettate;
       4. Rielabora con un altro modello mantiene log e immagini;
       5. costo totale = step 1 + consolidamento + step 2.

## Edge case: comportamento atteso

1. Solo PDF con content type Video: rifiuto, «serve almeno un video».
2. Due PDF: rifiuto, «massimo un PDF di slide».
3. PDF cifrato, oltre `MAX_PAGES` o oltre 50 MB: rifiuto con messaggio esplicito.
4. Video senza etichetta (manifest vecchi o YAML senza `kind`): trattato come webinar.
5. Step senza alcuna immagine: slide PPT solo testo, HTML senza immagine.
6. Timestamp oltre la durata del video: clamp come oggi, con avviso nel log.
7. Consolidamento fallito dopo i retry: run FAILED, `step1_v{n}.json` conservati, messaggio che suggerisce un modello con output più lungo o di dividere la serie.
8. `pptx` richiesto via CLI per una run non video: artefatto saltato, avviso nel log.

## Rischi aperti

1. Video e PDF nella stessa chiamata Gemini. La documentazione non lo conferma esplicitamente: lo verifica il task 1, che ha anche un fallback.
2. Serie molto lunghe. L'output del consolidamento può superare il limite di output del modello scelto. Il task 1 misura le dimensioni reali; l'errore è esplicito e non silenzioso.
3. Qualità della deduplica. Dipende dal modello scelto: con il modello economico conviene verificare il log nel collaudo.
4. Pillola più recente con interfaccia aggiornata. Perde contro webinar e slide per la regola confermata. Il log la segnala con ATTENZIONE.

## Fuori scope

1. Deduplica e PPT per le run documento e manuale.
2. Template PowerPoint aziendale del cliente.
3. Deduplica tra run diverse.
4. Riconoscimento automatico tra webinar e pillola.
5. Abbinamento automatico tra video e PDF nella modalità batch a cartella.

---

## Emendamenti dopo la verifica sul codice (Claude, 16/10/2026)

Verifica al commit `da567c3`. Le decisioni marcate "Simone" sono state confermate in chat il 16/10/2026.

1. **Retry con i dati (task 7).** `_run_step2`, al retry, sostituisce il prompt con il solo feedback (`pipeline/core.py:346`): il provider è single-turn, quindi dal secondo tentativo il modello non vede più il JSON. Il consolidamento non copia questo schema: ogni retry rimanda richiesta originale (PDF compreso), risposta precedente e correzioni puntuali. Si tiene l'ultimo candidato senza errori bloccanti; se i tentativi finiscono su un errore bloccante e un candidato valido esiste, si usa quello con gli avvisi.
2. **Regola di parità totale (task 7).** Applicata a coppie, "se la data manca vince l'ultima caricata" non è transitiva quando solo alcune fonti hanno la data. Regola adottata: un'unica chiave d'ordinamento — tipo, poi "con data" prima di "senza data", poi data, poi ordine di caricamento. Vale per prompt, validazione, immagini e riga ATTENZIONE.
3. **Normalizzazione dello step 1 (task 7).** Il codice rinumera procedure e step di ogni video prima di costruire i `ref`; `step1_v{n}.json` salva la versione normalizzata.
4. **Validazione dopo la copia (task 7).** Le regole si controllano dopo la copia degli step a riferimento singolo. Concetti senza `title`/`content` e procedure senza `title` o senza step sono errori bloccanti. `pdf/N` è ammesso anche in `merged_from`. La richiesta indica il numero di pagine del PDF.
5. **Ordine di salvataggio (task 7–8).** Arricchimento → immagini → `raw.json`, così gli avvisi di estrazione entrano in `consolidation_log.warnings` e nel log. Nel percorso esistente gli avvisi di clamp restano in `error_message`; il RUNBOOK si corregge nel task 14.
6. **Costi anche in caso di errore (task 7).** Nel percorso consolidato `cost_eur` e `tokens_*` si aggiornano dopo ogni fase.
7. **File omonimi (task 5, 7, 12).** Nei manifest video il file si salva come `{input_id}_{filename}`; nel manifest resta il nome originale. Idem nella cartella temporanea della pipeline.
8. **Date YAML (task 5).** PyYAML converte le date non quotate in `datetime.date`: la validazione accetta `date` e stringhe ISO.
9. **Task 6 prima del 7.** Il task 6 consegna un helper testabile da solo (prompt e allegati di step 1), cablato nel task 7. Il controllo `git diff --stat` sui prompt protetti è un comando di verifica, non un test pytest.
10. **Righe del log senza prefisso (task 10).** `Logger.add_block(lines)` aggiunge righe senza timestamp.
11. **Migrazione concorrente (task 3).** L'errore "duplicate column name" di un `ALTER TABLE` parallelo si ignora.
12. **`source_slides` (task 6).** Conversione vera in interi ≥1 (anche da "Slide 3"); il resto si scarta.
13. **Marcatore in inglese (addendum, da confermare in review).** Proposta: aggiungere all'addendum «Mantieni il prefisso "DISCORDANZA SLIDE:" esattamente così, in qualunque lingua».
14. **Percorso didattico (task 7).** L'ordine didattico vale dentro concetti e dentro procedure; l'alternanza tra i due richiederebbe un cambio di schema, fuori scope.
15. **PPT senza consolidamento (task 11).** Senza `sources`, le note del relatore usano `source_timestamps`/`timestamp`.
16. **Selettori in UI (task 12).** Webinar/Pillola e data compaiono solo con "Processa di gruppo".
17. **Retry dello step 2 (task 9, Simone).** Al retry `_run_step2` manda il JSON grezzo seguito dal feedback, invece del solo feedback. Vale anche per Rielabora.
18. **Branch e PR (Simone).** PR in bozza con base `claude/streamlit-guide-section-c7zbcu`.
19. **Spike in parallelo (Simone).** Il task 1 lo esegue Simone in locale; gli altri task procedono, con gli allegati di step 1 costruiti in un'unica funzione per applicare l'eventuale ripiego PNG.
