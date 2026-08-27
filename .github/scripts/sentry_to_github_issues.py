"""Creates GitHub issues for new unresolved Sentry issues that don't already have one.

Requires env vars: SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT,
GITHUB_TOKEN, GITHUB_REPOSITORY.
"""
from __future__ import annotations

import os
import re
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
SENTRY_ID_PATTERN = re.compile(r"\*\*Sentry Issue ID:\*\* (\d+)")
SENTRY_SHORT_ID_PATTERN = re.compile(r"\*\*Sentry Issue:\*\* ([A-Z0-9-]+)")

sentry_session = requests.Session()
sentry_session.headers.update({"Authorization": f"Bearer {SENTRY_AUTH_TOKEN}"})

github_session = requests.Session()
github_session.headers.update({
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
})


def get_sentry_issues(query: str | None = None) -> list[dict]:
    issues = []
    url = f"{SENTRY_API}/projects/{SENTRY_ORG}/{SENTRY_PROJECT}/issues/"
    params = {"sort": "new"}
    if query:
        params["query"] = query
    if query == "is:unresolved is:for_review":
        params["statsPeriod"] = STATS_PERIOD

    while url:
        resp = sentry_session.get(url, params=params)
        resp.raise_for_status()
        issues.extend(resp.json())

        params = None
        url = None
        next_link = resp.links.get("next")
        if next_link and next_link.get("results") == "true":
            url = next_link["url"]

    return issues


def get_new_sentry_issues() -> list[dict]:
    return get_sentry_issues("is:unresolved is:for_review")


def get_sentry_issues_for_sync() -> list[dict]:
    issues_by_id = {}
    for query in ("is:unresolved", "is:resolved", "is:ignored"):
        for issue in get_sentry_issues(query):
            issues_by_id[issue["id"]] = issue
    return list(issues_by_id.values())


def get_sentry_issue(sentry_id: str) -> dict | None:
    resp = sentry_session.get(f"{SENTRY_API}/issues/{sentry_id}/")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_github_issues() -> list[dict]:
    issues = []
    page = 1
    while True:
        resp = github_session.get(
            f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/issues",
            params={"labels": ISSUE_LABEL, "state": "all", "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        page_issues = resp.json()
        issues.extend(issue for issue in page_issues if "pull_request" not in issue)
        if len(page_issues) < 100:
            return issues
        page += 1


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
    sentry_id = sentry_issue["id"]

    body = (
        f"**Sentry Issue:** {short_id}\n"
        f"**Sentry Issue ID:** {sentry_id}\n"
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


def get_sentry_issue_id(github_issue: dict, sentry_issues: dict[str, dict]) -> str | None:
    body = github_issue.get("body") or ""
    match = SENTRY_ID_PATTERN.search(body)
    if match:
        return match.group(1)

    match = SENTRY_SHORT_ID_PATTERN.search(body)
    if match and match.group(1) in sentry_issues:
        return sentry_issues[match.group(1)]["id"]
    return None


def close_github_issue(github_issue: dict) -> None:
    resp = github_session.patch(
        f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/issues/{github_issue['number']}",
        json={"state": "closed"},
    )
    resp.raise_for_status()
    print(f"Closed GitHub issue #{github_issue['number']} because Sentry is resolved.")


def resolve_sentry_issue(sentry_id: str) -> None:
    resp = sentry_session.put(
        f"{SENTRY_API}/issues/{sentry_id}/",
        json={"status": "resolved"},
    )
    resp.raise_for_status()
    print(f"Resolved Sentry issue {sentry_id} because GitHub is closed.")


def synchronize_issue_states(sentry_issues: list[dict], github_issues: list[dict]) -> None:
    sentry_by_id = {issue["id"]: issue for issue in sentry_issues}
    sentry_by_short_id = {issue["shortId"]: issue for issue in sentry_issues}

    for github_issue in github_issues:
        sentry_id = get_sentry_issue_id(github_issue, sentry_by_short_id)
        if not sentry_id:
            continue

        sentry_issue = sentry_by_id.get(sentry_id) or get_sentry_issue(sentry_id)
        if not sentry_issue:
            continue

        if sentry_issue.get("status") in {"resolved", "ignored"} and github_issue["state"] == "open":
            close_github_issue(github_issue)
        elif sentry_issue.get("status") == "unresolved" and github_issue["state"] == "closed":
            resolve_sentry_issue(sentry_id)


def main() -> int:
    try:
        issues = get_new_sentry_issues()
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            print(
                f"::warning::Sentry API request failed with HTTP {status}. "
                "This usually means SENTRY_AUTH_TOKEN is missing the 'event:read' "
                "and/or 'project:read' scopes required to list issues."
            )
        raise

    github_issues = get_github_issues()
    legacy_issues = []
    if any(not SENTRY_ID_PATTERN.search(issue.get("body") or "") for issue in github_issues):
        legacy_issues = get_sentry_issues_for_sync()
    synchronize_issue_states(legacy_issues, github_issues)

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
