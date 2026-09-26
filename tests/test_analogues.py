import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_support as S  # noqa: E402
from nre import analogues as an  # noqa: E402
from nre import cli  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre.core import DataError, iso, timestamp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REAL = fp.load_inputs()
NEW = fp.new_target({"release_timing": "after_hours", "sic": "7372", "as_of": iso(S.LATE)}, {})
LABELS_EXAMPLE = ["day1_close_return", "session_5_close_return", "session_20_close_return", "positive_gap_filled"]


def scenario():
    """Against an after-hours software target: three events at distance 0, two at 0.5, three at 1.0 and one beyond the cap of 1.0."""
    return ([S.event(i, sic="7372") for i in range(3)]
            + [S.event(i, sic="8742") for i in range(3, 5)]
            + [S.event(5, sic="2834"), S.event(6, sic="2836"), S.event(7, sic="7372", timing="premarket")]
            + [S.event(8, sic="2834", timing="premarket")])


def target_at(when, **extra):
    return fp.new_target({"release_timing": "after_hours", "sic": "7372", "as_of": iso(when), **extra}, {})


def retrieve(events=None, target=NEW, label="day1_close_return", policy=None):
    return an.retrieve(target, scenario() if events is None else events, label, policy or S.POLICY)


def reasons(result):
    return {row["event_id"]: row["reason"] for row in result["excluded"]}


class DistanceTests(unittest.TestCase):
    def test_distance_combines_timing_and_sector_mismatch(self):
        cases = [("after_hours", "7372", 0.0), ("after_hours", "7389", 0.0), ("after_hours", "8742", 0.5), ("after_hours", "2834", 1.0),
                 ("premarket", "7372", 1.0), ("premarket", "8742", 1.5), ("premarket", "2834", 2.0)]
        for timing, sic, expected in cases:
            self.assertEqual(an.distance(NEW, S.event(0, timing=timing, sic=sic), S.POLICY), expected, (timing, sic))

    def test_distance_follows_the_policy_weights(self):
        policy = S.policy_with(**{"analogues.distance.timing_mismatch": 0.25, "analogues.distance.sector_mismatch.same_division": 0.25})
        self.assertEqual(an.distance(NEW, S.event(0, timing="premarket", sic="8742"), policy), 0.5)

    def test_distance_ignores_every_label_value(self):
        for event, junk in zip(scenario(), S.poisoned(scenario())):
            self.assertEqual(an.distance(NEW, event, S.POLICY), an.distance(NEW, junk, S.POLICY))

    def test_effective_sample_size_is_kishs(self):
        for weights, expected in (([1, 1, 1, 1], 4.0), ([1, 0, 0, 0], 1.0), ([2, 1, 1], 16 / 6), ([3], 1.0), ([], 0.0), ([0, 0], 0.0)):
            self.assertAlmostEqual(an.effective_sample_size(weights), expected, places=12, msg=str(weights))
        self.assertLess(an.effective_sample_size([5, 1, 1, 1]), 4)


