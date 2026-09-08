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
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WF = REPO_ROOT / ".github" / "workflows" / "703-sites-list-generate.yml"


def _workflow() -> dict:
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


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
