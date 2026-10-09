# Milestone 5 — Phase 1a: which regime and market-structure fields can be had point-in-time (findings)

**Status: findings of the availability probe the owner authorized on 2026-10-08 ("authorize phase 1a", `reports/m5-phase1a-authorization-2026-10-08.json`), written on 2026-10-09. They rest on two runs of the probe, a
bounded SEC check and primary-source documentation (section 7). Nothing was added to the dataset, no later phase was started, and none of the six decisions was changed: where a finding touches one, section 6 says so
and leaves it to the owner.** The figures come from `reports/m5-phase1a-probe-run1-2026-10-08.json`, `reports/m5-phase1a-probe-run2-2026-10-09.json` and `reports/m5-phase1a-sec-availability-2026-10-09.json`, and are
collected in `reports/m5-phase1a-findings-2026-10-09.json`.

## Summary

- **Daily bars exist for nearly every probed symbol.** 49 of the 51 symbols (all 28 ETFs and 21 of the 23 issuers) have all 754 sessions from 2023-10-02 to 2026-10-02, with no gap after a symbol's first bar and no
  zero-volume bar in any of the 51 series, and SPY's series equals the expected trading calendar exactly.
- **The daily bar mixes two definitions: its prices are regular-session prices and its volume is all-hours volume,** which is what Alpaca's aggregation table says, as `docs/ALPACA-ACCESS.md` recorded it, now measured.
  The daily open was never the first pre-market trade (0 of the 18 sessions that could tell them apart), and the daily volume was 1.0000 to 1.0002 of SPY's all-hours minute volume but 1.1032 to 1.1903 of its minute
  volume through the closing minute.
- **Pre-market volume exists in the minute bars:** plentiful for the ETFs (SPY has 244 to 290 pre-market minute bars a session) and sparse for the issuers (0 to 11, and none at all in 5 of 15 sampled issuer sessions).
- **Three issuers need an explicit lookback rule.** KLC and SLSN cannot supply the 252 sessions an annual high or low needs, and TECX reaches them only through a symbol mapping that adds 181 sessions from before
  2024-06-21, under its former name.
- **From the SEC,** shares outstanding exist as entity-wide facts for 20 of the 23 issuers and public float for 23 of 23 (from annual reports); public as-filed bulk files exist for institutional and insider ownership, but their
  rows are not mapped to the issuers.
- **Not found point-in-time:** free float, implied volatility, option open interest and gamma. Short interest (FINRA) and the VIX itself (Cboe) exist at providers the project has not reviewed; Alpaca has products on VIX
  futures as proxies for the VIX.
- **For the owner:** a point-in-time source was found for pre-market volume (Alpaca) and, as SEC bulk files that still need mapping, for institutional and insider ownership, which is the case decision 6 leaves open.
  Nothing was changed; section 6 lists what Phase 0 would have to settle.

## 1. What was done

- **The authorization** (`reports/m5-phase1a-authorization-2026-10-08.json`) covers the availability probe as the proposal words it, and nothing after it.
- **The probe** is a read-only, metadata-only check of the Alpaca market-data API, fixed in `config/m5-phase1a-probe-spec.json` before it ran: 51 symbols (28 ETFs and the 23 issuers) over 2023-10-02 to 2026-10-02, with
  the checks listed in the spec. It keeps dates, counts, status codes, unit-free ratios and booleans, never a price or a volume value, and a test checks every report for that.
- **Run 1** (spec revision 1, run 37839340734 on commit 3cc9796) gave the daily-bar, symbol-mapping, corporate-action, adjustment, feed and calendar results and a first minute sample, which showed that the daily bar's
  volume matches the all-hours minute volume. It also exposed two gaps in my own minute sample: the 16:00 minute, the close-boundary bar that probably holds the closing-auction cross, was counted as after hours, and
  nothing said whether the daily bar's prices are regular-session or all-hours. **Run 2** (revision 2, run 37887398952 on commit 5a57316) keeps the 16:00 minute apart and adds booleans for the daily prices; it adds no
  request, symbol or session, and its stated basis is run 1's availability results only. Its daily-bar, symbol-mapping, adjustment, feed, corporate-action and calendar results are identical to run 1's, 8 hours 46
  minutes later. Each run made 152 requests (the budget was 320), and neither had a failed check.
