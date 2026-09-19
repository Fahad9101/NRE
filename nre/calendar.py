"""Versioned, bounded session calendar. Unknown years fail closed."""
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import DataError, timestamp


class Calendar:
    def __init__(self, spec=None):
        self.spec = spec or json.loads(Path(__file__).with_name("calendar-2026.json").read_text())
        self.zone = ZoneInfo(self.spec["timezone"])
        start, end = date.fromisoformat(self.spec["start"]), date.fromisoformat(self.spec["end"])
        self.days = []
        while start <= end:
            if start.weekday() < 5 and start.isoformat() not in self.spec["holidays"]:
                self.days.append(start.isoformat())
            start += timedelta(days=1)

    def bounds(self, day):
        if day not in self.days:
            raise DataError("not a supported session: " + day)
        d = date.fromisoformat(day)
        close = time.fromisoformat(self.spec["early_closes"].get(day, "16:00"))
        return (datetime.combine(d, time(9, 30), self.zone).astimezone(timezone.utc),
                datetime.combine(d, close, self.zone).astimezone(timezone.utc))

    def classify(self, value):
        t = timestamp(value)
        day = t.astimezone(self.zone).date().isoformat()
        if not self.spec["start"] <= day <= self.spec["end"]:
            raise DataError("CALENDAR_OUT_OF_RANGE")
        if day not in self.days:
            timing = "closed"
        else:
            opening, close = self.bounds(day)
            if t == opening or t == close:
                return day, "bell_ambiguous"
            if opening < t < close:
                return day, "regular"
            if t < opening:
                return day, "premarket"
            timing = "after_hours"
        future = [d for d in self.days if d > day]
        if not future:
            raise DataError("CALENDAR_OUT_OF_RANGE")
        return future[0], timing

    def offset(self, day, offset):
        if day not in self.days:
            raise DataError("not a supported session")
        i = self.days.index(day) + offset
        if not 0 <= i < len(self.days):
            raise DataError("CALENDAR_OUT_OF_RANGE")
        return self.days[i]
