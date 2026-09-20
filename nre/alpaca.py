"""Audit connector daily-bar exports without promoting them to accepted labels."""
from datetime import date, time
from .calendar import Calendar
from .core import DataError, canonical, digest, number, timestamp


def audit_daily(payload, retrieved_at):
    """Input is the decoded get_stock_bars structured response, not an MCP envelope.

    Calendar coverage is measured against the requested interval, never inferred
    from the first/last returned bar. Missing rows are not filled or shifted.
    """
    retrieved = timestamp(retrieved_at)
    cal = Calendar()
    req = payload["request"]
    if payload.get("tool") != "get_stock_bars" or req.get("timeframe") != "1Day":
        raise DataError("expected Alpaca connector 1Day export")
    if req.get("feed") != "sip":
        raise DataError("explicit SIP feed required; no fallback")
    symbols = req.get("symbols")
    if not isinstance(symbols, list) or not symbols or any(not isinstance(s, str) or not s for s in symbols):
        raise DataError("nonempty requested symbol list required")
    if len(set(symbols)) != len(symbols):
        raise DataError("duplicate requested symbol")
    # This auditor deliberately supports whole date windows only.
    start, end = date.fromisoformat(req["start"]), date.fromisoformat(req["end"])
    if start > end or str(start) < cal.spec["start"] or str(end) > cal.spec["end"]:
        raise DataError("unsupported date interval")
    if not req.get("asof"):
        raise DataError("explicit historical symbol asof required")
    asof = date.fromisoformat(req["asof"])
    if asof > retrieved.astimezone(cal.zone).date():
        raise DataError("symbol asof is in the future")
    if req.get("tz") != "America/New_York" or req.get("sort") != "asc":
        raise DataError("New York timezone and ascending order required")
    if req.get("currency") not in (None, "USD"):
        raise DataError("USD prices required")
    expected = [d for d in cal.days if str(start) <= d <= str(end)]
    if not expected or cal.bounds(expected[-1])[1] > retrieved:
        raise DataError("requested window not yet closed or has no sessions")
    bars = payload["bars"]
    if not isinstance(bars, dict) or set(bars) - set(symbols):
        raise DataError("unexpected symbol in export")
    counts = payload["counts"]
    total = 0
    coverage = {}
    for symbol in symbols:
        rows = bars.get(symbol, [])
        seen = []
        zero_volume = []
        for row in rows:
            if row.get("symbol") != symbol:
                raise DataError("bar symbol mismatch")
            t = timestamp(row["timestamp"]).astimezone(cal.zone)
            day = t.date().isoformat()
            if t.time() != time(0):
                raise DataError("daily timestamp must be New York midnight")
            if day in seen or day not in expected or (seen and day < seen[-1]):
                raise DataError("duplicate, unordered or out-of-window session")
            for field in ("open", "high", "low", "close"):
                number(row[field], positive=True)
            number(row["volume"])
            if row["volume"] < 0 or not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
                raise DataError("invalid OHLCV")
            if row["volume"] == 0:
                zero_volume.append(day)
            seen.append(day)
        if counts["per_symbol"].get(symbol, 0) != len(rows):
            raise DataError("per-symbol count mismatch")
        total += len(rows)
        coverage[symbol] = {"expected": len(expected), "received": len(rows),
                            "missing_sessions": sorted(set(expected) - set(seen)),
                            "zero_volume_sessions": zero_volume}
    if counts["records"] != total or counts["symbols"] != len(bars):
        raise DataError("export count mismatch")
    blockers = ["REGULAR_SESSION_VOLUME_UNVERIFIED", "ADJUSTMENT_UNVERIFIED",
                "CORPORATE_ACTION_REVIEW_REQUIRED", "HISTORICAL_IDENTITY_REVIEW_REQUIRED",
                "PROVIDER_RIGHTS_REVIEW_REQUIRED", "PAGINATION_METADATA_UNAVAILABLE"]
    if any(v["missing_sessions"] for v in coverage.values()):
        blockers.append("MISSING_SESSIONS")
    if any(v["zero_volume_sessions"] for v in coverage.values()):
        blockers.append("ZERO_VOLUME_SESSIONS")
    return {"state": "STAGED_REVIEW_REQUIRED", "accepted_for_labels": False,
            "retrieved_at": retrieved_at, "payload_sha256": digest(canonical(payload)),
            "hash_basis": "canonical decoded connector payload", "request": req,
            "record_count": total, "coverage": coverage, "blockers": blockers,
            "note": "Calendar coverage is not proof of trade completeness or historical availability."}
