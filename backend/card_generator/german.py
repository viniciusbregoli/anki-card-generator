"""German: note types, the model prompt, and checks against Wiktionary and suffix rules."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import tagging
from .dictionary import ARTICLES, PLURAL_ONLY, Dictionary

Language = Literal["de", "es"]
Kind = Literal["noun", "verb", "word", "phrase"]
Level = Literal["ok", "warn", "info"]
GENDER_OF = {"der": "m", "die": "f", "das": "n"}
GENDER_NAME = {"m": "masculine", "f": "feminine", "n": "neuter"}


# -- draft -----------------------------------------------------------------------


class Example(BaseModel):
    """The legacy de key holds the sentence in the draft's language."""

    de: str
    en: str


class Draft(BaseModel):
    """One card's content, as the model proposed it and the user edited it."""

    kind: Kind
    language: Language = "de"
    lemma: str = Field(min_length=1)
    article: Literal["der", "die", "das", "el", "la", "los", "las", ""] = ""
    plural: str = ""
    part_of_speech: str = ""
    meaning: str = ""
    gender_rule: str = ""
    present: str = ""
    preterite: str = ""
    perfect: str = ""
    governs: str = ""
    examples: list[Example] = []
    note: str = ""
    source: str = ""  # the sentence where the user met the word
    tags: list[str] = []  # level::… and topic::…

    @model_validator(mode="after")
    def article_matches_language(self) -> Draft:
        articles = {"de": {"der", "die", "das"}, "es": {"el", "la", "los", "las"}}
        if self.article and self.article not in articles[self.language]:
            raise ValueError("The article does not belong to the draft language.")
        return self


class Check(BaseModel):
    level: Level
    message: str


# -- model prompt ------------------------------------------------------------------

SYSTEM_PROMPT = """\
You write German flashcards for an adult learner (native Brazilian Portuguese, fluent \
English, German level A2-B1). Card text that explains German is written in English.

The user gives a German word, expression or sentence, sometimes with the sentence \
where they met it. Decide what card to make:
- "noun": a single noun. lemma = nominative singular, capitalised ("Rechnung"). If the \
user typed a plural or inflected form, use the singular and say so in input_note.
- "verb": lemma = infinitive, with "sich" for reflexive verbs ("sich freuen"), separable \
verbs written joined ("anfangen").
- "word": any other single word (adjective, adverb, preposition, conjunction, ...). \
lemma = base form. part_of_speech names it in English.
- "phrase": an idiom, fixed expression or whole sentence worth learning as a chunk. \
lemma = the corrected German phrase. meaning = a natural English equivalent.
Fix spelling mistakes in the input and mention the fix in input_note. Otherwise \
input_note is "".

Fields (use "" for anything that does not apply to the kind):
- article: der/die/das, nouns only. Be careful: this is the most important field.
- plural: nouns only, the plural form without article ("Rechnungen"); "" if the noun \
has no plural.
- meaning: concise English, at most three senses separated by "; ", most common \
first. If a context sentence is given, put the sense used there first.
- gender_rule: nouns only. One short English sentence giving a rule that predicts \
this noun's gender (a suffix, or a meaning group such as days, months, seasons, \
car brands, nominalised infinitives, metals), or explaining why it is an exception \
to a well-known rule. "" if no real rule applies. Never invent a rule.
- present / preterite / perfect: verbs only, third person singular ("wartet", \
"wartete", "hat gewartet").
- governs: verbs only, case or preposition the verb takes, in German notation \
("auf + Akk.", "+ Dat."). "" if none worth noting.
- examples: for noun, verb and word ALWAYS exactly two short, natural, everyday \
sentences (at most 12 words, A2-B1), each with an English translation. Wrap the target \
word (in whatever form it takes in the sentence) in <b></b>. A context sentence does \
not replace them: write two new ones that differ from it. For phrase, an empty list.
- note: one short, useful usage note (register, false friend, typical collocation, \
irregularity), or "".
""" + tagging.prompt_text()

SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind", "lemma", "article", "plural", "part_of_speech", "meaning", "gender_rule",
        "present", "preterite", "perfect", "governs", "examples", "note", "input_note", "level", "topic",
    ],
    "properties": {
        "kind": {"type": "string", "enum": ["noun", "verb", "word", "phrase"]},
        "lemma": {"type": "string"},
        "article": {"type": "string", "enum": ["der", "die", "das", ""]},
        "plural": {"type": "string"},
        "part_of_speech": {"type": "string"},
        "meaning": {"type": "string"},
        "gender_rule": {"type": "string"},
        "present": {"type": "string"},
        "preterite": {"type": "string"},
        "perfect": {"type": "string"},
        "governs": {"type": "string"},
        "examples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["de", "en"],
                "properties": {"de": {"type": "string"}, "en": {"type": "string"}},
            },
        },
        "note": {"type": "string"},
        "input_note": {"type": "string"},
        "level": {"type": "string", "enum": list(tagging.LEVELS)},
        "topic": {"type": "string", "enum": list(tagging.TOPICS)},
    },
}


REVIEW_PROMPT = """\
You are a native German speaker and an experienced German teacher. You check a flashcard \
draft written for an adult learner (native Brazilian Portuguese, fluent English, A2-B1) \
before it is saved. Check strictly:
- lemma: the right dictionary form (e.g. "alle" for the plural determiner, not "all").
- meaning: accurate concise English, most common sense first, at most three senses.
- examples (not for phrases): each German sentence must be grammatically correct, natural \
everyday German (at most 12 words) and must use the target word itself in its usual \
sense, not a compound, a different separable verb or a fixed phrase where it loses its \
meaning ("wiederholen" does not illustrate "wieder", "fernsehen" does not illustrate \
"sehen"). The <b></b> tags wrap exactly the target word's form, nothing more, in both \
sentences. The English translates the German faithfully and naturally. If there are \
fewer than two examples, write them.
- note: correct and useful, or "".
Keep the lemma the learner asked for when it is a real dictionary entry: "möchten" stays \
"möchten" (not "mögen"), "später" stays "später" (not "spät"). Only fix misspellings and \
non-dictionary forms.
examples always holds exactly two items for nouns, verbs and words (the full corrected \
sentences, not a description of them).
Return the corrected fields (unchanged where they were fine) and, in changes, one short \
English line per fix. If nothing needed fixing, changes is an empty list.
"""

REVIEW_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lemma", "meaning", "examples", "note", "changes"],
    "properties": {
        "lemma": {"type": "string"},
        "meaning": {"type": "string"},
        "examples": SCHEMA["properties"]["examples"],
        "note": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}},
    },
}


def review_message(draft: Draft, hint: str = "") -> str:
    fields = {"kind": draft.kind, "lemma": draft.lemma, "article": draft.article,
              "part_of_speech": draft.part_of_speech, "meaning": draft.meaning,
              "examples": [e.model_dump() for e in draft.examples], "note": draft.note}
    if hint.strip():
        fields["intended_sense"] = hint.strip()
    return json.dumps(fields, ensure_ascii=False)


def apply_review(draft: Draft, data: dict) -> list[str]:
    """Takes the reviewer's corrections into the draft; returns what it changed."""
    draft.lemma = data["lemma"].strip() or draft.lemma
    draft.meaning = data["meaning"].strip() or draft.meaning
    draft.note = data["note"].strip()
    if draft.kind != "phrase" and len(data["examples"]) >= 2:
        draft.examples = [Example(**e) for e in data["examples"]][:2]
    return [c.strip() for c in data["changes"] if c.strip()]


