# MASTER BUILD PROMPT

## US News Reaction & Gap Opportunity Engine — NRE 1.0

You are taking ownership of building a production-grade **US News Reaction & Gap Opportunity Engine**, abbreviated **NRE 1.0**.

The purpose of this system is **not to claim deterministic prediction of tomorrow’s gap-up stocks**.

Its purpose is to identify and rank U.S.-listed equities where a new or upcoming catalyst creates an unusually favorable **conditional probability of a large price move**, based on:

1. the magnitude and surprise of the news,
2. historical reactions to comparable events,
3. the individual ticker’s historical reaction fingerprint,
4. market structure and positioning,
5. current market regime,
6. and the difference between the model-implied reaction and the price reaction already observed.

The central hypothesis is:

> **A tradeable edge may exist when the historical expected reaction to new information is materially larger than the market reaction observed so far.**

The system must be built scientifically, point-in-time correctly, reproducibly, and without look-ahead leakage.

---

# 1. PRIMARY OBJECTIVE

Build an engine capable of answering three separate questions.

## Model A — Pre-Catalyst Opportunity Model

Before a scheduled catalyst:

> Which U.S. stocks have an unusually high probability of experiencing a large absolute or positive price movement following an upcoming catalyst?

Examples:

- earnings
- FDA PDUFA
- FDA Advisory Committee
- expected regulatory decisions
- scheduled clinical-trial readouts
- major medical congress presentations
- investor days
- major product announcements
- court decisions when scheduled
- major contract decisions where timing is reasonably known

This model must not assume the catalyst will be positive.

It should estimate probabilities such as:

- P(|move| ≥ 5%)
- P(|move| ≥ 10%)
- P(|move| ≥ 20%)
- P(up move ≥ 10%)
- P(down move ≥ 10%)

Direction should only be modeled when sufficient evidence exists.

---

# 2. MODEL B — IMMEDIATE NEWS REACTION MODEL

This is the primary model.

Once material news becomes public:

> How large should the stock reasonably react to this specific information?

The system must compare:

### Expected reaction

versus

### Observed reaction

and calculate:

```math
Reaction\ Gap = Expected\ Reaction - Observed\ Reaction
```

The core opportunity is:

```math
Expected\ Reaction \gg Observed\ Reaction
```

This may indicate an **underreaction**.

Likewise:

```math
Observed\ Reaction \gg Expected\ Reaction
```

may indicate:

- overreaction,
- chase risk,
- poor risk/reward,
- or likely mean reversion.

The system must never assume every positive catalyst deserves buying.

---

# 3. MODEL C — GAP CONTINUATION / FADE MODEL

For a stock that has already moved significantly:

> What is the probability that the gap continues, holds, or fades?

Outputs should include:

- probability gap remains ≥50% intact by close,
- probability of full gap fill,
- probability of another ≥5% extension,
- probability of another ≥10% extension,
- expected Day-1 maximum excursion,
- expected Day-1 close,
- expected 2–5 day continuation,
- expected retracement before continuation.

This must be a separate model from the initial-news model.

Do not combine all three problems into one classifier.

---

# 4. SYSTEM PHILOSOPHY

The engine should optimize for:

> **precision over quantity**

It is acceptable—and desirable—for the system to return:

> NO QUALIFIED OPPORTUNITY

on many trading days.

Do not optimize for producing daily trade ideas.

Optimize for identifying rare situations where the historical conditional probability and expected payoff are materially favorable.

Avoid building a generic momentum scanner.

---

# 5. UNIVERSE

Initial universe:

- U.S.-listed common stocks
- NASDAQ
- NYSE
- NYSE American

Initially exclude unless specifically useful:

- ETFs
- closed-end funds
- preferred shares
- warrants
- SPAC units
- OTC securities

Maintain sufficient metadata to identify:

- ticker
- company name
- exchange
- sector
- industry
- market cap
- shares outstanding
- public float
- security type

The architecture should permit later filters based on liquidity and market capitalization.

