"""Spanish: note types, model prompts, and checks against Wiktionary."""

from __future__ import annotations

import re

from . import german, tagging
from .dictionary import PLURAL_ONLY, Dictionary, Noun, Verb, _forms, _is_form_of

SOURCE_URL = "https://kaikki.org/dictionary/Spanish/kaikki.org-dictionary-Spanish.jsonl"
SCHEMA_VERSION = 2

GENDER_OF = {"el": "m", "la": "f"}
GENDER_NAME = {"m": "masculine", "f": "feminine"}
ARTICLES = {"m": "el", "f": "la", "m-p": "los", "f-p": "las"}
GENDER_TAGS = {"masculine": "m", "feminine": "f"}


# -- Kaikki parsing ---------------------------------------------------------------


def _genders(entry: dict) -> list[str]:
    senses = entry.get("senses", [])
    plural_only = any("plural-only" in sense.get("tags", []) for sense in senses)
    found: list[str] = []
    for sense in senses:
        for tag in sense.get("tags", []):
            gender = GENDER_TAGS.get(tag)
            if gender and gender not in found:
                found.append(gender)
    if not found:
        for head in entry.get("head_templates", []):
            words = head.get("expansion", "").split("(")[0].split()
            for word in words[1:]:
                if word in ("m", "f") and word not in found:
                    found.append(word)
    if plural_only:
        return [f"{gender}-p" for gender in found] or [PLURAL_ONLY]
    return found


def parse_noun(entry: dict) -> list[Noun]:
    if entry.get("pos") != "noun" or _is_form_of(entry):
        return []
    gloss = next((sense["glosses"][0] for sense in entry.get("senses", []) if sense.get("glosses")), "")
    plurals = tuple(_forms(entry, {"plural"}))
    return [Noun(entry["word"], gender, plurals, gloss[:120]) for gender in _genders(entry)]


def parse_verb(entry: dict) -> Verb | None:
    if entry.get("pos") != "verb" or _is_form_of(entry):
        return None
    present = _forms(entry, {"indicative", "present", "singular", "third-person"})
    preterite = _forms(entry, {"indicative", "preterite", "singular", "third-person"})
    participle = _forms(entry, {"participle", "past"})
    participle += [form for form in _forms(entry, {"masculine", "participle", "past", "singular"})
                   if form not in participle]
    if not (present or preterite or participle):
        return None
    first = lambda values: values[0] if values else ""  # noqa: E731
    return Verb(entry["word"], first(present), first(preterite), first(participle),
                ("haber",) if participle else ())


# -- model prompt -----------------------------------------------------------------


SYSTEM_PROMPT = """\
You write Spanish flashcards for an adult learner (native Brazilian Portuguese, fluent \
English, Spanish level A2-B1). Card text that explains Spanish is written in English.

The user gives a Spanish word, expression or sentence, sometimes with the sentence \
where they met it. Decide what card to make:
- "noun": a single noun. lemma = singular ("casa"). For a plural-only noun, keep the \
plural lemma ("tijeras"). If the user typed an inflected form, use the lemma and say so \
in input_note.
- "verb": lemma = infinitive. Reflexive infinitives end in "se" ("levantarse").
- "word": any other single word (adjective, adverb, preposition, conjunction, ...). \
lemma = base form. part_of_speech names it in English.
- "phrase": an idiom, fixed expression or whole sentence worth learning as a chunk. \
lemma = the corrected Spanish phrase. meaning = a natural English equivalent.
Fix spelling mistakes in the input and mention the fix in input_note. Otherwise \
input_note is "".

Fields (use "" for anything that does not apply to the kind):
- article: el/la for singular nouns, los/las for plural-only nouns. Be careful: this is \
the most important field. Feminine nouns beginning with a stressed a/ha take singular \
el ("el agua") but remain feminine; explain that in gender_rule instead of calling them \
masculine. Their plural uses las ("las aguas").
- plural: singular nouns only, the plural form without article ("casas"); "" for \
plural-only nouns and nouns with no plural.
- meaning: concise English, at most three senses separated by "; ", most common \
first. If a context sentence is given, put the sense used there first.
- gender_rule: nouns only. One short English sentence giving a useful gender or article \
rule, including the stressed a/ha rule where relevant. "" if no real rule applies. \
Never invent a rule.
- present / preterite / perfect: verbs only, third person singular ("habla", "habló", \
"ha hablado"). For reflexive verbs, all three begin with "se " ("se levanta", \
"se levantó", "se ha levantado"). The perfect always uses haber.
- governs: verbs only, a preposition or construction worth noting ("a + person", \
"de + noun"). "" if none worth noting.
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
        **german.SCHEMA["properties"],
        "article": {"type": "string", "enum": ["el", "la", "los", "las", ""]},
    },
}

REVIEW_PROMPT = """\
You are a native Spanish speaker and an experienced Spanish teacher. You check a flashcard \
draft written for an adult learner (native Brazilian Portuguese, fluent English, A2-B1) \
before it is saved. Check strictly:
- lemma: the right dictionary form. Reflexive infinitives end in "se".
- meaning: accurate concise English, most common sense first, at most three senses.
- examples (not for phrases): each Spanish sentence must be grammatically correct, natural \
everyday Spanish (at most 12 words) and must use the target word itself in its usual \
sense, not a compound or a fixed phrase where it loses its meaning. The <b></b> tags wrap \
exactly the target word's form, nothing more, in both sentences. The English translates \
the Spanish faithfully and naturally. If there are fewer than two examples, write them.
- note: correct and useful, or "".
Keep the lemma the learner asked for when it is a real dictionary entry. Only fix \
misspellings and non-dictionary forms.
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

