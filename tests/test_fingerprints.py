import contextlib
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_support as S  # noqa: E402
from nre import cli  # noqa: E402
from nre import event_acquire as ea  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre.core import DataError, canonical, digest, iso, timestamp  # noqa: E402
from nre.dataset import build  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads(ea.DEFAULT_SPEC.read_text(encoding="utf-8"))
REAL = fp.load_inputs()
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
W, U, R = fp.WITHHELD, fp.UNRELIABLE, fp.REPORTED


def copy_inputs(directory):
    for name in ("config", "reports"):
        shutil.copytree(ROOT / name, Path(directory) / name)
    return Path(directory)


def load_copy(root):
    return fp.load_inputs(root / "config" / "m1-events.json", root / "config" / "sector-map.json", root / "config" / "fingerprint-policy.json", root)


def edit_json(path, change):
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


class PolicyTests(unittest.TestCase):
    def test_repository_policy_holds_the_defaults_the_owner_confirmed(self):
        # analogues.min_members was amended from 5 to 10 on 2026-09-27 by explicit owner instruction
        # (reports/m2-policy-amendment-2026-09-27.json); every other value is as originally confirmed.
        expected = {"count_unit": "event", "wilson_confidence": 0.95, "proportion": {"report_from_n": 5, "unreliable_below_n": 10},
                    "mean_median": {"report_from_n": 10, "unreliable_below_n": 20},
                    "quantiles": {"levels": [0.1, 0.25, 0.5, 0.75, 0.9], "report_from_n": 20}, "pooling": {"prior_strength": 10},
                    "analogues": {"min_members": 10, "max_distance": 1.0,
                                  "distance": {"timing_mismatch": 1.0, "sector_mismatch": {"same_major_group": 0.0, "same_division": 0.5, "other": 1.0}}}}
        for key, value in expected.items():
            self.assertEqual(S.POLICY[key], value, key)

    def test_invalid_policies_are_rejected(self):
        for path, value in (("count_unit", "day"), ("wilson_confidence", 1.5), ("proportion.report_from_n", 11), ("proportion.report_from_n", True),
                            ("mean_median.unreliable_below_n", 0), ("quantiles.levels", [0.5, 0.25]), ("quantiles.levels", [0.0, 0.5]),
                            ("quantiles.report_from_n", 5), ("pooling.prior_strength", -1), ("analogues.min_members", 0),
                            ("analogues.max_distance", -0.5), ("analogues.distance.sector_mismatch.same_division", 2.0)):
            with self.subTest(path=path, value=value), self.assertRaises(DataError):
                S.policy_with(**{path: value})

    def test_unknown_or_missing_keys_are_rejected(self):
        extra = copy.deepcopy(S.POLICY)
        extra["surprise"] = 1
        missing = copy.deepcopy(S.POLICY)
        del missing["pooling"]
        for policy in (extra, missing):
            with self.assertRaises(DataError):
                fp.validate_policy(policy)


class SectorTests(unittest.TestCase):
    def test_division_boundaries(self):
        cases = {"0100": "A", "0999": "A", "1000": "B", "1499": "B", "1500": "C", "1799": "C", "2000": "D", "3999": "D", "4000": "E",
                 "4999": "E", "5000": "F", "5199": "F", "5200": "G", "5999": "G", "6000": "H", "6799": "H", "7000": "I", "8999": "I",
                 "9100": "J", "9999": "J"}
        for sic, division in cases.items():
            self.assertEqual(fp.sic_parts(sic), (division, sic[:2]), sic)

    def test_codes_outside_every_division_are_rejected(self):
        for bad in ("1800", "1999", "9000", "9099", "abc", "123", "12345", 2834, None):
            with self.subTest(bad=bad), self.assertRaises(DataError):
                fp.sic_parts(bad)

    def test_repository_sector_map_covers_exactly_the_accepted_issuers(self):
        accepted = {e["security"]["cik"] for e in SPEC["events"] if "recorded_result" in e}
        self.assertEqual(set(REAL["sectors"]), accepted)
        for cik, sector in REAL["sectors"].items():
            self.assertTrue(sector["sic_description"], cik)
            self.assertEqual(fp.sic_parts(sector["sic"]), (sector["sic_division"], sector["sic_major_group"]), cik)

    def test_sector_map_with_a_wrong_source_url_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sector-map.json"
            data = json.loads((ROOT / "config" / "sector-map.json").read_text(encoding="utf-8"))
            next(iter(data["issuers"].values()))["source_url"] = "https://example.com/other.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(DataError):
                fp.load_sector_map(path)


