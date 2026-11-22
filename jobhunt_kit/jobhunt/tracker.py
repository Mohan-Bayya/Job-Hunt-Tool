"""The job-level tracker (companies/applications.csv) and status updates in the company lists.

CSV files are written the way the existing company lists are saved (UTF-8 with BOM, CRLF line
endings) so they keep opening cleanly in Excel and Numbers.
"""
import csv
import os
import shutil
import tempfile

from . import config
from .matching import company_keys

# Same columns, in the same order, as the Applications tab of the Google Sheet. "fingerprint" is the
# only column that exists just in the CSV (it is how repeat postings are recognised).
FIELDS = [
    "found_on", "posted_on", "applied_on", "status", "score", "company", "title", "location",
    "years_required", "matched_skills", "missing_skills", "job_url", "resume", "applied",
    "interested for referral", "source", "job_key", "notes", "fingerprint",
]
TO_APPLY, APPLIED, NOT_A_FIT = "To apply", "Applied", "Not a fit"


def read_csv(path):
    """Return (fieldnames, rows, newline) for a CSV file, or ([], [], CRLF) if it doesn't exist."""
    if not path.exists():
        return [], [], "\r\n"
    with open(path, "rb") as handle:
        newline = "\r\n" if b"\r\n" in handle.read(4096) else "\n"
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader), newline


def write_csv(path, fields, rows, newline="\r\n"):
    """Write to a temp file first, then copy over the original (keeps its Finder metadata)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".csv")
    try:
        with os.fdopen(handle, "w", newline="", encoding="utf-8-sig") as out:
            writer = csv.DictWriter(out, fieldnames=fields, lineterminator=newline, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        shutil.copyfile(temp, path)
    finally:
        os.remove(temp)


def load(path=None):
    return read_csv(path or config.TRACKER_CSV)[1]


def save(rows, path=None):
    write_csv(path or config.TRACKER_CSV, FIELDS, rows)


def company_directory(paths=None):
    """Company key -> {"name", "category", "star"} from the company lists.

    "star" is the Tier 1 (★) priority from target_companies.csv; "category" picks which resume
    bullets to lead with.
    """
    directory = {}
    for path in paths or config.COMPANY_CSVS:
        for row in read_csv(path)[1]:
            name = (row.get("Company") or "").strip()
            if not name:
                continue
            entry = {"name": name, "category": row.get("Category") or "", "star": row.get("Priority") == "Tier 1"}
            for key in company_keys(name):
                known = directory.setdefault(key, entry)
                known["category"] = known["category"] or entry["category"]
                known["star"] = known["star"] or entry["star"]
    return directory


def lookup(directory, company):
    for key in company_keys(company):
        if key in directory:
            return directory[key]
    return None


def mark_company_applied(company, title, day, paths=None):
    """Set Status/Date applied/Notes for the company in each company list. Returns updated file names."""
    keys = company_keys(company)
    updated = []
    for path in paths or config.COMPANY_CSVS:
        fields, rows, newline = read_csv(path)
        hit = False
        for row in rows:
            if company_keys(row.get("Company") or "") & keys:
                row["Status"] = "Applied"
                row["Date applied"] = day
                entry = f"Applied: {title} ({day})"
                notes = row.get("Notes") or ""
                if entry not in notes:
                    row["Notes"] = f"{notes}; {entry}" if notes else entry
                hit = True
        if hit:
            write_csv(path, fields, rows, newline)
            updated.append(path.name)
    return updated
