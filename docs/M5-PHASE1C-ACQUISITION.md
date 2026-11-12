# Milestone 5 Phase 1c — Derived feature acquisition

The owner authorized this phase and confirmed that the existing Alpaca SIP data rights cover the 128 development and 43 holdout events. The [authorization record](../reports/m5-phase1c-authorization-2026-11-12.json) binds the frozen [Phase 0 protocol](../config/m5-protocol.json).

The workflow verifies the protocol and cohort hashes before requesting data. It requests raw SIP daily bars and dated corporate actions for the registered issuers and six ETFs. Each feature uses completed exchange sessions strictly before the New York cutoff date. Issuer windows start within the attested security identity interval, and provider symbol remapping is disabled. Missing sessions, short histories, unresolved corporate actions and corporate actions within a lookback cause the affected feature to be unavailable. The attested identity intervals provide fewer than 252 sessions for every event in this version, so the registered distance-to-252-session-high feature is unavailable throughout.

Raw bars and corporate-action payloads stay in memory. The workflow artifact contains development feature rows and a summary of both partitions. The summary binds the development rows and the separately computed holdout rows by SHA-256 and reports aggregate availability. Only the holdout feature commitment and aggregate coverage leave the acquisition process. Authorized Phase 4 can recompute those features against the commitment. The existing holdout label commitments are used only to verify membership at this stage.

The live run starts with the authorized push. Validate the workflow result, artifact schema, row counts, checksums and availability before recording the live acquisition. Phase 2 requires separate authorization.
