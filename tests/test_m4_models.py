"""The Milestone 4 Phase 2 baselines on synthetic data: the linear algebra and fits checked against independent calculations, the cell baselines and their
fallbacks, the history-based predictors, the logistic regression's monotone repair and the ridge regression's residual quantiles. No real event is used."""
import copy
import math
import random
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m4_support as S  # noqa: E402
from nre import fingerprints as fp  # noqa: E402
from nre import m4_data as d  # noqa: E402
from nre import m4_features as feat  # noqa: E402
from nre import m4_harness as h  # noqa: E402
from nre import m4_models as mm  # noqa: E402
from nre import m4_protocol as pr  # noqa: E402
from nre import m4_scoping_evidence as ev  # noqa: E402

PROTOCOL = pr.load_json(pr.PROTOCOL_PATH)
TARGETS = d.targets(PROTOCOL)
FOLDS = {f.name: f for f in d.folds(PROTOCOL)}


def det(matrix):
    """The determinant by Laplace expansion: slow, short and unrelated to the module's elimination, for checking it."""
    if len(matrix) == 1:
        return matrix[0][0]
    return sum(((-1) ** j) * matrix[0][j] * det([row[:j] + row[j + 1:] for row in matrix[1:]]) for j in range(len(matrix)))


def cramer(a, b):
    total = det(a)
    return [det([row[:i] + [b[r]] + row[i + 1:] for r, row in enumerate(a)]) / total for i in range(len(a))]


def reference_logistic(z, y, lam=1.0, iterations=60):
    """Penalized logistic regression by Newton's method with Cramer's rule for the step, written separately from the module."""
    rows = [[1.0] + list(r) for r in z]
    k = len(rows[0])
    beta = [0.0] * k
    for _ in range(iterations):
        p = [1 / (1 + math.exp(-sum(b * x for b, x in zip(beta, row)))) for row in rows]
        g = [sum(row[j] * (yi - pi) for row, yi, pi in zip(rows, y, p)) - (lam * beta[j] if j else 0.0) for j in range(k)]
        hessian = [[sum(row[a] * row[b] * pi * (1 - pi) for row, pi in zip(rows, p)) + (lam if a == b and a else 0.0) for b in range(k)] for a in range(k)]
        beta = [b + s for b, s in zip(beta, cramer(hessian, g))]
    return beta


def random_problem(seed, n=60, features=3, separable=False):
    rng = random.Random(seed)
    z = [[rng.gauss(0, 1) for _ in range(features)] for _ in range(n)]
    truth = [rng.gauss(0, 1.5) for _ in range(features)]
    y = []
    for row in z:
        score = sum(t * x for t, x in zip(truth, row)) * (8 if separable else 1)
        y.append(1.0 if rng.random() < 1 / (1 + math.exp(-score)) else 0.0)
    return z, y


def gradient_of(z, y, beta, lam=1.0):
    rows = [[1.0] + list(r) for r in z]
    p = [1 / (1 + math.exp(-sum(b * x for b, x in zip(beta, row)))) for row in rows]
    return [sum(row[j] * (yi - pi) for row, yi, pi in zip(rows, y, p)) - (lam * beta[j] if j else 0.0) for j in range(len(beta))]


def blank(**values):
    labels = {name: {"value": None, "reason": "TEST_ABSENT"} for name in fp.LABELS}
    for name, value in values.items():
        labels[name] = {"value": value, "reason": None}
    return labels


def day(n):
    return [x for x in S.CAL.days if "2026-02-02" <= x <= "2026-06-30"][n]


def small_event(n, timing="after_hours", sic="2834", positive=False, issuer=None, **labels):
    return S.build_event(n, day(n), timing, "%010d" % (issuer if issuer is not None else 1000 + n), sic, "k%d" % n, blank(gap_ge_3pct=positive, **labels))


