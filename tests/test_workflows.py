"""The SEC cohort freeze workflow must never be able to re-freeze or overwrite the frozen Milestone 1 cohort.

The standard library has no YAML parser, so the checks read the workflow text: which events trigger it, and the order and content of
its steps. Each check is itself run against deliberately broken copies of the workflow, and the guard's shell behaviour is run against
throwaway git repositories (only where bash and git are on the PATH and the platform is not Windows; CI covers it, and
NRE_SHELL_TESTS=1 forces it elsewhere, for example under Git Bash).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / ".github" / "workflows" / "sec-cohort-freeze.yml").read_text(encoding="utf-8")
FROZEN = ("config/m1-frozen-issuer-cohort.json", "config/m1-frozen-candidate-ledger.json", "reports/m1-sec-cohort-freeze.json")
WRITES = ("cp /tmp/nre-sec-freeze", "git add", "git commit", "git push")
HAZARDS = ("duckdb", "urllib", "freeze-sec-cohort") + WRITES  # network acquisition, and anything that changes the repository

# An abbreviated copy of the workflow as it stood before the guard: any push touching nre/cli.py would have run it.
ORIGINAL = """name: NRE M1 SEC Cohort Freeze

on:
  push:
    paths:
      - '.github/workflows/sec-cohort-freeze.yml'
      - 'config/sec-cohort-spec.json'
      - 'nre/cohort.py'
      - 'nre/ingestion.py'
      - 'nre/cli.py'

permissions:
  contents: write

jobs:
  freeze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Freeze deterministic historical candidate membership
        run: |
          python -m nre freeze-sec-cohort --spec config/sec-cohort-spec.json
      - name: Publish frozen metadata only from unchanged source SHA
        run: |
          git fetch origin main
          test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
          cp /tmp/nre-sec-freeze/issuer-cohort.json config/m1-frozen-issuer-cohort.json
          git push origin HEAD:main
"""


def events(text):
    """Every event named under the top-level `on:` key, whether written in block or inline form."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^on\s*:", line)), None)
    if start is None:
        return None
    found = re.findall(r"[A-Za-z_]+", re.sub(r"^on\s*:", "", lines[start]).split("#")[0])
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        found += re.findall(r"^  ([A-Za-z_]+)\s*:", line)
    return found


def steps(text):
    """The job's steps, in order, each with its name (or `uses`) and its text."""
    body = text.partition("\n    steps:\n")[2]
    parts = []
    for block in re.split(r"(?m)^(?=      - )", body):
        if block.startswith("      - "):
            parts.append({"name": re.sub(r"^      - (name|uses):\s*", "", block.splitlines()[0]), "text": block})
    return parts


def script(step_text):
    """The shell of a step's `run: |` block, dedented."""
    lines = step_text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^        run:\s*\|\s*$", line)), None)
    if start is None:
        return ""
    body = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith("          "):
            break
        body.append(line[10:] if line.strip() else "")
    return "\n".join(body).strip() + "\n"


def is_guard(step_text):
    """A guard reads origin/main's tree with git ls-tree, names every frozen file, fails closed and exits non-zero."""
    code = script(step_text)
    return bool(code and "git fetch origin main" in code and re.search(r"git ls-tree[^\n]*\borigin/main\b", code)
                and all(path in code for path in FROZEN) and re.search(r"(?m)^set -[a-z]*e", code) and re.search(r"\bexit 1\b", code)
                and "|| true" not in code and "|| :" not in code)


def problems(text):
    found = []
    triggers = events(text)
    if triggers != ["workflow_dispatch"]:
        found.append("it can be triggered by %s, not only by hand" % (triggers,))
    parts = steps(text)
    guards = [i for i, part in enumerate(parts) if is_guard(part["text"])]
    if not guards:
        return found + ["no step checks origin/main for an existing frozen file"]
    for i, part in enumerate(parts):
        if i < guards[0] and any(marker in part["text"] for marker in HAZARDS):
            found.append("step %r can run before the first guard" % part["name"])
        code = script(part["text"])
        writes = [code.find(marker) for marker in WRITES if marker in code]
        if writes and (not is_guard(part["text"]) or code.find("git ls-tree") > min(writes)):
            found.append("step %r changes the repository without checking first" % part["name"])
    return found


