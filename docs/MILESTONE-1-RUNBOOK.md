# Milestone 1 — earnings event dataset

Minute-precision publication timestamps are supported as intervals: encode the minute start with a timezone offset and `precision: "minute"`. The builder retains the exclusive upper bound, requires the full interval before the decision cutoff and checks session and identity validity throughout. First-public verification and source evidence remain mandatory. This does not automatically admit minute-level wire timestamps. Date-only and market-boundary-ambiguous releases remain quarantined. See `reports/four-candidate-interval-replay.json` for the real-event replay.

## Current state

The engineering foundation is implemented. **Historical-data acceptance is not complete.** Tests use explicitly synthetic sources and prices, not trading evidence. No model, ranking, reaction fingerprint, analogue engine, investment score, brokerage integration or downstream modification is included.

The pilot protocol is frozen in `config/pilot.json`: releases 2026-01-05 through 2026-03-31, price coverage through 2026-04-30, at least 100 eligible events and 25 issuers. It must be used when constructing the reviewed input cohort; the general-purpose builder does not automatically enforce this particular research sample window. Candidate selection must precede inspection of returns. These are engineering sample targets, not statistical evidence of an edge.

## Run without Docker or third-party Python dependencies

Use Python 3.12+ on a host with IANA America/New_York timezone data. Python 3.12 and 3.13 are CI targets. From the repository root:

```bash
python -m unittest discover -s tests -v
python -m nre build tests/fixtures/synthetic_bundle.json --output data/snapshots
python -m nre verify data/snapshots/RETURNED_SNAPSHOT_ID
python -m nre replay data/snapshots/RETURNED_SNAPSHOT_ID
python -m nre fetch-universe --output data/universe
python -m nre discover-sec tests/fixtures/sec_submissions.json --cik 0 --output data/sec-fixture.json
```

Optional package installation uses the pinned setuptools build backend in `pyproject.toml`; source-tree operation above needs no installation. Runtime/test dependency list is empty, documented in `requirements.txt`. Snapshots record Python and SQLite versions, timezone bytes, code hashes, calendar version, inputs and outputs. Snapshots are deterministic within the same recorded runtime; SQLite byte identity across different runtimes is not promised.

For live SEC acquisition, provide an identifying contact in `SEC_USER_AGENT` through your environment, then:

```bash
python -m nre fetch-sec --cik 320193 --include-history --output data/sec/320193
```

Never commit credentials. This command is a per-CIK source acquisition, not a complete market census. It follows declared historical submissions continuation files, archives original response bytes and retrieval metadata, and preserves a ledger for every 8-K/8-K amendment encountered. Omitted Item fields are unknown; non-2.02 filings are explicit exclusions; amendments need review. Failure exits with code 2 and writes `failure.json`. HTTP 403 is not retried or bypassed. A serial client caps request frequency at four requests/second; use only one acquisition process per source/IP until a shared limiter is implemented.

Current Nasdaq directories are archived with retrieval and provider creation timestamps. ETFs/test issues/other exchanges and likely non-common instruments are marked; remaining rows require identity review. This snapshot must never be used as proof of 2026 Q1 membership or delisted-stock completeness.

## Reviewed input boundary

`build` accepts one normalized UTF-8 JSON bundle. `tests/fixtures/synthetic_bundle.json` is a complete executable example, explicitly synthetic. Real bundles require HTTPS provenance and `synthetic:false`; renaming a fixture flag does not pass validation. A human or upstream source-specific reviewed process must establish the historical facts before setting verification fields. A matching evidence substring proves presence, not correctness of the review.

