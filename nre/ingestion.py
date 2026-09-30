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
        self.min_interval = 3.1  # unauthenticated Reader is documented at 20 RPM

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
            time.sleep(max(0, self.min_interval - (time.monotonic() - self.last)))
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
        allowed = {"data.sec.gov", "www.sec.gov", "www.nasdaqtrader.com",
                   "clinicaltrials.gov", "api.fda.gov"}
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
        accession_dir = accession.replace("-", "")
        index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_dir}/{accession}-index.html"
        parts = primary.split("/") if isinstance(primary, str) else []
        safe_primary = bool(parts) and not str(primary).startswith("/") and all(
            part and part not in {".", ".."} and re.fullmatch(r"[A-Za-z0-9_.-]+", part)
            for part in parts
        )
        primary_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_dir}/{primary}"
            if safe_primary else None
        )
        result.append({"candidate_id": accession, "cik": str(cik).zfill(10), "form": form,
                       "filing_date": rows["filingDate"][i], "items": sorted(item_set),
                       "acceptance_at": rows.get("acceptanceDateTime", [None] * size)[i],
                       "state": state, "first_public_verified": False,
                       "primary_document_raw": primary,
                       "primary_document_state": "PARSED_SAFE" if safe_primary else "REVIEW_REQUIRED",
                       "primary_url": primary_url,
                       "filing_index_url": index_url,
                       "url": primary_url or index_url})
    return {"candidates": result, "continuation_files": filings.get("files", []),
            "historical_coverage_complete": not bool(filings.get("files"))}


def xbrl_company_concept(client, cik, taxonomy, tag, unit, output):
    """Fetch one XBRL concept's full reported history for a company (data.sec.gov/api/xbrl/
    companyconcept/), for Milestone 3 Phase B's earnings-surprise computation
    (nre.earnings_surprise). Returns the raw fact list for `unit` exactly as SEC's own API reports
    it -- nothing computed or filtered here, that is nre.earnings_surprise's own job. A concept a
    company has never reported (e.g. the wrong revenue tag) surfaces as SourceUnavailable
    ("HTTP_404") through `client.fetch()` itself, the same as any other missing public source."""
    if not str(cik).isdigit():
        raise DataError("invalid CIK")
    if not re.fullmatch(r"[a-z-]+", taxonomy) or not re.fullmatch(r"[A-Za-z0-9]+", tag):
        raise DataError("invalid taxonomy or tag")
    url = "https://data.sec.gov/api/xbrl/companyconcept/CIK%010d/%s/%s.json" % (int(cik), taxonomy, tag)
    body, meta = client.fetch(url, output)
    document = json.loads(body)
    if document.get("cik") != int(cik):
        raise DataError("XBRL response CIK does not match the request")
    units = document.get("units")
    if not isinstance(units, dict) or unit not in units:
        raise DataError("XBRL response has no %s facts for this concept" % unit)
    facts = units[unit]
    if not isinstance(facts, list) or not all(isinstance(f, dict) for f in facts):
        raise DataError("XBRL unit facts malformed")
    return facts, meta


def clinical_trials_study(client, nct_id, output):
    """Fetch one real study record by its own NCT id (clinicaltrials.gov/api/v2/studies/{nctId} --
    verified live and free 2026-09-30), for Milestone 3 Phase C's biotech catalyst classification
    (nre.biotech_trials). Returns the raw protocolSection document exactly as ClinicalTrials.gov's
    own API reports it -- nothing computed or classified here. An id with no matching study
    surfaces as SourceUnavailable ("HTTP_404") through `client.fetch()` itself, the same as any
    other missing public source."""
    if not re.fullmatch(r"NCT\d{8}", nct_id):
        raise DataError("invalid NCT id")
    url = "https://clinicaltrials.gov/api/v2/studies/%s" % nct_id
    body, meta = client.fetch(url, output)
    document = json.loads(body)
    protocol = document.get("protocolSection")
    if not isinstance(protocol, dict) or protocol.get("identificationModule", {}).get("nctId") != nct_id:
        raise DataError("ClinicalTrials.gov response NCT id does not match the request")
    return protocol, meta