- **The SEC check** asked the company-concept API for two entity-wide facts for each of the 23 issuers (46 requests for the result kept and about 110 in all, 300 ms apart; see section 8) and kept counts, forms and filing dates only.
- **The documentation** of Alpaca, the SEC, FINRA and Cboe was read as primary sources (section 7). No data was fetched from FINRA or Cboe.

## 2. The fields, from where, and with what caveats

Every field in sections 10 and 11 of the master prompt has a row; relative volume is split into its daily and intraday forms, and support and resistance zones share a row. Status words: **in hand (Alpaca)** is available
from the project's existing provider; **SEC filings** is public data from a provider the project already uses, and needs work; **unreviewed provider** exists at FINRA or Cboe and would need a terms review first;
**derivable** combines two fields; **proxy only** has a substitute, not the field; **not found** was not found point-in-time in what was read.

| Fields | Master prompt section | Status | Source and timing | What the probe found |
| --- | --- | --- | --- | --- |
| market capitalization | 10 | derivable | shares outstanding (SEC cover page) times the raw close at the cutoff (Alpaca); shares are known from their filing date, and a split after that filing needs the corporate-action list | shares-outstanding facts exist for 20 of 23 issuers; HURN, JBSS and OKTA have no entity-wide fact in the window |
| float | 10 | proxy only | no free-float series found; shares outstanding and the annual public-float value (SEC) are proxies, the latter as of the end of the second fiscal quarter | public-float facts exist for 23 of 23 issuers, 2 to 4 filed in the window; the value is a dollar amount, not a share count |
| shares outstanding | 10 | SEC filings | SEC XBRL cover-page fact dei:EntityCommonStockSharesOutstanding; available from its filing date plus a margin (the SEC does not guarantee its lag) | 20 of 23 issuers, with 7 to 10 filing dates in the window; KLC's first fact was filed on 2024-11-21, after the first event day, 2024-11-04 |
| average daily dollar volume; relative volume (daily) | 10 | in hand (Alpaca) | Alpaca SIP daily bars: all-hours volume with regular-session prices; a day's volume is complete only after 20:00 ET | 49 of 51 symbols have all 754 sessions; the daily volume is 1.0000 to 1.0002 of SPY's all-hours minute volume and up to 1.2247 of an issuer's |
| premarket volume; relative volume (intraday); distance from VWAP | 10 | in hand (Alpaca) | Alpaca SIP minute bars from 04:00 to 20:00 ET; the minutes before the cutoff are known at the cutoff, though the provider's history today may include late reports (not tested) | SPY has 244 to 290 pre-market minute bars a session and XBI 28 to 80; the four sampled issuers 0 to 11, with none in 5 of 15 issuer sessions |
| short interest; days to cover | 10 | unreviewed provider | FINRA equity short interest, twice a month; provided for publication on the 7th business day after the settlement date; corrections are flagged and only the most recent data is made available; days to cover also needs the average daily volume from the daily bars | documentation read only; no data fetched; FINRA has not been reviewed as a provider |
| institutional ownership | 10 | SEC filings | SEC Form 13F data sets: quarterly postings of the as-filed 13F data, usable from each filing's date if the tables carry it (the table definitions are in a PDF that was not read) | documentation read only; 69.66 to 96.05 MB a posting for 2024 to 2026; the rows are not mapped to the issuers' securities |
| insider ownership | 10 | SEC filings | SEC insider transactions data sets (Forms 3, 4 and 5, as filed): quarterly postings, usable from each filing's date if the tables carry it (the table definitions are in a PDF that was not read) | documentation read only; 7.59 to 13.23 MB a posting for 2024 to 2026; the rows are not mapped to the issuers |
| ATR; realized volatility; recent price compression; breakout structure; support and resistance zones; previous gaps; distance from major moving averages | 10 | in hand (Alpaca) | Alpaca SIP daily bars, raw prices; regular-session open, high, low and close, known after the close (late corrections were not tested) | 49 of 51 symbols have all 754 sessions with no gap; 5 of the 23 issuers have a corporate action in the window |
| distance from 52-week high/low | 10 | in hand (Alpaca) | the same daily bars; needs 252 sessions before the event | all 28 ETFs and 21 of 23 issuers have them; KLC has 19 sessions and SLSN none before the first reaction session; TECX has them only through the symbol mapping (181 of its sessions are under the former name) |
| implied volatility; call/put activity; options open interest; gamma-related variables | 10 | not found | Alpaca documents option bars (aggregates by contract symbol); no implied-volatility or open-interest history was found in what was read | documentation read only; no data fetched |
| SPY trend; QQQ trend; Russell 2000 trend | 11 | in hand (Alpaca) | Alpaca SIP daily bars of SPY, QQQ and IWM (with IJR for small caps); IWM, a Russell 2000 fund, is a proxy for the index, which was not queried | 754 sessions each, no gap |
| VIX | 11 | proxy only | VIXY and VXX on Alpaca are products on VIX futures, not the index (by their names; not checked); Cboe links the VIX daily close from 1990 and has not been reviewed as a provider | VIXY and VXX have 754 sessions each; the Cboe page was read, no data fetched |
| sector ETF behavior; recent biotech momentum | 11 | in hand (Alpaca) | Alpaca SIP daily bars of 13 sector and theme ETFs plus XBI and IBB | 754 sessions each; 5 of the 23 issuers carry a drug-related SIC code (2834, 2835 or 2836), so recent biotech momentum applies to a minority of them; SIC is coarse and not point-in-time |
| breadth | 11 | proxy only | RSP (an equal-weight S&P 500 fund) against SPY is a proxy; no advance-decline series was found | RSP has 754 sessions |
| risk-on/risk-off environment; recent small-cap momentum | 11 | in hand (Alpaca) | Alpaca SIP daily bars of TLT, HYG, LQD, GLD, UUP, IWM and IJR; the composite is for the protocol to define | 754 sessions each |