def user_message(text: str, context: str = "", kind: Kind | None = None, hint: str = "") -> str:
    parts = [f"Input: {text.strip()}"]
    if context.strip():
        parts.append(f"Context sentence: {context.strip()}")
    if hint.strip():
        parts.append(f"Intended sense: {hint.strip()}")
    if kind:
        parts.append(f'Make a "{kind}" card.')
    return "\n".join(parts)


def draft_from_model(data: dict, source: str = "", *, language: Language = "de") -> tuple[Draft, str]:
    """Model JSON -> Draft, plus the model's note about how it read the input."""
    kind = data["kind"]
    draft = Draft(
        kind=kind,
        language=language,
        lemma=data["lemma"].strip(),
        article=data["article"] if kind == "noun" else "",
        plural=data["plural"].strip() if kind == "noun" else "",
        part_of_speech=data["part_of_speech"].strip() if kind == "word" else "",
        meaning=data["meaning"].strip(),
        gender_rule=data["gender_rule"].strip() if kind == "noun" else "",
        present=data["present"].strip() if kind == "verb" else "",
        preterite=data["preterite"].strip() if kind == "verb" else "",
        perfect=data["perfect"].strip() if kind == "verb" else "",
        governs=data["governs"].strip() if kind == "verb" else "",
        examples=[Example(**e) for e in data["examples"]][:3] if kind != "phrase" else [],
        note=data["note"].strip(),
        source=source.strip(),
        tags=tagging.tags(data.get("level", ""), data.get("topic", "")),
    )
    return draft, data.get("input_note", "").strip()


# -- gender rules ------------------------------------------------------------------

# (suffix, gender, always?) — longest suffix wins. "Always" rules have no common
# exceptions; the others are strong tendencies, so a mismatch is reported as an
# exception rather than corrected.
SUFFIX_RULES: list[tuple[str, str, bool]] = sorted(
    [
        ("ung", "f", True), ("heit", "f", True), ("keit", "f", True), ("schaft", "f", True),
        ("tät", "f", True), ("ion", "f", False), ("enz", "f", False), ("anz", "f", False),
        ("ik", "f", False), ("ei", "f", False), ("ie", "f", False), ("e", "f", False),
        ("chen", "n", True), ("lein", "n", True), ("ment", "n", False), ("tum", "n", False),
        ("ismus", "m", True), ("ling", "m", False), ("ist", "m", False), ("or", "m", False),
        ("ig", "m", False), ("eur", "m", False), ("ant", "m", False),
    ],
    key=lambda r: -len(r[0]),
)


def suffix_rule(word: str) -> tuple[str, str, bool] | None:
    lower = word.lower()
    for suffix, gender, always in SUFFIX_RULES:
        # The word must be clearly longer than the suffix: "Ei" is not an "-ei" noun.
        if lower.endswith(suffix) and len(lower) >= len(suffix) + 3:
            return suffix, gender, always
    return None


def _suffix_text(suffix: str, gender: str, always: bool) -> str:
    quantifier = "always" if always else "usually"
    extra = " (diminutives)" if suffix in ("chen", "lein") else ""
    return f"Nouns ending in -{suffix} are {quantifier} {GENDER_NAME[gender]}{extra}."