class LinearAlgebraTests(unittest.TestCase):
    def test_solve_a_known_system(self):
        self.assertEqual([round(x, 12) for x in mm.solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0])], [0.8, 1.4])

    def test_solve_agrees_with_cramers_rule_on_random_systems_and_pivots_around_a_zero(self):
        rng = random.Random(5)
        for _ in range(25):
            k = rng.randint(2, 5)
            a = [[rng.gauss(0, 1) for _ in range(k)] for _ in range(k)]
            b = [rng.gauss(0, 1) for _ in range(k)]
            for got, want in zip(mm.solve(a, b), cramer(a, b)):
                self.assertAlmostEqual(got, want, places=8)
        self.assertEqual([round(x, 12) for x in mm.solve([[0.0, 1.0], [1.0, 0.0]], [2.0, 3.0])], [3.0, 2.0])

    def test_a_singular_system_is_model_fit_failed(self):
        with self.assertRaises(h.Abstain) as caught:
            mm.solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])
        self.assertEqual(caught.exception.state, "MODEL_FIT_FAILED")

    def test_the_sigmoid_does_not_overflow_and_is_symmetric(self):
        self.assertEqual(mm.sigmoid(0.0), 0.5)
        self.assertEqual(mm.sigmoid(800.0), 1.0)
        self.assertEqual(mm.sigmoid(-800.0), 0.0)
        for z in (-3.0, -0.2, 1.7, 9.0):
            self.assertAlmostEqual(mm.sigmoid(-z), 1 - mm.sigmoid(z), places=14)

    def test_logit_inverts_the_sigmoid_and_rates_are_clipped_to_the_protocols_bounds(self):
        self.assertAlmostEqual(mm.logit(mm.sigmoid(1.3)), 1.3)
        self.assertEqual((mm.clip_rate(0.0), mm.clip_rate(1.0), mm.clip_rate(0.4)), (0.01, 0.99, 0.4))

    def test_standardization_uses_the_population_standard_deviation_and_drops_a_constant_feature(self):
        rows = [[1.0, 5.0, 0.1], [2.0, 5.0, 0.1], [3.0, 5.0, 0.1], [4.0, 5.0, 0.1]]
        means, sds, kept, dropped = mm.standardization(rows)
        self.assertEqual(means[:2], [2.5, 5.0])
        self.assertAlmostEqual(sds[0], math.sqrt(1.25))  # divided by n = 4, not 3
        self.assertEqual((kept, dropped), ([0], [1, 2]))  # a constant column, 0.1 included whatever its rounding, is dropped
        self.assertEqual(mm.standardized([3.5, 5.0, 0.1], means, sds, kept), [(3.5 - 2.5) / math.sqrt(1.25)])


