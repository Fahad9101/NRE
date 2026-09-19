"""Reproducible offline normalized inputs -> daily reaction dataset.

The normalized bundle is a reviewed input contract, not automatic event-time
discovery. Every output is anchored to the previous regular-session close.
"""
import json
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from zoneinfo import TZPATH
from .calendar import Calendar
from .core import DataError, asof, canonical, digest, iso, number, timestamp, unique


def validate(bundle, calendar):
    if bundle.get("schema_version") != 1 or type(bundle.get("synthetic")) is not bool:
        raise DataError("schema_version=1 and explicit synthetic boolean required")
    cutoff = timestamp(bundle["as_of"])
    if bundle["availability_mode"] not in {"historical_reconstruction", "forward_observed"}:
        raise DataError("invalid availability mode")
    sources = unique(bundle["sources"], "source_id")
    securities = unique(bundle["securities"], "security_id")
    providers = unique(bundle["providers"], "provider_id")
    events = unique(bundle["events"], "event_id")
    unique(bundle["events"], "cluster_id")
    unique(bundle["prices"], "price_id")
    for source in sources.values():
        if not isinstance(source["text"], str) or not source["url"]:
            raise DataError("source text/url required")
        if not bundle["synthetic"] and not source["url"].startswith("https://"):
            raise DataError("real-data source requires an HTTPS provenance URL")
        if timestamp(source["first_seen_at"]) > timestamp(source["retrieved_at"]):
            raise DataError("source observation chronology invalid")
        if timestamp(source["retrieved_at"]) > cutoff:
            raise DataError("source retrieved after dataset as_of")
        if source.get("sha256") and source["sha256"] != digest(source["text"].encode()):
            raise DataError("source checksum mismatch")
    for security in securities.values():
        if security["source_id"] not in sources:
            raise DataError("security source missing")
        timestamp(security["available_at"])
        timestamp(security["valid_from"])
        if not security["company_id"] or not security["ticker"]:
            raise DataError("security identity missing")
        if security.get("valid_to") and timestamp(security["valid_to"]) <= timestamp(security["valid_from"]):
            raise DataError("invalid security validity interval")
    for event in events.values():
        if event["source_id"] not in sources or event["security_id"] not in securities:
            raise DataError("event foreign key missing")
        timestamp(event["cutoff"])
        if timestamp(event["cutoff"]) > cutoff:
            raise DataError("event cutoff after dataset as_of")
        if event["precision"] == "second":
            timestamp(event["published_at"])
        if type(event["first_public_verified"]) is not bool:
            raise DataError("first-public verification must be boolean")
        if event["first_public_verified"] and event["precision"] == "second":
            evidence = event.get("timestamp_evidence")
            if not evidence or evidence not in sources[event["source_id"]]["text"]:
                raise DataError("timestamp evidence missing from source")
    seen = set()
    for bar in bundle["prices"]:
        if bar["source_id"] not in sources or bar["security_id"] not in securities:
            raise DataError("price foreign key missing")
        if bar["provider_id"] not in providers:
            raise DataError("price provider missing")
        key = (bar["security_id"], bar["session"])
        if key in seen:
            raise DataError("duplicate daily bar; select one provider/revision per snapshot")
        seen.add(key)
        _, close = calendar.bounds(bar["session"])
        if timestamp(bar["available_at"]) < close:
            raise DataError("daily bar available before session close")
        for field in ("open", "high", "low", "close"):
            number(bar[field], positive=True)
        number(bar["volume"])
        if bar["volume"] < 0 or not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
            raise DataError("invalid OHLCV")
        for flag in ("complete", "corporate_actions_verified", "halted"):
            if type(bar[flag]) is not bool:
                raise DataError("bar quality flag must be boolean")
        if bar["price_basis"] != "raw":
            raise DataError("M1 requires raw prices and explicit action audit")
    for action in bundle.get("corporate_actions", []):
        if action["security_id"] not in securities or action["source_id"] not in sources:
            raise DataError("action foreign key missing")
        timestamp(action["available_at"])
    for feature in bundle.get("features", []):
        if feature["security_id"] not in securities or feature["source_id"] not in sources:
            raise DataError("feature foreign key missing")
        asof([feature], bundle["as_of"], bundle["availability_mode"])
    return sources, securities, providers


