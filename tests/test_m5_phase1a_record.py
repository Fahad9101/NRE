"""What Milestone 5 Phase 1a recorded about itself: the owner's go-ahead and how it was read (reports/m5-phase1a-authorization-2026-10-08.json)."""
import json
import unittest
from pathlib import Path

from nre import m5_phase1a_probe as probe
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m5-phase1a-authorization-2026-10-08.json"
RUN1 = ROOT / "reports" / "m5-phase1a-probe-run1-2026-10-08.json"
RUN2 = ROOT / "reports" / "m5-phase1a-probe-run2-2026-10-09.json"
SEC = ROOT / "reports" / "m5-phase1a-sec-availability-2026-10-09.json"
PROPOSAL = ROOT / "docs" / "M5-ADVANCED-MODELS-SCOPE.md"
RATIO_KEYS = {"daily_volume_over_regular_minute_volume", "daily_volume_over_all_hours_minute_volume", "premarket_share_of_all_hours_minute_volume", "after_hours_share_of_all_hours_minute_volume"}
RATIO_KEYS_2 = {"daily_volume_over_regular_and_closing_minute_volume", "daily_volume_over_all_hours_minute_volume", "premarket_share_of_all_hours_minute_volume",
                "closing_minute_share_of_all_hours_minute_volume", "after_hours_share_of_all_hours_minute_volume"}


def leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaves(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from leaves(value, path + (index,))
    else:
        yield path, node


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual([(m["text"], m["at"]) for m in record["owner_messages"]], [("authorize phase 1a", "2026-10-08T16:25:07.994Z")])
        self.assertIn("line 35069", record["owner_messages"][0]["source"])
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_messages"][0]["at"])
        self.assertTrue(replied["text"].startswith("`1e2375b` is on `origin/main`, and CI is green."))
        for phrase in ('say "authorize phase 1a" to start the availability probe', "a small read-only check", "no prices, and nothing would enter the dataset", "This is a recommendation, not an authorization."):
            self.assertIn(phrase, replied["text"])

    def test_the_phase_it_authorizes_is_worded_as_in_the_proposal(self):
        words = self.record["phase_as_proposed"]["words"]
        self.assertIn(words, " ".join(PROPOSAL.read_text(encoding="utf-8").split()))
        self.assertTrue(words.startswith("an availability probe (no acquisition into the dataset)"))
        self.assertEqual(self.record["phase_as_proposed"]["document"], "docs/M5-ADVANCED-MODELS-SCOPE.md")

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("It authorizes Phase 1a of docs/M5-ADVANCED-MODELS-SCOPE.md", "committed before the probe is run", "Nothing is bought", "no event, label, feature or price is added to the dataset or committed",
                       "The words do not carry a push", "It does not authorize 1b, 0, 1c or any later phase", "Disclosure:", "a test checks that its report holds no price or volume value"):
            self.assertIn(phrase, text)

    def test_what_is_authorized_and_what_is_not_is_listed(self):
        record = self.record
        authorized = " ".join(record["authorized_under_these_words"])
        for phrase in ("The probe spec, the probe module, its tests and its GitHub Actions workflow", "once the owner has said \"push\"", "Reading primary-source documentation (Alpaca, SEC, FINRA, CBOE)",
                       "A findings record and a findings document"):
            self.assertIn(phrase, authorized)
        not_authorized = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("Phase 1b, enumerating or collecting any event since 2026-04-01", "Phase 1c, acquiring any derived feature", "Phase 0, pre-registering", "Phase 2", "Phase 3", "Phase 4",
                       "Computing or storing any return, label, feature, price or volume value", "Fetching data from a provider the project has not reviewed", "Any read of a block-5 outcome",
                       "provider-rights-at-scale question", "Pushing without the owner's word", "Declaring Milestone 5 accepted", "Any change to the accepted Milestone 4 work"):
            self.assertIn(phrase, not_authorized)
        self.assertIn("does not change a confirmed default on its own", record["change_rule"])
        self.assertIn("Not a claim that any feature family will be used", " ".join(record["not_a_claim"]))
        self.assertEqual(record["kind"], "m5_phase1a_authorization")


class Run1RecordTests(unittest.TestCase):
    """The first run of the probe (spec revision 1), as recorded from the run's public annotations."""
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RUN1.read_text(encoding="utf-8"))
        cls.report = cls.record["report"]

    def test_the_report_is_the_one_its_digest_names_and_comes_from_the_pushed_run(self):
        self.assertEqual(digest(canonical(self.report)), self.record["report_canonical_sha256"])
        self.assertEqual(self.record["report_canonical_sha256"], "6a91a9d3de304696ff6ca51246e9c6955c4c34c3f1472b46d7031605277b2312")
        self.assertEqual(len(canonical(self.report)), self.record["report_canonical_bytes"])
        run = self.record["run"]
        self.assertEqual((run["run_id"], run["job_id"], run["attempt"], run["event"], run["conclusion"]), (37839340734, 113524435620, 1, "push", "success"))
        self.assertTrue(run["commit"].startswith("3cc9796") and len(run["commit"]) == 40)
        github = self.report["github"]
        self.assertEqual((github["GITHUB_RUN_ID"], github["GITHUB_SHA"], github["GITHUB_WORKFLOW"]), ("37839340734", run["commit"], "M5 Phase 1a availability probe"))
        self.assertEqual((self.report["spec_revision"], self.report["spec_sha256"]), (1, "05b127628b739f839106f86732d15743c8aa1ca4726c5132ae3dfdf79bf11362"))
        self.assertEqual((self.report["complete"], self.report["checks_that_errored"], self.report["requests_made"]), (True, 0, 152))
        self.assertIn("check-runs/113524435620/annotations", self.record["how_it_was_read"])
        self.assertIn("closing-auction cross", " ".join(self.record["known_limits_of_this_run"]))

    def test_it_holds_availability_metadata_and_no_price_or_volume_value(self):
        self.assertFalse(probe.contains_value_keys(self.report))
        floats = [(path, value) for path, value in leaves(self.report) if isinstance(value, float)]
        self.assertTrue(floats)
        for path, value in floats:
            self.assertIn(path[-1], RATIO_KEYS, path)
        self.assertEqual(sorted(self.report["daily_bars"]), sorted(probe.spec_symbols(probe.load_spec())))        # the symbols the spec lists
        self.assertEqual(len(self.report["daily_bars"]), 51)

    def test_the_facts_the_findings_rest_on(self):
        report, daily = self.report, self.report["daily_bars"]
        self.assertEqual((report["window"]["expected_sessions"], report["reference_calendar"]["matches_expected_sessions"]), (754, True))
        full = [s for s, d in daily.items() if d["bars"] == 754 and d["missing_sessions"] == 0 and d["first_bar_date"] == "2023-10-02" and d["has_required_lookback"]]
        self.assertEqual(len(full), 49)
        self.assertEqual({s: (d["first_bar_date"], d["bars"], d["bars_before_first_reaction_session"], d["has_required_lookback"]) for s, d in daily.items() if s not in full},
                         {"KLC": ("2024-10-09", 497, 19, False), "SLSN": ("2025-04-08", 374, 0, False)})
        self.assertTrue(all(d["zero_volume_bars"] == 0 and d["bars_on_unexpected_dates"] == 0 and d["status"] == 200 for d in daily.values()))
        mapping = report["symbol_mapping"]
        self.assertEqual({s for s, m in mapping.items() if m["mapping_changes_the_history"]}, {"TECX"})
        self.assertEqual((mapping["TECX"]["bars_that_only_the_mapping_supplies"], mapping["TECX"]["first_bar_date_without_mapping"]), (181, "2024-06-21"))
        actions = {s: d["by_type"] for s, d in report["corporate_actions"].items() if d["by_type"]}
        self.assertEqual(actions, {"ASMB": {"reverse_splits": 1}, "CXT": {"cash_dividends": 12}, "JBSS": {"cash_dividends": 7}, "NBIX": {"cash_mergers": 1}, "TECX": {"name_changes": 1, "reverse_splits": 1}})
        self.assertTrue(all(d["status"] == 200 and "chunked_by_year_after_400" not in d for d in report["corporate_actions"].values()))
        feeds, modes = report["feeds"], report["adjustment_modes"]
        self.assertEqual({k: v["status"] for k, v in feeds.items()}, {"sip": 200, "iex": 200, "boats": 200, "otc": 403})
        self.assertEqual((feeds["otc"]["message"], feeds["boats"]["bars"]), ("subscription does not permit querying OTC data", 4))
        self.assertEqual(sorted(modes), ["all", "dividend", "raw", "spin-off", "split"])
        self.assertTrue(all(v["status"] == 200 and v["bars"] == 5 for v in modes.values()))

    def test_the_minute_sample_shows_extended_hours_volume_exists_and_the_daily_volume_is_all_hours(self):
        sample = self.report["minute_sample"]
        self.assertEqual(sample["skipped_for_nearness_to_a_candidate_date"], [{"session": "2025-03-12", "symbol": "ACHV"}])
        self.assertEqual(len(sample["pairs"]), 23)
        self.assertTrue(all(p["status"] == 200 and p["daily_bar_present"] for p in sample["pairs"]))
        spy = [p for p in sample["pairs"] if p["symbol"] == "SPY"]
        self.assertEqual(len(spy), 4)
        self.assertTrue(all(p["minute_bars"]["premarket"] > 200 and p["minute_bars"]["after_hours"] > 200 for p in spy))
        self.assertTrue(all(0.9998 <= p["daily_volume_over_all_hours_minute_volume"] <= 1.0002 for p in spy))      # the daily volume equals the all-hours minute volume
        issuers = [p for p in sample["pairs"] if p["symbol"] in ("CACI", "NBIX", "TTWO", "ACHV")]
        self.assertTrue(all(p["minute_bars"]["premarket"] <= 11 for p in issuers))                                    # pre-market minute bars are sparse for these issuers on ordinary days
        self.assertTrue(all(1.0 <= p["daily_volume_over_all_hours_minute_volume"] <= 1.23 for p in issuers))