def check_noun(draft: Draft, dictionary: Dictionary) -> list[Check]:
    """Verify gender and plural; corrects the draft in place when Wiktionary is unambiguous."""
    checks: list[Check] = []
    word = draft.lemma
    entries = dictionary.nouns(word)
    genders = list(dict.fromkeys(e.gender for e in entries))

    if genders == [PLURAL_ONLY]:
        draft.article, draft.plural = "die", ""
        checks.append(Check(level="ok", message=f"Plural-only noun in Wiktionary: always die {word}."))
        return checks
    genders = [g for g in genders if g != PLURAL_ONLY]
    entries = [e for e in entries if e.gender != PLURAL_ONLY]

    if not draft.article:
        checks.append(Check(level="warn", message="No article. Pick der, die or das."))
    elif genders:
        model_g = GENDER_OF[draft.article]
        if model_g in genders:
            checks.append(Check(level="ok", message=f"Gender confirmed by Wiktionary: {draft.article} {word}."))
        elif len(genders) == 1:
            correct = ARTICLES[genders[0]]
            checks.append(Check(
                level="warn",
                message=f"The model said “{draft.article}”, Wiktionary says “{correct}”. Changed to {correct}.",
            ))
            draft.article = correct
        else:
            options = ", ".join(f"{e.article} {word} ({e.gloss})" for e in entries)
            checks.append(Check(level="warn", message=f"Wiktionary has several genders: {options}. Check which one you mean."))
        if draft.article in (ARTICLES[g] for g in genders):
            for e in entries:
                if e.article != draft.article:
                    checks.append(Check(level="info", message=f"Wiktionary also lists {e.article} {word}: {e.gloss}."))
    elif dictionary.state == "ready" and not dictionary.compound_head(word):
        checks.append(Check(level="info", message="Not in Wiktionary, so the gender is unverified."))
    elif dictionary.state == "ready":
        pass  # an unknown compound: judged by its last part in _set_gender_rule
    else:
        checks.append(Check(level="info", message="The dictionary isn't ready yet, so the gender is unverified."))

    # Plural: only compare against entries with the gender we ended up with.
    same = [e for e in entries if e.article == draft.article]
    plurals = list(dict.fromkeys(p for e in same for p in e.plurals))
    named = set(re.findall(r"[^\W\d_]+", draft.plural))  # "Banken (money); Bänke (seat)"
    if same and plurals and not draft.plural:
        # Mass nouns (Musik, Blut) have rare plurals in Wiktionary; "none" is the useful answer.
        checks.append(Check(level="info", message=f"Wiktionary also lists the plural “{plurals[0]}”."))
    elif same and plurals and draft.plural not in plurals and not named & set(plurals):
        old = draft.plural
        draft.plural = plurals[0]
        checks.append(Check(level="warn", message=f"Plural changed from “{old}” to “{plurals[0]}” (Wiktionary)."))
    elif same and plurals and len(plurals) > 1:
        checks.append(Check(level="info", message=f"Other plural forms: {', '.join(p for p in plurals if p != draft.plural)}."))
    elif same and not plurals and draft.plural:
        checks.append(Check(level="info", message="Wiktionary lists no plural for this noun."))

    if draft.article:
        _set_gender_rule(draft, dictionary, bool(entries), checks)
    return checks


def _set_gender_rule(draft: Draft, dictionary: Dictionary, known: bool, checks: list[Check]) -> None:
    gender = GENDER_OF[draft.article]
    rule = suffix_rule(draft.lemma)
    if rule:
        suffix, rule_gender, always = rule
        if rule_gender == gender:
            draft.gender_rule = _suffix_text(suffix, rule_gender, always)
            return
        exception = (
            f"Exception: nouns ending in -{suffix} are usually {GENDER_NAME[rule_gender]}, "
            f"but it's {draft.article} {draft.lemma}."
        )
        model_rule = draft.gender_rule if draft.gender_rule and "exception" not in draft.gender_rule.lower() else ""
        draft.gender_rule = f"{exception} {model_rule}".strip()
        return

    found = dictionary.compound_head(draft.lemma)
    if found:
        head, head_entries = found
        head_genders = {e.gender for e in head_entries}
        if gender in head_genders:
            if not draft.gender_rule:
                draft.gender_rule = (
                    f"Compound noun: it takes the gender of its last part, {ARTICLES[gender]} {head}."
                )
            if not known:
                checks.append(Check(
                    level="ok",
                    message=f"Not in Wiktionary, but its last part is {ARTICLES[gender]} {head}, "
                            f"and compounds take that gender.",
                ))
        elif not known:
            head_article = " / ".join(ARTICLES[g] for g in sorted(head_genders))
            checks.append(Check(
                level="warn",
                message=f"Compounds take the gender of their last part, and {head_article} {head} "
                        f"suggests “{head_article}”, not “{draft.article}”. Check this one.",
            ))


