# Milestone 5 Phase 2 — Evaluation harness

The owner authorized Phase 2 in the NRE Codex chat with “Authorize NRE Milestone 5 Phase 2.” The harness follows [protocol v1](../config/m5-protocol.json) and uses Python's standard library. Phase 2 tests fit and evaluate models on synthetic fixtures.

The development artifact verifier binds the archive and its contents to the [Phase 1c result](../reports/m5-phase1c-acquisition-result-2026-11-13.json). The development input loader checks the accepted Milestone 4 dataset and joins only its 128 events to those derived features. The new holdout is represented only by sealed membership metadata during artifact verification.

The harness provides ordered, cluster-preserving partitions and maturity checks, fit-only feature encoding, model and baseline selection, Platt calibration, paired evaluation, four family ablations and descriptive permutation importance. Fold results retain selection attempts, calibration status, predictions, feature coverage and abstentions for the Phase 3 experiment record. Synthetic tests check model arithmetic, repeatability, rejected inputs and the effect of changing future data.

Phase 3 requires separate authorization for running the development comparison and publishing its experiment record. The final fit and one-look holdout runner belong to separately authorized later work.
