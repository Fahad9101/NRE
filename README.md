# NRE 1.0 — US News Reaction & Gap Opportunity Engine

Independent research system for estimating conditional market reactions to corporate news and identifying potential underreaction or overreaction.

## Current boundary

Milestone 0: repository audit and research design. Documentation only; no predictive engine, validated edge, dataset, trading execution or production ranking exists. Milestone 1 requires explicit user approval.

## Documents

- [Technical implementation contract](docs/MILESTONE-0-TECHNICAL-CONTRACT.md): architecture, taxonomy, schemas, point-in-time methodology, target definitions, source plan, validation and risks.
- [Original master build prompt](docs/NRE-1.0-MASTER-PROMPT.md): governing scope and sequential milestone authorization.

## Model separation

- A: pre-catalyst probability distributions.
- B: immediate-news expected reaction, the primary research question.
- C: continuation and fade after an observed gap.

IEE v1.7.2, SOE and BOE frozen rules remain protected. Integration is deferred to Milestone 9. NRE does not place trades or size positions.

## Recommended next milestone

An earnings-first historical event dataset with verified release timing, security identity, permitted price data, explicit missingness, reproducible reaction labels and leakage tests. No predictive scoring in Milestone 1.

## Validation status

Milestone 0 document consistency and original-prompt preservation are checked before publication. No implementation tests apply yet. GitHub Actions is not configured; absence of checks is not a successful test run. See the delivery report for the verified remote commit.