user_message = german.user_message
review_message = german.review_message
apply_review = german.apply_review


def draft_from_model(data: dict, source: str = "") -> tuple[german.Draft, str]:
    """Model JSON -> Spanish Draft, plus the model's note about how it read the input."""
    return german.draft_from_model(data, source, language="es")


# -- checks -----------------------------------------------------------------------


_FEMININE_EL_WORDS = {
    "acta", "agua", "águila", "ala", "alma", "alta", "área", "arma", "arpa", "asa",
    "ascua", "asma", "asta", "aula", "aura", "ave", "hacha", "hada", "habla", "hambre", "hampa", "haya",
}


def check_noun(draft: german.Draft, dictionary: Dictionary) -> list[german.Check]:
    checks: list[german.Check] = []
    word = draft.lemma
    entries = dictionary.nouns(word)
    genders = list(dict.fromkeys(entry.gender for entry in entries))

    if genders and all(gender == PLURAL_ONLY or gender.endswith("-p") for gender in genders):
        articles = list(dict.fromkeys(ARTICLES[gender] for gender in genders if gender in ARTICLES))
        if len(articles) == 1 and draft.article != articles[0]:
            draft.article = articles[0]
            checks.append(german.Check(level="warn", message=f"Plural-only noun: changed article to {draft.article}."))
        elif draft.article in articles:
            checks.append(german.Check(level="ok", message=f"Plural-only noun confirmed: {draft.article} {word}."))
        else:
            checks.append(german.Check(level="warn", message="Plural-only noun: check whether los or las applies."))
        draft.plural = ""
        return checks

    genders = [gender for gender in genders if gender in ("m", "f")]
    entries = [entry for entry in entries if entry.gender in ("m", "f")]
    feminine_el = genders == ["f"] and word.lower() in _FEMININE_EL_WORDS
    unverified_el = (genders == ["f"] and draft.article == "el" and not feminine_el
                     and bool(re.match(r"h?[aá]", word.lower())))
    expected_article = (None if unverified_el else "el" if feminine_el
                        else ARTICLES[genders[0]] if len(genders) == 1 else None)
    if not draft.article:
        checks.append(german.Check(level="warn", message="No article. Pick el or la."))
    elif draft.article in ("los", "las") and genders:
        checks.append(german.Check(level="warn", message=f"{draft.article} is only for plural-only nouns. Pick el or la."))
    elif genders:
        model_gender = GENDER_OF[draft.article]
        if unverified_el:
            checks.append(german.Check(
                level="warn", message="Feminine noun: verify that el is justified by a stressed initial a/ha.",
            ))
        elif expected_article and draft.article != expected_article:
            checks.append(german.Check(
                level="warn",
                message=f"The model said “{draft.article}”, Wiktionary says “{expected_article}”. Changed to {expected_article}.",
            ))
            draft.article = expected_article
        elif feminine_el:
            checks.append(german.Check(
                level="ok",
                message=f"Feminine noun confirmed: singular el {word} follows the stressed a/ha article rule.",
            ))
        elif model_gender in genders:
            checks.append(german.Check(level="ok", message=f"Gender confirmed by Wiktionary: {draft.article} {word}."))
        else:
            options = ", ".join(f"{ARTICLES[entry.gender]} {word} ({entry.gloss})" for entry in entries)
            checks.append(german.Check(
                level="warn", message=f"Wiktionary has several genders: {options}. Check which one you mean."
            ))
        if draft.article in GENDER_OF and GENDER_OF[draft.article] in genders and not feminine_el:
            for entry in entries:
                if entry.gender != GENDER_OF[draft.article]:
                    checks.append(german.Check(
                        level="info",
                        message=f"Wiktionary also lists {ARTICLES[entry.gender]} {word}: {entry.gloss}.",
                    ))
    elif dictionary.state == "ready":
        checks.append(german.Check(level="info", message="Not in Wiktionary, so the gender is unverified."))
    else:
        checks.append(german.Check(level="info", message="The dictionary isn't ready yet, so the gender is unverified."))

    if feminine_el:
        draft.gender_rule = "Feminine: singular el precedes stressed a/ha; the plural uses las."
    same = [entry for entry in entries
            if entry.gender == ("f" if feminine_el or unverified_el else GENDER_OF.get(draft.article))]
    plurals = list(dict.fromkeys(plural for entry in same for plural in entry.plurals))
    if same and plurals and not draft.plural:
        checks.append(german.Check(level="info", message=f"Wiktionary also lists the plural “{plurals[0]}”."))
    elif same and plurals and draft.plural not in plurals:
        old = draft.plural
        draft.plural = plurals[0]
        checks.append(german.Check(level="warn", message=f"Plural changed from “{old}” to “{plurals[0]}” (Wiktionary)."))
    elif same and plurals and len(plurals) > 1:
        checks.append(german.Check(
            level="info", message=f"Other plural forms: {', '.join(p for p in plurals if p != draft.plural)}."
        ))
    elif same and not plurals and draft.plural:
        checks.append(german.Check(level="info", message="Wiktionary lists no plural for this noun."))
    return checks


