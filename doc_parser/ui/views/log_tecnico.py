"""Pagina Log tecnico (solo admin): tabella completa, totali e filtro periodo."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import streamlit as st

from doc_parser.core.models import RunStatus
from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import (
    cost_summary_windows,
    fmt_dt,
    input_download_entries,
    output_artifact_entries,
)


def render() -> None:
    _, repo, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None or not user.is_admin:
        st.error("Accesso riservato agli amministratori.")
        st.stop()

    st.title("Log tecnico")

    st.subheader("Riepilogo costi per utente")
    for idx, (label, rows) in enumerate(cost_summary_windows(repo)):
        with st.expander(label, expanded=(idx == 0)):
            if rows:
                st.dataframe(
                    [
                        {
                            "Utente": r["group_key"],
                            "Run": r["run_count"],
                            "Token": r["tokens_total"],
                            "Costo (EUR)": f"{r['cost_eur']:.4f}",
                        }
                        for r in rows
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Nessuna run nel periodo.")
    st.divider()

    today = datetime.now(timezone.utc).date()
    col_from, col_to = st.columns(2)
    date_from = col_from.date_input("Dal", value=today - timedelta(days=30))
    date_to = col_to.date_input("Al", value=today)
    since = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    until = datetime.combine(date_to, time.max, tzinfo=timezone.utc)

    runs = repo.list_runs(since=since, until=until, limit=1000)
    st.caption(f"{len(runs)} run nel periodo selezionato")

    st.subheader("Run (tabella completa)")
    rows = []
    for run in runs:
        row = run.model_dump()
        for field in ("created_at", "started_at", "completed_at"):
            row[field] = fmt_dt(getattr(run, field))
        row["status"] = run.status.value
        rows.append(row)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Nessuna run nel periodo.")

    downloadable = [r for r in runs if r.status in (RunStatus.DONE, RunStatus.DUPLICATE)]
    if downloadable:
        st.subheader("Download file (input/output di qualunque run)")
        options = {f"{r.requester_upn} — {r.input_filename} — {r.run_id[:8]}": r for r in downloadable}
        choice = st.selectbox("Run", list(options))
        run = options[choice]

        if run.output_path:
            st.download_button(
                "Scarica output (zip completo)",
                data=repo.get_file(run.output_path),
                file_name=f"{run.run_id[:8]}_output",
                key=f"tech_dl_output_{run.run_id}",
            )
        for name, path in output_artifact_entries(run):
            st.download_button(
                f"Output: {name}",
                data=repo.get_file(path),
                file_name=name,
                key=f"tech_dl_artifact_{run.run_id}_{name}",
            )
        for name, ref in input_download_entries(repo, run):
            st.download_button(
                f"Input: {name}",
                data=repo.get_file(ref),
                file_name=name,
                key=f"tech_dl_input_{run.run_id}_{name}",
            )

    st.subheader("Totali")
    tab_user, tab_session, tab_run = st.tabs(["Per utente", "Per sessione", "Per run"])
    for tab, by in ((tab_user, "user"), (tab_session, "session"), (tab_run, "run")):
        with tab:
            aggregates = repo.aggregate_costs(by=by, since=since, until=until)
            if not aggregates:
                st.info("Nessun dato nel periodo.")
                continue
            total_cost = sum(row["cost_eur"] or 0 for row in aggregates)
            total_tokens = sum(row["tokens_total"] or 0 for row in aggregates)
            metric_cost, metric_tokens = st.columns(2)
            metric_cost.metric("Costo totale (EUR)", f"{total_cost:.4f}")
            metric_tokens.metric("Token totali", f"{total_tokens:,}")
            st.dataframe(aggregates, use_container_width=True, hide_index=True)
