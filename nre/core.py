"""Strict times, immutable JSON, and point-in-time joins."""
import hashlib
import json
import math
from datetime import datetime, timezone


class DataError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise DataError("timestamp must include time and UTC offset")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataError("invalid timestamp") from exc
    if result.tzinfo is None:
        raise DataError("naive timestamp rejected")
    return result.astimezone(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def number(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError("numeric value required")
    if not math.isfinite(value) or (positive and value <= 0):
        raise DataError("invalid or nonfinite numeric value")
    return value


def unique(rows, key):
    result = {}
    for row in rows:
        identity = row[key]
        if not isinstance(identity, str) or not identity or identity in result:
            raise DataError("duplicate/invalid " + key)
        result[identity] = row
    return result


def asof(rows, cutoff, mode="historical_reconstruction"):
    """Latest revision per feature, with availability AND valid-time filtering."""
    if mode not in {"historical_reconstruction", "forward_observed"}:
        raise DataError("unknown availability mode")
    t = timestamp(cutoff)
    selected = {}
    for row in rows:
        available = timestamp(row["available_at"])
        if mode == "forward_observed":
            available = max(available, timestamp(row["first_seen_at"]))
        if available > t or timestamp(row["valid_from"]) > t:
            continue
        if row.get("valid_to") and t >= timestamp(row["valid_to"]):
            continue
        if row.get("label_available_at") and timestamp(row["label_available_at"]) > t:
            continue
        key = row["name"]
        rank = (available, row["revision_id"])
        if key not in selected or rank > selected[key][0]:
            selected[key] = (rank, row)
    return {key: row for key, (_, row) in sorted(selected.items())}
