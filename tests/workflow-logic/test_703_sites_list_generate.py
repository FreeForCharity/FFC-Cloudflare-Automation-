"""Guards for 703's checkout freshness.

703 is a weekly cron whose only job sits on the gated `github-prod`
environment. A cron cannot approve its own gate, so the run waits — and a
run's default checkout is pinned to the SHA it was CREATED at, not the SHA it
eventually runs at. `peter-evans/create-pull-request` branches from whatever is
checked out, so the data PR inherits that staleness.

Measured 2026-09-07: run 11 was created 2026-08-31 and approved seven days
later. It checked out `2ceb54d`, and the PR it opened (#1249) was **133 commits
behind `main`** against Phantom Revert Guard's threshold of 5. The generation
itself was green; the PR simply could not merge without a hand-run
update-branch. That is not a one-off — it recurs every week the gate is
answered late, which is the normal case for a gate a human answers when they
get to it.

The fix is `ref: main` on the checkout, which resolves at checkout time.

These guards are deliberately about the WORKFLOW FILE rather than about a
script's behaviour: the defect lives in the absence of one YAML key, and the
regression is someone dropping it. A test that ran the generator would pass
either way.

Run: python3 tests/workflow-logic/test_703_sites_list_generate.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from wf_extract import find_step, load_workflow, step_run

WF_NAME = "703-sites-list-generate.yml"


def _workflow() -> dict:
    # Shared helper rather than a local read (raised in review on #1254): it
    # centralises the utf-8 rationale, which is not cosmetic — workflow files
    # here carry ✓/❌/em-dashes, and a cp1252 decode on Windows crashes the
    # module before any test runs, printing a traceback instead of FAIL lines.
    return load_workflow(WF_NAME)


def _generate_steps() -> list[dict]:
    wf = _workflow()
    assert "generate" in wf["jobs"], f"703 lost its `generate` job: {sorted(wf['jobs'])}"
    return wf["jobs"]["generate"]["steps"]


def _checkout_steps() -> list[dict]:
    return [s for s in _generate_steps() if "actions/checkout" in str(s.get("uses", ""))]


def test_the_generate_job_checks_out_something():
    """Anchor: if the checkout step is gone, every other guard here is vacuous."""
    steps = _checkout_steps()
    assert len(steps) == 1, f"expected exactly one checkout step in `generate`, found {len(steps)}"


def test_checkout_pins_ref_to_main_not_the_runs_creation_sha():
    """The fix itself. Without `ref:`, the checkout is the run's creation SHA."""
    step = _checkout_steps()[0]
    ref = (step.get("with") or {}).get("ref")
    assert ref is not None, (
        "703's checkout has no `ref:`, so it resolves to the SHA the run was CREATED at. "
        "This job waits on the `github-prod` gate, so that SHA ages by however long the "
        "approval takes, and the data PR is opened that far behind `main` (run 11: 133 "
        "commits behind, Phantom Revert Guard threshold 5). Set `ref: main`."
    )
    assert ref == "main", f"expected `ref: main` on 703's checkout, found {ref!r}"


def test_the_gate_that_makes_this_necessary_is_still_there():
    """
    If 703 ever moves off a gated environment the delay disappears and this
    guard's premise weakens. That is a good outcome, not a silent one: the
    reader should be told the reason changed rather than finding a rule whose
    justification quietly stopped applying.
    """
    job = _workflow()["jobs"]["generate"]
    assert job.get("environment") == "github-prod", (
        "703's `generate` job is no longer on `github-prod`. If it is now ungated, the "
        "approval delay this module exists for is gone — re-read the docstring and decide "
        "whether `ref: main` is still wanted (it probably is, for generator freshness) "
        f"rather than leaving a stale rationale. Found: {job.get('environment')!r}"
    )


def test_the_pr_step_still_branches_from_the_checkout():
    """
    `ref: main` only fixes the PR's base if the PR is still cut from the
    checked-out commit. An explicit `base:` on create-pull-request would make
    the checkout ref irrelevant to the PR and silently re-open the hazard from
    the other side.
    """
    pr_steps = [
        s for s in _generate_steps() if "create-pull-request" in str(s.get("uses", ""))
    ]
    assert len(pr_steps) == 1, f"expected one create-pull-request step, found {len(pr_steps)}"
    with_ = pr_steps[0].get("with") or {}
    base = with_.get("base")
    assert base in (None, "main"), (
        "create-pull-request carries an explicit `base` that is not `main`, so the "
        f"checkout ref no longer determines what the data PR branches from: {base!r}"
    )


# --------------------------------------------------------------------------
# The 601 decoupling.
#
# 703 used to dispatch 601 from inside its own gated job and block on
# `gh run watch`. 601 sits on `wpmudev-prod`, which has a required reviewer, so
# the second approval prompt only APPEARED ~10 minutes after this job's own was
# granted -- and if nobody answered it, the step waited until it timed out,
# wasting the approval already spent on this run. Measured 2026-09-07: the
# operator approved 703, and 601 surfaced as a separate prompt ten minutes later.
#
# 601 now runs on its own cron half an hour earlier, so both approvals are
# pending at the same moment, and 703 reuses 601's newest successful export.
# The reviewer on `wpmudev-prod` is deliberately KEPT -- this is about when the
# approval is asked for, not about removing it.
# --------------------------------------------------------------------------

