"""Factory dei provider di autenticazione, selezionati da AUTH_PROVIDER."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doc_parser.auth.base import AuthProvider

if TYPE_CHECKING:
    from doc_parser.settings import Settings


def get_auth_provider(settings: Settings) -> AuthProvider:
    if settings.auth_provider == "password":
        from doc_parser.auth.password_auth import PasswordAuthProvider

        return PasswordAuthProvider(users_file=settings.users_file)
    raise ValueError(f"AUTH_PROVIDER non valido: {settings.auth_provider!r}")
