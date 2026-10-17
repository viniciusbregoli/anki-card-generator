"""Build the phrases-and-expressions list: chunks for the grammar words plus everyday expressions."""
import json, os, re, sys, concurrent.futures as cf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from card_generator.clients import TextModel
text = TextModel(os.environ["OPENROUTER_API_KEY"], "openai/gpt-6-luna", reasoning="medium")
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
seeds = json.load(open(D + "phrase-seeds.json"))

LEARNER = """The learner is an adult (native Portuguese, fluent English) who wants to get by and talk with
people in everyday life in Germany. Phrases must be what native speakers actually say today, in standard
German, short (2-7 words), and reusable as a chunk. Use "..." for an open slot ("Ich hätte gern ...").
Avoid textbook-only, dated or regional expressions."""
ITEM = {"type": "object", "additionalProperties": False,
        "required": ["german", "english", "note", "register", "tier"], "properties": {
            "german": {"type": "string"}, "english": {"type": "string"},
            "note": {"type": "string", "description": "short usage hint, or empty"},
            "register": {"type": "string", "enum": ["neutral", "informal", "formal"]},
            "tier": {"type": "integer", "enum": [1, 2, 3],
                     "description": "1 = you need it in your first weeks, 2 = common, 3 = useful later"}}}
def schema(extra):
    return {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
        "type": "array", "items": {**ITEM, "required": ITEM["required"] + list(extra),
                                   "properties": {**ITEM["properties"], **extra}}}}}

SEED_SYSTEM = LEARNER + """
Each word below is a grammar word whose meaning depends on the phrase around it (prepositions, pronouns,
possessives, modal particles, da-words). For each, give the 3-5 most frequent everyday chunks that teach
how it is really used, e.g. "zu Hause", "nach Hause", "um acht Uhr", "Mir ist kalt.", "Komm doch mit!".
Put the word itself in "teaches"."""
SITUATIONS = """greetings and goodbyes; politeness, thanks and apologies; small talk and introducing yourself;
reactions and fillers in conversation (Echt?, Na ja, Genau); agreeing, disagreeing and giving opinions;
not understanding and asking to repeat; asking for help and directions; at the café and restaurant;
shopping and paying; at the supermarket and bakery; on the phone; making plans and appointments;
time, dates and being late; public transport and travel; at the doctor and pharmacy; feelings and how you are;
at work and with colleagues; at home and with flatmates or neighbours; paperwork and offices (Amt, bank);
encouragement, wishes and celebrations; complaints and problems; weather and everyday comments""".split(";")
SIT_SYSTEM = LEARNER + """
Give the 20 most useful expressions for the situation below, most useful first. Put the 1-3 key words
the expression relies on in "teaches"."""

def ask(system, user, extra):
    for _ in range(3):
        try:
            return text.json(system, user, schema(extra), "phrases")["items"]
        except Exception as e:
            print("retry", e, file=sys.stderr)
    raise SystemExit("failed")

T = {"teaches": {"type": "array", "items": {"type": "string"}}}
jobs = [(SEED_SYSTEM, "\n".join(f'{x["lemma"]} ({x["english"]})' for x in seeds[i:i + 15]), "seed")
        for i in range(0, len(seeds), 15)]
jobs += [(SIT_SYSTEM, "Situation: " + s.strip(), s.strip()) for s in SITUATIONS]
items = []
with cf.ThreadPoolExecutor(6) as p:
    for (_, _, src), got in zip(jobs, p.map(lambda j: ask(j[0], j[1], T), jobs)):
        items += [{**g, "source": src} for g in got]

def norm(s):
    return re.sub(r"[^\wäöüß ]", "", s.lower()).strip()
seen, unique = set(), []
for it in sorted(items, key=lambda x: x["tier"]):
    if norm(it["german"]) not in seen:
        seen.add(norm(it["german"])); unique.append(it)
# Keep the generated list before the last request, so a failure there loses no generation work.
json.dump(unique, open(D + "phrases-generated.json", "w"), ensure_ascii=False, indent=0)
# One pass over the whole list for near-duplicates ("Wie geht's?" / "Wie geht es dir?").
listing = "\n".join(f"{i}\t{x['german']}" for i, x in enumerate(unique))
def find_duplicates():
    return text.json(LEARNER + "\nBelow is a phrase list. List the indexes of entries that are near-duplicates "
                "of an earlier entry (same expression with trivial variation). Keep genuinely different uses.",
                listing, {"type": "object", "additionalProperties": False, "required": ["drop"],
                          "properties": {"drop": {"type": "array", "items": {"type": "integer"}}}}, "dups")["drop"]
for attempt in range(3):
    try:
        dup = find_duplicates()
        break
    except Exception as e:  # transient model or network error: try again
        if attempt == 2:
            raise
        print("duplicate check failed, retrying:", e)
final = [x for i, x in enumerate(unique) if i not in set(dup)]
final.sort(key=lambda x: x["tier"])
for i, x in enumerate(final, 1):
    x["rank"] = i
json.dump(final, open(D + "phrases.json", "w"), ensure_ascii=False, indent=0)
import csv, collections
with open(D + "phrases.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rank", "german", "english", "note", "register", "tier", "teaches", "source"])
    for x in final: w.writerow([x["rank"], x["german"], x["english"], x["note"], x["register"], x["tier"],
                                ", ".join(x["teaches"]), x["source"]])
print(len(items), "generated,", len(unique), "unique,", len(dup), "near-duplicates,", len(final), "kept")
print("tiers:", collections.Counter(x["tier"] for x in final), "register:", collections.Counter(x["register"] for x in final))