def _verb_mismatches(draft: Draft, verb) -> dict[str, str]:
    """Field -> Wiktionary's value, for each verb form of the draft that differs from `verb`.

    Reflexive verbs keep their "sich": "erinnert sich", "hat sich erinnert".
    """
    reflexive = draft.lemma.startswith("sich ")
    unsich = lambda form: re.sub(r"\bsich\b\s*", "", form).strip()  # noqa: E731
    lacks_sich = lambda form: reflexive and not re.search(r"\bsich\b", form)  # noqa: E731
    out: dict[str, str] = {}
    if verb.present and (unsich(draft.present) != verb.present or lacks_sich(draft.present)):
        out["present"] = f"{verb.present} sich" if reflexive else verb.present
    if verb.preterite and (unsich(draft.preterite) != verb.preterite or lacks_sich(draft.preterite)):
        out["preterite"] = f"{verb.preterite} sich" if reflexive else verb.preterite
    if verb.participle:
        aux_word, _, participle = unsich(draft.perfect).partition(" ")
        aux = {"hat": "haben", "ist": "sein"}.get(aux_word)
        if (participle.strip() != verb.participle or (verb.auxiliaries and aux not in verb.auxiliaries)
                or lacks_sich(draft.perfect)):
            if aux not in verb.auxiliaries:
                aux = verb.auxiliaries[0] if verb.auxiliaries else "haben"
            out["perfect"] = f"{'hat' if aux == 'haben' else 'ist'} {'sich ' if reflexive else ''}{verb.participle}"
    return out


def check_verb(draft: Draft, dictionary: Dictionary) -> list[Check]:
    """Verify the verb forms; like nouns, corrects the draft in place from Wiktionary.

    Some verbs have two conjugations (schaffen: schuf "create" / schaffte "manage"), so the
    draft is compared with the one it matches best and only corrected where that differs.
    """
    base = draft.lemma.removeprefix("sich ").strip()
    verbs = dictionary.verbs(base)
    if not verbs:
        if dictionary.state == "ready":
            return [Check(level="info", message="Not in Wiktionary, so the verb forms are unverified.")]
        return []
    verb, fixes = min(((v, _verb_mismatches(draft, v)) for v in verbs), key=lambda vf: len(vf[1]))
    labels = {"present": "Present", "preterite": "Preterite", "perfect": "Perfect"}
    checks: list[Check] = []
    for field, value in fixes.items():
        old = getattr(draft, field) or "none"
        setattr(draft, field, value)
        checks.append(Check(level="warn", message=f"{labels[field]} changed from “{old}” to “{value}” (Wiktionary)."))
    if "perfect" in fixes and len(verb.auxiliaries) > 1:
        checks.append(Check(level="info", message="Wiktionary allows both haben and sein in the perfect."))
    if not checks:
        checks.append(Check(level="ok", message="Verb forms match Wiktionary."))
    return checks


def check(draft: Draft, dictionary: Dictionary) -> list[Check]:
    if draft.kind == "noun":
        return check_noun(draft, dictionary)
    if draft.kind == "verb":
        return check_verb(draft, dictionary)
    return []


# -- duplicates --------------------------------------------------------------------

# Headword fields of this app's note types and of the existing Goethe note types.
EXACT_FIELDS = ["Wort", "Infinitiv", "Satz", "Wort_DE", "base_d"]
# Fields like "die Ansage, -n" or "gelten, gilt, galt, hat gegolten".
LOOSE_FIELDS = ["de_word", "full_d"]


def _escape(value: str) -> str:
    return re.sub(r'([\\"*_])', r"\\\1", value)


def duplicate_query(lemma: str) -> str:
    v = _escape(lemma.strip())
    terms = [f'"{f}:{v}"' for f in EXACT_FIELDS]
    for f in LOOSE_FIELDS:
        terms += [f'"{f}:{v}"', f'"{f}:{v},*"', f'"{f}:d__ {v}"', f'"{f}:d__ {v},*"']
    return "(" + " OR ".join(terms) + ")"


