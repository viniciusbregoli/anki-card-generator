"""A dictionary built from real Wiktionary entries, and fakes for the three remote services."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from card_generator import spanish
from card_generator.api import LanguageServices, Services, create_app
from card_generator.clients import AnkiManager, Speech, TextModel
from card_generator.dictionary import Dictionary, build

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def dictionary(tmp_path_factory) -> Dictionary:
    path = tmp_path_factory.mktemp("dict") / "de.sqlite"
    with open(FIXTURES / "kaikki-sample.jsonl", encoding="utf-8") as f:
        build(f, path)
    d = Dictionary(path)
    assert d.state == "ready"
    return d


class FakeManager:
    """Just enough of anki-manager's API, recording what was written."""

    def __init__(self) -> None:
        self.notetypes: dict[str, dict] = {}
        self.decks: dict[str, int] = {"Default": 1}
        self.media: dict[str, bytes] = {}
        self.notes: list[dict] = []
        self.searches: list[str] = []
        self.existing: list[dict] = []  # rows returned by any search

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-anki-manager") == "1"
        path, method = request.url.path, request.method
        if path == "/api/status":
            return httpx.Response(200, json={"sync": {"state": "ok"}, "notes": len(self.notes)})
        if path == "/api/notetypes" and method == "PUT":
            body = json.loads(request.content)
            nt = self.notetypes.setdefault(body["name"], {**body, "id": 1000 + len(self.notetypes)})
            return httpx.Response(200, json={"id": nt["id"], "name": nt["name"]})
        if path == "/api/decks" and method == "GET":
            return httpx.Response(200, json=[
                {"id": i, "full_name": n, "children": []} for n, i in self.decks.items()
            ])
        if path == "/api/decks" and method == "POST":
            name = json.loads(request.content)["name"]
            self.decks[name] = 2000 + len(self.decks)
            return httpx.Response(201, json={"id": self.decks[name]})
        if path == "/api/notes" and method == "GET":
            q = request.url.params["q"]
            self.searches.append(q)
            return httpx.Response(200, json={"total": len(self.existing), "notes": self.existing})
        if path == "/api/media":
            # Multipart body: pull out the filename and keep the raw bytes.
            name = request.content.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
            self.media[name] = request.content
            return httpx.Response(201, json={"filename": name})
        if path == "/api/notes" and method == "POST":
            body = json.loads(request.content)
            if not body["allow_duplicate"] and any(n["fields"][0] == body["fields"][0] for n in self.notes):
                return httpx.Response(409, json={"detail": {"code": "duplicate", "message": "duplicate"}})
            nt = next(n for n in self.notetypes.values() if n["id"] == body["notetype_id"])
            self.notes.append({**body, "id": 5000 + len(self.notes)})
            return httpx.Response(201, json={"id": self.notes[-1]["id"], "notetype": nt["name"]})
        return httpx.Response(404, json={"detail": "not found"})


class FakeModel:
    """Replays a canned JSON answer and records the prompt."""

    def __init__(self) -> None:
        self.answer: dict = {}
        self.prompts: list[str] = []
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        assert body["response_format"]["json_schema"]["strict"] is True
        self.prompts.append(body["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(self.answer)}}]})


class FakeSpeech:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.languages: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model_id"] == "eleven_v4" and body["language_code"] in ("de", "es")
        self.spoken.append(body["text"])
        self.languages.append(body["language_code"])
        return httpx.Response(200, content=b"ID3fake-mp3:" + body["text"].encode())


@pytest.fixture
def fakes():
    return FakeManager(), FakeModel(), FakeSpeech()


@pytest.fixture
def client(tmp_path: Path, dictionary: Dictionary, fakes):
    manager, model, speech = fakes
    services = Services(
        text=TextModel("key", "openai/gpt-6-luna", client=httpx.Client(transport=httpx.MockTransport(model.handler))),
        speech=Speech("key", "voice", "eleven_v4", tmp_path / "audio",
                      client=httpx.Client(transport=httpx.MockTransport(speech.handler))),
        manager=AnkiManager("http://manager", client=httpx.Client(transport=httpx.MockTransport(manager.handler))),
        dictionary=dictionary,
        deck="German - Mine",
    )
    es_path = tmp_path / "es.sqlite"
    with open(FIXTURES / "kaikki-spanish-sample.jsonl", encoding="utf-8") as lines:
        build(lines, es_path, spanish.parse_noun, spanish.parse_verb, spanish.SCHEMA_VERSION)
    services.languages["es"] = LanguageServices(
        speech=Speech("key", "spanish-voice", "eleven_v4", tmp_path / "audio",
                      client=httpx.Client(transport=httpx.MockTransport(speech.handler))),
        dictionary=Dictionary(es_path, spanish.parse_noun, spanish.parse_verb, spanish.SCHEMA_VERSION),
        deck="Spanish - Mine",
    )
    app = create_app(services, static_dir=Path("/nonexistent"), build_dictionary=False)
    with TestClient(app, headers={"x-card-generator": "1"}) as c:
        yield c


def answer(**overrides) -> dict:
    """A complete model answer for a noun; override fields per test."""
    base = {
        "kind": "noun", "lemma": "Rechnung", "article": "die", "plural": "Rechnungen",
        "part_of_speech": "", "meaning": "bill; invoice", "gender_rule": "",
        "present": "", "preterite": "", "perfect": "", "governs": "",
        "examples": [
            {"de": "Die <b>Rechnung</b>, bitte.", "en": "The bill, please."},
            {"de": "Ich bezahle die <b>Rechnung</b> morgen.", "en": "I'll pay the bill tomorrow."},
        ],
        "note": "", "input_note": "", "level": "A2", "topic": "shopping-money",
    }
    return {**base, **overrides}
