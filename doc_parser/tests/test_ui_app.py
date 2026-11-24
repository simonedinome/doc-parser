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


def _content_type_box(at: AppTest):
    return next(sb for sb in at.selectbox if sb.label == "Tipo di contenuto")


def test_elabora_pptx_checkbox_only_for_video_and_off_by_default(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "utente@demo.local", "demo123!")
    assert not any("Presentazione tutorial" in cb.label for cb in at.checkbox)

    _content_type_box(at).set_value("Video")
    at = at.run()
    assert not at.exception
    pptx_boxes = [cb for cb in at.checkbox if "Presentazione tutorial" in cb.label]
    assert len(pptx_boxes) == 1 and pptx_boxes[0].value is False

    _content_type_box(at).set_value("Documento")
    at = at.run()
    assert not any("Presentazione tutorial" in cb.label for cb in at.checkbox)


def test_elabora_video_urls_get_kind_and_date_inputs(app_env) -> None:
    at = AppTest.from_file(_APP_PATH, default_timeout=30).run()
    at = _login(at, "utente@demo.local", "demo123!")
    _content_type_box(at).set_value("Video")
    at = at.run()
    at.text_area[0].set_value("https://esempio.com/webinar.mp4\nhttps://esempio.com/pillola.mp4\nhttps://esempio.com/slide.pdf")
    at = at.run()
    assert not at.exception
    kind_boxes = [sb for sb in at.selectbox if sb.label == "Tipo"]
    assert len(kind_boxes) == 2  # nessun selettore per il PDF di slide
    assert all(sb.value == "Webinar" for sb in kind_boxes)
    assert len([d for d in at.date_input if d.label == "Data di registrazione"]) == 2


def test_video_manifest_descriptors_maps_labels_and_dates() -> None:
    from datetime import date

    from doc_parser.ui.views.elabora import video_manifest_descriptors

    descriptors = video_manifest_descriptors(
        ["w.mp4", "p.mp4", "deck.pdf", "w2.mp4"],
        {0: ("Webinar", date(2026, 6, 3)), 1: ("Pillola", None), 3: ("Webinar", None)},
    )
    assert [(d["input_id"], d["role"], d.get("kind"), d.get("recorded_at")) for d in descriptors] == [
        ("v1", "video", "webinar", "2026-06-03"),
        ("v2", "video", "pillola", None),
        ("pdf", "slides", None, None),
        ("v3", "video", "webinar", None),
    ]
