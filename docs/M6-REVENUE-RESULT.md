# Milestone 6 — Quarterly revenue development result

**Stop the quarterly revenue comparison at the development gate.** The clean-window sample met every support floor. Adding quarterly revenue growth increased mean squared forecast error by 15.15%, and the 99% interval for the paired improvement included zero. The sensitivity with caveated labels retained also favored the opening-gap baseline.

| Variant | Pairs | Baseline MSE | Baseline plus revenue MSE | Relative MSE reduction | 99% envelope for paired improvement |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clean-window primary | 51 | 0.006903 | 0.007949 | −15.15% | [−0.003940, +0.001181] |
| Sensitivity with caveats retained | 51 | 0.006970 | 0.008042 | −15.38% | [−0.004045, +0.001265] |

Positive improvement favors adding revenue. The interval is in squared decimal-return units and spans the outer endpoints of the separate issuer- and session-clustered 99% bootstrap intervals. The registered minimum reduction was 5%, with a positive lower endpoint and a nonnegative sensitivity improvement.

## Coverage and clock

Blocks 3, 4 and 5 supplied 17, 18 and 16 test pairs, with 35, 52 and 70 clean fit rows. The 51 pairs span 21 issuers and 32 sessions, with 28 up gaps and 23 down gaps. Revenue grew in 42 pairs and declined in nine. Across all 128 screened events, 88 had qualified revenue by the 15-minute cutoff. Coverage was 69 of 96 after-hours releases and 19 of 32 premarket releases. Two issuers supplied zero qualified rows. Among quarters with at least 10 screened events, coverage was highest in 2025 Q3 at 17 of 21 and lowest in 2025 Q2 at 14 of 25. Both arms used the same eligible rows in each variant. The sensitivity admitted two extra fit rows in each fold and scored the same test events.

The feature used the coverage audit's original wire, SEC exhibit and periodic filing priority, with reconstructed availability strictly before the 15-minute cutoff. The model used a fixed inverse hyperbolic sine transform of the growth fraction. Both forecasts also used the daily opening-gap proxy, so the predictions are defined at that opening reference. Source availability was reconstructed from archived timestamps. An independent study would need untouched events and validated official opens. [Coverage audit](M6-REVENUE-COVERAGE.md)

## Run record

The runner and protocol were committed at `69435e1fb2765fea29481b50dafca87e38f657b4` before the single run. Stored per-fold sums of squared errors reproduce the pooled MSEs. The aggregate report records the coverage strata, cluster intervals and pair membership digests. The already opened Milestone 4 final test block served as development block 5. The comparison used zero confirmation-cohort accesses. Milestone 6 remains at research closeout with the engine deferred and the 2027 study on hold. [Protocol](../config/m6-revenue-protocol.json) · [Freeze](../reports/m6-revenue-freeze-2026-11-16.json) · [Attempt](../reports/m6-revenue-attempt-2026-11-16.json) · [Result](../reports/m6-revenue-result-2026-11-16.json)