## 3. What the daily bar is

On 23 ordinary sessions of six symbols (SPY, XBI, CACI, NBIX, TTWO and ACHV, on four Wednesdays in 2025) the probe compared each daily bar with the same provider's minute bars from 04:00 to 20:00 ET. A comparison can tell
the two definitions apart only on a day when the all-hours and regular-session values differ, so the table counts only those sessions.

| Daily value | Sessions that can tell the two apart | Equal to the all-hours value | Equal to the regular-session value |
| --- | --- | --- | --- |
| open | 18 | 0 | 17 |
| high | 9 | 1 | 8 |
| low | 6 | 0 | 6 |

- **Open and low:** where the all-hours and regular-session values differ, the daily open never equalled the first pre-market trade's (0 of 18) and the daily low never equalled the all-hours low (0 of 6). Among the 18
  sessions in the table, the one open that matched neither candidate was SPY on 2025-09-10, probably the opening-auction price (not checked); NBIX on the same date also matched neither, but there the two candidates
  are the same bar, so it is not in the table.
- **High:** 8 of 9 equal the regular-session maximum. The exception (CACI, 2025-06-11) had no pre-market or after-hours bar, and its daily high equals the all-hours maximum, which there is the regular session plus the
  16:00 minute, and not the regular session's alone: the daily high includes the closing minute.
