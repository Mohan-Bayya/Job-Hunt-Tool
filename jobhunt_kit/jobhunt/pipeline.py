"""The search and apply steps."""
import hashlib
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from . import config, discover, matching, sheets, sources, tailor, tracker


def serpapi_key():
    """SERPAPI_KEY from the environment, or from jobhunt/.env (KEY=value lines)."""
    if os.environ.get("SERPAPI_KEY"):
        return os.environ["SERPAPI_KEY"].strip()
    if config.ENV_FILE.exists():
        for line in config.ENV_FILE.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "SERPAPI_KEY" and value.strip():
                return value.strip().strip("'\"")
    return ""


def load_boards():
    """Target-company boards, the wider boards found by `scan`, Workday sites, and own-feed sites."""
    boards = json.loads(config.BOARDS_JSON.read_text()) if config.BOARDS_JSON.exists() else []
    boards += [b for b in config.MANUAL_BOARDS
               if not any(b["ats"] == x["ats"] and b["slug"].lower() == x["slug"].lower() for x in boards)]
    known = {(b["ats"], b["slug"].lower()) for b in boards}
    if config.WIDE_BOARDS_JSON.exists():
        boards += [dict(b, wide=True) for b in json.loads(config.WIDE_BOARDS_JSON.read_text())
                   if (b["ats"], b["slug"].lower()) not in known]
    boards += [{"company": name, "ats": "workday", "url": url} for name, url in config.WORKDAY_SITES.items()]
    boards += config.EXTRA_BOARDS
    return boards


def fetch_all(boards):
    jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(sources.FETCHERS[b["ats"]], b, matching.prefilter): b for b in boards}
        if config.WORKABLE_SEARCHES:
            futures[pool.submit(sources.workable_aggregator, config.WORKABLE_SEARCHES, matching.prefilter)] = \
                {"company": "Workable job site", "ats": "workable"}
        for future in as_completed(futures):
            board = futures[future]
            try:
                jobs += future.result()
            except Exception as error:  # one broken board shouldn't stop the run
                errors.append(f"{board['company']} ({board['ats']}): {error}")
    key = serpapi_key()
    if key and config.GOOGLE_JOBS_SEARCHES:
        try:
            jobs += sources.google_jobs(config.GOOGLE_JOBS_SEARCHES, key, matching.prefilter)
        except Exception as error:
            errors.append(f"Google Jobs: {error}")
    if key and google_companies_due():
        searches = company_searches(boards)
        try:
            jobs += sources.google_jobs(searches, key, matching.prefilter)
            save_state(google_companies_last=date.today().isoformat())
            print(f"Google Jobs company searches: {len(searches)} searches for companies without a public job feed.")
        except Exception as error:
            errors.append(f"Google Jobs (companies): {error}")
    return jobs, errors


def load_state():
    return json.loads(config.STATE_JSON.read_text()) if config.STATE_JSON.exists() else {}


def save_state(**values):
    config.STATE_JSON.write_text(json.dumps({**load_state(), **values}, indent=1) + "\n")


def google_companies_due():
    last = load_state().get("google_companies_last")
    return not last or (date.today() - date.fromisoformat(last)).days >= config.GOOGLE_COMPANY_EVERY_DAYS


def uncovered_companies(boards):
    """Companies on your lists that none of the boards, Workday sites or own-feed sites cover."""
    covered = set()
    for board in boards:
        if not board.get("wide"):  # wide boards aren't checked against the company name
            covered |= matching.company_keys(board["company"])
    names = {}
    for entry in tracker.company_directory().values():
        names[entry["name"]] = entry
    return [name for name in names
            if not matching.company_keys(name) & covered and not matching.excluded_company(name)]


def company_searches(boards):
    """Google Jobs searches that each cover a few uncovered companies, e.g.
    ('data engineer (PhonePe OR Zepto OR Flipkart OR Uber)', 'India')."""
    names = []
    for company in uncovered_companies(boards):
        names += [n for n in discover.display_names(company)[:2] if n not in names]
    size = config.GOOGLE_GROUP_SIZE
    return [("data engineer (" + " OR ".join(f'"{n}"' if " " in n else n for n in names[i:i + size]) + ")", "India")
            for i in range(0, len(names), size)]


def _run(command, **options):
    """subprocess.run that does nothing when the command isn't installed (open, pbcopy and
    osascript are macOS tools)."""
    try:
        return subprocess.run(command, **options)
    except FileNotFoundError:
        return None


