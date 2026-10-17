"""Order phrases: by tier; within a tier the survival situations first, grammar-word chunks every third slot."""
import os, csv, json
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
PRIORITY = ["greetings", "politeness", "not understanding", "small talk", "feelings", "reactions",
            "at the café", "shopping", "at the supermarket", "time, dates", "public transport", "asking for help",
            "at the doctor", "making plans", "on the phone", "agreeing", "at work", "at home", "paperwork",
            "complaints", "encouragement", "weather"]
def prio(x):
    return next(i for i, p in enumerate(PRIORITY) if x["source"].startswith(p))
phrases = json.load(open(D + "phrases.json"))
out = []
for tier in (1, 2, 3):
    sit = sorted((x for x in phrases if x["tier"] == tier and x["source"] != "seed"), key=prio)
    seeds = [x for x in phrases if x["tier"] == tier and x["source"] == "seed"]
    while sit or seeds:
        for _ in range(2):
            if sit: out.append(sit.pop(0))
        if seeds: out.append(seeds.pop(0))
for i, x in enumerate(out, 1): x["rank"] = i
json.dump(out, open(D + "phrases.json", "w"), ensure_ascii=False, indent=0)
with open(D + "phrases.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rank", "german", "english", "note", "register", "tier", "teaches", "source"])
    for x in out: w.writerow([x["rank"], x["german"], x["english"], x["note"], x["register"], x["tier"], ", ".join(x["teaches"]), x["source"]])
print(len(out)); print([x["german"] for x in out[:25]])
