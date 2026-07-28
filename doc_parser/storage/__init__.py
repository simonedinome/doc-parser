"""Factory del repository, selezionato da STORAGE_BACKEND (sqlite|azure)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doc_parser.storage.base import Repository

if TYPE_CHECKING:
    from doc_parser.settings import Settings


def get_repository(settings: Settings) -> Repository:
    if settings.storage_backend == "sqlite":
        from doc_parser.storage.sqlite_repo import SqliteRepository

        return SqliteRepository(data_dir=settings.data_dir)
    raise ValueError(f"STORAGE_BACKEND non valido: {settings.storage_backend!r}")
