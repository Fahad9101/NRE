"""Audit pre-open coverage of fiscal-quarter revenue growth from SEC filings."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from .calendar import Calendar
from .caveat_sensitivity import caveated_pairs
from .core import canonical, digest, timestamp
from .m4_scoping_evidence import assign_blocks
from .m5_phase1b_audit import load

ROOT = Path(__file__).resolve().parents[1]
SPEC = "config/m2-step3-combined-events.json"
CALENDAR = "config/m2-merged-calendar-2024-2026.json"
FREEZE = "config/m6-revenue-coverage.json"
WIRE = "reports/m6-revenue-wire-evidence-2026-11-16.json"
EXHIBITS = "reports/m6-revenue-exhibit-evidence-2026-11-16.json"
ZONE = ZoneInfo("America/New_York")
TAGS = ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax")
FIELDS = ("accessionNumber", "form", "reportDate", "filingDate", "acceptanceDateTime", "primaryDocument")
ORIGINAL_FORMS = ("10-Q", "10-K")


def filings_before(submissions, published, deadline):
    columns = submissions["filings"]["recent"]
    if len({len(columns[key]) for key in FIELDS}) != 1:
        raise ValueError("SEC submissions columns differ in length")
    local_day = published.astimezone(ZONE).date()
    eligible = []
    for accession, form, report_date, filing_date, acceptance, document in zip(
            *(columns[key] for key in FIELDS)):
        if form not in ORIGINAL_FORMS or not report_date or not acceptance:
            continue
        accepted = timestamp(acceptance)
        if not published <= accepted < deadline:
            continue
        local_accepted = accepted.astimezone(ZONE)
        if local_accepted.time() >= time(17, 30):
            continue
        period_end = date.fromisoformat(report_date)
        filed = date.fromisoformat(filing_date)
        available = max(accepted + timedelta(minutes=2), datetime.combine(filed, time.min, ZONE))
        if available < deadline and 0 <= (local_day - period_end).days <= 110:
            eligible.append((period_end, available, accession, accepted, filed, form, document))
    return eligible


def matching_revenue(facts, accession, filed, form, period_end):
    """Use comparable USD quarter figures from one accession and one tag."""
    pairs = {}
    gaap = facts["facts"].get("us-gaap", {})
    for tag in TAGS:
        quarters = defaultdict(set)
        for fact in gaap.get(tag, {}).get("units", {}).get("USD", ()):
            if (fact.get("accn") != accession or fact.get("form") != form
                    or fact.get("filed") != filed.isoformat() or not fact.get("start")):
                continue
            start, end = date.fromisoformat(fact["start"]), date.fromisoformat(fact["end"])
            value = fact["val"]
            if (80 <= (end - start).days + 1 <= 100 and type(value) in (int, float)
                    and isfinite(value) and value >= 0):
                quarters[end].add((start, value))
        current = quarters.get(period_end, set())
        prior = {(end, start, value) for end, entries in quarters.items()
                 if 340 <= (period_end - end).days <= 390 for start, value in entries}
        if len(current) == len(prior) == 1:
            current_start, current_value = next(iter(current))
            prior_end, prior_start, prior_value = next(iter(prior))
            if prior_value > 0:
                pairs[tag] = (current_start, current_value, prior_end, prior_start, prior_value)
        elif current and prior:
            # Conflicting periods or amounts within a candidate tag make it ambiguous.
            return None
    if len(set(pairs.values())) != 1:
        return None
    tag = next(iter(pairs))
    return tag, pairs[tag]


def select_growth(facts, submissions, cik, published, deadline):
    if str(facts["cik"]).zfill(10) != cik or str(submissions["cik"]).zfill(10) != cik:
        raise ValueError("SEC issuer mismatch")
    filings = filings_before(submissions, published, deadline)
    if not filings:
        return {"status": "no_eligible_filing"}
    newest = max(f[0] for f in filings)
    period_end, available, accession, accepted, filed, form, document = min(
        (f for f in filings if f[0] == newest), key=lambda f: (f[1], f[2]))
    result = {"accession": accession, "accepted_at": accepted.isoformat(),
              "availability_proxy": available.isoformat(), "filing_date": filed.isoformat(),
              "form": form, "period_end": period_end.isoformat(),
              "filing_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"}
    measure = matching_revenue(facts, accession, filed, form, period_end)
    if measure is None:
        return {"status": "unusable_revenue", **result}
    tag, (start, value, prior_end, prior_start, prior_value) = measure
    return {"status": "usable", **result, "tag": tag, "current_start": start.isoformat(),
            "prior_start": prior_start.isoformat(), "prior_end": prior_end.isoformat(),
            "current_usd": value, "prior_usd": prior_value,
            "growth_fraction": value / prior_value - 1}


def published_growth(current, previous, end, prior, published):
    period_end, prior_end = date.fromisoformat(end), date.fromisoformat(prior)
    if (not 0 <= (published.astimezone(ZONE).date() - period_end).days <= 110
            or not 340 <= (period_end - prior_end).days <= 390
            or type(current) is not int or type(previous) is not int or current < 0 or previous <= 0):
        raise ValueError("Invalid verified publication revenue pair")
    return {"status": "usable", "period_end": end, "prior_end": prior,
            "current_usd": current, "prior_usd": previous,
            "growth_fraction": current / previous - 1}


def wire_growth(row, event, deadline):
    if any(timestamp(row[left]) != timestamp(event[right])
           for left, right in (("published_at", "published_at"), ("cutoff_at", "cutoff"))):
        raise ValueError("Wire evidence timestamp does not match the pinned event")
    if row["source_url"] != event["source"]["url"] or not row["basis"]:
        raise ValueError("Wire evidence source does not match the pinned event")
    published = timestamp(row["published_at"])
    available = published + timedelta(minutes=1)
    if available >= deadline:
        return None
    result = published_growth(row["current_revenue_usd"], row["prior_revenue_usd"],
                              row["period_end"], row["prior_period_end"], published)
    return dict(result, source="original_wire", source_url=row["source_url"],
                availability_proxy=available.isoformat())


def exhibit_growth(row, event, submissions, deadline):
    cik = event["security"]["cik"]
    accession = event["candidate_id"]
    directory = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
    if (row["accession"] != accession or row["cik"] != cik or row["form"] != "8-K"
            or row["exhibit"] not in ("99.1", "99.2") or row["currency"] != "USD"
            or not row["release_url"].startswith(directory)):
        raise ValueError("Exhibit source does not match the pinned event")
    columns = submissions["filings"]["recent"]
    index = columns["accessionNumber"].index(accession)
    accepted = timestamp(columns["acceptanceDateTime"][index])
    filing_date = columns["filingDate"][index]
    if (accepted != timestamp(row["accepted_at"]) or filing_date != row["filing_date"]
            or columns["form"][index] != row["form"]):
        raise ValueError("Exhibit timing disagrees with SEC submissions")
    published = timestamp(event["published_at"])
    if (row.get("comparison_caveat") or accepted < published
            or accepted.astimezone(ZONE).time() >= time(17, 30)):
        return None
    available = max(accepted + timedelta(minutes=2),
                    datetime.combine(date.fromisoformat(filing_date), time.min, ZONE))
    if available >= deadline:
        return None
    result = published_growth(row["current_usd"], row["prior_usd"],
                              row["current_quarter_end"], row["prior_quarter_end"], published)
    return dict(result, source="sec_earnings_exhibit", source_url=row["release_url"],
                accession=accession, accepted_at=accepted.isoformat(),
                availability_proxy=available.isoformat())

def summarize(rows, clock):
    usable = [row for row in rows if row[clock]["status"] == "usable"]
    clean = [row for row in usable if row["clean_label_metadata"] and row["block"] in (3, 4, 5)]
    return {"statuses": dict(Counter(row[clock]["status"] for row in rows)),
            "usable_issuers": len({r["cik"] for r in usable}),
            "usable_sessions": len({r["reaction_session"] for r in usable}),
            "by_release_timing": dict(Counter(r["release_timing"] for r in usable)),
            "by_source": dict(Counter(r[clock].get("source", "sec_periodic_filing") for r in usable)),
            "clean_earliest_fit_rows": sum(r["clean_label_metadata"] and r["block"] < 3 for r in usable),
            "clean_development_test_rows": len(clean),
            "clean_development_test_issuers": len({r["cik"] for r in clean}),
            "clean_development_test_sessions": len({r["reaction_session"] for r in clean}),
            "clean_development_test_by_block": dict(Counter(str(r["block"]) for r in clean)),
            "clean_development_distinct_values": len({r[clock]["growth_fraction"] for r in clean}),
            "clean_development_positive": sum(r[clock]["growth_fraction"] > 0 for r in clean),
            "clean_development_negative": sum(r[clock]["growth_fraction"] < 0 for r in clean)}


def audit(cache):
    freeze = load(ROOT / FREEZE)
    spec, cal, evidence, exhibited = (load(ROOT / path) for path in (SPEC, CALENDAR, WIRE, EXHIBITS))
    for path, value in ((SPEC, spec), (CALENDAR, cal), (WIRE, evidence), (EXHIBITS, exhibited)):
        if digest(canonical(value)) != freeze["canonical_input_sha256"][path]:
            raise ValueError("Pinned cohort or calendar changed")
    calendar = Calendar(cal)
    events = spec["events"]
    if len(events) != 128 or len({e["cluster_id"] for e in events}) != 128:
        raise ValueError("Unexpected development membership")
    valid_ids = {e["event_id"] for e in events}
    wire = {row["event_id"]: row for row in evidence["rows"]}
    exhibits = {row["event_id"]: row for row in exhibited["events"]}
    if (len(wire) != len(evidence["rows"]) or len(exhibits) != len(exhibited["events"])
            or not (wire.keys() | exhibits.keys()) <= valid_ids):
        raise ValueError("Unexpected release evidence membership")
    blocks = assign_blocks([dict(e, reaction_session=e["expected_reaction_session"]) for e in events])
    caveats = caveated_pairs(spec, with_derived=True)
    cache_data, provenance, rows, sec_only = {}, {}, [], []
    for event in events:
        cik, eid = event["security"]["cik"], event["event_id"]
        if cik not in cache_data:
            paths = {kind: cache / f"{cik}-{kind}.json" for kind in ("facts", "submissions")}
            cache_data[cik] = {kind: load(path) for kind, path in paths.items() if path.is_file()}
            provenance[cik] = {kind: digest(path.read_bytes()) for kind, path in paths.items() if path.is_file()}
        data = cache_data[cik]
        published, cutoff = (timestamp(event[field]) for field in ("published_at", "cutoff"))
        session, timing = calendar.classify(event["published_at"])
        opening, _ = calendar.bounds(session)
        if session != event["expected_reaction_session"] or not published <= cutoff < opening:
            raise ValueError("Unexpected earnings event clock")
        row = {"event_id": eid, "cik": cik, "reaction_session": session, "release_timing": timing,
               "block": blocks[eid], "published_at": published.isoformat(),
               "news_cutoff_at": cutoff.isoformat(), "scheduled_open_at": opening.isoformat(),
               "clean_label_metadata": not ({"day1_open_return", "day1_close_return"} & caveats.get(eid, set()))}
        for clock, deadline in (("news_cutoff", cutoff), ("scheduled_open", opening)):
            row[clock] = (select_growth(data["facts"], data["submissions"], cik, published, deadline)
                          if len(data) == 2 else {"status": "sec_data_unavailable"})
        sec_only.append(row.copy())
        for clock, deadline in (("news_cutoff", cutoff), ("scheduled_open", opening)):
            verified = wire_growth(wire[eid], event, deadline) if eid in wire else None
            if verified is None and eid in exhibits and "submissions" in data:
                verified = exhibit_growth(exhibits[eid], event, data["submissions"], deadline)
            if verified is not None:
                row[clock] = verified
        rows.append(row)
    return {"schema_version": 1, "screened": len(rows), "issuers": len(cache_data),
            "method_sha256": digest(canonical(freeze)), "sec_response_sha256": provenance,
            "sec_only_coverage": {clock: summarize(sec_only, clock)
                                  for clock in ("news_cutoff", "scheduled_open")},
            "coverage": {clock: summarize(rows, clock) for clock in ("news_cutoff", "scheduled_open")},
            "events": sorted(rows, key=lambda r: r["event_id"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.cache)
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    print(result["coverage"])


if __name__ == "__main__":
    main()
