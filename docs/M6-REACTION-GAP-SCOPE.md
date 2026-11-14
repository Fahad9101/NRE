# Milestone 6 — Reaction Gap Engine scope proposal

**Status:** For owner review. Milestone 5 is [accepted](../reports/m5-acceptance-declaration-2026-11-14.json). This proposal covers a historical research engine and a separately authorized fresh-data study.

## 1. Expected and observed reaction

Start with premarket and after-hours earnings releases from the previously accepted issuer universe. Freeze the universe, eligible filing rules, calendar, source and cohort dates before enumeration. Use the first eligible regular session after the release. The decision clock is the availability of that session's verified opening print, with after-hours and premarket events defined by the existing event contract.

Use the previous regular close as the common anchor. The observation is the opening return from that close. The expectation is the arithmetic mean of historical first-session close returns from the same anchor, pooled across qualifying earnings events. Freeze the expectation at the recorded pre-open news cutoff so the opening observation does not enter its own benchmark. Only earlier reaction sessions and outcomes mature strictly before that cutoff enter the pool. Keep the 10th, 50th and 90th empirical close-return quantiles with the mean and sample counts. The quantiles describe dispersion in historical event outcomes. Their coverage must be measured separately.

This is a new use of a simple pooled benchmark, motivated by the [M4 baseline results](M4-REPORT.md) and [M5 promotion results](M5-REPORT.md). The previous work establishes the case for starting simple. The benchmark's close-return expectation and the utility of the resulting gap still need prospective evidence.

For expected close return μ and observed opening return g, record the gap in percentage points as 100 × (μ − g). Record the corresponding residual expected return from the opening price as (1 + μ) / (1 + g) − 1. Transform the expectation quantiles with the same denominator. A positive gap means the open is below the benchmark expectation and a negative gap means it is above. These are research flags for possible underreaction or overreaction. The model does not identify the cause of a deviation.

## 2. When to withhold a flag

Proposed initial defaults are a pool of at least 60 clean, deduplicated economic events covering at least 20 distinct reaction sessions and 15 issuers. Require an absolute gap of at least two percentage points and an observed opening return strictly outside the empirical 10th–90th percentile close-return range. Use a single pooled window that expands until the fresh-study freeze, then stays fixed throughout that study. Specify the quantile implementation and exact boundary behavior in pre-registration. Report all eligible observations and their flags or abstention reasons.

Abstain for unverified release or opening-print timestamps, an ambiguous session assignment, stale or missing observations, unresolved halts or corporate actions, incomplete lineage, or competing catalysts already known at the flag clock. Freeze provenance and quality rules before the fresh study. If the daily source cannot verify the opening observation or its availability at the intended clock, use it only for offline arithmetic checks and defer empirical validation until an authorized source can verify the clock. Daily OHLC cannot establish an executable price at the decision time. Report data sufficiency for timing regimes and both gap directions. Keep liquidity and executable-quote assessment as separate prerequisites for any later use.

Use information known at the flag clock for flag eligibility. A confounding catalyst first disclosed after the flag can mask the close outcome in the registered clean-window analysis. Retain that observation and its reason in the coverage accounting, and report an all-event sensitivity.

## 3. Fresh validation

Treat the 128 M4/M5 development events as development history. The 43-event M5 forward extension has already been opened. Use the published M5 aggregate record as scoping evidence. If a separately authorized development build uses any historical outcome data, retain its provenance and avoid reusing it as confirmatory evidence.

Register a fresh chronological cohort whose events occur after the protocol and collection rules are frozen. Record every eligible filing, exclusions, the forecast and timestamp, the flag and its availability time, before examining that event's close outcome. Group same-session events and related disclosures, and prevent future labels, price revisions and test examples from changing the locked benchmark. Freeze the end date up front and report insufficient support if the cohort ends before reaching the registered minimum.

Primary outcome is the reaction-session close divided by the verified opening reference minus one. Define the directional score as the sign of the reaction gap times that opening-to-close return. Positive scores mean the price moved in the direction of the pre-open expectation. The proposed primary contrast is the mean paired improvement in this score over a simple opening-gap fade rule, applied to the same flagged rows. Register zero-gap handling, a direction-neutral reference, and same-clock opening-gap comparators before validation. Report unflagged coverage separately to show how selective the flag rule is. A positive directional mean alone is insufficient because the pooled gap can closely resemble a fade rule.

Report event and issuer/session counts, direction-specific support, predictive interval coverage, mean and median residual returns, and paired differences with issuer- and session-clustered confidence intervals. Use a single 99% primary interval envelope and report whether its lower bound exceeds zero. Require a positive directional mean as well. Supporting diagnostics are descriptive. Before authorizing collection, propose a fixed horizon, minimum flagged counts and cluster support for each direction using development-only coverage and variance estimates, a practically meaningful effect and stated power assumptions. A broad interval or thin support yields an inconclusive or counts-only result. Study results describe price-reference returns, with execution economics reserved for later validation.

## 4. Work and decision boundaries

| Step | Deliverable |
| --- | --- |
| A. Pre-register | Freeze the cohort and data source, measurement clock, support and quality gates, fixed study duration, comparators and claim rule. |
| B. Build and test | Historical engine with forecast and observation lineage, quality states and snapshot IDs. Test common anchors, maturity, corporate actions, exact boundaries, deterministic replay and injected future information. |
| C. Fresh study | Verify data rights and timestamp coverage, collect the pre-registered cohort and issue one aggregate report with coverage, attrition, uncertainty and discrepancies. |

Recommended owner decision is to authorize Step A with the pooled benchmark, one opening snapshot and one close target. Step A should bring back the proposed cohort dates and precision requirements before acquisition. Subsequent build and data collection require their own authorization. A technically complete engine with inconclusive evidence is a valid Milestone 6 result. Real-time ranking, paper-trading validation and downstream integration have their own milestones.
