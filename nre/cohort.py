"""Deterministic Milestone 1 SEC cohort discovery and membership freeze.

This module discovers filing candidates only. It never imports market prices.
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .core import DataError, canonical, digest, iso
from .ingestion import PublicClient, SecRelayClient, sec_candidates


_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
_MASTER_FILENAME = re.compile(r"edgar/data/(\d+)/(\d{10}-\d{2}-\d{6})\.txt")


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DataError("invalid ISO date") from exc


def exchange_issuers(document, allowed_exchanges):
    """Legacy exploratory current-directory frame; not used by the v2 pilot."""
    fields = document.get("fields")
    data = document.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise DataError("SEC exchange directory missing fields/data")
    required = {"cik", "name", "ticker", "exchange"}
    if not required.issubset(fields):
        raise DataError("SEC exchange directory schema missing required fields")
    idx = {name: fields.index(name) for name in required}
    allowed = {str(x).strip().lower() for x in allowed_exchanges}
    if not allowed:
        raise DataError("allowed exchanges required")

    grouped = {}
    for row in data:
        if not isinstance(row, list) or len(row) != len(fields):
            raise DataError("SEC exchange directory row length mismatch")
        exchange = str(row[idx["exchange"]] or "").strip()
        if exchange.lower() not in allowed:
            continue
        cik_raw = str(row[idx["cik"]] or "").strip()
        ticker = str(row[idx["ticker"]] or "").strip().upper()
        name = str(row[idx["name"]] or "").strip()
        if not cik_raw.isdigit() or not ticker or not name:
            raise DataError("invalid SEC issuer row")
        cik = str(int(cik_raw)).zfill(10)
        item = grouped.setdefault(cik, {"cik": cik, "name": name, "tickers": set(), "exchanges": set()})
        item["tickers"].add(ticker)
        item["exchanges"].add(exchange)
        if name < item["name"]:
            item["name"] = name

    output = []
    for cik, item in grouped.items():
        output.append({
            "cik": cik,
            "name": item["name"],
            "tickers": sorted(item["tickers"]),
            "exchanges": sorted(item["exchanges"]),
        })
    return sorted(output, key=lambda x: x["cik"])


def deterministic_issuer_sample(issuers, sample_size, seed, exclude_ciks=()):
    if type(sample_size) is not int or sample_size < 1:
        raise DataError("positive sample size required")
    if not isinstance(seed, str) or not seed:
        raise DataError("deterministic seed required")
    excluded = {str(int(x)).zfill(10) for x in exclude_ciks}
    eligible = []
    for issuer in issuers:
        cik = issuer["cik"]
        if cik in excluded:
            continue
        row = dict(issuer)
        row["selection_key"] = digest((seed + "|" + cik).encode("utf-8"))
        eligible.append(row)
    eligible.sort(key=lambda x: (x["selection_key"], x["cik"]))
    if len(eligible) < sample_size:
        raise DataError("issuer selection frame smaller than requested sample")
    return eligible[:sample_size]


def historical_issuer_pool(frame, spec):
    """Build a deterministic issuer pool from a pinned historical SEC-index mirror.

    The mirror is discovery transport only. It never proves security eligibility,
    Item 2.02 status, or source truth; those are reconciled downstream.
    """
    if not isinstance(frame, dict) or frame.get("schema_version") != 1:
        raise DataError("unsupported historical frame")
    hf = spec.get("historical_frame", {})
    source = frame.get("source", {})
    expected = {
        "dataset": hf.get("dataset"),
        "parquet_filename": hf.get("parquet_filename"),
        "parquet_url": hf.get("parquet_url"),
        "parquet_sha256": hf.get("parquet_sha256"),
        "parquet_listing_sha256": hf.get("parquet_listing_sha256"),
    }
    if any(source.get(k) != v for k, v in expected.items()):
        raise DataError("historical frame source does not match preregistered artifact")
    if frame.get("filing_screen_start") != spec.get("filing_screen_start") or frame.get("filing_screen_end") != spec.get("filing_screen_end"):
        raise DataError("historical frame filing screen mismatch")

    rows = frame.get("rows")
    if not isinstance(rows, list) or not rows:
        raise DataError("historical frame rows required")
    allowed_forms = set(hf.get("allowed_forms", []))
    allowed_sources = set(hf.get("allowed_canonical_sources", []))
    if not allowed_forms or not allowed_sources:
        raise DataError("historical frame allowed forms/sources required")
    start, end = _date(spec["filing_screen_start"]), _date(spec["filing_screen_end"])

    grouped = {}
    seen_filing = {}
    for row in rows:
        if not isinstance(row, dict):
            raise DataError("historical frame row must be object")
        required = ("cik", "company_name", "form_type", "date_filed", "filename", "src")
        if any(k not in row for k in required):
            raise DataError("historical frame row missing field")
        form = str(row["form_type"])
        if form not in allowed_forms:
            raise DataError("unexpected form in historical frame")
        filed = _date(str(row["date_filed"]))
        if not start <= filed <= end:
            raise DataError("historical frame row outside filing screen")
        src = str(row["src"])
        if src not in allowed_sources:
            raise DataError("historical frame canonical source not preregistered")
        cik_raw = str(row["cik"]).strip()
        if not cik_raw.isdigit() or int(cik_raw) <= 0:
            raise DataError("invalid historical frame CIK")
        cik = str(int(cik_raw)).zfill(10)
        filename = str(row["filename"])
        match = _MASTER_FILENAME.fullmatch(filename)
        if not match or int(match.group(1)) != int(cik):
            raise DataError("historical master filename/CIK mismatch")
        accession = match.group(2)
        if not _ACCESSION.fullmatch(accession):
            raise DataError("invalid historical accession")
        fingerprint = (cik, accession)
        normalized = {
            "cik": cik,
            "company_name": str(row["company_name"]).strip(),
            "form_type": form,
            "date_filed": filed.isoformat(),
            "filename": filename,
            "src": src,
            "accession": accession,
        }
        old = seen_filing.get(fingerprint)
        if old is not None and old != normalized:
            raise DataError("conflicting historical master-index accession")
        seen_filing[fingerprint] = normalized

    for normalized in seen_filing.values():
        cik = normalized["cik"]
        item = grouped.setdefault(cik, {
            "cik": cik,
            "historical_names": set(),
            "historical_accessions": set(),
            "historical_filing_rows": [],
        })
        if normalized["company_name"]:
            item["historical_names"].add(normalized["company_name"])
        item["historical_accessions"].add(normalized["accession"])
        item["historical_filing_rows"].append({
            k: normalized[k] for k in ("accession", "form_type", "date_filed", "filename", "src")
        })

    issuers = []
    for cik, item in grouped.items():
        names = sorted(item["historical_names"])
        filings = sorted(item["historical_filing_rows"], key=lambda x: (x["date_filed"], x["accession"]))
        issuers.append({
            "cik": cik,
            "name": names[0] if names else "",
            "historical_names": names,
            "historical_accessions": sorted(item["historical_accessions"]),
            "historical_filing_rows": filings,
            "historical_8k_count": len(filings),
        })

    max_issuers = spec.get("issuer_pool_max")
    if type(max_issuers) is not int or max_issuers < 1:
        raise DataError("positive issuer_pool_max required")
    selected = deterministic_issuer_sample(
        issuers,
        max_issuers,
        spec.get("deterministic_seed"),
        spec.get("exclude_ciks", []),
    )
    return selected


def _one_year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def relevant_history_files(document, screen_start, retrieved_at=None):
    """Return continuation files required for the requested filing screen."""
    start = _date(screen_start)
    filings = document.get("filings", {})
    recent = filings.get("recent", {})
    dates = recent.get("filingDate")
    if not isinstance(dates, list):
        raise DataError("SEC submissions missing recent filing dates")

    if retrieved_at is not None:
        try:
            retrieved_day = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise DataError("invalid SEC retrieval timestamp") from exc
        if start >= _one_year_before(retrieved_day):
            return []

    if dates:
        parsed = [_date(x) for x in dates]
        if min(parsed) <= start:
            return []

    files = filings.get("files", [])
    if not isinstance(files, list):
        raise DataError("SEC continuation metadata malformed")
    if not files:
        return []

    needed = []
    for item in files:
        if not isinstance(item, dict) or not all(k in item for k in ("name", "filingFrom", "filingTo")):
            raise DataError("SEC continuation metadata incomplete")
        low, high = _date(item["filingFrom"]), _date(item["filingTo"])
        if low <= start <= high or high >= start:
            needed.append(item)

    if needed:
        needed.sort(key=lambda x: x["name"])
        return needed
    raise DataError("SEC submissions do not prove filing-screen coverage")


def screen_item_202(candidates, screen_start, screen_end):
    start, end = _date(screen_start), _date(screen_end)
    if start > end:
        raise DataError("invalid filing screen")
    rows = []
    for row in candidates:
        day = _date(row["filing_date"])
        if start <= day <= end and "2.02" in set(row.get("items", [])):
            rows.append(row)
    return sorted(rows, key=lambda x: (x["filing_date"], x["candidate_id"]))


def screen_all_8k(candidates, screen_start, screen_end):
    start, end = _date(screen_start), _date(screen_end)
    rows = []
    for row in candidates:
        day = _date(row["filing_date"])
        if start <= day <= end:
            rows.append(row)
    return sorted(rows, key=lambda x: (x["filing_date"], x["candidate_id"]))


def _client(spec, user_agent):
    transport = spec.get("sec_transport", "direct")
    if transport == "direct":
        return PublicClient(user_agent), transport
    if transport == "r_jina_relay":
        return SecRelayClient(user_agent), transport
    raise DataError("unsupported SEC cohort transport")


def freeze_sec_cohort(spec, protocol, output, user_agent, frame=None):
    """Fetch, enumerate and freeze a clean source-side filing candidate cohort."""
    if spec.get("schema_version") != 2 or spec.get("selection_mode") != "historical_sec_master_mirror":
        raise DataError("historical cohort spec version 2 required")
    protocol_sha = digest(canonical(protocol))
    if spec.get("protocol_sha256") != protocol_sha:
        raise DataError("cohort spec protocol hash mismatch")
    if spec.get("event_window_start") != protocol.get("event_window_start") or spec.get("event_window_end") != protocol.get("event_window_end"):
        raise DataError("cohort spec event window differs from pilot protocol")
    if frame is None:
        raise DataError("historical issuer frame required")

    batch_size = spec.get("issuer_batch_size")
    target_candidates = spec.get("freeze_min_item_2_02_candidates")
    target_issuers = spec.get("freeze_min_item_2_02_issuers")
    for value, name in ((batch_size, "issuer_batch_size"), (target_candidates, "candidate target"), (target_issuers, "issuer target")):
        if type(value) is not int or value < 1:
            raise DataError("positive " + name + " required")

    root = Path(output)
    raw_root = root / "raw"
    root.mkdir(parents=True, exist_ok=True)
    client, transport = _client(spec, user_agent)
    selected_pool = historical_issuer_pool(frame, spec)
    frame_sha = digest(canonical(frame))

    all_candidates = []
    issuer_results = []
    stopped = False
    stop_boundary = None
    for position, issuer in enumerate(selected_pool, start=1):
        cik = issuer["cik"]
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        body, submissions_meta = client.fetch(submissions_url, raw_root)
        try:
            document = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataError("invalid SEC submissions JSON") from exc

        ledgers = [sec_candidates(document, cik)]
        observations = [submissions_meta]
        for history in relevant_history_files(
            document,
            spec["filing_screen_start"],
            submissions_meta["retrieved_at"],
        ):
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

        window_rows = screen_all_8k(list(merged.values()), spec["filing_screen_start"], spec["filing_screen_end"])
        sec_accessions = {r["candidate_id"] for r in window_rows}
        historical_accessions = set(issuer["historical_accessions"])
        missing_in_submissions = sorted(historical_accessions - sec_accessions)
        extra_in_submissions = sorted(sec_accessions - historical_accessions)
        reconciliation_state = "MATCHED" if not missing_in_submissions and not extra_in_submissions else "REVIEW_REQUIRED"

        screened = screen_item_202(window_rows, spec["filing_screen_start"], spec["filing_screen_end"])
        issuer_candidate_ids = []
        for row in screened:
            all_candidates.append({
                "candidate_id": row["candidate_id"],
                "source_sha256": submissions_meta["sha256"],
                "cik": cik,
                "filing_date": row["filing_date"],
                "form": row["form"],
                "items": row["items"],
                "primary_url": row["url"],
                "primary_source_sha256": None,
                "primary_review_state": "REQUIRED_POST_FREEZE",
                "historical_frame_reconciliation": reconciliation_state,
                "discovery_submission_sha256": submissions_meta["sha256"],
                "discovery_submission_representation": submissions_meta.get("source_representation", "raw"),
                "discovery_transport_sha256": submissions_meta.get("transport_sha256"),
            })
            issuer_candidate_ids.append(row["candidate_id"])

        issuer_results.append({
            **issuer,
            "selection_position": position,
            "submissions_url": submissions_url,
            "submissions_sha256": submissions_meta["sha256"],
            "observations": len(observations),
            "historical_frame_reconciliation": reconciliation_state,
            "missing_historical_accessions_in_submissions": missing_in_submissions,
            "extra_submissions_accessions_vs_historical_frame": extra_in_submissions,
            "item_2_02_candidates": len(issuer_candidate_ids),
            "candidate_ids": issuer_candidate_ids,
        })

        if position % batch_size == 0:
            candidate_issuers = sum(1 for x in issuer_results if x["item_2_02_candidates"])
            if len(all_candidates) >= target_candidates and candidate_issuers >= target_issuers:
                stopped = True
                stop_boundary = position
                break

    ids = [x["candidate_id"] for x in all_candidates]
    if len(ids) != len(set(ids)):
        raise DataError("duplicate accession in frozen candidate membership")
    all_candidates.sort(key=lambda x: x["candidate_id"])
    frozen_at = iso(datetime.now(timezone.utc))
    membership = [{"candidate_id": x["candidate_id"], "source_sha256": x["source_sha256"]} for x in all_candidates]
    membership_sha = digest(canonical(membership))
    candidate_issuers = sum(1 for x in issuer_results if x["item_2_02_candidates"])
    reconciled_issuers = sum(1 for x in issuer_results if x["historical_frame_reconciliation"] == "MATCHED")

    issuer_cohort = {
        "schema_version": 2,
        "frozen_at": frozen_at,
        "selection_mode": spec["selection_mode"],
        "selection_method": spec["selection_method"],
        "deterministic_seed": spec["deterministic_seed"],
        "historical_frame_sha256": frame_sha,
        "historical_frame_source": frame["source"],
        "issuer_pool_max": spec["issuer_pool_max"],
        "issuer_batch_size": batch_size,
        "processed_issuers": len(issuer_results),
        "stop_boundary": stop_boundary,
        "source_side_thresholds_met": stopped,
        "excluded_preexplored_ciks": spec.get("exclude_ciks", []),
        "issuers": issuer_results,
    }
    candidate_ledger = {
        "protocol_sha256": protocol_sha,
        "frozen_at": frozen_at,
        "membership_sha256": membership_sha,
        "historical_frame_sha256": frame_sha,
        "candidates": all_candidates,
    }
    state = "FROZEN_CANDIDATE_MEMBERSHIP" if stopped else "FROZEN_UNDERSIZED"
    report = {
        "schema_version": 2,
        "state": state,
        "frozen_at": frozen_at,
        "price_data_accessed_by_this_workflow": False,
        "selection_mode": spec["selection_mode"],
        "historical_frame_sha256": frame_sha,
        "historical_frame_parquet_sha256": frame["source"]["parquet_sha256"],
        "processed_issuers": len(issuer_results),
        "issuer_pool_max": len(selected_pool),
        "stop_boundary": stop_boundary,
        "candidate_count": len(all_candidates),
        "issuers_with_item_2_02_candidates": candidate_issuers,
        "reconciled_issuers": reconciled_issuers,
        "issuers_requiring_frame_reconciliation_review": len(issuer_results) - reconciled_issuers,
        "freeze_min_item_2_02_candidates": target_candidates,
        "freeze_min_item_2_02_issuers": target_issuers,
        "minimum_eligible_events_target": protocol["minimum_eligible_events"],
        "minimum_unique_issuers_target": protocol["minimum_unique_issuers"],
        "membership_sha256": membership_sha,
        "filing_screen": [spec["filing_screen_start"], spec["filing_screen_end"]],
        "event_window": [spec["event_window_start"], spec["event_window_end"]],
        "accepted_events": 0,
        "sec_transport": transport,
        "limitations": spec.get("limitations", []) + [
            "Historical-frame mirror rows define discovery order only; SEC submissions are the candidate source.",
            "Primary filing/release archival, first-public timing, common-stock/exchange identity, provider rights and corporate-action review remain unresolved.",
            "No clean-cohort market prices were accessed by this workflow.",
        ],
    }

    for name, value in (
        ("issuer-cohort.json", issuer_cohort),
        ("candidate-ledger.json", candidate_ledger),
        ("discovery-report.json", report),
    ):
        (root / name).write_bytes(canonical(value))
    return issuer_cohort, candidate_ledger, report
