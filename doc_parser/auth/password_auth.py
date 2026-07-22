"""Autenticazione v1: utenti da users.yaml con password bcrypt, ruolo admin/user."""

from __future__ import annotations

import uuid
from pathlib import Path

import bcrypt
import yaml

from doc_parser.auth.base import AuthProvider
from doc_parser.core.models import User

_STATE_USER = "auth_user"
_STATE_SESSION_ID = "auth_session_id"


class PasswordAuthProvider(AuthProvider):
    def __init__(self, users_file: Path) -> None:
        self._users_file = Path(users_file)

    def _load_users(self) -> dict[str, dict]:
        if not self._users_file.is_file():
            raise FileNotFoundError(
                f"File utenti non trovato: {self._users_file}. "
                "Copia users.example.yaml in users.yaml e definisci gli utenti."
            )
        data = yaml.safe_load(self._users_file.read_text(encoding="utf-8")) or {}
        return {str(entry["upn"]).strip().lower(): entry for entry in data.get("users", [])}

    def verify_credentials(self, upn: str, password: str) -> User | None:
        """Verifica pura delle credenziali, indipendente da Streamlit."""
        entry = self._load_users().get(upn.strip().lower())
        if entry is None:
            return None
        hashed = str(entry.get("password_hash", "")).encode("utf-8")
        if not hashed or not bcrypt.checkpw(password.encode("utf-8"), hashed):
            return None
        return User(
            upn=entry["upn"],
            display_name=str(entry.get("display_name", entry["upn"])),
            is_admin=str(entry.get("role", "user")).lower() == "admin",
        )

    # --- Integrazione Streamlit ---

    def get_current_user(self) -> User | None:
        import streamlit as st

        raw = st.session_state.get(_STATE_USER)
        return User(**raw) if raw else None

    def get_session_id(self) -> str:
        import streamlit as st

        return st.session_state.get(_STATE_SESSION_ID, "")

    def login_form(self) -> None:
        import streamlit as st

        st.title("doc-parser — Accesso")
        with st.form("login"):
            upn = st.text_input("Utente (UPN)", placeholder="utente@demo.local")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Accedi", type="primary")
        if submitted:
            user = self.verify_credentials(upn, password)
            if user is None:
                st.error("Credenziali non valide")
                return
            st.session_state[_STATE_USER] = user.model_dump()
            st.session_state[_STATE_SESSION_ID] = str(uuid.uuid4())
            st.rerun()

    def logout(self) -> None:
        import streamlit as st

        st.session_state.pop(_STATE_USER, None)
        st.session_state.pop(_STATE_SESSION_ID, None)
