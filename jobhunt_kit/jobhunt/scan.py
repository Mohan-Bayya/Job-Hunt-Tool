"""Scans thousands of company job boards (not just your target list) for openings in India.

The board names come from community-kept lists (config.SLUG_LISTS). A board is kept when it has at
least one posting located in India; the result goes to jobhunt/boards_wide.json and the daily
search reads it. Boards with nothing in India today are dropped, so run this about once a week to
pick up companies that start hiring in India.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from . import config, discover, sources


def pretty(slug):
    """'acme-data-labs' -> 'Acme Data Labs' (used when the board doesn't report a company name)."""
    return " ".join(word.capitalize() for word in re.split(r"[-_]+", slug) if word)


def load_slugs():
    slugs = []
    for ats, url in config.SLUG_LISTS.items():
        names = sources.get_json(url) or []
        slugs += [(ats, name) for name in dict.fromkeys(names) if isinstance(name, str) and name]
        print(f"  {ats}: {len(names)} boards in the list")
    return slugs


def probe(task):
    ats, slug = task
    try:
        result = discover.PROBES[ats](slug)
    except Exception:
        return task, None
    if not result or result[0] <= 0:
        return task, None
    count, label, _ = result
    return task, {"company": label or pretty(slug), "ats": ats, "slug": slug, "india_postings": count,
                  "checked_on": date.today().isoformat()}


def scan(workers=12):
    print("Loading board lists...")
    tasks = load_slugs()
    print(f"Checking {len(tasks)} boards for postings in India (takes roughly 10-20 minutes)...", flush=True)
    found, started = [], time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(probe, task) for task in tasks]
        for done, future in enumerate(as_completed(futures), 1):
            _, board = future.result()
            if board:
                found.append(board)
            if done % 1000 == 0:
                print(f"  {done}/{len(tasks)} checked, {len(found)} boards with India postings "
                      f"({int(time.time() - started)}s)", flush=True)
    found.sort(key=lambda b: (b["company"].lower(), b["ats"]))
    config.WIDE_BOARDS_JSON.write_text(json.dumps(found, indent=1) + "\n")
    print(f"\nSaved {len(found)} boards with India postings to {config.WIDE_BOARDS_JSON.relative_to(config.ROOT)}")
    print(f"{sum(b['india_postings'] for b in found)} India postings across them right now.")
