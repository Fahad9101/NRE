# Milestone 6 — Research closeout for owner review

**Recommendation.** Close the completed feasibility and development research and defer the Reaction Gap Engine build. Keep the proposed 2027 study on hold. The authorized work established where the proposed designs fail their gates. An operational engine with verified decision-time inputs, an accepted rule for emitting underreaction and overreaction candidates, and a fresh validation study are still outstanding.

| Research question | Result |
| --- | --- |
| Does the original tail rule give a different direction from simple opening-gap fade? | The frozen benchmark and tail thresholds force the same direction on flagged events. Their paired directional scores are identical. [Step A result](M6-PROTOCOL.md) |
| Do the tail and magnitude rules select different events often enough to study? | Historical SIP verified 107 of 119 eligible openings. The rules disagreed on four of 107 (3.7%), below the five-disagreement and 10% floors. Opening receipt latency remains unverified. [Historical feasibility result](M6-HISTORICAL-OPENING.md) |
| Does issuer history improve forecasts beyond opening-gap size and direction? | The single offline comparison met the clean support floors. The challenger reduced MSE by 0.85% on 64 clean paired rows versus the 5% requirement. The 99% interval included zero. The 67-row all-event sensitivity showed 0.66% higher MSE. [Issuer-context result](M6-CONTEXT-RESULT.md) |

## Evidence that would justify reopening

A materially different, point-in-time input is the most direct reason to reopen. One example is an earnings-release measure with source lineage and demonstrated availability before the news cutoff across enough issuers and sessions. The current worked example does not establish that coverage. For any new design, demonstrate usable coverage and variation before fitting, then fix the outcome, comparison, minimum practical effect and precision requirements before collecting a separate untouched cohort. A historical study would need comparable official opening records. Any prospective opening-clock study would also need a verified live feed, receiver clock evidence and capture rights. [Context coverage](M6-CONTEXT-COMPARISON-SCOPE.md) · [Opening feasibility requirements](M6-OPENING-PRINT-FEASIBILITY.md)

On 2026-11-15, the owner [acknowledged the research closeout and deferred the engine build](../reports/m6-research-closeout-acknowledgment-2026-11-15.json). Formal milestone progression requires a separate owner decision under the [sequential milestone contract](MILESTONE-0-TECHNICAL-CONTRACT.md).
