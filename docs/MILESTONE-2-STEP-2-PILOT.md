# Milestone 2 step 2 — depth pilot

**Status: candidates frozen, review not started.** Authorized 2026-09-28 (`reports/m2-step2-authorization-2026-09-28.json`); candidates discovered and frozen the same day (`reports/m2-step2-sec-cohort-freeze.json`). No candidate has been reviewed, and none is included in any dataset yet.

## Scope

The owner chose the pilot scope and the full Milestone 1 review standard, both recommended options, in reply to "decide milestone 2 step 2" (`reports/m2-step2-authorization-2026-09-28.json`): two prior quarterly earnings cycles for the same 23 already-accepted issuers, reviewed one named reviewer per event with no shortcuts, deliberately not committing to the proposal's fuller 4–8 quarter range up front. The reasoning: Milestone 1's own 100→20 event target amendment already showed that solo manual-review throughput is easy to overestimate, so this pilot exists to measure real throughput before any wider commitment.

## What's frozen and how

`nre/depth_cohort.py` is a new, separate module — not a modification of `nre/cohort.py`, which stays exactly as Milestone 1 left it. Unlike `freeze_sec_cohort`, which samples an unknown issuer pool down to a target size, this pilot's issuer set is already fixed (the 23 accepted issuers), so there is no historical-frame mirror, no deterministic sampling and no stopping threshold — it fetches each issuer's SEC submissions directly and screens Item 2.02 8-Ks in the window. 24 offline tests (`tests/test_depth_cohort.py`) cover it, including two run directly against the real committed `config/m2-step2-*.json` files.

**A separate protocol, not an amendment.** `config/m2-step2-protocol.json` is a new, parallel file — Milestone 1's `config/pilot.json`, its frozen 243-candidate membership and every M1 record are untouched. The two protocols' event windows cannot overlap: this pilot's window ends 2026-01-04, the day before Milestone 1's begins.

**A separate calendar, not an extension.** `nre/calendar-2025.json` is a new file covering all of 2025, read directly from NYSE's official 2025 trading calendar PDF and cross-checked against `nre/calendar-2026.json`'s already-trusted pattern (same 10-holiday count; the earlier AI-search-summary draft of these dates was wrong about Columbus Day, Veterans Day, and two early-close dates, caught by reading the primary source directly — see the file's own `review_note`). `nre/calendar-2026.json`, which every Milestone 1 label was computed against, is not modified; `nre/depth_cohort.merged_calendar_spec()` combines the two at call time, additively, whenever step-2 code needs a calendar spanning both years.

**Window:** 2025-06-01 to 2026-01-04 (event window and filing screen, identical). **Price window:** through 2026-02-28, comfortably covering the 20th reaction session after the latest possible event date (computed as 2026-02-02).

**Discovery:** real SEC EDGAR data, fetched 2026-09-28. Direct `urllib` access from this machine returned HTTP 403 (SEC blocks the request in a way GitHub Actions apparently doesn't hit), so discovery went through the built-in browser instead — the same channel already used for this project's per-candidate review work. Every response's SHA-256 was computed in-browser over the true response bytes, then independently re-verified in Python against the decoded text before it was used for anything (`hashlib.sha256(text.encode("utf-8"))` matched the browser's own hash for all 23 issuers), so `source_sha256` in the frozen ledger is the hash of what a live re-fetch of the same URL would produce, not of some intermediate reconstruction. No issuer needed a continuation file: every one of the 23 issuers' "recent" filing window already reached back well before 2025-06-01.

## Result

**48 candidates across all 23 issuers** — every issuer has at least one, most have exactly two (matching "2 prior quarters"), and two have three: LOVE (2025-06-12, 2025-09-11, 2025-12-11) and REKR (2025-08-12, 2025-10-14, 2025-11-13). Worth checking in review whether all of an issuer's candidates are genuinely quarterly-earnings releases or whether some are a different kind of Item 2.02 disclosure (a preliminary update, for instance) — this is exactly the review that has not happened yet, so nothing is assumed here either way.

Frozen files:
- `config/m2-step2-frozen-issuer-cohort.json` — per-issuer discovery record.
- `config/m2-step2-frozen-candidate-ledger.json` — the 48 candidates, membership hash `62150f194f03448498a619a23470c1d94b9fd95d2e35f0fb30dfe27094a0e383`.
- `reports/m2-step2-sec-cohort-freeze.json` — the discovery report.

The raw SEC response bytes and their hashes are preserved locally at `data/m2-step2-freeze/raw/` (gitignored, matching how Milestone 1's raw archive was never committed either). This is not yet a durable archive anywhere else — the same limitation Milestone 1's SEC freeze had before the owner was asked to keep a copy separately.

## What's left

Nothing is reviewed. The next step, at the standard the owner chose, is the same per-candidate work Milestone 1 did for its 243 candidates: chronology (is there an earlier disclosure a wire timestamp would miss?), identity (common stock, eligible exchange), competing catalysts, corporate actions, and a dry run through `nre/event_acquire.py`-equivalent label computation — one candidate at a time, one named reviewer, no shortcuts. That is genuinely substantial work; Milestone 1 took its full duration to get 23 events through that process from a much larger pool. This record exists so that work can start from a frozen, outcome-blind pool, exactly like Milestone 1's did.
