"""German noun genders, plurals and verb forms from Wiktionary, for checking the model.

The source is kaikki.org's extract of English Wiktionary (~1 GB of JSON lines). It is
streamed once into a small SQLite file holding only what the checks need.

    python -m card_generator.dictionary build [SOURCE] [OUT]
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterable, Iterator

import httpx

log = logging.getLogger(__name__)

SOURCE_URL = "https://kaikki.org/dictionary/German/kaikki.org-dictionary-German.jsonl"
SCHEMA_VERSION = 2

GENDER_TAGS = {"masculine": "m", "feminine": "f", "neuter": "n"}
PLURAL_ONLY = "p"  # Leute, Eltern: no gender, always "die"
ARTICLES = {"m": "der", "f": "die", "n": "das", PLURAL_ONLY: "die"}


@dataclass(frozen=True)
class Noun:
    word: str
    gender: str  # m, f, n, or p for plural-only nouns
    plurals: tuple[str, ...]  # empty for singular-only nouns
    gloss: str

    @property
    def article(self) -> str:
        return ARTICLES[self.gender]


@dataclass(frozen=True)
class Verb:
    word: str
    present: str  # 3rd person singular, "wartet"
    preterite: str  # "wartete"
    participle: str  # "gewartet"
    auxiliaries: tuple[str, ...]  # ("haben",), ("sein",) or both


# -- parsing -------------------------------------------------------------------


def _forms(entry: dict, tags: set[str]) -> list[str]:
    """Forms whose tag set is exactly `tags` (so "nonstandard plural" doesn't count)."""
    out = []
    for f in entry.get("forms", []):
        if set(f.get("tags", [])) == tags and f.get("form") and f["form"] not in out:
            out.append(f["form"])
    return out


def _is_form_of(entry: dict) -> bool:
    senses = entry.get("senses", [])
    return bool(senses) and all("form_of" in s or "form-of" in s.get("tags", []) for s in senses)


def _genders(entry: dict) -> list[str]:
    found: list[str] = []
    for sense in entry.get("senses", []):
        for tag in sense.get("tags", []):
            g = GENDER_TAGS.get(tag)
            if g and g not in found:
                found.append(g)
    if found:
        return found
    # Fall back to the head line: "Rechnung f (genitive Rechnung, plural Rechnungen)".
    for head in entry.get("head_templates", []):
        words = head.get("expansion", "").split("(")[0].split()
        for w in words[1:]:
            if w in ("m", "f", "n") and w not in found:
                found.append(w)
    if not found and any("plural-only" in s.get("tags", []) for s in entry.get("senses", [])):
        found.append(PLURAL_ONLY)
    return found


def parse_noun(entry: dict) -> list[Noun]:
    if entry.get("pos") != "noun" or _is_form_of(entry):
        return []
    gloss = next((s["glosses"][0] for s in entry.get("senses", []) if s.get("glosses")), "")
    plurals = tuple(_forms(entry, {"plural"}))
    return [Noun(entry["word"], g, plurals, gloss[:120]) for g in _genders(entry)]


def parse_verb(entry: dict) -> Verb | None:
    if entry.get("pos") != "verb" or _is_form_of(entry):
        return None
    present = _forms(entry, {"present", "singular", "third-person"})
    preterite = _forms(entry, {"past"})
    participle = _forms(entry, {"participle", "past"})
    # Auxiliaries come as "haben", "sein" and sometimes "haben or sein".
    aux = tuple(dict.fromkeys(a for f in _forms(entry, {"auxiliary"}) for a in f.split(" or ")))
    if not (present or preterite or participle):
        return None
    first = lambda xs: xs[0] if xs else ""  # noqa: E731
    return Verb(entry["word"], first(present), first(preterite), first(participle), aux)


def iter_entries(lines: Iterable[str]) -> Iterator[dict]:
    for line in lines:
        # Cheap prefilter: only nouns and verbs are parsed as JSON.
        if '"pos": "noun"' in line or '"pos": "verb"' in line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# -- building ------------------------------------------------------------------


def build(lines: Iterable[str], out: Path) -> int:
    """Write a fresh database to `out` (atomically). Returns the number of rows."""
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(
        """
        create table nouns (word text not null, gender text not null, plurals text not null, gloss text not null);
        create table verbs (word text not null, present text, preterite text, participle text, auxiliaries text);
        create table meta (key text primary key, value text);
        """
    )
    rows = 0
    for entry in iter_entries(lines):
        for noun in parse_noun(entry):
            db.execute(
                "insert into nouns values (?, ?, ?, ?)",
                (noun.word, noun.gender, "|".join(noun.plurals), noun.gloss),
            )
            rows += 1
        if verb := parse_verb(entry):
            db.execute(
                "insert into verbs values (?, ?, ?, ?, ?)",
                (verb.word, verb.present, verb.preterite, verb.participle, "|".join(verb.auxiliaries)),
            )
            rows += 1
    db.executescript("create index nouns_word on nouns(word); create index verbs_word on verbs(word);")
    db.execute("insert into meta values ('schema', ?)", (str(SCHEMA_VERSION),))
    db.commit()
    db.close()
    tmp.replace(out)
    return rows


def _download_lines(url: str) -> Iterator[str]:
    with httpx.stream("GET", url, timeout=httpx.Timeout(60, read=300), follow_redirects=True) as r:
        r.raise_for_status()
        yield from r.iter_lines()


def _file_lines(f: IO[str]) -> Iterator[str]:
    yield from f


# -- lookups -------------------------------------------------------------------


class Dictionary:
    """Read side, plus an optional one-time background build when the file is missing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.state = "missing"  # missing | building | ready | error
        self.error: str | None = None
        self._local = threading.local()
        if self._valid():
            self.state = "ready"

    def _valid(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as db:
                row = db.execute("select value from meta where key = 'schema'").fetchone()
            return row is not None and row[0] == str(SCHEMA_VERSION)
        except sqlite3.Error:
            return False

    def build_in_background(self, url: str = SOURCE_URL) -> None:
        if self.state in ("ready", "building"):
            return
        self.state = "building"

        def run() -> None:
            try:
                rows = build(_download_lines(url), self.path)
                log.info("dictionary built: %d rows", rows)
                self.state = "ready"
            except Exception as exc:  # noqa: BLE001 - reported through status
                log.exception("dictionary build failed")
                self.state, self.error = "error", str(exc)

        threading.Thread(target=run, daemon=True, name="dictionary-build").start()

    def _db(self) -> sqlite3.Connection | None:
        if self.state != "ready":
            return None
        db = getattr(self._local, "db", None)
        if db is None:
            db = self._local.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        return db

    def nouns(self, word: str) -> list[Noun]:
        db = self._db()
        if db is None or not word:
            return []
        rows = db.execute("select word, gender, plurals, gloss from nouns where word = ?", (word,)).fetchall()
        return [Noun(w, g, tuple(p for p in ps.split("|") if p), gl) for w, g, ps, gl in rows]

    def verbs(self, word: str) -> list[Verb]:
        """Every conjugation Wiktionary lists: schaffen is schuf (create) and schaffte (manage)."""
        db = self._db()
        if db is None or not word:
            return []
        rows = db.execute(
            "select word, present, preterite, participle, auxiliaries from verbs where word = ?", (word,)
        ).fetchall()
        return [Verb(w, pres or "", pret or "", part or "", tuple(a for a in (aux or "").split("|") if a))
                for w, pres, pret, part, aux in rows]

    def verb(self, word: str) -> Verb | None:
        found = self.verbs(word)
        return found[0] if found else None

    def compound_head(self, word: str) -> tuple[str, list[Noun]] | None:
        """The longest known noun at the end of a compound: Haustür -> ("Tür", [...]).

        Both parts must have at least three letters, so "Fenster" doesn't split into
        "Fen" + "Ster".
        """
        for i in range(3, len(word) - 2):
            tail = word[i:]
            head = tail[0].upper() + tail[1:]
            found = [n for n in self.nouns(head) if n.gender != PLURAL_ONLY]
            if found:
                return head, found
        return None


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] != "build":
        raise SystemExit(__doc__)
    source = argv[2] if len(argv) > 2 else SOURCE_URL
    out = Path(argv[3] if len(argv) > 3 else "de-dictionary.sqlite")
    if source.startswith("http"):
        rows = build(_download_lines(source), out)
    else:
        with open(source, encoding="utf-8") as f:
            rows = build(_file_lines(f), out)
    print(f"{rows} rows -> {out}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv)
