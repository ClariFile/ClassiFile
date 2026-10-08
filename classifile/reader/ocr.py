"""Selective OCR (decision record B3, E8) through PyMuPDF's built-in Tesseract. Imports nothing from classifile.

Only units flagged suspected_unread are OCR'd, and only their non-repeated pictures that meet the rule
(common.SUSPECT_MIN_PICTURE_AREA of the page or slide). OCR text is kept apart from native text, after
the junk filter below; the number of discarded characters is recorded. Per-unit status:
  done               OCR found usable text
  no_text            OCR ran and found none, or only junk (photos, decorations); see ocr_discarded_chars
  no_readable_image  no image in the unit could be decoded (e.g. EMF/WMF)
  failed             the OCR engine raised on every readable image
  unavailable        Tesseract language data not found
  deferred           the document's OCR time budget ran out first (never a rejection: the gap stays disclosed)
  disabled           OCR switched off with CLASSIFILE_OCR=off (tests that do not exercise OCR)
All constants are provisional; E8 revisits them.
"""
import math
import os
import re
import time
from collections import Counter
from pathlib import Path

import pymupdf

from .common import ocr_worthy, page_layout

OCR_LANGUAGE = "eng"
OCR_DPI = 300
MAX_OCR_PIXELS = 25_000_000     # larger regions are rendered at a lower resolution
OCR_BUDGET_SECONDS = 240        # per document, inside the worker's 300 s per-file timeout
WINDOWS_TESSDATA = Path(r"C:\Program Files\Tesseract-OCR\tessdata")
SWITCH_ENV = "CLASSIFILE_OCR"


def tessdata():
    """Tesseract language-data folder: TESSDATA_PREFIX, else the default Windows install, else None."""
    for folder in (os.environ.get("TESSDATA_PREFIX"), WINDOWS_TESSDATA if os.name == "nt" else None):
        if folder and (Path(folder) / f"{OCR_LANGUAGE}.traineddata").is_file():
            return str(folder)
    return None


def dpi_for(rect):
    """OCR_DPI, lowered so the rendered region stays under MAX_OCR_PIXELS."""
    area_in2 = max(rect.width * rect.height, 1.0) / (72 * 72)
    return max(72, min(OCR_DPI, int(math.sqrt(MAX_OCR_PIXELS / area_in2))))


def render_image(data):
    """Embedded image bytes -> pixmap composited on white. Raises for formats MuPDF cannot open (EMF, WMF)."""
    with pymupdf.open(stream=data) as d:
        page = d[0]
        return page.get_pixmap(dpi=dpi_for(page.rect))


def ocr_pixmap(pix, folder, with_layout=False):
    """The text OCR reads; with_layout also returns its blocks and lines, positioned as fractions of the picture."""
    data = pix.pdfocr_tobytes(language=OCR_LANGUAGE, tessdata=folder)
    with pymupdf.open("pdf", data) as d:
        text = d[0].get_text()
        if not with_layout:
            return text
        return text, page_layout(d[0].get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES),
                                 normalize=True)["blocks"]


# Junk filter. Photos and decorations make OCR invent fragments ("oe", vowel runs, stray capitals). A line is
# kept when most of its tokens look like words; a picture whose OCR output is mostly junk is dropped whole, and
# a photo-like picture (continuous tone) must read as mostly words. Provisional; the OCR-quality pass measures it.
SHORT_WORDS = frozenset("""a i an as at be by do go he if in is it me my no of on or so to up us we
am ad ah ok ox id tv pc ip""".split())
OCR_LINE_WORD_SHARE = 0.6        # at least this share of a line's tokens must look like words
OCR_MIN_WORD_SHARE = 0.15        # below this share of word-like tokens in a picture, all of its OCR text is junk
OCR_PHOTO_MIN_WORD_SHARE = 0.5   # the same, for photo-like pictures
PHOTO_MAX_FLAT_SHARE = 0.5       # pictures whose 16 commonest colours cover less than this are photo-like
_VOWELS = set("aeiouyAEIOUY")
_EDGE_PUNCT = ".,;:!?()[]{}\"'“”‘’«»*•·|"


def _plausible_word(t):
    """An alphabetic token that could be a word or an acronym."""
    if len(t) <= 2:
        return t.casefold() in SHORT_WORDS
    if re.fullmatch(r"[A-Z]{2,4}s?", t):                                 # acronyms: TCP, DNS, APIs
        return True
    if (re.fullmatch(r"[A-Z]{2,}[a-z]+", t) or re.search(r"[a-z][A-Z]{2}", t)
            or (len(t) <= 6 and re.search(r"[a-z][A-Z][a-z]", t))
            or re.search(r"[aeiouy]{4}", t.casefold()) or re.search(r"(.)\1\1", t.casefold())):
        return False                                                       # "LSSo", "ooSSoo", "oeLe", "eeeeo", "ooo"
    vowels = sum(c in _VOWELS for c in t)
    return 0 < vowels < len(t) and not (len(t) >= 5 and vowels / len(t) > 0.7)