class RetrievalTests(unittest.TestCase):
    def test_expansion_stops_at_the_minimum_and_ties_enter_together(self):
        result = retrieve()
        self.assertEqual((result["state"], result["distance_reached"]), (an.FOUND, 0.5))
        self.assertEqual([m["event_id"] for m in result["members"]], ["e0", "e1", "e2", "e3", "e4"])
        self.assertEqual([m["distance"] for m in result["members"]], [0.0, 0.0, 0.0, 0.5, 0.5])
        self.assertEqual(reasons(result), {"e5": "BEYOND_EXPANSION", "e6": "BEYOND_EXPANSION", "e7": "BEYOND_EXPANSION", "e8": "BEYOND_MAX_DISTANCE"})
        self.assertEqual(result["pool"], {"eligible": 9, "excluded_by_reason": {"BEYOND_EXPANSION": 3, "BEYOND_MAX_DISTANCE": 1}})

    def test_a_tie_is_taken_whole_even_when_one_member_would_do(self):
        result = retrieve(policy=S.policy_with(**{"analogues.min_members": 4}))
        self.assertEqual((result["distance_reached"], result["counts"]["members"]), (0.5, 5))

    def test_a_larger_minimum_expands_further_but_never_past_the_maximum(self):
        result = retrieve(policy=S.policy_with(**{"analogues.min_members": 8}))
        self.assertEqual((result["state"], result["distance_reached"], result["counts"]["members"]), (an.FOUND, 1.0, 8))
        self.assertEqual(reasons(result), {"e8": "BEYOND_MAX_DISTANCE"})

    def test_below_the_minimum_the_answer_abstains_but_lists_what_it_found(self):
        result = retrieve(policy=S.policy_with(**{"analogues.min_members": 9}))
        self.assertEqual(result["state"], an.INSUFFICIENT)
        self.assertIsNone(result["summary"])
        self.assertEqual((result["counts"]["members"], result["distance_reached"]), (8, 1.0))
        self.assertEqual(set(reasons(result).values()), {"BEYOND_MAX_DISTANCE"})
        self.assertEqual(len(result["members"]), 8)

    def test_a_tight_maximum_distance_limits_the_pool(self):
        result = retrieve(policy=S.policy_with(**{"analogues.max_distance": 0.0}))
        self.assertEqual((result["state"], result["counts"]["members"]), (an.INSUFFICIENT, 3))

    def test_no_event_in_range_reports_no_distance(self):
        result = retrieve(events=[S.event(0, sic="2834", timing="premarket")])
        self.assertEqual((result["state"], result["distance_reached"], result["counts"]["members"], result["members"]), (an.INSUFFICIENT, None, 0, []))

    def test_an_empty_history_abstains(self):
        result = retrieve(events=[])
        self.assertEqual((result["state"], result["pool"]["eligible"], result["summary"]), (an.INSUFFICIENT, 0, None))

    def test_the_summary_applies_the_reporting_thresholds_to_the_analogue_count(self):
        events = [S.event(i, sic="7372") for i in range(12)]
        flag = retrieve(events=events, label="gap_ge_3pct")["summary"]
        self.assertEqual((flag["n"], flag["k"], flag["proportion"]["state"], flag["proportion"]["value"]), (12, 6, fp.REPORTED, 0.5))
        returns = retrieve(events=events, label="day1_close_return")["summary"]
        self.assertEqual((returns["mean"]["state"], returns["quantiles"]["state"]), (fp.UNRELIABLE, fp.WITHHELD))
        self.assertAlmostEqual(returns["mean"]["value"], sum(0.01 * (i + 1) for i in range(12)) / 12, places=9)

    def test_a_reaction_session_count_unit_can_make_the_same_events_insufficient(self):
        events = [S.event(i, session=S.SESSIONS[0], sic="7372") for i in range(6)]
        self.assertEqual(retrieve(events=events)["state"], an.FOUND)
        self.assertEqual(retrieve(events=events, policy=S.policy_with(count_unit="reaction_session"))["state"], an.INSUFFICIENT)

    def test_members_expose_what_the_contract_requires(self):
        result = retrieve()
        required = {"event_id", "ticker", "cik", "cluster_id", "published_at", "reaction_session", "category", "source_id", "source_url",
                    "release_timing", "sic", "sic_division", "sic_major_group", "distance", "weight", "outcomes"}
        for member in result["members"]:
            self.assertLessEqual(required, set(member))
            self.assertEqual((member["weight"], member["category"]), (1.0, fp.CATEGORY))
        self.assertEqual(result["counts"]["effective_sample_size"], result["counts"]["members"])

    def test_an_unknown_label_is_refused(self):
        with self.assertRaises(DataError):
            retrieve(label="day2_return")

    def test_a_category_with_no_history_abstains_explicitly(self):
        result = retrieve(target=dict(NEW, category="guidance/raise"))
        self.assertEqual((result["state"], result["reason"], result["members"], result["summary"]), (an.INSUFFICIENT, "NO_EVENTS_OF_CATEGORY", [], None))


