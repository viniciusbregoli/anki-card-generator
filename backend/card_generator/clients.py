"""Small HTTP clients: OpenRouter (text), ElevenLabs (speech) and anki-manager (the collection)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import httpx


class UpstreamError(Exception):
    """A service this app depends on failed. `status` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 502, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _error_text(r: httpx.Response) -> str:
    try:
        data = r.json()
    except ValueError:
        return r.text[:300] or r.reason_phrase
    if not isinstance(data, dict):  # valid JSON need not be an object
        return json.dumps(data, ensure_ascii=False)[:300]
    detail = data.get("error") or data.get("detail") or data
    if isinstance(detail, dict):
        detail = detail.get("message") or json.dumps(detail)[:300]
    return str(detail)


# -- OpenRouter ----------------------------------------------------------------------


class TextModel:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str | None, model: str, *, reasoning: str = "medium",
                 client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.reasoning = reasoning
        self._http = client or httpx.Client(timeout=httpx.Timeout(10, read=120))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def json(self, system: str, user: str, schema: dict, name: str, *, reasoning: str | None = None) -> dict:
        """One chat completion constrained to `schema`; returns the parsed object."""
        if not self.api_key:
            raise UpstreamError("OPENROUTER_API_KEY is not set.", 503, "not_configured")
        try:
            r = self._http.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}", "X-Title": "anki-card-generator"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": name, "strict": True, "schema": schema},
                    },
                    "reasoning": {"effort": reasoning or self.reasoning},
                },
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Text model is unreachable ({exc}).") from exc
        if r.status_code != 200:
            raise UpstreamError(f"Text model error: {_error_text(r)}")
        try:
            body = r.json()
        except ValueError as exc:
            raise UpstreamError(f"Text model returned a non-JSON answer: {r.text[:200]}") from exc
        if not isinstance(body, dict):
            raise UpstreamError(f"Text model returned an unexpected answer: {str(body)[:200]}")
        if error := body.get("error"):
            message = error.get("message", error) if isinstance(error, dict) else error
            raise UpstreamError(f"Text model error: {message}")
        try:
            return json.loads(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise UpstreamError(f"Text model returned no usable JSON ({exc}).") from exc


# -- ElevenLabs ----------------------------------------------------------------------


class Speech:
    """Text to speech with a disk cache, so the same sentence is never paid for twice."""

    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"

    def __init__(self, api_key: str | None, voice_id: str, model: str, cache_dir: Path, *,
                 client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.cache_dir = cache_dir
        self.backoff = 1.5  # seconds; multiplied by the attempt number
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = client or httpx.Client(timeout=httpx.Timeout(10, read=90))

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.voice_id)

    def key(self, text: str, language: str) -> str:
        raw = f"{self.model}\x1f{self.voice_id}\x1f{language}\x1f{text.strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def filename(self, key: str) -> str:
        """Name used both in the cache and in Anki's media folder."""
        return f"acg-{key}.mp3"

    def path(self, key: str) -> Path:
        return self.cache_dir / self.filename(key)

    def synthesize(self, text: str, language: str) -> str:
        """Returns the cache key; the audio is at `path(key)`."""
        text = text.strip()
        if not text:
            raise UpstreamError("Nothing to speak.", 400)
        key = self.key(text, language)
        if self.path(key).is_file():
            return key
        if not self.configured:
            raise UpstreamError("ELEVENLABS_API_KEY is not set.", 503, "not_configured")
        for attempt in range(3):
            try:
                r = self._http.post(
                    self.URL.format(voice=self.voice_id),
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": self.api_key or ""},
                    json={"text": text, "model_id": self.model, "language_code": language},
                )
            except httpx.HTTPError as exc:
                raise UpstreamError(f"Speech service is unreachable ({exc}).") from exc
            # 429: too many requests at once for the plan's concurrency limit.
            if r.status_code != 429 or attempt == 2:
                break
            time.sleep(self.backoff * (attempt + 1))
        if r.status_code != 200 or not r.content:
            raise UpstreamError(f"Speech error: {_error_text(r)}")
        tmp = self.path(key).with_suffix(".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(self.path(key))
        return key


# -- anki-manager -----------------------------------------------------------------


class AnkiManager:
    """The collection lives in anki-manager; this app only talks to its JSON API."""

    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = client or httpx.Client(timeout=httpx.Timeout(10, read=60))

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            r = self._http.request(method, self.base_url + path, headers={"x-anki-manager": "1"}, **kwargs)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"anki-manager is unreachable ({exc}).", 503, "manager_down") from exc
        if r.status_code >= 400:
            code = None
            try:
                body = r.json()
                if isinstance(body, dict):
                    detail = body.get("detail")
                    code = body.get("code") or (detail.get("code") if isinstance(detail, dict) else None)
            except ValueError:
                pass
            status = r.status_code if r.status_code in (400, 404, 409) else 502
            raise UpstreamError(f"anki-manager: {_error_text(r)}", status, code)
        return r

    def status(self) -> dict:
        return self._call("GET", "/api/status").json()

    def ensure_notetype(self, definition: dict) -> int:
        return self._call("PUT", "/api/notetypes", json=definition).json()["id"]

    def ensure_deck(self, name: str) -> int:
        def walk(nodes: list[dict]) -> int | None:
            for n in nodes:
                if n["full_name"] == name:
                    return n["id"]
                if (found := walk(n["children"])) is not None:
                    return found
            return None

        if (found := walk(self._call("GET", "/api/decks").json())) is not None:
            return found
        return self._call("POST", "/api/decks", json={"name": name}).json()["id"]

    def find_notes(self, query: str, *, limit: int = 10, page: int = 1, sort: str = "created",
                   order: str = "desc") -> list[dict]:
        params = {"q": query, "limit": limit, "page": page, "sort": sort, "order": order}
        return self._call("GET", "/api/notes", params=params).json()["notes"]

    def upload_media(self, filename: str, data: bytes) -> str:
        files = {"file": (filename, data, "audio/mpeg")}
        return self._call("POST", "/api/media", files=files).json()["filename"]

    def add_note(self, notetype_id: int, deck_id: int, fields: list[str], tags: list[str],
                 *, allow_duplicate: bool = False) -> dict:
        body = {"notetype_id": notetype_id, "deck_id": deck_id, "fields": fields, "tags": tags,
                "allow_duplicate": allow_duplicate}
        return self._call("POST", "/api/notes", json=body).json()
