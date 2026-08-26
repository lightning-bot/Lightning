"""Creates GitHub issues for new unresolved Sentry issues that don't already have one.

Requires env vars: SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT,
GITHUB_TOKEN, GITHUB_REPOSITORY.
"""
from __future__ import annotations

import os
import sys

import requests

SENTRY_AUTH_TOKEN = os.environ["SENTRY_AUTH_TOKEN"]
SENTRY_ORG = os.environ["SENTRY_ORG"]
SENTRY_PROJECT = os.environ["SENTRY_PROJECT"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]

# How far back to look for "new" issues on each run.
STATS_PERIOD = os.environ.get("SENTRY_STATS_PERIOD", "24h")
ISSUE_LABEL = "sentry"

SENTRY_API = "https://sentry.io/api/0"
GITHUB_API = "https://api.github.com"

sentry_session = requests.Session()
sentry_session.headers.update({"Authorization": f"Bearer {SENTRY_AUTH_TOKEN}"})

github_session = requests.Session()
github_session.headers.update({
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
})


def get_new_sentry_issues() -> list[dict]:
    issues = []
    url = f"{SENTRY_API}/projects/{SENTRY_ORG}/{SENTRY_PROJECT}/issues/"
    params = {
        "query": "is:unresolved is:for_review",
        "statsPeriod": STATS_PERIOD,
        "sort": "new",
    }

    while url:
        resp = sentry_session.get(url, params=params)
        resp.raise_for_status()
        issues.extend(resp.json())

        # Sentry paginates via the Link header, subsequent requests don't need params again.
        params = None
        url = None
        next_link = resp.links.get("next")
        if next_link and next_link.get("results") == "true":
            url = next_link["url"]

    return issues


def find_existing_github_issue(short_id: str) -> bool:
    query = f'repo:{GITHUB_REPOSITORY} in:body "{short_id}" is:issue'
    resp = github_session.get(f"{GITHUB_API}/search/issues", params={"q": query})
    resp.raise_for_status()
    return resp.json()["total_count"] > 0


def create_github_issue(sentry_issue: dict) -> None:
    short_id = sentry_issue["shortId"]
    title = sentry_issue.get("title") or sentry_issue.get("culprit") or short_id
    permalink = sentry_issue.get("permalink", "")
    culprit = sentry_issue.get("culprit", "N/A")
    level = sentry_issue.get("level", "unknown")
    count = sentry_issue.get("count", "unknown")

    body = (
        f"**Sentry Issue:** {short_id}\n"
        f"**Level:** {level}\n"
        f"**Culprit:** {culprit}\n"
        f"**Events:** {count}\n\n"
        f"[View in Sentry]({permalink})"
    )

    payload = {
        "title": f"[Sentry] {title}",
        "body": body,
        "labels": [ISSUE_LABEL],
    }
    resp = github_session.post(f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/issues", json=payload)
    resp.raise_for_status()
    print(f"Created issue for {short_id}: {resp.json()['html_url']}")


def main() -> int:
    try:
        issues = get_new_sentry_issues()
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            print(
                f"⚠️ Sentry API request failed with HTTP {status}. "
                "This usually means SENTRY_AUTH_TOKEN is missing the 'event:read' "
                "and/or 'project:read' scopes required to list issues."
            )
        raise

    print(f"Found {len(issues)} unresolved Sentry issue(s) in the last {STATS_PERIOD}.")

    for issue in issues:
        short_id = issue["shortId"]
        if find_existing_github_issue(short_id):
            print(f"Skipping {short_id}, a GitHub issue already exists.")
            continue

        create_github_issue(issue)

    return 0


if __name__ == "__main__":
    sys.exit(main())
