"""The daily run.

    python -m jobwatcher.run

1. fetch every source into data/raw/<date>/<source>.json.gz
2. build data/history.csv from the raw files
3. write data/status.json
4. open (or update) the day's GitHub Issue and close the previous one
The workflow then commits the data folder.
"""
import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .build import build_history, raw_dates, write_history
from .issue import issue_body, publish_issue
from .sources import ROOT, SEARCH_LIMIT, fetch, load_sources, normalize


def save_raw(raw, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(data)


def fetch_all(sources, day_dir, fetcher=fetch):
    """Fetch every source. A failure is recorded and never stops the run."""
    if day_dir.exists():  # a second run on the same day replaces that day's raw files
        shutil.rmtree(day_dir)
    results = []
    for src in sources:
        try:
            raw = fetcher(src)
            count = len(normalize(src, raw))
            if count == 0:
                # An empty answer would mark every posting of this employer as
                # removed, so it is treated as a failed call.
                raise ValueError("board returned no postings")
            if count > SEARCH_LIMIT and not src.get("search"):
                raise ValueError(f"{count} postings: add a search term for this source")
            save_raw(raw, day_dir / f"{src['name']}.json.gz")
            results.append({"name": src["name"], "ok": True, "count": count})
            print(f"ok    {src['name']}: {count}")
        except Exception as e:  # noqa: BLE001 - any failure is recorded, the run goes on
            results.append({"name": src["name"], "ok": False, "count": 0, "error": f"{type(e).__name__}: {e}"[:200]})
            print(f"FAIL  {src['name']}: {e}")
    return results


def make_status(rows, results, run_time, raw_dir):
    date = run_time.strftime("%Y-%m-%d")
    dates = raw_dates(raw_dir)
    return {
        "run_time": run_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_run_date": dates[0] if dates else None,
        "days_with_success": len(dates),
        "open": sum(r["status"] == "open" for r in rows),
        "new_today": sum(r["first_seen"] == date and not r["first_run"] for r in rows),
        "removed_today": sum(r["removed_date"] == date for r in rows),
        "sources": results,
    }


def run(root=ROOT, now=None, fetcher=fetch, sources=None):
    now = now or datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    sources = sources or load_sources()
    data = Path(root) / "data"

    results = fetch_all(sources, data / "raw" / date, fetcher)
    rows = build_history(data / "raw", sources)
    write_history(rows, data / "history.csv")
    status = make_status(rows, results, now, data / "raw")
    (data / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    new = [r for r in rows if r["first_seen"] == date and not r["first_run"]]
    removed = [r for r in rows if r["removed_date"] == date]
    import os
    number = publish_issue(date, issue_body(date, new, removed, os.environ.get("SITE_URL", "")))
    ok = sum(r["ok"] for r in results)
    print(f"{date}: {ok}/{len(results)} sources ok, {status['open']} open, "
          f"{len(new)} new, {len(removed)} removed" + (f", issue #{number}" if number else ""))
    return status


if __name__ == "__main__":
    run()
