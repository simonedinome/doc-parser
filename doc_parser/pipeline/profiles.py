"""Selezione dei prompt system/user in base al profilo di contenuto (content_type)."""

from __future__ import annotations

from doc_parser.pipeline import doc_prompts, manuale_prompts, prompts, video_prompts

CONTENT_TYPES = ("documento", "manuale", "video", "screencast")


def resolve_profile_prompts(content_type: str) -> tuple[str, str]:
    """Ritorna (system_prompt, user_prompt) per il profilo indicato."""
    if content_type == "screencast":
        return prompts.SYSTEM_PROMPT, prompts.USER_PROMPT
    if content_type == "video":
        return video_prompts.VIDEO_SYSTEM_PROMPT, video_prompts.VIDEO_USER_PROMPT
    if content_type == "manuale":
        return manuale_prompts.MANUALE_SYSTEM_PROMPT, manuale_prompts.MANUALE_USER_PROMPT
    if content_type == "documento":
        return doc_prompts.DOC_SYSTEM_PROMPT, doc_prompts.DOC_USER_PROMPT
    raise ValueError(f"Tipo di contenuto non valido: {content_type!r}")
