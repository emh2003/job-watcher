"""The daily GitHub Issue: one issue per date, listing new and removed postings."""
import os

import requests

LABEL = "job-watcher"
MAX_BODY = 60000  # GitHub's limit is 65,536 characters


def _lines(rows):
    return [f"- [{r['title']}]({r['url']}) — {r['employer']}, {r['location'] or 'location not given'}"
            for r in rows]


def issue_body(date, new, removed, site_url=""):
    """Markdown body. Postings in the watched role are listed first."""
    def section(title, rows):
        out = [f"## {title} ({len(rows)})", ""]
        role = [r for r in rows if r["in_role"]]
        other = [r for r in rows if not r["in_role"]]
        if not rows:
            out.append("None.")
        if role:
            out += ["**In my role**", ""] + _lines(role) + [""]
        if other:
            out += ["**Other postings**", ""] + _lines(other)
        return out + [""]

    lines = [f"Job watcher run for {date} (UTC)."]
    if site_url:
        lines.append(f"Site: {site_url}")
    lines.append("")
    lines += section("New postings", new) + section("Removed postings", removed)
    body = "\n".join(lines)
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY].rsplit("\n", 1)[0] + "\n\n_List cut short to fit; the full lists are on the site._"
    return body


def publish_issue(date, body):
    """Create or update the issue titled with the date and close earlier ones.
    Does nothing (returns None) outside GitHub Actions."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    api = f"https://api.github.com/repos/{repo}"
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})

    issues = s.get(f"{api}/issues", params={"labels": LABEL, "state": "all", "per_page": 100}, timeout=60)
    issues.raise_for_status()
    issues = [i for i in issues.json() if "pull_request" not in i]

    today = next((i for i in issues if i["title"] == date), None)
    if today:  # a second run on the same day updates that day's issue
        r = s.patch(f"{api}/issues/{today['number']}", json={"body": body, "state": "open"}, timeout=60)
    else:
        r = s.post(f"{api}/issues", json={"title": date, "body": body, "labels": [LABEL]}, timeout=60)
    r.raise_for_status()
    number = r.json()["number"]

    for i in issues:
        if i["state"] == "open" and i["number"] != number:
            s.patch(f"{api}/issues/{i['number']}", json={"state": "closed"}, timeout=60).raise_for_status()
    return number