---

# 6. EVENT / NEWS TAXONOMY

Every material event must be normalized into a structured taxonomy.

At minimum:

## Earnings

Capture:

- EPS actual
- EPS consensus
- EPS surprise %
- revenue actual
- revenue consensus
- revenue surprise %
- gross margin
- operating margin
- EBITDA where meaningful
- FCF
- guidance
- prior guidance
- consensus guidance
- guidance raise/cut
- management commentary
- major one-time items

---

## Biotechnology / Pharmaceuticals

Capture:

- trial phase
- indication
- primary endpoint
- secondary endpoints
- statistical significance
- effect size
- clinical significance
- safety
- discontinuations
- dose response
- subgroup findings
- comparator
- regulatory status
- FDA decision
- CRL
- approval
- label breadth
- PDUFA
- AdCom outcome
- competitor read-through
- TAM implications
- partnership/licensing
- milestone payment
- financing/dilution implications

Clinical success must not automatically be scored as economically transformational.

Separate:

**scientific success**

from

**economic significance**.

---

## General Corporate Events

Capture:

- acquisitions
- divestitures
- major contracts
- customer wins/losses
- partnerships
- restructurings
- CEO/CFO changes
- legal judgments
- regulatory decisions
- product launches
- major capital expenditure
- buybacks
- special dividends
- debt refinancing
- bankruptcy/restructuring risk
- strategic reviews

---

## Capital Markets Events

Capture:

- secondary offerings
- ATM activity
- convertible issuance
- debt issuance
- share repurchases
- insider transactions
- lockup expirations
- major institutional ownership changes

---

# 7. NEWS SURPRISE ENGINE

Do not simply classify news as:

- positive
- neutral
- negative

Build a structured **News Surprise / Catalyst Strength** framework.

Potential variables include:

- magnitude versus consensus
- magnitude versus previous guidance
- direction of revision
- novelty
- economic significance
- scientific significance
- confidence/quality of evidence
- reversibility
- expected duration of effect
- addressable market impact
- dilution consequences
- balance-sheet consequences
- competitive implications

Produce structured features.

Example:

Catalyst type: Phase III clinical result
Scientific significance: 94/100
Commercial significance: 78/100
Unexpectedness: 89/100
Safety quality: 87/100
Dilution risk: 20/100
Overall catalyst strength: derived systematically

Do not rely exclusively on opaque LLM-generated scores.

LLMs may extract and normalize information, but scoring rules and downstream models must be testable and auditable.

---

# 8. TICKER REACTION FINGERPRINT

One of the most important components is a historical **Reaction Fingerprint** for each ticker.

For every material historical event, store:

- ticker
- event date/time
- source
- event category
- event subtype
- event sentiment
- surprise magnitude
- catalyst strength
- release timing:
  - premarket
  - regular session
  - after-hours
- pre-event price
- initial after-hours/premarket move
- opening gap
- first 5-minute return
- first 15-minute return
- first 30-minute return
- first 60-minute return
- Day-1 high
- Day-1 low
- Day-1 close
- 2-day return
- 5-day return
- 10-day return
- 20-day return
- maximum favorable excursion
- maximum adverse excursion
- gap retention
- gap fill
- volume
- relative volume
- pre-event ATR
- pre-event trend
- previous resistance
- distance from 52-week high
- float
- short interest where available
- institutional ownership where available
- options-related variables where reliable data exists
- sector performance
- SPY/QQQ performance
- market regime

The engine should learn whether individual companies historically:

- underreact initially,
- overreact initially,
- gap and fade,
- gap and trend,
- react strongly to earnings,
- react weakly to earnings,
- respond disproportionately to regulatory events,
- respond disproportionately to clinical data,
- or exhibit no stable identifiable pattern.

Do not force a ticker-specific model where sample size is inadequate.

Use hierarchical/generalized models where appropriate.

---

# 9. HISTORICAL ANALOGUE ENGINE

Build a nearest-neighbor / similarity system to answer:

