"""Record types and helpers shared by the format readers. Imports nothing from classifile outside the reader.

A unit is a source location: a PDF page, a PPTX slide, or a DOCX/ODT body block (paragraph, heading,
list or table). Failure reasons are fixed strings and never contain document text.
"""
import hashlib
import math
import os
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

RECORD_VERSION = 6         # format of DocumentRecord/UnitRecord; bump when fields change

# Suspected-unread / selective-OCR rule (decision record B3), adopted from E8 on development data: any
# non-repeated picture covering at least 5% of its page or slide, regardless of the unit's native text.
# The first rule (< 300 native characters and >= 30% picture area) missed most text-bearing pictures.
SUSPECT_RULE = "nonrepeated_picture_at_least_5pct"
SUSPECT_MIN_PICTURE_AREA = 0.05

REPEATED_SHARE = 0.5      # an image or line on at least half the pages/slides is "repeated" / a template line
SHORT_LINE_MAX = 80       # max characters for a "recurring short line"
OPENING_LINES_MAX = 40    # flow documents: opening lines kept as "first page lines"
DEFAULT_MAX_BYTES = 512 * 1024 * 1024    # safety cap -> "pending: too large", never a rejection
MAX_PART_BYTES = 256 * 1024 * 1024       # decompressed size cap per zip part (zip-bomb guard)


@dataclass
class UnitRecord:
    index: int                    # 1-based position: page, slide or block number
    kind: str                     # page | slide | hidden slide | paragraph | heading | title | list | table | notes
    text: str
    native_chars: int
    text_area: float | None       # share of the page/slide; None where there is no page geometry
    image_area: float | None
    nonrepeated_image_area: float | None
    suspected_unread: bool
    suspect_rule: str | None
    level: int | None = None      # heading level
    title: str | None = None      # slide title placeholder text
    notes: str | None = None      # speaker notes
    ocr_status: str | None = None # see reader/ocr.py; None when the unit was not flagged for OCR
    ocr_text: str | None = None   # kept apart from native text
    ocr_discarded_chars: int | None = None  # OCR characters dropped as junk (photos, decorations)
    ocr_raw_text: str | None = None  # OCR text before the junk filter, as Tesseract returned it
    # Layout for readable formatting later (never used for categorizing):
    # {"width", "height", "blocks": [{"bbox", "lines": [{"text", "bbox", "size"}]}]}; positions and sizes are in
    # points (None where the format stores none: DOCX/ODT have no positions until a word processor lays them out).
    layout: dict | None = None
    # Per OCR'd picture: {"picture", "region", "blocks"}; block and line boxes are fractions of the picture, size is
    # the line height as a fraction of the picture height, and each line says whether the junk filter kept it.
    ocr_layout: list = field(default_factory=list)
    pictures: list = field(default_factory=list)  # package paths of the unit's pictures (PPTX/DOCX/ODT)


@dataclass
class DocumentRecord:
    format: str                   # pdf | pptx | docx | odt
    unit: str                     # page | slide | block
    unit_count: int
    metadata: dict
    template_lines: list          # [{"line": digits-as-#, "example": first original, "pages": [...]}]
    recurring_lines: list         # [{"line": str, "pages": [...]}]
    running_lines: list           # [{"line": str, "part": header | footer | master | layout}]
    first_page_lines: list        # first page or slide; opening lines for flow documents
    units: list = field(default_factory=list)
    ocr: dict = field(default_factory=dict)  # OCR engine settings; empty when no unit needed OCR
    reader_version: str = ""
    record_version: int = RECORD_VERSION


@dataclass
class ReadResult:
    status: str            # "ok" | "failed" | "pending"
    reason: str | None
    sha256: str | None
    size: int | None
    record: DocumentRecord | None = None


class ReadFailure(Exception):
    """Raised by parsers with a fixed, text-free reason."""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_snapshot(path, parse, label, max_bytes=DEFAULT_MAX_BYTES):
    """Read the bytes once, parse them, and discard the result if the source changed meanwhile."""
    try:
        size = os.stat(path).st_size
        if size > max_bytes:
            return ReadResult("pending", "too large", sha256_file(path), size)
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return ReadResult("failed", "source could not be opened", None, None)
    sha = hashlib.sha256(data).hexdigest()
    if not data:
        return ReadResult("failed", "empty file", sha, 0)

    try:
        status, reason, record = "ok", None, parse(data)
    except ReadFailure as e:
        status, reason, record = "failed", str(e), None
    except Exception as e:
        status, reason, record = "failed", f"error while reading {label} ({type(e).__name__})", None

    try:
        changed = sha256_file(path) != sha
    except OSError:
        changed = True
    if changed:
        return ReadResult("failed", "source changed during reading", sha, len(data))
    return ReadResult(status, reason, sha, len(data), record)


def _box(b, fx=1.0, fy=1.0, nd=1):
    return [round(b[0] * fx, nd), round(b[1] * fy, nd), round(b[2] * fx, nd), round(b[3] * fy, nd)]


