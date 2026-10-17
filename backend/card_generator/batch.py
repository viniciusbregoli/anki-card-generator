"""Cards for the core word and phrase lists, a batch at a time, through this app's own API.

The lists live in /data/frequency (core-words.json, phrases.json). A batch is drafted
first (each draft gets the stricter review pass) and written to /data/batches/<name>.json
so it can be read before anything is saved; `save` then adds the notes in list order, so new cards come up in that order.

    python -m card_generator.batch draft words 1-50       # -> /data/batches/words-0001-0050.json
    python -m card_generator.batch draft phrases 1-25
    python -m card_generator.batch save words-0001-0050
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

DATA = Path(os.environ.get("CARD_GENERATOR_DATA", "/data"))
API = os.environ.get("CARD_GENERATOR_SELF", "http://127.0.0.1:8000")
HEADERS = {"x-card-generator": "1"}


def _items(kind: str, first: int, last: int) -> list[dict]:
    if kind == "words":
        rows = json.loads((DATA / "frequency/core-words.json").read_text())
        return [{"rank": r["deck_rank"], "text": r["lemma"], "hint": r["english"], "kind": None,
                 "tags": ["core-words", _band(r["deck_rank"])]} for r in rows[first - 1 : last]]
    rows = json.loads((DATA / "frequency/phrases.json").read_text())
    return [{"rank": r["rank"], "text": r["german"], "kind": "phrase",
             "hint": r["english"] + (f" ({r['note']})" if r["note"] else ""),
             "tags": ["core-phrases", f"phrase-tier::{r['tier']}"]} for r in rows[first - 1 : last]]


def _band(rank: int) -> str:
    """core::0001-0100, core::0101-0200, …: one tag per hundred, for filtered decks."""
    start = (rank - 1) // 100 * 100 + 1
    return f"core::{start:04d}-{start + 99:04d}"


def draft(kind: str, first: int, last: int, http: httpx.Client) -> Path:
    def one(item: dict) -> dict:
        body = {"text": item["text"], "hint": item["hint"], "review": True,
                **({"kind": item["kind"]} if item["kind"] else {})}
        for _ in range(2):  # a draft that still lacks examples is drafted again
            r = _post(http, body)
            if isinstance(r, str) or r.status_code != 200:
                return {**item, "error": r if isinstance(r, str) else r.text[:300]}
            got = r.json()
            if item["kind"] == "phrase" or len(got["draft"]["examples"]) >= 2:
                break
        got["draft"]["tags"] += item["tags"]
        return {**item, **got}

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(one, _items(kind, first, last)))
    out = DATA / "batches" / f"{kind}-{first:04d}-{last:04d}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    for row in rows:
        _print(row)
    return out


def _post(http: httpx.Client, body: dict) -> httpx.Response | str:
    """POST a draft, retrying network errors and 5xx answers; a string is the last error."""
    for attempt in range(4):
        try:
            r = http.post(f"{API}/api/drafts", json=body)
            if r.status_code < 500:
                return r
            error = f"{r.status_code}: {r.text[:300]}"
        except httpx.TransportError as e:
            error = f"{type(e).__name__}: {e}"
        time.sleep(5 * (attempt + 1))
    return error


def _print(row: dict) -> None:
    if "error" in row:
        print(f"{row['rank']:>4} {row['text']}: ERROR {row['error']}")
        return
    d = row["draft"]
    head = f"{d['article']} {d['lemma']}".strip()
    flags = [c["message"] for c in row["checks"] if c["level"] == "warn" or c["message"].startswith("Review:")]
    if row["duplicates"]:
        flags.append("already in the collection: " + ", ".join(x["text"] for x in row["duplicates"]))
    print(f"{row['rank']:>4} [{d['kind']}] {head} = {d['meaning']}  {' '.join(d['tags'][:2])}")
    for ex in d["examples"]:
        print(f"       {ex['de']} | {ex['en']}")
    for f in flags + ([row["input_note"]] if row.get("input_note") else []):
        print(f"       ! {f}")


def save(name: str, http: httpx.Client) -> None:
    path = DATA / "batches" / f"{name}.json"
    rows = json.loads(path.read_text())
    for row in rows:
        if "error" in row or row.get("saved"):
            continue
        if row["duplicates"]:
            print(f"{row['rank']:>4} {row['draft']['lemma']}: skipped, already in the collection")
            continue
        r = http.post(f"{API}/api/notes", json={"draft": row["draft"]})
        if r.status_code != 201:
            print(f"{row['rank']:>4} {row['draft']['lemma']}: ERROR {r.text[:300]}")
            continue
        row["saved"] = r.json()["id"]
        print(f"{row['rank']:>4} {row['draft']['lemma']}: saved ({r.json()['audio']} audio)")
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))  # a rerun skips saved rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m card_generator.batch")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draft", help="draft a range of the list, save nothing")
    d.add_argument("kind", choices=["words", "phrases"])
    d.add_argument("range", help="ranks, e.g. 1-50")
    s = sub.add_parser("save", help="add a drafted batch to Anki")
    s.add_argument("name", help="batch name, e.g. words-0001-0050")
    args = parser.parse_args(argv)

    http = httpx.Client(headers=HEADERS, timeout=httpx.Timeout(10, read=300))
    if args.command == "draft":
        first, last = (int(x) for x in args.range.split("-"))
        print(f"\nDrafted to {draft(args.kind, first, last, http)}")
    else:
        save(args.name, http)
    return 0


if __name__ == "__main__":
    sys.exit(main())