class EventTests(unittest.TestCase):
    def test_label_names_and_availability_agree_with_the_dataset_engine(self):
        entry = next(e for e in SPEC["events"] if "recorded_result" in e)
        window = ea.event_window(entry, S.CAL)
        bars = {s: {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 10} for s in window["required_sessions"]}
        bars[window["reaction_session"]] = {"open": 106.0, "high": 110.0, "low": 100.0, "close": 108.0, "volume": 10}
        outcome = build(ea.build_bundle(entry, SPEC["provider"], window, bars, [], NOW, S.CAL))[0][0]
        self.assertEqual(outcome["state"], "MAPPED")
        self.assertEqual(set(outcome["labels"]), set(fp.LABELS))
        for name, label in outcome["labels"].items():
            self.assertIsNone(label["reason"], name)  # a positive gap, so every label exists
            self.assertEqual(label["label_available_at"], iso(fp.label_available_at(name, window["reaction_session"], S.CAL)), name)

    def test_label_kinds_partition_the_sixteen_labels(self):
        self.assertEqual(len(fp.LABELS), 16)
        self.assertEqual(len(fp.RETURN_LABELS), 8)
        self.assertEqual(len(fp.BOOLEAN_LABELS), 8)
        self.assertEqual(set(fp.RETURN_LABELS) & set(fp.BOOLEAN_LABELS), set())

    def test_availability_grows_with_the_horizon(self):
        session = S.SESSIONS[3]
        times = [fp.label_available_at(name, session, S.CAL) for name in ("day1_close_return", "session_2_close_return",
                                                                         "session_5_close_return", "session_10_close_return",
                                                                         "session_20_close_return")]
        self.assertEqual(times, sorted(times))
        self.assertEqual(len(set(times)), 5)
        self.assertEqual(fp.label_available_at("gap_ge_3pct", session, S.CAL), times[0])
        self.assertEqual(times[0], S.CAL.bounds(session)[1] + timedelta(minutes=1))

    def test_an_early_close_moves_the_availability(self):
        early = next(iter(S.CAL.spec["early_closes"]))
        close = S.CAL.bounds(early)[1]
        self.assertEqual(fp.label_available_at("day1_close_return", early, S.CAL), close + timedelta(minutes=1))
        self.assertEqual(close.astimezone(S.CAL.zone).strftime("%H:%M"), S.CAL.spec["early_closes"][early])

    def test_malformed_events_are_rejected(self):
        good = S.event(0)

        def labels(**changes):
            base = copy.deepcopy(good["labels"])
            base.update(changes)
            return base

        def make(**changes):
            args = dict(calendar=S.CAL, event_id="x", cluster_id="c", ticker="T", cik="0000000001", release_timing="after_hours",
                        published_at="2026-02-02T21:30:00Z", cutoff="2026-02-02T21:35:00Z", reaction_session=S.SESSIONS[1],
                        sector=fp.sector_from_sic("7372"), labels=good["labels"])
            args.update(changes)
            return fp.make_event(**args)

        make()  # the baseline is valid
        cases = {"regular timing": dict(release_timing="regular"), "cutoff before publication": dict(cutoff="2026-02-02T21:00:00Z"),
                 "null without reason": dict(labels=labels(gap_ge_3pct={"value": None, "reason": None})),
                 "value with reason": dict(labels=labels(gap_ge_3pct={"value": True, "reason": "X"})),
                 "boolean label holding a number": dict(labels=labels(gap_ge_3pct={"value": 1.0, "reason": None})),
                 "return label holding a boolean": dict(labels=labels(day1_close_return={"value": True, "reason": None})),
                 "nonfinite return": dict(labels=labels(day1_close_return={"value": float("nan"), "reason": None})),
                 "missing label": dict(labels={k: v for k, v in good["labels"].items() if k != "gap_ge_5pct"}),
                 "unknown label": dict(labels=labels(extra={"value": 1.0, "reason": None})),
                 "empty identifier": dict(event_id="")}
        for name, changes in cases.items():
            with self.subTest(name), self.assertRaises(DataError):
                make(**changes)

    def test_records_without_label_reasons_are_read_with_the_documented_reasons(self):
        for name, label in (("slsn-2026-03-31", None), ("cxt-2026-02-11", "session_20_close_return")):
            entry = next(e for e in SPEC["events"] if e["event_id"] == name)
            record = json.loads((ROOT / entry["recorded_result"]["recorded_in"]).read_text(encoding="utf-8"))
            self.assertNotIn("label_reasons", record, name)
            event = next(e for e in REAL["events"] if e["event_id"] == name)
            if label:
                self.assertEqual(event["labels"][label], {"value": None, "reason": "CORPORATE_ACTION_IN_WINDOW"})
            for label_name, value in event["labels"].items():
                self.assertEqual(value["value"] is None, value["reason"] is not None, label_name)


