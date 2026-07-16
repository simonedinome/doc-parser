"""Provider Azure AI Foundry (Azure OpenAI, Responses API) — dormiente in v1.

Non è esposto nel menu utente né raggiungibile da get_provider_for_model:
conservato per l'attivazione v2 (Azure), stessa interfaccia storica
parse_pdf()/ParseResult del vecchio pdf_parser (non la BaseProvider.generate()
generica usata dal resto della pipeline).

Prova l'input PDF diretto sul deployment; se non supportato ripiega su
rasterizzazione PyMuPDF (150 DPI) con batching di pagine per richiesta,
mantenendo la stessa semantica a chunk della modalità KB densa.
"""

from __future__ import annotations

import base64
import time
from abc import ABC, abstractmethod

from doc_parser.core import assembler, kb_densa_prompts as prompts
from doc_parser.core.models import Chunk, ParseResult, utcnow
from doc_parser.providers.base import PermanentProviderError, TransientProviderError


class LegacyPdfProvider(ABC):
    """Interfaccia storica a singolo metodo, usata solo da FoundryProvider dormiente."""

    name: str

    @abstractmethod
    def parse_pdf(self, pdf_bytes: bytes, filename: str) -> ParseResult: ...


class FoundryProvider(LegacyPdfProvider):
    name = "foundry"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        pages_per_batch: int = 10,
        raster_dpi: int = 150,
    ) -> None:
        if not endpoint or not api_key or not deployment:
            raise ValueError(
                "FOUNDRY_ENDPOINT, FOUNDRY_API_KEY e FOUNDRY_DEPLOYMENT sono obbligatori "
                "per attivare FoundryProvider"
            )
        from openai import OpenAI

        self._client = OpenAI(
            base_url=endpoint.rstrip("/") + "/openai/v1/",
            api_key=api_key,
        )
        self._deployment = deployment
        self._pages_per_batch = max(1, pages_per_batch)
        self._raster_dpi = raster_dpi
        self._direct_pdf_supported: bool | None = None

    def parse_pdf(self, pdf_bytes: bytes, filename: str) -> ParseResult:
        if self._direct_pdf_supported is not False:
            try:
                result = self._parse_direct(pdf_bytes, filename)
                self._direct_pdf_supported = True
                return result
            except _DirectPdfUnsupported:
                self._direct_pdf_supported = False
        return self._parse_rasterized(pdf_bytes, filename)

    def _parse_direct(self, pdf_bytes: bytes, filename: str) -> ParseResult:
        content = [
            {
                "type": "input_file",
                "filename": filename,
                "file_data": "data:application/pdf;base64,"
                + base64.b64encode(pdf_bytes).decode("ascii"),
            },
            {"type": "input_text", "text": prompts.USER_PROMPT},
        ]
        started = time.monotonic()
        response = self._create(content, probe_direct_pdf=True)
        llm_duration_ms = int((time.monotonic() - started) * 1000)

        chunks = self._extract(response)
        tokens_in, tokens_out, tokens_total = _usage(response)
        return self._result(chunks, filename, tokens_in, tokens_out, tokens_total, llm_duration_ms)

    def _parse_rasterized(self, pdf_bytes: bytes, filename: str) -> ParseResult:
        pages = self._rasterize(pdf_bytes)
        total_pages = len(pages)

        all_chunks: list[Chunk] = []
        tokens_in = tokens_out = tokens_total = 0
        llm_duration_ms = 0

        for batch_start in range(0, total_pages, self._pages_per_batch):
            batch = pages[batch_start : batch_start + self._pages_per_batch]
            note = prompts.IMAGE_BATCH_NOTE.format(
                filename=filename,
                start=batch_start + 1,
                end=batch_start + len(batch),
                total=total_pages,
                next_index=len(all_chunks) + 1,
            )
            content = [{"type": "input_text", "text": prompts.USER_PROMPT + "\n\n" + note}]
            for png in batch:
                content.append(
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,"
                        + base64.b64encode(png).decode("ascii"),
                    }
                )
            started = time.monotonic()
            response = self._create(content)
            llm_duration_ms += int((time.monotonic() - started) * 1000)

            batch_chunks = self._extract(response)
            for chunk in batch_chunks:
                chunk.index = len(all_chunks) + 1
                all_chunks.append(chunk)
            t_in, t_out, t_total = _usage(response)
            tokens_in += t_in
            tokens_out += t_out
            tokens_total += t_total

        return self._result(
            all_chunks, filename, tokens_in, tokens_out, tokens_total, llm_duration_ms
        )

    def _create(self, content: list[dict], probe_direct_pdf: bool = False):
        import openai

        try:
            return self._client.responses.create(
                model=self._deployment,
                instructions=prompts.SYSTEM_PROMPT,
                input=[{"role": "user", "content": content}],
            )
        except openai.BadRequestError as exc:
            if probe_direct_pdf:
                raise _DirectPdfUnsupported(str(exc)) from exc
            raise PermanentProviderError(str(exc)) from exc
        except (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        ) as exc:
            raise TransientProviderError(str(exc)) from exc
        except openai.OpenAIError as exc:
            raise PermanentProviderError(str(exc)) from exc

    def _extract(self, response) -> list[Chunk]:
        raw = getattr(response, "output_text", "") or ""
        try:
            return assembler.extract_chunks(raw)
        except assembler.ModelResponseError as exc:
            raise PermanentProviderError(str(exc)) from exc

    def _rasterize(self, pdf_bytes: bytes) -> list[bytes]:
        import fitz

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise PermanentProviderError(f"PDF non apribile per la rasterizzazione: {exc}") from exc
        with doc:
            if doc.needs_pass:
                raise PermanentProviderError("PDF cifrato: impossibile rasterizzare")
            return [page.get_pixmap(dpi=self._raster_dpi).tobytes("png") for page in doc]

    def _result(
        self,
        chunks: list[Chunk],
        filename: str,
        tokens_in: int,
        tokens_out: int,
        tokens_total: int,
        llm_duration_ms: int,
    ) -> ParseResult:
        text = assembler.assemble_txt(chunks, filename, utcnow())
        return ParseResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_total=tokens_total or (tokens_in + tokens_out),
            chunk_count=len(chunks),
            uncertainty_count=assembler.count_uncertainty(chunks),
            llm_duration_ms=llm_duration_ms,
            provider=self.name,
            model_version=self._deployment,
            prompt_version=prompts.PROMPT_VERSION,
        )


class _DirectPdfUnsupported(Exception):
    """Il deployment non accetta input_file PDF: usare il fallback raster."""


def _usage(response) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
    tokens_total = int(getattr(usage, "total_tokens", 0) or (tokens_in + tokens_out))
    return tokens_in, tokens_out, tokens_total