| Collection / field | Meaning and required review |
|---|---|
| `schema_version`, `synthetic`, `as_of`, `availability_mode` | Version 1; explicit boolean; dataset maturity time; historical reconstruction or actual forward observation |
| `sources` | Unique source ID, public URL, exact archived text, first-seen and retrieval timestamps; optional SHA256 verified when supplied |
| `securities` | Stable security and company IDs, contemporaneous ticker/exchange/common-stock status, evidence source, valid interval and availability timestamp |
| `providers` | Provider ID, research-use permission, terms URL, supported feeds, and verified regular-session coverage |
| `events` | Event ID, unique economic cluster, security/source IDs, first-public timestamp and precision, evidence substring, explicit first-public verification and decision cutoff |
| `prices` | Unique price IDs, security/source/provider/feed, session date, raw regular-session OHLCV, availability time, completeness/halt state, corporate-action audit flag |
| `corporate_actions` | Security/source, effective date, availability and action type; explicit list of detected actions, with coverage attested by price flags |
| `features` | Optional reviewed observations: name/revision, source/security, value, valid and available times, actual first-seen time; historical-outcome features also require label availability |

The offline bundle is the price adapter in this release. No automatic Alpaca integration or unreviewed web-scraped price source is enabled. A free account is a possible future data input, not a purchased requirement. All provider permission and quality flags are explicit review attestations, not automatically verified licenses or data facts.

SEC acceptance times remain separate from first-public news release times. Retrieve the relevant issuer release/exhibit and review the first-public timestamp, timezone and competing earlier disclosures. The generic evidence extractor does not infer timestamps or automatically certify first-public status. Sources, disclosures and revisions must be grouped into one economic-event cluster before building. Duplicate cluster IDs are rejected rather than counted twice.

Security aliases/share classes are resolved by the input reviewer using stable IDs and valid intervals. The pilot builder accepts one reviewed identity interval per security per snapshot; it does not yet reconstruct multi-year ticker histories automatically. Historical membership, delistings, missing issuers and every candidate exclusion must remain documented externally in the cohort ledger.

## Labels and conservative exclusions

This release implements **previous regular-session close anchored** daily reaction labels. They are not exact last-trade-before-news returns. For an after-hours event, the anchor is that day's regular close and the reaction session is the next trading session. For premarket/weekend/holiday events, it is the prior regular close before the reaction session.

Targets: day-1 open/high/low/close returns; inclusive gap thresholds 3/5/10/15/20/30%; half-gap retention/full fill for positive gaps of at least 0.5%; and close returns on reaction-session indices 2/5/10/20. Index 1 is the reaction session. Return units are decimal fractions, not displayed percentages. Negative/small gaps receive unknown positive-gap labels, not false fill outcomes.

Intraday news, exact opening/closing bells and date-only timestamps are quarantined. They require finer data, not a guessed clock. Missing daily bars do not shift the horizon. Incomplete/halted/zero-volume sessions, unknown action coverage, mixed feeds, unverified provider permission or session coverage suppress labels. Known corporate actions within a label window suppress that window rather than applying an unverified split/dividend adjustment. A later incomplete horizon does not erase valid day-1 labels.

No intraday extensions, executable entries, MFE/MAE, order sequencing or historical alpha are claimed. Whole-day lows can establish a whole-day positive-gap fill for a pre-open study; they cannot establish what happened after a 09:45 signal.

