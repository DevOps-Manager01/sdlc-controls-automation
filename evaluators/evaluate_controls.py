"""
evaluators/evaluate_controls.py
--------------------------------
Reads:
  - controls/*.yaml           (what "compliant" means for each control)
  - reports/evidence_*.json    (facts collected by github_collector.py)

Writes:
  - reports/results.json       (pass/fail per control, per repo, with detail)

Each evaluate_* function below takes the raw evidence dict for one repo and
returns a list of per-PR (or per-item) findings, plus an overall status.
Kept deliberately simple and readable over clever — this is meant to be
read by non-engineers (auditors, reviewers) as much as it is run by CI.
"""

import os
import glob
import json
import yaml


def evaluate_segregation_of_duties(evidence):
    findings = []
    for pr in evidence["pull_requests"]:
        if pr["state"] != "closed" or not pr.get("merged_at"):
            continue  # only judge PRs that were actually merged
        author = pr["author"]
        approvals = [r for r in pr["reviews"] if r["state"] == "APPROVED" and r["author"] != author]
        passed = len(approvals) >= 1
        findings.append({
            "pr_number": pr["number"],
            "title": pr["title"],
            "author": author,
            "approving_reviewers": [a["author"] for a in approvals],
            "status": "PASS" if passed else "FAIL",
            "detail": (
                f"Approved by {', '.join(a['author'] for a in approvals)}"
                if passed else
                "No independent approving review found before merge."
            ),
        })
    overall = "PASS" if findings and all(f["status"] == "PASS" for f in findings) else (
        "FAIL" if any(f["status"] == "FAIL" for f in findings) else "NO_DATA"
    )
    return overall, findings


def evaluate_branch_protection(evidence):
    protection = evidence.get("branch_protection")
    if not protection:
        return "FAIL", [{"detail": f"No branch protection configured on '{evidence['default_branch']}'."}]

    checks = []
    required_reviews = protection.get("required_pull_request_reviews")
    checks.append(("Pull request reviews required", bool(required_reviews)))

    force_push_allowed = protection.get("allow_force_pushes", {}).get("enabled", False)
    checks.append(("Force pushes disallowed", force_push_allowed is False))

    deletions_allowed = protection.get("allow_deletions", {}).get("enabled", False)
    checks.append(("Branch deletion disallowed", deletions_allowed is False))

    enforce_admins = protection.get("enforce_admins", {}).get("enabled", False)
    checks.append(("Enforced for admins (no bypass)", enforce_admins is True))

    findings = [{"detail": name, "status": "PASS" if ok else "FAIL"} for name, ok in checks]
    overall = "PASS" if all(ok for _, ok in checks) else "FAIL"
    return overall, findings


def evaluate_security_gate(evidence):
    protection = evidence.get("branch_protection") or {}
    required_contexts = (protection.get("required_status_checks") or {}).get("contexts", [])

    findings = []
    for pr in evidence["pull_requests"]:
        if pr["state"] != "closed" or not pr.get("merged_at"):
            continue
        run_results = {r["name"]: r["conclusion"] for r in pr.get("check_runs", [])}
        missing_or_failed = [
            ctx for ctx in required_contexts
            if run_results.get(ctx) != "success"
        ]
        passed = len(missing_or_failed) == 0
        findings.append({
            "pr_number": pr["number"],
            "title": pr["title"],
            "required_checks": required_contexts,
            "status": "PASS" if passed else "FAIL",
            "detail": (
                "All required checks passed."
                if passed else
                f"Missing/failed required checks: {', '.join(missing_or_failed) or 'none configured'}"
            ),
        })

    if not required_contexts:
        return "FAIL", [{"detail": "No required status checks are configured in branch protection."}]

    overall = "PASS" if findings and all(f["status"] == "PASS" for f in findings) else (
        "FAIL" if any(f["status"] == "FAIL" for f in findings) else "NO_DATA"
    )
    return overall, findings


def evaluate_traceability(evidence):
    findings = []
    for pr in evidence["pull_requests"]:
        if pr["state"] != "closed" or not pr.get("merged_at"):
            continue
        linked = pr.get("closing_issues", [])
        passed = len(linked) > 0
        findings.append({
            "pr_number": pr["number"],
            "title": pr["title"],
            "linked_issues": linked,
            "status": "PASS" if passed else "FAIL",
            "detail": (
                f"Linked to issue(s): {', '.join('#' + str(i) for i in linked)}"
                if passed else
                "No linked issue found in PR description (no closing keyword detected)."
            ),
        })
    overall = "PASS" if findings and all(f["status"] == "PASS" for f in findings) else (
        "FAIL" if any(f["status"] == "FAIL" for f in findings) else "NO_DATA"
    )
    return overall, findings


def evaluate_access_review(evidence):
    """
    This control is intentionally not scored PASS/FAIL by the automation.
    Least-privilege is a judgment call a human has to make (does this
    person's access level still match their actual role?) — the automation's
    job is to produce a clean, dated snapshot for that human decision, not
    to fake an automated verdict on something it can't actually judge.
    """
    findings = [
        {
            "login": c["login"],
            "role": c["role_name"],
            "detail": f"{c['login']} currently has '{c['role_name']}' access.",
            "status": "EVIDENCE",
        }
        for c in evidence.get("collaborators", [])
    ]
    return "EVIDENCE_CAPTURED", findings


EVALUATORS = {
    "evaluate_segregation_of_duties": evaluate_segregation_of_duties,
    "evaluate_branch_protection": evaluate_branch_protection,
    "evaluate_security_gate": evaluate_security_gate,
    "evaluate_traceability": evaluate_traceability,
    "evaluate_access_review": evaluate_access_review,
}


def load_controls():
    controls = []
    for path in sorted(glob.glob("controls/*.yaml")):
        with open(path) as f:
            controls.append(yaml.safe_load(f))
    return controls


def load_evidence():
    evidence_by_repo = {}
    for path in sorted(glob.glob("reports/evidence_*.json")):
        with open(path) as f:
            data = json.load(f)
            evidence_by_repo[data["repo"]] = data
    return evidence_by_repo


def main():
    controls = load_controls()
    evidence_by_repo = load_evidence()

    results = {
        "generated_at": None,
        "controls": [],
    }
    import time
    results["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for control in controls:
        evaluator_fn = EVALUATORS[control["evaluator"]]
        control_result = {
            "id": control["id"],
            "name": control["name"],
            "description": control["description"].strip(),
            "framework_mapping": control["framework_mapping"],
            "per_repo": {},
        }
        for repo_name, evidence in evidence_by_repo.items():
            overall, findings = evaluator_fn(evidence)
            control_result["per_repo"][repo_name] = {
                "overall": overall,
                "findings": findings,
            }
        results["controls"].append(control_result)

    os.makedirs("reports", exist_ok=True)
    with open("reports/results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Wrote reports/results.json")


if __name__ == "__main__":
    main()
