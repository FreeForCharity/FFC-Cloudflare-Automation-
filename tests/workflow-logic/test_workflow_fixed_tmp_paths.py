"""Unit tests for the fixed-temp-path guard (#1247).

The load-bearing tests here are `test_the_scanner_flags_the_pre_fix_738_body`
and `test_two_concurrent_copies_of_a_body_writing_a_fixed_path_collide`. The
tree is clean by construction after the fix, so every other test in this module
would also pass against a scanner that returned `[]` unconditionally: one feeds
it the exact body that shipped before the fix and requires a finding, the other
demonstrates on the filesystem that the shape the guard rejects really does lose
data when two processes run it at once.

That second one is unusual for this suite -- it measures behaviour rather than
text -- and it is here because AC4 of #1247 asks for the fix to be shown failing
under the old path. A guard whose premise cannot be reproduced is a guard nobody
will believe the next time it is inconvenient.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from wf_extract import child_env, runner_temp, step_run  # noqa: E402

import importlib.util  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "check-workflow-fixed-tmp-paths.py"

_spec = importlib.util.spec_from_file_location("check_workflow_fixed_tmp_paths", GUARD)
guard = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(guard)


def _scan(body: str) -> list[tuple[int, str]]:
    return guard.scan_body(body)


# --- the pre-fix shapes ----------------------------------------------------


def test_the_scanner_flags_the_pre_fix_738_body():
    """The exact three lines 738 shipped before #1247, verbatim.

    Without this the module asserts only that a clean tree is clean.
    """
    body = (
        '            if ! gh api "repos/${repo}/contents/${SMOKE_PATH}" \\\n'
        '                   -H "Accept: application/vnd.github.raw" \\\n'
        "                   >/tmp/smoke-body 2>/tmp/smoke-err; then\n"
        '          entries="/tmp/entries.json"\n'
        "            sha256sum /tmp/smoke-body | cut -d' ' -f1\n"
    )
    hits = [text for _, text in _scan(body)]
    assert sorted(hits) == sorted(
        [
            "/tmp/smoke-body",
            "/tmp/smoke-err",
            "/tmp/entries.json",
            "/tmp/smoke-body",
        ]
    ), hits


def test_the_scanner_flags_a_fixed_path_in_a_github_script_body():
    """743's classify step is JS, not bash, and read three fixed paths."""
    body = (
        "            const targets = JSON.parse(fs.readFileSync('/tmp/targets.json', 'utf8'));\n"
        "              const headPath = `/tmp/probes/${safe}.head`;\n"
    )
    hits = [text for _, text in _scan(body)]
    assert "/tmp/targets.json" in hits, hits
    assert any(h.startswith("/tmp/probes/") for h in hits), hits


def test_a_read_is_a_finding_not_only_a_write():
    """A read is how the collision surfaces, and it depends on some other body
    having written the fixed path in the first place."""
    assert _scan('          body=$(cat /tmp/drift-report.md)\n'), "read not flagged"


def test_a_finding_carries_the_line_it_is_on():
    body = "echo one\necho two\ncat /tmp/x.json\n"
    assert _scan(body) == [(3, "/tmp/x.json")], _scan(body)


# --- what is deliberately NOT a finding ------------------------------------


def test_the_bash_runner_temp_form_is_not_a_finding():
    body = (
        '          tmpd="${RUNNER_TEMP:-/tmp}"\n'
        '          : > "$tmpd/smoke-dispatched.tsv"\n'
        '          } > "${RUNNER_TEMP:-/tmp}/report.md"\n'
    )
    assert _scan(body) == [], _scan(body)


def test_the_node_runner_temp_form_is_not_a_finding():
    body = (
        '            const tmpd = process.env.RUNNER_TEMP || "/tmp";\n'
        '            fs.writeFileSync(tmpd + "/targets.json", "[]");\n'
        "              const headPath = `${tmpd}/probes/${safe}.head`;\n"
    )
    assert _scan(body) == [], _scan(body)


def test_a_comment_line_is_not_a_finding():
    """#1019: four guards in 48h flagged prose about the thing they catch, and
    this guard's own CI step has to name the paths to explain itself."""
    body = (
        "          # RUNNER_TEMP, not /tmp/entries.json, so two local runs cannot\n"
        "          # clobber each other (was /tmp/smoke-body and /tmp/smoke-err).\n"
        "            // const targets = require('/tmp/targets.json');\n"
    )
    assert _scan(body) == [], _scan(body)


