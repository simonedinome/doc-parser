"""Consolidamento di più video (e dell'eventuale PDF di slide) in un'unica
documentazione senza ripetizioni.

Il modello indica solo quali step sorgente ha unito (``merged_from``) e quali
slide ha usato (``slides``); fonti, timestamp, ID e log delle discordanze li
ricava il codice, così non possono essere inventati. Il risultato arricchito
diventa il ``raw.json`` della run.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field

from doc_parser.pipeline import parser
from doc_parser.pipeline.consolidation_prompts import (
    CONSOLIDATION_INVALID_JSON_TEMPLATE,
    CONSOLIDATION_RETRY_TEMPLATE,
    CONSOLIDATION_SYSTEM_PROMPT,
    CONSOLIDATION_USER_PROMPT_TEMPLATE,
)
from doc_parser.pipeline.inputs import SLIDES_INPUT_ID, InputFile
from doc_parser.pipeline.language import apply_language_directive
from doc_parser.pipeline.slides_addendum import DISCREPANCY_MARKER, slides_attachments
from doc_parser.providers.base import Attachment, BaseProvider

REQUIRED_KEYS = ("title", "summary", "prerequisites", "procedures", "glossary", "notes")
SLIDES_KIND = "slide"

_KIND_RANK = {"webinar": 3, SLIDES_KIND: 2, "pillola": 1}
_VIDEO_REF = re.compile(r"^(v\d+)/(proc_\d+)/(\d+)$")
_PDF_REF = re.compile(r"^pdf/(\d+)$")
_MAX_LISTED_ISSUES = 40
_STEP_TEXT_FIELDS = ("title", "description", "notes", "embedding_keywords")

TRUNCATION_HINT = (
    "Se il JSON non è valido la risposta è probabilmente troncata: la serie è troppo lunga per "
    "l'output del modello scelto. Scegli un modello con un output più lungo o dividi la serie in più run."
)


class ConsolidationValidationError(ValueError):
    """Il consolidamento non ha prodotto un risultato valido entro i tentativi.

    Porta i token consumati dai tentativi, così la run fallita li registra.
    """

    def __init__(self, message: str, tokens_in: int = 0, tokens_out: int = 0) -> None:
        super().__init__(message)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


@dataclass
class SourceStep:
    ref: str
    input_id: str
    procedure_title: str
    step: dict


@dataclass
class ConsolidationIndex:
    videos: list[InputFile]
    slides: InputFile | None
    slide_count: int
    step1: dict[str, dict]
    steps: dict[str, SourceStep]
    priority: list[str]

    def rank(self, input_id: str) -> int:
        return len(self.priority) - self.priority.index(input_id)

    def input(self, input_id: str) -> InputFile | None:
        if input_id == SLIDES_INPUT_ID:
            return self.slides
        return next((v for v in self.videos if v.input_id == input_id), None)


@dataclass
class Validation:
    output: dict | None
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    uncovered_slides: list[int] = field(default_factory=list)


# --- Preparazione delle fonti ---


def normalize_step1(data: dict) -> dict:
    """Rinumera procedure (proc_001…) e step (1…n) di un JSON di step 1, così
    i riferimenti ``v1/proc_002/3`` sono univoci anche se il modello ha
    duplicato ID o saltato numeri."""
    normalized = copy.deepcopy(data)
    for proc_index, proc in enumerate(normalized.get("procedures", []), 1):
        proc["id"] = f"proc_{proc_index:03d}"
        for step_index, step in enumerate(proc.get("steps", []), 1):
            step["number"] = step_index
    return normalized


def priority_order(videos: list[InputFile], slides: InputFile | None) -> list[str]:
    """input_id dalla fonte più autorevole alla meno autorevole.

    Una sola chiave d'ordinamento, così la priorità è sempre transitiva: tipo
    (webinar > slide > pillola), poi le fonti con data prima di quelle senza,
    poi la data più recente, poi l'ultima in ordine di caricamento.
    """
    entries = [
        (_KIND_RANK.get(v.kind or "webinar", _KIND_RANK["webinar"]), v.recorded_at is not None, v.recorded_at or "", i, v.input_id)
        for i, v in enumerate(videos)
    ]
    if slides is not None:
        entries.append((_KIND_RANK[SLIDES_KIND], False, "", len(videos), slides.input_id))
    return [entry[-1] for entry in sorted(entries, reverse=True)]


def build_index(
    videos: list[tuple[InputFile, dict]],
    slides: InputFile | None,
    slide_count: int,
) -> ConsolidationIndex:
    """*videos* è ``[(video, json_step1_normalizzato)]`` in ordine di caricamento."""
    steps: dict[str, SourceStep] = {}
    for video, data in videos:
        for proc in data.get("procedures", []):
            for step in proc.get("steps", []):
                ref = f"{video.input_id}/{proc['id']}/{step['number']}"
                steps[ref] = SourceStep(ref, video.input_id, proc.get("title", ""), step)
    return ConsolidationIndex(
        videos=[v for v, _ in videos],
        slides=slides,
        slide_count=slide_count if slides is not None else 0,
        step1={v.input_id: data for v, data in videos},
        steps=steps,
        priority=priority_order([v for v, _ in videos], slides),
    )


def _describe_source(index: ConsolidationIndex, input_id: str) -> str:
    if input_id == SLIDES_INPUT_ID:
        return f"{input_id} (slide)"
    video = index.input(input_id)
    date = video.recorded_at or "data non indicata"
    return f"{input_id} ({video.kind}, {date})"


def build_request(index: ConsolidationIndex, language: str) -> tuple[str, str, list[Attachment]]:
    """Prompt di sistema, prompt utente e allegati della chiamata di consolidamento."""
    slides_header = ""
    attachments: list[Attachment] = []
    if index.slides is not None:
        slides_header = (
            f"=== FONTE pdf · slide · {index.slides.filename} · {index.slide_count} pagine ===\n"
            f"Il PDF delle slide è allegato. Numero di slide = numero di pagina, da 1 a {index.slide_count}.\n\n"
        )
        attachments = slides_attachments(index.slides.filename, index.slides.data)

    blocks: list[str] = []
    for video in index.videos:
        data = copy.deepcopy(index.step1[video.input_id])
        for proc in data.get("procedures", []):
            for step in proc.get("steps", []):
                step["ref"] = f"{video.input_id}/{proc['id']}/{step['number']}"
        recorded = f"registrato il {video.recorded_at}" if video.recorded_at else "data di registrazione non indicata"
        header = f"=== FONTE {video.input_id} · {video.kind} · {recorded} · {video.filename} ==="
        blocks.append(f"{header}\n{json.dumps(data, ensure_ascii=False)}")

    priority = " > ".join(_describe_source(index, input_id) for input_id in index.priority)
    user_prompt = CONSOLIDATION_USER_PROMPT_TEMPLATE.format(
        slides_header=slides_header, priority=priority, sources="\n\n".join(blocks)
    )
    system_prompt = apply_language_directive(CONSOLIDATION_SYSTEM_PROMPT, language)
    return system_prompt, user_prompt, attachments


# --- Validazione ---


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _ref_input_id(ref: str) -> str | None:
    if _PDF_REF.match(ref):
        return SLIDES_INPUT_ID
    match = _VIDEO_REF.match(ref)
    return match.group(1) if match else None


def _is_known_ref(index: ConsolidationIndex, ref: str) -> bool:
    pdf = _PDF_REF.match(ref)
    if pdf:
        return 1 <= int(pdf.group(1)) <= index.slide_count
    return ref in index.steps


def _clean_refs(index: ConsolidationIndex, raw_refs, where: str, blocking: list[str]) -> list[str]:
    refs: list[str] = []
    for raw in _as_list(raw_refs):
        ref = str(raw).strip()
        if not _is_known_ref(index, ref):
            blocking.append(f"{where}: riferimento inesistente {ref!r}")
            continue
        if ref not in refs:
            refs.append(ref)
    return refs


def _clean_slides(index: ConsolidationIndex, raw_slides, refs: list[str], where: str, warnings: list[str]) -> list[int]:
    slides = parser.normalize_slide_numbers(_as_list(raw_slides))
    slides += [int(_PDF_REF.match(r).group(1)) for r in refs if _PDF_REF.match(r)]
    valid = []
    for number in slides:
        if number > index.slide_count:
            limit = f"il PDF ha {index.slide_count} pagine" if index.slides is not None else "la run non ha un PDF di slide"
            warnings.append(f"{where}: slide {number} fuori intervallo ({limit}), rimossa")
        elif number not in valid:
            valid.append(number)
    return valid


def _copy_from_source(index: ConsolidationIndex, item: dict, refs: list[str]) -> None:
    """Forma breve: uno step con un solo riferimento a uno step video riprende
    dalla fonte i campi di testo che non ha."""
    if len(refs) != 1 or refs[0] not in index.steps:
        return
    source = index.steps[refs[0]].step
    for key in _STEP_TEXT_FIELDS:
        if not item.get(key):
            item[key] = copy.deepcopy(source.get(key, [] if key == "embedding_keywords" else ""))


def _source_slides_of(index: ConsolidationIndex, refs: list[str]) -> list[int]:
    return [n for r in refs if r in index.steps for n in index.steps[r].step.get("source_slides", []) or []]


def validate(output: dict, index: ConsolidationIndex) -> Validation:
    """Applica le regole di validazione del piano e risolve la forma breve.

    Ritorna l'output risolto (copia dei testi, slide ripulite) con gli errori
    bloccanti e gli avvisi non bloccanti, entrambi da usare come feedback.
    """
    if not isinstance(output, dict):
        return Validation(None, ["la risposta non è un oggetto JSON"])
    missing = [k for k in REQUIRED_KEYS if k not in output]
    if missing:
        return Validation(None, [f"mancano le chiavi obbligatorie: {', '.join(missing)}. {TRUNCATION_HINT}"])

    resolved = copy.deepcopy(output)
    blocking: list[str] = []
    warnings: list[str] = []

    for key in ("prerequisites", "glossary", "notes"):
        if not isinstance(resolved[key], list):
            blocking.append(f"'{key}' deve essere una lista")
    if not isinstance(resolved["procedures"], list):
        return Validation(None, ["'procedures' deve essere una lista"])
    concepts = resolved.get("concepts") or []
    if not isinstance(concepts, list):
        blocking.append("'concepts' deve essere una lista")
        concepts = []
    if not all(isinstance(item, dict) for item in concepts + resolved["procedures"]):
        return Validation(None, ["ogni concetto e ogni procedura deve essere un oggetto JSON"])
    if any(not isinstance(step, dict) for proc in resolved["procedures"] for step in _as_list(proc.get("steps"))):
        return Validation(None, ["ogni step deve essere un oggetto JSON"])
    if isinstance(resolved["glossary"], list) and not all(
        isinstance(g, dict) and g.get("term") and "definition" in g for g in resolved["glossary"]
    ):
        blocking.append("ogni voce del glossario deve avere 'term' e 'definition'")
    resolved["concepts"] = concepts

    covered: set[str] = set()
    used_slides: set[int] = set()

    for con_index, con in enumerate(concepts, 1):
        where = f"concetto {con_index} ({con.get('title', '')!r})"
        refs = _clean_refs(index, con.get("merged_from"), where, blocking)
        con["merged_from"] = refs
        con["slides"] = _clean_slides(index, con.get("slides"), refs, where, warnings)
        covered.update(r for r in refs if r in index.steps)
        used_slides.update(con["slides"], _source_slides_of(index, refs))
        if not refs and not con["slides"]:
            blocking.append(f"{where}: né merged_from né slides, contenuto non tracciabile")
        if not con.get("title") or not con.get("content"):
            blocking.append(f"{where}: mancano title o content")

    for proc_index, proc in enumerate(resolved["procedures"], 1):
        where_proc = f"procedura {proc_index} ({proc.get('title', '')!r})"
        if not proc.get("title"):
            blocking.append(f"{where_proc}: manca il title")
        steps = proc.get("steps")
        if not isinstance(steps, list) or not steps:
            blocking.append(f"{where_proc}: nessuno step")
            proc["steps"] = []
            continue
        for step_index, step in enumerate(steps, 1):
            where = f"{where_proc}, step {step_index}"
            refs = _clean_refs(index, step.get("merged_from"), where, blocking)
            step["merged_from"] = refs
            _copy_from_source(index, step, refs)
            step["slides"] = _clean_slides(index, step.get("slides"), refs, where, warnings)
            covered.update(r for r in refs if r in index.steps)
            used_slides.update(step["slides"], _source_slides_of(index, refs))
            if not refs and not step["slides"]:
                blocking.append(f"{where}: né merged_from né slides, step non tracciabile")
            if not step.get("title") or not step.get("description"):
                blocking.append(f"{where}: mancano title o description (obbligatori se lo step non riprende un solo step video)")

    dropped = []
    for item in _as_list(resolved.get("dropped")):
        item = item if isinstance(item, dict) else {"ref": item}
        refs = _clean_refs(index, item.get("ref"), "dropped", blocking)
        for ref in refs:
            dropped.append({"ref": ref, "reason": item.get("reason", "")})
            covered.add(ref)
            if _PDF_REF.match(ref):
                used_slides.add(int(_PDF_REF.match(ref).group(1)))
    resolved["dropped"] = dropped

    conflicts = []
    for c_index, item in enumerate(_as_list(resolved.get("conflicts")), 1):
        if not isinstance(item, dict):
            continue
        where = f"conflitto {c_index} ({item.get('topic', '')!r})"
        chosen = _clean_refs(index, item.get("chosen"), where, blocking)
        discarded = _clean_refs(index, item.get("discarded"), where, blocking)
        if not chosen:
            continue
        chosen_ref = chosen[0]
        chosen_rank = index.rank(_ref_input_id(chosen_ref))
        for ref in discarded:
            if index.rank(_ref_input_id(ref)) > chosen_rank:
                warnings.append(
                    f"{where}: tenuta {_describe_source(index, _ref_input_id(chosen_ref))} ma scartata "
                    f"{_describe_source(index, _ref_input_id(ref))}, che ha priorità più alta: applica l'ordine di priorità"
                )
        used_slides.update(int(_PDF_REF.match(r).group(1)) for r in [chosen_ref, *discarded] if _PDF_REF.match(r))
        conflicts.append({**item, "chosen": chosen_ref, "discarded": discarded})
    resolved["conflicts"] = conflicts

    skipped = []
    for item in _as_list(resolved.get("skipped_slides")):
        item = item if isinstance(item, dict) else {"slide": item}
        numbers = parser.normalize_slide_numbers(item.get("slide"))
        if not numbers or numbers[0] > index.slide_count:
            warnings.append(f"skipped_slides: slide {item.get('slide')!r} non valida, ignorata")
            continue
        skipped.append({"slide": numbers[0], "reason": item.get("reason", "")})
        used_slides.add(numbers[0])
    resolved["skipped_slides"] = skipped

    uncovered_refs = [ref for ref in index.steps if ref not in covered]
    if uncovered_refs:
        listed = ", ".join(uncovered_refs[:_MAX_LISTED_ISSUES])
        more = f" e altri {len(uncovered_refs) - _MAX_LISTED_ISSUES}" if len(uncovered_refs) > _MAX_LISTED_ISSUES else ""
        blocking.append(f"step sorgente non coperti (né in merged_from né in dropped): {listed}{more}")

    uncovered_slides = [n for n in range(1, index.slide_count + 1) if n not in used_slides]
    if uncovered_slides:
        warnings.append(
            "slide non incluse in nessuno step o concetto e non motivate in skipped_slides: "
            + ", ".join(str(n) for n in uncovered_slides)
        )

    for where, text in _texts(resolved):
        if DISCREPANCY_MARKER in text:
            warnings.append(f"{where}: il testo contiene ancora {DISCREPANCY_MARKER!r}, risolvi la discordanza")

    return Validation(resolved, blocking, warnings, uncovered_slides)


def _texts(data: dict):
    for i, con in enumerate(data.get("concepts", []), 1):
        yield f"concetto {i}", f"{con.get('title', '')} {con.get('content', '')}"
    for p, proc in enumerate(data.get("procedures", []), 1):
        for s, step in enumerate(proc.get("steps", []), 1):
            yield f"procedura {p}, step {s}", f"{step.get('title', '')} {step.get('description', '')} {step.get('notes', '')}"
    for n, note in enumerate(data.get("notes", []) or [], 1):
        yield f"nota generale {n}", str(note)


# --- Arricchimento ---


def _dedupe(items: list) -> list:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def resolve_ref(index: ConsolidationIndex, ref: str) -> dict:
    """Descrittore leggibile di un riferimento, per log e note: file, tipo,
    data e timestamp (video) o numero di slide (PDF)."""
    pdf = _PDF_REF.match(ref)
    if pdf:
        return {
            "ref": ref, "input_id": SLIDES_INPUT_ID, "filename": index.slides.filename,
            "kind": SLIDES_KIND, "recorded_at": None, "timestamps": [], "slide": int(pdf.group(1)), "step_title": "",
        }
    source = index.steps[ref]
    video = index.input(source.input_id)
    return {
        "ref": ref, "input_id": video.input_id, "filename": video.filename, "kind": video.kind,
        "recorded_at": video.recorded_at, "timestamps": list(source.step.get("source_timestamps", []) or []),
        "slide": None, "step_title": source.step.get("title", ""),
    }


def _provenance(index: ConsolidationIndex, refs: list[str], slides: list[int]) -> dict:
    timestamps: dict[str, list[str]] = {}
    for ref in refs:
        if ref in index.steps:
            source = index.steps[ref]
            timestamps.setdefault(source.input_id, []).extend(source.step.get("source_timestamps", []) or [])
    sources = []
    for input_id in index.priority:
        if input_id in timestamps:
            video = index.input(input_id)
            sources.append(
                {
                    "input_id": input_id, "filename": video.filename, "kind": video.kind,
                    "recorded_at": video.recorded_at, "timestamps": _dedupe(timestamps[input_id]),
                }
            )
    source_slides = [n for n in _dedupe(slides + _source_slides_of(index, refs)) if 1 <= n <= index.slide_count]
    return {"merged_from": refs, "sources": sources, "source_slides": source_slides}


def enrich(validation: Validation, index: ConsolidationIndex, extra_warnings: list[str] | None = None) -> dict:
    """JSON consolidato arricchito: ID deterministici, provenienza calcolata
    dai riferimenti, descrittori degli input e log del consolidamento."""
    output = validation.output
    concepts = [
        {
            "id": f"con_{i:03d}",
            "title": con.get("title", ""),
            "content": con.get("content", ""),
            "embedding_keywords": _as_list(con.get("embedding_keywords")),
            **_provenance(index, con["merged_from"], con["slides"]),
        }
        for i, con in enumerate(output.get("concepts", []), 1)
    ]
    procedures = [
        {
            "id": f"proc_{p:03d}",
            "title": proc.get("title", ""),
            "steps": [
                {
                    "number": s,
                    "title": step.get("title", ""),
                    "description": step.get("description", ""),
                    "notes": step.get("notes", "") or "",
                    "embedding_keywords": _as_list(step.get("embedding_keywords")),
                    **_provenance(index, step["merged_from"], step["slides"]),
                }
                for s, step in enumerate(proc.get("steps", []), 1)
            ],
        }
        for p, proc in enumerate(output["procedures"], 1)
    ]

    source_inputs = [
        {"input_id": v.input_id, "filename": v.filename, "role": "video", "kind": v.kind, "recorded_at": v.recorded_at}
        for v in index.videos
    ]
    if index.slides is not None:
        source_inputs.append(
            {"input_id": SLIDES_INPUT_ID, "filename": index.slides.filename, "role": "slides", "pages": index.slide_count}
        )

    consolidation_log = {
        "priority_order": list(index.priority),
        "conflicts": [
            {
                "topic": c.get("topic", ""),
                "reason": c.get("reason", ""),
                "chosen": resolve_ref(index, c["chosen"]),
                "discarded": [resolve_ref(index, r) for r in c["discarded"]],
            }
            for c in output.get("conflicts", [])
        ],
        "dropped": [{**resolve_ref(index, d["ref"]), "reason": d["reason"]} for d in output.get("dropped", [])],
        "skipped_slides": output.get("skipped_slides", []),
        "uncovered_slides": validation.uncovered_slides,
        "warnings": list(validation.warnings) + list(extra_warnings or []),
    }

    return {
        "title": output.get("title", ""),
        "summary": output.get("summary", ""),
        "prerequisites": output.get("prerequisites", []),
        "concepts": concepts,
        "procedures": procedures,
        "glossary": output.get("glossary", []),
        "notes": output.get("notes", []),
        "source_inputs": source_inputs,
        "consolidation_log": consolidation_log,
    }


# --- Chiamata con retry ---


def _issues_text(issues: list[str]) -> str:
    listed = issues[:_MAX_LISTED_ISSUES]
    lines = [f"- {issue}" for issue in listed]
    if len(issues) > len(listed):
        lines.append(f"- … e altri {len(issues) - len(listed)} problemi dello stesso tipo")
    return "\n".join(lines)


def consolidate(
    provider: BaseProvider,
    index: ConsolidationIndex,
    language: str,
    max_attempts: int,
) -> tuple[dict, int, int, int]:
    """Chiama il modello, valida e ritenta con feedback.

    Ogni retry rimanda la richiesta completa (PDF compreso), la risposta
    precedente e le correzioni: il provider è single-turn. Gli avvisi non
    bloccanti chiedono una correzione finché restano tentativi; poi si
    accetta l'ultimo risultato senza errori bloccanti e gli avvisi vanno nel
    log. Ritorna (json_arricchito, tokens_in, tokens_out, tentativi_usati).
    """
    system_prompt, base_prompt, attachments = build_request(index, language)
    user_prompt = base_prompt
    tokens_in = tokens_out = 0
    best: tuple[Validation, int] | None = None
    last_issues: list[str] = []

    for attempt in range(1, max_attempts + 1):
        raw, t_in, t_out = provider.generate(system_prompt, user_prompt, attachments)
        tokens_in += t_in
        tokens_out += t_out
        try:
            output = parser.load_json_response(raw)
        except ValueError as exc:
            last_issues = [f"JSON non valido: {exc}. {TRUNCATION_HINT}"]
            user_prompt = CONSOLIDATION_INVALID_JSON_TEMPLATE.format(request=base_prompt, error=exc)
            continue

        validation = validate(output, index)
        if not validation.blocking:
            best = (validation, attempt)
            if not validation.warnings:
                break
        last_issues = validation.blocking + validation.warnings
        if attempt < max_attempts:
            user_prompt = CONSOLIDATION_RETRY_TEMPLATE.format(
                request=base_prompt, previous=raw, issues=_issues_text(last_issues)
            )

    if best is None:
        raise ConsolidationValidationError(
            f"Il consolidamento non ha prodotto un risultato valido dopo {max_attempts} tentativi: "
            f"{'; '.join(last_issues[:10])}. I JSON di step 1 restano salvati (step1_v*.json).",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    validation, attempt = best
    extra = [] if attempt == 1 else [f"Consolidamento riuscito al tentativo {attempt} di {max_attempts}"]
    return enrich(validation, index, extra), tokens_in, tokens_out, attempt
