"""Fetches postings from public job-board APIs and returns them in one shape (Job).

Every source here is a public endpoint that the company's own careers page uses, so no login or
scraping of LinkedIn/Naukri is involved. Each fetcher takes a board entry and a prefilter(title,
posted) callback, and skips detail requests for postings that fail the prefilter.
"""
import hashlib
import html
import re
import time
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
import requests  # noqa: E402

from .matching import REMOTE_RX, mentions_india  # noqa: E402

TIMEOUT = 30
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "jobhunt/1.0 (personal job search)"

# Job boards that repost listings. Google Jobs results prefer the company's own apply link.
AGGREGATORS = (
    "linkedin", "naukri", "indeed", "glassdoor", "foundit", "monster", "shine.com", "timesjobs",
    "instahyre", "cutshort", "wellfound", "hirist", "apna", "jooble", "talent.com", "simplyhired",
    "ziprecruiter", "bebee", "jobrapido", "adzuna", "careerjet", "whatjobs", "dice.com", "learn4good",
    "jobaaj", "getmereferred", "kitjob", "myinternships", "jobzmall", "gravityer", "hirect", "jobsora",
    "talentrover", "jobhat", "recruit.net", "joblist", "jobtensor", "mintly", "freshersworld",
)


@dataclass
class Job:
    source: str
    board: str
    job_id: str
    company: str
    title: str
    url: str
    locations: list = field(default_factory=list)
    remote: bool = False
    description: str = ""
    posted: object = None  # datetime.date or None

    @property
    def key(self):
        return f"{self.source}:{self.board}:{self.job_id}"

    @property
    def location(self):
        return "; ".join(dict.fromkeys(loc.strip() for loc in self.locations if loc and loc.strip()))


# ------------------------------------------------------------------------ Helpers


def get_json(url, params=None, body=None):
    """GET (or POST when body is given) and parse JSON. Returns None on 404; retries 429/5xx."""
    problem = ""
    for attempt in range(3):
        try:
            if body is None:
                response = SESSION.get(url, params=params, timeout=TIMEOUT)
            else:
                response = SESSION.post(url, params=params, json=body, timeout=TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as error:
            problem = type(error).__name__
        else:
            status = response.status_code
            if status == 404:
                return None
            if status < 400:
                return response.json()
            if status not in (429, 500, 502, 503, 504):
                # Build the message by hand: requests' own error text includes the query string,
                # which would print API keys into the terminal and logs.
                raise RuntimeError(f"HTTP {status} from {url}: {response.text[:150]}")
            problem = f"HTTP {status}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{problem} from {url}")


def html_to_text(markup):
    if not markup:
        return ""
    text = re.sub(r"(?i)<\s*(br|/p|/div|/h[1-6]|/tr|/ul|/ol)\s*/?>", "\n", markup)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def iso_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def relative_date(text):
    """'Posted 3 Days Ago', '3 days ago', 'Posted Today', '30+ days ago', '5 hours ago' -> date."""
    if not text:
        return None
    text = text.lower()
    today = date.today()
    if any(word in text for word in ("today", "hour", "minute", "just")):
        return today
    if "yesterday" in text:
        return today - timedelta(days=1)
    match = re.search(r"(\d+)\+?\s*(day|week|month)", text)
    if not match:
        return None
    return today - timedelta(days=int(match.group(1)) * {"day": 1, "week": 7, "month": 30}[match.group(2)])


# ------------------------------------------------------------------------ Company job boards