def drugsfda_application(client, application_number, output):
    """Fetch one real Drugs@FDA application record by its own application number
    (api.fda.gov/drug/drugsfda.json -- verified live and free 2026-09-30), for Milestone 3 Phase C's
    biotech catalyst classification (nre.fda_approvals). Returns the raw application document
    exactly as openFDA's own API reports it -- nothing computed or classified here. An application
    number with no matching record surfaces as DataError: verified directly against the real API
    2026-09-30 (a well-formed but nonexistent application_number, both by itself and re-checked
    through drugsfda_sponsor_search()'s own zero-result path below) that openFDA returns a real
    HTTP 404 with an {"error": {"code": "NOT_FOUND", ...}} body -- not a 200, correcting an earlier,
    never-actually-exercised assumption in this same function (every real dispatch before this had
    used an application_number that exists, so the not-found path had never been hit for real)."""
    if not re.fullmatch(r"(NDA|ANDA|BLA)\d+", application_number):
        raise DataError("invalid application_number (must start with NDA, ANDA, or BLA)")
    url = "https://api.fda.gov/drug/drugsfda.json?search=application_number:%s&limit=1" % urllib.parse.quote(
        '"' + application_number + '"')
    try:
        body, meta = client.fetch(url, output)
    except SourceUnavailable as exc:
        if str(exc) == "HTTP_404":
            raise DataError("openFDA: no application found for " + application_number) from exc
        raise
    document = json.loads(body)
    if "error" in document:
        raise DataError("openFDA: " + document["error"].get("message", "unknown error"))
    results = document.get("results")
    if not isinstance(results, list) or not results or results[0].get("application_number") != application_number:
        raise DataError("openFDA response application_number does not match the request")
    return results[0], meta


def clinical_trials_sponsor_search(client, sponsor, output, page_size=20):
    """Search real studies by lead sponsor (clinicaltrials.gov/api/v2/studies?query.spons= --
    verified live 2026-09-30), for discovering a company's own trials without already knowing an
    NCT id -- Milestone 3's connection of Phase C to this project's own issuers. query.spons matches
    broadly (collaborators too, sometimes by a stemmed/partial token: a real check against
    "Assembly Biosciences" also matched unrelated sponsors on the shared token "Bioscience(s)") --
    callers must check each result's own leadSponsor.name before treating it as that company's
    trial, the same discipline as an EDGAR self-declaration search (search broadly, then verify the
    specific record actually says what you are looking for). A zero-result search returns a normal
    HTTP 200 with an empty studies list (verified directly) -- unlike openFDA's exact/prefix lookup
    below, no not-found translation is needed here. Returns each matching study's protocolSection,
    identical in shape to what clinical_trials_study() returns for one id, so
    nre.biotech_trials.classify_study() applies unchanged to each item."""
    if not sponsor or not isinstance(sponsor, str):
        raise DataError("sponsor must be a non-empty string")
    url = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode(
        {"query.spons": sponsor, "pageSize": page_size})
    body, meta = client.fetch(url, output)
    document = json.loads(body)
    studies = document.get("studies")
    if not isinstance(studies, list):
        raise DataError("ClinicalTrials.gov search response missing studies list")
    protocols = []
    for study in studies:
        protocol = study.get("protocolSection")
        if not isinstance(protocol, dict):
            raise DataError("ClinicalTrials.gov search result missing protocolSection")
        protocols.append(protocol)
    return protocols, meta


