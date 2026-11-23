# Annual guidance comparison: registered decision

The single registered annual-revenue-guidance comparison **failed its development gates**. Adding the fixed guidance-revision feature increased mean squared forecast error by 2.8845% on 51 clean held events. The 99% issuer/session uncertainty envelope crossed zero, and the all-defined sensitivity also had higher error. The registered outcome is `STOP_DEVELOPMENT_GATE_NOT_MET`; this comparison is closed and no model is promoted. [Aggregate result](../reports/m6-guidance-result-2026-11-23.json) · [Registered protocol](../config/m6-guidance-protocol-v2.json)

| Analysis | Held pairs | Baseline MSE | Guidance MSE | Increase in MSE |
| --- | ---: | ---: | ---: | ---: |
| Clean primary | 51 | 0.0018296981 | 0.0018824760 | 2.8845% |
| All-defined sensitivity | 53 | 0.0017546158 | 0.0017685159 | 0.7922% |

MSE measures error in the registered sign-adjusted opening-to-close fade target, in squared fractional-return units. These figures measure forecast accuracy, not portfolio performance. Mean paired clean improvement, defined as baseline loss minus guidance loss, was -0.0000527779. Its outer 99% bootstrap envelope was [-0.0002059986, 0.0000864273]. The intervals do not establish deterioration either; the study did not demonstrate the required improvement.

## Frozen gates and support

All support floors passed. The clean sample covers 19 issuers, 42 reaction sessions, 28 up gaps and 23 down gaps. Its three held folds score 25, 14 and 12 pairs. Their preceding common fit pools have 42, 67 and 81 rows. The sensitivity scores 25, 15 and 13 pairs using preceding fit pools of 50, 75 and 90. There are 36 guidance raises, 12 unchanged revisions and three cuts in the clean held sample. Cut support remains limited to two issuers.

| Registered advancement condition | Observed primary/sensitivity result | Outcome |
| --- | --- | --- |
| At least 5% primary relative MSE reduction | -2.8845% reduction | Failed |
| Strictly positive lower 99% outer interval endpoint | -0.0002059986 | Failed |
| Nonnegative mean improvement in sensitivity | -0.0000139001 | Failed |

The same ridge penalty, transformed feature, training-only population scaling, folds and maturity rules were used in both arms. The two cluster bootstraps each used 5,000 resamples and the registered seeds 640001/640002. No parameter search, additional feature, alternative cohort or second scoring attempt was run.

## Source, acquisition and execution evidence

Before closing labels, the final review applied three additive hard exclusions and one additive soft caveat under the existing rules, preserving earlier frozen masks. The resulting clean source pools had 43 training and 51 held rows. Acquisition withheld one additional training event under the registered price-quality rules, leaving 42 clean training rows and 50 sensitivity training rows. All 103 usable label commitments replayed unchanged before fitting; no provider response-digest changes occurred. [Final source review](../reports/m6-guidance-final-source-review-2026-11-23.json) · [Hash-only acquisition](../reports/m6-guidance-acquisition-2026-11-23.json)

The acquisition-only run used commit `f7ac3e3421db95a7c37bbfeef6c887a4c30b3129`. Its manifest was committed in `eb7b3fb8d70eaccdbb7486f67f9c1462be69a7d1` before scoring. The scoring workflow exclusively created the durable attempt in commit `ce27ec229a5094f92762e05db66dd85147c702da`, then fitted the registered comparison once against the committed acquisition. The attempt file remains immutable. [Acquisition run](https://github.com/Fahad9101/NRE/actions/runs/45177816805) · [Sole scoring run](https://github.com/Fahad9101/NRE/actions/runs/45178617120) · [Attempt](../reports/m6-guidance-attempt-v2-001.json) · [Run metadata](../reports/m6-guidance-result-run-2026-11-23.json)

Run `python -m nre.m6_guidance_result_audit` to verify the protocol/code/source chain, attempt/acquisition bindings, fit and test memberships, maturity boundaries, aggregate loss arithmetic, bootstrap settings/envelope and registered decision without reopening private labels. Raw prices, event returns, targets and forecasts are absent from the published result. [Auditor](../nre/m6_guidance_result_audit.py)

## Decision point

This is retrospective development in a selected historical universe, with reconstructed source clocks, source-classification inferences and limited guidance-cut support. It is not independent validation or evidence of trading profitability. The negative result is specific to this registered feature, sample and comparator; it does not prove that every possible news signal is uninformative.

The evidence supports **stopping further engine development under the current NRE approach** and retaining the repository as an audited research record. The M6 engine and Milestones 7–9 remain deferred. Any future research would require a separately justified, pre-specified hypothesis; this completed comparison will not be tuned or rerun after seeing its outcome. No additional subscription was used. The owner can decide whether to shelve NRE entirely; no repository archive/delete action is implied by this research closeout.
