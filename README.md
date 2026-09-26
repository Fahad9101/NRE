# NRE 1.0 — US News Reaction & Gap Opportunity Engine

Independent research system for estimating conditional market reactions to corporate news and identifying potential underreaction or overreaction.

## Current boundary

Milestone 1 authorized: earnings event dataset engineering is implemented; the acceptance sample is assembled (22 eligible events across 22 issuers), all 16 structural audit gates pass, and **the project owner declared Milestone 1 accepted on 2026-09-26**. The repository includes a standard-library Python pipeline, source ingestion, daily reaction extraction, point-in-time checks, immutable snapshots, SQLite schema, tests and CI. No predictive engine, validated edge, trading execution or production ranking exists. Milestone 2 step 1, which only describes the accepted events, is built and awaits the owner's review (see below).

## Documents

- [Technical implementation contract](docs/MILESTONE-0-TECHNICAL-CONTRACT.md): architecture, taxonomy, schemas, point-in-time methodology, target definitions, source plan, validation and risks.
- [Original master build prompt](docs/NRE-1.0-MASTER-PROMPT.md): governing scope and sequential milestone authorization.
- [Milestone 1 runbook](docs/MILESTONE-1-RUNBOOK.md): commands, reviewed input format, target semantics, limitations and acceptance requirements.
- [Milestone 1 validation evidence](reports/milestone-1-validation.json): live source capability and historical acceptance status.
- [Milestone 2 scope proposal](docs/M2-SCOPE-PROPOSAL.md): the step 1 scope the owner confirmed, what the data can support, and the step 2 options.
- [Milestone 2 runbook](docs/MILESTONE-2-RUNBOOK.md): commands, how to read the outputs, the point-in-time rule and the limits.

## Model separation

- A: pre-catalyst probability distributions.
- B: immediate-news expected reaction, the primary research question.
- C: continuation and fade after an observed gap.

IEE v1.7.2, SOE and BOE frozen rules remain protected. Integration is deferred to Milestone 9. NRE does not place trades or size positions.

## Run locally

```bash
python -m unittest discover -s tests -v
python -m nre build tests/fixtures/synthetic_bundle.json --output data/snapshots
```

Python 3.12+ and IANA timezone data are required. No Docker, API subscription or runtime Python packages are required. Fixtures are synthetic and must not be interpreted as historical market observations.

## Milestone 1 status

Declared accepted by the project owner on 2026-09-26 ([declaration](reports/m1-acceptance-declaration-2026-09-26.json)). The amended target (20 events across 15 issuers) is met by 22 eligible events across 22 issuers, and the formal audit's 16 structural gates all pass ([final audit record](reports/m1-consolidated-audit-final-2026-09-26.json), [assessment](docs/M1-READINESS-ASSESSMENT.md)). The engine's `milestone_accepted` flag stays false by design. No predictive scoring exists.

## Milestone 2 status

The project owner replied "approve" on 2026-09-26 to a two-step plan and then confirmed the [scope proposal](docs/M2-SCOPE-PROPOSAL.md) for step 1 with all six of its defaults ([approval record](reports/m2-authorization-2026-09-26.json), [confirmation record](reports/m2-scope-confirmation-2026-09-26.json)). Step 1, reaction fingerprints and analogue retrieval on the existing 23 events with leakage tests and sparse-data suppression, is built ([runbook](docs/MILESTONE-2-RUNBOOK.md), [build record](reports/m2-step-1-build-record-2026-09-26.json)) and awaits the owner's review. It describes the accepted events and predicts nothing, and with one event per issuer most answers are "insufficient data". Milestone 2 is not accepted, and step 2, the data-depth push, is a separate decision that has not been made.

## Validation status

The test suite covers schemas, timestamps, leakage, prices, ingestion and replay. GitHub Actions runs tests and the synthetic CLI build on Python 3.12/3.13. See the exact commit's Actions checks for CI status; test success does not establish real-data acceptance or predictive performance.