def event_outcome(event, bundle, calendar, sources, securities, providers):
    result = {"event_id": event["event_id"], "security_id": event["security_id"],
              "state": "QUARANTINED", "reasons": [], "labels": {}, "features": {},
              "target_version": "previous-regular-close-v1", "synthetic": bundle["synthetic"]}

    def stop(reason):
        result["reasons"].append(reason)
        return result

    if event["precision"] != "second":
        return stop("AMBIGUOUS_PUBLICATION_TIME")
    if not event["first_public_verified"]:
        return stop("FIRST_PUBLIC_TIME_UNVERIFIED")
    pub, cut = timestamp(event["published_at"]), timestamp(event["cutoff"])
    src = sources[event["source_id"]]
    available = pub
    if bundle["availability_mode"] == "forward_observed":
        available = max(pub, timestamp(src["first_seen_at"]))
    if available > cut:
        return stop("NEWS_NOT_AVAILABLE_AT_CUTOFF")
    security = securities[event["security_id"]]
    if security["exchange"] not in {"NASDAQ", "NYSE", "NYSE American"} or security["security_type"] != "common_stock":
        return stop("INELIGIBLE_SECURITY")
    identity_available = timestamp(security["available_at"])
    if bundle["availability_mode"] == "forward_observed":
        identity_available = max(identity_available, timestamp(sources[security["source_id"]]["first_seen_at"]))
    if identity_available > pub or timestamp(security["valid_from"]) > pub:
        return stop("IDENTITY_NOT_KNOWN_AT_RELEASE")
    if security.get("valid_to") and pub >= timestamp(security["valid_to"]):
        return stop("IDENTITY_EXPIRED")
    try:
        session, timing = calendar.classify(event["published_at"])
        result.update(reaction_session=session, release_timing=timing)
        if timing in {"regular", "bell_ambiguous"}:
            return stop("INTRADAY_OR_BELL_REQUIRES_FINER_DATA")
        previous = calendar.offset(session, -1)
    except DataError:
        return stop("CALENDAR_OUT_OF_RANGE")
    # B open forecasts cannot originate after the opening price is already known.
    if cut >= calendar.bounds(session)[0]:
        return stop("CUTOFF_NOT_BEFORE_REACTION_OPEN")
    result["features"] = asof([r for r in bundle.get("features", [])
                               if r["security_id"] == event["security_id"]],
                              event["cutoff"], bundle["availability_mode"])
    bars = {b["session"]: b for b in bundle["prices"] if b["security_id"] == event["security_id"]}
    anchor = bars.get(previous)
    if not anchor:
        return stop("MISSING_PREVIOUS_SESSION")
    result["anchor"] = {"price_id": anchor["price_id"], "session": previous,
                        "price": anchor["close"], "basis": "previous_regular_close"}
    maturity = timestamp(bundle["as_of"])

    def quality(window):
        if any(d not in bars for d in window):
            return "MISSING_SESSION"
        selected = [bars[d] for d in window]
        if len({(b["provider_id"], b["feed"], b["price_basis"]) for b in selected}) != 1:
            return "MIXED_PRICE_FEEDS"
        for b in selected:
            provider = providers[b["provider_id"]]
            if provider.get("research_permitted") is not True or not provider.get("terms_url"):
                return "PROVIDER_USE_UNVERIFIED"
            if b["feed"] not in provider.get("feeds", []):
                return "UNDECLARED_FEED"
            if provider.get("session_scope") != "regular":
                return "REGULAR_SESSION_COVERAGE_UNVERIFIED"
            if not b["complete"] or b["halted"] or b["volume"] == 0:
                return "INCOMPLETE_OR_HALTED_SESSION"
            if not b["corporate_actions_verified"]:
                return "CORPORATE_ACTION_AUDIT_MISSING"
            if timestamp(b["available_at"]) > maturity:
                return "LABEL_NOT_MATURE"
        if any(a["security_id"] == event["security_id"] and window[0] < a["effective_date"] <= window[-1]
               for a in bundle.get("corporate_actions", [])):
            return "CORPORATE_ACTION_IN_WINDOW"
        return None

    if timestamp(anchor["available_at"]) > cut:
        return stop("ANCHOR_UNAVAILABLE_AT_CUTOFF")
    if bundle["availability_mode"] == "forward_observed" and timestamp(sources[anchor["source_id"]]["first_seen_at"]) > cut:
        return stop("ANCHOR_NOT_OBSERVED_AT_CUTOFF")
    basic_error = quality([previous, session])
    if basic_error:
        return stop(basic_error)
    current, p = bars[session], anchor["close"]

    def label(value, window, reason=None):
        observed = [bars[d] for d in window if d in bars]
        available = max((timestamp(b["available_at"]) for b in observed), default=maturity)
        if bundle["availability_mode"] == "forward_observed":
            available = max([available] + [timestamp(sources[b["source_id"]]["first_seen_at"]) for b in observed])
        return {"value": value, "reason": reason, "window": window,
                "price_ids": [b["price_id"] for b in observed],
                "label_available_at": iso(available) if reason is None else None}

    window = [previous, session]
    for field in ("open", "high", "low", "close"):
        result["labels"]["day1_" + field + "_return"] = label(current[field] / p - 1, window)
    gap = current["open"] / p - 1
    for threshold in (3, 5, 10, 15, 20, 30):
        # Compare prices to avoid threshold drift from subtractive cancellation.
        reached = Decimal(str(current["open"])) >= Decimal(str(p)) * (1 + Decimal(threshold) / 100)
        result["labels"][f"gap_ge_{threshold}pct"] = label(reached, window)
    if Decimal(str(current["open"])) >= Decimal(str(p)) * Decimal("1.005"):
        result["labels"]["positive_gap_retained_half"] = label(current["close"] >= (current["open"] + p) / 2, window)
        result["labels"]["positive_gap_filled"] = label(current["low"] <= p, window)
    else:
        for name in ("positive_gap_retained_half", "positive_gap_filled"):
            result["labels"][name] = label(None, window, "NOT_POSITIVE_GAP_GE_0_5PCT")
    for n in (2, 5, 10, 20):
        try:
            window = [previous] + [calendar.offset(session, i) for i in range(n)]
            reason = quality(window)
        except DataError:
            reason, window = "CALENDAR_OUT_OF_RANGE", []
        value = None if reason else bars[window[-1]]["close"] / p - 1
        result["labels"][f"session_{n}_close_return"] = label(value, window, reason)
    result["state"] = "MAPPED"
    return result


