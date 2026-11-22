"""Finds which public job boards (Greenhouse, Lever, Ashby, SmartRecruiters) your companies use.

It tries likely board names for every company in the company lists and keeps a board only when it
has postings in India (and, where the board reports a company name, the name matches). The result
goes to jobhunt/boards.json, which the search step reads. Re-run it every month or two to pick up
companies that switch job boards.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import config, sources, tracker
from .matching import company_keys, mentions_india

GENERIC_WORDS = {
    "india", "in", "global", "tech", "group", "technologies", "technology", "labs", "systems",
    "cloud", "energy", "analytics", "innovation", "digital", "internet", "platforms", "data", "the",
    "ai", "by", "company",
}


def slug_candidates(name):
    """Likely board names: "Zeta Global" -> zetaglobal, zeta-global, zeta."""
    chunks = [re.sub(r"\(.*?\)", "", name)] + re.findall(r"\(([^)]*)\)", name)
    slugs = []
    for chunk in chunks:
        for part in chunk.split(","):
            words = re.findall(r"[a-z0-9]+", part.lower().replace("'", "").replace("&", ""))
            core = [w for w in words if w not in GENERIC_WORDS]
            for group in (words, core):
                if group:
                    slugs += ["".join(group), "-".join(group)]
    return [s for s in dict.fromkeys(slugs) if len(s) >= 3]


def count_india(texts_per_job):
    return sum(1 for texts in texts_per_job if mentions_india(" | ".join(t for t in texts if t)))


def display_names(company):
    """'Eternal (Zomato, Blinkit)' -> ['Eternal', 'Zomato', 'Blinkit']."""
    chunks = [re.sub(r"\(.*?\)", "", company)] + re.findall(r"\(([^)]*)\)", company)
    return [part.strip() for chunk in chunks for part in chunk.split(",") if part.strip()]


def belongs_to(company, slug, label, text):
    """Whether a board found under this slug is really this company's.

    Greenhouse and SmartRecruiters report a company name (label). Lever and Ashby don't, so the
    posting text must name the company: the full name for shortened slugs ("zeta" for Zeta Global
    could be another Zeta), or at least its first word when the slug is the whole name.
    """
    if label:
        return bool(company_keys(label) & company_keys(company))
    text = text.lower()

    def said(phrase):
        return bool(re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text))

    names = display_names(company)
    if any(said(name) for name in names):
        return True
    for name in names:
        words = re.findall(r"[a-z0-9]+", name.lower().replace("'", ""))
        if words and slug in ("".join(words), "-".join(words)) and said(words[0]):
            return True
    return False


def probe_greenhouse(slug):
    data = sources.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if data is None:
        return None
    jobs = data.get("jobs", [])
    label = jobs[0].get("company_name", "") if jobs else ""
    return count_india([[(j.get("location") or {}).get("name", "")] for j in jobs]), label, ""


def probe_lever(slug):
    data = sources.get_json(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
    if data is None:
        return None
    cats = [p.get("categories") or {} for p in data]
    text = " ".join((p.get("descriptionPlain") or "")[:3000] for p in data[:30])
    return count_india([[c.get("location") or ""] + list(c.get("allLocations") or []) for c in cats]), "", text


def probe_ashby(slug):
    data = sources.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if data is None:
        return None
    jobs = data.get("jobs", [])
    texts = []
    for job in jobs:
        items = [job.get("location") or "", json.dumps(job.get("address") or {})]
        items += [json.dumps(extra) for extra in job.get("secondaryLocations") or []]
        texts.append(items)
    text = " ".join((job.get("descriptionPlain") or "")[:3000] for job in jobs[:30])
    return count_india(texts), "", text


def probe_smartrecruiters(slug):
    data = sources.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                            {"country": "in", "limit": 1})
    if not data or not data.get("totalFound"):
        return None
    first = (data.get("content") or [{}])[0]
    return data["totalFound"], (first.get("company") or {}).get("name", ""), ""


PROBES = {
    "greenhouse": probe_greenhouse,
    "lever": probe_lever,
    "ashby": probe_ashby,
    "smartrecruiters": probe_smartrecruiters,
}


def safe_probe(task):
    _, ats, slug = task
    try:
        return PROBES[ats](slug)
    except Exception:
        return None


def check_workday(item):
    company, url = item
    try:
        host, tenant, site = sources.parse_workday_url(url)
        api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        data = sources.get_json(api, body={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "data engineer"})
        return company, "ok" if data is not None else "not found"
    except Exception as error:
        return company, str(error)[:80]


def discover():
    directory = tracker.company_directory()
    companies = list(dict.fromkeys(entry["name"] for entry in directory.values()))
    workday = set(config.WORKDAY_SITES)
    tasks = [(name, ats, slug) for name in companies for ats in PROBES for slug in slug_candidates(name)]
    print(f"Checking {len(companies)} companies ({len(tasks)} board names); this takes a minute or two...")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(safe_probe, tasks))

    best, name_mismatch = {}, []
    for (company, ats, slug), result in zip(tasks, results):
        if not result or result[0] <= 0:
            continue
        count, label, text = result
        if not belongs_to(company, slug, label, text):
            owner = f"'{label}'" if label else "postings that don't name the company"
            name_mismatch.append(f"{company} -> {ats}/{slug} has {owner}")
            continue
        if count > best.get((company, ats), {}).get("india_postings", 0):
            best[(company, ats)] = {"company": company, "ats": ats, "slug": slug, "india_postings": count,
                                    "checked_on": date.today().isoformat()}

    boards = sorted(best.values(), key=lambda b: (b["company"].lower(), b["ats"]))
    config.BOARDS_JSON.write_text(json.dumps(boards, indent=2) + "\n")

    covered = ({b["company"] for b in boards} | workday | {b["company"] for b in config.EXTRA_BOARDS}
               | {b["company"] for b in config.MANUAL_BOARDS})
    print(f"\nFound {len(boards)} job boards with postings in India:")
    for board in boards:
        print(f"  {board['ats']:<16} {board['company']} ({board['slug']}): {board['india_postings']} in India")
    if name_mismatch:
        print("\nIgnored because the board belongs to a different company:")
        for line in name_mismatch:
            print(f"  {line}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        broken = [(c, status) for c, status in pool.map(check_workday, config.WORKDAY_SITES.items()) if status != "ok"]
    print(f"\nWorkday sites in config.py: {len(workday) - len(broken)} of {len(workday)} respond.")
    for company, status in broken:
        print(f"  {company}: {status}")
    missing = [name for name in companies if name not in covered]
    print(f"\nCovered: {len(covered & set(companies))} of {len(companies)} companies.")
    print(f"No public board found for {len(missing)} (Google Jobs covers these when SERPAPI_KEY is set):")
    print("  " + ", ".join(missing))
    print(f"\nSaved {config.BOARDS_JSON.relative_to(config.ROOT)}")