The session calendar is deliberately limited to **2026**. Verified NYSE holiday/early-close exceptions and America/New_York conversion support the US core equity session. Unsupported dates fail closed. Emergency closures or a new year require a reviewed calendar version before use. Calendar reference: [NYSE hours and holidays](https://www.nyse.com/trade/hours-calendars), reviewed 2026-09-19.

## Point-in-time and reproducibility

Historical reconstruction uses reviewed public availability and explicitly labels that mode; downloading a historical source today does not prove the engine saw it in real time. Forward mode requires the news, security identity, pre-event anchor and features to have been observed by cutoff. A pre-open label is unavailable when decision cutoff is already after the open. Features filter valid time, availability, observation time in forward mode and historical label maturity. Future revisions cannot alter an earlier selection.

Snapshot directories are content-addressed. Each contains canonical inputs, source texts, outcome rows, quality report, SQLite with foreign keys, and a manifest. New source content produces a new snapshot. Identical input/code/runtime reuses and verifies the existing snapshot. `verify` checks file/identity hashes; `replay` recomputes outputs and reports without network access. Source network fetches independently archive exact response bytes before normalization. The reviewed text in a bundle must preserve the source bytes' provenance; normalization itself is an explicit audit step.

Snapshots and downloaded data are ignored by Git. Publish only permitted metadata/aggregates and authored synthetic fixtures. A local data directory is not a durable production archive; maintain a permitted durable source archive before running an accepted research cohort.

## Database scope

`nre/schema.sql` is migration version 1: sources, securities, events, prices, outcomes and snapshots. Each snapshot is immutable, so a changed source/event belongs to a new dataset snapshot. A schema change requires a new schema version. Full multi-model registry, analogue membership, advanced features, Parquet and production services remain outside this milestone's implemented subset.

## Validation and remaining acceptance work

### Executable cohort audit

```bash
python -m nre audit-cohort reviewed-bundle.json --protocol config/pilot.json --ledger frozen-candidates.json --review evidence-review.json --output cohort-audit.json
```

Start with `config/candidate-ledger.template.json` and `config/acceptance-review.template.json`. Empty templates deliberately fail. Do not populate a review claim without its evidence. Candidate rows require `candidate_id`, archived `source_sha256`, and either `disposition:included` plus `event_id`, or `disposition:excluded` plus a reason. The frozen membership hash is the SHA256 of canonical JSON for the candidate-ID-sorted list of `{candidate_id,source_sha256}` objects; freeze it before inspecting prices. The protocol hash is SHA256 of canonical `config/pilot.json`. The audit checks these declarations for consistency; it cannot independently authenticate when a hash or review was created.

Real events must declare `category:earnings` and `subtype:results`; issuer counts use normalized nonzero SEC CIKs, so renamed companies and multiple share classes cannot inflate the issuer count. Eligible counts require complete 20-session labels within the frozen price window. Event-window dates use New York time. Every event must reconcile to exactly one included candidate. Two distinct events per included timing class must each have two named independent reviewers and evidence references in `spot_checks`.

The command returns exit code 2 when blocked and lists all failed gates. Even if structural checks pass, it returns `STRUCTURAL_GATES_PASSED_REVIEW_REQUIRED` with `milestone_accepted:false`; source truth, permission and independent review require actual evidence sign-off. This distinction prevents a user-entered boolean from becoming a certificate of data validity.

`reports/milestone-1-cohort-gates.json` is the audit of the current **empty real-input inventory**, not a market sample. It is reproducible from `reports/milestone-1-input-inventory.json` and the two empty templates above. Zero real events remain available; synthetic test success cannot satisfy this gate.

Automated validation covers time/session rules, schema constraints, source checksums, duplicate economic clusters, corporate-action and price quality, missing horizons, explicit unknowns, future-information exclusion, database integrity, snapshot tampering and deterministic replay. CI runs offline tests on Python 3.12 and 3.13 plus the synthetic CLI build.

Before historical acceptance, obtain permitted archived SEC/issuer documents and raw regular-session prices, enumerate the frozen-window cohort without selecting on outcomes, reconcile every candidate into mapped/excluded/quarantined states, review security history and source timing, meet the 100-event/25-issuer target, and complete two independent spot checks for each timing class used. Store signed-off review evidence and coverage/exclusion counts. The program intentionally reports `NOT_EVALUATED` for a real input bundle; passing schema checks is not an automatic acceptance certificate.

Live evidence and unresolved blockers are in `reports/milestone-1-validation.json`. Milestone 1 remains open while the real cohort is unverified. Milestone 2 requires separate approval after acceptance.

## Source references

- [SEC submissions and historical continuation files](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC developer access guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions)
- [Nasdaq symbol-directory field definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)
- [Alpaca historical bars](https://docs.alpaca.markets/us/reference/stockbars): candidate future adapter; pagination, feed, adjustment and symbol as-of must be explicit. Daily bars must not be assumed to establish regular-session open/high/low without validation.

No source review establishes an investment edge.