def greenhouse(board, prefilter):
    """The board list is light; each posting's text is fetched only if the title, date and
    location could fit. This keeps scans of thousands of boards fast."""
    slug = board["slug"]
    base = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    data = get_json(base) or {}
    jobs = []
    for item in data.get("jobs", []):
        posted = iso_date(item.get("first_published") or item.get("updated_at"))
        if not prefilter(item.get("title", ""), posted):
            continue
        place = (item.get("location") or {}).get("name", "")
        if not (mentions_india(place) or REMOTE_RX.search(place)):
            continue
        detail = get_json(f"{base}/{item['id']}") or {}
        locations = [place]
        locations += [office.get("location") or office.get("name") or "" for office in detail.get("offices", [])]
        jobs.append(Job(
            "greenhouse", slug, str(item["id"]), item.get("company_name") or board["company"],
            item["title"].strip(), item.get("absolute_url", ""), locations,
            description=html_to_text(html.unescape(detail.get("content", ""))), posted=posted,
        ))
    return jobs


def lever(board, prefilter):
    slug = board["slug"]
    data = get_json(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"}) or []
    jobs = []
    for item in data:
        created = item.get("createdAt")
        posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).date() if created else None
        if not prefilter(item.get("text", ""), posted):
            continue
        categories = item.get("categories") or {}
        locations = list(categories.get("allLocations") or []) + [categories.get("location") or ""]
        parts = [item.get("descriptionPlain") or ""]
        for section in item.get("lists") or []:
            parts += [section.get("text", ""), html_to_text(section.get("content", ""))]
        parts.append(item.get("additionalPlain") or "")
        jobs.append(Job(
            "lever", slug, item["id"], board["company"], item["text"].strip(), item.get("hostedUrl", ""),
            locations, remote=item.get("workplaceType") == "remote",
            description="\n".join(p for p in parts if p).strip(), posted=posted,
        ))
    return jobs


def ashby(board, prefilter):
    slug = board["slug"]
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}") or {}
    jobs = []
    for item in data.get("jobs", []):
        posted = iso_date(item.get("publishedAt"))
        if item.get("isListed") is False or not prefilter(item.get("title", ""), posted):
            continue
        locations, addresses = [item.get("location") or ""], [item.get("address")]
        for extra in item.get("secondaryLocations") or []:
            locations.append(extra.get("location") or "")
            addresses.append(extra.get("address"))
        for address in addresses:
            postal = (address or {}).get("postalAddress") or {}
            parts = (postal.get("addressLocality"), postal.get("addressRegion"), postal.get("addressCountry"))
            locations.append(", ".join(p for p in parts if p))
        jobs.append(Job(
            "ashby", slug, item["id"], board["company"], item["title"].strip(), item.get("jobUrl", ""),
            locations, remote=bool(item.get("isRemote")) or item.get("workplaceType") == "Remote",
            description=item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml", "")),
            posted=posted,
        ))
    return jobs


def smartrecruiters(board, prefilter):
    slug = board["slug"]
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    jobs, offset = [], 0
    while offset < 1000:
        data = get_json(base, {"country": "in", "limit": 100, "offset": offset}) or {}
        page = data.get("content", [])
        for item in page:
            posted = iso_date(item.get("releasedDate"))
            if not prefilter(item.get("name", ""), posted):
                continue
            detail = get_json(item["ref"]) or {}
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            description = "\n\n".join(
                html_to_text((sections.get(name) or {}).get("text", ""))
                for name in ("jobDescription", "qualifications", "additionalInformation"))
            location = item.get("location") or {}
            jobs.append(Job(
                "smartrecruiters", slug, str(item["id"]), board["company"], item["name"].strip(),
                detail.get("postingUrl") or f"https://jobs.smartrecruiters.com/{slug}/{item['id']}",
                [location.get("fullLocation") or location.get("city") or ""],
                remote=bool(location.get("remote")), description=description.strip(), posted=posted,
            ))
        offset += len(page)
        if not page or offset >= data.get("totalFound", 0):
            break
    return jobs


def parse_workday_url(url):
    """https://acme.wd5.myworkdayjobs.com/en-US/Careers -> (host, tenant, site)."""
    match = re.match(r"https?://([^/]+)/(?:recruiting/([^/]+)/)?(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)", url)
    if not match:
        raise ValueError(f"not a Workday careers URL: {url}")
    host, tenant, site = match.groups()
    return host, tenant or host.split(".")[0], site