class StatisticsTests(unittest.TestCase):
    def test_wilson_interval_known_values(self):
        low, high = fp.wilson(5, 10, 0.95)
        self.assertAlmostEqual(low, 0.2366, places=4)
        self.assertAlmostEqual(high, 0.7634, places=4)
        low, high = fp.wilson(0, 5, 0.95)
        self.assertAlmostEqual(low, 0.0, places=6)
        self.assertAlmostEqual(high, 0.4345, places=4)
        low, high = fp.wilson(5, 5, 0.95)
        self.assertAlmostEqual(low, 0.5655, places=4)
        self.assertAlmostEqual(high, 1.0, places=6)

    def test_wilson_interval_widens_with_confidence_and_narrows_with_n(self):
        self.assertLess(fp.wilson(5, 10, 0.90)[1] - fp.wilson(5, 10, 0.90)[0], fp.wilson(5, 10, 0.99)[1] - fp.wilson(5, 10, 0.99)[0])
        self.assertGreater(fp.wilson(5, 10, 0.95)[1] - fp.wilson(5, 10, 0.95)[0], fp.wilson(50, 100, 0.95)[1] - fp.wilson(50, 100, 0.95)[0])

    def test_quantile_uses_linear_interpolation(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        for p, expected in ((0.0, 1.0), (0.1, 1.4), (0.25, 2.0), (0.5, 3.0), (0.75, 4.0), (0.9, 4.6), (1.0, 5.0)):
            self.assertAlmostEqual(fp.quantile(data, p), expected, places=12, msg=str(p))
        self.assertAlmostEqual(fp.quantile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5, places=12)
        self.assertEqual(fp.quantile([7.0], 0.9), 7.0)

    def test_band_states_at_every_boundary(self):
        rules = {"proportion": S.POLICY["proportion"], "mean": S.POLICY["mean_median"], "quantiles": {"report_from_n": 20}}
        expected = {"proportion": {4: W, 5: U, 9: U, 10: R, 19: R, 20: R}, "mean": {4: W, 5: W, 9: W, 10: U, 19: U, 20: R},
                    "quantiles": {4: W, 5: W, 9: W, 10: W, 19: W, 20: R}}
        for name, rule in rules.items():
            for n, state in expected[name].items():
                self.assertEqual(fp.band(n, rule)[0], state, "%s n=%d" % (name, n))

    def test_cells_apply_every_threshold_to_synthetic_events(self):
        expected = {4: (W, W, W), 5: (U, W, W), 9: (U, W, W), 10: (R, U, W), 19: (R, U, W), 20: (R, R, R)}
        for count, (proportion, mean, quantiles) in expected.items():
            cell = fp.describe_cell([S.event(i) for i in range(count)], S.LATE, S.POLICY)
            flag, ret = cell["labels"]["gap_ge_3pct"], cell["labels"]["day1_close_return"]
            self.assertEqual((flag["proportion"]["state"], ret["mean"]["state"], ret["quantiles"]["state"]), (proportion, mean, quantiles), count)
            self.assertEqual(ret["median"]["state"], ret["mean"]["state"])
            self.assertEqual((flag["n"], ret["n"], ret["n_absent"]), (count, count, 0))

    def test_withheld_statistics_carry_no_estimate(self):
        cell = fp.describe_cell([S.event(i) for i in range(4)], S.LATE, S.POLICY)
        for name, block in cell["labels"].items():
            for stat in fp.statistic_blocks(block):
                self.assertEqual(stat["state"], W)
                self.assertEqual(set(stat), {"state", "reason"}, name)

    def test_estimates_match_hand_computed_values(self):
        events = [S.event(i, values={"day1_close_return": v, "gap_ge_3pct": v > 0.03}) for i, v in enumerate([-0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.1])]
        cell = fp.describe_cell(events, S.LATE, S.POLICY)
        returns, flags = cell["labels"]["day1_close_return"], cell["labels"]["gap_ge_3pct"]
        self.assertEqual(returns["n"], 10)
        self.assertAlmostEqual(returns["mean"]["value"], 0.037, places=10)
        self.assertAlmostEqual(returns["median"]["value"], 0.035, places=10)
        self.assertEqual((flags["k"], flags["n"]), (5, 10))
        self.assertAlmostEqual(flags["proportion"]["value"], 0.5, places=10)
        self.assertAlmostEqual(flags["proportion"]["wilson_low"], 0.2366, places=4)

    def test_absent_labels_are_counted_apart_with_their_reasons(self):
        events = [S.event(i, absent=("positive_gap_filled",) if i < 3 else ()) for i in range(12)]
        block = fp.describe_cell(events, S.LATE, S.POLICY)["labels"]["positive_gap_filled"]
        self.assertEqual((block["n"], block["n_absent"], block["absent_reasons"]), (9, 3, {"TEST_ABSENT": 3}))
        self.assertEqual(block["gate_n"], 9)

    def test_counting_reaction_sessions_is_stricter_than_counting_events(self):
        events = [S.event(i, session=S.SESSIONS[0]) for i in range(5)]
        by_event = fp.describe_cell(events, S.LATE, S.POLICY)["labels"]["gap_ge_3pct"]
        by_session = fp.describe_cell(events, S.LATE, S.policy_with(count_unit="reaction_session"))["labels"]["gap_ge_3pct"]
        self.assertEqual((by_event["gate_n"], by_event["proportion"]["state"]), (5, U))
        self.assertEqual((by_session["gate_n"], by_session["n"], by_session["proportion"]["state"]), (1, 5, W))


class CellTests(unittest.TestCase):
    def cells(self, events, key_events=None, policy=None, cutoff=S.LATE):
        keys = [fp.cell_keys(e) for e in (key_events or events[:1])]
        return fp.compute_cells(events, cutoff, policy or S.POLICY, keys)

    def test_events_in_one_cluster_count_once_and_the_earliest_is_kept(self):
        events = [S.event(i) for i in range(4)] + [S.event(4, cluster="c0")]
        self.assertEqual(sorted(e["event_id"] for e in fp.dedupe_clusters(events)), ["e0", "e1", "e2", "e3"])
        self.assertEqual(self.cells(events)[("all", fp.CATEGORY)]["counts"]["events"], 4)

    def test_maturity_is_decided_label_by_label(self):
        event = S.event(0)
        day1 = fp.label_available_at("day1_close_return", event["reaction_session"], S.CAL)
        session2 = fp.label_available_at("session_2_close_return", event["reaction_session"], S.CAL)
        blocks = lambda when: fp.describe_cell([event], when, S.POLICY)  # noqa: E731
        self.assertEqual(blocks(day1 - timedelta(minutes=1))["counts"]["events"], 0)
        at_day1 = blocks(day1)
        self.assertEqual((at_day1["counts"]["events"], at_day1["labels"]["day1_close_return"]["n"],
                          at_day1["labels"]["session_2_close_return"]["n"]), (1, 1, 0))
        self.assertEqual(blocks(session2)["labels"]["session_2_close_return"]["n"], 1)
        self.assertEqual(blocks(session2 - timedelta(minutes=1))["labels"]["session_2_close_return"]["n"], 0)

    def test_partial_pooling_moves_a_cell_toward_its_parent_recursively(self):
        events = ([S.event(i, sic="2834", values={"gap_ge_3pct": True}) for i in range(6)]
                  + [S.event(i, sic="3841", values={"gap_ge_3pct": False}) for i in range(6, 12)]
                  + [S.event(i, sic="7372", values={"gap_ge_3pct": False}) for i in range(12, 16)])
        cells = self.cells(events)
        root = cells[("all", fp.CATEGORY)]["labels"]["gap_ge_3pct"]
        division = cells[("sic_division", "D")]["labels"]["gap_ge_3pct"]
        group = cells[("sic_major_group", "28")]["labels"]["gap_ge_3pct"]
        self.assertNotIn("pooled", root)
        self.assertAlmostEqual(root["proportion"]["value"], 6 / 16, places=9)
        self.assertAlmostEqual(division["proportion"]["value"], 0.5, places=9)
        self.assertAlmostEqual(division["pooled"]["value"], (12 * 0.5 + 10 * 6 / 16) / 22, places=9)
        self.assertEqual(division["pooled"]["toward"], {"level": "all", "key": fp.CATEGORY})
        self.assertAlmostEqual(group["proportion"]["value"], 1.0, places=9)
        self.assertAlmostEqual(group["pooled"]["value"], (6 * 1.0 + 10 * division["pooled"]["value"]) / 16, places=9)
        self.assertEqual(group["pooled"]["toward"], {"level": "sic_division", "key": "D"})
        self.assertLess(group["pooled"]["value"], group["proportion"]["value"])
        self.assertGreater(group["pooled"]["value"], division["pooled"]["value"])
        self.assertAlmostEqual(group["pooled"]["weight_on_cell"], 6 / 16, places=9)

    def test_pooling_never_inflates_the_cells_own_count(self):
        events = [S.event(i, sic="2834") for i in range(6)] + [S.event(i, sic="7372") for i in range(6, 12)]
        cells = self.cells(events)
        for cell in cells.values():
            for name, block in cell["labels"].items():
                if "pooled" in block or "pooled_mean" in block:
                    pooled = block.get("pooled") or block["pooled_mean"]
                    self.assertEqual(block["n"], sum(1 for e in events if fp.cell_keys(e)[cell["level"]] == cell["key"]
                                                     and e["labels"][name]["value"] is not None), name)
                    self.assertEqual(pooled["prior_strength"], 10)

    def test_a_pooled_mean_lies_between_the_cells_mean_and_its_parents(self):
        events = ([S.event(i, sic="2834", values={"day1_close_return": 0.10}) for i in range(10)]
                  + [S.event(i, sic="3841", values={"day1_close_return": 0.0}) for i in range(10, 25)])
        cells = self.cells(events)
        block = cells[("sic_major_group", "28")]["labels"]["day1_close_return"]
        parent = cells[("sic_division", "D")]["labels"]["day1_close_return"]
        self.assertEqual((block["mean"]["state"], parent["mean"]["state"]), (U, R))
        self.assertAlmostEqual(block["pooled_mean"]["value"], (10 * 0.10 + 10 * parent["pooled_mean"]["value"]) / 20, places=9)
        self.assertLess(block["pooled_mean"]["value"], block["mean"]["value"])

    def test_no_pooling_when_the_prior_strength_is_zero(self):
        events = [S.event(i, sic="2834") for i in range(6)] + [S.event(i, sic="7372") for i in range(6, 12)]
        for cell in self.cells(events, policy=S.policy_with(**{"pooling.prior_strength": 0})).values():
            for block in cell["labels"].values():
                self.assertNotIn("pooled", block)
                self.assertNotIn("pooled_mean", block)

    def test_a_withheld_cell_keeps_its_counts_and_names_its_parent(self):
        events = [S.event(i) for i in range(8)]
        inputs = S.inputs_for(events)
        target = fp.new_target({"release_timing": "after_hours", "sic": "0100", "as_of": "2026-06-01T00:00:00Z"}, {})
        chain = fp.target_fingerprint(inputs, target)["chain"]
        self.assertEqual([c["level"] for c in chain], ["all", "timing", "sic_division", "sic_major_group"])
        division = chain[2]
        self.assertTrue(division["all_statistics_withheld"])
        self.assertTrue(division["falls_back_to_parent"])
        self.assertEqual(division["parent"], {"level": "all", "key": fp.CATEGORY})
        self.assertEqual(division["counts"], {"events": 0, "issuers": 0, "reaction_sessions": 0})
        self.assertEqual(set(division["n_by_label"].values()), {0})
        self.assertIn("labels", chain[0])

    def test_a_target_never_sees_its_own_cluster_or_unmatured_events(self):
        events = [S.event(i) for i in range(10)]
        target = fp.historical_target(events[5])
        chain = fp.target_fingerprint(S.inputs_for(events), target)["chain"]
        self.assertEqual(chain[0]["counts"]["events"], 5)  # e0..e4 have matured by e5's cutoff; e5 itself and e6..e9 do not count
        self.assertEqual(chain[-1]["level"], "issuer")
        self.assertEqual(chain[-1]["counts"]["events"], 0)
        twin = S.event(10, session=S.SESSIONS[2], cluster="c5")  # matured long ago, but it belongs to the target's own cluster
        chain = fp.target_fingerprint(S.inputs_for(events + [twin]), target)["chain"]
        self.assertEqual(chain[0]["counts"]["events"], 5)

    def test_a_new_event_sees_every_matured_event(self):
        events = [S.event(i) for i in range(10)]
        target = fp.new_target({"release_timing": "after_hours", "sic": "7372", "as_of": iso(S.LATE)}, {})
        self.assertEqual(fp.target_fingerprint(S.inputs_for(events), target)["chain"][0]["counts"]["events"], 10)


class RealDataTests(unittest.TestCase):
    def test_all_accepted_events_load_and_reproduce_their_pinned_digests(self):
        pins = {e["event_id"]: e["recorded_result"]["labels_sha256"] for e in SPEC["events"] if "recorded_result" in e}
        self.assertEqual(len(pins), 23)
        self.assertEqual({e["event_id"]: e["labels_sha256"] for e in REAL["events"]}, pins)

    def test_default_calendar_is_2026_only_but_a_spec_can_extend_it(self):
        # config/m2-step2-events.json is real, already on disk, and 2025-dated throughout: load_inputs()
        # with no --calendar must fail exactly as it always has (2026-only default, via
        # nre.event_acquire.validate_spec's own calendar.classify() call chain), and passing the
        # real merged 2025+2026 calendar must load all 45 of its accepted events.
        m2_step2 = ROOT / "config" / "m2-step2-events.json"
        with self.assertRaises(DataError):
            fp.load_inputs(m2_step2, calendar_path=None)
        inputs = fp.load_inputs(m2_step2, calendar_path=ROOT / "config" / "m2-step2-merged-calendar.json")
        self.assertEqual(len(inputs["events"]), 45)

    def test_a_changed_label_value_fails_the_digest_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_inputs(tmp)
            edit_json(root / "reports" / "m1-achv-complete-event-2026-09-26.json", lambda d: d["computed_labels"].update(day1_close_return=0.5))
            with self.assertRaisesRegex(DataError, "pinned digest"):
                load_copy(root)

    def test_a_record_that_disagrees_with_the_spec_is_refused(self):
        changes = {"identity": lambda d: d.update(cik="0000000001"),
                   "timing": lambda d: d["event_context"].update(release_timing="after_hours"),
                   "reaction session": lambda d: d["event_context"].update(reaction_session="2026-03-25"),
                   "missing label": lambda d: d["computed_labels"].pop("gap_ge_5pct")}
        for name, change in changes.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = copy_inputs(tmp)
                edit_json(root / "reports" / "m1-achv-complete-event-2026-09-26.json", change)
                with self.assertRaises(DataError):
                    load_copy(root)

    def test_an_issuer_missing_from_the_sector_map_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_inputs(tmp)
            edit_json(root / "config" / "sector-map.json", lambda d: d["issuers"].pop("0000949858"))
            with self.assertRaisesRegex(DataError, "no SIC entry"):
                load_copy(root)

    def test_suppression_matches_the_hand_computed_table_in_the_proposal(self):
        cells = {(c["level"], c["key"]): c for c in fp.fingerprint_table(REAL)["cells"]}
        sizes = {("all", fp.CATEGORY): 23, ("timing", "after_hours"): 16, ("timing", "premarket"): 7, ("sic_division", "D"): 10,
                 ("sic_division", "I"): 8, ("sic_major_group", "28"): 6, ("sic_major_group", "73"): 6}
        for key, size in sizes.items():
            self.assertEqual(cells[key]["counts"]["events"], size, key)
        # (proportion of a gap flag, day-1 mean, day-1 quantiles, session-20 mean, session-20 quantiles)
        expected = {("all", fp.CATEGORY): (R, R, R, R, R), ("timing", "after_hours"): (R, U, W, U, W),
                    ("timing", "premarket"): (U, W, W, W, W), ("sic_division", "D"): (R, U, W, W, W),
                    ("sic_division", "I"): (U, W, W, W, W), ("sic_major_group", "28"): (U, W, W, W, W),
                    ("sic_major_group", "73"): (U, W, W, W, W)}
        for key, states in expected.items():
            labels = cells[key]["labels"]
            got = (labels["gap_ge_3pct"]["proportion"]["state"], labels["day1_close_return"]["mean"]["state"],
                   labels["day1_close_return"]["quantiles"]["state"], labels["session_20_close_return"]["mean"]["state"],
                   labels["session_20_close_return"]["quantiles"]["state"])
            self.assertEqual(got, states, key)
        self.assertEqual(cells[("all", fp.CATEGORY)]["labels"]["session_20_close_return"]["n"], 22)
        self.assertEqual(cells[("sic_division", "D")]["labels"]["session_20_close_return"]["n"], 9)
        self.assertEqual(cells[("all", fp.CATEGORY)]["labels"]["positive_gap_filled"]["n"], 12)
        rest = [c for key, c in cells.items() if key not in sizes]
        self.assertEqual(len(rest), 38)
        for cell in rest:
            self.assertTrue(cell["all_statistics_withheld"], (cell["level"], cell["key"]))
            self.assertLessEqual(cell["counts"]["events"], 2)

    def test_every_issuer_history_is_withheld_because_each_issuer_has_one_event(self):
        issuers = [c for c in fp.fingerprint_table(REAL)["cells"] if c["level"] == "issuer"]
        self.assertEqual(len(issuers), 23)
        for cell in issuers:
            self.assertEqual(cell["counts"]["events"], 1)
            self.assertTrue(cell["all_statistics_withheld"])

    def test_an_earlier_as_of_sees_fewer_events(self):
        table = fp.fingerprint_table(REAL, timestamp("2026-02-20T00:00:00Z"))
        counts = table["cells"][0]["counts"]["events"]
        self.assertTrue(0 < counts < 23, counts)
        self.assertEqual(table["as_of"], "2026-02-20T00:00:00Z")

    def test_milestone_1_audit_inputs_are_unchanged_since_the_declaration(self):
        declared = json.loads((ROOT / "reports/m1-acceptance-declaration-2026-09-26.json").read_text(encoding="utf-8"))["state_declared"]["audit_input_hashes"]
        load = lambda name: json.loads((ROOT / name).read_text(encoding="utf-8"))  # noqa: E731
        ledger = load("reports/m1-reviewed-candidate-ledger.json")
        membership = sorted([{k: c.get(k) for k in ("candidate_id", "source_sha256")} for c in ledger["candidates"]],
                            key=lambda c: c["candidate_id"])
        recomputed = {"protocol_sha256": digest(canonical(load("config/pilot.json"))), "ledger_sha256": digest(canonical(ledger)),
                      "review_sha256": digest(canonical(load("reports/m1-acceptance-review.json"))),
                      "membership_sha256": digest(canonical(membership))}
        for key, value in recomputed.items():
            self.assertEqual(declared[key], value, key)


class ReportTests(unittest.TestCase):
    def test_dump_report_round_trips_and_keeps_small_objects_on_one_line(self):
        value = {"a": {"b": {"c": {"d": {"e": 1, "f": [1, 2]}}}}, "flat": {"x": 1, "y": None}, "list": [{"k": 1}, {"k": 2}], "empty": {}, "text": "é"}
        text = fp.dump_report(value)
        self.assertEqual(json.loads(text), value)
        self.assertIn('"flat": {"x": 1, "y": null}', text)
        self.assertIn('"d": {"e": 1, "f": [1, 2]}', text)
        self.assertGreater(text.count("\n"), 5)

    def test_dump_report_refuses_nonfinite_numbers(self):
        with self.assertRaises(ValueError):
            fp.dump_report({"x": float("nan")})

    def test_reports_are_byte_identical_across_runs(self):
        first = fp.dump_report(fp.fingerprint_table(REAL))
        second = fp.dump_report(fp.fingerprint_table(fp.load_inputs()))
        self.assertEqual(first, second)

    def test_the_committed_fingerprint_table_is_what_the_code_produces(self):
        committed = json.loads((ROOT / "reports/m2-fingerprints-2026-09-26.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, json.loads(fp.dump_report(fp.fingerprint_table(REAL))))

    def test_every_output_states_its_policy_inputs_and_scope(self):
        table = fp.fingerprint_table(REAL)
        self.assertEqual(table["policy"]["sha256"], REAL["policy_sha256"])
        self.assertEqual(len(table["inputs"]["event_labels_sha256"]), 23)
        self.assertIn("not market base rates", table["scope_note"])
        self.assertTrue(any("SIC" in limit for limit in table["limits"]))

    def test_the_command_writes_a_report_and_a_summary(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            path = Path(tmp) / "table.json"
            self.assertEqual(cli.main(["fingerprints", "--output", str(path)]), 0)
            summary = json.loads(out.getvalue())
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((summary["state"], summary["kind"]), ("WRITTEN", "reaction_fingerprint_table"))
        self.assertEqual(summary["report_sha256"], digest(canonical(written)))

    def test_the_command_answers_for_a_historical_event_and_a_new_event(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            historical, new = Path(tmp) / "h.json", Path(tmp) / "n.json"
            self.assertEqual(cli.main(["fingerprints", "--event", "rekr-2026-03-31", "--output", str(historical)]), 0)
            self.assertEqual(cli.main(["fingerprints", "--descriptor", str(ROOT / "tests/fixtures/m2_new_event_example.json"), "--output", str(new)]), 0)
            self.assertEqual(json.loads(historical.read_text(encoding="utf-8"))["target"]["kind"], "historical")
            chain = json.loads(new.read_text(encoding="utf-8"))["chain"]
        self.assertEqual([c["level"] for c in chain], ["all", "timing", "sic_division", "sic_major_group"])
        self.assertEqual(chain[0]["counts"]["events"], 23)

    def test_bad_requests_fail_with_a_structured_error(self):
        for argv in (["fingerprints", "--event", "nope"], ["fingerprints", "--event", "rekr-2026-03-31", "--descriptor", "x.json"],
                     ["analogues"], ["analogues", "--all-targets", "--event", "rekr-2026-03-31"]):
            with self.subTest(argv), tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cli.main(argv + ["--output", str(Path(tmp) / "x.json")]), 2)
                self.assertEqual(json.loads(err.getvalue())["state"], "INVALID_INPUT")

    def test_no_network_is_touched(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                patch("socket.socket.connect", side_effect=AssertionError("network access")):
            self.assertEqual(cli.main(["fingerprints", "--output", str(Path(tmp) / "t.json")]), 0)
            self.assertEqual(cli.main(["analogues", "--all-targets", "--output", str(Path(tmp) / "p.json")]), 0)


if __name__ == "__main__":
    unittest.main()
