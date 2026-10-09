"""What Milestone 5 Phase 1a found (reports/m5-phase1a-findings-2026-10-09.json) and says in prose (docs/M5-PHASE1A-AVAILABILITY.md), bound to the two probe-run records, the SEC record, the project's own configs and
reports, the master prompt and the committed SEC archive. Every figure is recomputed here from those, not read back from the findings record."""
import datetime
import hashlib
import json
import re
import unittest
from pathlib import Path

from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "reports" / "m5-phase1a-findings-2026-10-09.json"
NOTE = ROOT / "docs" / "M5-PHASE1A-AVAILABILITY.md"
RUN1, RUN2 = ROOT / "reports" / "m5-phase1a-probe-run1-2026-10-08.json", ROOT / "reports" / "m5-phase1a-probe-run2-2026-10-09.json"
SEC = ROOT / "reports" / "m5-phase1a-sec-availability-2026-10-09.json"
AUTHORIZATION = ROOT / "reports" / "m5-phase1a-authorization-2026-10-08.json"
CONFIRMATION = ROOT / "reports" / "m5-scope-confirmation-2026-10-08.json"
SPEC = ROOT / "config" / "m5-phase1a-probe-spec.json"
SECTOR_MAP = ROOT / "config" / "sector-map.json"
MASTER = ROOT / "docs" / "NRE-1.0-MASTER-PROMPT.md"
PROPOSAL = ROOT / "docs" / "M5-ADVANCED-MODELS-SCOPE.md"
TECX_ARCHIVE = ROOT / "archive" / "m2-step2-sec-freeze" / "nre-sec-freeze" / "raw"
WORDS = {1: "one", 3: "three", 5: "five", 7: "seven", 12: "twelve"}
DRUG_SIC = ("2834", "2835", "2836")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def flat(text):
    return " ".join(text.split())


def span(values, digits=4):
    return ("%%.%df" % digits) % min(values), ("%%.%df" % digits) % max(values)


def percent(values):
    return "%.1f" % (100 * min(values)), "%.1f" % (100 * max(values))


