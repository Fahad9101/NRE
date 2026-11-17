"""Index frozen M6 guidance research filings and extract original current-report exhibits."""
import gzip
import re
from collections import Counter
from html.parser import HTMLParser
from io import BytesIO

from .core import DataError, digest

SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
PUBLIC_MIRROR = "https://edgar-mirror.sec-api.io"
FILING_FIELDS = ("accessionNumber", "acceptanceDateTime", "filingDate", "form", "items", "primaryDocument")


def current_reports(recent, cik, first, last, *, guidance_updates=False):
    """Enumerate candidate submissions. An Item 2.02 alone does not establish an earnings event."""
    if len({len(recent[key]) for key in FILING_FIELDS}) != 1:
        raise DataError("Mismatched SEC submission columns")
    required = {"2.02", "7.01", "8.01"} if guidance_updates else {"2.02"}
    rows = []
    for accession, accepted, filed, form, text, primary in zip(*(recent[key] for key in FILING_FIELDS)):
        items = set(re.findall(r"\b\d\.\d{2}\b", text or ""))
        if form != "8-K" or not first <= filed <= last or not items & required:
            continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise DataError("Invalid current-report accession")
        base = f"{int(cik)}/{accession.replace('-', '')}"
        rows.append({"cik": cik, "accession": accession, "accepted_at": accepted,
                     "filing_date": filed, "items": sorted(items), "primary_document": primary,
                     "source_url": f"{SEC_ARCHIVE}/{base}/{accession}.txt",
                     "mirror_url": f"{PUBLIC_MIRROR}/{base}/{accession}.txt"})
    return sorted(rows, key=lambda row: (row["accepted_at"], row["accession"]))


class ExhibitText(HTMLParser):
    """Retain paragraph and table row boundaries in SEC exhibits."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "ix:hidden"}:
            self.hidden += 1
        elif tag in {"br", "li"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "ix:hidden"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"tr", "p", "li", "div", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def lines(self):
        return [line for raw in "".join(self.parts).splitlines()
                if (line := " ".join(raw.split()).strip(" |"))]


def submission_text(payload):
    if payload.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=BytesIO(payload)) as stream:
            payload = stream.read(45_000_001)
    if len(payload) > 45_000_000:
        raise DataError("Submission size limit")
    return payload.decode("utf-8", errors="replace")


def exhibits(payload, filing):
    raw = submission_text(payload)
    header, marker, _ = raw.partition("</SEC-HEADER>")
    if (not marker or not re.search(rf"(?im)^ACCESSION NUMBER:\s*{re.escape(filing['accession'])}\s*$", header)
            or filing["cik"] not in re.findall(r"(?im)CENTRAL INDEX KEY:\s*(\d{10})", header)):
        raise DataError("Submission identity does not match SEC metadata")
    blocks = re.findall(r"(?is)<DOCUMENT>\s*(.*?)</DOCUMENT>", raw)
    count = re.search(r"(?im)^PUBLIC DOCUMENT COUNT:\s*(\d+)", header)
    if count is None or len(blocks) != raw.count("<DOCUMENT>") or not raw.rstrip().endswith("</SEC-DOCUMENT>"):
        raise DataError("Incomplete SEC submission")
    results = []
    for block in blocks:
        head, text_marker, rest = block.partition("<TEXT>")
        kind = re.search(r"(?im)^<TYPE>([^\r\n<]+)", head)
        if kind is None or not re.fullmatch(r"EX-99(?:\.\d+)?", kind.group(1).strip()):
            continue
        name = re.search(r"(?im)^<FILENAME>([^\r\n<]+)", head)
        if name is None or not text_marker or "</TEXT>" not in rest:
            raise DataError("Incomplete exhibit")
        document = rest.rsplit("</TEXT>", 1)[0]
        filename = name.group(1).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
            raise DataError("Invalid exhibit filename")
        parser = ExhibitText()
        if filename.lower().endswith((".htm", ".html", ".txt")):
            parser.feed(document)
            parser.close()
        results.append({"form_type": kind.group(1).strip(), "filename": filename,
                        "source_url": filing["source_url"].rsplit("/", 1)[0] + "/" + filename,
                        "lines": parser.lines()})
    return results, {"listed_document_count": int(count.group(1)), "available_document_count": len(blocks)}


ANCHOR = re.compile(
    r"(?i)\b(guidance|outlook|business outlook|financial outlook|forecast|expects?|anticipates?|projects?|reaffirms?)\b"
)
REVENUE = re.compile(r"(?i)\b(revenues?|net sales)\b")
HORIZON = re.compile(r"(?i)\b(?:full.{0,3}year|fiscal year|entire year|annual|FY\s*20\d{2}|FY\s*\d{2}|20\d{2})\b")


def outlook_review(lines):
    """Return text for source review. Missing hits do not exclude an issuer."""
    matches = []
    for index, line in enumerate(lines):
        if not REVENUE.search(line):
            continue
        before = " ".join(lines[max(0, index - 6):index])
        after = " ".join(lines[index:index + 3])
        if not ANCHOR.search(before + " " + after) or not (re.search(r"\d", line) or "$" in after):
            continue
        score = (2 * bool(HORIZON.search(before + " " + after))
                 + bool("$" in after) + bool(ANCHOR.search(line)))
        matches.append((score, index))
    return [{"line": index, "excerpt": lines[max(0, index - 2):index + 3]}
            for _, index in sorted(matches, key=lambda m: (-m[0], m[1]))[:14]]


def archive_review(payload, filing):
    documents, counts = exhibits(payload, filing)
    return {**filing, **counts, "archive_sha256": digest(payload),
            "exhibit_formats": dict(Counter(x["filename"].rsplit(".", 1)[-1] for x in documents)),
            "exhibits": [{**doc, "review_excerpt": outlook_review(doc["lines"])} for doc in documents]}


class ListingTags(HTMLParser):
    """Group dated EDGAR cover identifiers by the SEC tag context."""

    NAMES = {"tradingsymbol": "symbol", "securityexchangename": "exchange",
             "security12btitle": "security_class"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts = {}
        self.active = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag != "ix:nonnumeric":
            return
        fields = dict(attrs)
        local_name = fields.get("name", "").lower().split(":")[-1]
        name = self.NAMES.get(local_name)
        if name and fields.get("contextref"):
            self.active = (fields["contextref"], name)
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "ix:nonnumeric" and self.active:
            context, name = self.active
            value = " ".join("".join(self.parts).split())
            self.contexts.setdefault(context, {}).setdefault(name, set()).add(value)
            self.active = None

    def listings(self):
        return [{key: next(iter(values)) for key, values in row.items()}
                for row in self.contexts.values()
                if set(row) == set(self.NAMES.values()) and all(len(values) == 1 for values in row.values())]


def cover_listings(payload):
    parser = ListingTags()
    parser.feed(submission_text(payload))
    parser.close()
    return parser.listings()