- **Close:** the daily close equals the close of the 16:00 minute bar in 17 of the 23 sessions. In the other 6 (SPY on all four, XBI on 2025-06-11 and 2025-09-10) it equals none of the three minute closes tested (the
  last regular minute, the 16:00 minute and the last bar of the day). Of the 19 sessions with after-hours bars, 17 have a daily close that differs from the last after-hours trade. The likely reason, which I did not
  check, is that the close is the exchange's closing-auction price, which a minute bar need not show.
- **Volume:** the daily bar's volume was 1.0000 to 1.0002 of SPY's all-hours minute volume (1.0001 to 1.0056 of XBI's, and 1.0040 to 1.2247 of the four issuers'), but 1.1032 to 1.1903 of SPY's minute volume through the
  16:00 minute. It therefore includes pre-market and after-hours trading. For the thinner issuers it exceeds the all-hours minute sums by up to about 22%; I did not find out why (late reports or auction prints are
  possible). The 16:00 minute carries 1.5% to 40.6% of an issuer's all-hours minute volume and 1.1% to 3.0% of SPY's and XBI's.

What follows: **prices are regular-session prices,** which agrees with Alpaca's aggregation table as `docs/ALPACA-ACCESS.md` recorded it and with the daily labels the project built; and **volume is all-hours volume,**
which answers, for this sample, the question behind the Milestone 1 blocker `REGULAR_SESSION_VOLUME_UNVERIFIED`: the daily volume is not core-session volume. A day's volume is complete only after 20:00 ET (flag B). The
accepted Milestone 1 and 2 records were not touched (flag E).

## 4. Identity, history and corporate actions

- **KLC** has its first bar on 2024-10-09 (497 sessions, 19 of them before the first reaction session, 2024-11-05), consistent with a listing in October 2024 (not checked); its first shares-outstanding fact was filed on
  2024-11-21.
- **SLSN** has its first bar on 2025-04-08 (374 sessions, none before the first reaction session), with or without the symbol mapping. The subscription does not permit OTC data, and a possible reason for the late start,
  which I did not check, is that SLSN traded over the counter before it listed.
- **TECX** has 754 bars from 2023-10-02 with Alpaca's default symbol mapping and 573 from 2024-06-21 without it. The 181 sessions the mapping adds are from before 2024-06-21, when the series under TECX begins; the SEC
  submissions cached for Milestone 2 give its former names as AvroBio, Inc. and AVROBIO, Inc. until 2024-06-18. Alpaca lists a name change and a reverse split for it in the window (dates not kept), so raw prices
  across the mapped history may not be comparable.
- **Corporate actions over the three years** came back in one call per issuer (the documentation states no limit on the interval): ASMB one reverse split; CXT twelve cash dividends; JBSS seven; NBIX one cash merger;
  TECX one name change and one reverse split; none for the other 18. Alpaca warns: "Currently Alpaca has no guarantees on the creation time of corporate actions." So the list gives an action's dates, not when it
  became known.
- **Adjustments and feeds:** all five adjustment modes were accepted. The project uses raw prices (the existing raw-price policy in `docs/ALPACA-ACCESS.md`), which with the action list is the point-in-time choice,
  since prices adjusted for later actions embed information that was not yet known. The `sip`, `iex` and `boats` (overnight) feeds were accepted, and `otc` was refused with the message
  `subscription does not permit querying OTC data`.

## 5. Sources other than Alpaca

- **SEC shares outstanding and public float.** The company-concept API holds entity-wide facts. Shares outstanding exist for 20 of 23 issuers, with 7 to 10 filing dates in the window (2024-10-01 to 2026-10-02); HURN
  has none (I did not find out why), OKTA returns 404 and JBSS has only three facts, from 2011 to 2012 (for OKTA and JBSS the probable reason is shares reported by class; not checked). Public float exists for all
  23, 2 to 4 filed in the window, almost all from annual reports: a dollar value of non-affiliate holdings on one date a year, not a share count and not free float. The SEC says filings are often on sec.gov 1 to 3
  minutes after the EDGAR timestamp and does not guarantee it, so availability is the filing date plus a margin.
