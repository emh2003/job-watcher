"""Conversion of each applicant tracking system's JSON to the common columns."""
import json
from pathlib import Path

import pytest

from jobwatcher.sources import load_sources, normalize, utc_date, FETCHERS, NORMALIZERS

FIXTURES = Path(__file__).parent / "fixtures"
COMMON = {"source_id", "employer", "title", "location", "department", "posted_date", "url"}


def rows_for(ats, **extra):
    src = {"name": "x", "employer": "Example Co", "ats": ats, "board": "x", **extra}
    return normalize(src, json.loads((FIXTURES / f"{ats}.json").read_text()))


@pytest.mark.parametrize("ats", sorted(NORMALIZERS))
def test_every_ats_gives_exactly_the_common_columns(ats):
    rows = rows_for(ats, host="h.example.com", site="Careers")
    assert rows
    for row in rows:
        assert set(row) == COMMON
        assert row["employer"] == "Example Co"
        assert all(isinstance(v, str) for v in row.values())


def test_greenhouse():
    rows = rows_for("greenhouse")
    assert rows[0] == {
        "source_id": "8172508", "employer": "Example Co", "title": "Senior Financial Analyst, FP&A",
        "location": "Chicago, IL", "department": "",
        "posted_date": "2026-09-04",  # 22:32 at -04:00 is the next day in UTC
        "url": "https://stripe.com/jobs/search?gh_jid=8172508"}
    assert rows[1]["title"] == "Abuse Investigator"  # extra spaces are cleaned
    assert rows[1]["posted_date"] == ""


def test_lever():
    (row,) = rows_for("lever")
    assert row["source_id"] == "2a55d6c9-c564-443a-be3e-a3851db5a93b"
    assert row["title"] == "Account Executive - Commercial"
    assert row["location"] == "New York, NY"
    assert row["department"] == "Operations and Business Support"
    assert row["posted_date"] == utc_date(1792767640768)
    assert row["url"] == "https://jobs.lever.co/spotify/2a55d6c9-c564-443a-be3e-a3851db5a93b"


def test_ashby():
    (row,) = rows_for("ashby")
    assert row["title"] == "Software Engineer, Security, Cloud"
    assert row["location"] == "New York, NY (HQ)"
    assert row["department"] == "Engineering"
    assert row["posted_date"] == "2026-04-07"
    assert row["url"].startswith("https://jobs.ashbyhq.com/ramp/")


def test_smartrecruiters_reads_every_page():
    rows = rows_for("smartrecruiters")
    assert [r["source_id"] for r in rows] == ["744000161904329", "744000161904330"]
    assert rows[0]["location"] == "Austin, TX, United States"
    assert rows[0]["department"] == "Finance"
    assert rows[0]["posted_date"] == "2026-11-16"
    assert rows[0]["url"] == "https://jobs.smartrecruiters.com/Wise/744000161904329"
    assert rows[1]["location"] == "London" and rows[1]["department"] == ""


def test_workday_ids_urls_and_duplicates_across_pages():
    rows = rows_for("workday", host="mastercard.wd1.myworkdayjobs.com", site="CorporateCareers")
    assert [r["source_id"] for r in rows] == ["R-291799", "R-286980-1"]  # repeat on page 2 dropped
    assert rows[0]["url"] == ("https://mastercard.wd1.myworkdayjobs.com/CorporateCareers"
                              "/job/Toronto-Canada/Senior-Specialist--Customer-Success_R-291799")
    assert rows[0]["posted_date"] == "" and rows[0]["department"] == ""


def test_utc_date():
    assert utc_date("2026-11-16T20:07:24.621Z") == "2026-11-16"
    assert utc_date("2026-11-16T23:30:00-06:00") == "2026-11-17"
    assert utc_date(0) == "1970-01-01"
    assert utc_date(None) == "" and utc_date("") == ""


def test_sources_file():
    sources = load_sources()
    assert len(sources) >= 15
    names = [s["name"] for s in sources]
    assert len(names) == len(set(names))
    for s in sources:
        assert s["ats"] in FETCHERS and s["employer"]