class LeakageTests(unittest.TestCase):
    def test_the_target_is_never_in_its_own_pool(self):
        events = scenario()
        for event in events:
            result = an.retrieve(fp.historical_target(event), events, "day1_close_return", S.POLICY)
            self.assertNotIn(event["event_id"], [m["event_id"] for m in result["members"]])
            self.assertEqual(reasons(result)[event["event_id"]], "SELF")

    def test_a_label_available_exactly_at_the_cutoff_is_used_and_one_minute_earlier_is_not(self):
        events = [S.event(i) for i in range(4)]
        edge = fp.label_available_at("day1_close_return", events[2]["reaction_session"], S.CAL)
        policy = S.policy_with(**{"analogues.min_members": 1})

        def ask(when):
            result = retrieve(events=events, target=target_at(when), policy=policy)
            return [m["event_id"] for m in result["members"]], reasons(result)

        self.assertEqual(ask(edge), (["e0", "e1", "e2"], {"e3": "LABEL_NOT_YET_MATURED"}))
        self.assertEqual(ask(edge - timedelta(minutes=1)), (["e0", "e1"], {"e2": "LABEL_NOT_YET_MATURED", "e3": "LABEL_NOT_YET_MATURED"}))
        self.assertEqual(ask(edge + timedelta(minutes=1))[0], ["e0", "e1", "e2"])

    def test_an_event_injected_after_the_cutoff_changes_nothing(self):
        events = scenario()
        cutoff = timestamp("2026-03-02T00:00:00Z")
        before = retrieve(events=events, target=target_at(cutoff))
        future = S.event(20, session=S.SESSIONS[30])
        after = retrieve(events=events + [future], target=target_at(cutoff))
        self.assertEqual(after["members"], before["members"])
        self.assertEqual(reasons(after)["e20"], "LABEL_NOT_YET_MATURED")

    def test_maturity_is_decided_label_by_label(self):
        events = [S.event(0)]
        target = target_at(fp.label_available_at("day1_close_return", events[0]["reaction_session"], S.CAL))
        policy = S.policy_with(**{"analogues.min_members": 1})
        day1 = retrieve(events=events, target=target, policy=policy)
        session2 = retrieve(events=events, target=target, label="session_2_close_return", policy=policy)
        self.assertEqual((day1["state"], session2["state"]), (an.FOUND, an.INSUFFICIENT))
        self.assertEqual(reasons(session2), {"e0": "LABEL_NOT_YET_MATURED"})
        self.assertEqual(set(day1["members"][0]["outcomes"]), {n for n in fp.LABELS if not n.startswith("session_")})

    def test_outcomes_shown_for_a_member_are_only_those_that_matured_by_the_cutoff(self):
        for target_event in REAL["events"]:
            target = fp.historical_target(target_event)
            for label in ("day1_close_return", "session_10_close_return"):
                for member in an.retrieve(target, REAL["events"], label, REAL["policy"])["members"]:
                    event = next(e for e in REAL["events"] if e["event_id"] == member["event_id"])
                    self.assertLessEqual(event["available_at"][label], target["cutoff"])
                    for name in member["outcomes"]:
                        self.assertLessEqual(event["available_at"][name], target["cutoff"], (target_event["event_id"], member["event_id"], name))

    def test_absence_is_not_visible_before_the_label_matures(self):
        events = [S.event(0, absent=("positive_gap_filled",))]
        matured = fp.label_available_at("positive_gap_filled", events[0]["reaction_session"], S.CAL)
        early = retrieve(events=events, target=target_at(matured - timedelta(minutes=1)), label="positive_gap_filled")
        later = retrieve(events=events, target=target_at(matured), label="positive_gap_filled")
        self.assertEqual(reasons(early), {"e0": "LABEL_NOT_YET_MATURED"})
        self.assertEqual(reasons(later), {"e0": "LABEL_ABSENT"})
        self.assertEqual(later["excluded"][0]["detail"], "TEST_ABSENT")

    def test_same_cluster_events_count_once_and_the_targets_own_cluster_is_excluded(self):
        events = [S.event(0), S.event(1, cluster="c0"), S.event(2)]
        result = retrieve(events=events, policy=S.policy_with(**{"analogues.min_members": 1}))
        self.assertEqual([m["event_id"] for m in result["members"]], ["e0", "e2"])
        self.assertEqual(reasons(result), {"e1": "CLUSTER_ALREADY_COUNTED"})
        own = retrieve(events=events, target=target_at(S.LATE, cluster_id="c0"), policy=S.policy_with(**{"analogues.min_members": 1}))
        self.assertEqual([m["event_id"] for m in own["members"]], ["e2"])
        self.assertEqual(reasons(own), {"e0": "SAME_CLUSTER", "e1": "SAME_CLUSTER"})

    def test_selection_uses_no_outcome_value(self):
        events, junk = scenario(), S.poisoned(scenario())
        for label in ("day1_close_return", "gap_ge_5pct", "session_5_close_return", "positive_gap_filled"):
            plain, other = retrieve(events=events, label=label), retrieve(events=junk, label=label)
            choice = lambda r: (r["state"], r["distance_reached"], [(m["event_id"], m["distance"]) for m in r["members"]],  # noqa: E731
                                r["excluded"], r["pool"], r["counts"])
            self.assertEqual(choice(plain), choice(other), label)
            self.assertNotEqual(plain["members"][0]["outcomes"], other["members"][0]["outcomes"])  # the poison did change the values
        for event in events:
            target = fp.historical_target(event)
            for label in ("day1_close_return", "session_2_close_return"):
                a, b = an.retrieve(target, events, label, S.POLICY), an.retrieve(target, junk, label, S.POLICY)
                self.assertEqual([m["event_id"] for m in a["members"]], [m["event_id"] for m in b["members"]])
                self.assertEqual(a["excluded"], b["excluded"])

    def test_whether_a_conditional_label_exists_is_its_definition_and_the_only_outcome_dependence(self):
        events = [S.event(i) for i in range(6)]
        events[0] = S.event(0, absent=("positive_gap_filled",))
        conditional = retrieve(events=events, label="positive_gap_filled")
        self.assertEqual(reasons(conditional)["e0"], "LABEL_ABSENT")
        self.assertEqual(conditional["counts"]["members"], 5)
        unconditional = retrieve(events=events, label="day1_close_return")
        self.assertIn("e0", [m["event_id"] for m in unconditional["members"]])