def _verb_mismatches(draft: german.Draft, verb: Verb) -> dict[str, str]:
    reflexive = draft.lemma.endswith("se")
    prefix = "se " if reflexive else ""
    out: dict[str, str] = {}
    if verb.present and draft.present != prefix + verb.present:
        out["present"] = prefix + verb.present
    if verb.preterite and draft.preterite != prefix + verb.preterite:
        out["preterite"] = prefix + verb.preterite
    if verb.participle and draft.perfect != f"{prefix}ha {verb.participle}":
        out["perfect"] = f"{prefix}ha {verb.participle}"
    return out


def check_verb(draft: german.Draft, dictionary: Dictionary) -> list[german.Check]:
    base = draft.lemma.removesuffix("se").strip()
    verbs = dictionary.verbs(base)
    if not verbs:
        if dictionary.state == "ready":
            return [german.Check(level="info", message="Not in Wiktionary, so the verb forms are unverified.")]
        return []
    _, fixes = min(((verb, _verb_mismatches(draft, verb)) for verb in verbs), key=lambda item: len(item[1]))
    labels = {"present": "Present", "preterite": "Preterite", "perfect": "Perfect"}
    checks: list[german.Check] = []
    for field, value in fixes.items():
        old = getattr(draft, field) or "none"
        setattr(draft, field, value)
        checks.append(german.Check(
            level="warn", message=f"{labels[field]} changed from “{old}” to “{value}” (Wiktionary)."
        ))
    if not checks:
        checks.append(german.Check(level="ok", message="Verb forms match Wiktionary."))
    return checks


def check(draft: german.Draft, dictionary: Dictionary) -> list[german.Check]:
    if draft.kind == "noun":
        return check_noun(draft, dictionary)
    if draft.kind == "verb":
        return check_verb(draft, dictionary)
    return []


# -- duplicates -------------------------------------------------------------------


EXACT_FIELDS = ["Palabra", "Infinitivo", "Frase", "Wort_ES", "base_s"]
LOOSE_FIELDS = ["es_word", "full_s"]


def _escape(value: str) -> str:
    return re.sub(r'([\\"*_])', r"\\\1", value)


def duplicate_query(lemma: str) -> str:
    value = _escape(lemma.strip())
    terms = [f'"{field}:{value}"' for field in EXACT_FIELDS]
    for field in LOOSE_FIELDS:
        terms += [f'"{field}:{value}"', f'"{field}:{value},*"']
    return "(" + " OR ".join(terms) + ")"


# -- note types -------------------------------------------------------------------


CSS = german.CSS.replace(".de {", ".es {").replace("g-der", "g-el").replace("g-die", "g-la")
CSS += "\n.g-los { color: #2563eb; } .nightMode .g-los { color: #60a5fa; }\n"
CSS += ".g-las { color: #dc2626; } .nightMode .g-las { color: #f87171; }\n"