class FitTests(unittest.TestCase):
    def test_the_logistic_fit_satisfies_the_penalized_optimality_conditions(self):
        for seed in range(12):
            z, y = random_problem(seed, separable=seed % 3 == 0)  # every third problem is nearly separable: only the penalty keeps the solution finite
            beta, iterations, gradient = mm.fit_logistic(z, y)
            self.assertLess(max(abs(g) for g in gradient_of(z, y, beta)), 1e-7, seed)
            self.assertLess(iterations, 30)
            self.assertLess(gradient, 1e-7)
            self.assertTrue(all(math.isfinite(b) for b in beta))

    def test_the_logistic_fit_agrees_with_an_independent_newton_solver(self):
        for seed in (1, 2, 3, 4):
            z, y = random_problem(seed, features=3 if seed % 2 else 2)
            for got, want in zip(mm.fit_logistic(z, y)[0], reference_logistic(z, y)):
                self.assertAlmostEqual(got, want, places=7)

    def test_the_intercept_is_not_penalized_so_the_fitted_probabilities_sum_to_the_outcomes(self):
        z, y = random_problem(9)
        beta = mm.fit_logistic(z, y)[0]
        fitted = [mm.sigmoid(beta[0] + sum(b * x for b, x in zip(beta[1:], row))) for row in z]
        self.assertAlmostEqual(sum(fitted), sum(y), places=6)  # the intercept's own condition: the sum of (y - p) is zero

    def test_the_penalty_is_lambda_one_on_every_coefficient_but_the_intercept(self):
        z, y = random_problem(4)
        beta = mm.fit_logistic(z, y)[0]
        rows = [[1.0] + r for r in z]
        p = [mm.sigmoid(sum(b * x for b, x in zip(beta, row))) for row in rows]
        for j in range(1, len(beta)):  # at the optimum, the data term of the gradient equals lambda times the coefficient
            self.assertAlmostEqual(sum(row[j] * (yi - pi) for row, yi, pi in zip(rows, y, p)), pr.RIDGE_LAMBDA * beta[j], places=6)
        self.assertAlmostEqual(sum(yi - pi for yi, pi in zip(y, p)), 0.0, places=6)

    def test_without_the_iterations_to_converge_the_fit_is_model_fit_failed_and_nothing_is_returned(self):
        z, y = random_problem(2)
        with mock.patch.object(pr, "NEWTON_MAX_ITERATIONS", 1):
            with self.assertRaises(h.Abstain) as caught:
                mm.fit_logistic(z, y)
        self.assertEqual(caught.exception.state, "MODEL_FIT_FAILED")
        self.assertIn("did not converge", caught.exception.reason)

    def test_a_tighter_tolerance_than_the_iterations_allow_is_also_a_failure(self):
        z, y = random_problem(2)
        with mock.patch.object(pr, "NEWTON_TOLERANCE", 0.0):
            with self.assertRaises(h.Abstain):
                mm.fit_logistic(z, y)

    def test_the_ridge_fit_in_one_feature_is_the_closed_form(self):
        z = [[-1.5], [-0.5], [0.5], [1.5]]  # mean 0, so the intercept is the mean of y and the slope is sum(z y) / (sum(z^2) + lambda)
        y = [1.0, 2.0, 4.0, 7.0]
        beta = mm.fit_ridge(z, y)
        self.assertAlmostEqual(beta[0], 3.5)
        self.assertAlmostEqual(beta[1], (-1.5 * 1 - 0.5 * 2 + 0.5 * 4 + 1.5 * 7) / (2.25 + 0.25 + 0.25 + 2.25 + pr.RIDGE_LAMBDA))

    def test_the_ridge_fit_agrees_with_cramers_rule_and_leaves_the_intercept_unpenalized(self):
        rng = random.Random(8)
        z = [[rng.gauss(0, 1) for _ in range(3)] for _ in range(50)]
        y = [0.3 + 0.5 * r[0] - 0.2 * r[2] + rng.gauss(0, 0.1) for r in z]
        beta = mm.fit_ridge(z, y)
        rows = [[1.0] + r for r in z]
        a = [[sum(r[i] * r[j] for r in rows) + (1.0 if i == j and i else 0.0) for j in range(4)] for i in range(4)]
        b = [sum(r[i] * yi for r, yi in zip(rows, y)) for i in range(4)]
        for got, want in zip(beta, cramer(a, b)):
            self.assertAlmostEqual(got, want, places=9)
        residuals = [yi - sum(c * x for c, x in zip(beta, r)) for r, yi in zip(rows, y)]
        self.assertAlmostEqual(sum(residuals), 0.0, places=8)  # the intercept's own normal equation


