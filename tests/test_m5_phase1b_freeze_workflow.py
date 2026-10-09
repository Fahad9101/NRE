"""The Milestone 5 Phase 1b SEC cohort freeze workflow must never be able to re-freeze or overwrite the frozen pool, must read no price, and must run only on its own two files.

The standard library has no YAML parser, so the checks read the workflow text: which events trigger it, and the order and content of its steps. Each check is itself run against deliberately broken copies of the
workflow, and the guard's shell behaviour is run against throwaway git repositories (only where bash and git are on the PATH and the platform is not Windows; CI covers it, and NRE_SHELL_TESTS=1 forces it
elsewhere, for example under Git Bash).
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ".github/workflows/m5-phase1b-sec-cohort-freeze.yml"
TEXT = (ROOT / WORKFLOW).read_text(encoding="utf-8")
PUSH_PATHS = [".github/workflows/m5-phase1b-sec-cohort-freeze.yml", "config/m5-phase1b-cohort-spec.json"]
FROZEN = ("config/m5-phase1b-frozen-issuer-cohort.json", "config/m5-phase1b-frozen-candidate-ledger.json", "reports/m5-phase1b-sec-cohort-freeze.json", "archive/m5-phase1b-sec-freeze")
WRITES = ("cp ", "mkdir -p archive", "git add", "git commit", "git push")
HAZARDS = ("urllib", "freeze-targeted-cohort", "unittest") + WRITES  # network acquisition, and anything that changes the repository

# An abbreviated copy of a freeze workflow with no guard, triggered by any push to the code it uses.
UNGUARDED = """name: NRE M5 Phase 1b SEC Cohort Freeze

on:
  push:
    paths:
      - 'nre/cli.py'
      - 'nre/depth_cohort.py'

permissions:
  contents: write

jobs:
  freeze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Freeze deterministic targeted candidate membership
        run: |
          python -m nre.cli freeze-targeted-cohort --spec config/m5-phase1b-cohort-spec.json --protocol config/m5-phase1b-protocol.json --output /tmp/nre-m5-phase1b-freeze
      - name: Publish frozen metadata only from unchanged source SHA
        run: |
          cp /tmp/nre-m5-phase1b-freeze/issuer-cohort.json config/m5-phase1b-frozen-issuer-cohort.json
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


def push_paths(text):
    match = re.search(r"(?m)^  push:\s*\n    paths:\s*\n((?:      - '[^']+'\s*\n)+)", text)
    return re.findall(r"'([^']+)'", match.group(1)) if match else None


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
    """A guard reads origin/main's tree with git ls-tree, names every frozen path, fails closed and exits non-zero."""
    code = script(step_text)
    listed = re.search(r"(?m)^for path in ([^;\n]+); do$", code)             # the loop's own list, since a path named elsewhere in the step (a copy, a git add) is not checked
    return bool(code and "git fetch origin main" in code and re.search(r"git ls-tree[^\n]*\borigin/main\b", code)
                and listed and set(FROZEN) <= set(listed.group(1).split()) and re.search(r"(?m)^set -[a-z]*e", code) and re.search(r"\bexit 1\b", code)
                and "|| true" not in code and "|| :" not in code)


def covered(destination):
    return any(destination == path or destination.startswith(path + "/") for path in FROZEN)


def problems(text):
    found = []
    triggers = events(text)
    if sorted(triggers or []) != ["push", "workflow_dispatch"]:
        found.append("it can be triggered by %s, not only by a push of its own files or by hand" % (triggers,))
    if push_paths(text) != PUSH_PATHS:
        found.append("it runs on pushes touching %s, not only its own two files" % (push_paths(text),))
    parts = steps(text)
    guards = [i for i, part in enumerate(parts) if is_guard(part["text"])]
    if not guards:
        return found + ["no step checks origin/main for an existing frozen file"]
    if guards[0] != 1 or parts[0]["name"] != "actions/checkout@v4":
        found.append("the first guard does not directly follow the checkout")
    for i, part in enumerate(parts):
        if i < guards[0] and any(marker in part["text"] for marker in HAZARDS):
            found.append("step %r can run before the first guard" % part["name"])
        code = script(part["text"])
        writes = [code.find(marker) for marker in WRITES if marker in code]
        if writes and (not is_guard(part["text"]) or code.find("git ls-tree") > min(writes)):
            found.append("step %r changes the repository without checking first" % part["name"])
    publish = [part for part in parts if "git push" in part["text"]]
    if len(publish) != 1:
        found.append("exactly one step must push")
    else:
        code = script(publish[0]["text"])
        if 'test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"' not in code:
            found.append("the publish step does not check that main is unchanged")
        destinations = re.findall(r"cp (?:-r )?/tmp/nre-m5-phase1b-freeze/\S+ (\S+)", code)
        if not destinations or not all(covered(d) for d in destinations) or not all(any(d == p or d.startswith(p + "/") for d in destinations) for p in FROZEN):
            found.append("the publish step copies somewhere the guards do not name, or does not copy a frozen path: %s" % (destinations,))
    if not re.search(r"(?m)^permissions:\n  contents: write\n(?=\n|\S)", text):
        found.append("permissions are not exactly contents: write")
    if not re.search(r"(?m)^  cancel-in-progress: false\s*$", text):
        found.append("a run in progress can be cancelled")
    if "    if: github.actor != 'github-actions[bot]'\n" not in text:
        found.append("the bot's own commit is not kept from re-running it")
    if re.search(r"secrets\.|APCA|alpaca", text, re.I):
        found.append("it touches provider secrets or Alpaca")
    return found