> What historically comparable events have occurred?

Comparable dimensions may include:

- event category
- event subtype
- surprise magnitude
- catalyst strength
- sector
- industry
- market cap
- float
- short interest
- liquidity
- valuation
- prior momentum
- distance from highs
- market regime

For each new event return:

- number of historical analogues
- median opening gap
- median Day-1 high
- median Day-1 close
- 25th/75th percentile
- 10th/90th percentile when sample permits
- 5-day median
- continuation probability
- gap-fill probability

The analogue system must expose the actual historical events used.

No black-box statement such as:

> “Historical data suggests +25%.”

The user must be able to inspect the analogue sample.

---

# 10. MARKET STRUCTURE FEATURES

Include, where reliable and available:

- market capitalization
- float
- shares outstanding
- average daily dollar volume
- premarket volume
- relative volume
- short interest
- days to cover
- institutional ownership
- insider ownership
- ATR
- realized volatility
- implied volatility where feasible
- call/put activity where feasible
- options open interest
- gamma-related variables only if sufficiently reliable
- recent price compression
- breakout structure
- resistance zones
- support zones
- previous gaps
- distance from VWAP
- distance from major moving averages
- distance from 52-week high/low

The system should test whether combinations such as:

> strong catalyst + low float + high short interest + extreme RVOL

historically produce non-linear price reactions.

Do not assume they do.

Validate empirically.

---

# 11. MARKET REGIME

Event reactions may differ across regimes.

Capture variables such as:

- SPY trend
- QQQ trend
- Russell 2000 trend
- VIX
- sector ETF behavior
- breadth
- risk-on/risk-off environment
- recent small-cap momentum
- recent biotech momentum where applicable

Test interaction effects.

---

# 12. TARGET VARIABLES

Do not use only a binary UP/DOWN target.

Construct multiple targets.

Examples:

### Opening-gap targets

- ≥3%
- ≥5%
- ≥10%
- ≥15%
- ≥20%
- ≥30%

### Day-1 targets

- high ≥10%
- high ≥20%
- high ≥30%
- close ≥10%
- close ≥20%

### Continuation

- additional +5% after open
- additional +10% after open
- 5-day return ≥10%
- 5-day return ≥20%

### Fade

- loses ≥50% of opening gap
- full gap fill
- closes below opening price

### Regression targets

Also model:

- expected opening gap
- expected Day-1 maximum
- expected Day-1 close
- expected 5-day return

Return probability distributions where possible rather than only point estimates.

---

# 13. MODEL OUTPUT

A candidate result should eventually resemble:

Ticker: XYZ

Catalyst:
Phase III clinical-trial result

Catalyst strength:
92/100

Comparable historical events:
143

Model estimates:

P(gap >5%): 91%
P(gap >10%): 78%
P(gap >20%): 48%
P(gap >30%): 26%

Expected opening move:

+14% to +22%

Expected Day-1 range:

+9% to +31%

Observed premarket move:

+7.4%

Model-implied underreaction:

+8.6% to +14.6%

Gap-retention probability:

73%

P(+20% within 5 sessions):

58%

Historical analogue count:

143

Confidence:

HIGH / MODERATE / LOW

Reasons:

- large positive surprise
- strong comparable historical reactions
- unusually high RVOL
- limited float
- high short interest
- favorable sector regime

Risks:

- catalyst partly anticipated
- valuation stretched
- prior run-up
- financing overhang

The model must explicitly state when confidence is low.

---

# 14. REACTION GAP

Create a formal metric for:

```math
Expected\ Reaction - Observed\ Reaction
```

This is a central candidate-ranking feature.

Potential implementation:

### Expected reaction

Derived from:

- probabilistic model
- historical analogue distribution
- ticker reaction fingerprint

versus:

### Observed reaction

Measured from:

- after-hours
- premarket
- opening gap
- intraday price

The engine should distinguish between:

- genuine underreaction,
- delayed price discovery,
- insufficient liquidity,
- stale quote,
- already priced-in news,
- excessive overreaction.

