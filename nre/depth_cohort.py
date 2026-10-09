"""Milestone 2 steps 2 and 3, and (with window_relation_to_milestone_1 "after") Milestone 5 Phase 1b: a filing-candidate freeze for the already-accepted Milestone 1 issuers over another window.

Unlike nre/cohort.py's freeze_sec_cohort, which samples an unknown issuer pool down to a target size, this module's
issuer set is already fixed -- the 23 issuers with an accepted Milestone 1 event -- so there is no historical-frame
mirror, no deterministic sampling, and no stopping threshold. It reuses the same low-level SEC helpers
(sec_candidates, relevant_history_files, screen_item_202, PublicClient) over a later filing-screen window instead.

This module discovers filing candidates only; it never imports market prices. It writes to entirely separate
files from Milestone 1's frozen cohort (config/m1-frozen-*.json, reports/m1-sec-cohort-freeze.json) and never
reads or modifies config/pilot.json.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .calendar import Calendar
from .cohort import _client, relevant_history_files, screen_item_202
from .core import DataError, canonical, digest, iso
from .ingestion import sec_candidates


def merged_calendar_spec(*specs):
    """Combine several Calendar spec dicts (as read from nre/calendar-*.json) into one wider spec.

    Purely additive: it is built at call time from the pieces, never written back over any of them,
    so nre/calendar-2026.json (what Milestone 1's accepted labels were computed against) is untouched.
    """
    if len(specs) < 2:
        raise DataError("at least two calendar specs required to merge")
    zones = {spec["timezone"] for spec in specs}
    if len(zones) != 1:
        raise DataError("cannot merge calendars across different timezones")
    holidays, early_closes = set(), {}
    for spec in specs:
        holidays.update(spec["holidays"])
        for day, when in spec["early_closes"].items():
            if day in early_closes and early_closes[day] != when:
                raise DataError("conflicting early-close time for " + day)
            early_closes[day] = when
    return {"version": "merged(" + ",".join(spec["version"] for spec in specs) + ")", "timezone": zones.pop(),
            "start": min(spec["start"] for spec in specs), "end": max(spec["end"] for spec in specs),
            "holidays": sorted(holidays), "early_closes": early_closes}


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DataError("invalid ISO date") from exc


def validate_spec(spec, protocol):
    if spec.get("schema_version") != 1 or spec.get("selection_mode") != "fixed_issuer_set":
        raise DataError("step-2 cohort spec schema_version 1 (fixed_issuer_set) required")
    if spec.get("protocol_sha256") != digest(canonical(protocol)):
        raise DataError("cohort spec protocol hash mismatch")
    if spec.get("event_window_start") != protocol.get("event_window_start") or spec.get("event_window_end") != protocol.get("event_window_end"):
        raise DataError("cohort spec event window differs from step-2 protocol")
    if _date(spec["filing_screen_start"]) > _date(spec["filing_screen_end"]):
        raise DataError("invalid filing screen")
    relation = spec.get("window_relation_to_milestone_1", "before")
    if relation == "before":
        if _date(spec["filing_screen_end"]) >= date(2026, 1, 5):
            raise DataError("step-2 filing screen must end before Milestone 1's frozen window starts (2026-01-05), to keep the two candidate pools from overlapping")
    elif relation == "after":
        if _date(spec["filing_screen_start"]) <= date(2026, 3, 31):
            raise DataError("a forward filing screen must start after Milestone 1's event window ended (2026-03-31), to keep the two candidate pools from overlapping")
    else:
        raise DataError("window_relation_to_milestone_1 must be 'before' or 'after'")
    issuers = spec.get("issuers")
    if not isinstance(issuers, list) or not issuers:
        raise DataError("a nonempty issuer list is required")
    seen = set()
    for issuer in issuers:
        if not isinstance(issuer, dict) or not isinstance(issuer.get("ticker"), str) or not issuer["ticker"]:
            raise DataError("each issuer needs a ticker")
        cik = issuer.get("cik")
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit():
            raise DataError("each issuer needs a ten-digit CIK")
        if cik in seen:
            raise DataError("duplicate CIK in issuer list")
        seen.add(cik)
    allowed_forms = spec.get("allowed_forms")
    if not isinstance(allowed_forms, list) or not allowed_forms:
        raise DataError("allowed_forms required")


def freeze_targeted_candidates(spec, protocol, output, user_agent, client=None):
    """Fetch SEC submissions for spec's fixed issuer list and freeze their Item 2.02 candidates in the filing screen.

    Every issuer is processed in full (no batching/stopping threshold: the issuer count is already fixed and small).
    `client` is any object with the same `.fetch(url, output) -> (body, metadata)` interface as PublicClient; tests
    supply a fake one so the real orchestration logic below is fully covered without touching the network. Left as
    None, a real PublicClient (or SecRelayClient, per spec.sec_transport) is constructed exactly as freeze_sec_cohort does.
    """
    validate_spec(spec, protocol)
    root = Path(output)
    raw_root = root / "raw"
    root.mkdir(parents=True, exist_ok=True)
    transport = spec.get("sec_transport", "direct")
    if client is None:
        client, transport = _client({"sec_transport": transport}, user_agent)
    protocol_sha = digest(canonical(protocol))

    all_candidates, issuer_results = [], []
    for position, issuer in enumerate(sorted(spec["issuers"], key=lambda x: x["cik"]), start=1):
        cik, ticker = issuer["cik"], issuer["ticker"]
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        body, submissions_meta = client.fetch(submissions_url, raw_root)
        try:
            document = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataError("invalid SEC submissions JSON") from exc
        if str(document.get("cik", "")).zfill(10) != cik:
            raise DataError("SEC submissions CIK does not match the spec's issuer entry for " + ticker)

        ledgers = [sec_candidates(document, cik)]
        observations = [submissions_meta]
        for history in relevant_history_files(document, spec["filing_screen_start"], submissions_meta["retrieved_at"]):
            name = history["name"]
            if Path(name).name != name or not name.endswith(".json"):
                raise DataError("unsafe SEC continuation filename")
            hist_body, hist_meta = client.fetch("https://data.sec.gov/submissions/" + name, raw_root)
            try:
                hist_document = json.loads(hist_body)
            except json.JSONDecodeError as exc:
                raise DataError("invalid SEC continuation JSON") from exc
            ledgers.append(sec_candidates(hist_document, cik))
            observations.append(hist_meta)

        merged = {}
        for ledger in ledgers:
            for row in ledger["candidates"]:
                old = merged.get(row["candidate_id"])
                if old is not None and old != row:
                    raise DataError("conflicting SEC accession across source files")
                merged[row["candidate_id"]] = row

        screened = screen_item_202(list(merged.values()), spec["filing_screen_start"], spec["filing_screen_end"])
        issuer_candidate_ids = []
        for row in screened:
            all_candidates.append({
                "candidate_id": row["candidate_id"], "source_sha256": submissions_meta["sha256"], "cik": cik, "ticker": ticker,
                "filing_date": row["filing_date"], "form": row["form"], "items": row["items"], "primary_url": row["url"],
                "primary_source_sha256": None, "primary_review_state": "REQUIRED_POST_FREEZE",
                "discovery_submission_sha256": submissions_meta["sha256"],
                "discovery_submission_representation": submissions_meta.get("source_representation", "raw"),
                "discovery_transport_sha256": submissions_meta.get("transport_sha256"),
            })
            issuer_candidate_ids.append(row["candidate_id"])

        issuer_results.append({"ticker": ticker, "cik": cik, "selection_position": position, "submissions_url": submissions_url,
                               "submissions_sha256": submissions_meta["sha256"], "observations": len(observations),
                               "item_2_02_candidates": len(issuer_candidate_ids), "candidate_ids": issuer_candidate_ids})

    ids = [x["candidate_id"] for x in all_candidates]
    if len(ids) != len(set(ids)):
        raise DataError("duplicate accession in frozen candidate membership")
    all_candidates.sort(key=lambda x: x["candidate_id"])
    frozen_at = iso(datetime.now(timezone.utc))
    membership = [{"candidate_id": x["candidate_id"], "source_sha256": x["source_sha256"]} for x in all_candidates]
    membership_sha = digest(canonical(membership))
    candidate_issuers = sum(1 for x in issuer_results if x["item_2_02_candidates"])

    issuer_cohort = {"schema_version": 1, "frozen_at": frozen_at, "selection_mode": spec["selection_mode"],
                     "protocol_sha256": protocol_sha, "processed_issuers": len(issuer_results), "issuers": issuer_results}
    candidate_ledger = {"protocol_sha256": protocol_sha, "frozen_at": frozen_at, "membership_sha256": membership_sha,
                        "candidates": all_candidates}
    report = {"schema_version": 1, "state": "FROZEN_CANDIDATE_MEMBERSHIP", "frozen_at": frozen_at,
             "price_data_accessed_by_this_workflow": False, "selection_mode": spec["selection_mode"],
             "processed_issuers": len(issuer_results), "candidate_count": len(all_candidates),
             "issuers_with_item_2_02_candidates": candidate_issuers, "membership_sha256": membership_sha,
             "filing_screen": [spec["filing_screen_start"], spec["filing_screen_end"]],
             "event_window": [spec["event_window_start"], spec["event_window_end"]], "sec_transport": transport,
             "limitations": spec.get("limitations", []) + ["No clean-cohort market prices were accessed by this step."]}

    for name, value in (("issuer-cohort.json", issuer_cohort), ("candidate-ledger.json", candidate_ledger), ("discovery-report.json", report)):
        (root / name).write_bytes(canonical(value))
    return issuer_cohort, candidate_ledger, report
