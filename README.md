# NRE 1.0 — US News Reaction & Gap Opportunity Engine

Independent research system for estimating conditional market reactions to corporate news and identifying potential underreaction or overreaction.

## Project status

The owner has accepted Milestones 1–5. NRE includes an audited earnings event dataset, reaction fingerprints and analogues, catalyst extraction, and chronological comparisons of baseline and advanced predictive models. The accepted model research established no predictive edge and promoted no advanced models.

| Milestone | Status and evidence |
| --- | --- |
| 1 · Historical event dataset | Accepted. The initial cohort met the amended sample and structural audit requirements. [Acceptance](reports/m1-acceptance-declaration-2026-09-26.json) · [Final audit](reports/m1-consolidated-audit-final-2026-09-26.json) |
| 2 · Reaction fingerprints | Accepted. Later dataset expansion was accepted separately. [Acceptance](reports/m2-acceptance-declaration-2026-09-29.json) · [Expansion acceptance](reports/m2-step3-acceptance-declaration-2026-10-02.json) |
| 3 · News and catalyst intelligence | Accepted. [Acceptance](reports/m3-acceptance-declaration-2026-09-30.json) |
| 4 · Baseline predictive models | Accepted. No predictor was distinguishable from the pooled base rate. [Acceptance](reports/m4-acceptance-declaration-2026-10-08.json) · [Report](docs/M4-REPORT.md) |
| 5 · Advanced models | Accepted. The 43-event forward extension was opened once under the frozen protocol. Zero targets were promoted. [Acceptance](reports/m5-acceptance-declaration-2026-11-14.json) · [Report](docs/M5-REPORT.md) |
| 6 · Reaction Gap Engine | Research closeout acknowledged. The engine is deferred and the proposed 2027 study is on hold. [Closeout](docs/M6-RESEARCH-CLOSEOUT.md) · [Owner acknowledgment](reports/m6-research-closeout-acknowledgment-2026-11-15.json) |
| 7 · Real-Time Candidate Ranking | Pending a validated reaction-gap signal and engine. |
| 8 · Paper-Trading Validation | Pending forward validation using realistic entries and slippage. |
| 9 · Integration Contracts | Pending independent validation and documented handoffs to SOE, BOE and IEE. |

The latest Milestone 6 comparison found that adding quarterly revenue growth increased mean squared forecast error by 15.15% against the opening-gap baseline on 51 clean paired development events. Further signal research starts with verifying point-in-time input coverage and variation. A historical validation would require an untouched cohort and matched official opening evidence. [Revenue coverage](docs/M6-REVENUE-COVERAGE.md) · [Revenue result](docs/M6-REVENUE-RESULT.md)

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

## Validation status

The test suite covers schemas, timestamps, leakage, prices, ingestion and replay. GitHub Actions runs tests and the synthetic CLI build on Python 3.12/3.13. See the exact commit's Actions checks for CI status; test success does not establish real-data acceptance or predictive performance.
