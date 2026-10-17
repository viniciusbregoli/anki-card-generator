"""Blend spoken (SUBTLEX-DE) and written (DeReKo) lemma frequencies into one candidate list."""
import os, csv, json, math, collections
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
w = collections.Counter(); wpos = collections.defaultdict(collections.Counter)
for line in open(D + "DeReKo-2014-II-MainArchive-STT.100000.freq", encoding="utf-8", errors="replace"):
    p = line.rstrip("\n").split("\t")
    if len(p) != 4: continue
    form, lemma, pos, f = p
    if pos.startswith("$") or lemma in ("<unknown>", "UNKNOWN"): continue
    w[lemma] += float(f); wpos[lemma][pos] += float(f)
casing = {}  # lowercase -> most frequent written casing
for l, f in w.most_common():
    casing.setdefault(l.lower(), l)
s = collections.Counter(); forms = collections.defaultdict(collections.Counter)
for r in csv.DictReader(open(D + "SUBTLEXDE_LemmasJV.csv", encoding="utf-8")):
    if r["spell.check.OK..1.0."] != "1" or r["Lemma"] == "<unknown>": continue
    l = r["Lemma"]
    # Sentence-initial capitals in subtitles ("Ja"): use the much commoner written casing.
    other = casing.get(l.lower(), l)
    if w[other] > 5 * w[l]:
        l = other
    s[l] += int(r["WFfreqcount"]); forms[l][r["Word"]] += int(r["WFfreqcount"])
ws, ss = sum(w.values()), sum(s.values())
pos_of = {l: c.most_common(1)[0][0] for l, c in wpos.items()}
rows = []
for l in s:
    if pos_of.get(l) in {"NE", "FM", "XY", "TRUNC"}: continue
    a, b = s[l] / ss * 1e6, w[l] / ws * 1e6
    if not b:  # spoken only ("tschüss"): count it, at a penalty
        b = a / 20
    rows.append({"lemma": l, "pos": pos_of.get(l, "?"), "score": math.sqrt(a * b), "spoken_pm": round(a, 2),
                 "written_pm": round(b, 2), "forms": [f for f, _ in forms[l].most_common(4)]})
rows.sort(key=lambda r: -r["score"])
for i, r in enumerate(rows, 1): r["rank"] = i
json.dump(rows[:4000], open(D + "candidates-blend.json", "w"), ensure_ascii=False)
json.dump({r["lemma"]: r["score"] for r in rows}, open(D + "scores-all.json", "w"), ensure_ascii=False)
idx = {r["lemma"]: r["rank"] for r in rows}
print({k: idx.get(k) for k in ["ja", "Ja", "nein", "bitten", "danken", "Entschuldigung", "danke", "bitte", "hallo", "zwei", "zehn", "Brot", "okay", "tschüss", "Bahnhof"]})