def build(bundle):
    cal = Calendar()
    sources, securities, providers = validate(bundle, cal)
    results = [event_outcome(event, bundle, cal, sources, securities, providers)
               for event in sorted(bundle["events"], key=lambda r: r["event_id"])]
    mapped = [r for r in results if r["state"] == "MAPPED"]
    full = [r for r in mapped if r["labels"]["session_20_close_return"]["value"] is not None]
    counts = Counter(reason for r in results for reason in r["reasons"])
    report = {"synthetic": bundle["synthetic"], "events": len(results), "mapped_day1": len(mapped),
              "complete_20_session": len(full),
              "unique_issuers": len({securities[r["security_id"]]["company_id"] for r in full}),
              "quarantined": len(results) - len(mapped), "reasons": dict(sorted(counts.items())),
              "historical_acceptance": "NOT_EVALUATED" if not bundle["synthetic"] else "NOT_APPLICABLE_SYNTHETIC",
              "note": "Counts alone cannot certify sampling, timestamp review or survivorship coverage."}
    return results, report


def write_snapshot(bundle, output):
    results, report = build(bundle)
    root = Path(output)
    input_bytes = canonical(bundle)
    code = {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.iterdir())
            if p.suffix in {".py", ".sql", ".json"}}
    tzfile = next((Path(p) / "America/New_York" for p in TZPATH
                   if (Path(p) / "America/New_York").exists()), None)
    if tzfile is None:
        raise DataError("OS timezone bytes required for reproducible calendar metadata")
    runtime = {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
               "timezone_sha256": digest(tzfile.read_bytes())}
    identity = {"schema_version": 1, "input_sha256": digest(input_bytes), "code": code, "runtime": runtime,
                "output_sha256": digest(canonical(results)), "report_sha256": digest(canonical(report))}
    sid = digest(canonical(identity))
    destination = root / sid
    if destination.exists():
        verify_snapshot(destination)
        return destination, report
    # Validate everything before materializing a new snapshot; no live fetch during replay.
    root.mkdir(parents=True, exist_ok=True)
    import tempfile
    temporary = Path(tempfile.mkdtemp(prefix=".nre-", dir=root))
    try:
        files = {"input.json": input_bytes, "outcomes.json": canonical(results), "report.json": canonical(report)}
        for source in bundle["sources"]:
            body = source["text"].encode("utf-8")
            files["sources/" + digest(body) + ".txt"] = body
        for name, body in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        manifest = dict(identity, snapshot_id=sid, files={k: digest(v) for k, v in sorted(files.items())})
        with sqlite3.connect(temporary / "dataset.sqlite") as db:
            db.executescript(Path(__file__).with_name("schema.sql").read_text())
            for source in bundle["sources"]:
                db.execute("INSERT INTO sources VALUES (?,?,?)", (source["source_id"], digest(source["text"].encode()), canonical(source).decode()))
            for security in bundle["securities"]:
                db.execute("INSERT INTO securities VALUES (?,?,?)", (security["security_id"], security["source_id"], canonical(security).decode()))
            for event in bundle["events"]:
                db.execute("INSERT INTO events VALUES (?,?,?,?,?)", (event["event_id"], event["security_id"], event["source_id"], event["cluster_id"], canonical(event).decode()))
            for bar in bundle["prices"]:
                db.execute("INSERT INTO prices VALUES (?,?,?,?)", (bar["price_id"], bar["security_id"], bar["source_id"], canonical(bar).decode()))
            for row in results:
                db.execute("INSERT INTO outcomes VALUES (?,?,?)", (row["event_id"], row["state"], canonical(row).decode()))
            db.execute("INSERT INTO snapshots VALUES (?,?)", (sid, canonical(identity).decode()))
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise DataError("SQLite foreign-key failure")
        manifest["files"]["dataset.sqlite"] = digest((temporary / "dataset.sqlite").read_bytes())
        (temporary / "manifest.json").write_bytes(canonical(manifest))
        temporary.rename(destination)
    finally:
        import shutil
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination, report


def verify_snapshot(path):
    root = Path(path)
    manifest = json.loads((root / "manifest.json").read_text())
    identity = {key: manifest[key] for key in ("schema_version", "input_sha256", "code", "runtime", "output_sha256", "report_sha256")}
    if digest(canonical(identity)) != manifest["snapshot_id"] or root.name != manifest["snapshot_id"]:
        raise DataError("snapshot identity mismatch")
    if not {"input.json", "outcomes.json", "report.json", "dataset.sqlite"} <= manifest["files"].keys():
        raise DataError("snapshot missing required file hashes")
    for name, sha in manifest["files"].items():
        file = (root / name).resolve()
        if not file.is_relative_to(root.resolve()) or digest(file.read_bytes()) != sha:
            raise DataError("snapshot file checksum mismatch")
    if digest((root / "input.json").read_bytes()) != manifest["input_sha256"]:
        raise DataError("input hash mismatch")
    if digest((root / "outcomes.json").read_bytes()) != manifest["output_sha256"]:
        raise DataError("output hash mismatch")
    if digest((root / "report.json").read_bytes()) != manifest["report_sha256"]:
        raise DataError("report hash mismatch")
    return manifest