def workday_india_facet(facets):
    """Find the location filter values that are in India, e.g. {"locations": ["id1", "id2"]}."""
    found = {}

    def walk(items):
        for facet in items:
            values = facet.get("values") or []
            ids = [v["id"] for v in values
                   if v.get("id") and "values" not in v and mentions_india(v.get("descriptor", ""))]
            if ids:
                found.setdefault(facet.get("facetParameter") or "", []).extend(ids)
            walk([v for v in values if "values" in v])

    walk(facets)
    for name in ("locations", "locationCountry"):
        if name in found:
            return {name: found[name]}
    for name, ids in found.items():
        if "location" in name.lower() or "country" in name.lower():
            return {name: ids}
    return None


def workday(board, prefilter):
    host, tenant, site = parse_workday_url(board["url"])
    api = f"https://{host}/wday/cxs/{tenant}/{site}"
    query = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "data engineer"}
    first = get_json(api + "/jobs", body=query) or {}
    india = workday_india_facet(first.get("facets", []))
    if not india:
        return []
    query["appliedFacets"] = india
    jobs, total, offset = [], None, 0
    while offset < 200:
        query["offset"] = offset
        page = get_json(api + "/jobs", body=query) or {}
        if total is None:
            total = page.get("total", 0)  # Workday only reports the total on the first page
        postings = page.get("jobPostings", [])
        for item in postings:
            if not prefilter(item.get("title", ""), relative_date(item.get("postedOn"))):
                continue
            info = (get_json(api + item["externalPath"]) or {}).get("jobPostingInfo") or {}
            locations = [info.get("location") or item.get("locationsText") or ""]
            locations += list(info.get("additionalLocations") or [])
            jobs.append(Job(
                "workday", f"{tenant}/{site}", info.get("jobReqId") or item["externalPath"].rsplit("_", 1)[-1],
                board["company"], item["title"].strip(),
                info.get("externalUrl") or f"https://{host}/{site}{item['externalPath']}", locations,
                remote="remote" in (info.get("remoteType") or "").lower(),
                description=html_to_text(info.get("jobDescription", "")),
                posted=iso_date(info.get("startDate")) or relative_date(item.get("postedOn")),
            ))
        offset += 20
        if len(postings) < 20 or offset >= total:
            break
    return jobs


def amazon(board, prefilter):
    """amazon.jobs has its own public feed (the one its search page uses)."""
    jobs, offset = [], 0
    while offset < 500:
        data = get_json("https://www.amazon.jobs/en/search.json", {
            "base_query": "data engineer", "country": "IND", "result_limit": 100, "offset": offset,
            "sort": "recent",
        }) or {}
        page = data.get("jobs", [])
        for item in page:
            try:
                posted = datetime.strptime(" ".join(item.get("posted_date", "").split()), "%B %d, %Y").date()
            except ValueError:
                posted = None
            if not prefilter(item.get("title", ""), posted):
                continue
            sections = [item.get("description"), item.get("basic_qualifications"), item.get("preferred_qualifications")]
            jobs.append(Job(
                "amazon", "amazon.jobs", str(item.get("id_icims") or item.get("id")), board["company"],
                item["title"].strip(), "https://www.amazon.jobs" + item.get("job_path", ""),
                [item.get("normalized_location") or item.get("location") or ""],
                description="\n\n".join(html_to_text(s) for s in sections if s), posted=posted,
            ))
        offset += len(page)
        if not page or offset >= data.get("hits", 0):
            break
    return jobs


