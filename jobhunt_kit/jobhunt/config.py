"""Settings for the job pipeline. Edit these, then run:  python3 -m jobhunt search

Resume content (skills and bullets) stays in build_resume_final.py; the pipeline reads it from there.
"""
from pathlib import Path

# ------------------------------------------------------------------------ What to look for

# A posting is kept when its title matches an INCLUDE pattern and no EXCLUDE pattern
# (case-insensitive regular expressions).
TITLE_INCLUDE = [
    r"\bdata engineer",
    r"\bdata engineering\b",
    r"\bbig data\b.*\b(engineer|developer)\b",
    r"\b(py)?spark\b.*\b(engineer|developer)\b",
    r"\bdata platform engineer",
    r"\bdata (infrastructure|pipeline)s? engineer",
    r"\betl\b.*\b(engineer|developer)\b",
    r"\banalytics engineer\b",
    r"\bdata developer\b",
    r"\bsoftware (development )?engineer\b.*\bdata\b",
    r"\bdata\b.*\bsoftware (development )?engineer\b",
    r"\b(sde|swe)\b.*\bdata\b",
    r"\bdata\b.*\b(sde|swe)\b",
]
TITLE_EXCLUDE = [
    r"\b(smts|lmts|pmts)\b",  # Salesforce levels: senior, lead, and principal member of technical staff
    r"\bscientist\b", r"\bdata science\b", r"\bsales\b", r"\bsolutions? (architect|engineer)\b",
    r"\bsenior\b", r"\bsr\b", r"\bstaff\b", r"\bprincipal\b", r"\blead\b", r"\bmanager\b",
    r"\barchitect\b", r"\bdirector\b", r"\bhead\b", r"\bvp\b", r"\bvice president\b",
    r"\bintern", r"\btrainee\b", r"\b(iii|iv)\b",
]

# Cities you will work in. Add "hyderabad", "pune", "chennai", "gurugram", "gurgaon", "noida"
# or "mumbai" to widen the search.
CITIES = ["bengaluru", "bangalore"]  # EDIT: cities you would work in, in lower case
INCLUDE_REMOTE_INDIA = True   # remote roles open to candidates in India
INCLUDE_INDIA_NO_CITY = True  # postings whose location is just "India"

MAX_YEARS_REQUIRED = 3  # skip postings whose minimum experience is higher
MAX_AGE_DAYS = 14       # skip postings older than this
MIN_SCORE = 60          # skip postings whose match score (0-100) is lower

# A posting must mention at least one of these skills.
REQUIRE_ANY_SKILL = ["PySpark", "Spark", "AWS", "Airflow"]

EXCLUDE_COMPANIES = []  # companies to skip, such as your current employer: ["Acme Corp"]

# ------------------------------------------------------------------------ Skills used for scoring

# (name, regex, weight). A skill counts as yours when its pattern appears in the headline or skills
# section of build_resume_final.py, so adding a skill there updates matching automatically.
SKILL_TERMS = [
    ("PySpark", r"\bpy ?spark\b", 3),
    ("Spark", r"\bspark\b", 3),
    ("AWS", r"\baws\b|amazon web services", 3),
    ("Airflow", r"\bairflow\b|\bmwaa\b", 3),
    ("SQL", r"\bsql\b", 2),
    ("Python", r"\bpython\b", 2),
    ("EMR", r"\bemr\b", 2),
    ("S3", r"\bs3\b", 1),
    ("Glue", r"\bglue\b", 1),
    ("Athena", r"\bathena\b", 1),
    ("Redshift", r"\bredshift\b", 1),
    ("ETL/ELT", r"\betl\b|\belt\b", 1),
    ("Data modeling", r"\bdata model", 1),
    ("Data warehousing", r"\bdata ?warehous", 1),
    ("Data quality", r"\bdata quality\b|\bdata validation\b", 1),
    ("PostgreSQL", r"\bpostgres", 1),
    ("MySQL", r"\bmysql\b", 1),
    ("Parquet", r"\bparquet\b", 1),
    ("Bash", r"\bbash\b|\bshell script", 1),
    ("Git", r"\bgit\b|\bgithub\b", 1),
    ("Linux", r"\blinux\b|\bunix\b", 1),
    ("Geospatial", r"\bgeospatial\b|\bgis\b|\bgeohash", 1),
    # Common asks that are not on the resume today.
    ("Kafka", r"\bkafka\b", 2),
    ("Scala", r"\bscala\b", 2),
    ("Java", r"\bjava\b", 2),
    ("Azure", r"\bazure\b|\badf\b|\bsynapse\b", 4),
    ("GCP", r"\bgcp\b|\bgoogle cloud\b|\bbigquery\b|\bdataproc\b", 4),
    ("Snowflake", r"\bsnowflake\b", 2),
    ("Databricks", r"\bdatabricks\b", 2),
    ("dbt", r"\bdbt\b", 1),
    ("Streaming", r"\bstreaming\b|\breal[- ]time\b", 1),
    ("Flink", r"\bflink\b", 1),
    ("Hadoop/Hive", r"\bhadoop\b|\bhdfs\b|\bhive\b", 1),
    ("NoSQL", r"\bnosql\b|\bmongodb\b|\bcassandra\b|\bdynamodb\b", 1),
    ("Docker/Kubernetes", r"\bdocker\b|\bkubernetes\b|\bk8s\b", 1),
    ("Terraform", r"\bterraform\b", 1),
    ("Delta/Iceberg", r"\bdelta lake\b|\biceberg\b|\bhudi\b", 1),
]