def drugsfda_sponsor_search(client, sponsor_prefix, output, limit=20):
    """Search real Drugs@FDA applications by a sponsor_name prefix (api.fda.gov/drug/drugsfda.json
    -- verified live 2026-09-30), for discovering a company's own applications without already
    knowing an application_number. openFDA's own sponsor_name field holds a short registered name,
    not necessarily a company's full public name (real, verified examples: Neurocrine Biosciences'
    own applications are filed under just "NEUROCRINE"; Collegium Pharmaceutical's under "COLLEGIUM
    PHARM INC") -- an exact quoted phrase of the full public name will not match, and an unquoted
    multi-word query matches ANY word (OR, not AND: a real check on "Assembly Biosciences" matched
    unrelated sponsors sharing just the "Bioscience(s)" token). A prefix wildcard
    (sponsor_name:TERM*) is the reliable match verified here, at the cost of the caller supplying a
    sensible, distinctive prefix. Zero matches is a normal, valid outcome (e.g. a clinical-stage
    company with nothing FDA-approved yet -- verified real, e.g. for Achieve Life Sciences, Tectonic
    Therapeutic and Assembly Biosciences) and is returned as an empty list, never raised as an
    error: openFDA's own real 404-with-error-body for a zero-result search is caught here and
    translated, the same real behavior drugsfda_application() above now also handles. Returns each
    matching application dict, identical in shape to what drugsfda_application() returns for one
    application_number, so nre.fda_approvals.classify_application() applies unchanged to each
    item."""
    if not sponsor_prefix or not isinstance(sponsor_prefix, str):
        raise DataError("sponsor_prefix must be a non-empty string")
    url = "https://api.fda.gov/drug/drugsfda.json?" + urllib.parse.urlencode(
        {"search": "sponsor_name:%s*" % sponsor_prefix, "limit": limit})
    try:
        body, meta = client.fetch(url, output)
    except SourceUnavailable as exc:
        if str(exc) == "HTTP_404":
            return [], {"url": url, "result_count": 0, "empty_result_reason": "HTTP_404_NOT_FOUND"}
        raise
    document = json.loads(body)
    if "error" in document:
        if document["error"].get("code") == "NOT_FOUND":
            return [], meta
        raise DataError("openFDA: " + document["error"].get("message", "unknown error"))
    results = document.get("results")
    if not isinstance(results, list):
        raise DataError("openFDA search response missing results list")
    return results, meta


def device_sponsor_search(client, pathway, applicant_prefix, output, limit=20):
    """Search real openFDA medical-device records by an applicant prefix, for either pathway --
    "510k" (api.fda.gov/device/510k.json) or "pma" (.../device/pma.json), verified live 2026-09-30.
    Both endpoints share the same real applicant field and the same prefix-wildcard/404-as-empty
    behavior already verified for drugsfda_sponsor_search() above (a genuinely zero-result search
    returns a real HTTP 404 with an {"error": {...}} body, caught and translated to an empty list
    here rather than raised, since "this company has no records under this pathway" is a normal,
    valid outcome -- e.g. LNSR genuinely has zero real PMA records, only 510(k) ones). Returns each
    matching record dict unchanged, for nre.device_clearances.classify_510k()/classify_pma() to
    classify per pathway."""
    if pathway not in ("510k", "pma"):
        raise DataError('pathway must be "510k" or "pma"')
    if not applicant_prefix or not isinstance(applicant_prefix, str):
        raise DataError("applicant_prefix must be a non-empty string")
    url = "https://api.fda.gov/device/%s.json?" % pathway + urllib.parse.urlencode(
        {"search": "applicant:%s*" % applicant_prefix, "limit": limit})
    try:
        body, meta = client.fetch(url, output)
    except SourceUnavailable as exc:
        if str(exc) == "HTTP_404":
            return [], {"url": url, "result_count": 0, "empty_result_reason": "HTTP_404_NOT_FOUND"}
        raise
    document = json.loads(body)
    if "error" in document:
        if document["error"].get("code") == "NOT_FOUND":
            return [], meta
        raise DataError("openFDA: " + document["error"].get("message", "unknown error"))
    results = document.get("results")
    if not isinstance(results, list):
        raise DataError("openFDA search response missing results list")
    return results, meta


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