class CellBaselineTests(unittest.TestCase):
    TARGET = TARGETS["gap_ge_3pct"]

    def train(self):
        """24 after-hours events (6 positive), 9 premarket events (9 positive: below the cell minimum of 10); sectors D, I and B-other."""
        events = [small_event(n, "after_hours", sic="2834" if n % 3 == 0 else "7372" if n % 3 == 1 else "1311", positive=n < 6) for n in range(24)]
        events += [small_event(30 + n, "premarket", sic="2834", positive=True) for n in range(9)]
        return events

    def view(self, event_id="v", timing="after_hours", sic="2834"):
        return {"event_id": event_id, "release_timing": timing, "sic_division": fp.sector_from_sic(sic)["sic_division"]}

    def test_the_timing_rate_is_the_training_rate_within_the_release_timing(self):
        model = mm.timing_rate().fit(self.train(), self.TARGET)
        self.assertEqual(model["cells"]["after_hours"], {"n": 24, "positives": 6, "rate": 0.25})
        self.assertEqual(model["pooled_rate"], 15 / 33)
        self.assertEqual(mm.timing_rate().predict(model, self.view(timing="after_hours")), 0.25)
        self.assertEqual(model.diagnostics["fallbacks_to_the_pooled_rate"], 0)

    def test_a_cell_with_fewer_than_ten_defined_training_events_falls_back_to_the_pooled_rate_and_each_use_is_counted(self):
        predictor = mm.timing_rate()
        model = predictor.fit(self.train(), self.TARGET)
        self.assertEqual(model["cells"]["premarket"]["n"], 9)
        self.assertEqual(predictor.predict(model, self.view("a", "premarket")), 15 / 33)
        self.assertEqual(predictor.predict(model, self.view("b", "premarket")), 15 / 33)
        self.assertEqual((model.diagnostics["fallbacks_to_the_pooled_rate"], model.diagnostics["fallback_event_ids"]), (2, ["a", "b"]))

    def test_a_cell_of_exactly_ten_does_not_fall_back(self):
        train = self.train() + [small_event(50, "premarket", positive=False)]
        model = mm.timing_rate().fit(train, self.TARGET)
        self.assertEqual(model["cells"]["premarket"]["n"], 10)
        self.assertEqual(mm.timing_rate().predict(model, self.view(timing="premarket")), 0.9)

    def test_the_sector_group_rate_uses_d_i_and_other_with_the_same_fallback(self):
        predictor = mm.sector_group_rate()
        model = predictor.fit(self.train(), self.TARGET)
        groups = {key: cell["n"] for key, cell in model["cells"].items()}
        self.assertEqual(groups, {"D": 8 + 9, "I": 8, "other": 8})  # D: events 0, 3, ..., 21 (8) and the nine premarket events; SIC 7372 -> I; SIC 1311 -> B -> other
        self.assertEqual(predictor.predict(model, self.view(sic="2834")), model["cells"]["D"]["rate"])
        self.assertEqual(predictor.predict(model, self.view(sic="7372")), model["pooled_rate"])  # I has 8 < 10: pooled
        self.assertEqual(model.diagnostics["fallbacks_to_the_pooled_rate"], 1)

    def test_an_unseen_cell_also_falls_back(self):
        model = mm.timing_rate().fit([small_event(n, "after_hours", positive=n % 2 == 0) for n in range(12)], self.TARGET)
        self.assertEqual(mm.timing_rate().predict(model, self.view(timing="premarket")), 0.5)
        self.assertEqual(model.diagnostics["fallbacks_to_the_pooled_rate"], 1)

    def test_nothing_defined_to_learn_from_is_insufficient_data_for_every_baseline(self):
        undefined = [S.build_event(n, day(n), "after_hours", "%010d" % n, "2834", "k%d" % n, blank()) for n in range(5)]
        for predictor, target in ((mm.timing_rate(), self.TARGET), (mm.sector_group_rate(), self.TARGET), (mm.IssuerHistoryRate(), self.TARGET),
                                  (mm.timing_quantiles(), TARGETS["day1_close_return"])):
            with self.assertRaises(h.Abstain) as caught:
                predictor.fit(undefined, target)
            self.assertEqual(caught.exception.state, "INSUFFICIENT_DATA")

    def test_the_quantile_cells_are_type_7_quantiles_with_the_same_fallback(self):
        target = TARGETS["day1_close_return"]
        train = [S.build_event(n, day(n), "after_hours", "%010d" % n, "2834", "k%d" % n, blank(day1_close_return=0.01 * n)) for n in range(1, 13)]
        train += [S.build_event(20 + n, day(20 + n), "premarket", "%010d" % (20 + n), "2834", "k%d" % (20 + n), blank(day1_close_return=0.5 + n)) for n in range(4)]
        predictor = mm.timing_quantiles()
        model = predictor.fit(train, target)
        values = sorted(0.01 * n for n in range(1, 13))
        self.assertEqual(model["cells"]["after_hours"]["quantiles"], [fp.quantile(values, q) for q in (0.1, 0.5, 0.9)])
        self.assertEqual(predictor.predict(model, self.view(timing="after_hours")), tuple(model["cells"]["after_hours"]["quantiles"]))
        self.assertEqual(predictor.predict(model, self.view("p", "premarket")), tuple(model["pooled_quantiles"]))  # 4 < 10
        self.assertEqual(model.diagnostics["fallbacks_to_the_pooled_quantiles"], 1)
        self.assertEqual(model["pooled_quantiles"], [fp.quantile(sorted(e["labels"]["day1_close_return"]["value"] for e in train), q) for q in (0.1, 0.5, 0.9)])