- **SEC bulk files.** The Form 13F data sets (69.66 to 96.05 MB for each posting from 2024 to 2026) and the insider-transactions data sets (Forms 3, 4 and 5; 7.59 to 13.23 MB) are quarterly postings of as-filed data.
  Neither was downloaded or opened, so how their rows map to the 23 issuers' securities is not known, and whether each row carries its filing date, which point-in-time use needs, depends on table definitions in PDFs
  that were not read. The SEC does not guarantee their accuracy.
- **FINRA short interest.** Reported twice a month and provided for publication on the 7th business day after the settlement date; the interactive grid and the Equity API hold five rolling years, and historical files
  can be downloaded. When FINRA corrects a value it puts a Revision Flag next to the revised item and states: "Only the most recent data is made available." A corrected value therefore replaces the one first
  published, which weakens point-in-time use. FINRA has not been reviewed as a provider.
- **Cboe VIX.** Cboe's page links daily closing values of the VIX Index from 1990, updated daily, and offers custom VIX options and futures data through DataShop (not reviewed). Cboe has not been reviewed as a provider.
  On Alpaca, VIXY and VXX have all 754 sessions and are proxies (products on VIX futures, by their names).
- **Options.** Alpaca documents option bars by contract symbol. No implied-volatility, gamma or open-interest history was found in what was read, so those stay out of reach, as decision 6 says unless a source is found.

## 6. What this touches in the decisions

None of the six decisions was changed (`decisions.changed` in the findings record is empty), and the rule in `reports/m5-scope-confirmation-2026-10-08.json` still holds: a confirmed default is never changed by the
assistant alone. Two decisions are touched: decision 6 (flag A) and decision 2 (flag F).

- **A. Decision 6's exception is met for some fields.** Decision 6 says to declare float, short interest, institutional ownership, options and premarket volume out of reach unless a point-in-time source is found. Found: premarket volume, in Alpaca's minute bars (a provider the project has already reviewed); and institutional ownership, with insider ownership, which the master prompt also lists, as public as-filed SEC bulk files whose rows still have to be mapped to the 23 issuers (not started). Not found: float (only proxies) and options history. Short interest has a published schedule, but FINRA flags corrections and keeps only the most recent data, FINRA has not been reviewed, and decision 6 says no new provider is chosen. Nothing was changed: Phase 0 would have to say which of these it pre-registers, and each new source needs its own go-ahead and, outside the SEC and Alpaca, a terms review.
- **B. The daily bar's volume is all-hours volume.** Any volume feature built from a daily bar includes pre-market and after-hours trading, and a day's volume is complete only after 20:00 ET. For a release after the close, the same day's daily volume contains trading after the release; the protocol would need a rule (for example, use the previous completed day, or build the same-day figure from minute bars up to the cutoff) and must name which volume it means.
- **C. Three issuers need an explicit lookback rule.** KLC (19 sessions before the first reaction session) and SLSN (none) cannot supply a 252-session lookback. TECX reaches 276 sessions only through Alpaca's default symbol mapping, which adds 181 sessions from before 2024-06-21: the SEC submissions cached for Milestone 2 give its former names as AvroBio, Inc. and AVROBIO, Inc. until 2024-06-18, and Alpaca lists a name change and a reverse split for it, so those sessions are under an earlier name and symbol and the raw prices across them may not be comparable (no price was kept to check). Without the mapping TECX has 95 sessions before the first reaction session. Phase 0 would need to say whether such features abstain, use shorter windows or skip the mapped history.
- **D. Shares outstanding are missing for three issuers and, for KLC, before 2024-11-21.** HURN, JBSS and OKTA have no usable entity-wide shares-outstanding fact in the SEC API: OKTA's request returned 404 and JBSS's last fact was filed in 2012, probably because they report shares by class (not checked); HURN's entry is empty and I did not find out why. KLC's first fact was filed on 2024-11-21, after the first event day, 2024-11-04. Market capitalization for these would need another route or must abstain.
- **E. The daily prices are regular-session prices.** This agrees with how the labels were built (daily open, high, low and close) and with what `docs/ALPACA-ACCESS.md` recorded from Alpaca's aggregation table (extended-hours trade conditions do not update the daily open, high, low and close, but can update the daily volume); the sample now measures it, on 23 sessions of six symbols. It also answers, for that sample, the question behind the Milestone 1 blocker `REGULAR_SESSION_VOLUME_UNVERIFIED`: the daily volume is not core-session volume; it includes extended-hours trading. The accepted scope of Milestone 1 names price-based labels, and the accepted Milestone 1 and 2 records were not touched; whether to annotate the blocker in them is the owner's call.
- **F. The provider-rights-at-scale question gets bigger, not smaller.** Premarket volume and the other intraday fields would need minute bars around every event, and the forward extension adds events: both enlarge what is pulled from the provider and what is derived from it, which is the growth that the project's provider-rights review (`reports/m1-alpaca-provider-rights-review-2026-09-23.json`) asks to have revisited at scale. The proposal already puts the aggregate-at-scale question to the owner before 1b or 1c; these findings do not answer it.

