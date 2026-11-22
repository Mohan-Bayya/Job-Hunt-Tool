# Job Hunt Kit

A command-line tool that finds new job postings, builds a tailored resume for each one, walks you through
applying, and keeps a tracker. It was built for data engineer roles in India, and it reads **your** resume
from one file that you fill in.

```
find jobs  ->  score them against your skills  ->  tailor your resume per job  ->  you apply  ->  log it
```

You always click Submit yourself. The tool never fills in or sends an application, and it never logs in to
LinkedIn, Naukri or any other portal. It reads the public job feeds that companies' own career pages use.

## Is it tied to one person's resume?

No. Everything that comes from a resume is read from **`build_resume_codes/build_resume_final.py`**, and the
copy in this kit holds placeholder text. You replace it with your own details (step 3 below). Until you do,
the tool refuses to build resumes, so a sample resume can't go out by accident.

That one file decides:
- **Which skills you have.** The headline and the Skills section are compared with each posting to give it
  a match score. List every tool you really know, and nothing you don't.
- **What gets tailored.** For each job the tool reorders your skills and your latest job's bullets so the
  most relevant come first. It never adds, edits or invents text.
- **How your resumes look.** Layout, fonts and the one-page limit.

What is tuned for a data engineer job search (all editable, see "Change what it looks for"):
- the job titles it keeps and the senior titles it skips,
- the skills it scores (Spark, AWS, Airflow, SQL, and others),
- the location logic, which understands Indian cities and "remote India",
- the starter company lists.

## Prerequisites

- **Python 3.9 or newer.** Check with `python3 --version`.
- **An internet connection.** There is nothing to sign up for. No accounts or keys are needed for the core tool.
- **macOS is what it was built and tested on.**
  - On macOS everything works: opening postings, copying the resume path, notifications, and the daily schedule.
  - On Windows or Linux, search, tailoring and tracking work. Use `python -m jobhunt apply --no-open`
    (nothing opens automatically), skip the `schedule` command (use cron or Task Scheduler, see below),
    and expect a warning that Arial wasn't found. Resumes then use Helvetica, which looks slightly different.
- Optional: a free SerpApi key (Google Jobs search) and a Google account (Google Sheet tracker). Both are off
  until you add the details, and the tool runs without them.

## Set up (about 15 minutes)

**1. Get the folder and install the libraries**

