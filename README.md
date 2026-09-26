# NRE 1.0 — US News Reaction & Gap Opportunity Engine

Independent research system for estimating conditional market reactions to corporate news and identifying potential underreaction or overreaction.

## Current boundary

Milestone 1 authorized: earnings event dataset engineering is implemented; the acceptance sample is assembled (22 eligible events across 22 issuers) and all 16 structural audit gates pass, but Milestone 1 acceptance has **not been declared** by the project owner. The repository includes a standard-library Python pipeline, source ingestion, daily reaction extraction, point-in-time checks, immutable snapshots, SQLite schema, tests and CI. No predictive engine, validated edge, trading execution or production ranking exists.

## Documents

- [Technical implementation contract](docs/MILESTONE-0-TECHNICAL-CONTRACT.md): architecture, taxonomy, schemas, point-in-time methodology, target definitions, source plan, validation and risks.
- [Original master build prompt](docs/NRE-1.0-MASTER-PROMPT.md): governing scope and sequential milestone authorization.
- [Milestone 1 runbook](docs/MILESTONE-1-RUNBOOK.md): commands, reviewed input format, target semantics, limitations and acceptance requirements.
- [Milestone 1 validation evidence](reports/milestone-1-validation.json): live source capability and historical acceptance status.

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

## Remaining Milestone 1 work

The project owner's declaration that Milestone 1 is accepted, made outside the code. The amended target (20 events across 15 issuers) is met on record by 22 eligible events across 22 issuers, and the formal audit's gates all pass ([final audit record](reports/m1-consolidated-audit-final-2026-09-26.json), [assessment](docs/M1-READINESS-ASSESSMENT.md)). No predictive scoring in Milestone 1; Milestone 2 requires separate approval.

## Validation status

The test suite covers schemas, timestamps, leakage, prices, ingestion and replay. GitHub Actions runs tests and the synthetic CLI build on Python 3.12/3.13. See the exact commit's Actions checks for CI status; test success does not establish real-data acceptance or predictive performance.