def test_a_trailing_comment_on_a_line_of_code_is_still_scanned():
    """Stated so the over-report is a decision and not a surprise: the exclusion
    is by LEADING token, because deciding where a comment starts on a line of
    shell means deciding what is inside a string."""
    assert _scan("          cat /tmp/x  # the old path\n"), "trailing-comment line skipped"


def test_a_bare_tmp_with_no_segment_is_not_a_finding():
    """`TMPDIR=/tmp` names the directory, not a shared file, and the accepted
    RUNNER_TEMP fallbacks end exactly there."""
    assert _scan('          export TMPDIR=/tmp\n') == [], _scan('          export TMPDIR=/tmp\n')


# --- the population, and the freeze ----------------------------------------


def test_the_tree_is_clean():
    findings, errors, scanned = guard.scan_all()
    assert not errors, errors
    assert not findings, [str(f) for f in findings]
    assert scanned > 100, f"only {scanned} files scanned — the walk found almost nothing"


def test_the_scan_reads_real_bodies_and_not_an_empty_set():
    """A scanner that collected no bodies would report the tree clean forever.

    Pinned against a body this repo actually ships rather than a count.
    """
    doc = guard.yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "738-fleet-smoke-engine-drift-audit.yml")
        .read_text(encoding="utf-8")
    )
    bodies = guard.executable_bodies(doc)
    assert bodies, "no executable bodies extracted from 738"
    assert any("fetch_hash()" in b for _, _, b in bodies), (
        "738's gather body was not among the extracted bodies"
    )


def test_the_freeze_is_empty():
    """An entry here is an explicit exception. If one is ever added, this test
    is where the reader is told the normal state changed."""
    assert guard.KNOWN_FIXED_TMP_PATHS == {}, guard.KNOWN_FIXED_TMP_PATHS


def test_a_freeze_entry_naming_a_missing_file_is_an_error():
    errors = guard.compare({}, {"999-not-a-workflow.yml": ("/tmp/x",)})
    assert errors and "no such file" in errors[0], errors


def test_a_stale_freeze_entry_is_an_error():
    """The entry names a real file but a path that is no longer in it."""
    errors = guard.compare(
        {"738-fleet-smoke-engine-drift-audit.yml": []},
        {"738-fleet-smoke-engine-drift-audit.yml": ("/tmp/entries.json",)},
    )
    assert errors and "stale" in errors[0].lower(), errors


def test_a_frozen_path_is_not_reported_but_an_unfrozen_one_in_the_same_file_is():
    errors = guard.compare(
        {"738-fleet-smoke-engine-drift-audit.yml": ["/tmp/entries.json", "/tmp/new.json"]},
        {"738-fleet-smoke-engine-drift-audit.yml": ("/tmp/entries.json",)},
    )
    assert len(errors) == 1, errors
    assert "/tmp/new.json" in errors[0], errors
    assert "/tmp/entries.json" not in errors[0], errors


# --- fail closed -----------------------------------------------------------


def test_unparseable_yaml_is_reported_not_skipped():
    with tempfile.TemporaryDirectory() as td:
        bad = pathlib.Path(td) / "bad.yml"
        bad.write_text("jobs: [\n  unclosed\n", encoding="utf-8")
        findings, errors = guard.scan_file(bad)
        assert not findings
        assert errors and "could not be parsed" in errors[0], errors


def test_a_non_mapping_document_is_reported():
    with tempfile.TemporaryDirectory() as td:
        scalar = pathlib.Path(td) / "scalar.yml"
        scalar.write_text("just a string\n", encoding="utf-8")
        _findings, errors = guard.scan_file(scalar)
        assert errors and "did not parse to a mapping" in errors[0], errors


def test_a_non_string_run_body_is_still_examined():
    """`run:` coerced to a mapping by a templating mistake must not read as
    clean. It is stringified and scanned rather than skipped."""
    doc = {"jobs": {"j": {"steps": [{"name": "s", "run": {"nested": "/tmp/x.json"}}]}}}
    bodies = guard.executable_bodies(doc)
    assert bodies, "a non-string run: was dropped"
    assert _scan(bodies[0][2]), "a non-string run: was not scanned"


# --- the premise, reproduced ------------------------------------------------


