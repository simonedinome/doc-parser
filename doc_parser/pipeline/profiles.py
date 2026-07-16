"""Selezione dei prompt system/user in base al profilo di contenuto (content_type)."""

from __future__ import annotations

from doc_parser.pipeline import doc_prompts, hybrid_prompts, prompts, webinar_prompts

CONTENT_TYPES = ("screencast", "webinar", "hybrid", "doc")


def resolve_profile_prompts(content_type: str) -> tuple[str, str]:
    """Ritorna (system_prompt, user_prompt) per il profilo indicato."""
    if content_type == "screencast":
        return prompts.SYSTEM_PROMPT, prompts.USER_PROMPT
    if content_type == "webinar":
        return webinar_prompts.WEBINAR_SYSTEM_PROMPT, webinar_prompts.WEBINAR_USER_PROMPT
    if content_type == "hybrid":
        return hybrid_prompts.HYBRID_SYSTEM_PROMPT, hybrid_prompts.HYBRID_USER_PROMPT
    if content_type == "doc":
        return doc_prompts.DOC_SYSTEM_PROMPT, doc_prompts.DOC_USER_PROMPT
    raise ValueError(f"Tipo di contenuto non valido: {content_type!r}")
