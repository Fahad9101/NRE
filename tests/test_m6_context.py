import unittest
from datetime import datetime, timezone

from nre.m6_context import evaluate_fold, fold_rows, issuer_context, outcome


def at(day, hour):
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def event(event_id, day, *, cik="issuer-a", gap=0.10, close=0.20, maturity=None):
    return {
        "event_id": event_id,
        "cluster_id": event_id,
        "cik": cik,
        "reaction_session": at(day, 0).date().isoformat(),
        "cutoff": at(day, 12),
        "available_at": {"day1_close_return": maturity or at(day, 21)},
        "labels": {
            "day1_open_return": {"value": gap},
            "day1_close_return": {"value": close},
        },
    }


class ContextComparisonTests(unittest.TestCase):
    def test_target_is_signed_from_the_opening_reference(self):
        self.assertAlmostEqual(outcome(event("up-fade", 6, gap=0.25, close=0.0)), 0.2)
        self.assertAlmostEqual(outcome(event("down-fade", 6, gap=-0.2, close=0.0)), 0.25)
        self.assertAlmostEqual(outcome(event("up-continuation", 6, gap=0.25, close=0.5)), -0.2)

        for gap, close in [(0, 0.2), (None, 0.2), (0.1, None), (-1.0, 0.2), (0.1, float("inf"))]:
            with self.subTest(gap=gap, close=close):
                self.assertIsNone(outcome(event("unavailable", 6, gap=gap, close=close)))

    def test_context_uses_only_mature_earlier_session_closes(self):
        current = event("test", 6)
        own = event("own", 2, close=0.30)
        peer = event("peer", 3, cik="issuer-b", gap=None, close=0.10)
        history = [
            own,
            peer,
            event("exact-cutoff", 4, close=0.60, maturity=current["cutoff"]),
            event("too-late", 5, close=0.70, maturity=at(6, 13)),
            event("same-session", 6, close=0.80, maturity=at(6, 11)),
            event("caveated-close", 5, close=None),
        ]
        centered, used = issuer_context(current, history)
        self.assertAlmostEqual(centered, (0.30 - 0.20) / 11)
        self.assertCountEqual([row["event_id"] for row in used], ["own", "peer"])

    def test_context_is_independent_of_current_open_and_outcome(self):
        history = [event("prior-own", 2, close=0.30), event("prior-peer", 3, cik="issuer-b", close=0.10)]
        first, first_sources = issuer_context(event("test", 6, gap=0.20, close=0.45), history)
        second, second_sources = issuer_context(event("test", 6, gap=-0.25, close=None), history)
        self.assertEqual(first, second)
        self.assertEqual(first_sources, second_sources)

    def test_no_own_history_centers_to_zero(self):
        current = event("test", 6)
        peer = event("peer", 3, cik="issuer-b", close=0.10)
        centered, _ = issuer_context(current, [peer])
        self.assertEqual(centered, 0.0)
        self.assertEqual(issuer_context(current, []), (0.0, []))


    def test_first_test_cutoff_purges_fit_rows_and_their_history(self):
        train = [
            event("fit-peer", 1, cik="issuer-b", gap=-0.20, close=0.10),
            event("fit-own", 2, close=0.30),
            event("close-only", 3, gap=None, close=0.40),
            event("exact-boundary", 4, maturity=at(6, 12)),
            event("after-boundary", 5, maturity=at(6, 13)),
        ]
        test = [event("first-test", 6), event("later-test", 7, cik="issuer-c")]
        blocks = {row["event_id"]: 1 for row in train}
        blocks.update({row["event_id"]: 3 for row in test})
        fit_rows, test_rows = fold_rows(train + test, blocks, 3)
        self.assertEqual([row.get("exclusion") for row in fit_rows], [
            None, None, "opening_unavailable", "fit_label_not_mature", "fit_label_not_mature",
        ])
        for row in test_rows:
            self.assertCountEqual(row["history_ids"], ["fit-peer", "fit-own", "close-only"])
        self.assertEqual([row["own_history"] for row in test_rows], [2, 0])

        initial = evaluate_fold(train + test, blocks, 3, 10)["paired_rows"]
        changed = [test[0], event("later-test", 7, cik="issuer-c", close=0.5)]
        revised = evaluate_fold(train + changed, blocks, 3, 10)["paired_rows"]
        self.assertTrue(initial[1]["baseline_fallback"])
        self.assertEqual(initial[1]["baseline"], initial[1]["challenger"])
        self.assertEqual(initial[0], revised[0])
        self.assertNotEqual(initial[1]["target"], revised[1]["target"])
        self.assertEqual(initial[1]["challenger"], revised[1]["challenger"])

    def test_fold_rejects_split_sessions(self):
        train, test = event("training", 2), event("held", 2)
        with self.assertRaisesRegex(ValueError, "cluster or session"):
            fold_rows([train, test], {"training": 1, "held": 3}, 3)
