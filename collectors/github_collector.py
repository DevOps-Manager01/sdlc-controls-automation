"""
github_collector.py
--------------------
Pulls raw evidence from the GitHub API for every repo listed in config.yaml.
Writes one evidence JSON file per repo to reports/evidence_<repo>.json.

Auth: expects a GITHUB_TOKEN environment variable (a fine-grained PAT with
read-only Contents, Pull requests, Issues, Metadata, and Administration
permissions — see SETUP.md for exact scopes).

This file does NOT decide pass/fail — it only collects facts. Scoring
logic lives in evaluators/evaluate_controls.py, kept separate on purpose
so the "what happened" and "was that okay" concerns don't get tangled.
"""

import os
import re
import sys
import json
import time
import yaml
import requests

API_ROOT = "https://api.github.com"
CLOSING_KEYWORDS = re.compile(
    r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)", re.IGNORECASE
)


def _headers():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get(url, params=None):
    """GET with basic pagination handling and gentle rate-limit backoff."""
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset - time.time(), 1)
            print(f"Rate limited, waiting {wait:.0f}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data  # single-object endpoints (e.g. branch protection)
        url = resp.links.get("next", {}).get("url")
        params = None  # params only needed on first request
    return results


def get_branch_protection(org, repo, branch):
    url = f"{API_ROOT}/repos/{org}/{repo}/branches/{branch}/protection"
    try:
        return _get(url)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None  # no protection configured at all
        raise


def get_pull_requests(org, repo):
    """All PRs (open + closed), each enriched with its reviews."""
    prs = _get(f"{API_ROOT}/repos/{org}/{repo}/pulls", params={"state": "all", "per_page": 100})
    enriched = []
    for pr in prs:
        number = pr["number"]
        reviews = _get(f"{API_ROOT}/repos/{org}/{repo}/pulls/{number}/reviews")
        body = pr.get("body") or ""
        closing_issue_numbers = [int(m.group(3)) for m in CLOSING_KEYWORDS.finditer(body)]
        enriched.append({
            "number": number,
            "title": pr.get("title"),
            "author": pr.get("user", {}).get("login"),
            "state": pr.get("state"),
            "merged_at": pr.get("merged_at"),
            "body": body,
            "closing_issues": closing_issue_numbers,
            "head_sha": pr.get("head", {}).get("sha"),
            "reviews": [
                {
                    "author": r.get("user", {}).get("login"),
                    "state": r.get("state"),
                    "submitted_at": r.get("submitted_at"),
                }
                for r in reviews
            ],
        })
    return enriched


def get_check_runs(org, repo, sha):
    if not sha:
        return []
    data = _get(f"{API_ROOT}/repos/{org}/{repo}/commits/{sha}/check-runs")
    runs = data.get("check_runs", []) if isinstance(data, dict) else []
    return [{"name": r.get("name"), "conclusion": r.get("conclusion")} for r in runs]


def get_collaborators(org, repo):
    data = _get(f"{API_ROOT}/repos/{org}/{repo}/collaborators", params={"per_page": 100})
    return [
        {
            "login": c.get("login"),
            "role_name": c.get("role_name"),
            "permissions": c.get("permissions"),
        }
        for c in data
    ]


def collect_for_repo(org, repo_cfg):
    repo = repo_cfg["name"]
    branch = repo_cfg.get("default_branch", "main")
    print(f"Collecting evidence for {org}/{repo} ...")

    protection = get_branch_protection(org, repo, branch)
    pull_requests = get_pull_requests(org, repo)

    for pr in pull_requests:
        pr["check_runs"] = get_check_runs(org, repo, pr.get("head_sha"))

    collaborators = get_collaborators(org, repo)

    return {
        "org": org,
        "repo": repo,
        "default_branch": branch,
        "codeowner_required": repo_cfg.get("codeowner_required", False),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "branch_protection": protection,
        "pull_requests": pull_requests,
        "collaborators": collaborators,
    }


def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    org = config["org"]
    os.makedirs("reports", exist_ok=True)

    for repo_cfg in config["repos"]:
        evidence = collect_for_repo(org, repo_cfg)
        out_path = f"reports/evidence_{repo_cfg['name']}.json"
        with open(out_path, "w") as f:
            json.dump(evidence, f, indent=2)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