def indented(code):
    return "".join("          " + line if line.strip() else line for line in code.splitlines(True))


GUARD_STEP = re.search(r"      - name: Refuse to run while[\s\S]*?(?=      - uses: actions/setup-python)", TEXT).group(0)
GUARD_CODE = script(GUARD_STEP)


def without_publish_guard(text):
    head, marker, tail = text.partition("      - name: Publish frozen metadata")
    return head + marker + tail.replace(indented(GUARD_CODE), "", 1)


def replace_last(text, old, new):
    head, marker, tail = text.rpartition(old)
    assert marker, old
    return head + new + tail


MUTATIONS = {
    "a schedule trigger is added": lambda t: t.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  schedule:\n    - cron: '0 0 * * *'\n", 1),
    "the push trigger is dropped": lambda t: t.replace("  push:\n    paths:\n      - '.github/workflows/m5-phase1b-sec-cohort-freeze.yml'\n      - 'config/m5-phase1b-cohort-spec.json'\n", "", 1),
    "the push paths are widened": lambda t: t.replace("      - 'config/m5-phase1b-cohort-spec.json'\n", "      - 'config/m5-phase1b-cohort-spec.json'\n      - 'nre/cli.py'\n", 1),
    "the early guard is removed": lambda t: t.replace(GUARD_STEP, "", 1),
    "a frozen file is left out of the early guard": lambda t: t.replace(" archive/m5-phase1b-sec-freeze; do", "; do", 1),
    "a frozen file is left out of the publish guard": lambda t: replace_last(t, " archive/m5-phase1b-sec-freeze; do", "; do"),
    "the publish guard is removed": without_publish_guard,
    "the guard runs only after the freeze": lambda t: t.replace(GUARD_STEP, "", 1).replace("      - name: Verify freeze result", GUARD_STEP + "      - name: Verify freeze result", 1),
    "the early guard swallows its failure": lambda t: t.replace("              exit 1\n", "              exit 1 || true\n", 1),
    "the early guard no longer exits": lambda t: t.replace("              exit 1\n", "              echo stop\n", 1),
    "the source SHA check is removed": lambda t: t.replace('          test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"\n', "", 1),
    "the raw bytes are copied somewhere unguarded": lambda t: t.replace("archive/m5-phase1b-sec-freeze/raw\n", "archive/elsewhere/raw\n", 1),
    "the ledger is copied over an unguarded path": lambda t: t.replace("config/m5-phase1b-frozen-candidate-ledger.json\n          cp", "config/m5-phase1b-candidates.json\n          cp", 1),
    "provider secrets appear": lambda t: t.replace("        env:\n          SEC_USER_AGENT", "        env:\n          APCA_API_KEY_ID: ${{ secrets.APCA_API_KEY_ID }}\n          SEC_USER_AGENT", 1),
    "a run in progress can be cancelled": lambda t: t.replace("cancel-in-progress: false", "cancel-in-progress: true", 1),
    "the bot guard is removed": lambda t: t.replace("    if: github.actor != 'github-actions[bot]'\n", "", 1),
    "the permissions are widened": lambda t: t.replace("permissions:\n  contents: write\n", "permissions:\n  contents: write\n  actions: write\n", 1),
}


