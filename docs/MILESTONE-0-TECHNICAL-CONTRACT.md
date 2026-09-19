# NRE 1.0 — Milestone 0 technical implementation contract

Date: 2026-09-19. Contract version: 0.2. Status: Milestone 0 research/design and repository audit complete; publication is verified by the accompanying GitHub commit and delivery report. No predictive implementation or Milestone 1 work has begun.

## 1. Authority, scope, and audit record

Authority is the supplied `Pasted markdown(20260919-164425).md` master build prompt. Only Milestone 0 is authorized. NRE is an independent research discovery system. It must not place trades, size positions, change brokerage accounts, or change IEE v1.7.2, frozen SOE rules, or frozen BOE rules. Integration is reserved for Milestone 9 following independent validation.

Canonical repository: https://github.com/Fahad9101/NRE. The user supplied this newly created repository after initial discovery found no accessible NRE repository. GitHub is the single source of truth. Live audit on 2026-09-19 confirmed write permission and an empty public repository, with default branch metadata `main` but no actual branches or commits yet.

| Required repository evidence | Observed state before publication |
|---|---|
| Repository identity | Fahad9101/NRE; repository ID 1377398811 |
| Files and existing implementation | Contents API explicitly reported repository empty |
| Branches and commits | Branch list empty; commits API explicitly reported repository empty |
| AGENTS.md and dependencies | None; repository has no files |
| Issues and PRs | Both all-state lists empty |
| GitHub Actions | Run count zero; no workflow files in empty repository |
| Workflow-list API | Fetch endpoint rejected by connector allowlist; absence of workflows established by empty repository instead |

This milestone adds documentation only. No production code, scoring, dependency environment, predictive tests or CI workflow is installed. CI status is therefore **not configured**, not passed. Existing IEE, SOE and BOE repositories are outside the write scope. Publication must be followed by remote branch, tree and content readback and Actions/status checks; report the resulting SHA outside this document to avoid a self-referential commit hash. Stop before Milestone 1.

## 2. Research questions and prediction clocks

Keep separate datasets, estimators, calibrators, evaluations, and registries for A, B and C.

| Model | Prediction clock | Permitted information | Principal estimands |
|---|---|---|---|
| A: pre-catalyst | Last regular close before the scheduled event window, with schedule known then | Pre-event information only | Absolute move ≥5/10/20%; positive/negative move ≥10% |
| B: news reaction, primary | First ingestion and successful parsing of a material release; replay uses a declared latency policy | Release and prior information available by cutoff; only already observed prices | Conditional opening/close/5-session return distributions |
| C: continuation/fade | Fixed opening +15-minute observation, with later clocks registered separately | B information plus prices/volume through C cutoff | Future gap retention, fill, additional extension and continuation |

Model A must represent cancellations, postponed events, uncertain windows and unfavorable outcomes. Trial completion dates are not readout dates. B after the opening bell must not predict the opening gap that has already occurred; use future-only intraday/close targets. A later B update is a new timestamped prediction, not a replacement of the earlier record. C distinguishes already-filled gaps from future fill risk.

No claim of predictive edge is established by this contract. Numeric examples in the master prompt are illustrative, not estimates or performance claims.

## 3. Public/free data plan and evidence

Official documentation was reviewed on 2026-09-19. Documentation review is not an authenticated endpoint test, historical coverage audit, or redistribution-license clearance. No paid source is selected or authorized.

