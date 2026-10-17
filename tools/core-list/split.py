"""Split the ranked list into word cards and grammar words that are learned through phrases."""
import os, csv, json
D = os.environ.get("CORE_LIST_DATA", "data/frequency").rstrip("/") + "/"  # the lists and source files
ranked = json.load(open(D + "core-list.json"))

# No card: articles (gender lives on the noun cards), contractions, bare verb prefixes.
DROP = set("der ein fürs ans ums hin her heraus hinaus herum hinein fort entgegen".split())
# Meaning depends on the phrase around them: prepositions, pronouns and possessives,
# modal particles and da-words. These seed the phrases list instead of getting a card.
PHRASE = set("""in mit von auf für an aus um bei nach vor über bis durch unter gegen zu seit
    ich du er sie es wir ihr man sich mein dein unser euer
    doch mal denn eben wohl gar bloß ruhig
    damit dafür davon dazu darauf darüber daran darum dagegen darin daraus dadurch davor darunter
    daneben dabei drin drauf dran""".split())

words, seeds = [], []
for x in ranked:
    if x["lemma"] in DROP:
        continue
    (seeds if x["lemma"] in PHRASE else words).append(x)
words = words[:2000]
for i, x in enumerate(words, 1):
    x["deck_rank"] = i
json.dump(words, open(D + "core-words.json", "w"), ensure_ascii=False, indent=0)
json.dump(seeds, open(D + "phrase-seeds.json", "w"), ensure_ascii=False, indent=0)
with open(D + "core-words.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rank", "lemma", "english", "everyday", "source"])
    for x in words: w.writerow([x["deck_rank"], x["lemma"], x["english"], "yes" if x["everyday"] else "", x["source"]])
print(len(words), "word cards;", len(seeds), "phrase seeds; last word in:", words[-1]["lemma"], words[-1]["rank"])
missing = PHRASE - {x["lemma"] for x in seeds}
print("phrase words not found:", sorted(missing))