EXPORT_STEP = "Collect export artifacts"
WPMUDEV_WF = "601-wpmudev-export-sites.yml"


def _export_step_body() -> str:
    return step_run(WF_NAME, "generate", EXPORT_STEP)


def _cron_of(workflow_file: str) -> str:
    on = load_workflow(workflow_file).get("on") or load_workflow(workflow_file).get(True)
    schedules = on.get("schedule") or []
    assert len(schedules) == 1, f"{workflow_file}: expected exactly one cron, got {schedules}"
    return schedules[0]["cron"]


def test_703_does_not_dispatch_the_gated_export():
    """
    Re-adding 601 to the dispatch loop recreates the second, late approval
    prompt and the timeout that wasted the first one.
    """
    body = _export_step_body()
    dispatch_section = body.split("download_latest")[0]
    assert WPMUDEV_WF not in dispatch_section, (
        f"703 dispatches {WPMUDEV_WF} again. That workflow is gated on `wpmudev-prod`, so "
        "dispatching it from inside this already-gated job asks for a second approval ten "
        "minutes after the first, and blocks on it. Let its own cron run it."
    )


def test_703_still_consumes_the_gated_export():
    """
    Dropping the dispatch without the reuse would silently stop feeding WPMUDEV
    membership into the sites list -- green, and quietly wrong.
    """
    body = _export_step_body()
    # Anchored on the call itself, not on the two strings appearing anywhere in
    # the step: an `or` between a precise check and a loose one is only ever as
    # strong as the loose one.
    assert re.search(rf"download_latest_success\s+{re.escape(WPMUDEV_WF)}\s", body), (
        f"703 no longer reuses {WPMUDEV_WF}'s artifact. Dropping the dispatch without the "
        "reuse silently stops feeding WPMUDEV membership into the sites list."
    )


def test_the_reused_export_reports_its_age():
    """
    A reused artifact is by definition old. Using one silently is how the sites
    list would carry stale membership flags with nothing saying so.
    """
    body = _export_step_body()
    # Assert the COMPARISON, not that the words appear. The first version of this
    # guard checked only that `STALE_EXPORT_DAYS` and `::warning::` were present
    # somewhere in the step, and a mutation replacing the condition with
    # `if false; then` passed it — the names survive while the check does not.
    cond = re.search(
        r'if\s+\[\s+"\$age_days"\s+-ge\s+"\$STALE_EXPORT_DAYS"\s+\]', body
    )
    assert cond, (
        "the reuse path no longer compares the artifact's age against "
        "STALE_EXPORT_DAYS, so a months-old export would be used silently"
    )
    # ...and that the branch it guards is the one that warns.
    after = body[cond.end() :].split("fi", 1)[0]
    assert "::warning::" in after, (
        "the staleness branch no longer warns; a stale reused export would pass quietly"
    )
    step = find_step(_workflow(), "generate", EXPORT_STEP)
    threshold = (step.get("env") or {}).get("STALE_EXPORT_DAYS")
    assert threshold is not None and int(threshold) > 0, (
        "STALE_EXPORT_DAYS is not set to a positive value in the step's env, so the "
        f"comparison above reads an empty string and never fires. Found: {threshold!r}"
    )


def test_the_ungated_read_lanes_are_still_dispatched():
    """
    201 and 108 are ungated (`whmcs-prod-read` / `cloudflare-prod-read`), so
    dispatch-and-wait costs nothing. Moving them to reuse would make the sites
    list a week stale for no benefit.
    """
    dispatch_section = _export_step_body().split("download_latest")[0]
    assert "gh workflow run" in dispatch_section, "703 dispatches nothing at all any more"
    for wf in ("201-whmcs-export-domains.yml", "108-export-summary.yml"):
        assert wf in dispatch_section, (
            f"703 no longer dispatches {wf}. It is an ungated read lane, so reusing an old "
            "run would make the sites list a week stale for no benefit."
        )


def test_601_runs_before_703_on_the_same_day():
    """
    The decoupling only removes the second prompt if 601's approval is already
    pending when 703's appears. A later (or differently-scheduled) cron puts it
    back to arriving after.
    """
    wpmudev, sites = _cron_of(WPMUDEV_WF), _cron_of(WF_NAME)
    w_min, w_hour, _, _, w_dow = wpmudev.split()
    s_min, s_hour, _, _, s_dow = sites.split()
    assert w_dow == s_dow, f"601 ({wpmudev}) and 703 ({sites}) no longer run on the same day"
    assert (int(w_hour), int(w_min)) < (int(s_hour), int(s_min)), (
        f"601 ({wpmudev}) must run BEFORE 703 ({sites}) so its approval is already pending "
        "when 703's is granted"
    )


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failures = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL {t.__name__}: {str(e)[:400]}")
    sys.exit(1 if failures else 0)
