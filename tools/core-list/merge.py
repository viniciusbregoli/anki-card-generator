"""Merge the cleaned frequency list and the everyday additions into one ordered list."""
import os, json, re
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
cleaned = json.load(open(D + "candidates-cleaned.json"))
adds = json.load(open(D + "goethe-additions.json"))
scores = json.load(open(D + "scores-all.json"))
low = {}
for k, v in scores.items():
    low[k.lower()] = max(low.get(k.lower(), 0), v)
RESTORE = {"Präsident", "Bürgermeister", "Bevölkerung", "Journalist", "Minister", "Löwe", "Tiger",
           "Hubschrauber", "Finale"}  # general words the cleanup dropped too eagerly
FIX = {"Weste": "Westen", "tschüs": "tschüss"}
DROP = {"hunderteins", "Mobiltelefon", "Mailbox"}
# Words the lemmatizers folded into another lemma ("bitte" counted as "bitten"): borrow that score.
ALIAS = {"bitte": "bitten", "danke": "danken", "möchten": "mögen", "später": "spät", "leidtun": "leid",
         "wehtun": "weh", "erste": "zweite", "tschüss": "tschüss"}
BOOST = 3  # corpora underrate concrete daily-life words

def key(lemma):
    """One entry per word: "sich" and casing variants merge, but a noun stays apart from the
    verb or adjective spelled the same (das Leben / leben, der Arm / arm)."""
    bare = re.sub(r"^sich ", "", lemma)
    return bare if bare[:1].isupper() else bare.lower()

items = {}
def add(lemma, english, everyday, score, source):
    lemma = FIX.get(lemma, lemma)
    if lemma in DROP: return
    k = key(lemma)
    s = score * (BOOST if everyday else 1)
    old = items.get(k)
    if old is None or s > old["score"]:
        items[k] = {"lemma": lemma, "english": english, "everyday": everyday, "score": s,
                    "freq": score, "source": source}
for x in cleaned:
    if x["verdict"] == "drop" and x["source_lemma"] not in RESTORE: continue
    add(x["lemma"], x["english"], x["verdict"] == "everyday", x["score"], f'frequency #{x["rank"]}')
unscored = []
for x in adds:
    if not x["keep"]: continue
    # The exact lemma's own score first, so "leben" does not borrow the score of "Leben".
    sc = scores.get(x["lemma"]) or scores.get(key(x["lemma"])) or max(
        low.get(x["lemma"].lower(), 0), low.get(x["source"].lower(), 0), low.get(ALIAS.get(x["lemma"], "-"), 0))
    if not sc: unscored.append(x["lemma"])
    add(x["lemma"], x["english"], True, sc, f'Goethe {x["goethe"]}')
# Feminine forms (Kollegin) when the masculine is in the list: the noun card can mention both.
for k in [k for k in items if k.endswith("in") and items[k]["lemma"][0].isupper()]:
    if k[:-2] in items or k[:-2] + "e" in items:
        items.pop(k)
ranked = sorted(items.values(), key=lambda x: -x["score"])
# Greetings and politeness come first whatever the corpora say ("tschüss" is rare in print).
PIN = ["hallo", "tschüss", "danke", "bitte", "Entschuldigung", "okay"]
for k in map(key, PIN):
    if k not in items:  # dropped upstream: nothing to pin
        print("pinned word missing from the list:", k)
        continue
    items[k]["score"] = max(items[k]["score"], ranked[120]["score"])
ranked = sorted(items.values(), key=lambda x: -x["score"])
floor = ranked[1500]["score"]
for x in ranked:  # official everyday words with no frequency data still make the list
    if x["score"] == 0: x["score"] = floor
ranked.sort(key=lambda x: -x["score"])
for i, x in enumerate(ranked, 1): x["rank"] = i
json.dump(ranked, open(D + "core-list.json", "w"), ensure_ascii=False, indent=0)
top = ranked[:2000]
print("total", len(ranked), "| in top 2000: everyday", sum(x["everyday"] for x in top),
      "goethe additions", sum(x["source"].startswith("Goethe") for x in top), "| unscored", unscored)
print("cut just below 2000:", [x["lemma"] for x in ranked[2000:2060]])

import csv
with open(D + "core-list.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rank", "lemma", "english", "everyday", "source"])
    for x in ranked: w.writerow([x["rank"], x["lemma"], x["english"], "yes" if x["everyday"] else "", x["source"]])
