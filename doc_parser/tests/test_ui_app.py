"""Smoke test della web app con streamlit AppTest: login, navigazione, ruoli."""

from pathlib import Path

import bcrypt
import pytest
import yaml
from streamlit.testing.v1 import AppTest

_APP_PATH = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")


@pytest.fixture
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    users_file = tmp_path / "users.yaml"
    users_file.write_text(yaml.safe_dump(users), encoding="utf-8")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("USERS_FILE", str(users_file))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WORKER_POLL_SECONDS", "0.2")

    from doc_parser.settings import get_settings
    from doc_parser.ui.context import get_app_context

    get_settings.cache_clear()
    get_app_context.clear()
    yield
    get_settings.cache_clear()
    get_app_context.clear()


def _login(at: AppTest, upn: str, password: str) -> AppTest:
    at.text_input[0].set_value(upn)
    at.text_input[1].set_value(password)
    at.button[0].set_value(True)
    return at.run()


def test_unauthenticated_sees_login_form(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    assert not at.exception
    assert any("Accesso" in t.value for t in at.title)
    assert len(at.text_input) == 2


def test_login_wrong_credentials_shows_error(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "utente@demo.local", "password-sbagliata")
    assert not at.exception
    assert any("Credenziali non valide" in e.value for e in at.error)
    assert "auth_user" not in at.session_state


def test_login_sets_user_and_session_guid(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "utente@demo.local", "demo123!")
    assert not at.exception
    assert at.session_state["auth_user"]["upn"] == "utente@demo.local"
    assert len(at.session_state["auth_session_id"]) == 36


def test_admin_flag_set_for_admin_login(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "admin@demo.local", "admin123!")
    assert not at.exception
    assert at.session_state["auth_user"]["is_admin"] is True


def test_elabora_page_renders_all_options(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "utente@demo.local", "demo123!")
    assert not at.exception
    labels = [sb.label for sb in at.selectbox]
    assert "Tipo di contenuto" in labels
    assert "Modello" in labels
    assert "Lingua output" in labels
    assert "Modalità HTML" not in labels
    assert "Modalità output" not in labels
    assert any(r.label == "Modalità di elaborazione" for r in at.radio)
    checkbox_labels = [cb.label for cb in at.checkbox]
    assert any("Procedura" in label for label in checkbox_labels)
    assert any("Glossario" in label for label in checkbox_labels)
    assert any("RAG" in label for label in checkbox_labels)


def test_elabora_page_content_type_has_documento_manuale_video(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "utente@demo.local", "demo123!")
    content_type_box = next(sb for sb in at.selectbox if sb.label == "Tipo di contenuto")
    assert content_type_box.options == ["Documento", "Manuale", "Video"]
