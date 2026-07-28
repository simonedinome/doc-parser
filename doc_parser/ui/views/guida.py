"""Pagina Guida: istruzioni d'uso della piattaforma dall'interfaccia Streamlit."""

from __future__ import annotations

import streamlit as st

from doc_parser.ui.context import get_app_context


def render() -> None:
    settings, _, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None:
        st.stop()

    st.title("Guida")
    st.caption("Come usare doc-parser dall'interfaccia web: pagina per pagina.")

    with st.expander("📄 Elabora — caricare ed elaborare un documento", expanded=True):
        st.markdown(
            f"""
La pagina **Elabora** è il punto di partenza: qui si carica il materiale e si
avvia l'elaborazione.

1. **Tipo di contenuto** — scegli tra *Documento*, *Manuale* o *Video*. La
   scelta determina come l'LLM interpreta e struttura l'output. Per i video
   viene sempre eseguita prima un'estrazione (step 1) e poi una riscrittura
   (step 2).
2. **File / URL** — carica uno o più file con il selettore, oppure incolla
   uno o più URL nel campo di testo (uno per riga, ad es. link diretti a
   video). Formati supportati: video (`.mp4`, `.mov`, `.avi`, `.mkv`,
   `.webm`), immagini (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp`),
   documenti (`.pdf`, `.docx`, `.doc`, `.xlsx`, `.csv`, `.txt`). Non è
   possibile mischiare immagini e altri documenti nello stesso caricamento.
   Limite: **{settings.max_upload_mb} MB** totali per richiesta.
3. **Modalità di elaborazione**:
   - *Processa di gruppo* — tutti i file caricati vengono uniti e producono
     un'unica documentazione (un solo output).
   - *Processa singolarmente* — ogni file o URL genera una run e un export
     separati.
4. **Modello** — seleziona il modello LLM da usare (elenco definito in
   `models.yaml`, con relativo costo per token).
5. **Lingua output** — Italiano o English.
6. **File da avere in output** — spunta i formati desiderati tra:
   - Documentazione HTML standalone (un unico file, immagini incorporate)
   - Documentazione HTML con cartella (screenshot separati)
   - Procedura (`procedura.txt`)
   - Glossario (`glossario.txt`)
   - Chunk RAG (`rag_chunks.jsonl`)

   Deve essere selezionato almeno un file di output.
7. Premi **Avvia elaborazione**. L'elaborazione parte in background: puoi
   chiudere il tab, lo stato della run resta visibile in fondo alla pagina
   (aggiornato automaticamente) e in **Le mie richieste**.
8. Quando la run è completata compare il pulsante **Scarica**. Se il
   documento risulta un duplicato di una richiesta precedente, l'output
   viene riutilizzato senza rielaborazione (nessun costo aggiuntivo).
            """
        )

    with st.expander("📋 Le mie richieste — stato, download e rielaborazione"):
        st.markdown(
            """
Elenca tutte le run avviate dall'utente collegato.

- **Riepilogo costi** — tre riquadri con costo e numero di run nelle ultime
  24 ore, 7 giorni e 28 giorni.
- **Tabella richieste** — una riga per run, con stato (🕓 in coda,
  ⚙️ in elaborazione, ✅ completata, ❌ fallita, 🚫 rifiutata, ♻️ duplicato),
  modello usato, costo e date. Si aggiorna automaticamente.
- **Scarica una run** — seleziona una run completata dal menu a tendina per
  scaricare lo ZIP completo dell'output. Espandendo *Scarica singoli file di
  output* e *Scarica file di input* è possibile scaricare i singoli
  artefatti generati o i file originariamente caricati.
- **Rielabora** — per le run video completate è possibile rigenerare solo lo
  step 2 (la riscrittura finale) con un modello diverso, riusando il JSON
  grezzo e gli screenshot già estratti in precedenza: nessun nuovo costo di
  estrazione, solo il costo della riscrittura con il nuovo modello.
            """
        )

    with st.expander("🗂️ Log — vista sintetica di tutte le richieste"):
        st.markdown(
            """
Vista di sola lettura, visibile a tutti gli utenti, con le run **di tutti**
gli utenti della piattaforma (non solo le proprie):

- **Riepilogo costi per utente** — tre finestre temporali (24h/7g/28g), una
  riga per utente con numero di run, token e costo.
- **Tabella richieste** — stessa proiezione sintetica di «Le mie richieste»,
  ma per tutti gli utenti. Non permette download né rielaborazione.
            """
        )

    if user.is_admin:
        with st.expander("🛠️ Log tecnico — solo amministratori"):
            st.markdown(
                """
Pagina visibile solo agli utenti con ruolo **admin**. Offre il dettaglio
completo per attività di supporto e controllo costi:

- **Riepilogo costi per utente** — come in Log.
- **Filtro periodo** (campi *Dal* / *Al*) — filtra tutte le sezioni
  sottostanti sull'intervallo di date scelto.
- **Tabella completa** — tutti i campi della run (non solo la vista
  sintetica), utile per il debug.
- **Download file** — scarica input e output di **qualunque** run, di
  qualunque utente.
- **Totali** — costo e token aggregati, con tre viste (per utente, per
  sessione, per singola run).
                """
            )
        st.info(
            "Sei amministratore: vedi anche la pagina «Log tecnico» nel menu "
            "laterale per il dettaglio completo e il download di run altrui."
        )

    with st.expander("❓ Domande frequenti"):
        st.markdown(
            f"""
**Perché la mia run è "🚫 Rifiutata"?**
Il file non ha superato i controlli preliminari: estensione non supportata,
dimensione oltre i {settings.max_upload_mb} MB, PDF cifrato o con troppe
pagine, oppure un mix non ammesso di immagini e documenti nello stesso
caricamento. Il motivo esatto è indicato nel messaggio di errore della run.

**Posso chiudere il browser mentre una run è in elaborazione?**
Sì: l'elaborazione avviene in un worker in background, indipendente dalla
sessione del browser. Ritrovi lo stato aggiornato in «Le mie richieste».

**Cosa significa "♻️ Duplicato"?**
Il documento (stesso contenuto, non solo stesso nome file) era già stato
elaborato in precedenza: l'output esistente viene riutilizzato senza
rieseguire l'LLM, così non si paga due volte per lo stesso file.

**Dove trovo l'elenco dei modelli disponibili e il loro costo?**
Nel selettore **Modello** della pagina Elabora; l'elenco e i prezzi sono
definiti in `models.yaml` e possono cambiare senza bisogno di riavviare
l'app.

**Come esco dall'app?**
Con il pulsante **Esci** nella barra laterale, sotto il tuo nome utente.
            """
        )