# -- note types ----------------------------------------------------------------------

CSS = """\
.card {
  font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  font-size: 20px; line-height: 1.45; text-align: center;
  color: #18181b; background: #ffffff;
}
.card.nightMode { color: #e4e4e7; background: #18181b; }
.de { font-size: 1.6em; font-weight: 600; }
.g-der { color: #2563eb; } .g-die { color: #dc2626; } .g-das { color: #16a34a; }
.nightMode .g-der { color: #60a5fa; } .nightMode .g-die { color: #f87171; } .nightMode .g-das { color: #4ade80; }
.blank { color: #a1a1aa; }
.meaning { font-size: 1.15em; margin-top: .3em; }
.sub { color: #71717a; font-size: .85em; margin-top: .3em; }
.hint { color: #a1a1aa; font-size: .8em; margin-top: .5em; }
.rule { margin: 1em auto 0; max-width: 32em; font-size: .8em; padding: .6em .9em;
  border-radius: 8px; background: #f4f4f5; }
.nightMode .rule { background: #27272a; }
.examples { margin: 1.2em auto 0; max-width: 32em; text-align: left; font-size: .85em; }
.ex { margin: .7em 0; }
.ex .en, .note, .source { color: #71717a; font-size: .9em; }
.note, .source { margin: 1em auto 0; max-width: 32em; font-size: .75em; }
.source { font-style: italic; }
.links { margin: 1.2em auto 0; font-size: .75em; color: #a1a1aa; }
.links a { color: #2563eb; text-decoration: none; }
.nightMode .links a { color: #60a5fa; }
"""

_EXAMPLES = """\
<div class="examples">
{{#Beispiel1}}<div class="ex"><div>{{Beispiel1}} {{Audio_Beispiel1}}</div><div class="en">{{Beispiel1_EN}}</div></div>{{/Beispiel1}}
{{#Beispiel2}}<div class="ex"><div>{{Beispiel2}} {{Audio_Beispiel2}}</div><div class="en">{{Beispiel2_EN}}</div></div>{{/Beispiel2}}
</div>
{{#Notiz}}<div class="note">{{Notiz}}</div>{{/Notiz}}
{{#Quelle}}<div class="source">“{{Quelle}}”</div>{{/Quelle}}"""

_EXAMPLE_FIELDS = ["Beispiel1", "Beispiel1_EN", "Beispiel2", "Beispiel2_EN", "Notiz", "Quelle"]
_AUDIO_FIELDS = ["Audio_Wort", "Audio_Beispiel1", "Audio_Beispiel2"]

_NOUN_WORD = '<div class="de g-{{Artikel}}">{{Artikel}} {{Wort}}</div>'
_NOUN_PLURAL = '{{#Plural}}<div class="sub">Pl. die {{Plural}}</div>{{/Plural}}'
_NOUN_RULE = '{{#Genusregel}}<div class="rule">{{Genusregel}}</div>{{/Genusregel}}'

# Dictionary links on the answer side. The script builds them from the headword: it drops a
# reflexive "sich" where a site wants the bare verb and URL-encodes umlauts and spaces.
_LINKS_SCRIPT = """\
<script>
(function () {
  var vf = "https://www.verbformen.com/", enc = encodeURIComponent;
  document.querySelectorAll(".links[data-w]").forEach(function (el) {
    var full = el.getAttribute("data-w").trim(), w = full.replace(/^sich /, "");
    var kind = el.getAttribute("data-kind"), pos = el.getAttribute("data-pos") || "";
    if (!full || el.childElementCount) return;
    var links = [["Wiktionary", "https://en.wiktionary.org/wiki/" + enc(w.replace(/ /g, "_")) + "#German"]];
    if (kind === "verb") links.push(["Conjugation", vf + "conjugation/?w=" + enc(full)]);
    if (kind === "noun") links.push(["Declension", vf + "declension/nouns/?w=" + enc(w)]);
    if (kind === "word" && /adjecti/i.test(pos)) links.push(["Declension", vf + "declension/adjectives/?w=" + enc(w)]);
    links.push(["dict.cc", "https://www.dict.cc/?s=" + enc(full)]);
    el.innerHTML = links.map(function (l) { return '<a href="' + l[1] + '">' + l[0] + "</a>"; }).join(" · ");
  });
})();
</script>"""


