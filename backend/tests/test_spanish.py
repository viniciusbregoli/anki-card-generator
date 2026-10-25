"""Spanish checks against real-shaped Wiktionary entries."""

import json
import re
from pathlib import Path

import pytest

from card_generator import german, spanish
from card_generator.dictionary import Dictionary, build
from card_generator.german import Draft
from conftest import spanish_answer as model_answer

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def dictionary(tmp_path) -> Dictionary:
    path = tmp_path / "es.sqlite"
    with open(FIXTURES / "kaikki-spanish-sample.jsonl", encoding="utf-8") as lines:
        build(lines, path, spanish.parse_noun, spanish.parse_verb, spanish.SCHEMA_VERSION)
    dictionary = Dictionary(path, spanish.parse_noun, spanish.parse_verb, spanish.SCHEMA_VERSION)
    assert dictionary.state == "ready"
    return dictionary


def noun(lemma: str, article: str, plural: str = "", rule: str = "") -> Draft:
    return Draft(kind="noun", language="es", lemma=lemma, article=article, plural=plural, gender_rule=rule)


def levels(checks):
    return [check.level for check in checks]


def test_dictionary_uses_spanish_parsers_and_schema(dictionary):
    assert [(noun.gender, noun.plurals) for noun in dictionary.nouns("casa")] == [("f", ("casas",))]
    assert dictionary.nouns("agua")[0].gender == "f"
    assert dictionary.nouns("casas") == []
    assert dictionary.nouns("nupcias")[0].gender == "f-p"
    assert dictionary.nouns("víveres")[0].gender == "m-p"
    verb = dictionary.verb("hablar")
    assert (verb.present, verb.preterite, verb.participle) == ("habla", "habló", "hablado")
    assert verb.auxiliaries == ("haber",)
    assert Dictionary(dictionary.path, schema_version=spanish.SCHEMA_VERSION + 1).state == "missing"


def test_real_shape_fixture_is_valid_jsonl():
    with open(FIXTURES / "kaikki-spanish-sample.jsonl", encoding="utf-8") as lines:
        entries = [json.loads(line) for line in lines]
    assert len(entries) == 6
    assert all(entry["lang_code"] == "es" for entry in entries)


def test_noun_gender_and_plural_are_corrected(dictionary):
    draft = noun("casa", "el", "cases")
    checks = spanish.check(draft, dictionary)
    assert (draft.article, draft.plural) == ("la", "casas")
    assert levels(checks) == ["warn", "warn"]
    assert "Changed to la" in checks[0].message
    assert "Plural changed" in checks[1].message


def test_feminine_stressed_a_keeps_singular_el(dictionary):
    draft = noun("agua", "el", "aguas", "Feminine, but singular el precedes stressed a.")
    checks = spanish.check(draft, dictionary)
    assert draft.article == "el"
    assert "Feminine" in draft.gender_rule and "las" in draft.gender_rule
    assert levels(checks) == ["ok"]
    assert "Feminine noun" in checks[0].message


def test_plural_only_noun(dictionary):
    draft = noun("nupcias", "los", "nupcias")
    checks = spanish.check(draft, dictionary)
    assert (draft.article, draft.plural) == ("las", "")
    assert checks[0].level == "warn"

    draft = noun("nupcias", "las", "nupcias")
    checks = spanish.check(draft, dictionary)
    assert (draft.article, draft.plural) == ("las", "")
    assert levels(checks) == ["ok"]

    draft = noun("víveres", "las")
    spanish.check(draft, dictionary)
    assert draft.article == "los"


def test_feminine_el_correction_keeps_feminine_plural(dictionary):
    draft = noun("agua", "la", "incorrect")
    checks = spanish.check(draft, dictionary)
    assert (draft.article, draft.plural) == ("el", "aguas")
    assert levels(checks) == ["warn", "warn"]


def test_plural_only_without_gender_requires_review(tmp_path):
    path = tmp_path / "unknown.sqlite"
    entry = {"word": "unknown", "pos": "noun", "senses": [{"tags": ["plural-only"]}]}
    build([json.dumps(entry)], path, spanish.parse_noun, spanish.parse_verb, spanish.SCHEMA_VERSION)
    dictionary = Dictionary(path, spanish.parse_noun, spanish.parse_verb, spanish.SCHEMA_VERSION)
    draft = noun("unknown", "la")
    checks = spanish.check(draft, dictionary)
    assert draft.article == "la"
    assert levels(checks) == ["warn"]