def _wordlike(token):
    t = token.strip(_EDGE_PUNCT)
    if re.fullmatch(r"\d+(?:[.,:/-]\d+)*%?", t):                         # numbers, dates, addresses
        return True
    if re.fullmatch(r"[A-Za-z]{1,4}\d+|\d+[A-Za-z]{1,3}", t):            # IPv4, MP3, 10GB, 2nd
        return True
    if t.isalpha():
        return _plausible_word(t)
    parts = re.split(r"[-'’]", t)                                          # well-known, it's
    return len(parts) > 1 and all(p.isalpha() and (len(p) <= 2 or _plausible_word(p)) for p in parts)


def usable_ocr_text(text, photo_like=False):
    """OCR text without the lines that look like junk; "" when the whole picture is junk."""
    if not text:
        return ""
    tokens = text.split()
    floor = OCR_PHOTO_MIN_WORD_SHARE if photo_like else OCR_MIN_WORD_SHARE
    if not tokens or sum(map(_wordlike, tokens)) / len(tokens) < floor:
        return ""
    kept = []
    for line in text.splitlines():
        toks = line.split()
        good = sum(map(_wordlike, toks))
        if toks and good / len(toks) >= OCR_LINE_WORD_SHARE and (good >= 2 or len(toks[0].strip(_EDGE_PUNCT)) >= 4):
            kept.append(" ".join(toks))
    return "\n".join(kept)




def flat_share(pix, top=16):
    """Share of (sampled) pixels in the picture's `top` commonest colours, at 4 bits per channel. Text, diagrams
    and screenshots are mostly flat colour (about 0.6 to 1.0 on the development pictures); photos are not."""
    if pix.n - pix.alpha < 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    s, n = pix.samples, pix.n
    step = max(1, (pix.width * pix.height) // 40000)
    counts = Counter((s[i] >> 4, s[i + 1] >> 4, s[i + 2] >> 4) for i in range(0, len(s) - n + 1, n * step))
    return sum(v for _, v in counts.most_common(top)) / max(1, sum(counts.values()))


def flow_sources(units, blocks, page_area, load):
    """DOCX/ODT: pixmap makers for the images of suspected blocks. Block images are (area, ref); load(ref) -> bytes."""
    out = {}
    for u, b in zip(units, blocks):
        if u.suspected_unread:
            out[u.index] = [lambda ref=ref: render_image(load(ref)) for area, ref in b["images"]
                            if ref and page_area and ocr_worthy(area / page_area)]
    return out


def run(units, sources):
    """Fill ocr_status/ocr_text on suspected units. sources: {unit index: [zero-argument pixmap makers]}.
    Returns the engine settings for the document record."""
    disabled = os.environ.get(SWITCH_ENV, "").casefold() == "off"
    folder = tessdata()
    deadline = time.monotonic() + OCR_BUDGET_SECONDS
    for u in units:
        if not u.suspected_unread:
            continue
        if disabled or folder is None:
            u.ocr_status = "disabled" if disabled else "unavailable"
            continue
        if time.monotonic() > deadline:
            u.ocr_status = "deferred"
            continue
        texts, raws, readable, failed, discarded, layouts = [], [], 0, 0, 0, []
        for n, make in enumerate(sources.get(u.index, ())):
            try:
                made = make()
            except Exception:
                continue
            pix, region = made if isinstance(made, tuple) else (made, None)
            readable += 1
            try:
                raw, blocks = ocr_pixmap(pix, folder, with_layout=True)
                raw = raw.strip()
            except Exception:
                failed += 1
                continue
            raws.append(raw)
            clean = usable_ocr_text(raw, photo_like=flat_share(pix) < PHOTO_MAX_FLAT_SHARE)
            discarded += len("".join(raw.split())) - len("".join(clean.split()))
            texts.append(clean)
            kept = set(clean.splitlines())
            for b in blocks:
                for line in b["lines"]:
                    line["kept"] = " ".join(line["text"].split()) in kept
            layouts.append({"picture": n, "region": region, "blocks": blocks})
        text = "\n".join(t for t in texts if t)
        u.ocr_text = text or None
        u.ocr_discarded_chars = discarded
        u.ocr_raw_text = "\n".join(r for r in raws if r) or None
        u.ocr_layout = layouts
        u.ocr_status = ("done" if text else "no_readable_image" if not readable
                        else "failed" if failed == readable else "no_text")
    return {"engine": f"mupdf-tesseract (PyMuPDF {pymupdf.VersionBind})", "language": OCR_LANGUAGE,
            "dpi": OCR_DPI, "available": folder is not None and not disabled, "budget_seconds": OCR_BUDGET_SECONDS}
