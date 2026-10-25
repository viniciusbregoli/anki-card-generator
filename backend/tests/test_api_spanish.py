"""Both languages use their own prompts, dictionaries, voices, and Anki definitions."""

import json

import httpx
import pytest

from card_generator import spanish
from card_generator.api import create_app, services_from_env
from conftest import answer


def spanish_answer(**overrides):
    return answer(
        **{
            "lemma": "casa", "article": "la", "plural": "casas", "meaning": "house",
            "examples": [
                {"de": "La <b>casa</b> es grande.", "en": "The house is big."},
                {"de": "Voy a <b>casa</b>.", "en": "I'm going home."},
            ],
            **overrides,
        }
    )


def test_status_has_independent_language_services(client):
    body = client.get("/api/status").json()
    assert body["language"] == "de"
    assert body["deck"] == body["languages"]["de"]["deck"] == "German - Mine"
    assert body["languages"]["es"]["deck"] == "Spanish - Mine"
    assert body["languages"]["es"]["speech"]["voice"] == "spanish-voice"
    assert all(lang["dictionary"]["state"] == "ready" for lang in body["languages"].values())


def test_spanish_draft_uses_its_prompt_schema_dictionary_and_duplicates(client, fakes):
    manager, model, _ = fakes
    model.answer = spanish_answer(article="el", plural="cases")
    response = client.post("/api/drafts", json={"text": "casa", "language": "es"})
    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    assert (draft["language"], draft["article"], draft["plural"]) == ("es", "la", "casas")
    request = model.requests[0]
    assert request["messages"][0]["content"] == spanish.SYSTEM_PROMPT
    assert request["response_format"]["json_schema"]["name"] == "es_card"
    assert request["response_format"]["json_schema"]["schema"]["properties"]["article"]["enum"] == [
        "el", "la", "los", "las", ""
    ]
    assert '"Palabra:casa"' in manager.searches[0]
    assert "Wort_DE" not in manager.searches[0]


@pytest.mark.parametrize("kind,count", [("noun", 3), ("verb", 2), ("word", 2), ("phrase", 3)])
def test_spanish_saves_each_note_type_with_spanish_audio(client, fakes, kind, count):
    manager, model, speech = fakes
    model.answer = spanish_answer(kind=kind)
    draft = client.post("/api/drafts", json={"text": "casa", "language": "es"}).json()["draft"]
    response = client.post("/api/notes", json={"draft": draft})
    assert response.status_code == 201, response.text
    saved = response.json()
    name = f"ES {kind.title()}"
    assert saved["notetype"] == name
    assert saved["deck"] == "Spanish - Mine"
    assert len(manager.notetypes[name]["templates"]) == count
    assert manager.notes[0]["deck_id"] == manager.decks["Spanish - Mine"]
    assert saved["audio"] == (1 if kind == "phrase" else 3)
    assert speech.languages == ["es"] * saved["audio"]
    assert all(f"[sound:{name}]" in manager.notes[0]["fields"] for name in manager.media)
    assert "German - Mine" not in manager.decks


def test_mixed_saves_keep_separate_note_type_caches_and_decks(client, fakes):
    manager, model, _ = fakes
    model.answer = spanish_answer()
    es = client.post("/api/drafts", json={"text": "casa", "language": "es"}).json()["draft"]
    model.answer = answer()
    de = client.post("/api/drafts", json={"text": "Rechnung"}).json()["draft"]
    assert de["language"] == "de"
    for draft in [es, de, {**es, "lemma": "otra casa"}]:
        assert client.post("/api/notes", json={"draft": draft}).status_code == 201
    assert set(manager.notetypes) == {"ES Noun", "DE Noun"}
    assert [n["notetype_id"] for n in manager.notes] == [
        manager.notetypes[name]["id"] for name in ["ES Noun", "DE Noun", "ES Noun"]
    ]
    assert [n["deck_id"] for n in manager.notes] == [
        manager.decks[name] for name in ["Spanish - Mine", "German - Mine", "Spanish - Mine"]
    ]


def test_speech_cache_keeps_same_text_separate_by_language(client, fakes):
    _, _, speech = fakes
    de = client.post("/api/speak", json={"text": "normal"}).json()
    es = client.post("/api/speak", json={"text": "normal", "language": "es"}).json()
    assert es != de
    assert client.post("/api/speak", json={"text": "normal", "language": "es"}).json() == es
    assert speech.languages == ["de", "es"]
    for audio in [de, es]:
        assert client.get(audio["url"]).content.startswith(b"ID3")