class IssuerHistoryTests(unittest.TestCase):
    def test_c4_is_the_issuer_history_rate_used_directly_and_counts_where_its_prior_came_from(self):
        target = TARGETS["gap_ge_3pct"]
        train = [small_event(n, positive=n % 2 == 0, issuer=1 + n % 2) for n in range(8)]
        view = {k: v for k, v in small_event(20, positive=True, issuer=1).items() if k != "labels"}
        predictor = mm.IssuerHistoryRate()
        model = predictor.fit(train, target)
        want = feat.issuer_history_rate(view, train, target)
        self.assertEqual(predictor.predict(model, view), want["rate"])
        self.assertEqual(model.diagnostics["test_events_by_prior_source"], {want["prior_source"]: 1})
        stranger = {**view, "event_id": "z", "cik": "0000009999"}
        self.assertAlmostEqual(predictor.predict(model, stranger), feat.issuer_history_rate(stranger, train, target)["rate"])
        self.assertEqual(model.diagnostics["test_events_without_an_earlier_event_of_their_own_issuer"], 1)


class LogisticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=(24, 44, 36, 36, 20))
        cls.blocks = ev.assign_blocks(cls.events)
        cls.target = TARGETS["gap_ge_3pct"]
        cls.train, cls.test = d.split(cls.events, cls.blocks, FOLDS["dev_test_block_3"])
        cls.defined = [e for e in cls.train if cls.target.function(e["labels"]) is not None]

    def test_the_features_are_the_protocols_for_each_variant_and_clock(self):
        self.assertEqual(mm.Logistic(True).names(self.target), ["after_hours", "is_I", "is_other", "logit_issuer_history_rate"])
        self.assertEqual(mm.Logistic(False).names(self.target), ["after_hours", "logit_issuer_history_rate"])
        self.assertEqual(mm.Logistic(True).names(TARGETS["extension_after_open_ge_5pct"])[-1], "open_gap")
        self.assertEqual((mm.Logistic(True).id, mm.Logistic(False).id), ("M2_logistic", "M2_without_sector"))

    def test_the_raw_features_are_the_protocols_in_order_with_the_logit_of_the_clipped_history_rate(self):
        target = TARGETS["gap_ge_3pct"]
        # issuer 1 had two earlier events (one positive); with 5 earlier events in all (2 positive) the prior is 0.4: rate = (1 + 10 * 0.4) / (2 + 10)
        train = [small_event(0, positive=True, issuer=1), small_event(1, positive=False, issuer=1), small_event(2, positive=True, issuer=2),
                 small_event(3, positive=False, issuer=3), small_event(4, positive=False, issuer=4)]
        event = small_event(9, timing="premarket", sic="7372", positive=True, issuer=1)
        expected = [0, 1, 0, math.log(((1 + 10 * 0.4) / 12) / (1 - (1 + 10 * 0.4) / 12))]
        for got, want in zip(mm.Logistic(True).raw(event, train, target), expected):
            self.assertAlmostEqual(got, want, places=12)
        self.assertEqual(len(mm.Logistic(False).raw(event, train, target)), 2)  # after_hours and the history feature only
        shifted = [small_event(n, positive=False, issuer=1 + n % 2) for n in range(6)]  # a history of all negatives clips at 0.01 instead of diverging
        self.assertAlmostEqual(mm.Logistic(True).raw(small_event(20, issuer=1), shifted, target)[-1], mm.logit(0.01), places=12)

    def test_the_fit_satisfies_the_optimality_conditions_on_the_standardized_features(self):
        for with_sector in (True, False):
            predictor = mm.Logistic(with_sector)
            model = predictor.fit(self.defined, self.target)
            raw = [predictor.raw(e, self.defined, self.target) for e in self.defined]
            means, sds, kept, dropped = mm.standardization(raw)
            z = [mm.standardized(row, means, sds, kept) for row in raw]
            y = [1.0 if self.target.function(e["labels"]) else 0.0 for e in self.defined]
            self.assertLess(max(abs(g) for g in gradient_of(z, y, model.context["beta"])), 1e-7)
            for got, want in zip(model.context["beta"], reference_logistic(z, y)):
                self.assertAlmostEqual(got, want, places=7)
            self.assertEqual(model["rows"], len(self.defined))
            self.assertTrue(model.diagnostics["converged"])

    def test_parameters_are_rounded_for_the_record_and_include_what_is_needed_to_reproduce_them(self):
        model = mm.Logistic().fit(self.defined, self.target)
        for key in ("intercept",):
            self.assertEqual(model[key], round(model[key], 12))
        self.assertEqual(sorted(model), sorted(["features", "kept", "dropped", "means", "standard_deviations", "intercept", "coefficients", "lambda", "rows"]))
        self.assertEqual(model["lambda"], 1.0)
        self.assertTrue(all(x == round(x, 12) for x in model["coefficients"] + model["means"] + model["standard_deviations"]))

    def test_a_constant_feature_is_dropped_and_logged_and_the_model_still_fits(self):
        after_hours_only = [e for e in self.defined if e["release_timing"] == "after_hours"]
        model = mm.Logistic().fit(after_hours_only, self.target)
        self.assertEqual(model["dropped"], ["after_hours"])
        self.assertEqual(model.diagnostics["dropped_features"], ["after_hours"])
        self.assertEqual(len(model["coefficients"]), 3)
        predictor = mm.Logistic()
        view = {k: v for k, v in self.test[0].items() if k != "labels"}
        flipped = {**view, "release_timing": "premarket" if view["release_timing"] == "after_hours" else "after_hours"}
        self.assertEqual(predictor.predict(model, view), predictor.predict(model, flipped))  # a dropped feature takes no part in predicting

    def test_predictions_are_probabilities_and_do_not_depend_on_the_test_events_labels(self):
        predictor = mm.Logistic()
        model = predictor.fit(self.defined, self.target)
        for event in self.test:
            view = {k: v for k, v in event.items() if k not in ("labels", "labels_sha256")}
            p = predictor.predict(model, view)
            self.assertTrue(0 < p < 1)
        flipped = copy.deepcopy(self.test[0])
        for label in flipped["labels"].values():
            if isinstance(label["value"], bool):
                label["value"] = not label["value"]
        a = predictor.predict(model, {k: v for k, v in self.test[0].items() if k != "labels"})
        b = predictor.predict(model, {k: v for k, v in flipped.items() if k != "labels"})
        self.assertEqual(a, b)

    def test_a_training_rows_history_feature_uses_only_earlier_matured_events(self):
        predictor = mm.Logistic()
        before = predictor.raw(self.defined[10], self.defined, self.target)
        altered = copy.deepcopy(self.defined)
        flipped = 0
        for event in altered:
            if event["reaction_session"] >= self.defined[10]["reaction_session"] and event["event_id"] != self.defined[10]["event_id"]:
                event["labels"]["gap_ge_3pct"]["value"] = not event["labels"]["gap_ge_3pct"]["value"]
                flipped += 1
        self.assertGreater(flipped, 10)
        self.assertEqual(predictor.raw(altered[10], altered, self.target), before)
        earlier = copy.deepcopy(self.defined)
        for event in earlier:
            if event["reaction_session"] < self.defined[10]["reaction_session"]:
                event["labels"]["gap_ge_3pct"]["value"] = not event["labels"]["gap_ge_3pct"]["value"]
        self.assertNotEqual(predictor.raw(earlier[10], earlier, self.target), before)  # ...while the earlier ones are exactly what it learns from

    def test_the_monotone_repair_caps_each_probability_at_the_looser_thresholds_and_counts_every_repair(self):
        predictor, base = mm.Logistic(), mm.Logistic()
        model = base.fit(self.defined, self.target)
        views = [{k: v for k, v in e.items() if k != "labels"} for e in self.test]
        plain = [base.predict(model, v) for v in views]
        cap = {v["event_id"]: (p / 2 if i % 2 == 0 else 1.0) for i, (v, p) in enumerate(zip(views, plain))}  # every even-numbered event is above its cap
        capped = mm.Logistic(True, cap)
        capped_model = capped.fit(self.defined, self.target)
        out = [capped.predict(capped_model, v) for v in views]
        for i, (p, q, v) in enumerate(zip(plain, out, views)):
            self.assertEqual(q, cap[v["event_id"]] if i % 2 == 0 else p)
        repaired = [v["event_id"] for i, v in enumerate(views) if i % 2 == 0]
        self.assertEqual(capped_model.diagnostics["repairs_of_the_nested_threshold"], len(repaired))
        self.assertEqual(capped_model.diagnostics["repaired_event_ids"], repaired)
        self.assertEqual(predictor.cap, None)

    def test_a_probability_exactly_at_its_cap_is_not_a_repair(self):
        base = mm.Logistic()
        model = base.fit(self.defined, self.target)
        view = {k: v for k, v in self.test[0].items() if k != "labels"}
        p = base.predict(model, view)
        capped = mm.Logistic(True, {view["event_id"]: p})
        capped_model = capped.fit(self.defined, self.target)
        self.assertEqual(capped.predict(capped_model, view), p)
        self.assertEqual(capped_model.diagnostics["repairs_of_the_nested_threshold"], 0)

    def test_without_the_looser_thresholds_probabilities_the_capped_model_fails_rather_than_goes_uncapped(self):
        with self.assertRaises(h.Abstain) as caught:
            mm.Logistic(True, {}).fit(self.defined, self.target)
        self.assertEqual(caught.exception.state, "MODEL_FIT_FAILED")
        capped = mm.Logistic(True, {"someone-else": 0.5})
        model = capped.fit(self.defined, self.target)
        with self.assertRaises(d.ProtocolGap):
            capped.predict(model, {k: v for k, v in self.test[0].items() if k != "labels"})

    def test_the_fit_uses_only_events_with_the_target_defined(self):
        undefined = copy.deepcopy(self.defined[:5])
        for event in undefined:
            event["event_id"] += "-undefined"
            event["labels"]["gap_ge_3pct"] = {"value": None, "reason": "CAVEAT"}
        model = mm.Logistic().fit(self.defined + undefined, self.target)
        self.assertEqual(model["rows"], len(self.defined))


class RidgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.spec = S.dataset(sizes=(24, 44, 36, 36, 20))
        cls.blocks = ev.assign_blocks(cls.events)
        cls.target = TARGETS["day1_close_return"]
        cls.train, cls.test = d.split(cls.events, cls.blocks, FOLDS["dev_test_block_3"])

    def test_the_features_are_the_protocols_and_the_variants_differ_only_by_the_sector_indicators(self):
        self.assertEqual(mm.Ridge(True).names(self.target), ["after_hours", "is_I", "is_other", "issuer_history_mean"])
        self.assertEqual(mm.Ridge(False).names(self.target), ["after_hours", "issuer_history_mean"])
        self.assertEqual((mm.Ridge(True).id, mm.Ridge(False).id), ("M3_ridge_linear", "M3_without_sector"))

    def test_training_rows_with_no_earlier_matured_event_are_left_out_counted_and_still_serve_as_history(self):
        predictor = mm.Ridge()
        model = predictor.fit(self.train, self.target)
        without = [e for e in self.train if not feat.history(e, self.train, self.target)]
        self.assertGreater(len(without), 0)
        self.assertEqual(model.diagnostics["training_rows_without_an_earlier_event"], len(without))
        self.assertEqual(sorted(model.diagnostics["left_out_event_ids"]), sorted(e["event_id"] for e in without))
        self.assertEqual(model["rows"], len(self.train) - len(without))
        later = next(e for e in self.train if e["event_id"] not in {w["event_id"] for w in without})
        self.assertTrue(set(w["event_id"] for w in without) & set(feat.issuer_history_mean(later, self.train, self.target)["history_event_ids"]))

    def test_the_fit_is_the_ridge_solution_and_the_residuals_sum_to_zero(self):
        predictor = mm.Ridge()
        model = predictor.fit(self.train, self.target)
        rows, ys = [], []
        for event in self.train:
            try:
                rows.append(predictor.raw(event, self.train, self.target))
            except d.ProtocolGap:
                continue
            ys.append(event["labels"]["day1_close_return"]["value"])
        means, sds, kept, dropped = mm.standardization(rows)
        z = [[1.0] + mm.standardized(r, means, sds, kept) for r in rows]
        a = [[sum(r[i] * r[j] for r in z) + (1.0 if i == j and i else 0.0) for j in range(len(z[0]))] for i in range(len(z[0]))]
        b = [sum(r[i] * y for r, y in zip(z, ys)) for i in range(len(z[0]))]
        for got, want in zip(model.context["beta"], cramer(a, b)):
            self.assertAlmostEqual(got, want, places=8)
        residuals = [y - sum(c * x for c, x in zip(model.context["beta"], r)) for r, y in zip(z, ys)]
        self.assertAlmostEqual(sum(residuals), 0.0, places=8)

    def test_the_quantile_outputs_are_the_fitted_mean_plus_the_training_residual_quantiles(self):
        predictor = mm.Ridge()
        model = predictor.fit(self.train, self.target)
        view = {k: v for k, v in self.test[0].items() if k != "labels"}
        c = model.context
        x = predictor.raw(view, self.train, self.target)
        mean = c["beta"][0] + sum(b * z for b, z in zip(c["beta"][1:], mm.standardized(x, c["means"], c["sds"], c["kept"])))
        low, mid, high = predictor.predict(model, view)
        self.assertAlmostEqual(low, mean + c["residual_quantiles"][0])
        self.assertAlmostEqual(high, mean + c["residual_quantiles"][2])
        self.assertLessEqual(low, mid)
        self.assertLessEqual(mid, high)
        self.assertEqual(model["residual_quantiles"], [mm.clean(q) for q in c["residual_quantiles"]])

    def test_a_fit_with_fewer_than_forty_rows_left_is_insufficient_data(self):
        with self.assertRaises(h.Abstain) as caught:
            mm.Ridge().fit(self.train[:41], self.target)  # a few of the earliest have no history, which leaves fewer than 40
        self.assertEqual(caught.exception.state, "INSUFFICIENT_DATA")
        mm.Ridge().fit(self.train[:50], self.target)

    def test_a_test_event_with_no_earlier_event_stops_the_run_instead_of_being_given_a_default(self):
        predictor = mm.Ridge()
        model = predictor.fit(self.train, self.target)
        view = {k: v for k, v in self.test[0].items() if k != "labels"}
        view["reaction_session"] = "2020-01-02"
        with self.assertRaises(d.ProtocolGap):
            predictor.predict(model, view)

    def test_the_without_sector_variant_has_fewer_coefficients(self):
        self.assertEqual(len(mm.Ridge(True).fit(self.train, self.target)["coefficients"]), 4)
        self.assertEqual(len(mm.Ridge(False).fit(self.train, self.target)["coefficients"]), 2)

    def test_a_row_whose_earlier_events_had_not_matured_is_left_out_of_the_fit(self):
        train = d.split(self.events, self.blocks, FOLDS["dev_test_block_4"])[0]  # the larger fold, so that enough rows are left after the change
        event = train[40]
        late = copy.deepcopy(train)
        for other in late:
            if other["reaction_session"] < event["reaction_session"]:
                other["available_at"]["day1_close_return"] = event["cutoff"] + timedelta(seconds=1)
        self.assertTrue(feat.history(event, train, self.target))
        self.assertEqual(feat.history(event, late, self.target), [])  # nothing earlier had matured when this event's cutoff passed
        base = mm.Ridge().fit(train, self.target)
        model = mm.Ridge().fit(late, self.target)
        self.assertIn(event["event_id"], model.diagnostics["left_out_event_ids"])  # no history mean, so no default: the row is left out
        self.assertNotIn(event["event_id"], base.diagnostics["left_out_event_ids"])
        self.assertGreater(model.diagnostics["training_rows_without_an_earlier_event"], base.diagnostics["training_rows_without_an_earlier_event"])


class RoundingTests(unittest.TestCase):
    def test_predictions_are_rounded_to_twelve_decimals_and_never_negative_zero(self):
        self.assertEqual(h.rounded(0.1234567890123456), 0.123456789012)
        self.assertEqual(str(h.rounded(-1e-17)), "0.0")
        self.assertEqual(h.rounded((0.12345678901234, -0.5, 1)), (0.123456789012, -0.5, 1.0))
        self.assertEqual(mm.clean(2.0000000000004), 2.0)


if __name__ == "__main__":
    unittest.main()
