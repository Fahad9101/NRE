"""Public-source acquisition and conservative normalization; no scores."""
import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .core import DataError, canonical, digest, iso, timestamp


class SourceUnavailable(RuntimeError):
    pass


class SecRelayClient:
    """Read-only transport for public SEC URLs through r.jina.ai.

    The relay representation is never described as raw SEC bytes. Both the full
    relay response and extracted payload are hashed and archived, while the
    canonical SEC URL remains the source identity.
    """
    def __init__(self, user_agent, timeout=45):
        if not user_agent or not ("@" in user_agent or "https://" in user_agent):
            raise DataError("identifiable User-Agent with contact required")
        self.user_agent, self.timeout, self.last = user_agent, timeout, 0.0

    @staticmethod
    def relay_url(url):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"data.sec.gov", "www.sec.gov"}:
            raise DataError("SEC relay accepts canonical SEC HTTPS URLs only")
        path = urllib.parse.urlunparse(("http", parsed.netloc, parsed.path, "", parsed.query, ""))
        return "https://r.jina.ai/" + path

    @staticmethod
    def payload(body, canonical_url):
        try:
            text = body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DataError("SEC relay response is not UTF-8") from exc
        marker = "Markdown Content:"
        if marker not in text:
            raise DataError("SEC relay response missing Markdown Content marker")
        payload = text.split(marker, 1)[1].lstrip("\r\n ")
        lower_path = urllib.parse.urlparse(canonical_url).path.lower()
        if lower_path.endswith(".json"):
            # Relay JSON is normally emitted directly after the marker. Decode
            # one complete JSON value so relay prose/fences cannot contaminate it.
            start = min((i for i in (payload.find("{"), payload.find("[")) if i >= 0), default=-1)
            if start < 0:
                raise DataError("SEC relay JSON payload missing JSON value")
            try:
                value, _ = json.JSONDecoder().raw_decode(payload[start:])
            except json.JSONDecodeError as exc:
                raise DataError("SEC relay JSON payload invalid") from exc
            return canonical(value), "relay_json_extract"
        return payload.encode("utf-8"), "relay_markdown"

    def fetch(self, url, output):
        transport_url = self.relay_url(url)
        for attempt in range(3):
            time.sleep(max(0, 0.25 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                request = urllib.request.Request(
                    transport_url,
                    headers={"User-Agent": self.user_agent, "Accept": "text/plain"},
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    relay_body = response.read(20_000_001)
                    if len(relay_body) > 20_000_000:
                        raise SourceUnavailable("relay response too large")
                break
            except urllib.error.HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise SourceUnavailable("RELAY_HTTP_" + str(exc.code)) from exc
            except (OSError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise SourceUnavailable("RELAY_" + type(exc).__name__) from exc

        payload, representation = self.payload(relay_body, url)
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        relay_sha = digest(relay_body)
        payload_sha = digest(payload)
        relay_path = root / (relay_sha + ".relay.raw")
        payload_path = root / (payload_sha + ".payload")
        if relay_path.exists() and relay_path.read_bytes() != relay_body:
            raise DataError("relay raw object collision")
        if payload_path.exists() and payload_path.read_bytes() != payload:
            raise DataError("relay payload collision")
        relay_path.write_bytes(relay_body)
        payload_path.write_bytes(payload)
        metadata = {
            "url": url,
            "canonical_url": url,
            "transport": "r.jina.ai",
            "transport_url": transport_url,
            "transport_sha256": relay_sha,
            "sha256": payload_sha,
            "size": len(payload),
            "transport_size": len(relay_body),
            "retrieved_at": iso(datetime.now(timezone.utc)),
            "raw_file": relay_path.name,
            "payload_file": payload_path.name,
            "source_representation": representation,
            "raw_sec_bytes_archived": False,
        }
        (root / (digest(canonical(metadata)) + ".json")).write_bytes(canonical(metadata))
        return payload, metadata


class PublicClient:
    """Serial client, at most 4 requests/sec; no auth bypass or retry on 403."""
    def __init__(self, user_agent, timeout=20):
        if not user_agent or not ("@" in user_agent or "https://" in user_agent):
            raise DataError("identifiable User-Agent with contact required")
        self.user_agent, self.timeout, self.last = user_agent, timeout, 0.0

    def fetch(self, url, output):
        parsed = urllib.parse.urlparse(url)
        allowed = {"data.sec.gov", "www.sec.gov", "www.nasdaqtrader.com"}
        if parsed.scheme != "https" or parsed.hostname not in allowed:
            raise DataError("unsupported public source")
        for attempt in range(3):
            time.sleep(max(0, 0.25 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read(20_000_001)
                    if len(body) > 20_000_000:
                        raise SourceUnavailable("response too large; use a bulk/offline workflow")
                break
            except urllib.error.HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise SourceUnavailable("HTTP_" + str(exc.code)) from exc
            except (OSError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise SourceUnavailable(type(exc).__name__) from exc
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        sha = digest(body)
        path = root / (sha + ".raw")
        if path.exists() and path.read_bytes() != body:
            raise DataError("raw object collision")
        path.write_bytes(body)
        metadata = {"url": url, "sha256": sha, "size": len(body),
                    "retrieved_at": iso(datetime.now(timezone.utc)), "raw_file": path.name}
        # Each observation remains separate, even if the provider repeats identical bytes.
        (root / (digest(canonical(metadata)) + ".json")).write_bytes(canonical(metadata))
        return body, metadata


def sec_candidates(document, cik):
    """Supports main submissions and each historical continuation JSON.

    Emits a ledger for every 8-K, including rejects and unknown Item fields.
    Acceptance timestamps are never represented as verified release timestamps.
    """
    if not str(cik).isdigit():
        raise DataError("invalid CIK")
    filings = document.get("filings", {})
    rows = filings.get("recent", document)
    if "accessionNumber" not in rows:
        raise DataError("SEC submissions schema missing accessionNumber")
    required = ["accessionNumber", "form", "filingDate", "primaryDocument"]
    size = len(rows["accessionNumber"])
    if any(not isinstance(rows.get(k), list) or len(rows[k]) != size for k in required):
        raise DataError("SEC column length mismatch")
    for key in ("items", "acceptanceDateTime"):
        if key in rows and (not isinstance(rows[key], list) or len(rows[key]) != size):
            raise DataError("SEC optional column length mismatch")
    result, seen = [], set()
    for i in range(size):
        form = rows["form"][i]
        if form not in {"8-K", "8-K/A"}:
            continue
        accession = rows["accessionNumber"][i]
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise DataError("invalid accession")
        if accession in seen:
            raise DataError("duplicate SEC accession")
        seen.add(accession)
        items = rows.get("items", [None] * size)[i]
        item_set = set(re.findall(r"\b\d+\.\d{2}\b", items or ""))
        state = ("AMENDMENT_REVIEW" if form.endswith("/A") else
                 "ITEMS_UNAVAILABLE" if items is None else
                 "EARNINGS_CANDIDATE" if "2.02" in item_set else "NOT_ITEM_2_02")
        primary = rows["primaryDocument"][i]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", primary):
            raise DataError("invalid primary document path")
        result.append({"candidate_id": accession, "cik": str(cik).zfill(10), "form": form,
                       "filing_date": rows["filingDate"][i], "items": sorted(item_set),
                       "acceptance_at": rows.get("acceptanceDateTime", [None] * size)[i],
                       "state": state, "first_public_verified": False,
                       "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary}"})
    return {"candidates": result, "continuation_files": filings.get("files", []),
            "historical_coverage_complete": not bool(filings.get("files"))}


def nasdaq_directory(text, available_at):
    timestamp(available_at)
    lines = text.splitlines()
    footer = [line for line in lines if line.startswith("File Creation Time:")]
    if len(footer) != 1:
        raise DataError("directory timestamp footer missing/duplicate")
    rows = list(csv.DictReader(io.StringIO("\n".join(
        line for line in lines if not line.startswith("File Creation Time:"))), delimiter="|"))
    output, seen = [], set()
    for row in rows:
        symbol = row.get("Symbol", row.get("ACT Symbol"))
        if not symbol or symbol in seen:
            raise DataError("missing/duplicate directory symbol")
        seen.add(symbol)
        exchange = "NASDAQ" if "Market Category" in row else {
            "N": "NYSE", "A": "NYSE American"}.get(row.get("Exchange"), "OTHER")
        name = row.get("Security Name", "")
        state = "REQUIRES_IDENTITY_REVIEW"
        if row.get("Test Issue") == "Y":
            state = "EXCLUDED_TEST"
        elif row.get("ETF") == "Y":
            state = "EXCLUDED_ETF"
        elif exchange == "OTHER":
            state = "EXCLUDED_EXCHANGE"
        elif re.search(r"\b(warrants?|preferred|units?|depositary|depositary shares|rights)\b", name, re.I):
            state = "EXCLUDED_OR_REQUIRES_TYPE_REVIEW"
        output.append({"ticker": symbol, "name": name, "exchange": exchange,
                       "state": state, "available_at": available_at,
                       "file_creation_time_raw": footer[0].split("|")[0],
                       "historical_membership_established": False})
    return output


def release_evidence(source, published_at, evidence):
    """Explicit evidence review, not an arbitrary inferred news-time parser."""
    timestamp(published_at)
    if not evidence or evidence not in source["text"]:
        raise DataError("release timestamp evidence not present in source")
    # The reviewer must verify timezone, first publication and issuer identity.
    return {"published_at": published_at, "evidence": evidence,
            "source_id": source["source_id"], "review_required": True}