# When a posting mentions the first skill, the listed alternatives are shown but don't lower the
# score, because postings often say "AWS, Azure or GCP" or "Python, Scala or Java".
ALTERNATIVES = {"AWS": ["Azure", "GCP"], "Python": ["Scala", "Java"]}

# ------------------------------------------------------------------------ Google Jobs (optional)

# Google Jobs collects postings from LinkedIn, Naukri, Indeed and company sites. It is read through
# SerpApi (free plan: 250 searches a month; each line below uses 1 search per run).
# To turn it on, put  SERPAPI_KEY=your_key  in jobhunt/.env
GOOGLE_JOBS_SEARCHES = [
    ("data engineer pyspark aws", "Bengaluru, Karnataka, India"),
    ("big data engineer spark", "Bengaluru, Karnataka, India"),
    ("data engineer spark airflow remote", "India"),
]

# Companies on your lists that have no public job feed (PhonePe, Flipkart, Uber, Zepto, ...) are
# searched on Google Jobs in groups of GOOGLE_GROUP_SIZE names per search, once every
# GOOGLE_COMPANY_EVERY_DAYS days. At 4 per group that is about 19 searches a week, so together with
# the 3 daily searches above the total stays under the free 250 a month.
GOOGLE_GROUP_SIZE = 4
GOOGLE_COMPANY_EVERY_DAYS = 7

# ------------------------------------------------------------------------ Workday career sites

# Workday sites can't be found from the company name, so they are listed here (all checked on
# 2026-11-16). To add one, open the company's careers page and paste its URL:
# https://<company>.wd<N>.myworkdayjobs.com/<site>
WORKDAY_SITES = {
    "Adobe": "https://adobe.wd5.myworkdayjobs.com/external_experienced",
    "BlackRock": "https://blackrock.wd1.myworkdayjobs.com/BlackRock_Professional",
    "Capital One": "https://capitalone.wd12.myworkdayjobs.com/Capital_One",
    "Cisco": "https://cisco.wd5.myworkdayjobs.com/Cisco_Careers",
    "Cloudera": "https://cloudera.wd5.myworkdayjobs.com/External_Career",
    "Disney": "https://disney.wd5.myworkdayjobs.com/disneycareer",
    "Expedia Group": "https://expedia.wd108.myworkdayjobs.com/search",
    "Fractal": "https://fractal.wd1.myworkdayjobs.com/Careers",
    "Lowe's India": "https://lowes.wd5.myworkdayjobs.com/LWS_External_CS",
    "Mastercard": "https://mastercard.wd1.myworkdayjobs.com/CorporateCareers",
    "Morgan Stanley": "https://ms.wd5.myworkdayjobs.com/External",
    "PayPal": "https://paypal.wd1.myworkdayjobs.com/jobs",
    "S&P Global": "https://spgi.wd5.myworkdayjobs.com/SPGI_Careers",
    "Sabre": "https://sabre.wd1.myworkdayjobs.com/SabreJobs",
    "Salesforce": "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site",
    "Shell": "https://shell.wd3.myworkdayjobs.com/ShellCareers",
    "Sprinklr": "https://sprinklr.wd1.myworkdayjobs.com/careers",
    "Target in India": "https://target.wd5.myworkdayjobs.com/targetcareers",
    "Thomson Reuters": "https://thomsonreuters.wd5.myworkdayjobs.com/External_Career_Site",
    "Visa": "https://visa.wd5.myworkdayjobs.com/Visa",
    "Quantiphi": "https://quantiphi.wd1.myworkdayjobs.com/Careers_at_Quantiphi",
    "Warner Bros. Discovery": "https://warnerbros.wd5.myworkdayjobs.com/global",
    "Wells Fargo": "https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs",
}

