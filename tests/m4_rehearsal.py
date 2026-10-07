"""The dress rehearsal's machinery (P4-7), shared by the tests that need a Phase 4 output to work with: the REAL inputs in a temporary copy of config/ and reports/ cut back to what they
held before the look, with the 23 block-5 record files destroyed and seeded synthetic labels behind the gate. Nothing here reads a block-5 outcome or touches a real log or output."""
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_phase4 as p4  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_registry as reg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
OUTPUTS = ("m4-phase4-holdout-results-*", "m4-phase4-holdout-predictions-*", "m4-phase4-descriptive-*")  # what the look writes (not the authorization or the audit)
HOLDOUT_FOLD = "holdout_test_block_5"


def real_log_counts():
    return len(reg.read(reg.EXPERIMENT_LOG)), len(reg.read(reg.HOLDOUT_LOG))


def rehearsal_root(owner):
    """A temporary copy of config/ and reports/ as they stood before the look, with the 23 block-5 record files destroyed."""
    directory = tempfile.TemporaryDirectory()
    owner.addClassCleanup(directory.cleanup)
    root = Path(directory.name)
    for name in ("config", "reports"):
        shutil.copytree(ROOT / name, root / name)
    for pattern in OUTPUTS:
        for path in (root / "reports").glob(pattern):
            path.unlink()
    for name, keep in (("m4-experiment-log.jsonl", p4.EXPERIMENTS_BEFORE), ("m4-holdout-access-log.jsonl", 1)):
        path = root / "reports" / name
        lines = [line for line in path.read_bytes().split(b"\n") if line.strip()]
        path.write_bytes(b"\n".join(lines[:keep]) + b"\n")  # a log is a chain: its first records are a valid log
    inputs = d.load_inputs(PROTOCOL)  # the real inputs, with the holdout sealed: this reads no block-5 record
    held = {e["event_id"] for e in inputs["events"] if d.is_sealed(e)}
    destroyed = []
    for entry in inputs["spec"]["events"]:
        if entry["event_id"] in held:
            target = root / entry["recorded_result"]["recorded_in"]
            target.write_text("destroyed", encoding="utf-8")
            destroyed.append(target)
    return root, destroyed


def rehearse(owner, choose):
    """Runs p4.run on the real inputs in a temporary root with the labels `choose(position, n)` behind the gate. Returns (summary, root, harness, destroyed files)."""
    root, destroyed = rehearsal_root(owner)
    harness = h.Harness.from_repository(root)
    sealed = sorted((e for e in harness.events if d.is_sealed(e)), key=fp.event_order)
    position = {e["event_id"]: i for i, e in enumerate(sealed)}
    harness.gate._loader = lambda event_id: choose(position[event_id], len(sealed))  # the real loader, which would read the record files, is never called
    with mock.patch.object(h, "ALLOW_HOLDOUT_LOOK", True), mock.patch.object(h, "ALLOW_REAL_EVALUATION", True):
        summary = p4.run(harness, "2026-10-07", root=root, commit_state=("f" * 40, True))
    return summary, root, harness, destroyed