def oracle_hcm(board, prefilter):
    """Careers sites built on Oracle Hiring (JPMorgan, American Express, Honeywell, Oracle).

    board needs "host" (like jpmc.fa.oraclecloud.com) and "site" (like CX_1001).
    """
    host, site = board["host"], board["site"]
    api = f"https://{host}/hcmRestApi/resources/latest"
    finder = f'findReqs;siteNumber={site},limit=50,keyword="data engineer",sortBy=POSTING_DATES_DESC'
    first = get_json(f"{api}/recruitingCEJobRequisitions", {
        "onlyData": "true", "finder": finder + ",facetsList=LOCATIONS"}) or {}
    top = (first.get("items") or [{}])[0]
    india_id = next((str(f["Id"]) for f in top.get("locationsFacet") or []
                     if (f.get("Name") or "").strip().lower() == "india"), None)
    if not india_id:
        return []
    jobs, offset = [], 0
    while offset < 300:
        page = get_json(f"{api}/recruitingCEJobRequisitions", {
            "onlyData": "true", "expand": "requisitionList.secondaryLocations",
            "finder": f"{finder},offset={offset},selectedLocationsFacet={india_id}"}) or {}
        top = (page.get("items") or [{}])[0]
        listing = top.get("requisitionList") or []
        for item in listing:
            posted = iso_date(item.get("PostedDate"))
            if not prefilter(item.get("Title", ""), posted):
                continue
            detail = ((get_json(f"{api}/recruitingCEJobRequisitionDetails", {
                "onlyData": "true", "expand": "all",
                "finder": f'ById;Id="{item["Id"]}",siteNumber={site}'}) or {}).get("items") or [{}])[0]
            parts = [detail.get("ExternalDescriptionStr"), detail.get("ExternalResponsibilitiesStr"),
                     detail.get("ExternalQualificationsStr")]
            places = [item.get("PrimaryLocation") or ""]
            places += [loc.get("Name") or "" for loc in item.get("secondaryLocations") or []]
            jobs.append(Job(
                "oracle", host, str(item["Id"]), board["company"], item["Title"].strip(),
                f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{item['Id']}", places,
                remote=(item.get("WorkplaceType") or "").lower() == "remote",
                description="\n\n".join(html_to_text(p) for p in parts if p), posted=posted,
            ))
        offset += len(listing)
        if not listing or offset >= int(top.get("TotalJobsCount") or 0):
            break
    return jobs


def eightfold(board, prefilter):
    """Careers sites built on Eightfold (Microsoft). board needs "host" and "domain"."""
    host, domain = board["host"], board["domain"]
    jobs, start = [], 0
    while start < 100:
        data = (get_json(f"https://{host}/api/pcsx/search", {
            "domain": domain, "query": "data engineer", "location": "India", "start": start,
            "sort_by": "timestamp"}) or {}).get("data") or {}
        positions = data.get("positions") or []
        for item in positions:
            stamp = item.get("postedTs")
            posted = datetime.fromtimestamp(int(stamp), tz=timezone.utc).date() if stamp else None
            if not prefilter(item.get("name", ""), posted):
                continue
            detail = (get_json(f"https://{host}/api/pcsx/position_details", {
                "position_id": item["id"], "domain": domain, "hl": "en"}) or {}).get("data") or {}
            jobs.append(Job(
                "eightfold", host, str(item["id"]), board["company"], item["name"].strip(),
                f"https://{host}{item.get('positionUrl') or '/careers/job/' + str(item['id'])}",
                list(item.get("standardizedLocations") or []) + list(item.get("locations") or []),
                remote=item.get("workLocationOption") == "remote",
                description=html_to_text(detail.get("jobDescription") or ""), posted=posted,
            ))
        start += len(positions)
        if not positions or start >= int(data.get("count") or 0):
            break
    return jobs


def recruitee(board, prefilter):
    slug = board["slug"]
    data = get_json(f"https://{slug}.recruitee.com/api/offers/") or {}
    jobs = []
    for item in data.get("offers", []):
        posted = iso_date(item.get("published_at") or item.get("created_at"))
        if not prefilter(item.get("title", ""), posted):
            continue
        parts = [item.get("description"), item.get("requirements")]
        jobs.append(Job(
            "recruitee", slug, str(item["id"]), board["company"], item["title"].strip(),
            item.get("careers_url", ""),
            [item.get("location") or "", item.get("country") or "", item.get("city") or ""],
            remote=bool(item.get("remote")),
            description="\n\n".join(html_to_text(p) for p in parts if p), posted=posted,
        ))
    return jobs


