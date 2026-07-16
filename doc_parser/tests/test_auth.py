from pathlib import Path

import bcrypt
import pytest
import yaml

from doc_parser.auth import get_auth_provider
from doc_parser.auth.password_auth import PasswordAuthProvider
from doc_parser.settings import Settings


def _users_file(tmp_path: Path) -> Path:
    users = {
        "users": [
            {
                "upn": "admin@demo.local",
                "display_name": "Admin Demo",
                "role": "admin",
                "password_hash": bcrypt.hashpw(b"admin123!", bcrypt.gensalt(rounds=4)).decode(),
            },
            {
                "upn": "utente@demo.local",
                "display_name": "Utente Demo",
                "role": "user",
                "password_hash": bcrypt.hashpw(b"demo123!", bcrypt.gensalt(rounds=4)).decode(),
            },
        ]
    }
    path = tmp_path / "users.yaml"
    path.write_text(yaml.safe_dump(users), encoding="utf-8")
    return path


def test_factory_returns_password_provider(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, users_file=_users_file(tmp_path))
    assert isinstance(get_auth_provider(settings), PasswordAuthProvider)


def test_verify_valid_admin(tmp_path: Path) -> None:
    provider = PasswordAuthProvider(users_file=_users_file(tmp_path))
    user = provider.verify_credentials("admin@demo.local", "admin123!")
    assert user is not None
    assert user.is_admin is True
    assert user.display_name == "Admin Demo"


def test_verify_valid_user_not_admin(tmp_path: Path) -> None:
    provider = PasswordAuthProvider(users_file=_users_file(tmp_path))
    user = provider.verify_credentials("utente@demo.local", "demo123!")
    assert user is not None
    assert user.is_admin is False


def test_verify_upn_is_case_insensitive(tmp_path: Path) -> None:
    provider = PasswordAuthProvider(users_file=_users_file(tmp_path))
    assert provider.verify_credentials("  ADMIN@demo.local ", "admin123!") is not None


def test_verify_wrong_password(tmp_path: Path) -> None:
    provider = PasswordAuthProvider(users_file=_users_file(tmp_path))
    assert provider.verify_credentials("admin@demo.local", "sbagliata") is None


def test_verify_unknown_user(tmp_path: Path) -> None:
    provider = PasswordAuthProvider(users_file=_users_file(tmp_path))
    assert provider.verify_credentials("nessuno@demo.local", "admin123!") is None


def test_missing_users_file_raises_clear_error(tmp_path: Path) -> None:
    provider = PasswordAuthProvider(users_file=tmp_path / "assente.yaml")
    with pytest.raises(FileNotFoundError, match="users.example.yaml"):
        provider.verify_credentials("x@y", "z")
