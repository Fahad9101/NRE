"""Rebuild the locked issuer roster from SEC-rendered N-PORT text."""
import argparse
import re
from collections import defaultdict
from pathlib import Path

from .core import DataError, canonical, digest
from .m5_phase1b_audit import load

FRAME = "config/m6-guidance-frame.json"


def field(section, label):
    values = re.findall(rf"(?m)^{re.escape(label)}[^\S\n]*\n([^\n]+)", section)
    if len(values) != 1 or not values[0].strip():
        raise DataError(f"Expected one SEC filing field: {label}")
    return values[0].strip()


def holdings(payload):
    sections = payload.decode("utf-8").replace("\r\n", "\n").split("Item C.1. Identification of investment.")
    if not sections[1:]:
        raise DataError("Missing SEC portfolio positions")
    by_name = defaultdict(list)
    identifiers = set()
    for section in sections[1:]:
        header = section.split("Item C.2. Amount of each investment.", 1)[0]
        name = field(header, "a. Name of issuer (if any).")
        title = field(header, "c. Title of the issue or description of the investment.")
        isin = field(header, "ISIN")
        country = field(section, "Report the ISO country code that corresponds to the country where the issuer is organized.")
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin) or isin in identifiers:
            raise DataError("Invalid or duplicate portfolio security identifier")
        identifiers.add(isin)
        by_name[name].append({"isin": isin, "title": title, "country": country})
    return [{"issuer": name, "securities": sorted(securities, key=lambda row: row["isin"])}
            for name, securities in sorted(by_name.items(), key=lambda item: item[0].casefold())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path, help="Archived SEC-rendered filing represented as text")
    parser.add_argument("--frame", type=Path, default=Path(FRAME))
    args = parser.parse_args()
    frame = load(args.frame)
    payload = args.payload.read_bytes()
    if digest(payload) != frame["nport_source"]["payload_sha256"]:
        raise DataError("Roster source digest mismatch")
    roster = holdings(payload)
    if digest(canonical(roster)) != frame["issuer_roster_sha256"] or roster != frame["issuer_roster"]:
        raise DataError("Rebuilt issuer roster does not match the lock")
    print(f"Verified {len(roster)} issuers and {sum(len(row['securities']) for row in roster)} securities")


if __name__ == "__main__":
    main()
