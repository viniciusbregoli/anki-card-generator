"""HTTP API and static frontend: draft a card with the text model, check it, save it to Anki."""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import german, spanish, tagging
from .clients import AnkiManager, Speech, TextModel, UpstreamError
from .dictionary import SOURCE_URL, Dictionary

log = logging.getLogger(__name__)

CSRF_HEADER = "x-card-generator"
LANGUAGE = "de"
LANGUAGES = {"de": german, "es": spanish}
TAGS = ["card-generator"]


@dataclass
class LanguageServices:
    speech: Speech
    dictionary: Dictionary
    deck: str


@dataclass
class Services:
    text: TextModel
    speech: Speech
    manager: AnkiManager
    dictionary: Dictionary
    deck: str
    languages: dict[str, LanguageServices] = field(default_factory=dict)

    def for_language(self, language: str) -> LanguageServices:
        if language in self.languages:
            return self.languages[language]
        if language == LANGUAGE:
            return LanguageServices(self.speech, self.dictionary, self.deck)
        raise HTTPException(503, f"Language '{language}' is not configured.")

    def configured_languages(self) -> list[str]:
        return [code for code in LANGUAGES if code == LANGUAGE or code in self.languages]


# -- request bodies --------------------------------------------------------------


class DraftIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: german.Language = LANGUAGE
    context: str = Field("", max_length=1000)
    kind: german.Kind | None = None
    hint: str = Field("", max_length=200)  # the sense to write the card for, e.g. "to be"
    review: bool = False  # a second, stricter pass over the draft (slower; used by batches)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    language: german.Language = LANGUAGE


class SaveIn(BaseModel):
    draft: german.Draft
    allow_duplicate: bool = False


# -- app ---------------------------------------------------------------------------


def create_app(services: Services | None = None, *, static_dir: Path | None = None,
               build_dictionary: bool | None = None) -> FastAPI:
    app = FastAPI(title="Card Generator")
    app.state.services = services or services_from_env()
    notetype_ids: dict[tuple[str, str], int] = {}
    notetype_lock = threading.Lock()

    sources = {
        "de": os.environ.get("CARD_GENERATOR_DICTIONARY_URL", SOURCE_URL),
        "es": os.environ.get("CARD_GENERATOR_DICTIONARY_URL_ES", spanish.SOURCE_URL),
    }
    for code in app.state.services.configured_languages():
        url = sources[code]
        if build_dictionary or (build_dictionary is None and url):
            app.state.services.for_language(code).dictionary.build_in_background(url)

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Same scheme as anki-manager: browsers can't send a custom header cross-origin
        # without a CORS preflight, which is never approved, so other sites can't
        # spend API credits or add cards.
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
            if request.headers.get(CSRF_HEADER) != "1":
                return JSONResponse({"detail": f"missing {CSRF_HEADER} header"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(UpstreamError)
    async def _upstream(_: Request, exc: UpstreamError):
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=exc.status)

    def svc(request: Request) -> Services:
        return request.app.state.services

    # -- status ------------------------------------------------------------------

    @app.get("/api/status")
    def status(request: Request):
        s = svc(request)
        try:
            manager = s.manager.status()
            anki = {"ok": True, "sync": manager["sync"]["state"], "notes": manager["notes"], "error": None}
        except UpstreamError as exc:
            anki = {"ok": False, "sync": None, "notes": None, "error": str(exc)}
        languages = {}
        for code in s.configured_languages():
            ls = s.for_language(code)
            languages[code] = {
                "deck": ls.deck,
                "speech": {
                    "configured": ls.speech.configured,
                    "model": ls.speech.model,
                    "voice": ls.speech.voice_id,
                },
                "dictionary": {"state": ls.dictionary.state, "error": ls.dictionary.error},
            }
        return {
            "language": LANGUAGE,
            "deck": s.deck,
            "text_model": {"configured": s.text.configured, "model": s.text.model},
            "speech": languages[LANGUAGE]["speech"],
            "tags": {"levels": list(tagging.LEVELS), "topics": list(tagging.TOPICS)},
            "dictionary": languages[LANGUAGE]["dictionary"],
            "languages": languages,
            "anki": anki,
        }

    # -- drafting ------------------------------------------------------------------

    @app.post("/api/drafts")
    def make_draft(body: DraftIn, request: Request):
        s = svc(request)
        lang = LANGUAGES[body.language]
        ls = s.for_language(body.language)
        ask = lambda: s.text.json(  # noqa: E731
            lang.SYSTEM_PROMPT,
            lang.user_message(body.text, body.context, body.kind, body.hint),
            lang.SCHEMA,
            f"{body.language}_card",
        )
        data = ask()
        for _ in range(2):
            # The model sometimes skips examples (mostly when given a context
            # sentence or a hint); a retry almost always fixes it.
            if (body.kind or data["kind"]) == "phrase" or len(data["examples"]) >= 2:
                break
            retry = ask()
            if len(retry["examples"]) >= 2:
                data = retry
        if body.kind:
            data["kind"] = body.kind  # the user's choice wins over the model's
        draft, input_note = lang.draft_from_model(data, body.context)
        draft.language = body.language
        checks: list[german.Check] = []
        if body.review:
            fixed = lang.apply_review(draft, s.text.json(
                lang.REVIEW_PROMPT, lang.review_message(draft, body.hint), lang.REVIEW_SCHEMA,
                "review", reasoning="high",
            ))
            checks += [german.Check(level="info", message=f"Review: {c}") for c in fixed]
        checks = lang.check(draft, ls.dictionary) + checks
        duplicates = _duplicates(s, body.language, draft.lemma, checks)
        return {"draft": draft, "checks": checks, "input_note": input_note, "duplicates": duplicates}

    @app.post("/api/speak")
    def speak(body: SpeakIn, request: Request):
        s = svc(request)
        speech = s.for_language(body.language).speech
        key = speech.synthesize(german.strip_html(body.text), body.language)
        return {"url": f"/audio/{speech.filename(key)}"}

    @app.get("/audio/{filename}")
    def audio(filename: str, request: Request):
        s = svc(request)
        for code in s.configured_languages():
            cache_dir = s.for_language(code).speech.cache_dir.resolve()
            path = (cache_dir / filename).resolve()
            if path.parent == cache_dir and path.is_file():
                return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})
        raise HTTPException(404)

    # -- saving ----------------------------------------------------------------------

    def notetype_id(s: Services, language: str, kind: str, *, refresh: bool = False) -> int:
        with notetype_lock:
            key = (language, kind)
            if refresh or key not in notetype_ids:
                notetype_ids[key] = s.manager.ensure_notetype(LANGUAGES[language].NOTETYPES[kind])
            return notetype_ids[key]

    @app.post("/api/notes", status_code=201)
    def save(body: SaveIn, request: Request):
        s = svc(request)
        draft = body.draft
        lang = LANGUAGES[draft.language]
        ls = s.for_language(draft.language)
        audio: dict[str, str] = {}
        if ls.speech.configured:
            texts = lang.speech_texts(draft)
            # The word and its examples are spoken in parallel; uploads stay sequential.
            with ThreadPoolExecutor(max_workers=3) as pool:
                keys = dict(zip(texts, pool.map(
                    lambda t: ls.speech.synthesize(t, draft.language), texts.values()
                )))
            for field_name, key in keys.items():
                audio[field_name] = s.manager.upload_media(
                    ls.speech.filename(key), ls.speech.path(key).read_bytes()
                )
        fields = lang.note_fields(draft, audio)
        deck_id = s.manager.ensure_deck(ls.deck)
        # Anki tags can't contain spaces.
        tags = [*TAGS, draft.kind, *(t.strip().replace(" ", "_") for t in draft.tags if t.strip())]
        try:
            note = s.manager.add_note(notetype_id(s, draft.language, draft.kind), deck_id, fields, tags,
                                      allow_duplicate=body.allow_duplicate)
        except UpstreamError as exc:
            if exc.status != 404:
                raise
            # The note type was deleted elsewhere since it was cached; recreate it once.
            note = s.manager.add_note(
                notetype_id(s, draft.language, draft.kind, refresh=True), deck_id, fields, tags,
                allow_duplicate=body.allow_duplicate,
            )
        return {"id": note["id"], "notetype": note["notetype"], "deck": ls.deck, "audio": len(audio)}

    @app.get("/api/recent")
    def recent(request: Request, language: german.Language = LANGUAGE):
        s = svc(request)
        deck = s.for_language(language).deck
        return s.manager.find_notes(f'"deck:{deck}" tag:card-generator', limit=20)

    # -- frontend --------------------------------------------------------------------

    static = static_dir or Path(os.environ.get("CARD_GENERATOR_STATIC", Path(__file__).parent / "static"))
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")

    return app


