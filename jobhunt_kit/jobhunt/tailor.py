"""Builds a resume for one posting by reordering the real content of build_resume_final.py.

Nothing is invented. The tailored resume uses the same summary, the same skill wording and the same
bullets (plus any you list in resume.EXTRA_BULLETS). Only these change:
- the headline lists the posting's skills first,
- each skills row lists the posting's skills first,
- the current-job bullets are ordered by how well they match the posting and the company's
  category (the "Lead with" notes in companies/target_companies.md).
"""
import contextlib
import copy
import hashlib
import io
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

from . import config
from .matching import WEIGHTS, skills_in
from .resume import EXTRA_BULLETS, base

TOPICS = {
    "ads": r"\bads?\b|advertis|ad[- ]tech|programmatic|campaign|impression|audience|martech|marketing",
    "location": r"geospatial|geohash|location data|location intelligence|\bpoi\b|mobility|\bmaps?\b|"
                r"\bgps\b|postcode|sedona|devices",
    "travel": r"travel|airline|hotel|booking|visitor|tourism|hospitality",
    "media": r"\bmedia\b|\bnews\b|publisher|streaming|readers|\bott\b",
    "measurement": r"measurement|attribution|test-and-control|\blift\b|incrementality|experiment",
    "quality": r"data quality|validat|quality checks|\btests?\b|accuracy|recall|reliab|runbook|"
               r"root[- ]cause|\bsla\b",
    "performance": r"runtime|optimi[sz]|performance|skew|broadcast join|\baqe\b|partition|tuning|"
                   r"latency|faster|\bscal(e|ing|able)\b",
    "cost": r"\bcost|duplicate|efficien|once instead",
    "privacy": r"privacy|\bpii\b|hashing|privacy-safe|gdpr|consent",
    "production": r"production|on-call|incident|support",
}
TOPIC_RX = {name: re.compile(rx, re.I) for name, rx in TOPICS.items()}

# Mirrors the "Lead with" note for each category in companies/target_companies.md.
CATEGORY_TOPICS = {
    "Ad-tech, martech and customer data": ["ads", "privacy", "measurement"],
    "Location, mobility and logistics": ["location"],
    "Travel and hospitality": ["travel", "measurement"],
    "Media, streaming and measurement": ["media", "measurement"],
    "Consumer internet and commerce": ["performance", "cost", "production"],
    "Fintech and payments": ["quality", "production"],
    "Data platforms and B2B SaaS": ["performance"],
    "Global capability centers (GCCs)": ["performance", "cost"],
}


STEM = base.NAME.replace(" ", "_") + "_Resume"  # file name inside each tailored folder



def resume_pdf(value):
    """The PDF for a tracker `resume` cell, which holds just the folder name inside tailored/.

    Older rows held a path from the resume folder (generated (resume)/tailored/<folder>/<file>.pdf);
    those still resolve.
    """
    if not value:
        return None
    if "/" in value:
        return config.ROOT / value
    return config.TAILORED_DIR / value / f"{STEM}.pdf"


def topics_in(text):
    return {name for name, rx in TOPIC_RX.items() if rx.search(text)}


def posting_skills(text):
    """Skills a posting asks for. "Spark" and "PySpark" count as the same ask."""
    asked = skills_in(text)
    if asked & {"Spark", "PySpark"}:
        asked |= {"Spark", "PySpark"}
    return asked


def split_items(items):
    """Split "A, B (x, y), C" on top-level commas only."""
    parts, depth, current = [], 0, ""
    for char in items:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def tailor_headline(headline, asked):
    title, *skills = [part.strip() for part in headline.split("|")]
    pool = skills + [s for s in ("Python",) if s not in skills]
    hits = [s for s in pool if skills_in(s) & asked]
    chosen = (hits + [s for s in skills if s not in hits])[:len(skills)]
    return " | ".join([title] + chosen)


def tailor_skills(skills, asked):
    rows = []
    for category, items in skills:
        parts = split_items(items)
        hits = [p for p in parts if skills_in(p) & asked]
        rows.append((category, ", ".join(hits + [p for p in parts if p not in hits])))
    return rows