def notify(message):
    message = message.replace('"', "'")
    _run(["osascript", "-e", f'display notification "{message}" with title "Job search"'],
                   check=False, capture_output=True)


def write_job_file(folder, job, result):
    """Save the posting next to its resume; postings often disappear before the interview."""
    experience = "not stated" if result["years"] is None else f"{result['years']}+ years"
    lines = [
        f"# {job.title} at {job.company}",
        "",
        f"- Location: {job.location}",
        f"- Posted: {job.posted or 'unknown'}",
        f"- Link: {job.url}",
        f"- Match score: {result['score']}",
        f"- Skills you have: {', '.join(result['matched'])}",
        f"- Not on your resume: {', '.join(result['missing']) or 'none'}",
        f"- Experience asked: {experience}",
        "",
        "## Job description",
        "",
        job.description,
        "",
    ]
    (folder / "job.md").write_text("\n".join(lines), encoding="utf-8")


def search(dry_run=False, send_notification=False):
    boards = load_boards()
    if not config.BOARDS_JSON.exists():
        print("No company boards yet, so only Workday sites are searched. Run: python3 -m jobhunt discover")
    jobs, errors = fetch_all(boards)
    have = matching.resume_skills()
    directory = tracker.company_directory()
    if not dry_run:
        sheets.sync_quietly()  # picks up rows you added by hand in the sheet, so they aren't found again
    rows = tracker.load()
    seen_keys = {row["job_key"] for row in rows}
    seen_prints = {row.get("fingerprint") for row in rows if row.get("fingerprint")}
    earlier = {}  # (company key, title key) -> tracker rows with that company and title
    for row in rows:
        for key in matching.company_keys(row["company"]):
            earlier.setdefault((key, matching.title_key(row["title"])), []).append(row)

    # Duplicates: the same posting can come from a company board and from Google Jobs, or be posted
    # twice with identical text. Different openings on one board with the same title (Cisco posts
    # several "Data Engineer" roles) have their own IDs and text, so they are kept.
    matches, skipped, batch = [], Counter(), {}
    for job in jobs:
        info = tracker.lookup(directory, job.company)
        if info:
            job.company = info["name"]
        pairs = {(key, matching.title_key(job.title)) for key in matching.company_keys(job.company)}
        before = [row for pair in pairs for row in earlier.get(pair, [])]
        if job.key in seen_keys or any(row["source"] != job.source for row in before):
            skipped["already in tracker"] += 1
            continue
        signature = hashlib.sha1((job.location + job.description).encode()).hexdigest()[:12]
        in_batch = [entry for pair in pairs for entry in batch.get(pair, [])]
        if signature in seen_prints or any(src != job.source or sig == signature for src, sig in in_batch):
            skipped["duplicate posting"] += 1
            continue
        result = matching.assess(job, have)
        if not result["keep"]:
            skipped[result["why"]] += 1
            continue
        result["fingerprint"] = signature
        for pair in pairs:
            batch.setdefault(pair, []).append((job.source, signature))
        if before:
            result["note"] = (f"Same title as an earlier {job.company} posting "
                              f"({before[0]['status']}, found {before[0]['found_on']})")
        star = bool(info and info["star"])
        matches.append((result["score"] + (10 if star else 0), job, result, info or {}))
    matches.sort(key=lambda item: -item[0])

    print(f"Searched {len(boards)} company boards, the Workable job site"
          f"{' and Google Jobs' if serpapi_key() else ''}: {len(jobs)} postings with a matching title.")
    if skipped:
        print("Skipped: " + ", ".join(f"{why} {n}" for why, n in skipped.most_common()))
    for message in errors[:8]:
        print(f"  could not fetch {message}")
    if len(errors) > 8:
        print(f"  ... and {len(errors) - 8} more boards could not be fetched")
    print(f"New matches: {len(matches)}")
    for _, job, result, info in matches:
        star = "★ " if info.get("star") else ""
        print(f"  {result['score']:>3}  {star}{job.company} | {job.title} | {job.location[:60]}")
    if dry_run or not matches:
        if send_notification and not dry_run:
            notify("No new matching jobs today.")
        return

    today = date.today().isoformat()
    for _, job, result, info in matches:
        folder = tailor.folder_for(job, today)
        folder.mkdir(parents=True, exist_ok=True)
        write_job_file(folder, job, result)
        notes = [result["note"]] if result.get("note") else []
        try:
            pdf_path, warnings = tailor.build(job, info.get("category", ""), folder)
            resume = pdf_path.parent.name
            if warnings:
                notes.append("layout: " + " / ".join(warnings))
        except Exception as error:
            resume = folder.name
            notes.append(f"resume build failed: {error}")
        note = "; ".join(notes)
        rows.append({
            "found_on": today, "status": tracker.TO_APPLY, "score": result["score"],
            "company": job.company, "title": job.title, "location": job.location,
            "years_required": "" if result["years"] is None else result["years"],
            "matched_skills": ", ".join(result["matched"]), "missing_skills": ", ".join(result["missing"]),
            "job_url": job.url, "resume": resume, "applied_on": "", "notes": note,
            "source": job.source, "posted_on": job.posted.isoformat() if job.posted else "",
            "job_key": job.key, "fingerprint": result["fingerprint"],
        })
    tracker.save(rows)
    sheets.sync_quietly()
    waiting = sum(1 for row in rows if row["status"] == tracker.TO_APPLY)
    print(f"Added {len(matches)} jobs to {config.TRACKER_CSV.relative_to(config.ROOT)} with tailored resumes in "
          f"{config.TAILORED_DIR.relative_to(config.ROOT)}/. {waiting} jobs are waiting. Next: python3 -m jobhunt apply")
    if send_notification:
        notify(f"{len(matches)} new jobs matched. {waiting} ready to apply: python3 -m jobhunt apply")


