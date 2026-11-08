"""Read GitHub review and Actions metadata without executing repository code."""
from __future__ import annotations

import json
import re

from .code_changes import CodeJobError, command


def number_from_url(repo, url):
    match = re.fullmatch(rf"https://github\.com/{re.escape(repo)}/pull/([1-9][0-9]*)", url)
    if not match:
        raise CodeJobError("The stored pull request does not belong to the configured repository.")
    return match[1]


def gh_json(cwd, *args):
    return json.loads(command(["gh", *args], cwd).stdout)


def review(cwd, repo, url):
    number = number_from_url(repo, url)
    pr = gh_json(cwd, "pr", "view", number, "--repo", repo, "--json",
                 "state,isDraft,headRefName,headRefOid,isCrossRepository,reviewDecision,"
                 "reviewRequests,reviews,statusCheckRollup")
    prefix = f"https://github.com/{repo}/actions/runs/"
    checks = []
    runs = set()
    for check in pr["statusCheckRollup"]:
        link = check.get("detailsUrl") or check.get("targetUrl") or ""
        match = re.fullmatch(re.escape(prefix) + r"(\d+)(?:/job/\d+)?", link)
        if match:
            runs.add(match[1])
        checks.append({
            "name": check.get("name") or check.get("context"),
            "state": check.get("conclusion") or check.get("status") or check.get("state"),
        })
    evidence = []
    evidence_error = False
    for run in sorted(runs, key=int, reverse=True)[:10]:
        try:
            artifacts = gh_json(cwd, "api", f"repos/{repo}/actions/runs/{run}/artifacts?per_page=100")
        except CodeJobError:
            evidence_error = True
            continue
        evidence.extend({
            "url": f"{prefix}{run}/artifacts/{item['id']}",
            "name": item["name"],
        } for item in artifacts["artifacts"]
          if item["name"] == "review-evidence" and not item["expired"])
    return {
        "state": pr["state"], "draft": pr["isDraft"], "head": pr["headRefOid"],
        "branch": pr["headRefName"], "fork": pr["isCrossRepository"],
        "decision": pr["reviewDecision"], "checks": checks, "evidence": evidence,
        "evidence_error": evidence_error,
        "requests": [item.get("login") or item.get("name") for item in pr["reviewRequests"]],
        "reviews": [
            {"author": (item.get("author") or {}).get("login"),
             "state": item["state"], "body": (item.get("body") or "")[:2000]}
            for item in pr["reviews"][-5:]
        ],
    }
