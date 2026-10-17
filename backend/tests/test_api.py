"""HTTP API with fake remote services."""

import json

import httpx
from fastapi.testclient import TestClient

from conftest import answer


def test_writes_require_csrf_header(client):
    bare = TestClient(client.app)
    assert bare.post("/api/drafts", json={"text": "Rechnung"}).status_code == 403
    assert bare.get("/api/status").status_code == 200


def test_status(client):
    body = client.get("/api/status").json()
    assert body["anki"]["ok"] and body["dictionary"]["state"] == "ready"
    assert body["text_model"] == {"configured": True, "model": "openai/gpt-6-luna"}


def test_draft_checks_and_finds_duplicates(client, fakes):
    manager, model, _ = fakes
    model.answer = answer(article="der", input_note="You typed the plural.")
    manager.existing = [{"id": 1, "first_field": "Rechnung", "notetype": "Goethe", "decks": ["Goethe::A2"]}]

    body = client.post("/api/drafts", json={"text": "Rechnungen", "context": "Die Rechnungen liegen da."}).json()
    assert body["draft"]["article"] == "die"  # corrected from der
    assert body["draft"]["source"] == "Die Rechnungen liegen da."
    assert body["input_note"] == "You typed the plural."
    assert body["duplicates"] == [{"id": 1, "text": "Rechnung", "notetype": "Goethe", "decks": ["Goethe::A2"]}]
    assert "Context sentence: Die Rechnungen liegen da." in model.prompts[0]
    assert '"Wort_DE:Rechnung"' in manager.searches[0]


def test_forced_kind_wins(client, fakes):
    _, model, _ = fakes
    model.answer = answer(kind="noun", lemma="Es kommt darauf an")
    body = client.post("/api/drafts", json={"text": "es kommt darauf an", "kind": "phrase"}).json()
    assert body["draft"]["kind"] == "phrase" and body["draft"]["article"] == ""
    assert body["draft"]["examples"] == []
    assert 'Make a "phrase" card.' in model.prompts[0]


def test_speak_caches_audio(client, fakes):
    _, _, speech = fakes
    first = client.post("/api/speak", json={"text": "die <b>Tür</b>"}).json()
    again = client.post("/api/speak", json={"text": "die Tür"}).json()
    assert first == again and speech.spoken == ["die Tür"]
    audio = client.get(first["url"])
    assert audio.status_code == 200 and audio.content.startswith(b"ID3")
    assert client.get("/audio/../../etc/passwd").status_code == 404


def test_save_creates_note_type_deck_media_and_note(client, fakes):
    manager, model, speech = fakes
    model.answer = answer()
    draft = client.post("/api/drafts", json={"text": "Rechnung"}).json()["draft"]

    r = client.post("/api/notes", json={"draft": draft})
    assert r.status_code == 201, r.text
    assert r.json()["audio"] == 3
    assert set(manager.notetypes) == {"DE Noun"}
    assert "German - Mine" in manager.decks
    note = manager.notes[0]
    assert note["deck_id"] == manager.decks["German - Mine"]
    assert note["tags"] == ["card-generator", "noun", "level::A2", "topic::shopping-money"]
    assert note["fields"][:3] == ["Rechnung", "die", "Rechnungen"]
    assert all(f"[sound:{name}]" in note["fields"] for name in manager.media)
    assert sorted(speech.spoken) == ["Die Rechnung, bitte.", "Ich bezahle die Rechnung morgen.", "die Rechnung"]

    # Saving again: same audio from the cache, and the duplicate is refused until allowed.
    dup = client.post("/api/notes", json={"draft": draft})
    assert dup.status_code == 409 and dup.json()["code"] == "duplicate"
    assert client.post("/api/notes", json={"draft": draft, "allow_duplicate": True}).status_code == 201
    assert len(speech.spoken) == 3


def test_missing_examples_are_retried_once(client, fakes):
    _, model, _ = fakes
    answers = iter([answer(examples=[]), answer()])

    def handler(request: httpx.Request) -> httpx.Response:
        model.answer = next(answers)
        return model.handler(request)

    client.app.state.services.text._http = httpx.Client(transport=httpx.MockTransport(handler))
    body = client.post("/api/drafts", json={"text": "Rechnung", "context": "Die Rechnung, bitte."}).json()
    assert len(body["draft"]["examples"]) == 2 and len(model.prompts) == 2


def test_speech_retries_when_rate_limited(client, fakes):
    _, _, speech = fakes
    responses = iter([httpx.Response(429, json={"detail": "busy"})])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses, None) or speech.handler(request)

    tts = client.app.state.services.speech
    tts._http, tts.backoff = httpx.Client(transport=httpx.MockTransport(handler)), 0
    assert client.post("/api/speak", json={"text": "die Tür"}).status_code == 200
    assert speech.spoken == ["die Tür"]


def test_draft_gets_level_and_topic_tags_from_the_model(client, fakes):
    _, model, _ = fakes
    model.answer = answer(level="B1", topic="work")
    draft = client.post("/api/drafts", json={"text": "Rechnung"}).json()["draft"]
    assert draft["tags"] == ["level::B1", "topic::work"]


def test_hint_reaches_the_prompt(client, fakes):
    _, model, _ = fakes
    model.answer = answer()
    client.post("/api/drafts", json={"text": "sein", "hint": "to be"})
    assert "Intended sense: to be" in model.prompts[0]


def test_saved_tags_have_no_spaces(client, fakes):
    manager, model, _ = fakes
    model.answer = answer()
    draft = client.post("/api/drafts", json={"text": "Rechnung"}).json()["draft"]
    draft["tags"] = ["level::A2", "topic::my topic", " "]
    assert client.post("/api/notes", json={"draft": draft}).status_code == 201
    assert manager.notes[0]["tags"] == ["card-generator", "noun", "level::A2", "topic::my_topic"]


def test_review_pass_fixes_the_draft(client, fakes):
    _, model, _ = fakes
    fixed = [{"de": "Ich möchte <b>auch</b> einen Kaffee.", "en": "I'd like a coffee too."},
             {"de": "Sie spricht <b>auch</b> Englisch.", "en": "She also speaks English."}]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["response_format"]["json_schema"]["name"] == "review":
            assert body["reasoning"] == {"effort": "high"}
            model.answer = {"lemma": "auch", "meaning": "also; too", "examples": fixed, "note": "",
                            "changes": ["Fixed the word order in example 1."]}
        else:
            model.answer = answer(kind="word", lemma="auch", article="", plural="", meaning="also",
                                  examples=[{"de": "Ich <b>auch</b> möchte einen Kaffee.", "en": "x"}])
        return model.handler(request)

    client.app.state.services.text._http = httpx.Client(transport=httpx.MockTransport(handler))
    body = client.post("/api/drafts", json={"text": "auch", "review": True}).json()
    assert body["draft"]["examples"] == fixed and body["draft"]["meaning"] == "also; too"
    assert {"level": "info", "message": "Review: Fixed the word order in example 1."} in body["checks"]