def _links(field: str, kind: str, pos: str = "") -> str:
    attrs = f'data-w="{{{{text:{field}}}}}" data-kind="{kind}"' + (f' data-pos="{{{{text:{pos}}}}}"' if pos else "")
    return f'<div class="links" {attrs}></div>{_LINKS_SCRIPT}'


_NOUN_LINKS = _links("Wort", "noun")
_VERB_LINKS = _links("Infinitiv", "verb")
_WORD_LINKS = _links("Wort", "word", "Wortart")

_VERB_FORMS = (
    '<div class="sub">{{Praesens}} · {{Praeteritum}} · {{Perfekt}}</div>'
    '{{#Rektion}}<div class="sub">{{Rektion}}</div>{{/Rektion}}'
)

NOTETYPES: dict[Kind, dict] = {
    "noun": {
        "name": "DE Noun",
        "fields": ["Wort", "Artikel", "Plural", "Bedeutung", "Genusregel", *_EXAMPLE_FIELDS, *_AUDIO_FIELDS],
        "templates": [
            {
                "name": "Deutsch → English",
                "front": f"{_NOUN_WORD}{{{{Audio_Wort}}}}",
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="meaning">{{{{Bedeutung}}}}</div>'
                        f"{_NOUN_PLURAL}{_NOUN_RULE}{_EXAMPLES}{_NOUN_LINKS}",
            },
            {
                "name": "English → Deutsch",
                "front": '<div class="meaning">{{Bedeutung}}</div><div class="hint">noun, with article</div>',
                "back": f'{{{{FrontSide}}}}<hr id="answer">{_NOUN_WORD}{{{{Audio_Wort}}}}{_NOUN_PLURAL}'
                        f"{_NOUN_RULE}{_EXAMPLES}{_NOUN_LINKS}",
            },
            {
                "name": "Genus",
                "front": '<div class="de"><span class="blank">___</span> {{Wort}}</div>'
                         '<div class="hint">der, die or das?</div>',
                "back": f'{_NOUN_WORD}{{{{Audio_Wort}}}}{_NOUN_RULE}<div class="sub">{{{{Bedeutung}}}}</div>{_NOUN_LINKS}',
            },
        ],
    },
    "verb": {
        "name": "DE Verb",
        "fields": ["Infinitiv", "Bedeutung", "Praesens", "Praeteritum", "Perfekt", "Rektion",
                   *_EXAMPLE_FIELDS, *_AUDIO_FIELDS],
        "templates": [
            {
                "name": "Deutsch → English",
                "front": '<div class="de">{{Infinitiv}}</div>{{Audio_Wort}}',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="meaning">{{{{Bedeutung}}}}</div>'
                        f"{_VERB_FORMS}{_EXAMPLES}{_VERB_LINKS}",
            },
            {
                "name": "English → Deutsch",
                "front": '<div class="meaning">{{Bedeutung}}</div><div class="hint">verb</div>',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="de">{{{{Infinitiv}}}}</div>'
                        f"{{{{Audio_Wort}}}}{_VERB_FORMS}{_EXAMPLES}{_VERB_LINKS}",
            },
        ],
    },
    "word": {
        "name": "DE Word",
        "fields": ["Wort", "Wortart", "Bedeutung", *_EXAMPLE_FIELDS, *_AUDIO_FIELDS],
        "templates": [
            {
                "name": "Deutsch → English",
                "front": '<div class="de">{{Wort}}</div>{{Audio_Wort}}',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="meaning">{{{{Bedeutung}}}}</div>'
                        f'<div class="sub">{{{{Wortart}}}}</div>{_EXAMPLES}{_WORD_LINKS}',
            },
            {
                "name": "English → Deutsch",
                "front": '<div class="meaning">{{Bedeutung}}</div><div class="hint">{{Wortart}}</div>',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="de">{{{{Wort}}}}</div>'
                        f"{{{{Audio_Wort}}}}{_EXAMPLES}{_WORD_LINKS}",
            },
        ],
    },
    "phrase": {
        "name": "DE Phrase",
        "fields": ["Satz", "Bedeutung", "Notiz", "Quelle", "Audio"],
        "templates": [
            {
                "name": "Deutsch → English",
                "front": '<div class="de">{{Satz}}</div>{{Audio}}',
                "back": '{{FrontSide}}<hr id="answer"><div class="meaning">{{Bedeutung}}</div>'
                        '{{#Notiz}}<div class="note">{{Notiz}}</div>{{/Notiz}}',
            },
            {
                "name": "English → Deutsch",
                "front": '<div class="meaning">{{Bedeutung}}</div><div class="hint">say it in German</div>',
                "back": '{{FrontSide}}<hr id="answer"><div class="de">{{Satz}}</div>{{Audio}}'
                        '{{#Notiz}}<div class="note">{{Notiz}}</div>{{/Notiz}}',
            },
            {
                # Only generated when there is audio: an empty front means no card.
                "name": "Hören",
                "front": '{{#Audio}}<div class="hint">Listen. What does it mean?</div>{{Audio}}{{/Audio}}',
                "back": '{{FrontSide}}<hr id="answer"><div class="de">{{Satz}}</div>'
                        '<div class="meaning">{{Bedeutung}}</div>',
            },
        ],
    },
}
for _nt in NOTETYPES.values():
    _nt["css"] = CSS