_EXAMPLES = """\
<div class="examples">
{{#Ejemplo1}}<div class="ex"><div>{{Ejemplo1}} {{Audio_Ejemplo1}}</div><div class="en">{{Ejemplo1_EN}}</div></div>{{/Ejemplo1}}
{{#Ejemplo2}}<div class="ex"><div>{{Ejemplo2}} {{Audio_Ejemplo2}}</div><div class="en">{{Ejemplo2_EN}}</div></div>{{/Ejemplo2}}
</div>
{{#Nota}}<div class="note">{{Nota}}</div>{{/Nota}}
{{#Fuente}}<div class="source">“{{Fuente}}”</div>{{/Fuente}}"""

_EXAMPLE_FIELDS = ["Ejemplo1", "Ejemplo1_EN", "Ejemplo2", "Ejemplo2_EN", "Nota", "Fuente"]
_AUDIO_FIELDS = ["Audio_Palabra", "Audio_Ejemplo1", "Audio_Ejemplo2"]

_NOUN_WORD = '<div class="es g-{{Artículo}}">{{Artículo}} {{Palabra}}</div>'
_NOUN_PLURAL = '{{#Plural}}<div class="sub">pl. {{Plural}}</div>{{/Plural}}'
_NOUN_RULE = '{{#ReglaGénero}}<div class="rule">{{ReglaGénero}}</div>{{/ReglaGénero}}'

_LINKS_SCRIPT = """\
<script>
(function () {
  var enc = encodeURIComponent;
  document.querySelectorAll(".links[data-w]").forEach(function (el) {
    var full = el.getAttribute("data-w").trim();
    var kind = el.getAttribute("data-kind");
    var w = kind === "verb" ? full.replace(/se$/, "").trim() : full;
    if (!full || el.childElementCount) return;
    var links = [["Wiktionary", "https://en.wiktionary.org/wiki/" + enc(w.replace(/ /g, "_")) + "#Spanish"]];
    if (kind === "verb") links.push(["Conjugation", "https://www.wordreference.com/conj/esverbs.aspx?v=" + enc(w)]);
    links.push(["Spanish-English", "https://www.wordreference.com/es/en/translation.asp?spen=" + enc(w)]);
    el.innerHTML = links.map(function (l) { return '<a href="' + l[1] + '">' + l[0] + "</a>"; }).join(" · ");
  });
})();
</script>"""


def _links(field: str, kind: str) -> str:
    return f'<div class="links" data-w="{{{{text:{field}}}}}" data-kind="{kind}"></div>{_LINKS_SCRIPT}'


_NOUN_LINKS = _links("Palabra", "noun")
_VERB_LINKS = _links("Infinitivo", "verb")
_WORD_LINKS = _links("Palabra", "word")

_VERB_FORMS = (
    '<div class="sub">{{Presente}} · {{Pretérito}} · {{Perfecto}}</div>'
    '{{#Régimen}}<div class="sub">{{Régimen}}</div>{{/Régimen}}'
)