class WorkflowTextTests(unittest.TestCase):
    def test_the_workflow_has_no_way_to_overwrite_the_frozen_pool(self):
        self.assertEqual(problems(TEXT), [])

    def test_it_runs_only_on_a_push_of_its_own_two_files_or_by_hand(self):
        self.assertEqual(sorted(events(TEXT)), ["push", "workflow_dispatch"])
        self.assertEqual(push_paths(TEXT), PUSH_PATHS)
        for path in PUSH_PATHS:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_the_first_guard_follows_checkout_and_precedes_all_acquisition_and_publishing(self):
        parts = steps(TEXT)
        self.assertEqual(parts[0]["name"], "actions/checkout@v4")
        self.assertTrue(is_guard(parts[1]["text"]), parts[1]["name"])
        self.assertFalse(any(marker in parts[0]["text"] + parts[1]["text"] for marker in HAZARDS))

    def test_the_publish_step_guards_again_before_it_copies_anything(self):
        publish = next(part for part in steps(TEXT) if "git push" in part["text"])
        code = script(publish["text"])
        self.assertTrue(is_guard(publish["text"]))
        self.assertLess(code.index("git ls-tree"), code.index("cp /tmp/nre-m5-phase1b-freeze"))
        self.assertLess(code.index("exit 1"), code.index("git push"))
        self.assertLess(code.index("git rev-parse origin/main"), code.index("cp /tmp/nre-m5-phase1b-freeze"))

    def test_every_guard_names_every_frozen_path_and_the_publish_step_writes_only_those(self):
        guards = [part for part in steps(TEXT) if is_guard(part["text"])]
        self.assertEqual(len(guards), 2)
        for part in guards:
            for path in FROZEN:
                self.assertIn(path, script(part["text"]))
        publish = script(next(part for part in steps(TEXT) if "git push" in part["text"])["text"])
        self.assertEqual(re.findall(r"cp (?:-r )?/tmp/nre-m5-phase1b-freeze/\S+ (\S+)", publish),
                         ["config/m5-phase1b-frozen-issuer-cohort.json", "config/m5-phase1b-frozen-candidate-ledger.json", "reports/m5-phase1b-sec-cohort-freeze.json", "archive/m5-phase1b-sec-freeze/raw"])
        added = re.search(r"git add (.+)", publish).group(1).split()
        self.assertEqual(added, ["config/m5-phase1b-frozen-issuer-cohort.json", "config/m5-phase1b-frozen-candidate-ledger.json", "reports/m5-phase1b-sec-cohort-freeze.json", "archive/m5-phase1b-sec-freeze"])

    def test_it_freezes_with_the_pre_registered_spec_and_protocol_and_reads_no_price(self):
        freeze = script(next(part for part in steps(TEXT) if "freeze-targeted-cohort" in part["text"])["text"])
        self.assertIn("--spec config/m5-phase1b-cohort-spec.json --protocol config/m5-phase1b-protocol.json", freeze)
        for path in ("config/m5-phase1b-cohort-spec.json", "config/m5-phase1b-protocol.json"):
            self.assertTrue((ROOT / path).is_file())
        self.assertIn('assert report["price_data_accessed_by_this_workflow"] is False', TEXT)
        self.assertNotRegex(TEXT, r"(?i)secrets\.|APCA|alpaca")
        self.assertIn("SEC_USER_AGENT: NRE research contact https://github.com/Fahad9101/NRE", TEXT)
        self.assertIn("python -m unittest discover -s tests", TEXT)

    def test_the_unguarded_workflow_is_flagged(self):
        found = problems(UNGUARDED)
        self.assertTrue(any("triggered by" in line for line in found), found)
        self.assertTrue(any("not only its own two files" in line for line in found), found)
        self.assertTrue(any("no step checks" in line for line in found), found)

    def test_every_deliberate_breakage_is_flagged(self):
        for name, mutate in MUTATIONS.items():
            with self.subTest(name):
                broken = mutate(TEXT)
                self.assertNotEqual(broken, TEXT, "the mutation must change the workflow")
                self.assertNotEqual(problems(broken), [], name)

    def test_the_checks_read_what_they_claim_to(self):
        self.assertEqual(events("name: x\non: push\n"), ["push"])
        self.assertEqual(events("name: x\non:\n  push:\n    paths:\n      - 'a'\n  workflow_dispatch:\n\npermissions:\n  contents: write\n"), ["push", "workflow_dispatch"])
        self.assertEqual(push_paths("on:\n  push:\n    paths:\n      - 'a'\n      - 'b'\n  workflow_dispatch:\n"), ["a", "b"])
        self.assertIsNone(push_paths("on:\n  workflow_dispatch:\n"))
        self.assertEqual([part["name"] for part in steps(TEXT)][0], "actions/checkout@v4")
        self.assertIn("git ls-tree", GUARD_CODE)
        self.assertTrue(GUARD_CODE.startswith("set -euo pipefail\n"))
        self.assertTrue(covered("archive/m5-phase1b-sec-freeze/raw") and not covered("archive/m5-phase1b-sec-freeze-x/raw") and not covered("config/other.json"))


SHELL_TESTS = bool(shutil.which("bash") and shutil.which("git")) and (os.name != "nt" or os.environ.get("NRE_SHELL_TESTS") == "1")


def git(*args, cwd):
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args], cwd=cwd, check=True, capture_output=True, text=True)


@unittest.skipUnless(SHELL_TESTS, "needs bash and git; CI runs it on Linux, NRE_SHELL_TESTS=1 forces it elsewhere")
class GuardBehaviourTests(unittest.TestCase):
    """Run the workflow's own guard scripts against throwaway repositories standing in for GitHub."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        publish = script(next(part for part in steps(TEXT) if "git push" in part["text"])["text"])
        self.scripts = {"early guard": GUARD_CODE, "publish step up to its first copy": publish.split("cp /tmp/nre-m5-phase1b-freeze", 1)[0]}

    def commit(self, seed, files, note):
        (seed / "README").write_text(note + "\n")
        for path in files:
            target = seed / path
            if path == "archive/m5-phase1b-sec-freeze":                   # a directory: the raw bytes live inside it
                target = target / "raw" / "example.raw"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n")
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

    def test_a_frozen_path_on_main_stops_the_run(self):
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
        self.commit(seed, [FROZEN[0]], "someone freezes the pool")
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
