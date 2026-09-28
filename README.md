# sdlc-controls-automation

Automated evidence collection and control testing for SDLC change-management
controls, mapped to SOC 2 / ISO 27001 / PCI-DSS / NIST 800-53. This is a
**Continuous Controls Monitoring (CCM)** proof of concept: instead of a
human manually clicking through GitHub settings to confirm a control is
working (which is how most of this was first validated — see
[`sdlc-demo-app`](https://github.com/grc-automation-lab/sdlc-demo-app)), this
repo pulls the same evidence via the GitHub API on a schedule, evaluates it
against a written control definition, and publishes a live dashboard.

**Live dashboard:** https://grc-automation-lab.github.io/sdlc-controls-automation/dashboard.html
*(populates after the first successful workflow run — see SETUP.md)*

## Why this exists

Most GRC work today is manual: screenshots, spreadsheets, quarterly access
review meetings. This project demonstrates the alternative — controls
expressed as code, evaluated automatically, with evidence that's always
current instead of a point-in-time snapshot from an audit cycle.

## Architecture

```
config.yaml                  → which org/repos this automation evaluates
controls/*.yaml              → what "compliant" means for each control,
                                 plus its framework mapping
collectors/github_collector.py → pulls raw facts from the GitHub API
                                   (branch protection, PR reviews, check
                                   runs, collaborator access)
evaluators/evaluate_controls.py → scores the evidence against each
                                    control's pass/fail logic
generate_dashboard.py         → renders results.json into a static,
                                  publishable HTML dashboard
.github/workflows/            → runs the whole pipeline daily and
                                  auto-publishes to GitHub Pages
```

The collector and evaluator are deliberately separate: the collector only
ever states facts ("this PR had these reviews"), never judgments. The
evaluator is the only place "pass/fail" logic lives. This separation is
what makes it possible to change a control's definition without touching
any API-calling code, and to audit *why* something failed without
re-running anything.

## Controls implemented

| ID | Control | SOC 2 | ISO 27001 | PCI-DSS | NIST 800-53 |
|---|---|---|---|---|---|
| CTRL-01 | Segregation of Duties | CC8.1 | A.8.29 | 6.3.2 | CM-3 |
| CTRL-02 | Change control (no direct commits) | CC8.1 | A.8.32 | 6.5.1 | CM-3 |
| CTRL-03 | Automated security testing gate | CC8.1 | A.8.28 | 6.3.1, 6.3.3 | SA-11 |
| CTRL-04 | Change traceability | CC8.1 | A.8.32 | 6.5.1 | CM-3 |
| CTRL-05 | Access review | CC6.1 | A.5.18, A.8.2 | 7.2.1 | AC-2 |

Full descriptions and exact pass/fail logic are in each `controls/*.yaml`
file and its corresponding function in `evaluators/evaluate_controls.py`.

## A documented limitation, on purpose

The organization's Owner account (`Arpit-GRC`) and the designated CODEOWNER
approver (`DevOps-Manager01`) both retain repository Admin rights, meaning
either could, in principle, edit branch protection settings directly rather
than going through the enforced PR/review flow. This automation does not
currently detect or flag that scenario — it evaluates *what actually
happened* (was every merged PR properly reviewed?), not *what was
technically possible*. A more mature version would add a control that
diffs the branch protection ruleset over time and alerts on any change,
which would catch exactly this kind of bypass. Flagging this here
intentionally, since acknowledging a control's limits is itself part of
good control design — most real audits find gaps like this, not zero gaps.

## Running it yourself

See [SETUP.md](SETUP.md) for the no-command-line, click-through setup
(GitHub UI only, matching how the rest of this project was built).