---

# 15. DATA SOURCES

Prefer reliable and reproducible sources.

Use free/public sources wherever practical during development.

Potential sources include:

## SEC

Use official SEC EDGAR data for:

- 10-K
- 10-Q
- 8-K
- Forms 3/4/5
- 13D/13G
- 13F where relevant
- registration statements
- offering documents

Respect SEC rate limits and user-agent requirements.

---

## FDA

Use official FDA sources for:

- approvals
- CRLs when publicly disclosed
- Advisory Committees
- PDUFA-related public information
- labels
- regulatory announcements

---

## ClinicalTrials.gov

Use for:

- trial status
- study design
- enrollment
- endpoints
- expected completion
- historical trial metadata

---

## Issuer Sources

Use:

- investor-relations press releases
- earnings releases
- presentations
- conference materials
- SEC-linked releases

---

## Market Data

During development prefer legally usable free/public sources.

Design provider adapters so better commercial market data can later be substituted without changing model logic.

Never silently use data that violates provider terms.

---

# 16. POINT-IN-TIME CORRECTNESS

This is non-negotiable.

Every training feature must represent only information available at that historical moment.

No:

- future filings,
- revised future consensus,
- later trial interpretation,
- updated float data applied retroactively,
- future short-interest data,
- post-event analyst commentary,
- later company disclosures.

Implement explicit point-in-time leakage tests.

Any model with leakage is invalid.

---

# 17. EVENT TIMESTAMPING

Timestamp accuracy is crucial.

Where possible capture:

- exact publication timestamp
- timezone
- exchange session state

Determine whether the event occurred:

- before market open,
- regular session,
- after market close.

All returns must be measured relative to the actual public information release.

Do not accidentally use same-day closing data for information released after the close.

---

# 18. MODELING APPROACH

Do not begin with deep learning simply because it is available.

Establish baselines first.

Potential progression:

1. heuristic/base-rate models
2. logistic regression
3. linear/quantile regression
4. random forest
5. gradient boosting / XGBoost / LightGBM
6. calibrated ensemble models
7. text embeddings / transformer features where justified

Compare models objectively.

The production model should win on out-of-sample performance, not complexity.

---

# 19. PROBABILITY CALIBRATION

Predicted probabilities must be calibrated.

Use appropriate methods such as:

- Platt scaling
- isotonic regression
- reliability diagrams
- Brier scores

If the model says:

> 70% probability

events in that probability bucket should occur approximately 70% of the time out of sample.

Calibration matters more than flashy classification accuracy.

---

# 20. CLASS IMBALANCE

Large gap events are uncommon.

Handle imbalance appropriately.

Do not optimize raw accuracy.

Primary evaluation metrics should include:

- precision
- recall
- PR-AUC
- ROC-AUC where useful
- calibration
- Brier score
- precision\@K
- expected return by probability decile
- false-positive rate
- false-negative rate
- sample size

For our use case:

> **precision at high-confidence thresholds**

is especially important.

---

# 21. WALK-FORWARD VALIDATION

Do not randomly split historical financial events into training/test data.

Use chronological walk-forward validation.

Example:

Train:

2016–2021

Validate:

2022

Train:

2016–2022

Validate:

2023

Train:

2016–2023

Validate:

2024

and so forth.

Simulate actual deployment conditions.

---

# 22. BACKTESTING

Backtests must include realistic assumptions.

At minimum:

- bid/ask spread
- slippage
- liquidity
- gap execution constraints
- inability to fill at theoretical prints
- premarket versus regular-session execution
- halted securities
- trading suspensions
- low-float distortion

Do not report paper alpha based on impossible fills.

---

# 23. TRANSACTION-COST SENSITIVITY

Run sensitivity analyses at several slippage assumptions.

Example:

- idealized
- modest
- conservative
- stressed

A strategy that disappears under modest transaction costs should not be considered production-ready.

---

# 24. BASE-RATE COMPARISON