def ask(prompt, default="q"):
    try:
        return input(prompt).strip()
    except EOFError:
        return default


def apply(open_pages=True):
    sheets.sync_quietly()  # so jobs you already marked in the sheet (for example from your phone) are skipped
    rows = tracker.load()
    directory = tracker.company_directory()
    queue = [row for row in rows if row["status"] == tracker.TO_APPLY]
    if not queue:
        print("Nothing waiting. Run: python3 -m jobhunt search")
        return

    def priority(row):
        info = tracker.lookup(directory, row["company"]) or {}
        return -(int(row["score"] or 0) + (10 if info.get("star") else 0))

    queue.sort(key=priority)
    print(f"{len(queue)} jobs to apply to.")
    if open_pages:
        print("Each posting opens in your browser and its resume path is copied: in the file-upload "
              "dialog press Cmd+Shift+G, paste, and press Enter.")
    print()
    today = date.today().isoformat()
    applied = 0
    for number, row in enumerate(queue, 1):
        info = tracker.lookup(directory, row["company"]) or {}
        resume = tailor.resume_pdf(row["resume"])
        years = f"asks {row['years_required']}+ yrs" if row["years_required"] else "years not stated"
        print(f"[{number}/{len(queue)}] {'★ ' if info.get('star') else ''}{row['company']} | {row['title']}")
        print(f"    {row['location']} | posted {row['posted_on'] or 'date unknown'} | {years} | score {row['score']}")
        print(f"    you have: {row['matched_skills']}")
        if row["missing_skills"]:
            print(f"    not on your resume: {row['missing_skills']}")
        print(f"    resume: {row['resume']}")
        print(f"    {row['job_url']}")
        if open_pages:
            _run(["open", row["job_url"]], check=False)
            if resume and resume.exists():
                _run(["pbcopy"], input=str(resume).encode(), check=False)
        while True:
            choice = ask("    [a] applied  [s] skip for now  [n] not a fit  [r] show resume in Finder  [q] quit > ").lower()
            if choice == "r" and resume:
                _run(["open", "-R", str(resume)], check=False)
            elif choice in ("a", "s", "n", "q"):
                break
        if choice == "q":
            break
        if choice == "a":
            note = ask("    note (referral, recruiter, anything to remember; Enter to skip): ", default="")
            row["status"], row["applied_on"] = tracker.APPLIED, today
            if note:
                row["notes"] = f"{row['notes']}; {note}" if row["notes"] else note
            tracker.save(rows)
            updated = tracker.mark_company_applied(row["company"], row["title"], today)
            applied += 1
            print(f"    logged as Applied{' (also updated ' + ', '.join(updated) + ')' if updated else ''}\n")
        elif choice == "n":
            row["status"] = tracker.NOT_A_FIT
            tracker.save(rows)
            print("    logged as Not a fit\n")
        else:
            print()
    left = sum(1 for row in rows if row["status"] == tracker.TO_APPLY)
    print(f"Applied to {applied} today. {left} still waiting.")
    sheets.sync_quietly()
