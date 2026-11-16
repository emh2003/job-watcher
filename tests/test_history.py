"""First-seen, last-seen, removed and reopened logic, built from raw files."""
import csv
from datetime import datetime, timezone

from jobwatcher.build import COLUMNS, build_history, write_history
from jobwatcher.run import fetch_all, make_status, run, save_raw

A = {"name": "a", "employer": "A Corp", "ats": "greenhouse", "board": "a"}
B = {"name": "b", "employer": "B Corp", "ats": "ashby", "board": "b"}


def gh(*ids, titles=None):
    titles = titles or {}
    return {"jobs": [{"id": i, "title": titles.get(i, f"Job {i}"), "location": {"name": "Remote"},
                      "absolute_url": f"https://a.example/{i}"} for i in ids]}


def ashby(*ids):
    return {"jobs": [{"id": i, "title": f"Role {i}", "location": "NYC", "department": "Finance",
                      "jobUrl": f"https://b.example/{i}"} for i in ids]}


def put(raw_dir, date, src, raw):
    save_raw(raw, raw_dir / date / f"{src['name']}.json.gz")


def by_id(rows):
    return {r["posting_id"]: r for r in rows}


def test_first_seen_last_seen_and_first_run(tmp_path):
    put(tmp_path, "2026-11-01", A, gh(1, 2))
    put(tmp_path, "2026-11-02", A, gh(1, 2, 3))
    h = by_id(build_history(tmp_path, [A]))
    assert h["a:1"]["first_seen"] == "2026-11-01" and h["a:1"]["last_seen"] == "2026-11-02"
    assert h["a:1"]["first_run"] is True
    assert h["a:3"]["first_seen"] == "2026-11-02" and h["a:3"]["first_run"] is False
    assert all(r["status"] == "open" and r["removed_date"] == "" for r in h.values())


def test_removed_gets_that_days_date(tmp_path):
    put(tmp_path, "2026-11-01", A, gh(1, 2))
    put(tmp_path, "2026-11-02", A, gh(1))
    put(tmp_path, "2026-11-03", A, gh(1))
    h = by_id(build_history(tmp_path, [A]))
    assert h["a:2"]["status"] == "removed"
    assert h["a:2"]["removed_date"] == "2026-11-02"
    assert h["a:2"]["last_seen"] == "2026-11-01"


def test_no_raw_file_means_nothing_is_removed(tmp_path):
    put(tmp_path, "2026-11-01", A, gh(1))
    put(tmp_path, "2026-11-01", B, ashby("x"))
    put(tmp_path, "2026-11-02", A, gh(1))        # B failed on the 2nd: no raw file
    put(tmp_path, "2026-11-03", A, gh(1))
    put(tmp_path, "2026-11-03", B, ashby("y"))
    h = by_id(build_history(tmp_path, [A, B]))
    assert h["b:x"]["status"] == "removed" and h["b:x"]["removed_date"] == "2026-11-03"
    assert h["b:x"]["last_seen"] == "2026-11-01"
    assert h["b:y"]["first_seen"] == "2026-11-03" and h["b:y"]["first_run"] is False


def test_first_run_is_per_source(tmp_path):
    put(tmp_path, "2026-11-01", A, gh(1))
    put(tmp_path, "2026-11-02", A, gh(1))
    put(tmp_path, "2026-11-02", B, ashby("x"))   # B's first raw file is a day later
    h = by_id(build_history(tmp_path, [A, B]))
    assert h["b:x"]["first_run"] is True and h["b:x"]["first_seen"] == "2026-11-02"


def test_reopened_posting_keeps_first_seen(tmp_path):
    put(tmp_path, "2026-11-01", A, gh(1, 2))
    put(tmp_path, "2026-11-02", A, gh(1))
    put(tmp_path, "2026-11-03", A, gh(1, 2))
    h = by_id(build_history(tmp_path, [A]))
    assert h["a:2"]["status"] == "open" and h["a:2"]["removed_date"] == ""
    assert h["a:2"]["first_seen"] == "2026-11-01" and h["a:2"]["last_seen"] == "2026-11-03"


def test_rows_sorted_and_in_role_marked(tmp_path):
    put(tmp_path, "2026-11-01", B, ashby("z", "m"))
    put(tmp_path, "2026-11-01", A, gh(2, 10, titles={10: "Financial Analyst"}))
    rows = build_history(tmp_path, [A, B])
    ids = [r["posting_id"] for r in rows]
    assert ids == sorted(ids)
    assert by_id(rows)["a:10"]["in_role"] is True and by_id(rows)["a:2"]["in_role"] is False


def test_build_is_reproducible_and_has_the_columns(tmp_path):
    raw = tmp_path / "raw"
    put(raw, "2026-11-01", A, gh(1, 2))
    put(raw, "2026-11-02", A, gh(2, 3))
    write_history(build_history(raw, [A]), tmp_path / "one.csv")
    write_history(build_history(raw, [A]), tmp_path / "two.csv")
    assert (tmp_path / "one.csv").read_bytes() == (tmp_path / "two.csv").read_bytes()
    with open(tmp_path / "one.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == COLUMNS
    assert {r["in_role"] for r in rows} <= {"true", "false"}
    assert {r["status"] for r in rows} == {"open", "removed"}


def test_one_failing_source_does_not_stop_the_run(tmp_path):
    def fetcher(src):
        if src["name"] == "a":
            raise RuntimeError("blocked")
        return ashby("x", "y")
    results = fetch_all([A, B], tmp_path / "2026-11-01", fetcher)
    assert results[0]["ok"] is False and results[0]["count"] == 0 and "blocked" in results[0]["error"]
    assert results[1] == {"name": "b", "ok": True, "count": 2}
    assert not (tmp_path / "2026-11-01" / "a.json.gz").exists()
    assert (tmp_path / "2026-11-01" / "b.json.gz").exists()


def test_second_run_same_day_replaces_the_day_and_status_counts(tmp_path):
    day1 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    run(tmp_path, day1, lambda s: gh(1, 2), [A])
    run(tmp_path, day2, lambda s: gh(1, 2, 3, 4), [A])
    status = run(tmp_path, day2, lambda s: gh(1, 3), [A])   # second run on day 2
    assert status["first_run_date"] == "2026-11-01"
    assert status["days_with_success"] == 2
    assert status["open"] == 2 and status["new_today"] == 1 and status["removed_today"] == 1
    assert status["run_time"] == "2026-11-02T12:00:00Z"
    assert status["sources"] == [{"name": "a", "ok": True, "count": 2}]
    with open(tmp_path / "data" / "history.csv", newline="") as f:
        ids = [r["posting_id"] for r in csv.DictReader(f)]
    assert ids == ["a:1", "a:2", "a:3"]                    # posting 4 never existed after the rerun
