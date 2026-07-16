"""Risorse condivise della web app: settings, repository, auth e worker.

Il worker parte una sola volta per processo (st.cache_resource) e gira in un
thread separato: le pagine non elaborano mai l'input dentro la richiesta.
"""

from __future__ import annotations

import streamlit as st

from doc_parser.auth import get_auth_provider
from doc_parser.auth.base import AuthProvider
from doc_parser.settings import Settings, get_settings
from doc_parser.storage import get_repository
from doc_parser.storage.base import Repository
from doc_parser.worker.processor import Worker


@st.cache_resource(show_spinner="Avvio dell'applicazione…")
def get_app_context() -> tuple[Settings, Repository, AuthProvider, Worker]:
    settings = get_settings()
    repo = get_repository(settings)
    auth = get_auth_provider(settings)
    worker = Worker(repo=repo, settings=settings)
    worker.start()
    return settings, repo, auth, worker
