"""LLM pass over official A1/A2 words that the frequency list missed: keep the everyday essentials."""
import json, os, sys, concurrent.futures as cf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from card_generator.clients import TextModel
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
text = TextModel(os.environ["OPENROUTER_API_KEY"], "openai/gpt-6-luna", reasoning="medium")
miss = json.load(open(D + "goethe_missing.json"))  # Goethe A1/A2 words missing from the frequency list
words = [(w, lv) for lv in ("A1", "A2") for w in miss[lv]]
SYSTEM = """These words come from the official Goethe A1/A2 vocabulary lists but are missing from a
frequency-based core list (film subtitles and newspapers rank concrete daily-life words too low). The
learner is an adult who wants to get by in everyday life in Germany. For each entry give:
- lemma: the dictionary form (nouns singular without article unless plural-only; verbs infinitive;
  numbers spelled out; strip list notation like "dein-", "lieb-", "gern(e)" -> "gern", "(ein)hundert" -> "hundert",
  "samstag/sonnabend" -> "Samstag"). Capitalise nouns.
- english: short English gloss.
- keep: true if it is a genuinely useful everyday word (shopping, food, transport, home, health, paperwork,
  work, family, time, numbers, politeness). false for: inflected forms of words a core list already covers
  (dich, dir, ihn, besser, das, alles, jeden), list fragments, specific years, dated words (Fax, CD, Disco),
  and niche words.
Return every entry, in order, with its index."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["index", "lemma", "english", "keep"], "properties": {
            "index": {"type": "integer"}, "lemma": {"type": "string"}, "english": {"type": "string"},
            "keep": {"type": "boolean"}}}}}}
def one(start):
    chunk = words[start:start + 80]
    user = "\n".join(f"{start + i}\t{w}\t{lv}" for i, (w, lv) in enumerate(chunk))
    for _ in range(3):
        try:
            got = {g["index"]: g for g in text.json(SYSTEM, user, SCHEMA, "additions")["items"]}
            if all(start + i in got for i in range(len(chunk))):
                return [{**got[start + i], "source": w, "goethe": lv} for i, (w, lv) in enumerate(chunk)]
        except Exception as e:
            print("retry", e, file=sys.stderr)
    raise SystemExit("failed")
with cf.ThreadPoolExecutor(6) as p:
    out = [x for res in p.map(one, range(0, len(words), 80)) for x in res]
json.dump(out, open(D + "goethe-additions.json", "w"), ensure_ascii=False, indent=0)
keep = [x for x in out if x["keep"]]
print(len(out), "checked,", len(keep), "kept")
print("kept:", [x["lemma"] for x in keep])
print("dropped:", [x["source"] for x in out if not x["keep"]])