Every sophisticated model must be compared with simple baselines.

Examples:

- event-category historical average
- same-sector event average
- simple surprise model
- RVOL-only model
- momentum-only model
- random classifier

The model must demonstrate incremental predictive value.

---

# 25. FEATURE ABLATION

Perform feature-ablation analysis.

Determine what actually contributes value:

- news surprise
- ticker fingerprint
- analogue matching
- float
- short interest
- technical structure
- market regime
- premarket volume
- valuation
- sentiment/NLP

If a feature adds complexity without improving out-of-sample results, remove it.

---

# 26. SHAP / EXPLAINABILITY

Use appropriate explainability methods such as SHAP for tree-based models.

Every high-confidence prediction should have human-readable explanations.

Example:

Prediction elevated primarily because of:

1. catalyst surprise magnitude,
2. historically strong analogue reactions,
3. high relative volume,
4. low float,
5. favorable recent sector behavior.

Avoid opaque model outputs.

---

# 27. CONFIDENCE LEVELS

Produce structured confidence tiers based on:

- calibration,
- analogue count,
- model agreement,
- data completeness,
- feature quality,
- ticker-specific history.

Example:

HIGH

MODERATE

LOW

VERY LOW / INSUFFICIENT DATA

Do not present false precision when the sample is weak.

---

# 28. NO-TRADE / NO-SIGNAL STATE

The engine must support:

> NO QUALIFIED OPPORTUNITY

Reasons can include:

- probability below threshold
- insufficient historical analogues
- poor data quality
- extreme spread
- insufficient liquidity
- catalyst already fully priced
- conflicting models
- excessive downside risk

This is mandatory.

---

# 29. SPECIAL HANDLING FOR BIOTECH

Biotechnology should eventually receive a specialized sub-model because its catalysts behave differently.

The model should distinguish:

- preclinical
- Phase I
- Phase II
- Phase III
- NDA/BLA submission
- AdCom
- PDUFA
- approval
- CRL
- safety signal
- partnership
- licensing
- financing

Do not treat all “positive clinical data” equivalently.

Where practical integrate with the existing Biotech Opportunity Engine / BOE infrastructure later.

Do not modify BOE frozen rules during this project.

---

# 30. RELATIONSHIP WITH EXISTING SYSTEMS

This engine is an **upstream discovery system**.

The conceptual pipeline should be:

US market / news sources
↓
NRE — News Reaction Engine
↓
Catalyst understanding
↓
Historical analogue engine
↓
Ticker reaction fingerprint
↓
Expected move
↓
Observed move
↓
Reaction Gap
↓
Candidate ranking
↓
SOE or BOE where appropriate
↓
Investment Execution Engine

Maintain strict separation of responsibilities.

NRE asks:

> What may move disproportionately because of new information?

SOE / BOE ask:

> Does the opportunity satisfy their own frozen opportunity rules?

IEE asks:

> At what price and under what risk/reward conditions should capital actually be deployed?

Do not merge these engines into one scoring system.

---

# 31. EXISTING ENGINES — NON-NEGOTIABLE PROTECTION

Do not modify any frozen logic, scores, weights, thresholds, classifications, valuation logic, execution rules, technical rules, catalyst rules, or risk logic belonging to:

- Investment Execution Engine v1.7.2
- SOE frozen production rules
- BOE frozen production rules

Integration should occur only through documented APIs/contracts.

NRE must initially be independent.

---

# 32. ARCHITECTURE

Prefer modular architecture.

Potential modules:

- universe/
- news_ingestion/
- sec/
- fda/
- clinical_trials/
- issuer_sources/
- event_normalization/
- catalyst_classifier/
- earnings_parser/
- biotech_parser/
- corporate_event_parser/
- price_data/
- market_structure/
- event_store/
- reaction_fingerprint/
- analogue_engine/
- features/
- models/
- calibration/
- validation/
- backtesting/
- ranking/
- API/
- tests/
- docs/

Keep data acquisition separate from investment logic.