def indented(code):
    return "".join("          " + line if line.strip() else line for line in code.splitlines(True))


GUARD_STEP = re.search(r"      - name: Refuse to run while[\s\S]*?(?=      - uses: actions/setup-python)", TEXT).group(0)
GUARD_CODE = script(GUARD_STEP)


def without_publish_guard(text):
    head, marker, tail = text.partition("      - name: Publish frozen metadata")
    return head + marker + tail.replace(indented(GUARD_CODE), "", 1)


MUTATIONS = {
    "a push trigger is added": lambda t: t.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n    paths:\n      - 'nre/cli.py'\n", 1),
    "a pull request trigger is added": lambda t: t.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  pull_request:\n", 1),
    "a schedule is added": lambda t: t.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  schedule:\n    - cron: '0 0 * * *'\n", 1),
    "the events are written inline": lambda t: t.replace("on:\n  workflow_dispatch:\n", "on: [push, workflow_dispatch]\n", 1),
    "the early guard is removed": lambda t: t.replace(GUARD_STEP, "", 1),
    "the publish guard is removed": without_publish_guard,
    "the guard exits zero": lambda t: t.replace("exit 1", "exit 0"),
    "a frozen file is left out of the early guard": lambda t: t.replace(" reports/m1-sec-cohort-freeze.json; do", "; do", 1),
    "the guard no longer fails closed": lambda t: t.replace("set -euo pipefail\n", "", 1),
    "a failed ls-tree is ignored": lambda t: t.replace('-- "$path")"', '-- "$path" || true)"', 1),
    "the guard reads the local HEAD instead of origin/main": lambda t: t.replace("git ls-tree --name-only origin/main", "git ls-tree --name-only HEAD", 1),
    "the guard runs only after the freeze": lambda t: t.replace(GUARD_STEP, "", 1).replace(
        "      - name: Verify source-side freeze boundary", GUARD_STEP + "      - name: Verify source-side freeze boundary", 1),
}


class WorkflowTextTests(unittest.TestCase):
    def test_the_workflow_has_no_way_to_overwrite_the_frozen_cohort(self):
        self.assertEqual(problems(TEXT), [])

    def test_it_runs_only_when_dispatched_by_hand(self):
        self.assertEqual(events(TEXT), ["workflow_dispatch"])

    def test_the_first_guard_follows_checkout_and_precedes_all_acquisition_and_publishing(self):
        parts = steps(TEXT)
        self.assertEqual(parts[0]["name"], "actions/checkout@v4")
        self.assertTrue(is_guard(parts[1]["text"]), parts[1]["name"])
        self.assertFalse(any(marker in parts[0]["text"] + parts[1]["text"] for marker in HAZARDS))

    def test_the_publish_step_guards_again_before_it_copies_anything(self):
        publish = next(part for part in steps(TEXT) if "git push" in part["text"])
        code = script(publish["text"])
        self.assertTrue(is_guard(publish["text"]))
        self.assertLess(code.index("git ls-tree"), code.index("cp /tmp/nre-sec-freeze"))
        self.assertLess(code.index("exit 1"), code.index("git push"))

    def test_every_guard_names_every_frozen_file(self):
        guards = [part for part in steps(TEXT) if is_guard(part["text"])]
        self.assertEqual(len(guards), 2)
        for part in guards:
            for path in FROZEN:
                self.assertIn(path, script(part["text"]))

    def test_the_frozen_files_the_guards_name_are_the_ones_the_workflow_would_overwrite(self):
        publish = script(next(part for part in steps(TEXT) if "git push" in part["text"])["text"])
        overwritten = set(re.findall(r"cp /tmp/nre-sec-freeze/\S+ (\S+)", publish))
        self.assertEqual(overwritten, set(FROZEN))

    def test_the_pre_guard_workflow_is_flagged(self):
        found = problems(ORIGINAL)
        self.assertTrue(any("triggered by" in line for line in found), found)
        self.assertTrue(any("no step checks" in line for line in found), found)

    def test_every_deliberate_breakage_is_flagged(self):
        for name, mutate in MUTATIONS.items():
            with self.subTest(name):
                broken = mutate(TEXT)
                self.assertNotEqual(broken, TEXT, "the mutation must change the workflow")
                self.assertNotEqual(problems(broken), [], name)

    def test_the_checks_read_what_they_claim_to(self):
        self.assertEqual(events("name: x\non: push\n"), ["push"])
        self.assertEqual(events("name: x\non:\n  push:\n    paths:\n      - 'a'\n  workflow_dispatch:\n\npermissions:\n  contents: write\n"),
                         ["push", "workflow_dispatch"])
        self.assertEqual([part["name"] for part in steps(TEXT)][0], "actions/checkout@v4")
        self.assertIn("git ls-tree", script(GUARD_STEP))
        self.assertTrue(script(GUARD_STEP).startswith("set -euo pipefail\n"))


