"""Sources: one function per applicant tracking system (ATS) to fetch a job
board as JSON, and one to convert what it returned into the common columns."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 60
HEADERS = {"User-Agent": "job-watcher (class project)", "Accept": "application/json"}
SEARCH_LIMIT = 5000  # boards larger than this must be configured with a "search" term


def load_sources(path=None):
    return json.loads((Path(path) if path else ROOT / "sources.json").read_text())


# ---------- fetch: return exactly what the board's API returned ----------

def _get(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_greenhouse(src):
    return _get(f"https://boards-api.greenhouse.io/v1/boards/{src['board']}/jobs")


def fetch_lever(src):
    return _get(f"https://api.lever.co/v0/postings/{src['board']}", {"mode": "json"})


def fetch_ashby(src):
    return _get(f"https://api.ashbyhq.com/posting-api/job-board/{src['board']}")


def fetch_smartrecruiters(src):
    """Paged: 100 postings per request. Raw file keeps every page."""
    pages, offset = [], 0
    while True:
        params = {"limit": 100, "offset": offset}
        if src.get("search"):
            params["q"] = src["search"]
        page = _get(f"https://api.smartrecruiters.com/v1/companies/{src['board']}/postings", params)
        pages.append(page)
        offset += 100
        if not page.get("content") or offset >= page.get("totalFound", 0):
            break
    return {"pages": pages}


def fetch_workday(src):
    """Paged: 20 postings per POST request. Raw file keeps every page."""
    url = f"https://{src['host']}/wday/cxs/{src['tenant']}/{src['site']}/jobs"
    pages, offset, total = [], 0, None
    while True:
        body = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": src.get("search", "")}
        r = requests.post(url, json=body, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        page = r.json()
        pages.append(page)
        if total is None:  # Workday only reports the total on the first page
            total = page.get("total", 0)
        offset += 20
        if not page.get("jobPostings") or offset >= total:
            break
    return {"pages": pages}


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workday": fetch_workday,
}


def fetch(src):
    return FETCHERS[src["ats"]](src)


# ---------- normalize: raw JSON -> common columns ----------

def utc_date(value):
    """ISO timestamp string or epoch milliseconds -> 'YYYY-MM-DD' in UTC ('' if missing)."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _row(src, source_id, title, location, department, posted_date, url):
    clean = lambda s: " ".join(str(s or "").split())
    return {
        "source_id": str(source_id),
        "employer": src["employer"],
        "title": clean(title),
        "location": clean(location),
        "department": clean(department),
        "posted_date": posted_date,
        "url": url or "",
    }


def normalize_greenhouse(src, raw):
    # The jobs list does not include a department, so that column stays empty.
    return [
        _row(src, j["id"], j.get("title"), (j.get("location") or {}).get("name"), "",
             utc_date(j.get("first_published")), j.get("absolute_url"))
        for j in raw.get("jobs", [])
    ]


def normalize_lever(src, raw):
    rows = []
    for j in raw:
        cat = j.get("categories") or {}
        rows.append(_row(src, j["id"], j.get("text"), cat.get("location"), cat.get("department"),
                         utc_date(j.get("createdAt")), j.get("hostedUrl")))
    return rows


def normalize_ashby(src, raw):
    return [
        _row(src, j["id"], j.get("title"), j.get("location"), j.get("department"),
             utc_date(j.get("publishedAt")), j.get("jobUrl"))
        for j in raw.get("jobs", [])
    ]


def normalize_smartrecruiters(src, raw):
    rows = []
    for page in raw.get("pages", []):
        for j in page.get("content", []):
            loc = j.get("location") or {}
            company = (j.get("company") or {}).get("identifier") or src["board"]
            rows.append(_row(src, j["id"], j.get("name"), loc.get("fullLocation") or loc.get("city"),
                             (j.get("department") or {}).get("label"),
                             utc_date(j.get("releasedDate")),
                             f"https://jobs.smartrecruiters.com/{company}/{j['id']}"))
    return rows


def normalize_workday(src, raw):
    # Workday gives "Posted 3 Days Ago" rather than a date, so posted_date stays
    # empty, and no department. The ID is the requisition number at the end of the path.
    rows = []
    for page in raw.get("pages", []):
        for j in page.get("jobPostings", []):
            path = j.get("externalPath")
            if not path:
                continue
            rows.append(_row(src, path.rsplit("_", 1)[-1], j.get("title"), j.get("locationsText"), "", "",
                             f"https://{src['host']}/{src['site']}{path}"))
    return rows


NORMALIZERS = {
    "greenhouse": normalize_greenhouse,
    "lever": normalize_lever,
    "ashby": normalize_ashby,
    "smartrecruiters": normalize_smartrecruiters,
    "workday": normalize_workday,
}


def normalize(src, raw):
    """Common columns for every posting in one raw file, one row per source_id."""
    seen, rows = set(), []
    for row in NORMALIZERS[src["ats"]](src, raw):
        if row["source_id"] in seen:  # paged boards can repeat a posting across pages
            continue
        seen.add(row["source_id"])
        rows.append(row)
    return rows
