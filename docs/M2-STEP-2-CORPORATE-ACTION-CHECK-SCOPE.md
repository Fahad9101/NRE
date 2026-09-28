# Milestone 2 step 2 — corporate-action check scope proposal (for the project owner's review)

**Status: proposed 2026-09-28, not yet built. Nothing described here has been built or run.**

## Summary

- **Technical design:** no new Python module needed. `nre/event_acquire.py` already takes `--spec`
  as a CLI argument (default `config/m1-events.json`); its validation, fetch, and label logic are
  generic. The only new files needed are a new spec, `config/m2-step2-events.json` (same schema as
  `config/m1-events.json`), and a new workflow, `.github/workflows/depth-event-acquire.yml`
  (mirroring `event-acquire.yml`, but invoking `python -m nre.event_acquire --spec
  config/m2-step2-events.json`). Nothing Milestone-1-frozen — `nre/event_acquire.py`,
  `.github/workflows/event-acquire.yml`, `config/m1-events.json` — is modified.
- **Process design:** adopt Milestone 1's own evolved pattern (its first few events were signed off
  one at a time; by `reports/m1-signoff-packet-batch-2026-09-26.json` it had moved to batching
  several candidates into one packet, with one combined owner sign-off per batch) rather than
  either extreme — not silently self-attesting 46 candidates at once, and not asking for 46
  individual "sign off on X" replies.
- **What I need from you:** a decision on batch size/pacing (section 2), and an explicit
  reconfirmation that the Alpaca provider authorization covers this scale (section 3) — Milestone 1
  itself re-asked this at every size increase and never treated it as automatically extending.

## 1. The 46 candidates in scope

48 step-2 candidates were frozen; 2 are now excluded (`ASMB` 2025-08-06, same-day competing
catalyst; `REKR` 2025-10-14, not a qualifying event — see
`reports/m2-step2-same-day-catalyst-review-2026-09-28.json` and
`reports/m2-step2-eligibility-review-2026-09-28.json`). The remaining 46 already have: a confirmed
minute-precision wire timestamp (batch-1/batch-2 chronology), and a clean identity/exchange
re-verification (today). None has yet had a corporate-actions dry run, and none has any attestation.

## 2. Proposed process, mirroring Milestone 1's own evolution

1. **Build the spec, unattested.** Write `config/m2-step2-events.json` with all 46 candidates'
   `security`/`source`/`published_at`/`timestamp_evidence` fields filled from evidence already on
   file (the chronology reports). No `attestations` block on any event yet — every event will
   quarantine on `FIRST_PUBLIC_TIME_UNVERIFIED`, exactly like Milestone 1's own dry runs.
2. **Dry run.** Dispatch the new workflow with no attestations. This calls the real Alpaca API and
   reports, per candidate: session availability, zero-volume days, and any corporate action found in
   the window — without computing or exposing any label, the same way
   `reports/m1-signoff-packet-batch-2026-09-26.json`'s dry run caught TLF's dividend before any
   attestation was written.
3. **Compile signoff packet(s).** For candidates the dry run shows are clean, bundle the chronology
   evidence (already written), the identity evidence (already written), and the dry-run's
   corporate-actions finding into one packet per batch, and ask for one combined sign-off — the
   pattern the batch-2026-09-26 packet used. A candidate with a real corporate action found (like
   JBSS's already-known dividend) gets its own explicit note rather than being bundled as "clean."
4. **Add attestations, re-run for real.** Only after a sign-off does `config/m2-step2-events.json`
   get that batch's `attestations` filled in, referencing the packet as the `record`. Re-running then
   computes and exposes labels for that batch.

**Open question:** batch size. Milestone 1's batches ran roughly 8–13 at a time. I'd default to the
same order of magnitude (four batches of ~11–12) unless you'd rather do all 46 in one dry run and
then decide batching once we see how many come back clean versus flagged.

## 3. Provider-rights-at-scale — needs your explicit answer, not an assumption

`config/m1-events.json`'s own provider attestation record states: *"The 'aggregate at scale'
question is explicitly carried forward as something to revisit as the cohort grows, not closed by
this decision."* It was in fact revisited twice — explicitly, in your own words, each time the
recorded-event count grew past a threshold ("sign off on all eight"; "sign off on all thirteen,
provider rights fine"). Step 2 would take the aggregate exposed-derived-data footprint from
Milestone 1's ~23+ events past 46 more. Consistent with how this has always been handled, I'm not
treating the standing authorization as automatically covering this — it needs your explicit word,
the same way it did at each of Milestone 1's own scale-ups.

## 4. What this does not do

No label is computed or exposed until a batch is both dry-run-clean (or explicitly flagged, like
JBSS) and attested. No candidate becomes "included" by this check alone — the label-engine dry run
(distinct from the Alpaca dry run above: running the full accepted set through the same
label-computation path the fingerprints/analogues machinery consumes) and your final sign-off still
follow, the same order Milestone 1 used.
