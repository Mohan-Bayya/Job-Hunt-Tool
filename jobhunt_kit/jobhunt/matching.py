"""Decides which postings fit and scores each one against the resume."""
import re
from datetime import date

from . import config

INDIAN_CITIES = [
    "bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai", "navi mumbai", "gurugram",
    "gurgaon", "noida", "delhi", "new delhi", "kolkata", "ahmedabad", "kochi", "jaipur", "indore",
    "coimbatore", "thiruvananthapuram", "trivandrum", "mysuru", "mysore", "chandigarh", "vadodara",
]
INDIAN_STATES = [
    "karnataka", "maharashtra", "telangana", "tamil nadu", "haryana", "uttar pradesh", "kerala",
    "gujarat", "west bengal", "rajasthan",
]
VAGUE_LOCATIONS = {"", "anywhere", "remote", "worldwide", "global", "work from home"}


def _words(words):
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)


INDIA_RX = _words(["india"] + INDIAN_CITIES + INDIAN_STATES)
CITY_RX = _words(INDIAN_CITIES)
WANTED_RX = _words(config.CITIES)
REMOTE_RX = re.compile(r"\b(remote|virtual|work from home|wfh|anywhere)\b", re.I)
INCLUDE_RX = [re.compile(p, re.I) for p in config.TITLE_INCLUDE]
EXCLUDE_RX = [re.compile(p, re.I) for p in config.TITLE_EXCLUDE]
SKILL_RX = [(name, re.compile(rx, re.I), weight) for name, rx, weight in config.SKILL_TERMS]
WEIGHTS = {name: weight for name, _, weight in SKILL_RX}
ORDER = {name: i for i, (name, _, _) in enumerate(SKILL_RX)}
YEARS_RX = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|—|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b", re.I)
COMPANY_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "pvt", "private", "corp", "corporation", "co", "company",
    "companies", "india", "in", "technologies", "technology", "tech", "global", "group", "solutions",
    "services", "software", "labs",
}


# ------------------------------------------------------------------------ Names


def company_keys(name):
    """Normalized keys for a company name, including names in parentheses.

    "InMobi Technologies Pvt. Ltd." -> {"inmobi"}; "Eternal (Zomato, Blinkit)" -> {"eternal",
    "zomato", "blinkit"}. Used to match the same company across sources and the company lists.
    """
    names = [re.sub(r"\(.*?\)", "", name)] + re.findall(r"\(([^)]*)\)", name)
    keys = set()
    for chunk in names:
        for part in chunk.split(","):
            words = re.findall(r"[a-z0-9]+", part.lower().replace("&", "").replace("'", ""))
            while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
                words.pop()
            if words and words[0] == "the" and len(words) > 1:
                words.pop(0)
            if words:
                keys.add("".join(words))
    return keys


def title_key(title):
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


# ------------------------------------------------------------------------ Filters


def mentions_india(text):
    return bool(INDIA_RX.search(text or ""))


def title_ok(title):
    title = title.replace("_", " ")  # "Data Engineer_Vice President" should still read as two words
    return any(rx.search(title) for rx in INCLUDE_RX) and not any(rx.search(title) for rx in EXCLUDE_RX)


def too_old(posted):
    return posted is not None and (date.today() - posted).days > config.MAX_AGE_DAYS


def prefilter(title, posted):
    """Cheap check run while fetching, so detail pages are only requested for likely matches."""
    return title_ok(title) and not too_old(posted)


def location_reason(job):
    """Why the location fits ("city", "remote", "india"), or None if it doesn't."""
    text = " | ".join(job.locations)
    if WANTED_RX.search(text):
        return "city"
    remote = job.remote or bool(REMOTE_RX.search(text))
    if config.INCLUDE_REMOTE_INDIA and remote:
        if mentions_india(text):
            return "remote"
        vague = all(loc.strip().lower() in VAGUE_LOCATIONS for loc in job.locations)
        if vague and mentions_india(job.description):
            return "remote"
    if config.INCLUDE_INDIA_NO_CITY and mentions_india(text) and not CITY_RX.search(text):
        return "india"
    return None


def years_required(text):
    """Lowest number of years asked for in sentences that mention experience, or None."""
    found = []
    for sentence in re.split(r"(?<=[.;\n])", text or ""):
        if not re.search(r"experience|\bexp\b", sentence, re.I):
            continue
        found += [int(m.group(1)) for m in YEARS_RX.finditer(sentence) if int(m.group(1)) <= 15]
    return min(found) if found else None


EXCLUDED_KEYS = {key for name in config.EXCLUDE_COMPANIES for key in company_keys(name)}


def excluded_company(company):
    return bool(company_keys(company) & EXCLUDED_KEYS)


# ------------------------------------------------------------------------ Skills and score


def skills_in(text):
    return {name for name, rx, _ in SKILL_RX if rx.search(text or "")}


def resume_skills():
    from .resume import skills_text
    return skills_in(skills_text())


def sort_skills(names):
    return sorted(names, key=lambda n: ORDER.get(n, 999))


def score(text, have):
    """Return (score 0-100, skills you have that the posting asks for, skills you don't have).

    The score is 70% "share of the posting's skills you have" and 30% "how much of your core
    stack it asks for", so a posting that only lists SQL doesn't outrank a full PySpark/AWS match.
    """
    asked = skills_in(text)
    matched, missing = asked & have, asked - have
    forgiven = set()
    for first, alternatives in config.ALTERNATIVES.items():
        if first in matched:
            forgiven |= set(alternatives)
    have_weight = sum(WEIGHTS[s] for s in matched)
    miss_weight = sum(WEIGHTS[s] for s in missing - forgiven)
    if not have_weight:
        return 0, [], sort_skills(missing)
    share = have_weight / (have_weight + miss_weight)
    value = round(100 * (0.7 * share + 0.3 * min(1.0, have_weight / 12)))
    return value, sort_skills(matched), sort_skills(missing)


def assess(job, have):
    """Run every filter. Returns a dict with keep=True and match details, or keep=False and why."""
    if excluded_company(job.company):
        return {"keep": False, "why": "excluded company"}
    if not title_ok(job.title):
        return {"keep": False, "why": "title"}
    if too_old(job.posted):
        return {"keep": False, "why": "too old"}
    where = location_reason(job)
    if not where:
        return {"keep": False, "why": "location"}
    years = years_required(job.description)
    # Reposted listings often put the requirement in the title ("... | 5 to 10 years | ...").
    in_title = [int(m.group(1)) for m in YEARS_RX.finditer(job.title) if int(m.group(1)) <= 15]
    if in_title:
        years = min(in_title) if years is None else min(years, min(in_title))
    if years is not None and years > config.MAX_YEARS_REQUIRED:
        return {"keep": False, "why": "experience"}
    value, matched, missing = score(job.title + "\n" + job.description, have)
    if not set(matched) & set(config.REQUIRE_ANY_SKILL):
        return {"keep": False, "why": "no core skill"}
    if value < config.MIN_SCORE:
        return {"keep": False, "why": "low score"}
    return {"keep": True, "score": value, "matched": matched, "missing": missing,
            "years": years, "where": where}
