# Milestone 6 — Issuer-context development result

The single authorized offline comparison is complete. **Stop this design at the development gate.** The clean-window comparison met the sample requirements. Adding issuer context reduced mean squared forecast error by 0.85%, below the pre-registered 5% threshold. The 99% interval envelope included zero, and the all-event sensitivity slightly favored the opening-gap baseline.

| Variant | Paired rows | Baseline MSE | Issuer-context MSE | Relative MSE reduction | 99% interval envelope for paired improvement |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clean-window primary | 64 | 0.007646 | 0.007581 | +0.85% | [-0.000547, +0.000696] |
| All-event sensitivity | 67 | 0.007225 | 0.007273 | -0.66% | [-0.000470, +0.000329] |

Positive improvement favors issuer context. The intervals are in squared decimal-return units and take the outer endpoints of separate issuer-clustered and session-clustered bootstraps with fitted predictions held fixed.

The clean comparison covered 23 issuers and 37 reaction sessions, with 35 up gaps and 29 down gaps. Blocks 3, 4 and 5 contributed 20, 23 and 21 pairs. Three rows were excluded under the opening-label caveat rule. Every scored row had own-issuer history, so neither variant used a baseline fallback. The opening reference was the accepted daily-bar proxy. The 43-event Milestone 5 extension was outside the input cohort, and the run made zero holdout accesses.

The [protocol](../config/m6-context-protocol.json) was frozen at commit `acfa8b83c777556e076df2ef24a3e92fad8f26fb` before scoring. The [freeze record](../reports/m6-context-freeze-2026-11-15.json), [attempt record](../reports/m6-context-attempt-2026-11-15.json) and [paired result](../reports/m6-context-result-2026-11-15.json) bind the run and record both variants. The stored paired predictions reproduce the reported MSEs without a second fit. The existing 2027 study stays on hold.
