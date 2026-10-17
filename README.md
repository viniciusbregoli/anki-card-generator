<img src="assets/icon.svg" width="64" height="64" alt="">

# anki-card-generator

Type a German word, expression or sentence you ran into. A text model drafts the card,
Wiktionary checks the gender and plural, ElevenLabs reads it aloud, and after you review it
the card lands in your own Anki collection, ready on the phone after the next sync.

```
 browser ──► card generator ──► anki-manager ◄──► anki-sync (self-hosted) ◄──► phone / desktop
              OpenRouter         owns the copy      your sync server
              ElevenLabs         of the collection
              Wiktionary
```

This app holds no Anki data. Every write goes through anki-manager's API, so the
collection still has one web client and one sync path.

## What a card gets

| Type | Note type | Cards |
|---|---|---|
| Noun | `DE Noun` | Deutsch → English, English → Deutsch, **Genus** (`___ Rechnung` → die) |
| Verb | `DE Verb` | Deutsch → English, English → Deutsch, with present / preterite / perfect and case |
| Other word | `DE Word` | Deutsch → English, English → Deutsch |
| Phrase | `DE Phrase` | Deutsch → English, English → Deutsch, **Hören** (audio only) |

- Articles are coloured on every card: der blue, die red, das green.
- Each word card has two example sentences, with audio for the word and both examples.
- The answer side of noun, verb and word cards links to Wiktionary (all meanings, tables),
  Verbformen (full conjugation, or noun/adjective declension) and dict.cc. A small script in the
  template builds the links (it drops `sich` for Wiktionary); the draft editor shows the same links.
- New cards go to `German - Mine`, tagged `card-generator`, the type, a level and a topic.

## Level and topic tags

Every German note gets `level::A1`…`level::C2` and one of 20 `topic::…` tags (`food`,
`travel`, `grammar`, …; the list is in `tagging.py`), so filtered decks like
`tag:topic::food tag:level::A2` work. The text model picks both in the same call that
drafts the card, and you can change them before adding it. The level is a guess from how
common and basic the word is, not an official list.

## Core word and phrase lists

`/data/frequency/core-words.json` holds the 2,000 words the `German - Mine` deck is built
from, and `phrases.json` 559 everyday phrases. The words are ranked by frequency in German
film subtitles (SUBTLEX-DE) and written German (DeReKo), cleaned by the text model, with
everyday words the corpora underrate (Brot, Fahrkarte) boosted. Prepositions, pronouns and
particles get no word card; they are learned through the phrases. The scripts that built
both lists are in `tools/core-list/` (one-off, run in order: blend2, clean, add, merge,
split, phrases, review_phrases, order_phrases). They read and write `$CORE_LIST_DATA`
(default `data/frequency`); the LLM steps need `OPENROUTER_API_KEY` in the environment.

Cards are made a batch at a time. Each draft gets a second, stricter review by the text
model (high reasoning), and a batch is written to a file to read before anything is saved:

```sh
sudo docker exec anki-card-generator python -m card_generator.batch draft words 51-100
sudo docker exec anki-card-generator python -m card_generator.batch draft phrases 26-50
sudo docker exec anki-card-generator python -m card_generator.batch save words-0051-0100
```

Batch cards are tagged `core-words` and `core::0001-0100` (one tag per hundred), or
`core-phrases` and `phrase-tier::1`.

## Checks

- **Gender and plural** are compared against an English-Wiktionary extract (kaikki.org).
  It's downloaded once on first start (~1 GB streamed, ~40 s) into a 6 MB SQLite file.
  If Wiktionary has exactly one gender, a wrong article is corrected and flagged.
  Words with several genders (der/die See) keep the model's choice and list the others.
- **Gender rules** come from a fixed suffix table (‑ung, ‑heit, ‑chen, ‑ismus, …), so the
  card says "always", "usually" or "Exception: …". Compounds the dictionary doesn't
  know are checked against their last part (Gartentür → die Tür). Other rules
  (days, months, nominalised infinitives, …) come from the model.
- **Verb forms** (present, preterite, perfect with haben/sein) are compared, not corrected.
- **Duplicates** are searched in this app's note types and in the existing Goethe note
  types (`Wort_DE`, `base_d`, `de_word`, `full_d`).

## Layout

- `backend/card_generator/german.py`: note types, prompt, schema, checks, draft → fields.
- `backend/card_generator/dictionary.py`: Wiktionary extract builder and lookups.
- `backend/card_generator/clients.py`: OpenRouter, ElevenLabs (with disk cache), anki-manager.
- `backend/card_generator/tagging.py`: the level and topic lists.
- `backend/card_generator/batch.py`: cards for the core lists, a batch at a time.
- `backend/card_generator/api.py`: JSON API and static UI.
- `frontend/`: React + Vite + Tailwind.

Writes need an `x-card-generator: 1` header, for the same CSRF reason as anki-manager.
Generated audio is cached by `hash(model, voice, language, text)` in `/data/audio`, so
nothing is paid for twice.

## Development

```sh
cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest                  # fake remote services, real Wiktionary sample

# against a running anki-manager:
OPENROUTER_API_KEY=… ELEVENLABS_API_KEY=… CARD_GENERATOR_DATA=/tmp/acg \
ANKI_MANAGER_URL=http://127.0.0.1:8000 \
  .venv/bin/uvicorn card_generator.api:create_app --factory --port 8001 &
cd ../frontend && pnpm install && CARD_GENERATOR_BACKEND=http://127.0.0.1:8001 pnpm dev
```

## Configuration

| Variable | Default | |
|---|---|---|
| `ANKI_MANAGER_URL` | `http://anki-manager:8000` | anki-manager's API |
| `OPENROUTER_API_KEY` | (required) | |
| `OPENROUTER_MODEL` | `openai/gpt-6-luna` | Any OpenRouter model with structured outputs |
| `OPENROUTER_REASONING` | `medium` | Reasoning effort |
| `ELEVENLABS_API_KEY` | (none: cards are saved without audio) | |
| `ELEVENLABS_MODEL` | `eleven_v4` | |
| `ELEVENLABS_VOICE_ID` | `IWm8DnJ4NGjFI7QAM5lM` | "Stephan", native German male |
| `CARD_GENERATOR_DECK` | `German - Mine` | Created if missing |
| `CARD_GENERATOR_DATA` | `/data` | Dictionary and audio cache |
| `CARD_GENERATOR_DICTIONARY_URL` | kaikki.org German extract | Empty disables the automatic build |

## Note types

Note types are created on the first save, through anki-manager's
`PUT /api/notetypes`. Template and CSS changes in `german.py` are applied on the next
save after a restart, and they sync incrementally. Changing a note type's **fields**
or **card list** is refused, because it would force a full sync on every device. Make a
new note type instead.

## Deployment

Runs as a Docker Compose service (`anki-card-generator`) next to anki-manager, published only
on the private network (e.g. behind `tailscale serve`, bound to `127.0.0.1:8097`). Keys come
from the Compose `.env` file. After changing this repo, rebuild with
`docker compose up -d --build anki-card-generator`.