def atlassian(board, prefilter):
    """Atlassian's careers site feed (all roles in one file, no posting dates)."""
    jobs = []
    for item in get_json("https://www.atlassian.com/endpoint/careers/listings") or []:
        places = [str(place) for place in item.get("locations") or []]
        if not prefilter(item.get("title", ""), None) or not mentions_india(" | ".join(places)):
            continue
        parts = [item.get("overview"), item.get("responsibilities"), item.get("qualifications")]
        jobs.append(Job(
            "atlassian", "atlassian", str(item["id"]), board["company"], item["title"].strip(),
            (item.get("applyUrl") or "").split("?")[0], places,
            description="\n\n".join(html_to_text(p) for p in parts if p),
        ))
    return jobs


def workable_aggregator(queries, prefilter, location="India", max_pages=10):
    """jobs.workable.com lists openings from every company that hires through Workable
    (no key needed). Each query is paged until it runs out or max_pages is reached."""
    jobs, seen = [], set()
    for query in queries:
        token = None
        for _ in range(max_pages):
            params = {"query": query, "location": location}
            if token:
                params["pageToken"] = token
            data = get_json("https://jobs.workable.com/api/v1/jobs", params) or {}
            for item in data.get("jobs", []):
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                posted = iso_date(item.get("created"))
                if not prefilter(item.get("title", ""), posted):
                    continue
                place = item.get("location") or {}
                locations = [str(x) for x in item.get("locations") or []]
                locations.append(", ".join(p for p in (place.get("city"), place.get("subregion"), place.get("countryName")) if p))
                text = [item.get("description"), item.get("requirementsSection"), item.get("benefitsSection")]
                jobs.append(Job(
                    "workable", "aggregator", item["id"], (item.get("company") or {}).get("title", "").strip(),
                    item["title"].strip(), item.get("url", ""), locations,
                    remote=item.get("workplace") == "remote",
                    description="\n\n".join(html_to_text(t) for t in text if t), posted=posted,
                ))
            token = data.get("nextPageToken")
            if not token or not data.get("jobs"):
                break
    return jobs


FETCHERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
    "workday": workday,
    "amazon": amazon,
    "atlassian": atlassian,
    "oracle": oracle_hcm,
    "eightfold": eightfold,
    "recruitee": recruitee,
}


# ------------------------------------------------------------------------ Google Jobs (SerpApi)


def pick_apply_link(options):
    """Prefer the company's own site or ATS over job boards that repost the listing."""
    for option in options:
        if not any(name in (option.get("link", "") + " " + option.get("title", "")).lower() for name in AGGREGATORS):
            return option.get("link")
    return options[0].get("link") if options else None


def google_jobs(searches, api_key, prefilter):
    jobs = []
    for query, location in searches:
        data = get_json("https://serpapi.com/search.json", {
            "engine": "google_jobs", "q": query, "location": location, "gl": "in", "hl": "en",
            "api_key": api_key,
        }) or {}
        error = data.get("error", "")
        if error and "hasn't returned any results" not in error:
            raise RuntimeError(f"SerpApi: {error}")
        for item in data.get("jobs_results", []):
            extensions = item.get("detected_extensions") or {}
            posted = relative_date(extensions.get("posted_at"))
            if not prefilter(item.get("title", ""), posted):
                continue
            url = pick_apply_link(item.get("apply_options") or []) or item.get("share_link", "")
            job_id = hashlib.sha1((item.get("job_id") or url).encode()).hexdigest()[:12]
            jobs.append(Job(
                "google_jobs", "serpapi", job_id, (item.get("company_name") or "").strip(),
                (item.get("title") or "").strip(), url, [item.get("location", "")],
                remote=bool(extensions.get("work_from_home")), description=item.get("description", ""),
                posted=posted,
            ))
    return jobs
