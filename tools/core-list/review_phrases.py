"""Second-opinion review of every phrase (high reasoning): wrong glosses, unnatural German, wrong tier."""
import json, os, sys, collections, concurrent.futures as cf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from card_generator.clients import TextModel
text = TextModel(os.environ["OPENROUTER_API_KEY"], "openai/gpt-6-luna", reasoning="high")
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
phrases = json.load(open(D + "phrases.json"))
SYSTEM = """You are a native German speaker reviewing a phrase list for an adult learner living in Germany.
For each entry check, strictly:
1. Is the German correct, natural and current (not textbook-only or dated)? "..." marks an open slot.
2. Does the English say what a German speaker means by it? Watch idioms: "Was kann ich dafür?" means
   "How is that my fault?", not "What can I do about it?".
3. Tier: 1 = needed in the first weeks in Germany, 2 = common, 3 = useful later. Be strict with tier 1.
Verdict "ok" (leave as is), "fix" (give corrected german/english/note), or "drop" (not worth learning,
unnatural, or too niche). For "ok" copy the fields unchanged. Return every entry with its index."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["index", "verdict", "german", "english", "note", "tier", "reason"], "properties": {
            "index": {"type": "integer"}, "verdict": {"type": "string", "enum": ["ok", "fix", "drop"]},
            "german": {"type": "string"}, "english": {"type": "string"}, "note": {"type": "string"},
            "tier": {"type": "integer", "enum": [1, 2, 3]}, "reason": {"type": "string"}}}}}}
def one(start):
    chunk = phrases[start:start + 50]
    user = "\n".join(f'{start + i}\t{x["german"]}\t{x["english"]}\tnote: {x["note"]}\ttier {x["tier"]}' for i, x in enumerate(chunk))
    for _ in range(3):
        try:
            got = {g["index"]: g for g in text.json(SYSTEM, user, SCHEMA, "review")["items"]}
            if all(start + i in got for i in range(len(chunk))):
                return [got[start + i] for i in range(len(chunk))]
        except Exception as e:
            print("retry", e, file=sys.stderr)
    raise SystemExit("failed")
with cf.ThreadPoolExecutor(6) as p:
    reviews = [r for res in p.map(one, range(0, len(phrases), 50)) for r in res]
out = []
for x, r in zip(phrases, reviews):
    x["review"] = {"verdict": r["verdict"], "reason": r["reason"], "was": [x["german"], x["english"]]}
    if r["verdict"] == "drop": continue
    if r["verdict"] == "fix":
        x.update(german=r["german"], english=r["english"], note=r["note"])
    x["tier"] = r["tier"]
    out.append(x)
out.sort(key=lambda x: x["tier"])
for i, x in enumerate(out, 1): x["rank"] = i
json.dump(out, open(D + "phrases.json", "w"), ensure_ascii=False, indent=0)
json.dump(reviews, open(D + "phrases-review.json", "w"), ensure_ascii=False, indent=0)
import csv
with open(D + "phrases.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rank", "german", "english", "note", "register", "tier", "teaches", "source"])
    for x in out: w.writerow([x["rank"], x["german"], x["english"], x["note"], x["register"], x["tier"], ", ".join(x["teaches"]), x["source"]])
print(collections.Counter(r["verdict"] for r in reviews), "kept", len(out), "tiers", collections.Counter(x["tier"] for x in out))
for x, r in zip(phrases, reviews):
    if r["verdict"] != "ok": print(r["verdict"], "|", x["review"]["was"][0], "|", x["review"]["was"][1], "->", r["german"], "|", r["english"], "|", r["reason"][:90])
