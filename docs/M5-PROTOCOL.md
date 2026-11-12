# Milestone 5 Phase 0 — Pre-registered research protocol

The owner authorized Phase 0 on 2026-11-12. [Protocol v1](../config/m5-protocol.json) fixes the design before feature acquisition, model fitting or evaluation. The [freeze record](../reports/m5-protocol-freeze-2026-11-12.json) contains the canonical SHA-256.

## Data and validation

- Development uses the 128 accepted events and the five existing chronological blocks. The outer test folds are blocks 3, 4 and 5. Each fold has earlier, ordered fit, selection and calibration partitions. The old Milestone 4 holdout results were known at the freeze, so block 5 belongs to development.
- The final holdout consists of exactly the 43 events in the [sealed registry](../reports/m5-phase1b-s7-registry.json). Phase 4 requires separate authorization, a frozen development pipeline and a logged one-time look. The run must verify all 43 commitments before releasing holdout metrics.
- The five primary targets retain the Milestone 4 news and opening clocks. Clean-window results drive decisions, with all-event results alongside them. Earlier labels must be mature when used, and related events stay together.

## Comparisons

- The fixed model grid covers shallow trees, random forests, gradient boosting and an equal-weight ensemble. Each target has one confirmatory contrast against a baseline selected using earlier development data. Loss is measured with Brier score for binary targets and pinball loss for Day-1 return quantiles. Claims use 99% issuer- and session-clustered intervals.
- Four ablations cover issuer reaction history, analogues, daily market structure and market regime. Daily features use raw SIP bars from completed sessions before the release cutoff date in New York. The protocol specifies how to handle all-hours volume, short histories, missing data and corporate actions.
- Promotion requires development improvement, acceptable calibration and directional agreement on the sealed holdout within the frozen degradation margin. Sparse targets and inconclusive results are recorded with counts and uncertainty. Promotion means eligibility for later research under separate authorization.

The inner split, coverage rules, small model grids, calibration tolerances, holdout margin and seeds are Phase 0 design defaults. Any amendment requires owner authorization and a new version that records what was already known.
