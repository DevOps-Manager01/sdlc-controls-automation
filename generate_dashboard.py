"""
generate_dashboard.py
----------------------
Reads reports/results.json and writes reports/dashboard.html — a single
self-contained static page (no build step, no JS framework) suitable for
publishing via GitHub Pages.
"""

import json
import html

STATUS_COLORS = {
    "PASS": "#1a7f37",
    "FAIL": "#cf222e",
    "NO_DATA": "#9a6700",
    "EVIDENCE_CAPTURED": "#0969da",
}

STATUS_LABELS = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "NO_DATA": "NO DATA YET",
    "EVIDENCE_CAPTURED": "EVIDENCE CAPTURED",
}


def badge(status):
    color = STATUS_COLORS.get(status, "#57606a")
    label = STATUS_LABELS.get(status, status)
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:12px;font-weight:600;">{label}</span>'
    )


def render_findings(findings):
    if not findings:
        return "<p style='color:#57606a;'>No findings recorded.</p>"
    rows = []
    for f in findings:
        detail = html.escape(f.get("detail", ""))
        status = f.get("status")
        status_html = badge(status) if status else ""
        pr = f.get("pr_number")
        pr_label = f"PR #{pr} — " if pr else ""
        title = html.escape(f.get("title", "") or f.get("login", ""))
        rows.append(
            f"<li><strong>{pr_label}{title}</strong> {status_html}"
            f"<br><span style='color:#57606a;font-size:13px;'>{detail}</span></li>"
        )
    return f"<ul style='list-style:none;padding-left:0;'>{''.join(rows)}</ul>"


def render_control(control):
    mapping = control["framework_mapping"]
    mapping_html = " &middot; ".join(f"<strong>{k.upper()}</strong>: {v}" for k, v in mapping.items())

    repo_sections = []
    for repo_name, repo_result in control["per_repo"].items():
        repo_sections.append(f"""
        <div style="margin-top:12px;padding:12px;border:1px solid #d0d7de;border-radius:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong>{html.escape(repo_name)}</strong>
            {badge(repo_result['overall'])}
          </div>
          <div style="margin-top:8px;">{render_findings(repo_result['findings'])}</div>
        </div>
        """)

    return f"""
    <div style="border:1px solid #d0d7de;border-radius:10px;padding:20px;margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;">
        <h2 style="margin:0;font-size:18px;">{html.escape(control['id'])} — {html.escape(control['name'])}</h2>
      </div>
      <p style="color:#57606a;margin-top:8px;">{html.escape(control['description'])}</p>
      <p style="font-size:13px;color:#57606a;">{mapping_html}</p>
      {''.join(repo_sections)}
    </div>
    """


def main():
    with open("reports/results.json") as f:
        results = json.load(f)

    controls_html = "".join(render_control(c) for c in results["controls"])

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SDLC Controls Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1f2328; background:#f6f8fa; }}
  h1 {{ font-size: 26px; }}
  .meta {{ color:#57606a; font-size:13px; margin-bottom:30px; }}
</style>
</head>
<body>
  <h1>SDLC Controls — Continuous Monitoring Dashboard</h1>
  <p class="meta">Generated at {html.escape(results['generated_at'])} UTC &middot;
     Evidence pulled live from the GitHub API &middot;
     <a href="https://github.com/grc-automation-lab/sdlc-controls-automation">source</a></p>
  {controls_html}
</body>
</html>
"""
    with open("reports/dashboard.html", "w") as f:
        f.write(page)
    print("Wrote reports/dashboard.html")


if __name__ == "__main__":
    main()
