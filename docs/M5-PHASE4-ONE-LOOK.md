# Milestone 5 Phase 4 — One-look procedure

The owner authorized one holdout evaluation in the NRE Codex chat. The [authorization record](../reports/m5-phase4-authorization-2026-11-13.json) binds protocol v1 and the completed development comparison.

The workflow is manually dispatched on main. It verifies the Phase 1c archive and locks the development fit, selection and calibration before receiving Alpaca credentials. The lock records the development partitions and selections, with a digest of fitted predictions on development rows. The live step reproduces the lock before contacting Alpaca.

The workflow creates the GitHub tag `m5-phase4-holdout-look-v1` before contacting Alpaca. Its annotation binds the run, attempt, code revision and lock file hash. The tag is an exclusive access marker. An existing tag prevents another live attempt, including after a failure. Any failure after the tag is created requires an owner decision before another attempt.

All 43 label commitments and the separate Phase 1c holdout feature commitment must match before aggregate metrics can be released. Raw bars, event-level holdout outcomes and predictions stay in memory. Phase 3 recorded zero targets passing the development gate, so the holdout provides replication evidence and cannot promote a target.

The GitHub copy of the Phase 1c input archive expires on 2026-12-13. The run must obtain the pinned archive before acquiring any holdout data.