class TargetTests(unittest.TestCase):
    AS_OF = "2026-06-01T00:00:00Z"

    def test_a_new_event_descriptor_is_read(self):
        target = fp.new_target({"release_timing": "premarket", "sic": "2834", "as_of": self.AS_OF}, {})
        self.assertEqual((target["kind"], target["sic_division"], target["sic_major_group"], target["cik"], target["event_id"]),
                         ("new", "D", "28", None, None))
        self.assertEqual(target["cutoff"], timestamp(self.AS_OF))
        mapped = fp.new_target({"release_timing": "after_hours", "cik": "0000949858", "as_of": self.AS_OF}, REAL["sectors"])
        self.assertEqual((mapped["sic"], mapped["cik"]), ("2835", "0000949858"))

    def test_malformed_descriptors_are_refused(self):
        good = {"release_timing": "premarket", "sic": "2834", "as_of": self.AS_OF}
        cases = {"no as_of": {k: v for k, v in good.items() if k != "as_of"}, "no timing": {k: v for k, v in good.items() if k != "release_timing"},
                 "unknown key": dict(good, price=1.0), "regular timing": dict(good, release_timing="regular"), "numeric sic": dict(good, sic=2834),
                 "no sic or cik": {k: v for k, v in good.items() if k != "sic"}, "unknown cik": dict(good, cik="0000000001"),
                 "naive as_of": dict(good, as_of="2026-06-01T00:00:00"), "not an object": [good]}
        for name, descriptor in cases.items():
            with self.subTest(name), self.assertRaises(DataError):
                fp.new_target(descriptor, {})
        with self.assertRaises(DataError):
            fp.new_target({"release_timing": "after_hours", "cik": "0000949858", "sic": "7372", "as_of": self.AS_OF}, REAL["sectors"])

    def test_a_historical_target_is_selected_by_id(self):
        target = fp.resolve_target(REAL, "rekr-2026-03-31")
        self.assertEqual((target["kind"], target["ticker"], iso(target["cutoff"])), ("historical", "REKR", "2026-03-31T20:10:00Z"))
        with self.assertRaises(DataError):
            fp.resolve_target(REAL, "nope")
        with self.assertRaises(DataError):
            fp.resolve_target(REAL)


