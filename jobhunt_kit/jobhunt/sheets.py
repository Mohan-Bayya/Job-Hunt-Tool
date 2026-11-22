"""Two-way sync between companies/applications.csv and the "Applications" tab of a Google Sheet.

The sheet is reached through a small Google Apps Script web app that you paste into the sheet once
(jobhunt/sheets_script.gs). The tool never needs your Google password.

How rows are merged (each row is matched by its job_key):
- Columns the tool owns (company, title, link, score, ...) are copied from the CSV to the sheet.
- status, applied_on and notes can be edited in either place. A change made on only one side is
  copied to the other. If both sides changed, the sheet wins.
- Rows you add by hand in the sheet are imported into the CSV, so searches never re-add those jobs.
- The sheet's existing tabs and any extra columns you add to the Applications tab are never touched.
"""
import hashlib
import json
from datetime import date

from . import config, sources, tracker

SHEET_COLS = [c for c in tracker.FIELDS if c != "fingerprint"]
# Columns you can edit in either place. The tool never fills in `applied` or `interested for referral`.
MERGE_COLS = ["status", "applied_on", "notes", "applied", "interested for referral"]
TOOL_COLS = [c for c in SHEET_COLS if c not in MERGE_COLS and c != "job_key"]


def configured():
    return bool(config.env_value("SHEETS_WEBAPP_URL") and config.env_value("SHEETS_TOKEN"))


def call(action, **payload):
    url, token = config.env_value("SHEETS_WEBAPP_URL"), config.env_value("SHEETS_TOKEN")
    reply = sources.get_json(url, body={"token": token, "action": action, **payload})
    if not isinstance(reply, dict):
        raise RuntimeError("the web app gave no answer; check SHEETS_WEBAPP_URL in jobhunt/.env")
    if not reply.get("ok"):
        raise RuntimeError(f"the sheet script said: {reply.get('error', 'unknown error')}")
    return reply


def manual_key(company, title):
    digest = hashlib.sha1(f"{company.strip().lower()}|{title.strip().lower()}".encode()).hexdigest()[:10]
    return f"manual:{digest}"


def key_of(row):
    return row.get("job_key") or manual_key(row.get("company") or "", row.get("title") or "")


def load_state():
    return json.loads(config.SYNC_STATE_JSON.read_text()) if config.SYNC_STATE_JSON.exists() else {}


def resolve(mine, theirs, base):
    """Decide one merge cell. Returns (value, where) with where in same / sheet / csv / conflict."""
    if mine == theirs:
        return mine, "same"
    if base is not None:
        if base == theirs:
            return mine, "csv"          # only the CSV changed
        if base == mine:
            return theirs, "sheet"      # only the sheet changed
        return theirs, "conflict"       # both changed: the sheet wins
    if theirs == "":
        return mine, "csv"
    if mine == "":
        return theirs, "sheet"
    return theirs, "conflict"


def sync():
    """Sync once. Returns a summary dict, or None if Google Sheets isn't set up."""
    if not configured():
        return None
    today = date.today().isoformat()
    rows = tracker.load()
    state = load_state()
    sheet = call("read")
    updates, appends = [], []
    summary = {"added_to_sheet": 0, "updated_in_sheet": 0, "pulled_into_csv": 0,
               "imported": 0, "conflicts": 0}

    by_key = {}
    for s in sheet.get("rows", []):
        company, title = (s.get("company") or "").strip(), (s.get("title") or "").strip()
        if not company or not title:
            continue  # blank or half-typed row
        key = (s.get("job_key") or "").strip()
        if not key:
            key = manual_key(company, title)
            updates.append({"row": s["_row"], "cells": {"job_key": key}})
        by_key.setdefault(key, s)

    csv_rows = {key_of(r): r for r in rows}
    csv_changed = False
    newly_applied = []

    for key, row in csv_rows.items():
        s = by_key.get(key)
        if s is None:
            cells = {c: row.get(c) or "" for c in SHEET_COLS}
            cells["job_key"] = key
            appends.append(cells)
            state[key] = {c: row.get(c) or "" for c in MERGE_COLS}
            summary["added_to_sheet"] += 1
            continue
        cells = {c: row.get(c) or "" for c in TOOL_COLS if (row.get(c) or "") != s.get(c, "")}
        last = state.get(key)
        remembered = dict(last) if last else {}
        for col in MERGE_COLS:
            mine, theirs = row.get(col) or "", s.get(col, "")
            value, where = resolve(mine, theirs, remembered.get(col) if last else None)
            if where == "csv":
                cells[col] = value
            elif where in ("sheet", "conflict"):
                if col == "status" and value == tracker.APPLIED and mine != tracker.APPLIED:
                    newly_applied.append(row)
                row[col] = value
                csv_changed = True
                summary["pulled_into_csv"] += 1
                summary["conflicts"] += where == "conflict"
            remembered[col] = value
        state[key] = remembered
        if cells:
            updates.append({"row": s["_row"], "cells": cells})
            summary["updated_in_sheet"] += 1

    for key, s in by_key.items():
        if key in csv_rows:
            continue
        row = {field: "" for field in tracker.FIELDS}
        for col in SHEET_COLS:
            row[col] = s.get(col, "")
        row["job_key"] = key
        fill = {}
        if not row["source"]:
            row["source"] = "manual"
            fill["source"] = "manual"
        if not row["found_on"]:
            row["found_on"] = today
            fill["found_on"] = today
        if not row["status"]:
            row["status"] = tracker.APPLIED if row["applied_on"] else tracker.TO_APPLY
            fill["status"] = row["status"]
        if fill:
            updates.append({"row": s["_row"], "cells": fill})
        rows.append(row)
        csv_changed = True
        state[key] = {c: row.get(c) or "" for c in MERGE_COLS}
        summary["imported"] += 1
        if row["status"] == tracker.APPLIED:
            newly_applied.append(row)

    if updates or appends:
        call("write", updates=updates, appends=appends)
    for row in newly_applied:
        if not row.get("applied_on"):
            row["applied_on"] = today
        tracker.mark_company_applied(row["company"], row["title"], row["applied_on"])
    if csv_changed or newly_applied:
        tracker.save(rows)
    config.SYNC_STATE_JSON.write_text(json.dumps(state, indent=1) + "\n")
    return summary


def describe(summary):
    parts = [f"{n} {text}" for key, text in (
        ("added_to_sheet", "added to the sheet"), ("updated_in_sheet", "updated in the sheet"),
        ("pulled_into_csv", "changes copied from the sheet"), ("imported", "rows imported from the sheet"),
        ("conflicts", "conflicts (the sheet's value was kept)")) if (n := summary[key])]
    return ", ".join(parts) if parts else "already in sync"


def sync_quietly():
    """Sync, and never let a Google Sheets problem stop the search or apply steps."""
    try:
        summary = sync()
    except Exception as error:
        print(f"Google Sheets sync failed ({error}). The CSV is saved; run `python3 -m jobhunt sync` to retry.")
        return None
    if summary is not None:
        print(f"Google Sheets: {describe(summary)}.")
    return summary
