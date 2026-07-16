"""Pagina Log tecnico (solo admin): tabella completa, totali e filtro periodo."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import streamlit as st

from doc_parser.ui.context import get_app_context
from doc_parser.ui.format import fmt_dt


def render() -> None:
    _, repo, auth, _ = get_app_context()
    user = auth.get_current_user()
    if user is None or not user.is_admin:
        st.error("Accesso riservato agli amministratori.")
        st.stop()

    st.title("Log tecnico")

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