def _duplicates(s: Services, language: str, lemma: str, checks: list[german.Check]) -> list[dict]:
    try:
        rows = s.manager.find_notes(LANGUAGES[language].duplicate_query(lemma), limit=10)
    except UpstreamError as exc:
        checks.append(german.Check(level="info", message=f"Couldn't look for duplicates: {exc}"))
        return []
    return [{"id": r["id"], "text": r["first_field"], "notetype": r["notetype"], "decks": r["decks"]} for r in rows]


def services_from_env() -> Services:
    data = Path(os.environ.get("CARD_GENERATOR_DATA", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    services = Services(
        text=TextModel(
            os.environ.get("OPENROUTER_API_KEY") or None,
            os.environ.get("OPENROUTER_MODEL", "openai/gpt-6-luna"),
            reasoning=os.environ.get("OPENROUTER_REASONING", "medium"),
        ),
        speech=Speech(
            os.environ.get("ELEVENLABS_API_KEY") or None,
            os.environ.get("ELEVENLABS_VOICE_ID", "IWm8DnJ4NGjFI7QAM5lM"),  # "Stephan", native German
            os.environ.get("ELEVENLABS_MODEL", "eleven_v4"),
            data / "audio",
        ),
        manager=AnkiManager(os.environ.get("ANKI_MANAGER_URL", "http://anki-manager:8000")),
        dictionary=Dictionary(data / "de-dictionary.sqlite"),
        deck=os.environ.get("CARD_GENERATOR_DECK", "German - Mine"),
    )
    services.languages["es"] = LanguageServices(
        speech=Speech(
            os.environ.get("ELEVENLABS_API_KEY") or None,
            os.environ.get("ELEVENLABS_VOICE_ID_ES") or services.speech.voice_id,
            services.speech.model,
            data / "audio",
        ),
        dictionary=Dictionary(data / "es-dictionary.sqlite", spanish.parse_noun, spanish.parse_verb,
                              spanish.SCHEMA_VERSION),
        deck=os.environ.get("CARD_GENERATOR_DECK_ES", "Spanish - Mine"),
    )
    return services