def test_spanish_audio_is_served_from_its_own_cache_directory(client, tmp_path):
    client.app.state.services.for_language("es").speech.cache_dir = tmp_path
    response = client.post("/api/speak", json={"text": "casa", "language": "es"})
    assert response.status_code == 200
    audio = client.get(response.json()["url"])
    assert audio.status_code == 200 and audio.content.startswith(b"ID3")


def test_spanish_save_without_speech_still_creates_note(client, fakes):
    manager, model, speech = fakes
    client.app.state.services.for_language("es").speech.api_key = None
    model.answer = spanish_answer()
    draft = client.post("/api/drafts", json={"text": "casa", "language": "es"}).json()["draft"]
    response = client.post("/api/notes", json={"draft": draft})
    assert response.status_code == 201
    assert response.json()["audio"] == 0
    assert manager.notes[0]["fields"][0] == "casa"
    assert speech.spoken == []


def test_recent_searches_the_selected_language_deck(client, fakes):
    manager, _, _ = fakes
    assert client.get("/api/recent?language=es").status_code == 200
    assert '"deck:Spanish - Mine"' in manager.searches[-1]
    assert client.get("/api/recent").status_code == 200
    assert '"deck:German - Mine"' in manager.searches[-1]


def test_unknown_language_and_cross_language_articles_are_rejected(client):
    assert client.post("/api/drafts", json={"text": "casa", "language": "fr"}).status_code == 422
    assert client.post("/api/speak", json={"text": "casa", "language": "fr"}).status_code == 422
    assert client.get("/api/recent?language=fr").status_code == 422
    for language, article in [("de", "la"), ("es", "die")]:
        response = client.post("/api/notes", json={"draft": {
            "kind": "noun", "lemma": "casa", "language": language, "article": article,
        }})
        assert response.status_code == 422


def test_spanish_review_uses_spanish_prompt_and_keeps_language(client, fakes):
    _, model, _ = fakes

    def handler(request):
        body = json.loads(request.content)
        if body["response_format"]["json_schema"]["name"] == "review":
            assert body["messages"][0]["content"] == spanish.REVIEW_PROMPT
            model.answer = {"lemma": "casa", "meaning": "house; home", "examples": spanish_answer()["examples"],
                            "note": "", "changes": ["Added the home sense."]}
        else:
            model.answer = spanish_answer()
        return model.handler(request)

    client.app.state.services.text._http = httpx.Client(transport=httpx.MockTransport(handler))
    body = client.post("/api/drafts", json={"text": "casa", "language": "es", "review": True}).json()
    assert body["draft"]["language"] == "es"
    assert body["draft"]["meaning"] == "house; home"
    assert any(check["message"] == "Review: Added the home sense." for check in body["checks"])


def test_environment_configures_both_languages_without_changing_german(monkeypatch, tmp_path):
    monkeypatch.setenv("CARD_GENERATOR_DATA", str(tmp_path))
    monkeypatch.setenv("CARD_GENERATOR_DECK", "My German")
    monkeypatch.setenv("CARD_GENERATOR_DECK_ES", "My Spanish")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "german-voice")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID_ES", "es-voice")
    services = services_from_env()
    assert services.configured_languages() == ["de", "es"]
    assert services.for_language("de").deck == "My German"
    es = services.for_language("es")
    assert es.deck == "My Spanish"
    assert es.speech.voice_id == "es-voice"
    assert services.speech.voice_id == "german-voice"
    assert es.dictionary.path.name == "es-dictionary.sqlite"
    assert es.dictionary.parse_noun is spanish.parse_noun
    assert es.dictionary.parse_verb is spanish.parse_verb
    assert es.dictionary.schema_version == spanish.SCHEMA_VERSION
    monkeypatch.delenv("ELEVENLABS_VOICE_ID_ES")
    assert services_from_env().for_language("es").speech.voice_id == "german-voice"


def test_startup_builds_each_dictionary_with_its_own_source(client, monkeypatch):
    services = client.app.state.services
    built = []
    monkeypatch.setattr(type(services.dictionary), "build_in_background", lambda self, url: built.append((self.path.name, url)))
    monkeypatch.setenv("CARD_GENERATOR_DICTIONARY_URL", "https://example.test/german.jsonl")
    monkeypatch.setenv("CARD_GENERATOR_DICTIONARY_URL_ES", "https://example.test/spanish.jsonl")
    create_app(services)
    assert built == [(services.dictionary.path.name, "https://example.test/german.jsonl"),
                     (services.for_language("es").dictionary.path.name, "https://example.test/spanish.jsonl")]
    built.clear()
    monkeypatch.setenv("CARD_GENERATOR_DICTIONARY_URL_ES", "")
    create_app(services)
    assert len(built) == 1 and built[0][0] == services.dictionary.path.name