class Run2RecordTests(unittest.TestCase):
    """The second run of the probe (spec revision 2), as recorded from the run's public annotations."""
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RUN2.read_text(encoding="utf-8"))
        cls.report = cls.record["report"]
        cls.run1 = json.loads(RUN1.read_text(encoding="utf-8"))["report"]

    def test_the_report_is_the_one_its_digest_names_and_comes_from_the_pushed_run(self):
        self.assertEqual(digest(canonical(self.report)), self.record["report_canonical_sha256"])
        self.assertEqual(self.record["report_canonical_sha256"], "e50e904566082ade138af879f4b0542c71f55b1c79800eec76ffcb8df00ed752")
        self.assertEqual(len(canonical(self.report)), self.record["report_canonical_bytes"])
        run = self.record["run"]
        self.assertEqual((run["run_id"], run["job_id"], run["attempt"], run["event"], run["conclusion"]), (37887398952, 113680369835, 1, "push", "success"))
        self.assertTrue(run["commit"].startswith("5a57316") and len(run["commit"]) == 40)
        github = self.report["github"]
        self.assertEqual((github["GITHUB_RUN_ID"], github["GITHUB_SHA"]), ("37887398952", run["commit"]))
        self.assertEqual((self.report["spec_revision"], self.report["spec_sha256"]), (2, "8680f747be5b30d52acecc5bde753135924d15aebffafe2de42bd03894e23aab"))
        self.assertEqual((self.report["complete"], self.report["checks_that_errored"], self.report["requests_made"]), (True, 0, 152))
        self.assertIn("check-runs/113680369835/annotations", self.record["how_it_was_read"])
        self.assertIn("NRE Milestone 1 #240", run["ci_run_for_the_same_commit"])

    def test_the_sections_run_1_also_covered_repeat_exactly_and_the_gap_between_the_runs_is_stated_right(self):
        compared = self.record["compared_with_run_1"]
        self.assertEqual(compared["sections_identical_to_run_1"], ["reference_calendar", "daily_bars", "symbol_mapping", "adjustment_modes", "feeds", "corporate_actions"])
        for name in compared["sections_identical_to_run_1"]:
            self.assertEqual(canonical(self.report[name]), canonical(self.run1[name]), name)
        self.assertEqual((self.run1["retrieved_at"], self.report["retrieved_at"]), ("2026-10-08T20:25:36Z", "2026-10-09T05:11:45Z"))
        self.assertIn("8 hours 46 minutes after run 1", compared["meaning"])                                   # computed from those two timestamps: 31,569 seconds
        self.assertNotIn("32 hours", json.dumps(self.record))

    def test_it_holds_no_price_or_volume_value_only_ratios_and_booleans(self):
        self.assertFalse(probe.contains_value_keys(self.report))
        for path, value in leaves(self.report):
            if isinstance(value, float):
                self.assertIn(path[-1], RATIO_KEYS_2, path)
        self.assertEqual(sorted(self.report["daily_bars"]), sorted(probe.spec_symbols(probe.load_spec())))

    def test_the_minute_sample_with_the_closing_minute_apart_and_the_daily_prices_classified(self):
        pairs = self.report["minute_sample"]["pairs"]
        self.assertEqual(len(pairs), 23)
        self.assertTrue(all(p["minute_bars"]["closing_minute"] == 1 and p["ohlc_semantics"] for p in pairs))

        def tally(field, all_key, regular_key):
            rows = [p["ohlc_semantics"][field] for p in pairs]
            discriminating = [r for r in rows if r["the_two_differ_today"]]
            return (len(discriminating), sum(1 for r in discriminating if r[all_key]), sum(1 for r in discriminating if r[regular_key]))
        self.assertEqual(tally("daily_open", "equals_first_all_hours_bar_open", "equals_first_regular_bar_open"), (18, 0, 17))        # never the first pre-market trade
        self.assertEqual(tally("daily_high", "equals_all_hours_maximum", "equals_regular_maximum"), (9, 1, 8))
        self.assertEqual(tally("daily_low", "equals_all_hours_minimum", "equals_regular_minimum"), (6, 0, 6))
        closes = [p["ohlc_semantics"]["daily_close"] for p in pairs]
        self.assertEqual((sum(1 for c in closes if c["equals_closing_minute_bar"]), sum(1 for c in closes if c["equals_last_bar_of_the_day"])), (17, 6))
        with_after_hours = [p for p in pairs if p["minute_bars"]["after_hours"] > 0]
        self.assertEqual((len(with_after_hours), sum(1 for p in with_after_hours if not p["ohlc_semantics"]["daily_close"]["equals_last_bar_of_the_day"])), (19, 17))
        self.assertEqual(sorted((p["symbol"], p["session"]) for p in pairs if not any(p["ohlc_semantics"]["daily_close"][k] for k in ("equals_last_regular_bar", "equals_closing_minute_bar", "equals_last_bar_of_the_day"))),
                         [("SPY", "2025-03-12"), ("SPY", "2025-06-11"), ("SPY", "2025-09-10"), ("SPY", "2025-12-10"), ("XBI", "2025-06-11"), ("XBI", "2025-09-10")])

    def test_the_volume_ratios_and_the_extended_hours_counts(self):
        pairs = self.report["minute_sample"]["pairs"]
        etfs, issuers = [p for p in pairs if p["symbol"] in ("SPY", "XBI")], [p for p in pairs if p["symbol"] not in ("SPY", "XBI")]
        low_high = lambda ps, key: (min(p[key] for p in ps), max(p[key] for p in ps))        # noqa: E731
        self.assertEqual(low_high(etfs, "daily_volume_over_all_hours_minute_volume"), (1.0, 1.0056))
        self.assertEqual(low_high(issuers, "daily_volume_over_all_hours_minute_volume"), (1.004, 1.2247))
        self.assertEqual([p["daily_volume_over_all_hours_minute_volume"] for p in pairs if p["symbol"] == "SPY"], [1.0002, 1.0001, 1.0002, 1.0])
        self.assertEqual(low_high(issuers, "closing_minute_share_of_all_hours_minute_volume"), (0.0151, 0.4061))
        self.assertEqual([p["minute_bars"]["premarket"] for p in pairs if p["symbol"] == "SPY"], [258, 263, 244, 290])
        self.assertEqual((max(p["minute_bars"]["premarket"] for p in issuers), sum(1 for p in issuers if p["minute_bars"]["premarket"] == 0), len(issuers)), (11, 5, 15))
        self.assertIn("Six symbols on four ordinary Wednesdays", " ".join(self.record["known_limits_of_this_run"]))