@pytest.mark.parametrize("article", ["los", "las"])
def test_plural_articles_are_unverified_when_dictionary_is_missing(tmp_path, article):
    dictionary = Dictionary(tmp_path / "missing.sqlite", spanish.parse_noun, spanish.parse_verb,
                            spanish.SCHEMA_VERSION)
    draft = noun("nupcias", article)
    checks = spanish.check(draft, dictionary)
    assert draft.article == article
    assert levels(checks) == ["info"]
    assert "unverified" in checks[0].message


def test_plural_article_for_unknown_noun_is_unverified(dictionary):
    draft = noun("unknown", "las")
    checks = spanish.check(draft, dictionary)
    assert draft.article == "las"
    assert levels(checks) == ["info"]
    assert "unverified" in checks[0].message


def test_plural_article_for_known_singular_noun_is_flagged(dictionary):
    draft = noun("casa", "las")
    checks = spanish.check(draft, dictionary)
    assert checks[0].level == "warn"
    assert "Pick el or la" in checks[0].message


def test_verb_forms_are_corrected(dictionary):
    draft = Draft(kind="verb", language="es", lemma="hablar", present="hablo",
                  preterite="hablaba", perfect="he hablado")
    checks = spanish.check(draft, dictionary)
    assert (draft.present, draft.preterite, draft.perfect) == ("habla", "habló", "ha hablado")
    assert levels(checks) == ["warn", "warn", "warn"]

    good = Draft(kind="verb", language="es", lemma="hablar", present="habla",
                 preterite="habló", perfect="ha hablado")
    assert levels(spanish.check(good, dictionary)) == ["ok"]


def test_reflexive_verb_uses_bare_lookup_and_se_forms(dictionary):
    draft = Draft(kind="verb", language="es", lemma="levantarse", present="levanta",
                  preterite="levantó", perfect="ha levantado")
    checks = spanish.check(draft, dictionary)
    assert (draft.present, draft.preterite, draft.perfect) == (
        "se levanta", "se levantó", "se ha levantado"
    )
    assert levels(checks) == ["warn", "warn", "warn"]
    assert levels(spanish.check(draft, dictionary)) == ["ok"]


def test_duplicate_query_covers_spanish_note_types_and_escapes():
    query = spanish.duplicate_query("casa")
    assert '"Palabra:casa"' in query
    assert '"Infinitivo:casa"' in query
    assert '"es_word:casa,*"' in query
    assert 'casa\\"\\*' in spanish.duplicate_query('casa"*')


def test_note_fields_and_speech_follow_spanish_field_names():
    draft = noun("casa", "la", "casas")
    draft.meaning = "house"
    draft.examples = [german.Example(de="La <b>casa</b> es grande.", en="The house is big.")]
    fields = spanish.note_fields(draft, {"Audio_Palabra": "acg-es-1.mp3"})
    row = dict(zip(spanish.NOTETYPES["noun"]["fields"], fields))
    assert row["Palabra"] == "casa"
    assert row["Artículo"] == "la"
    assert row["Audio_Palabra"] == "[sound:acg-es-1.mp3]"
    assert row["Ejemplo2"] == ""
    assert spanish.speech_texts(draft) == {
        "Audio_Palabra": "la casa", "Audio_Ejemplo1": "La casa es grande."
    }


def test_templates_only_use_existing_fields_and_answer_side_links():
    for kind, notetype in spanish.NOTETYPES.items():
        for template in notetype["templates"]:
            used = set(re.findall(
                r"\{\{[#/^]?(?:text:)?([^}#/^:]+?)\}\}", template["front"] + template["back"]
            ))
            assert used - {"FrontSide"} <= set(notetype["fields"]), notetype["name"]
            if kind != "phrase":
                assert 'class="links"' in template["back"]
                assert "links" not in template["front"]
    verb_back = spanish.NOTETYPES["verb"]["templates"][0]["back"]
    assert 'data-w="{{text:Infinitivo}}"' in verb_back
    assert "#Spanish" in verb_back
    assert "wordreference.com/conj/esverbs.aspx" in verb_back
    assert "wordreference.com/es/en/translation.asp" in verb_back
    assert 'replace(/se$/, "")' in verb_back


def test_draft_from_model_sets_spanish_and_language_specific_fields():
    draft, input_note = spanish.draft_from_model(model_answer(input_note="Corrected input."), "  Mi casa.  ")
    assert draft.language == "es"
    assert draft.article == "la"
    assert draft.source == "Mi casa."
    assert input_note == "Corrected input."

    verb, _ = spanish.draft_from_model(model_answer(
        kind="verb", lemma="levantarse", article="", plural="", present="se levanta",
        preterite="se levantó", perfect="se ha levantado", governs="", examples=[],
    ))
    assert verb.language == "es"
    assert (verb.present, verb.preterite, verb.perfect) == ("se levanta", "se levantó", "se ha levantado")