| Source | Intended role | Constraints and acceptance evidence |
|---|---|---|
| SEC submissions, filings and exhibits | Earnings discovery, timestamp evidence, source documents, filings and ownership disclosures | API has no key requirement; preserve accession and raw bytes. Filing acceptance is not necessarily the first public release. Reconstruct from original documents, not latest values alone. [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) |
| SEC daily/quarterly indexes and RSS | Enumerate filing candidates, including issuers not in today's universe | Index coverage must be reconciled to manifest counts. Configure identifiable user agent and conservative global throttling; confirm current access policy before ingestion. [Developer resources](https://www.sec.gov/about/developer-resources) |
| Nasdaq Trader directories | Current securities and exchange metadata, prospectively archived | Directories expose symbol, name, exchange, ETF/test flags and generation time. They are not a reconstructed historical universe. Non-ETF does not establish common-stock eligibility. [Field definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs) |
| Issuer IR releases and SEC-linked exhibits | Release text, guidance, scheduled-event announcements | Preserve original publication time and later amendments; each issuer requires parser/terms review. Reposted releases are not new independent catalysts. |
| FDA Drugs@FDA / openFDA | Regulatory outcome corroboration | Do not infer first-public minute or intraday tradability from a database record. [Drugs@FDA API](https://open.fda.gov/apis/drug/drugsfda/) |
| FDA Advisory Committee calendar | Scheduled committee events | Snapshot dates and revisions; no assumption of a complete PDUFA calendar or complete CRL history. [Calendar](https://www.fda.gov/advisory-committees/advisory-committee-calendar) |
| ClinicalTrials.gov | Trial identity and study-design context | API pages were reachable but yielded insufficient detail in text retrieval. Historical-version semantics and API fields remain unverified; latest study records are not eligible historical features by default. [API](https://clinicaltrials.gov/data-api/api) |
| Alpaca market data, optional free account | Candidate daily/intraday provider | Documentation describes free Basic real-time equities as IEX-only, history since 2016 and a recent-15-minute historical restriction. Authentication is required. Verify actual feed entitlement, corporate-action behavior and symbol coverage. No credentials were tested. [Market-data documentation](https://docs.alpaca.markets/us/docs/about-market-data-api) |

Alpaca is a candidate adapter, not a required new subscription. IEX volume must never be described as consolidated volume or mixed with consolidated denominators for RVOL. If account-free data is required, use authorized supplied files until a reproducible, legally usable public price source passes the same audit. Do not silently scrape undocumented endpoints or assume public accessibility grants redistribution rights.

Historical analyst consensus, point-in-time float, short interest release histories, options data, historical NBBO and delisted intraday coverage are unresolved. Missing fields remain null with reasons. No fake consensus, float inferred as shares outstanding, or daily short-sale volume substituted for short interest. Earnings surprise versus prior guidance is a different feature from surprise versus analyst consensus.

Every provider must have a capability manifest: terms URL and review date; permitted research/storage/redistribution uses; authentication; exchanges/feed; time coverage; delay; timestamp semantics; adjustment policy; historical version availability; rate limit; quota; measured missingness. Unknown permissions block that use. Provider outages produce logged unavailability, not invented observations.

## 4. Taxonomy and structured extraction

Use versioned controlled enums with an explicit unknown value. One economic event can have multiple associated sources and multiple catalyst components.

| Category | Required subtypes | Structured payload |
|---|---|---|
| Earnings | Results, guidance initiation/raise/cut/withdrawal, restatement | Fiscal period; actual/consensus EPS and revenue; GAAP basis; margins; EBITDA/FCF where meaningful; current/prior/consensus guidance; currency, units, one-offs, commentary evidence |
| Biotech | Preclinical; phases I/II/III; filing; AdCom; PDUFA/decision; approval; CRL; safety; licensing | Trial ID, phase, indication, endpoints, comparator, sample size, effect/CI/p-value, multiplicity, safety, discontinuation, dose/subgroup evidence, label, regulatory outcome, economics, financing |
| Corporate | Acquisition/divestiture, contract/customer, partnership, restructuring, executive change, litigation, product, capex, buyback/dividend, refinancing, distress, strategic review | Parties, amounts, contingencies, timing, recurring versus one-off effect, balance-sheet effects |
| Capital markets | Secondary/ATM/convertible/debt, repurchase, insider, lockup, ownership | Announced versus completed, share count, proceeds, dilution basis, terms, effective/public dates, ownership-report lag |

Each extracted value includes source ID, quoted evidence span/location, extraction version, availability time, units, accounting basis and quality state. LLM extraction is schema-constrained and source-grounded; unsupported values become unknown. Model training cannot use retrospective human interpretations or LLM memorized later outcomes. Record prompt/model/version and verify extracted facts against the as-of source.

Define EPS surprise as `(actual-consensus)/abs(consensus)` only when consensus is nonzero and both values share period, units and accounting basis; otherwise report absolute difference and a denominator flag. Revenue follows the same comparability rule. Guidance midpoint comparisons require matching ranges/periods; ranges must also remain available. Novelty is based on prior available disclosures. Scientific and economic significance remain separate feature groups. Do not install arbitrary 0–100 catalyst weights in Milestone 0; transformations and any later aggregate score must be versioned, auditable, and validated.

## 5. Point-in-time architecture

All timestamps are timezone-aware UTC, retaining the original string/timezone. Use a versioned US exchange-session calendar, with America/New_York conversion, daylight saving, holidays and early closes. Never implement a fixed UTC market-open time.

For every source revision store `published_at`, timestamp precision and evidence; `first_seen_at`; `retrieved_at`; content hash; provider ID; revision ID; `supersedes_id`. A date-only release is an interval, not midnight. Quarantine precise gap/intraday labels when that interval crosses market boundaries.

Distinguish two availability modes:

1. **Historical information reconstruction:** verified contemporaneous public time plus explicitly modeled provider/processing delay. Modern retrieval time remains recorded; reconstructed availability is marked simulated and cannot certify actual historical system operation.
2. **Forward operational replay:** availability is no earlier than both publication and actual ingestion/processing completion. Delayed quotes become usable only after their delivery time.

Store valid/effective time separately from public availability and system observation. An as-of join must meet both effective-time and availability constraints. Features require `available_at <= prediction_at`; historical analogue outcomes also require `label_available_at <= prediction_at`. Quarterly period-end, short-interest settlement date and ownership reporting period are not publication dates.

A source's later correction creates a new immutable revision; it does not overwrite past predictions. Ticker aliases have validity intervals and map to permanent security IDs and issuer CIKs. Multiple share classes remain separate securities. Preserve delistings, mergers and bankruptcies in universe history; current directory snapshots cannot prove survivorship-free coverage.

Calendar changes, source edits, duplicate syndication and simultaneous earnings/guidance must be explicit. Group correlated disclosures into an event cluster, retaining components; do not count one release across several sources as independent samples. Mark later competing catalysts during outcome windows and report clean-window and all-event sensitivities without cherry-picking favorable cases.

## 6. Return and label contract

Returns are decimal fractions internally; displayed percentages multiply by 100. Percentage-point differences are labeled explicitly. Each label includes denominator, endpoint/window, session, price basis, feed, timestamp, completeness, label version and available-at time.

Let `P0` be the last eligible price strictly before public release. For premarket/after-hours opening-gap studies also retain `Cprev`, the last regular close preceding the reaction session; it is not necessarily the same as `P0`. `O,H,L,C` are the reaction session's regular open/high/low/close on a consistent corporate-action basis.

| Target | Definition / eligibility |
|---|---|
| Opening gap | `G = O/Cprev - 1`; thresholds ≥3/5/10/15/20/30%; eligible pre-open events only |
| Event-relative Day-1 | `H/P0-1`, `L/P0-1`, `C/P0-1`; only post-release extrema for intraday events |
| Opening-anchored Day-1 | `H/O-1`, `L/O-1`, `C/O-1`; distinct from event-relative returns |
| Minute response | Last complete eligible bar at release +5/15/30/60 trading minutes versus `P0`; no use of a bar containing pre-release extremes |
| Horizon returns | Close on reaction-session index 2/5/10/20 divided by `P0`, minus 1; reaction session is index 1 |
| Retention at close | For positive gaps, `(C-Cprev)/(O-Cprev) >= 0.5`; zero/small gaps below a preregistered threshold are ineligible |
| Full positive-gap fill | Any eligible post-open traded price ≤`Cprev`; negative gaps use price ≥`Cprev`, evaluated separately |
| Extension | For C, maximum price strictly after prediction divided by executable reference at prediction minus 1, ≥5/10%; also expose separate open-anchored label |
| Future MFE/MAE | Max/min return strictly after signal relative to defined entry/reference; unavailable without sufficient path data |
| Retracement before continuation | Ordered path to preregistered +5% extension; maximum adverse excursion before first hit; no hit is censored, not zero |

Future continuation/fill targets exclude facts already known at prediction time. Daily OHLC may support whole-session gap-fill labels for a before-open study, but cannot establish post-09:45 fill ordering or stop/target ordering. Missing sessions, halts, partial bars and unresolved corporate actions create unknown/censored labels rather than false negatives. Never forward-fill a halt into an executable trade. Store raw prices and action factors; remove split mechanical returns without silently treating future adjustment information as a historical feature. Keep dividends/total returns separate from quoted price reactions.

## 7. Reaction-gap semantics

Expected and observed reactions must share denominator and price basis. For horizon `h`, let model-predicted return from `P0` be `R_h`, and observed return at decision time be `r_t = P_t/P0-1`. Then `reaction_gap_pp = 100*(E[R_h|information at t]-r_t)`. Store horizon and cutoff in the output; opening-gap and five-day forecasts are never interchangeable.

The corresponding residual expected price return from the current quote is `(1+E[R_h])/(1+r_t)-1`, not the simple percentage-point gap. Transform forecast quantiles consistently. A conditional distribution is preferred over an invented expected range; identify whether an interval is a predictive interval, confidence interval, or interquartile interval.

A positive reaction gap alone is not a signal. Require quote freshness, sufficient liquidity/coverage, model validity, uncertainty and execution evidence. Observed prices may already be part of B's conditioning set; validate residual forecasts directly and do not count the same price information twice as independent support. Negative-news forecasts and short-side economics require separate validation; initial deployment does not imply short execution.

## 8. Logical schema and storage

Proposed implementation: Python package, SQLite metadata/event store for a local pilot, immutable content-addressed source files and Parquet for price/feature snapshots. No Docker required. Postgres migration is an adapter concern. This is a design choice, not installed production infrastructure.

All derived tables carry schema/code version, snapshot ID, created-at, lineage and quality flags. Foreign keys are mandatory; revisions are append-only. Monetary values use explicit currencies and decimal precision; missing and zero are distinct.

| Table | Key and essential fields |
|---|---|
| companies | company_id PK, CIK unique where known, legal identity |
| securities | security_id PK, company_id FK, share class, currency |
| security_history | (security_id, revision_id) PK; ticker/exchange/type/sector, valid interval, public/system times, source_id |
| universe_membership | (snapshot_id, security_id) PK; eligibility, exclusion reason, effective/public times |
| source_documents | source_id PK; URL/provider/accession, content SHA256, timestamp interval/precision, observation times, revision linkage, permitted-use record |
| events | event_id PK; security_id, cluster_id, taxonomy/version, release interval, timing evidence, session assignment, status |
| event_sources | (event_id, source_id) PK; role and evidence locations |
| schedules | schedule_revision_id PK; event/security, expected time interval, announcement availability, reschedule/cancel state |
| catalyst_features | (event_id, feature_name, feature_version, revision_id) PK; value/type/unit, basis, source/span, availability |
| corporate_actions | action_id PK; security, type, effective/public time, factors/cash, source |
| price_observations | observation_id PK; security/feed, trade or quote time, delivery time, bid/ask/size or price, conditions, revision |
| price_bars | (security_id, provider, feed, interval, start, revision_id) PK; OHLCV, end/availability, adjustment basis |
| structure_observations | observation_id PK; security, float/shares/short interest/etc., measurement/public/system times, source |
| sessions | (calendar_version, exchange, session_date) PK; open/close and exceptional status |
| reaction_outcomes | (event_id, target_version, horizon, revision_id) PK; value/unknown reason, anchor IDs, window, label_available_at |
| feature_snapshots | feature_snapshot_id PK; model task/cutoff, source/feature hashes, immutable values and availability proofs |
| analogue_members | (prediction_id, analogue_event_id) PK; distance, weight, eligible outcome version, exclusion audit |
| model_versions | model_version PK; task, code/model checksum, training/calibration windows, snapshot, feature/target versions, environment/seeds, approval state |
| predictions | prediction_id PK; model FK, security/event, timestamp, feature snapshot, horizon/anchor, quantiles/probabilities, confidence, state/reasons |
| quality_flags | flag_id PK; entity/table/key, severity, reason, evidence, rule version |
| datasets | snapshot_id PK; manifest URI/hash, object hashes, schema versions, query and exclusions |
| experiments | experiment_id PK; model/baseline/folds, config hash, metrics, sample counts, uncertainty, ablations |
| backtests | run_id PK; predictions, cost/latency/fill policy, eligible orders/fills/no-fills, return/excursion results |

Large raw payloads are stored by hash with durable artifact references; do not put credentials or restricted market-data dumps in GitHub. A prediction must be reproducible from immutable manifests, code and dependencies without refetching mutable live endpoints.

## 9. Modules and contracts

`universe`, `sources/{sec,fda,clinical_trials,issuer,market_data}`, `event_normalization`, `parsers/{earnings,biotech,corporate}`, `event_store`, `calendar`, `price_reactions`, `features`, `fingerprints`, `analogues`, `models/{a,b,c}`, `calibration`, `validation`, `backtesting`, `ranking`, `api`, `tests`, `docs`.

Dependencies flow from adapters to normalized immutable records, then as-of features and outcomes, then research models, then predictions. Adapters never assign investment scores. Feature builders cannot import future outcome tables except through explicit, cutoff-filtered historical aggregate interfaces. Training labels are attached after feature snapshots are sealed.

Provider methods return typed data plus provenance and availability, or typed failures. Extraction accepts source revisions; returns records plus evidence and rejects. Price extraction accepts event/calendar/price snapshots and emits labels plus completeness. Analogue retrieval accepts an as-of feature snapshot and returns actual event IDs, distances and eligible matured outcomes. API later exposes prediction/analogue/model metadata with explicit task, timestamps, states and missingness; no trading endpoint exists.

## 10. Fingerprints, analogues and modeling

First compute broad event-category and sector base rates. Ticker statistics use only earlier matured events; report sample counts and uncertainty. Use partial pooling/shrinkage instead of a ticker-specific model when sparse. Similarity feature transforms, missing-value handling, weights and neighbor count must be fitted or selected only inside training folds. Do not select analogues based on their realized returns.

Expose each analogue's ticker/security, date, event category, source, distance, feature values and outcomes. Weighted samples require effective sample size in addition to raw count. Sparse quantiles are suppressed or marked unreliable. Correlated event clusters do not inflate sample counts.

Progression: category base rates; logistic and linear/quantile baselines; optional tree models; calibrated ensembles only with incremental out-of-sample evidence. Fingerprint/analogue/market-structure/regime/text features each face ablation. No deep learning, arbitrary catalyst score, SHAP package, or production thresholds are implemented in Milestone 0. Later SHAP or coefficient explanations describe model associations, not causal effects.

## 11. Validation and anti-leakage protocol

Chronological expanding/rolling walk-forward folds are mandatory. Each fold has ordered training, hyperparameter selection, calibration and test periods. Fit preprocessing, imputers, embeddings adapted to data, analogue transforms, feature selection and calibration inside the permitted training pipeline. Test windows remain untouched during model selection. Freeze a final chronological holdout before iterative research; log every experiment and holdout access.

Purge training examples whose label windows cross later partition boundaries. Impose an embargo at least covering the maximum configured 20-session target horizon where required by the split. Keep event clusters together; additionally report dependence-aware issuer/date-block uncertainty. Train only on labels mature by the simulated model-fit time. Forward paper validation uses actual ingestion time and frozen versions.

Report PR-AUC, precision/recall, Brier score and reliability bins with counts, precision@K by decision date, false positives/negatives, quantile coverage and loss, baseline-relative lift, and expected return by score decile. ROC-AUC is supplementary. Confidence intervals must reflect clustering and rare positive counts; raw accuracy is not a promotion metric. Ensure monotonic probabilities across nested thresholds and ordered quantiles.

Comparisons: event-category and sector rates; simple surprise; RVOL-only; momentum-only; seeded random ranking with the same eligibility universe. Evaluate feature ablations without retuning against test outcomes. Report market regimes, liquidity/capitalization strata, sectors, missing-data cohorts, delisted issuers, and results with top winners removed. Treat these as robustness diagnostics, not opportunities to select only favorable slices.

Promotion requirements for later milestones: preregister horizons, eligible universe, capacity and confidence cutoff on development data; show improvement over strongest relevant baseline with uncertainty; calibration compatible with forecast usage; positive incremental economics under conservative costs; no unresolved leakage defects; explain tail dependence and regime weakness. Exact economic and precision cutoffs must be frozen before the final holdout is examined. No arbitrary performance guarantee is implied.

## 12. Execution realism and cost sensitivity

Predictions are research signals. Backtesting records a hypothetical executable price after decision latency, using spread/quotes where available. Never fill at an event's pre-release price, a stale last trade, or the session high. Reject fills during halts, unsupported sessions or insufficient liquidity; model order capacity and partial/no fills. Bars with unknown stop/target order require conservative ordering or exclusion.

Proposed diagnostic grid: 0, 10, 25 and 50 basis points additional slippage per side, plus measured spread, fees and latency. These are sensitivity scenarios, not claims that low-float premarket execution costs are covered. Add empirically measured or wider stressed cases when justified. Without historical quotes, report bounded price-reaction research and identify execution validation as incomplete. Report fill rate, turnover, capacity, costs, adverse excursions, and uncertainty; do not present unfillable returns as alpha.

## 13. Confidence, abstention and operations

Confidence combines held-out calibration support, analogue effective sample, data completeness, drift, model agreement and timestamp quality. HIGH/MODERATE/LOW thresholds must be configured and validated later. A model score alone cannot generate HIGH confidence.

Use separate response states: `QUALIFIED`, `NO_QUALIFIED_OPPORTUNITY`, `INSUFFICIENT_DATA`, `SOURCE_UNAVAILABLE`, `MODEL_NOT_VALIDATED`. Technical failure must not masquerade as a completed negative scan. Suppress opportunity output for stale quotes, ambiguous release time, unsupported security/feed, excessive spread, poor liquidity, uncalibrated model or material missingness. Store reason codes.

Structured logs record run/correlation IDs, requests and provider errors, revisions, as-of decisions, source hashes, exclusions, features, model/analogue versions, probabilities, confidence and reasons. Credentials are redacted. Use bounded retries/backoff, idempotent ingestion and deterministic replay. Monitor schema drift, duplicates, delayed delivery, missing bars, feature drift and mature-label calibration. Models are immutable and require explicit promotion; failures roll back by version rather than overwriting history.

## 14. Test and acceptance matrix

| Risk | Required future validation |
|---|---|
| Release clock errors | Fixtures for premarket, intraday, exact bell, after-hours, weekend, holiday, early close, DST, ambiguous/date-only time |
| Leakage | Inject future filing/consensus/float/short interest and ensure exclusion; reject future analogue labels; test delayed delivery and revised sources |
| Identity/survivorship | Renamed/reused ticker, multiple classes, IPO, delisting, merger, unknown security type |
| Price integrity | Split/dividend, missing minute, partial bar, halt, stale quote, provider/feed mismatch, delayed quote |
| Extraction errors | Zero/negative consensus, GAAP mismatch, guidance intervals, units/currencies, duplicate releases and conflicting documents |
| Target contamination | Same-day close after release, intraday pre-event high, already-filled C gap, unknown bar ordering, incomplete 20-session horizon |
| Reproducibility | Same immutable manifest/config produces identical canonical rows and hashes; changed source revision creates a new snapshot |
| Abstention | Outage, sparse analogues, stale quotes and unvalidated model emit explicit states and null predictions |

Milestone 0 validation is document/scope consistency only. These tests are specified for future implementation; none are claimed to have run. No model CI, backtest, dataset or calibration result exists from this task.

## 15. Recommended Milestone 1 scope — requires explicit approval

Build an earnings-first, reproducible event-to-reaction dataset with no predictive scoring. Begin with SEC Item 2.02 candidate filings and associated releases, verifying first-public timestamps against available source evidence. Use a fixed, preregistered recent completed window with enough subsequent sessions for the longest target; enumerate candidate events before inspecting returns. An initial engineering sample of at least 100 eligible events across at least 25 issuers is a functional acceptance target, not statistical power for predictive claims. If coverage cannot support it, report the failure without quietly substituting winners or current survivors.

Deliver: package/CLI and locked environment; universe snapshots and security identity records; normalized event/source schema and migrations; SEC/issuer ingestion; one verified permitted price adapter or clearly labeled offline input; exchange calendar; daily reaction labels, with intraday labels only when supported; immutable dataset manifest; exclusion/missingness report; parser/clock/leakage/replay tests; documentation and CI.

Acceptance: every eligible outcome traces to a timestamped source, security, price feed and return denominator; every candidate is accounted for as included/excluded/quarantined; rerun is deterministic; injected future information cannot change earlier feature snapshots; no missing outcome is treated as zero; two independent spot-checks of each major timing class reconcile to source documents and prices. Report engineering sample limitations and unresolved historical-universe completeness.

Later milestones remain sequential: M2 fingerprints/analogues; M3 extraction/intelligence; M4 baseline models; M5 calibrated advanced comparisons; M6 reaction gap; M7 ranking; M8 forward paper validation; M9 downstream contracts. Each requires authorization at its boundary.

## 16. Open risks and completion boundary

Critical implementation risks are trustworthy historical first-public timestamps, permitted historical price coverage, and as-of security identity/universe reconstruction. Repository identification and access are resolved. Important limitations include absent historical consensus and market-structure vintages, sparse extreme moves, event clustering, provider latency, feed mismatch, halted securities, selection bias and future revisions.

Free/public inputs may support a valuable reproducible research dataset before they support an immediate-news production system. If a required field cannot be verified, narrow the declared estimand or abstain; do not manufacture a complete-looking result. Repository audit and design are complete. Milestone 0 delivery requires publication and exact GitHub verification of these documents; the accompanying delivery report records that evidence. Milestone 1 is not authorized by this document.
