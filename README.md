# Job Watcher

[![tests](https://github.com/emh2003/job-watcher/actions/workflows/tests.yml/badge.svg)](https://github.com/emh2003/job-watcher/actions/workflows/tests.yml)
[![daily run](https://github.com/emh2003/job-watcher/actions/workflows/daily.yml/badge.svg)](https://github.com/emh2003/job-watcher/actions/workflows/daily.yml)

A tool that watches the job market for **financial analyst / FP&A** roles. Once a day, GitHub Actions
pulls every open position at 23 employers, compares it with the day before, records what is new and
what is gone, opens a GitHub Issue with the changes, and publishes the result to a website.

**Live site:** https://emh2003.github.io/job-watcher/

Project for Financial Data Analytics.

## How it works

1. **Fetch.** `python -m jobwatcher.run` calls every source in `sources.json` and saves exactly what
   each one returned, compressed, in `data/raw/<date>/<source>.json.gz`. If a source fails, the run
   carries on; that source writes no raw file that day and is marked as failed in `data/status.json`.
2. **Build.** `data/history.csv` is rebuilt from the raw files alone, replaying every day in order.
3. **Status.** `data/status.json` is written for the latest run.
4. **Issue.** A GitHub Issue titled with the date lists the new and removed postings with links, and
   the previous day's issue is closed. An issue is opened even on a day with no changes.
5. **Commit.** The workflow commits the `data/` folder and republishes the site.

Dates are UTC dates. A second run on the same day replaces that day's raw files, rebuilds the history
and updates that day's issue, so each day counts once.

## Commands

Build the history file from the raw files:

```
python -m jobwatcher.build
```

Other commands:

```
pip install -r requirements.txt   # once
python -m pytest                  # run the tests
python -m jobwatcher.run          # a full run (fetch, build, status); opens the issue only on GitHub Actions
python -m http.server             # then open http://localhost:8000 to see the site
```

## The title rule

A posting is marked `in_role` when its title matches the include pattern and does not match the
exclude pattern (both ignore upper/lower case). The rule lives in `jobwatcher/role.py`.

**Include** a title containing any of:

- `FP&A` (also `FP & A`)
- `financial planning`
- `strategic finance`
- `finance` or `financial` followed later by `analyst` (Financial Analyst, Finance Analyst II)
- `analyst` followed later by `finance` or `financial` (Senior Analyst, Corporate Finance)

**Exclude** a title containing any of: `financial crime(s)`, `engineer`/`engineering`, `developer`,
`compliance`, `recruit…`.

Every posting on each board is kept in the history; the rule only sets the `in_role` column. Because
the history is rebuilt from the raw files, changing the rule re-marks every day of the history.

## Sources

Each source is one employer's job board, read as JSON (no login, no HTML) through the applicant
tracking system (ATS) that hosts it.

| Source | Employer | ATS | Request |
|---|---|---|---|
| stripe | Stripe | Greenhouse | `GET boards-api.greenhouse.io/v1/boards/stripe/jobs` |
| coinbase | Coinbase | Greenhouse | `…/boards/coinbase/jobs` |
| block | Block | Greenhouse | `…/boards/block/jobs` |
| robinhood | Robinhood | Greenhouse | `…/boards/robinhood/jobs` |
| affirm | Affirm | Greenhouse | `…/boards/affirm/jobs` |
| sofi | SoFi | Greenhouse | `…/boards/sofi/jobs` |
| brex | Brex | Greenhouse | `…/boards/brex/jobs` |
| chime | Chime | Greenhouse | `…/boards/chime/jobs` |
| carta | Carta | Greenhouse | `…/boards/carta/jobs` |
| databricks | Databricks | Greenhouse | `…/boards/databricks/jobs` |
| janestreet | Jane Street | Greenhouse | `…/boards/janestreet/jobs` |
| point72 | Point72 | Greenhouse | `…/boards/point72/jobs` |
| toast | Toast | Greenhouse | `…/boards/toast/jobs` |
| palantir | Palantir | Lever | `GET api.lever.co/v0/postings/palantir?mode=json` |
| veeva | Veeva | Lever | `GET api.lever.co/v0/postings/veeva?mode=json` |
| ramp | Ramp | Ashby | `GET api.ashbyhq.com/posting-api/job-board/ramp` |
| plaid | Plaid | Ashby | `…/job-board/plaid` |
| airwallex | Airwallex | Ashby | `…/job-board/airwallex` |
| openai | OpenAI | Ashby | `…/job-board/openai` |
| wise | Wise | SmartRecruiters | `GET api.smartrecruiters.com/v1/companies/Wise/postings` (100 per page) |
| experian | Experian | SmartRecruiters | `…/companies/Experian/postings` |
| servicenow | ServiceNow | SmartRecruiters | `…/companies/ServiceNow/postings` |
| doordash | DoorDash | Greenhouse | `…/boards/doordashusa/jobs` |

Notes:

- **Workday:** the tool can also read Workday boards (`fetch_workday` in `jobwatcher/sources.py`, 20
  postings per page). Mastercard's Workday board was on the list at first, but it answered "429 Too
  Many Requests" to GitHub's servers on every run, even with pauses and retries, so it was replaced
  with DoorDash as the assignment directs for an employer that blocks the tool.
- **Search terms:** none. Every board above returns fewer than 5,000 postings, so each is read in
  full. If a board ever passes 5,000, the run records that source as failed until a `"search"` term
  is added to its entry in `sources.json` (and listed here).
- **Empty columns:** Greenhouse's job list does not give a department, so `department` is empty
  for those rows.
- **Rate limits:** a call that gets "too many requests" (429) or a server error is retried up to
  three times, waiting longer each time, before the source is recorded as failed.
- **Empty answers:** a board that answers with zero postings is recorded as a failed call, so a
  glitch cannot mark every posting of an employer as removed.

## Data

`data/history.csv` has one row per posting, sorted by `posting_id`:

`posting_id` (source + `:` + the source's own ID), `source`, `source_id`, `employer`, `title`,
`location`, `department`, `posted_date`, `url`, `in_role`, `first_run` (true when the posting was in
the first raw file of its source), `first_seen`, `last_seen`, `status` (`open` or `removed`),
`removed_date`.

- First seen: the first day the posting appears. Last seen: the latest day its source listed it.
- Removed: an open posting is marked removed, with that day's date, when its source has a raw file
  for that day and no longer lists it. A day without a raw file for the source changes nothing.
- Reopened: a removed posting that is listed again becomes open, its removed date is cleared and its
  first-seen date is kept.

`data/status.json` describes the latest run: `run_time`, `first_run_date`, `days_with_success`,
`open`, `new_today`, `removed_today`, and `sources` (`name`, `ok`, `count`, plus `error` on a failure).

## The site

Three pages that load the two data files and do all calculations in the browser.

- **Today** (`index.html`): time of the last run, status of every source, the four counts, and the
  new and removed postings of the latest run.
- **Browse** (`browse.html`): open postings with a my-role / all switch, filters for employer,
  location and days open, a title search, a sort by first-seen date, an apply link, and a star that
  saves a posting to a shortlist kept in the browser.
- **Market** (`market.html`): six findings computed from `history.csv`: new postings per day,
  removed postings per day, open postings per employer, days open (median), share removed within
  seven days, and top locations.

The site installs as an app (web app manifest + service worker). Online it loads the data from the
network; offline it opens and shows the last data it loaded.

## Files

| File | What it does |
|---|---|
| `README.md` | This file. |
| `sources.json` | The watch list: one entry per employer with its ATS and board name. |
| `requirements.txt` | Python packages: `requests` and `pytest`. |
| `pytest.ini` | Tells pytest where the tests are. |
| `.gitignore` | Files Git should ignore. |
| `jobwatcher/__init__.py` | Marks the folder as a Python package. |
| `jobwatcher/sources.py` | Fetches each ATS's JSON and converts it to the common columns. |
| `jobwatcher/role.py` | The title rule. |
| `jobwatcher/build.py` | Builds `data/history.csv` from the raw files. |
| `jobwatcher/issue.py` | Writes and opens the daily GitHub Issue and closes the previous one. |
| `jobwatcher/run.py` | The daily run: fetch, build, status, issue. |
| `tests/test_sources.py` | Tests the conversion of every ATS to the common columns. |
| `tests/test_role.py` | Tests the title rule. |
| `tests/test_history.py` | Tests first-seen, last-seen, removed, reopened, failed sources and same-day reruns. |
| `tests/fixtures/*.json` | A small sample answer from each ATS, used by the tests. |
| `.github/workflows/daily.yml` | Runs the pipeline every day at 11:17 UTC, commits the data, publishes the site. |
| `.github/workflows/tests.yml` | Runs pytest on every push. |
| `.github/workflows/pages.yml` | Republishes the site when a site file changes. |
| `scripts/make_site.sh` | Collects the pages and the two data files into `_site/` for GitHub Pages. |
| `index.html`, `browse.html`, `market.html` | The Today, Browse and Market pages. |
| `app.js` | All of the site's code: loading the data, the navigation bar, filters, shortlist, charts. |
| `style.css` | The shared fonts and colors. |
| `manifest.webmanifest` | Web app manifest that makes the site installable. |
| `sw.js` | Service worker: saves the pages and data so the site works offline. |
| `icons/icon-192.png`, `icons/icon-512.png` | App icons. |
| `data/raw/<date>/<source>.json.gz` | What each source returned on each day. |
| `data/history.csv` | One row per posting, built from the raw files. |
| `data/status.json` | The latest run. |

## AI tools

Built with Claude, as the assignment expects.
