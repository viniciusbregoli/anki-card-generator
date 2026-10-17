"""LLM pass over the blended candidates: fix lemmas, drop junk, mark everyday words."""
import json, os, sys, concurrent.futures as cf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from card_generator.clients import TextModel
text = TextModel(os.environ["OPENROUTER_API_KEY"], "openai/gpt-6-luna", reasoning="medium")
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
N, CHUNK = int(sys.argv[1]), 90
rows = json.load(open(D + "candidates-blend.json"))[:N]

SYSTEM = """You curate a German core-vocabulary list for an adult learner (native Portuguese, fluent English)
who wants to understand and take part in everyday conversation in Germany. You get candidates from a
frequency list built from film subtitles and newspapers, with the lemmatizer's guess, its POS tag and the
commonest forms seen. For each candidate decide:

- lemma: the dictionary form a learner should learn. Nouns without article and in the singular (unless
  only used in the plural), verbs in the infinitive (separable verbs joined: "aufstehen"), adjectives in
  the base form. Fix lemmatizer mistakes ("Haufe" -> "Haufen", "dritt" -> "dritte", "worden" -> "werden",
  "Akt|Akte" -> the likelier one given the forms). The definite article "die" covers der/die/das: use "der".
- english: a short English gloss (2-5 words) of the common everyday meaning.
- verdict:
  - "core": a word a learner needs for everyday conversation, including function words, numbers,
    common verbs/adjectives/adverbs and general nouns.
  - "everyday": concrete daily-life vocabulary (food, home, shopping, transport, body/health, clothes,
    family, work routine, city, weather, time) - frequency lists rank these too low, so mark them.
  - "drop": not worth a card at this stage. Reasons: "name" (people, places, brands; but keep
    Deutschland/deutsch and very common nationality words), "letter_or_abbreviation" (single letters, Mr,
    Dr, AG, km), "film_or_crime" (frequent only because of dubbed action/crime/fantasy films: Vampir, FBI,
    Sheriff, Dämon, Leiche), "news_or_business" (frequent only in newspapers: Stadtrat, Vorstand,
    Bundesliga), "vulgar" (slurs and strong sexual swearing; keep mild everyday ones like "Scheiße"),
    "junk" (not a real word / lemmatizer garbage / duplicate of a form already covered).
  Be conservative with drops: common general words stay even if they sound dramatic (töten, Krieg, Waffe
  are core). Only drop when the word is clearly niche for daily life.
- reason: the drop reason, or "" if kept.
Return every candidate, in order, with its rank."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["rank", "lemma", "english", "verdict", "reason"], "properties": {
            "rank": {"type": "integer"}, "lemma": {"type": "string"}, "english": {"type": "string"},
            "verdict": {"type": "string", "enum": ["core", "everyday", "drop"]},
            "reason": {"type": "string", "enum": ["", "name", "letter_or_abbreviation", "film_or_crime",
                                                   "news_or_business", "vulgar", "junk"]}}}}}}

def one(chunk):
    user = "\n".join(f'{r["rank"]}\t{r["lemma"]}\t{r["pos"]}\tforms: {", ".join(r["forms"])}' for r in chunk)
    for attempt in range(3):
        try:
            got = text.json(SYSTEM, user, SCHEMA, "vocab")["items"]
            by = {g["rank"]: g for g in got}
            missing = [r["rank"] for r in chunk if r["rank"] not in by]
            if not missing:
                return [{**r, **by[r["rank"]], "source_lemma": r["lemma"]} for r in chunk]
            print("missing", missing[:5], file=sys.stderr)
        except Exception as e:
            print("retry", chunk[0]["rank"], e, file=sys.stderr)
    raise SystemExit(f"chunk {chunk[0]['rank']} failed")

chunks = [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)]
out = []
with cf.ThreadPoolExecutor(6) as p:
    for i, res in enumerate(p.map(one, chunks), 1):
        out += res; print(f"{i}/{len(chunks)}", file=sys.stderr)
json.dump(out, open(D + "candidates-cleaned.json", "w"), ensure_ascii=False, indent=0)