```
cd jobhunt_kit
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run every command below from inside `jobhunt_kit`, with the environment activated.

**2. (Optional) create your settings file**

```
cp jobhunt/.env.example jobhunt/.env
```

Leave the placeholder values as they are until you set up the optional features near the end. The tool
ignores them while they are placeholders.

**3. Put your resume in `build_resume_codes/build_resume_final.py`**

Open it and replace the constants at the top: `NAME`, `HEADLINE`, `LOCATION`, `PHONE`, `EMAIL`, `LINKEDIN`,
`SUMMARY`, `SKILLS`, `EXPERIENCE` and `EDUCATION`. Read the notes at the top of the file. The main rules:
- `EXPERIENCE[0]` must be your current or latest job. Its bullets are the ones the tool reorders.
- Text between `**double asterisks**` prints in bold.
- Start each bullet with what you achieved and include numbers where you honestly can.

Then build a test copy and open it:

```
python3 build_resume_codes/build_resume_final.py
```

The files appear in `generated (resume)/`. The resume must fit on **one page**. If a line is too long, the build
prints a warning; shorten that text. Repeat until it looks right.

**4. Check the settings in `jobhunt/config.py`**

At minimum:
- `CITIES`: the cities you would work in, in lower case (remote roles in India are included separately).
- `MAX_YEARS_REQUIRED`: skip postings that ask for more years than this.
- `EXCLUDE_COMPANIES`: your current employer, for example `["Acme Corp"]`.

**5. First run**

```
python3 -m jobhunt search --dry-run     # preview matches, saves nothing
python3 -m jobhunt scan                  # about 10 minutes, finds more company boards (do it once, then weekly)
python3 -m jobhunt search                # saves matches and builds a tailored resume for each
python3 -m jobhunt apply                 # go through them
```

## Every day

```
python3 -m jobhunt search      # or let the schedule run it
python3 -m jobhunt apply
```

`apply` shows one job at a time, best match first, with your matching skills and the skills the posting
wants that aren't on your resume. It opens the posting in your browser and copies the path of that job's
tailored resume. On the application page:
1. Upload the resume. In the file dialog on macOS press **Cmd+Shift+G**, paste, and press **Enter**.
2. Fill in the form and click **Submit** yourself.
3. Back in the Terminal press one key:
   - `a` applied: logs the date, asks for an optional note, and marks the company Applied in your company lists
   - `s` skip for now (it comes back next time)
   - `n` not a fit (it never comes back)
   - `r` show the resume in Finder
   - `q` quit (you can stop any time)

## All commands

| Command | What it does |
|---|---|
| `python3 -m jobhunt search` | Find new jobs, build a tailored resume for each, add them to the tracker |
| `python3 -m jobhunt search --dry-run` | Show what it would find, without saving anything |
| `python3 -m jobhunt apply` | Go through the waiting jobs and log each result (`--no-open` skips the browser) |
| `python3 -m jobhunt run` | Search, then go straight into apply |
| `python3 -m jobhunt scan` | Check about 16,000 company job boards for openings in India (weekly) |
| `python3 -m jobhunt discover` | Re-check which companies in your lists have public job boards (monthly) |
| `python3 -m jobhunt schedule` | macOS only: run the search every day at 9:00 and show a notification |
| `python3 -m jobhunt unschedule` | Stop the daily search |
| `python3 -m jobhunt sync` | Sync the tracker with a Google Sheet (only if you set that up) |

On Windows the command may be `python` instead of `python3`.

## Where things are

| Path | What it is |
|---|---|
| `build_resume_codes/build_resume_final.py` | **Your resume.** Everything is built from this file |
| `companies/applications.csv` | The tracker: one row per job, with status, score, link, resume folder, dates, notes |
| `generated (resume)/tailored/<date>_<company>_<title>/` | That job's tailored resume (PDF and DOCX) and `job.md`, a saved copy of the posting |
| `companies/target_companies.csv` and `best_data_engineering_companies.csv` | Starter lists of companies. Edit them freely; applying marks the company here |
| `jobhunt/config.py` | All settings |
| `jobhunt/boards.json`, `boards_wide.json` | Starter lists of company job boards. `discover` and `scan` refresh them |
| `jobhunt/.env` | Your private keys (optional features only). Never share or upload this file |

Keep each job's `job.md`: postings often disappear before the interview.
Change `status` in `applications.csv` by hand to Interview, Rejected or Offer as things move.

## How a posting is chosen

A posting is kept when:
- its title matches (Data Engineer, Big Data Engineer, PySpark or Spark Developer, and similar) and is not senior, lead, staff,
  principal, manager, architect, director or an internship,
- its location is one of your `CITIES`, remote in India, or just "India",
- the minimum experience it asks for is `MAX_YEARS_REQUIRED` or less (the title and the text are both checked),
- it is no older than `MAX_AGE_DAYS`,
- it mentions at least one skill from `REQUIRE_ANY_SKILL` and scores `MIN_SCORE` or more.

The score (0 to 100) is 70% "share of the posting's skills that are in your skills section" plus 30% "how much
of your core stack it asks for". When a posting says "AWS, Azure or GCP", the alternatives don't count against you.

## Change what it looks for

Open `jobhunt/config.py`:

| Setting | What to change it for |
|---|---|
| `TITLE_INCLUDE`, `TITLE_EXCLUDE` | The job titles you want or want to skip (regular expressions) |
| `REQUIRE_ANY_SKILL` | Skills a posting must mention at least one of |
| `SKILL_TERMS` | The skills the score looks for, with a weight each |
| `CITIES`, `INCLUDE_REMOTE_INDIA` | Where you will work |
| `MAX_YEARS_REQUIRED`, `MAX_AGE_DAYS`, `MIN_SCORE` | How strict the filters are |
| `WORKDAY_SITES`, `EXTRA_BOARDS`, `MANUAL_BOARDS` | Add a company's career site. `WORKDAY_SITES` takes the company's Workday URL |

For a different kind of role (for example backend or data analyst), change the titles and skills here and
write your own resume in step 3. The location logic assumes India. For another country, the functions that
check locations in `jobhunt/matching.py` need rewriting.

## Where the jobs come from

- Company job boards (Greenhouse, Lever, Ashby, SmartRecruiters), including about 750 boards found by `scan`
- Workday career sites, amazon.jobs, and a few other companies' own feeds
- The Workable job site
- Optional: Google Jobs (below)

They don't include LinkedIn, Naukri, Indeed or Foundit, because those have no public job feed. Check them
yourself, or turn on their emailed job alerts. A few times a week, also search for recruiters' hiring posts.

## Optional: Google Jobs search (SerpApi)

Google Jobs lists postings from many sites, including some LinkedIn and Naukri postings, and it reaches
companies that have no public feed.

1. Create a free account at https://serpapi.com (250 searches a month).
2. Put your key in `jobhunt/.env`: `SERPAPI_KEY=your key`.
3. Edit `GOOGLE_JOBS_SEARCHES` in `jobhunt/config.py` (3 searches, one per run, with your city names).

Usage: each daily run uses 3 searches. Once every 7 days, companies in your lists that have no public
feed are searched in groups, about 20 more searches (see `GOOGLE_GROUP_SIZE` and `GOOGLE_COMPANY_EVERY_DAYS`).
That is roughly 190 of the free 250 a month. Lower those settings to use fewer.

## Optional: Google Sheet tracker

Keeps an "Applications" tab in your own Google Sheet in sync with `companies/applications.csv`, so you can
read and edit it from your phone. The CSV stays the main file.

1. Create a long random token: `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`
2. In `jobhunt/sheets_script.gs` replace `__PUT_A_LONG_RANDOM_TOKEN_HERE__` with that token.
3. Open your Google Sheet. Click **Extensions > Apps Script**, delete any code, paste the whole
   `sheets_script.gs`, and click Save.
4. Click **Deploy > New deployment**, choose **Web app**, set **Execute as: Me** and **Who has access: Anyone**,
   then Deploy. Authorize it when Google asks. If it says "Google hasn't verified this app", click Advanced,
   then "Go to ... (unsafe)", then Allow. It is your own script and it only touches that spreadsheet.
5. Copy the Web app URL (it ends in `/exec`). In `jobhunt/.env` set `SHEETS_WEBAPP_URL=` to that URL and
   `SHEETS_TOKEN=` to the same token.
6. Run `python3 -m jobhunt sync`.

How it works: it syncs by itself at the start and end of `apply` and during `search`. You can edit `status`,
`applied_on`, `notes` and the other free columns in the sheet or in the CSV, and the change is copied to the
other side. If both sides changed the same cell, the sheet wins. A row you add by hand in the sheet, with company
and title filled in, is imported into the CSV so searches never re-add it. Add your own columns to the tab
if you like, but tell the tool before renaming or removing the existing ones.

"Anyone" means anyone who has both the long URL and your token could read or change the tracker, so keep both
private. To switch it off, archive the deployment in Deploy > Manage deployments.

## Optional: a second copy of each resume with another email

Set `ALT_EMAIL` in `jobhunt/config.py` to a second address. Every tailored folder then also gets an identical
resume with that address in a `referral resume` subfolder. The tool only creates it; `apply` and the tracker
always use the main resume. Leave `ALT_EMAIL` empty for no second copy.

## Optional: run it every day

macOS: `python3 -m jobhunt schedule` (stop it with `unschedule`). If your Mac is asleep at 9:00, it runs
after the Mac wakes. The first run may ask whether python can access your folder; allow it.

Linux (cron): `0 9 * * * cd /full/path/to/jobhunt_kit && /full/path/to/.venv/bin/python -m jobhunt search`
Windows: use Task Scheduler to run the same command.

## Troubleshooting

| Message | What to do |
|---|---|
| `build_resume_final.py still has the template text` | Do step 3: put your own details in that file |
| `ModuleNotFoundError` | Activate the environment and run `pip install -r requirements.txt` |
| `reportlab requires 3.10+` | Install again with `pip install -r requirements.txt` (it needs reportlab 4.x, not 5) |
| `Arial not found; using Helvetica` | Normal on Windows and Linux. Resumes still build |
| A resume runs onto two pages | Shorten your bullets or summary in `build_resume_final.py` |
| `could not fetch ...` for some boards | A company's site was busy. The rest of the search still ran. Try again later |
| Few or no matches | Loosen `MAX_YEARS_REQUIRED`, `MIN_SCORE`, add cities to `CITIES`, run `scan`, or add Google Jobs |
| `Google Sheets sync failed` | The CSV is already saved. Check `SHEETS_WEBAPP_URL` and the token, then run `sync` again |

## Privacy

`jobhunt/.env` holds your keys, and `companies/applications.csv` holds your job history. The included
`.gitignore` keeps both, plus your generated resumes, out of git. Don't send those files to anyone.
Everything the tool fetches comes from public pages, and the only information it sends out is the search
words, to the job sites and, if you turn them on, to SerpApi and your own Google Sheet.
