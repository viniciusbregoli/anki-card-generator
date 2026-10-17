"""Checks against Wiktionary and the suffix rules, using real Wiktionary entries."""

from card_generator import german
from card_generator.dictionary import Verb
from card_generator.german import Draft


def noun(lemma: str, article: str, plural: str = "", rule: str = "") -> Draft:
    return Draft(kind="noun", lemma=lemma, article=article, plural=plural, gender_rule=rule)


def levels(checks):
    return [c.level for c in checks]


def test_dictionary_parses_nouns_and_verbs(dictionary):
    assert [(n.article, n.plurals) for n in dictionary.nouns("Rechnung")] == [("die", ("Rechnungen",))]
    assert {n.article for n in dictionary.nouns("See")} == {"der", "die"}
    assert dictionary.nouns("Rechnungen") == []  # "plural of Rechnung" is not a noun of its own
    assert dictionary.nouns("Leute")[0].gender == "p"
    v = dictionary.verb("anfangen")
    assert (v.present, v.participle, v.auxiliaries) == ("fängt an", "angefangen", ("haben", "sein"))


def test_correct_gender_is_confirmed_with_suffix_rule(dictionary):
    d = noun("Rechnung", "die", "Rechnungen")
    checks = german.check(d, dictionary)
    assert levels(checks) == ["ok"]
    assert d.gender_rule == "Nouns ending in -ung are always feminine."


def test_wrong_gender_is_corrected(dictionary):
    d = noun("Rechnung", "der", "Rechnungen")
    checks = german.check(d, dictionary)
    assert d.article == "die"
    assert checks[0].level == "warn" and "Changed to die" in checks[0].message


def test_diminutive_rule_and_plural(dictionary):
    d = noun("Mädchen", "das", "Mädchens")
    checks = german.check(d, dictionary)
    assert d.plural == "Mädchen"  # nonstandard plural replaced by the standard one
    assert any("Plural changed" in c.message for c in checks)
    assert "diminutives" in d.gender_rule


def test_two_genders_keep_the_models_choice_and_mention_the_other(dictionary):
    d = noun("See", "die", "Seen")
    checks = german.check(d, dictionary)
    assert d.article == "die"
    assert any(c.level == "info" and "der See" in c.message for c in checks)


def test_exception_to_suffix_rule(dictionary):
    # Name ends in -e (usually feminine) but is masculine.
    d = noun("Name", "der", "Namen", rule="Weak masculine noun (n-declension).")
    german.check(d, dictionary)
    assert d.gender_rule.startswith("Exception: nouns ending in -e are usually feminine, but it's der Name.")
    assert "n-declension" in d.gender_rule


def test_compound_rule_and_no_false_split(dictionary):
    d = noun("Haustür", "die", "Haustüren")
    german.check(d, dictionary)
    assert d.gender_rule == "Compound noun: it takes the gender of its last part, die Tür."

    d = noun("Fenster", "das", "Fenster")
    german.check(d, dictionary)
    assert d.gender_rule == ""  # not "Fen" + "Ster"


def test_unknown_compound_with_wrong_gender_is_flagged(dictionary):
    d = noun("Gartentür", "der", "Gartentüren")
    checks = german.check(d, dictionary)
    assert d.article == "der"  # not in Wiktionary: flagged, not changed
    assert any(c.level == "warn" and "die Tür" in c.message for c in checks)

    d = noun("Gartentür", "die", "Gartentüren")
    checks = german.check(d, dictionary)
    assert levels(checks) == ["ok"] and "last part is die Tür" in checks[0].message


def test_plural_only_noun(dictionary):
    d = noun("Leute", "der", "Leute")
    checks = german.check(d, dictionary)
    assert (d.article, d.plural) == ("die", "")
    assert checks[0].level == "ok"


def test_verb_forms(dictionary):
    good = Draft(kind="verb", lemma="gehen", present="geht", preterite="ging", perfect="ist gegangen")
    assert levels(german.check(good, dictionary)) == ["ok"]
    bad = Draft(kind="verb", lemma="gehen", present="geht", preterite="gehte", perfect="hat gegangen")
    checks = german.check(bad, dictionary)
    assert (bad.preterite, bad.perfect) == ("ging", "ist gegangen")  # corrected in place
    assert levels(checks) == ["warn", "warn"]


def test_duplicate_query_covers_existing_note_types():
    q = german.duplicate_query("Rechnung")
    for term in ['"Wort_DE:Rechnung"', '"base_d:Rechnung"', '"de_word:d__ Rechnung,*"', '"Wort:Rechnung"']:
        assert term in q
    assert german.duplicate_query('a"b*') .count('a\\"b\\*') > 0


def test_note_fields_follow_note_type_order():
    d = Draft(kind="noun", lemma="Tür", article="die", plural="Türen", meaning="door",
              examples=[german.Example(de="Die <b>Tür</b> ist zu.", en="The door is closed.")])
    fields = german.note_fields(d, {"Audio_Wort": "acg-1.mp3"})
    names = german.NOTETYPES["noun"]["fields"]
    assert len(fields) == len(names)
    row = dict(zip(names, fields))
    assert row["Wort"] == "Tür" and row["Artikel"] == "die" and row["Audio_Wort"] == "[sound:acg-1.mp3]"
    assert row["Beispiel2"] == "" and row["Audio_Beispiel1"] == ""
    assert german.speech_texts(d) == {"Audio_Wort": "die Tür", "Audio_Beispiel1": "Die Tür ist zu."}


def test_templates_only_use_existing_fields():
    import re
    for nt in german.NOTETYPES.values():
        used = set()
        for t in nt["templates"]:
            used |= set(re.findall(r"\{\{[#/^]?(?:text:)?([^}#/^:]+?)\}\}", t["front"] + t["back"]))
        assert used - {"FrontSide"} <= set(nt["fields"]), nt["name"]


def test_dictionary_links_only_on_the_answer_side():
    for kind in ("noun", "verb", "word"):
        for t in german.NOTETYPES[kind]["templates"]:
            assert 'class="links"' in t["back"] and f'data-kind="{kind}"' in t["back"], t["name"]
            assert "links" not in t["front"], t["name"]  # it would give the answer away
    assert 'data-w="{{text:Infinitiv}}"' in german.NOTETYPES["verb"]["templates"][0]["back"]


def test_verb_with_two_conjugations_keeps_the_one_it_matches():
    class TwoConjugations:
        state = "ready"

        def verbs(self, word):
            return [Verb("schaffen", "schafft", "schuf", "geschaffen", ("haben",)),
                    Verb("schaffen", "schafft", "schaffte", "geschafft", ("haben",))]

    d = Draft(kind="verb", lemma="schaffen", present="schafft", preterite="schaffte", perfect="hat geschafft")
    assert levels(german.check(d, TwoConjugations())) == ["ok"]
    assert (d.preterite, d.perfect) == ("schaffte", "hat geschafft")


def test_reflexive_verb_keeps_sich():
    class Erinnern:
        state = "ready"

        def verbs(self, word):
            return [Verb("erinnern", "erinnert", "erinnerte", "erinnert", ("haben",))]

    ok = Draft(kind="verb", lemma="sich erinnern", present="erinnert sich", preterite="erinnerte sich",
               perfect="hat sich erinnert")
    assert levels(german.check(ok, Erinnern())) == ["ok"]
    bad = Draft(kind="verb", lemma="sich erinnern", present="erinnert sich", preterite="erinnert sich",
                perfect="hat erinnert")
    german.check(bad, Erinnern())
    assert (bad.preterite, bad.perfect) == ("erinnerte sich", "hat sich erinnert")