def facts():
    """Every figure the findings state, recomputed from the committed records and configs (not from the findings record)."""
    run1, run2, sec_record, spec = load(RUN1), load(RUN2), load(SEC), load(SPEC)
    r1, r2, sec = run1["report"], run2["report"], sec_record["result"]
    daily, mapping, pairs = r2["daily_bars"], r2["symbol_mapping"], r2["minute_sample"]["pairs"]
    issuers = sorted(mapping)
    etfs = sorted(set(daily) - set(issuers))
    have_all = sorted(s for s, d in daily.items() if d["has_required_lookback"])
    spy, xbi = [p for p in pairs if p["symbol"] == "SPY"], [p for p in pairs if p["symbol"] == "XBI"]
    others = [p for p in pairs if p["symbol"] not in ("SPY", "XBI")]
    vol = "daily_volume_over_all_hours_minute_volume"
    shares = {t: next(iter(v["EntityCommonStockSharesOutstanding"].get("units", {}).values()), None) for t, v in sec.items()}
    floats = {t: next(iter(v["EntityPublicFloat"].get("units", {}).values()), None) for t, v in sec.items()}
    in_window = {t: u["distinct_filing_dates_in_window"] for t, u in shares.items() if u and u["facts"] and u["distinct_filing_dates_in_window"]}
    sectors = load(SECTOR_MAP)["issuers"]
    cohort = {i["ticker"]: i["cik"] for i in load(ROOT / "config" / "m2-step3-frozen-issuer-cohort.json")["issuers"]}
    former = json.loads((TECX_ARCHIVE / ("CIK%s.payload" % cohort["TECX"])).read_bytes())["formerNames"]
    stamps = [datetime.datetime.strptime(r["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ") for r in (r1, r2)]
    seconds = int((stamps[1] - stamps[0]).total_seconds())

    def tally(field, a, b):
        rows = [p["ohlc_semantics"][field] for p in pairs if p["ohlc_semantics"][field]["the_two_differ_today"]]
        return len(rows), sum(1 for r in rows if r[a]), sum(1 for r in rows if r[b])

    open_n, open_all, open_reg = tally("daily_open", "equals_first_all_hours_bar_open", "equals_first_regular_bar_open")
    high_n, high_all, high_reg = tally("daily_high", "equals_all_hours_maximum", "equals_regular_maximum")
    low_n, low_all, low_reg = tally("daily_low", "equals_all_hours_minimum", "equals_regular_minimum")
    closes = [p["ohlc_semantics"]["daily_close"] for p in pairs]
    with_after = [p for p in pairs if p["minute_bars"]["after_hours"]]
    first_reaction = spec["window"]["first_reaction_session"]
    neither = lambda o: not (o["equals_first_all_hours_bar_open"] or o["equals_first_regular_bar_open"])           # noqa: E731
    counted = [p for p in pairs if p["ohlc_semantics"]["daily_open"]["the_two_differ_today"] and neither(p["ohlc_semantics"]["daily_open"])]
    uncounted = [p for p in pairs if not p["ohlc_semantics"]["daily_open"]["the_two_differ_today"] and neither(p["ohlc_semantics"]["daily_open"])]
    v = dict(
        NEITHER_SYMBOL=counted[0]["symbol"], NEITHER_DATE=counted[0]["session"], NEITHER2_SYMBOL=uncounted[0]["symbol"], NEITHER2_DATE=uncounted[0]["session"],
        HOURS_FROM=r2["minute_sample"]["hours_new_york"][0], HOURS_TO=r2["minute_sample"]["hours_new_york"][1],
        SYMBOLS=len(daily), ETFS=len(etfs), ISSUERS=len(issuers), WITH_ALL=len(have_all), ISSUERS_FULL=len(set(have_all) & set(issuers)), SESSIONS=r2["window"]["expected_sessions"],
        START=r2["window"]["start"], END=r2["window"]["end"], NEEDED=spec["window"]["lookback_sessions_needed"], FIRST_REACTION=first_reaction,
        OPEN_N=open_n, OPEN_ALL=open_all, OPEN_REG=open_reg, HIGH_N=high_n, HIGH_ALL=high_all, HIGH_REG=high_reg, LOW_N=low_n, LOW_ALL=low_all, LOW_REG=low_reg,
        CLOSE_N=len(pairs), CLOSE_EQ=sum(1 for c in closes if c["equals_closing_minute_bar"]), AH_N=len(with_after),
        AH_DIFF=sum(1 for p in with_after if not p["ohlc_semantics"]["daily_close"]["equals_last_bar_of_the_day"]),
        SPY_PRE_MIN=min(p["minute_bars"]["premarket"] for p in spy), SPY_PRE_MAX=max(p["minute_bars"]["premarket"] for p in spy),
        XBI_PRE_MIN=min(p["minute_bars"]["premarket"] for p in xbi), XBI_PRE_MAX=max(p["minute_bars"]["premarket"] for p in xbi),
        ISS_PRE_MIN=min(p["minute_bars"]["premarket"] for p in others), ISS_PRE_MAX=max(p["minute_bars"]["premarket"] for p in others),
        ISS_ZERO=sum(1 for p in others if p["minute_bars"]["premarket"] == 0), ISS_SESS=len(others),
        TECX_MAP=mapping["TECX"]["bars_that_only_the_mapping_supplies"], TECX_WITH=mapping["TECX"]["bars_with_default_mapping"], TECX_WITHOUT=mapping["TECX"]["bars_without_mapping"],
        TECX_FIRST_WITH=mapping["TECX"]["first_bar_date_with_default_mapping"], TECX_FIRST_WITHOUT=mapping["TECX"]["first_bar_date_without_mapping"],
        TECX_LOOK_WITH=daily["TECX"]["bars_before_first_reaction_session"], TECX_LOOK_WITHOUT=daily["TECX"]["bars_before_first_reaction_session"] - mapping["TECX"]["bars_that_only_the_mapping_supplies"],
        KLC_FIRST=daily["KLC"]["first_bar_date"], KLC_BARS=daily["KLC"]["bars"], KLC_LOOK=daily["KLC"]["bars_before_first_reaction_session"],
        SLSN_FIRST=daily["SLSN"]["first_bar_date"], SLSN_BARS=daily["SLSN"]["bars"],
        SHARES_N=len(in_window), DATES_MIN=min(in_window.values()), DATES_MAX=max(in_window.values()), FLOAT_N=sum(1 for u in floats.values() if u and u["facts"]),
        FLOAT_MIN=min(u["facts_filed_in_window"] for u in floats.values()), FLOAT_MAX=max(u["facts_filed_in_window"] for u in floats.values()),
        SEC_START=sec_record["method"]["window"][0], SEC_END=sec_record["method"]["window"][1], KLC_FACT=shares["KLC"]["first_filed"], FIRST_EVENT_DAY=sec_record["method"]["first_event_day"],
        SEC_REQUESTS=sec_record["method"]["requests_for_this_result"], SEC_REQUESTS_ALL=int(re.search(r"about (\d+)", sec_record["method"]["requests_in_all"]).group(1)), RUN1_ID=run1["run"]["run_id"], RUN1_COMMIT=run1["run"]["commit"][:7], RUN2_ID=run2["run"]["run_id"], RUN2_COMMIT=run2["run"]["commit"][:7],
        GAP="%d hours %d minutes" % (seconds // 3600, seconds % 3600 // 60), REQUESTS=r2["requests_made"], BUDGET=spec["transport"]["request_budget"],
        FORMER_NAMES=" and ".join(sorted({n["name"] for n in former}, reverse=True)), FORMER_UNTIL=sorted({n["to"][:10] for n in former})[0],
        DRUG_N=sum(1 for s in sectors.values() if s["sic"] in DRUG_SIC), OTHERS=len(issuers) - len([s for s, d in r2["corporate_actions"].items() if d["by_type"]]),
        JBSS_FIRST_YEAR=shares["JBSS"]["first_filed"][:4], JBSS_LAST_YEAR=shares["JBSS"]["last_filed"][:4],
    )
    v["SPY_LO"], v["SPY_HI"] = span([p[vol] for p in spy])
    v["XBI_LO"], v["XBI_HI"] = span([p[vol] for p in xbi])
    v["ISS_LO"], v["ISS_HI"] = span([p[vol] for p in others])
    v["SPY_REG_LO"], v["SPY_REG_HI"] = span([p["daily_volume_over_regular_and_closing_minute_volume"] for p in spy])
    v["ISS_EXCESS"] = round((max(p[vol] for p in others) - 1) * 100)
    v["ISS_CLOSE_LO"], v["ISS_CLOSE_HI"] = percent([p["closing_minute_share_of_all_hours_minute_volume"] for p in others])
    v["ETF_CLOSE_LO"], v["ETF_CLOSE_HI"] = percent([p["closing_minute_share_of_all_hours_minute_volume"] for p in spy + xbi])
    return v, dict(run1=run1, run2=run2, sec=sec_record, spec=spec, pairs=pairs, daily=daily, mapping=mapping, issuers=issuers, etfs=etfs, shares=shares, floats=floats, in_window=in_window, cohort=cohort,
                   closes=closes, sectors=sectors)


def master_bullets(number):
    text = MASTER.read_text(encoding="utf-8")
    start = text.index("# %d. " % number)
    body = text[start:text.index("\n---", start)]
    return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]


class FindingsRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = load(FINDINGS)
        cls.v, cls.d = facts()

    def test_it_rests_on_the_records_it_names_and_their_digests(self):
        rest, d = self.record["rests_on"], self.d
        for key, other in (("probe_run_1", d["run1"]), ("probe_run_2", d["run2"])):
            self.assertEqual(load(ROOT / rest[key]["record"]), other)
            self.assertEqual(rest[key]["report_sha256"], other["report_canonical_sha256"])
            self.assertEqual(digest(canonical(other["report"])), rest[key]["report_sha256"])
            self.assertEqual(rest[key]["spec_revision"], other["report"]["spec_revision"])
        self.assertEqual((rest["probe_run_1"]["spec_revision"], rest["probe_run_2"]["spec_revision"]), (1, 2))
        self.assertEqual(load(ROOT / rest["sec_check"]["record"]), d["sec"])
        self.assertEqual(rest["sec_check"]["result_sha256"], d["sec"]["result_canonical_sha256"])
        self.assertEqual(digest(canonical(d["sec"]["result"])), rest["sec_check"]["result_sha256"])
        self.assertEqual(rest["documentation"], [s["id"] for s in self.record["sources"]])
        self.assertEqual((self.record["kind"], self.record["recorded_on"], self.record["authorization"]), ("m5_phase1a_findings", "2026-10-09", "reports/m5-phase1a-authorization-2026-10-08.json"))
        self.assertTrue((ROOT / self.record["authorization"]).is_file())

    def test_the_daily_bar_and_symbol_figures_are_recomputed_from_the_run_records(self):
        v, d, fig = self.v, self.d, self.record["figures"]
        daily = d["daily"]
        self.assertEqual(fig["daily_bars"], {
            "symbols": 51, "etfs": 28, "issuers": 23, "symbols_with_all_sessions_and_the_lookback": 49, "etfs_with_all_sessions": 28, "issuers_with_all_sessions": 21, "sessions": 754, "window": ["2023-10-02", "2026-10-02"],
            "spy_matches_the_expected_calendar": True, "missing_sessions_anywhere": sum(x["missing_sessions"] for x in daily.values()), "zero_volume_bars_anywhere": sum(x["zero_volume_bars"] for x in daily.values()),
            "short_history": {s: {"first_bar_date": x["first_bar_date"], "bars": x["bars"], "sessions_before_the_first_reaction_session": x["bars_before_first_reaction_session"]} for s, x in daily.items() if not x["has_required_lookback"]}})
        self.assertEqual((v["SYMBOLS"], v["ETFS"], v["ISSUERS"], v["WITH_ALL"], v["ISSUERS_FULL"], v["SESSIONS"]), (51, 28, 23, 49, 21, 754))
        self.assertEqual((fig["daily_bars"]["missing_sessions_anywhere"], fig["daily_bars"]["zero_volume_bars_anywhere"]), (0, 0))
        self.assertTrue(all(x["bars"] == 754 and x["first_bar_date"] == "2023-10-02" for s, x in daily.items() if x["has_required_lookback"]))
        self.assertEqual(sorted(fig["daily_bars"]["short_history"]), ["KLC", "SLSN"])
        self.assertTrue(d["run2"]["report"]["reference_calendar"]["matches_expected_sessions"])
        self.assertEqual(sorted(d["etfs"]), sorted(d["spec"]["symbols"]["regime_and_market_etfs"] + d["spec"]["symbols"]["biotech_and_sector_etfs"]))
        self.assertEqual(sorted(d["issuers"]), sorted(d["spec"]["symbols"]["issuers"]))
        self.assertEqual(sorted(d["issuers"]), sorted(d["cohort"]))
        mapping = fig["symbol_mapping"]
        self.assertEqual(mapping["issuers_whose_history_the_mapping_changes"], sorted(s for s, m in d["mapping"].items() if m["mapping_changes_the_history"]))
        self.assertEqual(mapping["issuers_whose_history_the_mapping_changes"], ["TECX"])
        self.assertEqual((mapping["TECX_bars_only_the_mapping_supplies"], mapping["TECX_bars_with_the_mapping"], mapping["TECX_bars_without_the_mapping"]), (181, 754, 573))
        self.assertEqual(mapping["TECX_bars_with_the_mapping"] - mapping["TECX_bars_without_the_mapping"], mapping["TECX_bars_only_the_mapping_supplies"])
        self.assertEqual((mapping["TECX_first_bar_with_the_mapping"], mapping["TECX_first_bar_without_the_mapping"]), ("2023-10-02", "2024-06-21"))
        self.assertEqual((mapping["TECX_sessions_before_the_first_reaction_session_with_the_mapping"], mapping["TECX_sessions_before_the_first_reaction_session_without_the_mapping"]), (276, 95))
        self.assertLess(v["TECX_FIRST_WITHOUT"], v["FIRST_REACTION"])                                  # so every session the mapping adds is before the first reaction session
        self.assertEqual(mapping["TECX_sessions_before_the_first_reaction_session_without_the_mapping"], 276 - 181)
        self.assertEqual(mapping["TECX_former_names_in_the_sec_submissions_cached_for_milestone_2"], "%s, both until %s" % (v["FORMER_NAMES"], v["FORMER_UNTIL"]))

    def test_the_former_names_are_in_the_committed_sec_archive_and_the_archive_is_intact(self):
        cik = self.d["cohort"]["TECX"]
        meta = load(TECX_ARCHIVE / ("CIK%s.json" % cik))
        payload = (TECX_ARCHIVE / ("CIK%s.payload" % cik)).read_bytes()
        self.assertEqual((hashlib.sha256(payload).hexdigest(), len(payload)), (meta["sha256"], meta["size"]))
        data = json.loads(payload)
        self.assertEqual(data["tickers"], ["TECX"])
        self.assertEqual(sorted((n["name"], n["to"][:10]) for n in data["formerNames"]), [("AVROBIO, Inc.", "2024-06-18"), ("AvroBio, Inc.", "2024-06-18")])
        self.assertEqual(self.v["FORMER_NAMES"], "AvroBio, Inc. and AVROBIO, Inc.")

    def test_the_corporate_action_adjustment_feed_and_request_figures_are_recomputed(self):
        fig, rep = self.record["figures"], self.d["run2"]["report"]
        by_type = {s: x["by_type"] for s, x in rep["corporate_actions"].items() if x["by_type"]}
        self.assertEqual(by_type, {"ASMB": {"reverse_splits": 1}, "CXT": {"cash_dividends": 12}, "JBSS": {"cash_dividends": 7}, "NBIX": {"cash_mergers": 1}, "TECX": {"name_changes": 1, "reverse_splits": 1}})
        self.assertEqual(fig["corporate_actions_over_the_window"], {"issuers_with_any": sorted(by_type), "by_type": by_type, "one_call_for_three_years_was_accepted": True})
        self.assertTrue(all(x["status"] == 200 and x["pages"] == 1 and "chunked_by_year_after_400" not in x for x in rep["corporate_actions"].values()))
        self.assertEqual(fig["adjustment_modes_accepted"], ["all", "dividend", "raw", "spin-off", "split"])
        self.assertTrue(all(x["status"] == 200 for x in rep["adjustment_modes"].values()))
        self.assertEqual(fig["feeds"], {"boats": 200, "iex": 200, "otc": 403, "sip": 200})
        self.assertEqual(fig["feeds"], {k: x["status"] for k, x in sorted(rep["feeds"].items())})
        self.assertEqual(fig["feed_messages"], {"otc": rep["feeds"]["otc"]["message"]})
        self.assertEqual((fig["requests_per_run"], fig["request_budget"], fig["hours_between_the_runs"]), ([152, 152], 320, "8 hours 46 minutes"))
        self.assertEqual((self.d["run1"]["report"]["requests_made"], rep["requests_made"], self.v["BUDGET"], self.v["GAP"]), (152, 152, 320, "8 hours 46 minutes"))
        self.assertTrue(all(r["report"]["complete"] and r["report"]["checks_that_errored"] == 0 for r in (self.d["run1"], self.d["run2"])))

    def test_the_daily_price_and_volume_figures_are_recomputed_from_the_minute_sample(self):
        v, fig, pairs = self.v, self.record["figures"], self.d["pairs"]
        prices = fig["daily_bar_prices"]
        self.assertEqual({k: prices["open"][k] for k in ("sessions_that_can_tell_the_two_apart", "equal_to_the_all_hours_value", "equal_to_the_regular_session_value")},
                         {"sessions_that_can_tell_the_two_apart": v["OPEN_N"], "equal_to_the_all_hours_value": v["OPEN_ALL"], "equal_to_the_regular_session_value": v["OPEN_REG"]})
        self.assertEqual({k: prices["high"][k] for k in ("sessions_that_can_tell_the_two_apart", "equal_to_the_all_hours_value", "equal_to_the_regular_session_value")},
                         {"sessions_that_can_tell_the_two_apart": v["HIGH_N"], "equal_to_the_all_hours_value": v["HIGH_ALL"], "equal_to_the_regular_session_value": v["HIGH_REG"]})
        self.assertEqual(prices["low"], {"sessions_that_can_tell_the_two_apart": v["LOW_N"], "equal_to_the_all_hours_value": v["LOW_ALL"], "equal_to_the_regular_session_value": v["LOW_REG"]})
        self.assertEqual([(v["OPEN_N"], v["OPEN_ALL"], v["OPEN_REG"]), (v["HIGH_N"], v["HIGH_ALL"], v["HIGH_REG"]), (v["LOW_N"], v["LOW_ALL"], v["LOW_REG"])], [(18, 0, 17), (9, 1, 8), (6, 0, 6)])
        by_session = {(p["symbol"], p["session"]): p for p in pairs}
        neither = lambda o: not (o["equals_first_all_hours_bar_open"] or o["equals_first_regular_bar_open"])           # noqa: E731
        self.assertEqual(prices["open"]["matched_neither"], [list(k) for k, p in sorted(by_session.items()) if p["ohlc_semantics"]["daily_open"]["the_two_differ_today"] and neither(p["ohlc_semantics"]["daily_open"])])
        self.assertEqual(prices["open"]["matched_neither_but_cannot_discriminate"], [list(k) for k, p in sorted(by_session.items()) if not p["ohlc_semantics"]["daily_open"]["the_two_differ_today"] and neither(p["ohlc_semantics"]["daily_open"])])
        self.assertEqual((prices["open"]["matched_neither"], prices["open"]["matched_neither_but_cannot_discriminate"]), ([["SPY", "2025-09-10"]], [["NBIX", "2025-09-10"]]))
        exception = prices["high"]["the_all_hours_exception"]
        bars = by_session[(exception["symbol"], exception["session"])]
        self.assertEqual((exception["symbol"], exception["session"]), ("CACI", "2025-06-11"))
        self.assertEqual((bars["minute_bars"]["premarket"], bars["minute_bars"]["after_hours"], bars["minute_bars"]["closing_minute"]), (exception["premarket_minute_bars"], exception["after_hours_minute_bars"], exception["closing_minute_bars"]))
        self.assertEqual((exception["premarket_minute_bars"], exception["after_hours_minute_bars"], exception["closing_minute_bars"]), (0, 0, 1))
        high = bars["ohlc_semantics"]["daily_high"]
        self.assertEqual((high["equals_all_hours_maximum"], high["equals_regular_maximum"], high["the_two_differ_today"]), (True, False, True))
        self.assertEqual([k for k, p in by_session.items() if p["ohlc_semantics"]["daily_high"]["the_two_differ_today"] and p["ohlc_semantics"]["daily_high"]["equals_all_hours_maximum"]], [("CACI", "2025-06-11")])
        none_of_three = sorted(list(k) for k, p in by_session.items() if not any(p["ohlc_semantics"]["daily_close"][name] for name in ("equals_last_regular_bar", "equals_closing_minute_bar", "equals_last_bar_of_the_day")))
        self.assertEqual(prices["close"], {"sessions": v["CLOSE_N"], "equal_to_the_closing_minute_bars_close": v["CLOSE_EQ"], "sessions_with_after_hours_bars": v["AH_N"],
                                           "of_those_where_the_close_is_not_the_last_after_hours_trade": v["AH_DIFF"], "equal_to_none_of_the_three_minute_closes": none_of_three})
        self.assertEqual((v["CLOSE_N"], v["CLOSE_EQ"], v["AH_N"], v["AH_DIFF"], len(none_of_three), v["CLOSE_N"] - v["CLOSE_EQ"]), (23, 17, 19, 17, 6, 6))
        self.assertEqual(none_of_three, [["SPY", "2025-03-12"], ["SPY", "2025-06-11"], ["SPY", "2025-09-10"], ["SPY", "2025-12-10"], ["XBI", "2025-06-11"], ["XBI", "2025-09-10"]])
        self.assertEqual(sorted(k for k, p in by_session.items() if not p["ohlc_semantics"]["daily_close"]["equals_closing_minute_bar"]), [tuple(x) for x in none_of_three])          # the six are exactly those
        volume = fig["daily_bar_volume"]
        vol = "daily_volume_over_all_hours_minute_volume"
        spy, xbi = [p for p in pairs if p["symbol"] == "SPY"], [p for p in pairs if p["symbol"] == "XBI"]
        others = [p for p in pairs if p["symbol"] not in ("SPY", "XBI")]
        self.assertEqual(volume["spy_over_the_all_hours_minute_volume"], [p[vol] for p in spy])
        self.assertEqual(volume["xbi_over_the_all_hours_minute_volume"], [min(p[vol] for p in xbi), max(p[vol] for p in xbi)])
        self.assertEqual(volume["etfs_over_the_all_hours_minute_volume"], [min(p[vol] for p in spy + xbi), max(p[vol] for p in spy + xbi)])
        self.assertEqual(volume["issuers_over_the_all_hours_minute_volume"], [min(p[vol] for p in others), max(p[vol] for p in others)])
        regular = "daily_volume_over_regular_and_closing_minute_volume"
        self.assertEqual(volume["spy_over_the_regular_and_closing_minute_volume"], [min(p[regular] for p in spy), max(p[regular] for p in spy)])
        share = "closing_minute_share_of_all_hours_minute_volume"
        self.assertEqual(volume["issuers_closing_minute_share_of_the_all_hours_minute_volume"], [min(p[share] for p in others), max(p[share] for p in others)])
        self.assertEqual(volume["etfs_closing_minute_share"], [min(p[share] for p in spy + xbi), max(p[share] for p in spy + xbi)])
        self.assertEqual((volume["spy_over_the_all_hours_minute_volume"], volume["xbi_over_the_all_hours_minute_volume"], volume["issuers_over_the_all_hours_minute_volume"], volume["spy_over_the_regular_and_closing_minute_volume"]),
                         ([1.0002, 1.0001, 1.0002, 1.0], [1.0001, 1.0056], [1.004, 1.2247], [1.1032, 1.1903]))
        extended = fig["extended_hours"]
        self.assertEqual(extended["spy_premarket_minute_bars"], [p["minute_bars"]["premarket"] for p in spy])
        self.assertEqual(extended["xbi_premarket_minute_bars"], [p["minute_bars"]["premarket"] for p in xbi])
        self.assertEqual(extended["issuer_premarket_minute_bars_range"], [min(p["minute_bars"]["premarket"] for p in others), max(p["minute_bars"]["premarket"] for p in others)])
        self.assertEqual((extended["spy_premarket_minute_bars"], extended["xbi_premarket_minute_bars"], extended["issuer_premarket_minute_bars_range"]), ([258, 263, 244, 290], [40, 33, 80, 28], [0, 11]))
        self.assertEqual((extended["issuer_sessions_sampled"], extended["issuer_sessions_with_no_premarket_bar"], extended["sessions_sampled"]), (v["ISS_SESS"], v["ISS_ZERO"], 23))
        self.assertEqual((v["ISS_SESS"], v["ISS_ZERO"]), (15, 5))
        self.assertEqual(extended["skipped_by_the_guard"], [{"session": "2025-03-12", "symbol": "ACHV"}])
        self.assertEqual(extended["skipped_by_the_guard"], self.d["run2"]["report"]["minute_sample"]["skipped_for_nearness_to_a_candidate_date"])

    def test_the_minute_sample_is_what_the_document_says_it_is(self):
        pairs = self.d["pairs"]
        self.assertEqual(sorted({p["symbol"] for p in pairs}), ["ACHV", "CACI", "NBIX", "SPY", "TTWO", "XBI"])
        sessions = sorted({p["session"] for p in pairs})
        self.assertEqual(sessions, ["2025-03-12", "2025-06-11", "2025-09-10", "2025-12-10"])
        self.assertEqual([datetime.date.fromisoformat(s).weekday() for s in sessions], [2, 2, 2, 2])                            # Wednesdays
        self.assertEqual(len(pairs), 6 * 4 - 1)                                                                                  # the guard skipped one
        self.assertEqual(self.d["spec"]["event_day_guard"]["exclude_within_calendar_days"], 5)
        self.assertEqual(self.d["run2"]["report"]["minute_sample"]["hours_new_york"], ["04:00", "20:00"])

    def test_the_sec_and_sector_figures_are_recomputed(self):
        v, fig, d = self.v, self.record["figures"], self.d
        sec = fig["sec"]
        self.assertEqual(sec["shares_outstanding_issuers_with_entity_wide_facts_in_the_window"], len(d["in_window"]))
        self.assertEqual(sorted(set(d["issuers"]) - set(d["in_window"])), ["HURN", "JBSS", "OKTA"])
        self.assertEqual(sec["distinct_filing_dates_in_the_window"], [v["DATES_MIN"], v["DATES_MAX"]])
        self.assertEqual((v["SHARES_N"], v["DATES_MIN"], v["DATES_MAX"], v["FLOAT_N"], v["FLOAT_MIN"], v["FLOAT_MAX"]), (20, 7, 10, 23, 2, 4))
        self.assertEqual((sec["public_float_issuers_with_facts"], sec["public_float_facts_in_the_window"]), (v["FLOAT_N"], [v["FLOAT_MIN"], v["FLOAT_MAX"]]))
        self.assertEqual(sec["issuers_with_no_fact_filed_by_2024_11_04"], sorted(t for t, u in d["shares"].items() if u and u["facts"] and not u["a_fact_was_filed_by_2024_11_04"]))
        self.assertEqual(sec["issuers_with_no_fact_filed_by_2024_11_04"], ["KLC"])
        self.assertEqual((sec["KLC_first_shares_fact_filed"], sec["first_event_day"]), (v["KLC_FACT"], v["FIRST_EVENT_DAY"]))
        self.assertEqual((v["KLC_FACT"], v["FIRST_EVENT_DAY"]), ("2024-11-21", "2024-11-04"))
        self.assertGreater(v["KLC_FACT"], v["FIRST_EVENT_DAY"])
        self.assertEqual(d["sec"]["result"]["OKTA"]["EntityCommonStockSharesOutstanding"], {"status": 404})
        self.assertEqual(d["shares"]["HURN"], {"facts": 0, "unit_entry_was_an_array": False})
        self.assertEqual((d["shares"]["JBSS"]["facts"], v["JBSS_FIRST_YEAR"], v["JBSS_LAST_YEAR"], d["shares"]["JBSS"]["facts_filed_in_window"]), (3, "2011", "2012", 0))
        self.assertEqual(sec["shares_outstanding_issuers_without"], {"HURN": "no facts", "JBSS": "3 facts, 2011 to 2012", "OKTA": "404"})
        total = sum(sum(u["forms"].values()) for u in d["floats"].values())
        quarterly = sum(u["forms"].get("10-Q", 0) for u in d["floats"].values())
        self.assertEqual((total, quarterly), (291, 13))
        self.assertLess(quarterly / total, 0.05)                                                                               # public float is almost always an annual-report fact
        sector = fig["sector"]
        self.assertEqual(sector["sic_codes_counted_as_drug_related"], list(DRUG_SIC))
        self.assertEqual(sector["issuers_with_such_a_code"], sorted(s["ticker"] for s in d["sectors"].values() if s["sic"] in DRUG_SIC))
        self.assertEqual((sector["issuers_with_such_a_code"], v["DRUG_N"]), (["ACHV", "ASMB", "COLL", "NBIX", "TECX"], 5))
        self.assertEqual(sorted(s["ticker"] for s in d["sectors"].values()), d["issuers"])
        self.assertIn("not point-in-time", sector["source"])

    def test_the_field_rows_cover_the_master_prompts_lists_and_use_the_six_status_words(self):
        rec = self.record
        self.assertEqual(rec["status_labels"], {"in_hand_alpaca": "in hand (Alpaca)", "derived": "derivable", "sec_filings": "SEC filings", "unreviewed_provider": "unreviewed provider",
                                               "proxy_only": "proxy only", "not_found": "not found"})
        self.assertTrue(all(f["status"] in rec["status_labels"] for f in rec["fields"]))
        self.assertEqual(len(rec["fields"]), 16)
        aliases = {"implied volatility where feasible": "implied volatility", "call/put activity where feasible": "call/put activity", "gamma-related variables only if sufficiently reliable": "gamma-related variables",
                   "resistance zones": "support and resistance zones", "support zones": "support and resistance zones", "relative volume": "relative volume (daily)",
                   "recent biotech momentum where applicable": "recent biotech momentum"}
        names = {name: f["master_prompt_section"] for f in rec["fields"] for name in f["fields"]}
        self.assertEqual(len(names), sum(len(f["fields"]) for f in rec["fields"]))                                   # no field named twice
        for number in (10, 11):
            bullets = master_bullets(number)
            self.assertGreaterEqual(len(bullets), 9)
            for bullet in bullets:
                with self.subTest(section=number, bullet=bullet):
                    name = aliases.get(bullet, bullet)
                    self.assertEqual(names.get(name), number)
        covered = {aliases.get(b, b) for n in (10, 11) for b in master_bullets(n)}
        self.assertEqual(set(names) - covered, {"relative volume (intraday)"})                                      # the one row the master prompt does not list: the split of relative volume
        self.assertEqual((len(master_bullets(10)), len(master_bullets(11))), (24, 9))
        statuses = {f["fields"][0]: f["status"] for f in rec["fields"]}
        self.assertEqual({s for s in statuses.values()}, set(rec["status_labels"]))                                   # every status word is used by some row

    def test_the_numeric_evidence_in_the_field_rows_is_the_recomputed_figures(self):
        v, d = self.v, self.d
        row = {f["fields"][0]: f["evidence"] for f in self.record["fields"]}
        issuers_without = ", ".join(["HURN", "JBSS"]) + " and OKTA"
        self.assertEqual(sorted(set(d["issuers"]) - set(d["in_window"])), ["HURN", "JBSS", "OKTA"])
        self.assertEqual(row["market capitalization"], "shares-outstanding facts exist for %d of %d issuers; %s have no entity-wide fact in the window" % (v["SHARES_N"], v["ISSUERS"], issuers_without))
        self.assertEqual(row["float"], "public-float facts exist for %d of %d issuers, %d to %d filed in the window; the value is a dollar amount, not a share count" % (v["FLOAT_N"], v["ISSUERS"], v["FLOAT_MIN"], v["FLOAT_MAX"]))
        self.assertEqual(row["shares outstanding"], "%d of %d issuers, with %d to %d filing dates in the window; KLC's first fact was filed on %s, after the first event day, %s" % (
            v["SHARES_N"], v["ISSUERS"], v["DATES_MIN"], v["DATES_MAX"], v["KLC_FACT"], v["FIRST_EVENT_DAY"]))
        self.assertEqual(row["average daily dollar volume"], "%d of %d symbols have all %d sessions; the daily volume is %s to %s of SPY's all-hours minute volume and up to %s of an issuer's" % (
            v["WITH_ALL"], v["SYMBOLS"], v["SESSIONS"], v["SPY_LO"], v["SPY_HI"], v["ISS_HI"]))
        self.assertEqual(row["premarket volume"], "SPY has %d to %d pre-market minute bars a session and XBI %d to %d; the four sampled issuers %d to %d, with none in %d of %d issuer sessions" % (
            v["SPY_PRE_MIN"], v["SPY_PRE_MAX"], v["XBI_PRE_MIN"], v["XBI_PRE_MAX"], v["ISS_PRE_MIN"], v["ISS_PRE_MAX"], v["ISS_ZERO"], v["ISS_SESS"]))
        self.assertEqual(row["ATR"], "%d of %d symbols have all %d sessions with no gap; %d of the %d issuers have a corporate action in the window" % (
            v["WITH_ALL"], v["SYMBOLS"], v["SESSIONS"], v["ISSUERS"] - v["OTHERS"], v["ISSUERS"]))
        self.assertEqual(row["distance from 52-week high/low"], "all %d ETFs and %d of %d issuers have them; KLC has %d sessions and SLSN none before the first reaction session; "
                         "TECX has them only through the symbol mapping (%d of its sessions are under the former name)" % (v["ETFS"], v["ISSUERS_FULL"], v["ISSUERS"], v["KLC_LOOK"], v["TECX_MAP"]))
        self.assertEqual(row["SPY trend"], "%d sessions each, no gap" % v["SESSIONS"])
        self.assertEqual(row["VIX"], "VIXY and VXX have %d sessions each; the Cboe page was read, no data fetched" % v["SESSIONS"])
        self.assertEqual(row["sector ETF behavior"], "%d sessions each; %d of the %d issuers carry a drug-related SIC code (2834, 2835 or 2836), so recent biotech momentum applies to a minority of them; "
                         "SIC is coarse and not point-in-time" % (v["SESSIONS"], v["DRUG_N"], v["ISSUERS"]))
        self.assertEqual(row["breadth"], "RSP has %d sessions" % v["SESSIONS"])
        self.assertEqual(row["risk-on/risk-off environment"], "%d sessions each" % v["SESSIONS"])
        spec_symbols = d["spec"]["symbols"]
        named = {"SPY", "QQQ", "IWM", "IJR", "VIXY", "VXX", "RSP", "TLT", "HYG", "LQD", "GLD", "UUP", "XBI", "IBB"}            # the symbols the rows name
        self.assertTrue(named <= set(d["etfs"]))
        self.assertTrue(all(d["daily"][s]["bars"] == 754 and d["daily"][s]["missing_sessions"] == 0 for s in named))
        sector_etfs = [s for s in spec_symbols["biotech_and_sector_etfs"] if s not in ("XBI", "IBB")]
        self.assertEqual(len(sector_etfs), 13)
        self.assertTrue(all(d["daily"][s]["bars"] == 754 for s in sector_etfs))
        self.assertEqual(sorted(spec_symbols["regime_and_market_etfs"]), sorted(["SPY", "QQQ", "IWM", "DIA", "RSP", "IJR", "VIXY", "VXX", "TLT", "HYG", "LQD", "GLD", "UUP"]))

    def test_the_documentation_ranges_in_the_rows_and_the_sources_agree(self):
        rows = {f["fields"][0]: f for f in self.record["fields"]}
        sources = {s["id"]: s for s in self.record["sources"]}
        for field, source, sizes in (("institutional ownership", "sec-13f-data-sets", ("69.66", "96.05")), ("insider ownership", "sec-insider-data-sets", ("7.59", "13.23"))):
            self.assertIn("%s to %s MB" % sizes, rows[field]["evidence"])
            self.assertIn("%s to %s MB" % sizes, sources[source]["says"])
        self.assertIn("7th business day", rows["short interest"]["source_and_timing"])
        self.assertIn("7th business day", sources["finra-short-interest"]["says"])
        self.assertIn("Revision Flag", sources["finra-short-interest"]["says"])

    def test_sources_are_listed_with_dates_and_only_three_sentences_are_quoted(self):
        sources = self.record["sources"]
        self.assertEqual([s["id"] for s in sources], ["alpaca-bars", "alpaca-corporate-actions", "alpaca-option-bars", "sec-edgar-apis", "sec-webmaster-faq", "sec-13f-data-sets", "sec-insider-data-sets",
                                                       "finra-short-interest", "cboe-vix-history", "project-alpaca-access-notes", "m1-provider-rights-review"])
        for s in sources:
            with self.subTest(source=s["id"]):
                self.assertIn(s["read_on"], ("2026-10-08", "2026-10-09"))
                self.assertTrue(s["name"] and s["says"].endswith("."))
                if s["url"].startswith("http"):
                    self.assertTrue(s["url"].startswith("https://"))
                else:
                    self.assertTrue((ROOT / s["url"]).is_file())
        quoted = [(s["id"], words) for s in sources for words in s["verbatim"]]
        self.assertEqual(quoted, [("alpaca-bars", "The special value of \"-\" means symbol mapping is skipped."),
                                  ("alpaca-corporate-actions", "Currently Alpaca has no guarantees on the creation time of corporate actions."),
                                  ("finra-short-interest", "Only the most recent data is made available.")])
        self.assertTrue(all(len(words.split()) >= 7 for _, words in quoted))
        self.assertEqual(len({words for _, words in quoted}), 3)

    def test_the_flags_the_decisions_and_the_limits(self):
        rec, v = self.record, self.v
        self.assertEqual([f["id"] for f in rec["flags_for_the_owner"]], list("ABCDEF"))
        self.assertTrue(all(f["title"] and f["text"] and not f["title"].endswith(".") for f in rec["flags_for_the_owner"]))
        confirmation = load(CONFIRMATION)
        decisions = {d["number"]: d for d in confirmation["decisions"]}
        self.assertEqual(rec["decisions"]["changed"], [])
        self.assertEqual(rec["decisions"]["touched"], ["decision 6 (flag A)", "decision 2 (flag F: the provider-rights-at-scale question is put to the owner before 1b or 1c)"])
        self.assertIn("never changed by the assistant alone", rec["decisions"]["rule"])
        self.assertIn("it does not change a confirmed default on its own", confirmation["change_rule"])
        six = decisions[6]
        self.assertIn("float, short interest, institutional ownership, options and premarket volume out of reach unless a point-in-time source is found", six["recommended_default"])
        self.assertIn("no new provider is chosen", six["effect"])
        self.assertIn("put to the owner again before 1b or 1c", decisions[2]["still_needed_before_it_takes_effect"])
        self.assertIn("is put to the owner again before 1b or 1c", flat(PROPOSAL.read_text(encoding="utf-8")))
        flags = {f["id"]: f["text"] for f in rec["flags_for_the_owner"]}
        self.assertIn("Decision 6 says to declare float, short interest, institutional ownership, options and premarket volume out of reach unless a point-in-time source is found", flags["A"])
        self.assertIn("decision 6 says no new provider is chosen", flags["A"])
        self.assertIn("KLC (%d sessions before the first reaction session) and SLSN (none)" % v["KLC_LOOK"], flags["C"])
        self.assertIn("TECX reaches %d sessions only through Alpaca's default symbol mapping, which adds %d sessions from before %s" % (v["TECX_LOOK_WITH"], v["TECX_MAP"], v["TECX_FIRST_WITHOUT"]), flags["C"])
        self.assertIn("Without the mapping TECX has %d sessions before the first reaction session" % v["TECX_LOOK_WITHOUT"], flags["C"])
        self.assertIn("%s until %s" % (v["FORMER_NAMES"], v["FORMER_UNTIL"]), flags["C"])
        self.assertIn("KLC's first fact was filed on %s, after the first event day, %s" % (v["KLC_FACT"], v["FIRST_EVENT_DAY"]), flags["D"])
        self.assertIn("JBSS's last fact was filed in %s" % v["JBSS_LAST_YEAR"], flags["D"])
        self.assertIn("a day's volume is complete only after 20:00 ET", flags["B"])
        limits = rec["limits"]
        self.assertEqual(len(limits), 9)
        self.assertIn("it made %d requests for the result kept and about %d in all" % (v["SEC_REQUESTS"], v["SEC_REQUESTS_ALL"]), limits[4])
        self.assertIn("so it sent the browser's own user agent, not a declared one as the SEC's guidance asks", limits[4])
        self.assertIn("at about 3 a second against the SEC's stated maximum of 10", limits[4])
        method = self.d["sec"]["method"]["how"]
        self.assertIn("A page script cannot set a user agent, so the browser sent its own.", method)
        self.assertIn("(about 3 a second; the SEC's stated maximum is 10 a second)", method)
        self.assertIn("data.sec.gov supports no cross-origin scripting", method)
        self.assertIn("with a declared user agent", {s["id"]: s["says"] for s in rec["sources"]}["sec-webmaster-faq"])
        self.assertIn("%s apart" % v["GAP"], limits[0])
        self.assertIn("%d sessions after the guard skipped one" % v["CLOSE_N"], limits[1])
        self.assertIn("the high and low rest on %d and %d sessions" % (v["HIGH_N"], v["LOW_N"]), limits[1])
        self.assertEqual(rec["not_done"], ["no event, label, feature, price or volume was added to the dataset", "no later phase was started (1b, 0, 1c, 2, 3, 4)", "no data was fetched from FINRA or Cboe and nothing was bought",
                                           "no block-5 outcome was read", "the provider-rights-at-scale question was not answered", "none of the six decisions was changed"])

    def test_the_record_holds_no_price_or_volume_value(self):
        floats = []

        def walk(node, path=()):
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertNotIn(key, ("o", "h", "l", "c", "v", "vw", "n", "price", "vwap", "volume"), path + (key,))
                    walk(value, path + (key,))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, path + (index,))
            elif isinstance(node, float):
                floats.append((path, node))
        walk(self.record)
        self.assertTrue(floats)
        for path, value in floats:
            self.assertEqual(path[:2], ("figures", "daily_bar_volume"), path)                                       # the only floats are the unit-free ratios and shares of the volume comparison
            self.assertTrue(0.0 < value <= 1.25, (path, value))


