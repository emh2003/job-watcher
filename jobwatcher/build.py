"""Build data/history.csv from the raw files alone.

    python -m jobwatcher.build

Replays every day in data/raw/ in date order, so running it again gives the
same file, and a change to a rule (for example the title rule) applies to
every day of the history.
"""
import csv
import gzip
import json
from pathlib import Path

from .role import in_role
from .sources import ROOT, load_sources, normalize

COLUMNS = ["posting_id", "source", "source_id", "employer", "title", "location", "department",
           "posted_date", "url", "in_role", "first_run", "first_seen", "last_seen", "status",
           "removed_date"]


def raw_dates(raw_dir):
    """Dates (YYYY-MM-DD) that have at least one raw file, oldest first."""
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        return []
    return sorted(d.name for d in raw_dir.iterdir() if d.is_dir() and any(d.glob("*.json.gz")))


def read_raw(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def build_history(raw_dir, sources):
    """Return the history rows (list of dicts, sorted by posting_id)."""
    history = {}        # posting_id -> row
    first_file = {}     # source name -> date of its first raw file
    for date in raw_dates(raw_dir):
        for src in sources:
            path = Path(raw_dir) / date / f"{src['name']}.json.gz"
            if not path.exists():
                continue  # the source failed that day: leave its postings untouched
            first_file.setdefault(src["name"], date)
            listed = set()
            for p in normalize(src, read_raw(path)):
                pid = f"{src['name']}:{p['source_id']}"
                listed.add(pid)
                row = history.get(pid)
                if row is None:
                    row = history[pid] = {
                        "posting_id": pid, "source": src["name"],
                        "first_run": date == first_file[src["name"]],
                        "first_seen": date,
                    }
                row.update(p)                       # latest title, location, url ...
                row["in_role"] = in_role(p["title"])
                row["last_seen"] = date
                row["status"] = "open"              # also reopens a removed posting
                row["removed_date"] = ""
            for pid, row in history.items():
                if row["source"] == src["name"] and row["status"] == "open" and pid not in listed:
                    row["status"] = "removed"
                    row["removed_date"] = date
    return [history[k] for k in sorted(history)]


def write_history(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for row in rows:
            out = dict(row)
            out["in_role"] = "true" if row["in_role"] else "false"
            out["first_run"] = "true" if row["first_run"] else "false"
            w.writerow(out)


def main():
    rows = build_history(ROOT / "data" / "raw", load_sources())
    write_history(rows, ROOT / "data" / "history.csv")
    print(f"history.csv: {len(rows)} postings, {sum(r['status'] == 'open' for r in rows)} open")


if __name__ == "__main__":
    main()