class RealDataTests(unittest.TestCase):
    def test_pool_report_matches_the_hand_computed_table_in_the_proposal(self):
        summary = an.pool_report(REAL)["summary"]
        expected = {"day1_close_return": (17, 13, 3, 1), "session_2_close_return": (16, 10, 3, 1), "session_5_close_return": (16, 8, 0, 1),
                    "session_10_close_return": (10, 7, 0, 3), "session_20_close_return": (7, 4, 0, 7)}
        for label, want in expected.items():
            got = summary[label]
            self.assertEqual((got["with_5_or_more"], got["with_10_or_more"], got["with_20_or_more"], got["with_none"]), want, label)
            self.assertEqual(got["targets"], 23)

    def test_analogue_sets_exist_for_fewer_targets_than_matured_events_suggest(self):
        summary = an.pool_report(REAL)["summary"]
        found = {label: summary[label]["analogues_found"] for label in an.HORIZON_LABELS}
        self.assertEqual(found, {"day1_close_return": 13, "session_2_close_return": 12, "session_5_close_return": 11,
                                 "session_10_close_return": 8, "session_20_close_return": 4})

    def test_the_earliest_target_has_nothing_matured_to_draw_on(self):
        first = an.pool_report(REAL)["targets"][0]
        self.assertEqual(first["event_id"], "caci-2026-01-21")
        for label, row in first["labels"].items():
            self.assertEqual((row["eligible"], row["state"]), (0, an.INSUFFICIENT), label)

    def test_committed_analogue_reports_are_what_the_code_produces(self):
        def committed(name):
            return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))

        def regenerate(report):
            return json.loads(fp.dump_report(report))

        self.assertEqual(committed("m2-analogue-pools-2026-09-26.json"), regenerate(an.pool_report(REAL)))
        historical = an.analogue_query(REAL, fp.resolve_target(REAL, "rekr-2026-03-31"), LABELS_EXAMPLE)
        self.assertEqual(committed("m2-analogue-example-historical-2026-09-26.json"), regenerate(historical))
        descriptor = ROOT / "tests" / "fixtures" / "m2_new_event_example.json"
        new = an.analogue_query(REAL, fp.resolve_target(REAL, None, descriptor), LABELS_EXAMPLE)
        self.assertEqual(committed("m2-analogue-example-new-event-2026-09-26.json"), regenerate(new))

    def test_the_command_writes_a_query_report(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            path = Path(tmp) / "q.json"
            argv = ["analogues", "--event", "rekr-2026-03-31", "--output", str(path)]
            for label in LABELS_EXAMPLE:
                argv += ["--label", label]
            self.assertEqual(cli.main(argv), 0)
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(out.getvalue())["kind"], "analogue_query")
        self.assertEqual([q["label"] for q in written["queries"]], LABELS_EXAMPLE)

    def test_a_new_event_is_answered_from_every_matured_event(self):
        target = fp.resolve_target(REAL, None, ROOT / "tests" / "fixtures" / "m2_new_event_example.json")
        result = an.retrieve(target, REAL["events"], "day1_close_return", REAL["policy"])
        self.assertEqual(result["pool"]["eligible"], 23)
        self.assertEqual(result["state"], an.FOUND)


if __name__ == "__main__":
    unittest.main()