class SecRecordTests(unittest.TestCase):
    """The bounded SEC availability check for the 23 issuers: counts, forms and filing dates, never a value."""
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(SEC.read_text(encoding="utf-8"))
        cls.result = cls.record["result"]

    def test_the_result_is_the_one_the_page_digested(self):
        self.assertEqual(digest(canonical(self.result)), "fc7f0bc60a3205766aa4658300066c9fecf690f4ef2b6716990e7c29264542fd")
        self.assertEqual((self.record["result_canonical_sha256"], self.record["result_canonical_bytes"], len(canonical(self.result))), ("fc7f0bc60a3205766aa4658300066c9fecf690f4ef2b6716990e7c29264542fd", 12098, 12098))
        cohort = json.loads((ROOT / "config" / "m2-step3-frozen-issuer-cohort.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted((i["ticker"], i["cik"]) for i in cohort["issuers"]), sorted((t, v["cik"]) for t, v in self.result.items()))
        method = self.record["method"]
        self.assertEqual((method["requests_for_this_result"], method["retrieved_at"], method["window"]), (46, "2026-10-09T05:13:53.660Z", ["2024-10-01", "2026-10-02"]))
        self.assertIn("data.sec.gov supports no cross-origin scripting", method["how"])
        self.assertIn("about 110", method["requests_in_all"])

    def test_no_fact_value_or_period_is_in_the_result(self):
        forbidden = {"val", "value", "end", "accn", "fy", "fp", "frame"}

        def keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from keys(value)
            elif isinstance(node, list):
                for item in node:
                    yield from keys(item)
        self.assertEqual(forbidden & set(keys(self.result)), set())
        self.assertFalse(probe.contains_value_keys(self.result))

    def test_the_summary_is_what_the_result_says_and_the_exceptions_are_the_three_the_findings_name(self):
        summary, result = self.record["summary"], self.result
        shares = {t: next(iter(v["EntityCommonStockSharesOutstanding"].get("units", {}).values()), None) for t, v in result.items()}
        floats = {t: next(iter(v["EntityPublicFloat"].get("units", {}).values()), None) for t, v in result.items()}
        in_window = {t: u["distinct_filing_dates_in_window"] for t, u in shares.items() if u and u["facts"] and u["distinct_filing_dates_in_window"] > 0}
        self.assertEqual(summary["shares_outstanding"]["issuers_with_entity_wide_facts_filed_in_the_window"], sorted(in_window))
        self.assertEqual((len(in_window), min(in_window.values()), max(in_window.values())), (20, 7, 10))
        self.assertEqual(sorted(set(result) - set(in_window)), ["HURN", "JBSS", "OKTA"])
        self.assertEqual(result["HURN"]["EntityCommonStockSharesOutstanding"]["units"]["shares"], {"facts": 0, "unit_entry_was_an_array": False})
        self.assertEqual(result["OKTA"]["EntityCommonStockSharesOutstanding"], {"status": 404})
        self.assertEqual((shares["JBSS"]["facts"], shares["JBSS"]["first_filed"], shares["JBSS"]["last_filed"], shares["JBSS"]["facts_filed_in_window"]), (3, "2011-11-02", "2012-05-01", 0))
        self.assertEqual([t for t, u in shares.items() if u and u["facts"] and not u["a_fact_was_filed_by_2024_11_04"]], ["KLC"])
        self.assertEqual(sorted(summary["shares_outstanding"]["forms_seen"]), ["10-K", "10-K/A", "10-Q", "10-Q/A"])
        self.assertEqual((sum(1 for u in floats.values() if u and u["facts"]), min(u["facts_filed_in_window"] for u in floats.values()), max(u["facts_filed_in_window"] for u in floats.values())), (23, 2, 4))
        self.assertEqual([t for t, u in floats.items() if not u["a_fact_was_filed_by_2024_11_04"]], ["KLC"])
        self.assertEqual(summary["public_float"]["count"], 23)

    def test_the_limits_it_states_include_the_dimensional_gap_and_what_public_float_is(self):
        text = " ".join(self.record["limits"])
        for phrase in ("does not aggregate dimensional facts", "not a share count and not free float", "does not guarantee either"):
            self.assertIn(phrase, text)
        self.assertIn("no value was kept", self.record["what_this_is"])
        self.assertIn("every fact's value", self.record["method"]["not_kept"])


if __name__ == "__main__":
    unittest.main()