# -- draft -> note -------------------------------------------------------------------


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def speech_texts(draft: Draft) -> dict[str, str]:
    """Audio field -> text to speak."""
    if draft.kind == "phrase":
        return {"Audio": strip_html(draft.lemma)}
    head = f"{draft.article} {draft.lemma}" if draft.kind == "noun" and draft.article else draft.lemma
    out = {"Audio_Wort": strip_html(head)}
    for i, ex in enumerate(draft.examples[:2], start=1):
        if ex.de.strip():
            out[f"Audio_Beispiel{i}"] = strip_html(ex.de)
    return out


def note_fields(draft: Draft, audio: dict[str, str]) -> list[str]:
    """Field values in note type order. `audio` maps audio field -> media filename."""
    ex = draft.examples + [Example(de="", en="")] * 2
    values: dict[str, str] = {
        "Bedeutung": draft.meaning,
        "Beispiel1": ex[0].de, "Beispiel1_EN": ex[0].en,
        "Beispiel2": ex[1].de, "Beispiel2_EN": ex[1].en,
        "Notiz": draft.note,
        "Quelle": draft.source,
        **{field: f"[sound:{name}]" for field, name in audio.items()},
    }
    match draft.kind:
        case "noun":
            values |= {"Wort": draft.lemma, "Artikel": draft.article, "Plural": draft.plural,
                       "Genusregel": draft.gender_rule}
        case "verb":
            values |= {"Infinitiv": draft.lemma, "Praesens": draft.present, "Praeteritum": draft.preterite,
                       "Perfekt": draft.perfect, "Rektion": draft.governs}
        case "word":
            values |= {"Wort": draft.lemma, "Wortart": draft.part_of_speech}
        case "phrase":
            values |= {"Satz": draft.lemma}
    return [values.get(name, "") for name in NOTETYPES[draft.kind]["fields"]]