def rank_bullets(bullets, posting_text, asked, category):
    """Order bullets by matching skills and topics; ties keep the original order.

    A topic the company's category calls for counts a little more than one the posting mentions,
    so the "Lead with" notes win over incidental words in the job description.
    """
    posting_topics = topics_in(posting_text)
    category_topics = set(CATEGORY_TOPICS.get(category, []))
    scored = []
    for index, bullet in enumerate(bullets):
        text = bullet.replace("**", "")
        topics = topics_in(text)
        points = sum(WEIGHTS[s] for s in skills_in(text) & asked)
        points += 2 * len(topics & posting_topics) + 3 * len(topics & category_topics)
        scored.append((-points, index, bullet))
    return [bullet for _, _, bullet in sorted(scored)]


def folder_for(job, day):
    def slug(text):
        return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40]
    digest = hashlib.sha1(job.key.encode()).hexdigest()[:6]
    return config.TAILORED_DIR / f"{day}_{slug(job.company)}_{slug(job.title)}_{digest}"


def render(patch, pdf_path, docx_path):
    """Build PDF and DOCX with build_resume.py after swapping in the tailored content."""
    saved = {name: getattr(base, name) for name in patch}
    output = io.StringIO()
    try:
        for name, value in patch.items():
            setattr(base, name, value)
        with contextlib.redirect_stdout(output):
            base.build_pdf(str(pdf_path))
            base.build_docx(str(docx_path))
    finally:
        for name, value in saved.items():
            setattr(base, name, value)
    return [line for line in output.getvalue().splitlines() if line.startswith("WARNING")]


@lru_cache(maxsize=1)
def base_warnings():
    """Layout warnings the untailored resume already has, so they aren't reported for every job."""
    with tempfile.TemporaryDirectory() as folder:
        return frozenset(render({}, Path(folder) / "base.pdf", Path(folder) / "base.docx"))


def alt_paths(folder):
    """(pdf, docx) of the second resume: same file names as the main one, in the referral subfolder."""
    sub = Path(folder) / config.ALT_DIR
    return sub / f"{STEM}.pdf", sub / f"{STEM}.docx"


def alt_pdf(folder):
    """The second resume in a tailored folder: same content, different email address."""
    return alt_paths(folder)[0]


def build(job, category, folder, only_alt=False):
    """Write the tailored PDF and DOCX into folder, plus a second copy that uses config.ALT_EMAIL.

    Both copies have identical content; only the email address differs. With only_alt=True just the
    second copy is written (used to add it to folders built before it existed).
    Returns (pdf_path, warnings), where warnings are layout problems that tailoring introduced.
    """
    posting_text = job.title + "\n" + job.description
    asked = posting_skills(posting_text)
    current = base.EXPERIENCE[0]
    count = len(current["bullets"])
    ranked = rank_bullets(current["bullets"] + EXTRA_BULLETS, posting_text, asked, category)

    experience = copy.deepcopy(base.EXPERIENCE)
    experience[0]["bullets"] = ranked[:count]
    patch = {
        "HEADLINE": tailor_headline(base.HEADLINE, asked),
        "SKILLS": tailor_skills(base.SKILLS, asked),
        "EXPERIENCE": experience,
    }
    folder = Path(folder)
    pdf_path, docx_path = folder / f"{STEM}.pdf", folder / f"{STEM}.docx"
    alt_email = config.ALT_EMAIL if config.ALT_EMAIL and config.ALT_EMAIL != base.EMAIL else ""
    if only_alt and not alt_email:
        return pdf_path, []
    # The copy that decides how many bullets fit on one page: the main one, or the alternate one.
    if alt_email:
        alt_paths(folder)[0].parent.mkdir(parents=True, exist_ok=True)
    first = ({**patch, "EMAIL": alt_email}, *alt_paths(folder)) if only_alt else (patch, pdf_path, docx_path)
    while True:
        warnings = render(first[0], first[1], first[2])
        pages = len(PdfReader(str(first[1])).pages)
        if pages == 1 or len(experience[0]["bullets"]) <= count - 2:
            break
        experience[0]["bullets"].pop()  # drop the weakest bullet until it fits on one page
    if alt_email and not only_alt:
        render({**patch, "EMAIL": alt_email}, *alt_paths(folder))
    return pdf_path, [w for w in warnings if w not in base_warnings()]
