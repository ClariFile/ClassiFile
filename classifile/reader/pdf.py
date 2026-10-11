"""Native PDF reading: per-page observations and a document record. Read-only; imports nothing from classifile."""
from collections import defaultdict

import pymupdf

from . import ocr
from .common import (
    REPEATED_SHARE, DocumentRecord, ReadFailure, UnitRecord, chars, line_stats, lines, ocr_worthy, page_layout,
    read_snapshot, suspect,
)

READER_VERSION = "pdf-5"   # extraction method; bump when output for the same bytes changes

LAYOUT_FLAGS = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES  # text only; no image bytes
pymupdf.TOOLS.mupdf_display_errors(False)  # MuPDF warnings could echo content; keep stderr clean


def read_pdf(path, **kw):
    return read_snapshot(path, _parse, "pages", **kw)


def _parse(data):
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ReadFailure("corrupt or unreadable PDF") from None
    with doc:
        if doc.needs_pass:
            raise ReadFailure("encrypted PDF")
        if doc.page_count == 0:
            raise ReadFailure("PDF has no pages")
        return _record(doc)


def _record(doc):
    n = doc.page_count
    texts, images = [], []
    for page in doc:
        texts.append(page.get_text())  # unsorted: sort=True merges side-by-side columns
        images.append(page.get_image_info(hashes=True, xrefs=True))

    # Images repeated on >= half the pages, identified by xref (0 = inline, no identity) or by digest.
    xref_pages, digest_pages = defaultdict(set), defaultdict(set)
    for i, infos in enumerate(images):
        for im in infos:
            if im["xref"]:
                xref_pages[im["xref"]].add(i)
            digest_pages[im["digest"]].add(i)
    repeated = max(2, n * REPEATED_SHARE)  # one page cannot make an image "repeated" (single-page scans)

    def is_repeated(im):
        return (im["xref"] and len(xref_pages[im["xref"]]) >= repeated) or len(digest_pages[im["digest"]]) >= repeated

    units = []
    for i, page in enumerate(doc):
        rect, area = page.rect, abs(page.rect) or 1.0
        # ponytail: overlapping boxes are summed then capped at 1, not unioned; fine as a coarse observation.
        frac = lambda boxes: round(min(1.0, sum(abs(pymupdf.Rect(b) & rect) for b in boxes) / area), 4)
        text_blocks = [b[:4] for b in page.get_text("blocks") if b[6] == 0]
        n_chars = chars(texts[i])
        nonrep = frac(im["bbox"] for im in images[i] if not is_repeated(im))
        flag, rule = suspect(abs(pymupdf.Rect(im["bbox"]) & rect) / area for im in images[i] if not is_repeated(im))
        units.append(UnitRecord(
            index=i + 1, kind="page", text=texts[i], native_chars=n_chars, text_area=frac(text_blocks),
            image_area=frac(im["bbox"] for im in images[i]), nonrepeated_image_area=nonrep,
            suspected_unread=flag, suspect_rule=rule, layout=page_layout(page.get_text("dict", flags=LAYOUT_FLAGS)),
        ))

    # Suspected pages: OCR each non-repeated image region (rendered from the page, so composited as shown).
    # ponytail: overlapping image boxes are OCR'd separately and may repeat text.
    sources = {}
    for i, u in enumerate(units):
        if u.suspected_unread:
            rect, area = doc[i].rect, abs(doc[i].rect) or 1.0
            clips = [pymupdf.Rect(im["bbox"]) & rect for im in images[i] if not is_repeated(im)]
            # Each maker returns the picture and where it sits on the page (points).
            sources[i + 1] = [lambda i=i, c=c: (doc[i].get_pixmap(dpi=ocr.dpi_for(c), clip=c), [round(v, 1) for v in c])
                              for c in clips if ocr_worthy(abs(c) / area)]

    template, recurring = line_stats(texts)
    return DocumentRecord(
        format="pdf", unit="page", unit_count=n, metadata=dict(doc.metadata or {}), template_lines=template,
        recurring_lines=recurring, running_lines=[], first_page_lines=lines(texts[0]), units=units,
        ocr=ocr.run(units, sources) if sources else {}, reader_version=READER_VERSION,
    )