---

# 33. DATABASE

Design a reproducible schema capable of storing:

### Companies

### Securities

### Events

### Event sources

### Catalyst features

### Historical prices

### Intraday prices

### Market structure

### Reaction outcomes

### Analogues

### Model predictions

### Model versions

### Data-quality flags

### Backtest results

Maintain versioning.

Every prediction should be reproducible later.

---

# 34. MODEL VERSIONING

Every prediction must record:

- model version
- feature version
- training-window dates
- data snapshot
- model checksum where appropriate
- prediction timestamp

No silent production model replacement.

---

# 35. TESTING

Implement:

- unit tests
- integration tests
- schema tests
- parser tests
- data-quality tests
- point-in-time leakage tests
- event timestamp tests
- regression tests
- model reproducibility tests

High-risk components require fixture-based tests.

---

# 36. FAILURE HANDLING

Do not invent data.

If a source fails:

- mark it unavailable,
- log the failure,
- degrade confidence,
- continue if appropriate.

Never substitute fabricated values.

---

# 37. OBSERVABILITY

Implement logging sufficient to answer:

> Why did the model produce this candidate?

Store:

- data sources used
- missing data
- feature values
- model probabilities
- analogues
- confidence
- ranking rationale

---

# 38. INITIAL MILESTONE STRUCTURE

Do not attempt everything at once.

Work sequentially.

## Milestone 0 — Repository Audit and Research Design

- inspect repository
- determine current state
- define architecture
- identify data sources
- define target variables
- define point-in-time methodology
- define schemas
- write implementation specification

Do not build production scoring yet.

---

## Milestone 1 — Historical Event Dataset

Build:

- universe
- event schema
- event ingestion
- timestamp normalization
- basic price-reaction extraction
- earnings events first if this provides the cleanest validation dataset

Acceptance:

Historical events can reproducibly be mapped to subsequent market reactions.

---

## Milestone 2 — Reaction Fingerprints

Build:

- company-level event histories
- sector histories
- event-type histories
- reaction statistics
- analogue retrieval

Acceptance:

Given a historical/new event, the system can return defensible comparable historical events and reaction distributions.

---

## Milestone 3 — News/Catalyst Intelligence

Implement:

- structured event extraction
- earnings surprise normalization
- biotech catalyst extraction
- corporate-event normalization
- catalyst-strength features

Acceptance:

Raw public announcements reliably become structured machine-readable event features.

---

## Milestone 4 — Baseline Predictive Models

Build baseline models for:

- opening gap
- Day-1 move
- gap retention
- continuation/fade

Perform walk-forward validation.

No production ranking yet.

---

## Milestone 5 — Advanced Models

Test:

- gradient boosting
- ensembles
- ticker reaction features
- analogue features
- market-structure features
- market-regime features

Perform calibration and ablation studies.

Promote only improvements that survive out-of-sample testing.

---

## Milestone 6 — Reaction Gap Engine

Build:

Expected reaction
versus
Observed reaction.

Generate underreaction and overreaction candidates.

---

## Milestone 7 — Real-Time Candidate Ranking

Produce candidate list with:

- catalyst
- expected move
- actual move
- reaction gap
- probabilities
- confidence
- analogues
- risks

---

## Milestone 8 — Paper-Trading Validation

Run forward paper validation.

Do not modify model using knowledge of future test outcomes without formal versioning.

Collect:

- signal timestamp
- theoretical entry
- realistic executable entry
- peak return
- close return
- 5-day return
- adverse excursion
- slippage

---

## Milestone 9 — Integration Contracts

Only after NRE is independently validated:

define documented handoff to:

- SOE
- BOE
- IEE

Do not alter their internal logic.

---

# 39. ACCEPTANCE CRITERIA

The system is not considered successful merely because historical returns look attractive.

Require evidence that:

1. probabilities are calibrated;
2. high-confidence predictions outperform relevant base rates;
3. results survive chronological out-of-sample testing;
4. no point-in-time leakage exists;
5. performance persists after realistic execution assumptions;
6. results are not driven by a handful of extreme winners;
7. model performance is reasonably stable across market regimes;
8. confidence falls appropriately when data quality is poor;
9. analogue selection is auditable;
10. the system can correctly produce NO SIGNAL.

---

# 40. RISK CONTROLS

Do not turn this into an execution bot yet.

NRE initially provides research signals only.

It must not:

- place trades,
- modify brokerage accounts,
- size positions,
- override SOE/BOE/IEE,
- chase extreme premarket moves,
- infer certainty from a high model score.

Trading/execution remains downstream.

---

# 41. DEVELOPMENT DISCIPLINE

Treat GitHub as the single source of truth.

For every milestone:

1. inspect current repository state;
2. implement only the approved milestone;
3. add tests;
4. run full relevant validation;
5. repair failures coherently;
6. commit changes;
7. push to GitHub;
8. verify CI/GitHub Actions;
9. report exact commit SHA;
10. report remaining limitations;
11. stop at the milestone boundary.

Do not silently move to the next milestone.

Do not leave tested work only locally.

---

# 42. AUTONOMOUS EXECUTION

Within an approved milestone:

Work autonomously.

Do not repeatedly stop to ask me minor implementation questions.

Make reasonable engineering decisions consistent with this specification.

If multiple implementation choices exist:

- prefer reproducibility,
- point-in-time correctness,
- maintainability,
- auditability,
- and empirical validity.

Do not simplify away core requirements merely to finish faster.

---

# 43. RESEARCH DISCIPLINE

For every claimed predictive edge:

ask:

> Does this survive out-of-sample testing?

Not:

> Does this make intuitive sense?

Do not embed beliefs such as:

- high short interest causes squeezes,
- low float causes large gaps,
- strong earnings beats continue,
- biotech approvals always produce sustained gains.

Treat these as hypotheses.

Test them.

---

# 44. ANTI-OVERFITTING REQUIREMENT

Avoid:

- excessive feature engineering on the test set,
- repeated tuning against the same holdout period,
- hindsight event selection,
- survivor bias,
- cherry-picking.

Maintain a final untouched out-of-sample period where practical.

---

# 45. END PRODUCT

The eventual system should answer:

### BEFORE CATALYST

“Which scheduled catalysts deserve attention?”

### IMMEDIATELY AFTER NEWS

“How significant is this information relative to expectations?”

### AFTER INITIAL PRICE REACTION

“Has the market underreacted, appropriately reacted, or overreacted?”

### AFTER GAP

“Is continuation or fade historically more probable?”

And ultimately:

> **Is the expected return distribution sufficiently favorable to hand this candidate to SOE/BOE/IEE for further evaluation?**

---

# 46. FIRST ACTION

Begin with **Milestone 0 only**.

Do the following autonomously:

1. inspect the repository;
2. inspect existing files, branches, issues, PRs and CI;
3. determine whether any implementation already exists;
4. research reliable public/free data sources;
5. define the event taxonomy;
6. define point-in-time data architecture;
7. define targets;
8. define database schema;
9. define module architecture;
10. define validation methodology;
11. identify major technical/data risks;
12. create a detailed NRE 1.0 technical implementation contract;
13. commit and push the Milestone 0 specification to GitHub;
14. verify the GitHub state;
15. report:

- commit SHA,
- files added/changed,
- architecture,
- data-source plan,
- validation design,
- known limitations,
- recommended Milestone 1 scope.

Then STOP.

Do not begin Milestone 1 until I explicitly approve it.

---

# NON-NEGOTIABLE PRINCIPLE

The objective is not:

> “Build an AI that predicts stocks.”

The objective is:

> **Build a scientifically validated event-reaction system that estimates the probability distribution of market reactions to new corporate information and identifies statistically meaningful discrepancies between the reaction history suggests should occur and the reaction the market has actually produced.**

Precision, calibration, point-in-time correctness and reproducibility take priority over producing more signals.