NOTETYPES: dict[german.Kind, dict] = {
    "noun": {
        "name": "ES Noun",
        "fields": ["Palabra", "Artículo", "Plural", "Significado", "ReglaGénero", *_EXAMPLE_FIELDS, *_AUDIO_FIELDS],
        "templates": [
            {
                "name": "Español → English",
                "front": f"{_NOUN_WORD}{{{{Audio_Palabra}}}}",
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="meaning">{{{{Significado}}}}</div>'
                        f"{_NOUN_PLURAL}{_NOUN_RULE}{_EXAMPLES}{_NOUN_LINKS}",
            },
            {
                "name": "English → Español",
                "front": '<div class="meaning">{{Significado}}</div><div class="hint">noun, with article</div>',
                "back": f'{{{{FrontSide}}}}<hr id="answer">{_NOUN_WORD}{{{{Audio_Palabra}}}}{_NOUN_PLURAL}'
                        f"{_NOUN_RULE}{_EXAMPLES}{_NOUN_LINKS}",
            },
            {
                "name": "Género",
                "front": '<div class="es"><span class="blank">___</span> {{Palabra}}</div>'
                         '<div class="hint">el, la, los or las?</div>',
                "back": f'{_NOUN_WORD}{{{{Audio_Palabra}}}}{_NOUN_RULE}'
                        f'<div class="sub">{{{{Significado}}}}</div>{_NOUN_LINKS}',
            },
        ],
    },
    "verb": {
        "name": "ES Verb",
        "fields": ["Infinitivo", "Significado", "Presente", "Pretérito", "Perfecto", "Régimen",
                   *_EXAMPLE_FIELDS, *_AUDIO_FIELDS],
        "templates": [
            {
                "name": "Español → English",
                "front": '<div class="es">{{Infinitivo}}</div>{{Audio_Palabra}}',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="meaning">{{{{Significado}}}}</div>'
                        f"{_VERB_FORMS}{_EXAMPLES}{_VERB_LINKS}",
            },
            {
                "name": "English → Español",
                "front": '<div class="meaning">{{Significado}}</div><div class="hint">verb</div>',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="es">{{{{Infinitivo}}}}</div>'
                        f"{{{{Audio_Palabra}}}}{_VERB_FORMS}{_EXAMPLES}{_VERB_LINKS}",
            },
        ],
    },
    "word": {
        "name": "ES Word",
        "fields": ["Palabra", "Categoría", "Significado", *_EXAMPLE_FIELDS, *_AUDIO_FIELDS],
        "templates": [
            {
                "name": "Español → English",
                "front": '<div class="es">{{Palabra}}</div>{{Audio_Palabra}}',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="meaning">{{{{Significado}}}}</div>'
                        f'<div class="sub">{{{{Categoría}}}}</div>{_EXAMPLES}{_WORD_LINKS}',
            },
            {
                "name": "English → Español",
                "front": '<div class="meaning">{{Significado}}</div><div class="hint">{{Categoría}}</div>',
                "back": f'{{{{FrontSide}}}}<hr id="answer"><div class="es">{{{{Palabra}}}}</div>'
                        f"{{{{Audio_Palabra}}}}{_EXAMPLES}{_WORD_LINKS}",
            },
        ],
    },
    "phrase": {
        "name": "ES Phrase",
        "fields": ["Frase", "Significado", "Nota", "Fuente", "Audio"],
        "templates": [
            {
                "name": "Español → English",
                "front": '<div class="es">{{Frase}}</div>{{Audio}}',
                "back": '{{FrontSide}}<hr id="answer"><div class="meaning">{{Significado}}</div>'
                        '{{#Nota}}<div class="note">{{Nota}}</div>{{/Nota}}',
            },
            {
                "name": "English → Español",
                "front": '<div class="meaning">{{Significado}}</div><div class="hint">say it in Spanish</div>',
                "back": '{{FrontSide}}<hr id="answer"><div class="es">{{Frase}}</div>{{Audio}}'
                        '{{#Nota}}<div class="note">{{Nota}}</div>{{/Nota}}',
            },
            {
                "name": "Escuchar",
                "front": '{{#Audio}}<div class="hint">Listen. What does it mean?</div>{{Audio}}{{/Audio}}',
                "back": '{{FrontSide}}<hr id="answer"><div class="es">{{Frase}}</div>'
                        '<div class="meaning">{{Significado}}</div>',
            },
        ],
    },
}
for _notetype in NOTETYPES.values():
    _notetype["css"] = CSS


# -- draft -> note ----------------------------------------------------------------


strip_html = german.strip_html


def speech_texts(draft: german.Draft) -> dict[str, str]:
    if draft.kind == "phrase":
        return {"Audio": strip_html(draft.lemma)}
    head = f"{draft.article} {draft.lemma}" if draft.kind == "noun" and draft.article else draft.lemma
    out = {"Audio_Palabra": strip_html(head)}
    for index, example in enumerate(draft.examples[:2], start=1):
        if example.de.strip():
            out[f"Audio_Ejemplo{index}"] = strip_html(example.de)
    return out


def note_fields(draft: german.Draft, audio: dict[str, str]) -> list[str]:
    examples = draft.examples + [german.Example(de="", en="")] * 2
    values: dict[str, str] = {
        "Significado": draft.meaning,
        "Ejemplo1": examples[0].de, "Ejemplo1_EN": examples[0].en,
        "Ejemplo2": examples[1].de, "Ejemplo2_EN": examples[1].en,
        "Nota": draft.note,
        "Fuente": draft.source,
        **{field: f"[sound:{name}]" for field, name in audio.items()},
    }
    match draft.kind:
        case "noun":
            values |= {"Palabra": draft.lemma, "Artículo": draft.article, "Plural": draft.plural,
                       "ReglaGénero": draft.gender_rule}
        case "verb":
            values |= {"Infinitivo": draft.lemma, "Presente": draft.present, "Pretérito": draft.preterite,
                       "Perfecto": draft.perfect, "Régimen": draft.governs}
        case "word":
            values |= {"Palabra": draft.lemma, "Categoría": draft.part_of_speech}
        case "phrase":
            values |= {"Frase": draft.lemma}
    return [values.get(name, "") for name in NOTETYPES[draft.kind]["fields"]]