SHELL_TESTS = bool(shutil.which("bash") and shutil.which("git")) and (os.name != "nt" or os.environ.get("NRE_SHELL_TESTS") == "1")


def git(*args, cwd):
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args], cwd=cwd, check=True,
                          capture_output=True, text=True)


@unittest.skipUnless(SHELL_TESTS, "needs bash and git; CI runs it on Linux, NRE_SHELL_TESTS=1 forces it elsewhere")
class GuardBehaviourTests(unittest.TestCase):
    """Run the workflow's own guard scripts against throwaway repositories standing in for GitHub."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        publish = script(next(part for part in steps(TEXT) if "git push" in part["text"])["text"])
        self.scripts = {"early guard": GUARD_CODE, "publish step up to its first copy": publish.split("cp /tmp/nre-sec-freeze", 1)[0]}

    def commit(self, seed, files, note):
        (seed / "README").write_text(note + "\n")
        for path in files:
            (seed / path).parent.mkdir(parents=True, exist_ok=True)
            (seed / path).write_text("{}\n")
        git("add", "-A", cwd=seed)
        git("commit", "-m", note, cwd=seed)

    def scenario(self, name, files=(), branch="main"):
        base = self.root / name
        base.mkdir()
        remote, seed, checkout = base / "remote.git", base / "seed", base / "checkout"
        git("init", "--bare", "--initial-branch=" + branch, str(remote), cwd=base)
        seed.mkdir()
        git("init", "--initial-branch=" + branch, cwd=seed)
        self.commit(seed, files, "first")
        git("push", str(remote), "HEAD:refs/heads/" + branch, cwd=seed)
        git("clone", str(remote), str(checkout), cwd=base)
        return remote, seed, checkout

    def run_guard(self, code, checkout):
        return subprocess.run(["bash", "-c", code], cwd=checkout, capture_output=True, text=True)

    def test_a_frozen_file_on_main_stops_the_run(self):
        for path in FROZEN:
            _, _, checkout = self.scenario("has-" + Path(path).stem, files=[path])
            for name, code in self.scripts.items():
                with self.subTest(path=path, script=name):
                    result = self.run_guard(code, checkout)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(path + " already exists on origin/main", result.stdout + result.stderr)

    def test_a_clean_main_lets_the_run_continue(self):
        _, _, checkout = self.scenario("clean")
        for name, code in self.scripts.items():
            with self.subTest(script=name):
                result = self.run_guard(code, checkout)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_file_that_reaches_main_after_the_checkout_is_still_caught(self):
        remote, seed, checkout = self.scenario("late")
        self.commit(seed, [FROZEN[0]], "someone freezes the cohort")
        git("push", str(remote), "HEAD:refs/heads/main", cwd=seed)
        self.assertFalse((checkout / FROZEN[0]).exists())
        for name, code in self.scripts.items():
            with self.subTest(script=name):
                self.assertEqual(self.run_guard(code, checkout).returncode, 1)

    def test_an_unreachable_main_fails_closed(self):
        _, _, checkout = self.scenario("no-main", branch="other")
        for name, code in self.scripts.items():
            with self.subTest(script=name):
                result = self.run_guard(code, checkout)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
