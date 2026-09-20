"""Deterministic Milestone 1 SEC cohort discovery and membership freeze.

This module discovers filing candidates only. It never imports market prices.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .core import DataError, canonical, digest, iso
from .ingestion import PublicClient, SecRelayClient, sec_candidates


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DataError("invalid ISO date") from exc


def exchange_issuers(document, allowed_exchanges):
    """Return unique SEC issuers with at least one ticker on an allowed exchange."""
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
        # The same CIK can have several listed classes. Preserve them instead of inflating issuer count.
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


def relevant_history_files(document, screen_start):
    """Return continuation files needed only when recent submissions do not reach screen_start."""
    start = _date(screen_start)
    filings = document.get("filings", {})
    recent = filings.get("recent", {})
    dates = recent.get("filingDate")
    if not isinstance(dates, list) or not dates:
        raise DataError("SEC submissions missing recent filing dates")
    parsed = [_date(x) for x in dates]
    if min(parsed) <= start:
        return []

    needed = []
    for item in filings.get("files", []):
        if not isinstance(item, dict) or not all(k in item for k in ("name", "filingFrom", "filingTo")):
            raise DataError("SEC continuation metadata incomplete")
        low, high = _date(item["filingFrom"]), _date(item["filingTo"])
        if low <= start <= high or high >= start:
            needed.append(item)
    if not needed:
        raise DataError("SEC submissions do not cover filing screen start")
    needed.sort(key=lambda x: x["name"])
    return needed


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


def _decode_sec_text(body):
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataError("SEC primary filing is not UTF-8 decodable") from exc


def freeze_sec_cohort(spec, protocol, output, user_agent):
    """Fetch, enumerate and freeze a clean SEC filing candidate cohort.

    No market-price endpoint is called here. Raw network objects stay under output/raw;
    callers may preserve them as a private workflow artifact rather than committing them.
    """
    if spec.get("schema_version") != 1:
        raise DataError("unsupported SEC cohort spec")
    protocol_sha = digest(canonical(protocol))
    if spec.get("protocol_sha256") != protocol_sha:
        raise DataError("cohort spec protocol hash mismatch")
    if spec.get("event_window_start") != protocol.get("event_window_start") or spec.get("event_window_end") != protocol.get("event_window_end"):
        raise DataError("cohort spec event window differs from pilot protocol")

    root = Path(output)
    raw_root = root / "raw"
    root.mkdir(parents=True, exist_ok=True)
    transport = spec.get("sec_transport", "direct")
    if transport == "direct":
        client = PublicClient(user_agent)
    elif transport == "r_jina_relay":
        client = SecRelayClient(user_agent)
    else:
        raise DataError("unsupported SEC cohort transport")

    selection_raw, selection_meta = client.fetch(spec["selection_source_url"], raw_root)
    try:
        selection_document = json.loads(selection_raw)
    except json.JSONDecodeError as exc:
        raise DataError("invalid SEC exchange directory JSON") from exc
    issuers = exchange_issuers(selection_document, spec["allowed_exchanges"])
    selected = deterministic_issuer_sample(
        issuers,
        spec["sample_size"],
        spec["deterministic_seed"],
        spec.get("exclude_ciks", []),
    )

    all_candidates = []
    issuer_results = []
    for issuer in selected:
        cik = issuer["cik"]
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        body, submissions_meta = client.fetch(submissions_url, raw_root)
        try:
            document = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataError("invalid SEC submissions JSON") from exc

        ledgers = [sec_candidates(document, cik)]
        observations = [submissions_meta]
        for history in relevant_history_files(document, spec["filing_screen_start"]):
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
            primary_body, primary_meta = client.fetch(row["url"], raw_root)
            primary_text = _decode_sec_text(primary_body)
            source_text_sha = digest(primary_text.encode("utf-8"))
            all_candidates.append({
                "candidate_id": row["candidate_id"],
                "source_sha256": source_text_sha,
                "cik": cik,
                "filing_date": row["filing_date"],
                "form": row["form"],
                "items": row["items"],
                "primary_url": row["url"],
                "primary_source_sha256": primary_meta["sha256"],
                "primary_source_representation": primary_meta.get("source_representation", "raw"),
                "primary_transport_sha256": primary_meta.get("transport_sha256"),
                "discovery_submission_sha256": submissions_meta["sha256"],
                "discovery_submission_representation": submissions_meta.get("source_representation", "raw"),
            })
            issuer_candidate_ids.append(row["candidate_id"])

        issuer_results.append({
            **issuer,
            "submissions_url": submissions_url,
            "submissions_sha256": submissions_meta["sha256"],
            "observations": len(observations),
            "item_2_02_candidates": len(issuer_candidate_ids),
            "candidate_ids": issuer_candidate_ids,
        })

    # SEC accessions should be globally unique. Duplicate discovery is a hard failure.
    ids = [x["candidate_id"] for x in all_candidates]
    if len(ids) != len(set(ids)):
        raise DataError("duplicate accession in frozen candidate membership")
    all_candidates.sort(key=lambda x: x["candidate_id"])
    frozen_at = iso(datetime.now(timezone.utc))
    membership = [{"candidate_id": x["candidate_id"], "source_sha256": x["source_sha256"]} for x in all_candidates]
    membership_sha = digest(canonical(membership))

    issuer_cohort = {
        "schema_version": 1,
        "frozen_at": frozen_at,
        "selection_source_url": spec["selection_source_url"],
        "selection_source_sha256": selection_meta["sha256"],
        "selection_source_retrieved_at": selection_meta["retrieved_at"],
        "selection_source_representation": selection_meta.get("source_representation", "raw"),
        "selection_transport": selection_meta.get("transport", "direct"),
        "selection_transport_sha256": selection_meta.get("transport_sha256"),
        "raw_sec_bytes_archived": selection_meta.get("raw_sec_bytes_archived", True),
        "selection_method": spec["selection_method"],
        "deterministic_seed": spec["deterministic_seed"],
        "sample_size": spec["sample_size"],
        "excluded_preexplored_ciks": spec.get("exclude_ciks", []),
        "issuers": issuer_results,
    }
    candidate_ledger = {
        "protocol_sha256": protocol_sha,
        "frozen_at": frozen_at,
        "membership_sha256": membership_sha,
        "candidates": all_candidates,
    }
    issuers_with_candidates = sum(1 for x in issuer_results if x["item_2_02_candidates"])
    report = {
        "schema_version": 1,
        "state": "FROZEN_CANDIDATE_MEMBERSHIP" if len(all_candidates) >= protocol["minimum_eligible_events"] else "FROZEN_UNDERSIZED",
        "frozen_at": frozen_at,
        "price_data_accessed_by_this_workflow": False,
        "selected_issuers": len(selected),
        "issuers_with_item_2_02_candidates": issuers_with_candidates,
        "candidate_count": len(all_candidates),
        "minimum_eligible_events_target": protocol["minimum_eligible_events"],
        "minimum_unique_issuers_target": protocol["minimum_unique_issuers"],
        "membership_sha256": membership_sha,
        "selection_source_sha256": selection_meta["sha256"],
        "filing_screen": [spec["filing_screen_start"], spec["filing_screen_end"]],
        "event_window": [spec["event_window_start"], spec["event_window_end"]],
        "accepted_events": 0,
        "sec_transport": transport,
        "raw_sec_bytes_archived": selection_meta.get("raw_sec_bytes_archived", True),
        "limitations": spec.get("limitations", []) + [
            "Item 2.02 membership is frozen before price acquisition, but publication-time eligibility, duplicate economic-event review, contemporaneous security identity and price-provider acceptance remain unresolved.",
            "Raw network objects are not intended for the public repository; preserve the workflow artifact or refetch immutable SEC primary filings and verify hashes before final acceptance.",
        ],
    }

    for name, value in (
        ("issuer-cohort.json", issuer_cohort),
        ("candidate-ledger.json", candidate_ledger),
        ("discovery-report.json", report),
    ):
        (root / name).write_bytes(canonical(value))
    return issuer_cohort, candidate_ledger, report