def _concurrent_rc(script: str, envs: list[dict]) -> list[int]:
    """Run one script once per env, all at the same time; return the exit codes.

    The envs must DIFFER in MARKER. Two writers of the same bytes cannot
    interfere with each other, and a fixture that passed both processes the same
    marker would report the race as absent — which is how the first draft of
    this test read a working collision as `[0, 0]`.
    """
    procs = [
        subprocess.Popen(
            ["bash", "-c", script],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for env in envs
    ]
    return [p.wait(timeout=120) for p in procs]


# A body of the shape the guard rejects: write a marker, settle, require it back.
# The settle is what makes the race deterministic rather than merely likely.
_COLLIDING = """
set -eu
f={path}
printf '%s' "$MARKER" > "$f"
sleep 0.5
test "$(cat "$f")" = "$MARKER"
"""


def test_two_concurrent_copies_of_a_body_writing_a_fixed_path_collide():
    """The premise. Two processes, one hardcoded path, and at least one loses.

    Runs under the module's own RUNNER_TEMP so the "fixed" path is fixed
    relative to this test rather than to the machine — the point is the SHARED
    name, and putting a real `/tmp/` file in a repo's test suite is the thing
    being argued against.
    """
    shared = f"{runner_temp()}/collide-fixture.txt"
    script = _COLLIDING.format(path=f'"{shared}"')
    codes = _concurrent_rc(script, [child_env(MARKER="A"), child_env(MARKER="B")])
    assert any(rc != 0 for rc in codes), (
        f"two concurrent writers of one fixed path both succeeded ({codes}) — the "
        f"fixture is not reproducing the race this guard exists for"
    )


def test_the_same_body_under_runner_temp_survives_concurrency():
    """The fix, on the same fixture: distinct RUNNER_TEMP, no interference."""
    script = _COLLIDING.format(path='"${RUNNER_TEMP:-/tmp}/collide-fixture.txt"')
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        codes = _concurrent_rc(
            script,
            [child_env(RUNNER_TEMP=a, MARKER="A"), child_env(RUNNER_TEMP=b, MARKER="B")],
        )
    assert codes == [0, 0], f"isolated writers still interfered: {codes}"


# --- the harness half of the fix -------------------------------------------


def test_child_env_hands_the_child_a_runner_temp():
    env = child_env()
    assert env.get("RUNNER_TEMP") == runner_temp(), env.get("RUNNER_TEMP")
    assert pathlib.Path(env["RUNNER_TEMP"]).is_dir(), env["RUNNER_TEMP"]


def test_child_env_runner_temp_can_still_be_overridden():
    """A module that wants its own scratch directory must be able to say so."""
    assert child_env(RUNNER_TEMP="/somewhere/else")["RUNNER_TEMP"] == "/somewhere/else"


def test_the_720_bodies_that_were_fixed_read_runner_temp():
    """Spot-check the two bodies whose modules execute them, so a revert to a
    fixed path fails here as well as in the tree-wide scan."""
    gather = step_run("738-fleet-smoke-engine-drift-audit.yml", "audit", "Gather smoke-engine hashes")
    assert "RUNNER_TEMP" in gather, "738's gather step no longer reads RUNNER_TEMP"
    dispatch = step_run(
        "120-bulk-cutover-to-github-pages.yml", "post-cutover-smoke", "Dispatch Post-Deploy Smoke"
    )
    assert "RUNNER_TEMP" in dispatch, "120's dispatch step no longer reads RUNNER_TEMP"


# --- wiring -----------------------------------------------------------------


def test_the_guard_is_wired_into_ci():
    """A checker nobody runs is the failure mode this whole class is about."""
    ci = (REPO_ROOT / ".github" / "workflows" / "722-ci.yml").read_text(encoding="utf-8")
    assert "scripts/check-workflow-fixed-tmp-paths.py" in ci, (
        "check-workflow-fixed-tmp-paths.py must run in 722-ci.yml, or the rule is "
        "documentation"
    )


def test_the_guard_installs_its_own_yaml_dependency_in_ci():
    """The runner image only happens to preinstall PyYAML; without the install
    an image that drops it turns this guard into an ImportError, which is a red
    build that says nothing about temp paths."""
    ci = (REPO_ROOT / ".github" / "workflows" / "722-ci.yml").read_text(encoding="utf-8")
    block = ci.split("Validate no workflow body names a fixed temp path", 1)[1]
    block = block.split("scripts/check-workflow-fixed-tmp-paths.py", 1)[0]
    assert "pip install --quiet pyyaml" in block, (
        "the fixed-temp-path step must install PyYAML defensively, like its siblings"
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
