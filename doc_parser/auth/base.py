"""Contratto astratto di autenticazione.

v1: password_auth (users.yaml + bcrypt). v2: easy_auth (header Entra ID a
monte, nessuna pagina di login) — stessa interfaccia, implementazione in più.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from doc_parser.core.models import User


class AuthProvider(ABC):
    @abstractmethod
    def get_current_user(self) -> User | None:
        """Utente autenticato della sessione corrente, o None."""

    @abstractmethod
    def get_session_id(self) -> str:
        """Identificativo della sessione applicativa corrente (GUID)."""

    def login_form(self) -> None:
        """Rende il form di login. Opzionale: i provider con autenticazione
        a monte (Easy Auth) non lo implementano."""

    def logout(self) -> None:
        """Chiude la sessione corrente. Opzionale."""