## 7. Sources read

- [Alpaca Market Data API: historical stock bars](https://docs.alpaca.markets/reference/stockbars), read on 2026-10-08. Inclusive RFC-3339 or date start and end; up to 10,000 bars a page; adjustments raw, split, dividend, spin-off and all (combinable); an asof date that, by default, maps an entity's earlier symbols into the queried one; feeds sip, iex, boats (overnight) and otc. Quoted verbatim: `The special value of "-" means symbol mapping is skipped.`
- [Alpaca Market Data API: corporate actions](https://docs.alpaca.markets/reference/corporateactions-1), read on 2026-10-08. Sixteen action types; start and end are inclusive dates, sorted by process date; no limit on the length of the interval is stated; incomplete actions are excluded by default; Alpaca warns that delays in receiving and processing are possible. Quoted verbatim: `Currently Alpaca has no guarantees on the creation time of corporate actions.`
- [Alpaca Market Data API: historical option bars](https://docs.alpaca.markets/reference/optionbars), read on 2026-10-09. Aggregates (bars) by option contract symbol, up to 100 contracts a request; the page states no history depth and mentions no implied-volatility or open-interest history.
- [SEC: EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), read on 2026-10-08. The XBRL company-concept, company-facts and frames APIs aggregate entity-wide facts from non-custom taxonomies including dei, update in real time (typically within a minute), and data.sec.gov supports no cross-origin scripting; bulk ZIPs are rebuilt nightly. Page reviewed 2025-04-08.
- [SEC: Webmaster Frequently Asked Questions](https://www.sec.gov/about/webmaster-frequently-asked-questions), read on 2026-10-08. Scripted access is allowed at up to 10 requests a second with a declared user agent; filings are often on sec.gov 1 to 3 minutes after the EDGAR timestamp, which the SEC does not guarantee or predict.
- [SEC: Form 13F Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets), read on 2026-10-09. ZIP files of the data extracted from the XML part of Form 13F submissions, July 2013 to August 2026, presented without change from the as-filed submissions in a flattened format; updated quarterly (since March 2024 run after the end of February, May, August and November for the prior three months), with documents filed after 5:30 p.m. Eastern on a quarter's last business day going into the next posting; 69.66 to 96.05 MB each for the files from 2024 to 2026; the table definitions are in a separate PDF, which was not read; the SEC cannot guarantee accuracy. Page reviewed 2026-08-31.
- [SEC: Insider Transactions Data Sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets), read on 2026-10-09. ZIP files of the data extracted from the XML fillable portion of Forms 3, 4 and 5, January 2006 to September 2026, presented without change from the as-filed submissions in a flattened format; updated quarterly, with documents filed after 5:30 p.m. Eastern on a quarter's last business day going into the next posting; 7.59 to 13.23 MB each for the files from 2024 to 2026; the table definitions are in a separate PDF, which was not read; the SEC cannot guarantee accuracy. Page reviewed 2026-09-30.
- [FINRA: About Equity Short Interest](https://www.finra.org/finra-data/browse-catalog/equity-short-interest), read on 2026-10-09. Member firms report short positions twice a month under Rule 4560; the data are provided for publication on the 7th business day after the reporting settlement date; the interactive grid and the Equity API hold five rolling years and historical files can be downloaded; when a correction is made, a Revision Flag appears next to the revised item. Quoted verbatim: `Only the most recent data is made available.`
- [Cboe: VIX historical data](https://www.cboe.com/tradable-products/vix/vix-historical-data), read on 2026-10-09. The page links daily closing values of the VIX Index from 1990 to the present (updated daily) and lists seven other volatility indices; it points to DataShop for custom VIX options and futures data on demand (not reviewed); the data are compiled for visitors' convenience and furnished without responsibility for accuracy.
- Project: Alpaca access notes (`docs/ALPACA-ACCESS.md`), read on 2026-10-09. As the project recorded it from Alpaca's market-data FAQ: extended-hours trade conditions do not update the daily open, high, low and close, but can update the daily volume; core-session volume was left unverified (also in `reports/alpaca-intake-validation.json`).
- Project: Alpaca provider-rights review (`reports/m1-alpaca-provider-rights-review-2026-09-23.json`), read on 2026-10-09. The review found the project's practice of committing only derived values, never raw OHLCV, consistent with the terms it read; it named as the open question what happens when derived labels accumulate across many events and securities over time, and asked that it be revisited at scale. It is not legal advice.

## 8. Limits

- Two runs of one probe, 8 hours 46 minutes apart; the daily-bar results repeated exactly, which says nothing about whether the provider ever revises past bars or how its history may change later (a vintage question that was not tested).
- The minute sample is six symbols on four ordinary 2025 Wednesdays (23 sessions after the guard skipped one), none within five calendar days of a candidate event date and none an early close. A field can be classified only on a session where its candidates differ, so the high and low rest on 9 and 6 sessions.
- The booleans compare the daily bar with minute bars of the same provider and feed; they do not show that either equals an exchange's official price.
- The SEC check used entity-wide facts only, kept no value, and cannot say whether the facts are right; the SEC does not guarantee its API's timing.
- The SEC check ran as same-origin fetches from a data.sec.gov tab of the built-in browser (data.sec.gov supports no cross-origin scripting), so it sent the browser's own user agent, not a declared one as the SEC's guidance asks; it made 46 requests for the result kept and about 110 in all, at about 3 a second against the SEC's stated maximum of 10.
- The documentation pages were read on 2026-10-08 and 2026-10-09 and can change; three sentences (two from Alpaca, one from FINRA) are quoted verbatim and the rest is paraphrased, and a test can compare the quotations with this record but not with the live pages. The PDFs with the SEC data sets' table definitions were not read.
- No data was fetched from FINRA or Cboe (only their documentation pages were read), nothing was bought, and the dataset is unchanged.
- The count of drug-related issuers uses SIC codes read on 2026-09-26 (`config/sector-map.json`), which are coarse and not point-in-time.
- VIXY, VXX, IWM, RSP and the other fund symbols are taken in their usual sense; the probe checked only that they have daily bars.

## 9. What this document does not do

It starts no phase, pre-registers nothing, fetches no data from FINRA or Cboe and buys nothing. It adds nothing to the dataset and reads no event-level outcome and no block-5 outcome. It does not decide anything in
section 6, and it does not answer the provider-rights-at-scale question.

**A disclosure, carried over from the proposal:** the assistant writing this has seen the block-5 results. Nothing here is motivated by them: the fields probed are the master prompt's own lists, and the probe read
no event-level outcome.