def page_layout(d, normalize=False):
    """PyMuPDF text dict -> layout blocks/lines with boxes and the largest font size per line.
    normalize=True gives boxes as fractions of the page and size as a fraction of its height (OCR pictures)."""
    w, h = d["width"] or 1.0, d["height"] or 1.0
    fx, fy, nd = (1 / w, 1 / h, 4) if normalize else (1.0, 1.0, 1)
    blocks = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        lines_ = [{"text": "".join(s["text"] for s in l["spans"]), "bbox": _box(l["bbox"], fx, fy, nd),
                   "size": round((l["bbox"][3] - l["bbox"][1]) / h, 4) if normalize
                   else round(max((s["size"] for s in l["spans"]), default=0), 1)}
                  for l in b["lines"]]
        blocks.append({"bbox": _box(b["bbox"], fx, fy, nd), "lines": lines_})
    return {"width": round(w, 1), "height": round(h, 1), "blocks": blocks}


def flow_layout(lines_with_sizes):
    """DOCX/ODT: one block of lines; no positions exist in the file. lines_with_sizes: [(text, size or None)]."""
    return {"width": None, "height": None,
            "blocks": [{"bbox": None, "lines": [{"text": t, "bbox": None, "size": s} for t, s in lines_with_sizes]}]}


def lines(text):
    return [" ".join(l.split()) for l in text.splitlines() if l.strip()]


def chars(text):
    return len("".join(text.split()))


def ocr_worthy(share):
    """share: one non-repeated picture's share of its page or slide (None where unknown)."""
    return share is not None and share >= SUSPECT_MIN_PICTURE_AREA


def suspect(picture_shares):
    hit = any(ocr_worthy(s) for s in picture_shares)
    return hit, SUSPECT_RULE if hit else None


def line_stats(texts):
    """Template lines (on >= half the pages, digits as #) and recurring short lines (on >= 2 pages)."""
    line_pages, template_pages, template_example = defaultdict(list), defaultdict(list), {}
    for i, text in enumerate(texts):
        for line in dict.fromkeys(lines(text)):  # unique per page, first-seen order
            line_pages[line].append(i + 1)
            key = re.sub(r"\d", "#", line)
            if not template_pages[key] or template_pages[key][-1] != i + 1:
                template_pages[key].append(i + 1)
            template_example.setdefault(key, line)
    # A template line needs at least two pages, so a one-page document has none.
    min_template = max(2, math.ceil(len(texts) * REPEATED_SHARE))
    template = [{"line": k, "example": template_example[k], "pages": p}
                for k, p in template_pages.items() if len(p) >= min_template]
    recurring = [{"line": l, "pages": p} for l, p in line_pages.items() if len(p) >= 2 and len(l) <= SHORT_LINE_MAX]
    return template, recurring


def running(parts):
    """[(part, text)] -> unique running lines in first-seen order."""
    seen, out = set(), []
    for part, text in parts:
        for line in lines(text):
            if (line, part) not in seen:
                seen.add((line, part))
                out.append({"line": line, "part": part})
    return out


def drop_empty(blocks):
    """Flow documents: drop blocks with no text or image, carrying their page breaks to the next kept block."""
    out, carry = [], False
    for b in blocks:
        if b["text"].strip() or b["images"]:
            b["page_break"] |= carry
            carry = False
            out.append(b)
        else:
            carry |= b["page_break"]
    return out


def opening_lines(blocks):
    """Flow documents: lines of the blocks before the first page break (explicit or as last rendered), capped."""
    out = []
    for i, b in enumerate(blocks):
        if (b["page_break"] and i > 0) or b["kind"] in ("footnotes", "endnotes"):
            break
        out += lines(b["text"])
    return out[:OPENING_LINES_MAX]


# -- zip containers (OOXML, ODF) ------------------------------------------------------------------
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def open_zip(data, label):
    import io
    if data.startswith(OLE_MAGIC):
        raise ReadFailure("encrypted or legacy-format Office file")
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ReadFailure(f"corrupt or unreadable {label}") from None


def part(zf, name, required=True):
    """Bytes of one zip part, or None when absent and optional."""
    try:
        info = zf.getinfo(name)
    except KeyError:
        if required:
            raise ReadFailure("required part missing") from None
        return None
    if info.file_size > MAX_PART_BYTES:
        raise ReadFailure("part too large to read safely")
    with zf.open(info) as f:
        data = f.read(MAX_PART_BYTES + 1)
    if len(data) > MAX_PART_BYTES:
        raise ReadFailure("part too large to read safely")
    return data


def package_part(path, name):
    """One part of a zip-based document, read from the file without changing it."""
    with open(path, "rb") as f:
        return part(open_zip(f.read(), "document"), name)


def xml(zf, name, required=True):
    data = part(zf, name, required)
    if data is None:
        return None
    # OOXML/ODF parts never declare a DOCTYPE, so refusing one rules out entity tricks without defusedxml.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ReadFailure("XML part declares a DOCTYPE")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise ReadFailure("malformed XML part") from None


DC = "{http://purl.org/dc/elements/1.1/}"