# Companies with their own public job feed (not on the boards above).
EXTRA_BOARDS = [
    {"company": "Amazon", "ats": "amazon"},      # amazon.jobs
    {"company": "Atlassian", "ats": "atlassian"},
    {"company": "Microsoft", "ats": "eightfold", "host": "apply.careers.microsoft.com", "domain": "microsoft.com"},
    {"company": "JPMorgan Chase", "ats": "oracle", "host": "jpmc.fa.oraclecloud.com", "site": "CX_1001"},
    {"company": "American Express", "ats": "oracle", "host": "egug.fa.us2.oraclecloud.com", "site": "CX_1"},
    {"company": "Honeywell", "ats": "oracle", "host": "ibqbjb.fa.ocs.oraclecloud.com", "site": "CX_1"},
    {"company": "Oracle", "ats": "oracle", "host": "eeho.fa.us2.oraclecloud.com", "site": "CX_45001"},
]

# Company boards that `discover` can't find by name but that exist (found by checking each
# company's careers page). Same format as boards.json.
MANUAL_BOARDS = [
    {"company": "Razorpay", "ats": "greenhouse", "slug": "razorpaysoftwareprivatelimited"},
    {"company": "Thoughtworks", "ats": "ashby", "slug": "thoughtworks"},
    {"company": "Merkle (dentsu)", "ats": "smartrecruiters", "slug": "merkleinc"},
    {"company": "Nielsen", "ats": "smartrecruiters", "slug": "TheNielsenCompany"},
    {"company": "Lenskart", "ats": "recruitee", "slug": "lenskartcareers"},
]

# ------------------------------------------------------------------------ Wider coverage

# Workable's job site lists openings from every company that hires through Workable (no key).
WORKABLE_SEARCHES = [
    "data engineer", "big data engineer", "pyspark", "spark developer", "etl developer",
    "data platform engineer",
]

# `python3 -m jobhunt scan` checks these community-kept lists of company job boards (about 16,000
# boards) and saves the ones with openings in India to jobhunt/boards_wide.json. Search then
# includes them. Re-run scan about once a week.
SLUG_LISTS = {
    "greenhouse": "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/greenhouse_companies.json",
    "lever": "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/lever_companies.json",
    "ashby": "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/ashby_companies.json",
}

# ------------------------------------------------------------------------ Files

ROOT = Path(__file__).resolve().parent.parent
TRACKER_CSV = ROOT / "companies" / "applications.csv"
COMPANY_CSVS = [
    ROOT / "companies" / "target_companies.csv",
    ROOT / "companies" / "best_data_engineering_companies.csv",
]
BOARDS_JSON = ROOT / "jobhunt" / "boards.json"
WIDE_BOARDS_JSON = ROOT / "jobhunt" / "boards_wide.json"
STATE_JSON = ROOT / "jobhunt" / "state.json"
SYNC_STATE_JSON = ROOT / "jobhunt" / "sync_state.json"
SHEETS_SCRIPT = ROOT / "jobhunt" / "sheets_script.gs"

# Optional. If you put a second email address here (for example one you use for referrals), every
# tailored folder also gets a second copy of the resume with that address, in the subfolder below.
# Leave it empty for no second copy.
ALT_EMAIL = ""
# The second copy goes in this subfolder of each tailored folder and keeps the main resume's file names.
ALT_DIR = "referral resume"


def env_value(name):
    """A setting from the environment, or from jobhunt/.env (NAME=value lines)."""
    import os
    if os.environ.get(name):
        return os.environ[name].strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name and value.strip():
                return value.strip().strip("'\"")
    return ""
TAILORED_DIR = ROOT / "generated (resume)" / "tailored"
ENV_FILE = ROOT / "jobhunt" / ".env"
LOG_DIR = ROOT / "jobhunt" / "logs"