class FindingsDocumentTests(unittest.TestCase):
    """The document is the record in prose: its tables and lists are the record's, and each sentence that uses a figure uses the recomputed one."""
    @classmethod
    def setUpClass(cls):
        cls.text = NOTE.read_text(encoding="utf-8")
        cls.flat = flat(cls.text)
        cls.record = load(FINDINGS)
        cls.v, cls.d = facts()

    def test_it_is_assembled_from_the_record_with_nothing_left_over(self):
        text, rec = self.text, self.record
        self.assertNotIn("{{", text)
        self.assertNotIn("}}", text)
        labels = rec["status_labels"]
        lines = ["| Fields | Master prompt section | Status | Source and timing | What the probe found |", "| --- | --- | --- | --- | --- |"]
        lines += ["| " + " | ".join(["; ".join(f["fields"]), str(f["master_prompt_section"]), labels[f["status"]], f["source_and_timing"], f["evidence"]]) + " |" for f in rec["fields"]]
        self.assertIn("\n".join(lines) + "\n", text)
        prices = rec["figures"]["daily_bar_prices"]
        table = ["| Daily value | Sessions that can tell the two apart | Equal to the all-hours value | Equal to the regular-session value |", "| --- | --- | --- | --- |"]
        table += ["| %s | %d | %d | %d |" % (name, prices[name]["sessions_that_can_tell_the_two_apart"], prices[name]["equal_to_the_all_hours_value"], prices[name]["equal_to_the_regular_session_value"])
                  for name in ("open", "high", "low")]
        self.assertIn("\n".join(table) + "\n", text)
        self.assertIn("\n".join("- **%s. %s.** %s" % (f["id"], f["title"], f["text"]) for f in rec["flags_for_the_owner"]) + "\n", text)
        self.assertIn("\n".join("- " + limit for limit in rec["limits"]) + "\n", text)
        for source in rec["sources"]:
            with self.subTest(source=source["id"]):
                where = "[%s](%s)" % (source["name"], source["url"]) if source["url"].startswith("http") else "%s (`%s`)" % (source["name"], source["url"])
                line = "- %s, read on %s. %s" % (where, source["read_on"], source["says"])
                if source["verbatim"]:
                    line += " Quoted verbatim: " + "; ".join("`%s`" % words for words in source["verbatim"])
                self.assertIn(line + "\n", text)
        headings = re.findall(r"^## (.+)$", text, re.M)
        self.assertEqual(headings, ["Summary", "1. What was done", "2. The fields, from where, and with what caveats", "3. What the daily bar is", "4. Identity, history and corporate actions",
                                    "5. Sources other than Alpaca", "6. What this touches in the decisions", "7. Sources read", "8. Limits", "9. What this document does not do"])

    def test_each_sentence_that_uses_a_figure_uses_the_recomputed_figure(self):
        """A figure that is right in a table but wrong in the prose would pass an 'appears somewhere' check, so each sentence is checked whole."""
        v = dict(self.v)
        sentences = [
            "{WITH_ALL} of the {SYMBOLS} symbols (all {ETFS} ETFs and {ISSUERS_FULL} of the {ISSUERS} issuers) have all {SESSIONS} sessions from {START} to {END}, with no gap after a symbol's first bar and no zero-volume bar "
            "in any of the {SYMBOLS} series, and SPY's series equals the expected trading calendar exactly",
            "The daily open was never the first pre-market trade ({OPEN_ALL} of the {OPEN_N} sessions that could tell them apart), and the daily volume was {SPY_LO} to {SPY_HI} of SPY's all-hours minute volume "
            "but {SPY_REG_LO} to {SPY_REG_HI} of its minute volume through the closing minute",
            "plentiful for the ETFs (SPY has {SPY_PRE_MIN} to {SPY_PRE_MAX} pre-market minute bars a session) and sparse for the issuers ({ISS_PRE_MIN} to {ISS_PRE_MAX}, and none at all in {ISS_ZERO} of {ISS_SESS} sampled issuer sessions)",
            "KLC and SLSN cannot supply the {NEEDED} sessions an annual high or low needs, and TECX reaches them only through a symbol mapping that adds {TECX_MAP} sessions from before {TECX_FIRST_WITHOUT}, under its former name",
            "shares outstanding exist as entity-wide facts for {SHARES_N} of the {ISSUERS} issuers and public float for {FLOAT_N} of {ISSUERS} (from annual reports)",
            "{SYMBOLS} symbols ({ETFS} ETFs and the {ISSUERS} issuers) over {START} to {END}",
            "**Run 1** (spec revision 1, run {RUN1_ID} on commit {RUN1_COMMIT})", "**Run 2** (revision 2, run {RUN2_ID} on commit {RUN2_COMMIT})",
            "are identical to run 1's, {GAP} later. Each run made {REQUESTS} requests (the budget was {BUDGET}), and neither had a failed check.",
            "for each of the {ISSUERS} issuers ({SEC_REQUESTS} requests for the result kept and about {SEC_REQUESTS_ALL} in all, 300 ms apart; see section 8)",
            "On {CLOSE_N} ordinary sessions of six symbols (SPY, XBI, CACI, NBIX, TTWO and ACHV, on four Wednesdays in 2025)",
            "the daily open never equalled the first pre-market trade's (0 of {OPEN_N}) and the daily low never equalled the all-hours low (0 of {LOW_N}). Among the {OPEN_N} sessions in the table, the one open that matched neither "
            "candidate was {NEITHER_SYMBOL} on {NEITHER_DATE}, probably the opening-auction price (not checked); {NEITHER2_SYMBOL} on the same date also matched neither, but there the two candidates are the same bar, so it is "
            "not in the table.",
            "the probe compared each daily bar with the same provider's minute bars from {HOURS_FROM} to {HOURS_TO} ET", "A day's volume is complete only after {HOURS_TO} ET (flag B).",
            "it adds no request, symbol or session, and its stated basis is run 1's availability results only",
            "**High:** {HIGH_REG} of {HIGH_N} equal the regular-session maximum. The exception (CACI, 2025-06-11) had no pre-market or after-hours bar",
            "the daily close equals the close of the 16:00 minute bar in {CLOSE_EQ} of the {CLOSE_N} sessions. In the other {CLOSE_OTHER} (SPY on all four, XBI on 2025-06-11 and 2025-09-10) it equals none of the three minute closes tested",
            "Of the {AH_N} sessions with after-hours bars, {AH_DIFF} have a daily close that differs from the last after-hours trade.",
            "the daily bar's volume was {SPY_LO} to {SPY_HI} of SPY's all-hours minute volume ({XBI_LO} to {XBI_HI} of XBI's, and {ISS_LO} to {ISS_HI} of the four issuers'), but {SPY_REG_LO} to {SPY_REG_HI} of SPY's minute volume "
            "through the 16:00 minute.",
            "it exceeds the all-hours minute sums by up to about {ISS_EXCESS}%",
            "The 16:00 minute carries {ISS_CLOSE_LO}% to {ISS_CLOSE_HI}% of an issuer's all-hours minute volume and {ETF_CLOSE_LO}% to {ETF_CLOSE_HI}% of SPY's and XBI's.",
            "**KLC** has its first bar on {KLC_FIRST} ({KLC_BARS} sessions, {KLC_LOOK} of them before the first reaction session, {FIRST_REACTION})", "its first shares-outstanding fact was filed on {KLC_FACT}.",
            "**SLSN** has its first bar on {SLSN_FIRST} ({SLSN_BARS} sessions, none before the first reaction session), with or without the symbol mapping.",
            "**TECX** has {TECX_WITH} bars from {TECX_FIRST_WITH} with Alpaca's default symbol mapping and {TECX_WITHOUT} from {TECX_FIRST_WITHOUT} without it. The {TECX_MAP} sessions the mapping adds are from before "
            "{TECX_FIRST_WITHOUT}, when the series under TECX begins; the SEC submissions cached for Milestone 2 give its former names as {FORMER_NAMES} until {FORMER_UNTIL}.",
            "ASMB one reverse split; CXT twelve cash dividends; JBSS seven; NBIX one cash merger; TECX one name change and one reverse split; none for the other {OTHERS}.",
            "Shares outstanding exist for {SHARES_N} of {ISSUERS} issuers, with {DATES_MIN} to {DATES_MAX} filing dates in the window ({SEC_START} to {SEC_END})",
            "JBSS has only three facts, from {JBSS_FIRST_YEAR} to {JBSS_LAST_YEAR}", "Public float exists for all {ISSUERS}, {FLOAT_MIN} to {FLOAT_MAX} filed in the window, almost all from annual reports: a dollar value of non-affiliate holdings on one date a year, "
            "not a share count and not free float.",
        ]
        for sentence in sentences:
            with self.subTest(sentence=sentence[:90]):
                self.assertIn(sentence.format(**dict(v, CLOSE_OTHER=v["CLOSE_N"] - v["CLOSE_EQ"])), self.flat)
        by_type = {s: x["by_type"] for s, x in self.d["run2"]["report"]["corporate_actions"].items() if x["by_type"]}                 # the words in the corporate-action sentence are the counts
        self.assertEqual(by_type, {"ASMB": {"reverse_splits": 1}, "CXT": {"cash_dividends": 12}, "JBSS": {"cash_dividends": 7}, "NBIX": {"cash_mergers": 1}, "TECX": {"name_changes": 1, "reverse_splits": 1}})
        self.assertEqual((WORDS[1], WORDS[12], WORDS[7]), ("one", "twelve", "seven"))
        self.assertEqual(self.d["shares"]["JBSS"]["facts"], 3)
        self.assertEqual(len(self.d["run2"]["report"]["adjustment_modes"]), 5)
        self.assertIn("all five adjustment modes were accepted", self.flat)
        feeds = self.d["run2"]["report"]["feeds"]
        self.assertEqual({k: x["status"] for k, x in feeds.items()}, {"sip": 200, "iex": 200, "boats": 200, "otc": 403})
        self.assertIn("The `sip`, `iex` and `boats` (overnight) feeds were accepted, and `otc` was refused with the message `%s`." % feeds["otc"]["message"], self.flat)
        sources = {s["id"]: s["says"] for s in self.record["sources"]}
        sizes = lambda text: re.search(r"([\d.]+) to ([\d.]+) MB", text).groups()                                         # noqa: E731
        self.assertIn("The Form 13F data sets (%s to %s MB for each posting from 2024 to 2026) and the insider-transactions data sets (Forms 3, 4 and 5; %s to %s MB)" % (
            sizes(sources["sec-13f-data-sets"]) + sizes(sources["sec-insider-data-sets"])), self.flat)

    def test_the_two_conclusions_follow_from_the_recomputed_figures(self):
        v, text = self.v, self.flat
        self.assertEqual(v["NEITHER_DATE"], v["NEITHER2_DATE"])                                                       # "on the same date"
        for name in ("OPEN", "HIGH", "LOW"):                                                                         # where a comparison can tell the two apart, the daily bar sides with the regular session
            with self.subTest(price=name):
                self.assertGreater(v[name + "_REG"], v[name + "_ALL"])
                self.assertGreaterEqual(v[name + "_REG"], 0.85 * v[name + "_N"])
        pairs = self.d["pairs"]
        spy, xbi = [p for p in pairs if p["symbol"] == "SPY"], [p for p in pairs if p["symbol"] == "XBI"]
        self.assertTrue(all(abs(p["daily_volume_over_all_hours_minute_volume"] - 1) <= 0.0005 for p in spy))        # and the daily volume is the all-hours minute volume
        self.assertTrue(all(abs(p["daily_volume_over_all_hours_minute_volume"] - 1) <= 0.006 for p in xbi))
        self.assertTrue(all(p["daily_volume_over_regular_and_closing_minute_volume"] > 1.1 for p in spy))             # and not the regular-session one
        for phrase in ("**prices are regular-session prices,**", "**volume is all-hours volume,**", "its prices are regular-session prices and its volume is all-hours volume"):
            self.assertIn(phrase, text)
        for phrase in ("prices are all-hours prices", "volume is regular-session volume"):
            self.assertNotIn(phrase, text)

    def test_every_quotation_is_verbatim_the_owners_or_a_recorded_message(self):
        text = self.flat
        outside_code = re.sub(r"`[^`]*`", "", text)
        self.assertEqual(outside_code.count('"') % 2, 0)                                         # so that quotation marks pair up
        spans = re.findall(r'"([^"]*)"', outside_code)
        owner = load(AUTHORIZATION)["owner_messages"]
        self.assertEqual([m["text"] for m in owner], ["authorize phase 1a"])
        verbatim = [words for s in self.record["sources"] for words in s["verbatim"]]
        known = set([owner[0]["text"]]) | {words for words in verbatim if '"' not in words}
        self.assertEqual(sorted(spans), sorted([owner[0]["text"], "Currently Alpaca has no guarantees on the creation time of corporate actions.", "Only the most recent data is made available."]))
        for words in spans:
            with self.subTest(span=words):
                self.assertIn(words, known)
        quoted_in_sources = re.findall(r"Quoted verbatim: ((?:`[^`]*`(?:; )?)+)", text)
        self.assertEqual([item for group in quoted_in_sources for item in re.findall(r"`([^`]*)`", group)], verbatim)       # and the sources section holds exactly the recorded sentences, in order
        for words in verbatim:
            self.assertEqual(text.count(words), 2 if '"' not in words else 1, words)

    def test_the_files_it_names_exist(self):
        names = sorted(set(re.findall(r"`((?:reports|docs|nre|tests|config|scripts|archive)/[A-Za-z0-9_./\-]+\.(?:json|jsonl|md|py|payload))`", self.text)))
        self.assertGreaterEqual(len(names), 9)
        for name in names:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())
        for name in ("reports/m5-phase1a-authorization-2026-10-08.json", "reports/m5-phase1a-probe-run1-2026-10-08.json", "reports/m5-phase1a-probe-run2-2026-10-09.json",
                     "reports/m5-phase1a-sec-availability-2026-10-09.json", "reports/m5-phase1a-findings-2026-10-09.json", "config/m5-phase1a-probe-spec.json", "docs/ALPACA-ACCESS.md",
                     "reports/m5-scope-confirmation-2026-10-08.json", "reports/m1-alpaca-provider-rights-review-2026-09-23.json"):
            self.assertIn("`%s`" % name, self.text)

    def test_what_it_says_about_the_projects_own_records_is_what_those_records_say(self):
        access = flat((ROOT / "docs" / "ALPACA-ACCESS.md").read_text(encoding="utf-8"))
        self.assertIn("extended-hours trade conditions do **not** update daily open/high/low/close, but can update daily volume", access)
        self.assertIn("leaving core-session volume unverified", access)
        self.assertIn("Under the existing raw-price policy", access)
        intake = load(ROOT / "reports" / "alpaca-intake-validation.json")["provider_documentation_review"]["findings"]
        self.assertEqual(intake["daily_ohlc_semantics"], "Alpaca's published aggregation table says extended-hours trade conditions do not update daily OHLC, although they can update daily volume.")
        self.assertEqual(intake["daily_volume_semantics"], "Daily volume can include extended-hours eligible trades and is not certified as core-session-only volume.")
        self.assertIn("REGULAR_SESSION_VOLUME_UNVERIFIED", (ROOT / "nre" / "alpaca.py").read_text(encoding="utf-8"))
        declaration = load(ROOT / "reports" / "m1-acceptance-declaration-2026-09-26.json")["accepted_scope"]
        self.assertIn("daily regular-session, previous-close-anchored reaction labels (day-1 open/high/low/close, gap thresholds, gap fill and retention, closes at sessions 2, 5, 10 and 20)", declaration)
        self.assertIn("computed from Alpaca SIP raw daily bars", declaration)
        self.assertIn("The accepted scope of Milestone 1 names price-based labels", self.flat)
        review = load(ROOT / "reports" / "m1-alpaca-provider-rights-review-2026-09-23.json")
        findings = flat(json.dumps(review))
        self.assertIn("what happens as the project accumulates derived labels across potentially 100+ events", findings)
        self.assertIn("This is worth revisiting again at scale", findings)
        self.assertIn("never committing raw OHLCV", findings)
        self.assertIn("It is not legal advice", review["not_legal_advice"])
        proposal = flat(PROPOSAL.read_text(encoding="utf-8"))
        self.assertIn("the aggregate-at-scale question, which the project's provider attestation carries forward and the owner has answered at each scale-up, is put to the owner again before 1b or 1c", proposal)
        self.assertIn("**A disclosure:** the assistant writing this proposal has seen the block-5 results", proposal)
        self.assertIn("**A disclosure, carried over from the proposal:** the assistant writing this has seen the block-5 results.", self.flat)

    def test_it_starts_nothing_changes_no_decision_and_says_what_it_does_not_do(self):
        text = self.flat
        for phrase in ("Nothing was added to the dataset, no later phase was started, and none of the six decisions was changed", "None of the six decisions was changed (`decisions.changed` in the findings record is empty)",
                       "a confirmed default is never changed by the assistant alone", "Two decisions are touched: decision 6 (flag A) and decision 2 (flag F).",
                       "It starts no phase, pre-registers nothing, fetches no data from FINRA or Cboe and buys nothing.", "reads no event-level outcome and no block-5 outcome",
                       "It does not decide anything in section 6, and it does not answer the provider-rights-at-scale question.", "No data was fetched from FINRA or Cboe.",
                       "Nothing here is motivated by them: the fields probed are the master prompt's own lists, and the probe read no event-level outcome."):
            with self.subTest(phrase=phrase[:70]):
                self.assertIn(phrase, text)
        for flag in ("(flag B)", "(flag E)", "(flag A)", "(flag F)"):
            self.assertIn(flag, text)
        self.assertEqual([f["id"] for f in self.record["flags_for_the_owner"]], list("ABCDEF"))
        self.assertEqual(self.record["decisions"]["changed"], [])
        self.assertNotIn("recommended next step", text.lower())                                      # a findings document carries no next step; that is for the owner to choose
        authorization = load(AUTHORIZATION)
        self.assertIn("It does not authorize 1b, 0, 1c or any later phase", " ".join(authorization["how_the_words_were_read"]))

    def test_the_hand_written_claims_about_the_runs_match_the_run_records(self):
        run1, run2, spec = self.d["run1"], self.d["run2"], self.d["spec"]
        self.assertIn("3cc9796", run1["run"]["spec"])
        self.assertIn("5a57316", run2["run"]["spec"])
        self.assertEqual((run1["run"]["event"], run1["run"]["conclusion"], run2["run"]["event"], run2["run"]["conclusion"]), ("push", "success", "push", "success"))
        revisions = spec["revisions"]
        self.assertIn("It adds no request, no symbol and no session", revisions[1]["reason"])
        self.assertIn("the availability results of run 1 only", revisions[1]["motivated_by"])
        self.assertIn("the 16:00 minute (which holds the closing-auction cross) was counted as after-hours", revisions[1]["reason"])
        self.assertIn("nothing said whether the daily bar's open, high, low and close are regular-session or all-hours prices", revisions[1]["reason"])
        self.assertIn("Run 1 showed that the daily bar's volume matches the all-hours minute volume", revisions[1]["reason"])
        self.assertEqual(self.d["sec"]["method"]["window"], ["2024-10-01", "2026-10-02"])
        self.assertIn("300 ms apart", self.d["sec"]["method"]["how"])
        self.assertEqual(spec["transport"]["request_budget"], 320)
        self.assertEqual((spec["window"]["start"], spec["window"]["end"], spec["window"]["lookback_sessions_needed"]), ("2023-10-02", "2026-10-02", 252))
        self.assertIn("the 16:00 minute, the close-boundary bar that probably holds the closing-auction cross, was counted as after hours, and nothing said whether the daily bar's prices are regular-session or all-hours", self.flat)


if __name__ == "__main__":
    unittest.main()
