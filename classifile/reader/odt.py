"""ODT reading with the standard library (zip + ElementTree). Read-only; imports nothing from classifile.

Covered: paragraphs, headings, lists, tables, sections, text boxes and grouped/custom shapes, footnotes and
endnotes, headers/footers (master pages), metadata. Tracked-change deletions, comments and generated indexes
(tables of contents) are skipped.
"""
import re

from . import ocr
from .common import (
    DC, DocumentRecord, ReadFailure, UnitRecord, chars, drop_empty, flow_layout, lines, open_zip, opening_lines,
    part, read_snapshot, running, suspect, xml,
)

READER_VERSION = "odt-4"
MIMETYPE = b"application/vnd.oasis.opendocument.text"

OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"
SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}"
META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"
XLINK = "{http://www.w3.org/1999/xlink}"

_SKIP = {OFFICE + "annotation", OFFICE + "annotation-end", TEXT + "tracked-changes", TEXT + "note-citation",
         TEXT + "table-of-content", TEXT + "alphabetical-index", TEXT + "illustration-index",
         TEXT + "table-index", TEXT + "object-index", TEXT + "user-index", TEXT + "bibliography",
         TEXT + "sequence-decls", TEXT + "variable-decls", TEXT + "user-field-decls", OFFICE + "forms",
         DRAW + "image"}
_UNIT_PT = {"in": 72.0, "cm": 72 / 2.54, "mm": 72 / 25.4, "pt": 1.0, "pc": 12.0, "px": 0.75}


def read_odt(path, **kw):
    return read_snapshot(path, _parse, "ODT", **kw)


def _pt(length):
    m = re.fullmatch(r"\s*([\d.]+)\s*([a-z]+)\s*", length or "")
    return float(m.group(1)) * _UNIT_PT[m.group(2)] if m and m.group(2) in _UNIT_PT else None


class _Acc:
    def __init__(self):
        self.text, self.boxes, self.notes, self.images, self.page_break, self.sizes = [], [], [], [], False, []


def _inline(el, acc, st):
    """Mixed content of a paragraph or heading, in order (element text, children, tails)."""
    acc.text.append(el.text or "")
    for ch in el:
        t = ch.tag
        if t in _SKIP:
            pass
        elif t == TEXT + "s":
            acc.text.append(" " * int(ch.get(TEXT + "c", "1")))
        elif t == TEXT + "tab":
            acc.text.append("\t")
        elif t == TEXT + "line-break":
            acc.text.append("\n")
        elif t == TEXT + "soft-page-break":
            acc.page_break = True
        elif t == TEXT + "note":  # footnote/endnote body: kept apart so it does not split the sentence
            body = ch.find(TEXT + "note-body")
            if body is not None:
                acc.notes += [b["text"] for b in _blocks(body, st) if b["text"].strip()]
        elif t in (DRAW + "frame", DRAW + "g", DRAW + "custom-shape", DRAW + "rect", DRAW + "ellipse",
                   DRAW + "text-box", DRAW + "a"):
            _drawing(ch, acc, st)
        else:
            if t == TEXT + "span" and st.size(ch.get(TEXT + "style-name")):
                acc.sizes.append(st.size(ch.get(TEXT + "style-name")))
            _inline(ch, acc, st)
        acc.text.append(ch.tail or "")


def _drawing(el, acc, st):
    """Frames, groups and shapes: text-box paragraphs go to boxes; images record (size in points², package path)."""
    w, h = _pt(el.get(SVG + "width")), _pt(el.get(SVG + "height"))
    image = el.find(DRAW + "image") if el.tag == DRAW + "frame" else None
    if image is not None and w and h:
        acc.images.append((w * h, image.get(XLINK + "href")))
    for ch in el:
        if ch.tag in (TEXT + "p", TEXT + "h", TEXT + "list"):
            acc.boxes += [l for b in _blocks([ch], st) for l in lines(b["text"])]
        elif ch.tag in (DRAW + "frame", DRAW + "g", DRAW + "custom-shape", DRAW + "rect", DRAW + "ellipse",
                        DRAW + "text-box", DRAW + "a"):
            _drawing(ch, acc, st)


def _blocks(container, st):
    """[{"kind", "level", "text", "images", "page_break", "notes"}] for block-level content."""
    out, pending_break = [], False
    for el in container:
        t = el.tag
        if t == TEXT + "soft-page-break":  # between blocks: the next block starts a page
            pending_break = True
            continue
        n_before = len(out)
        if t in (TEXT + "p", TEXT + "h"):
            acc = _Acc()
            _inline(el, acc, st)
            acc.page_break |= el.get(TEXT + "style-name") in st.breaks
            heading = t == TEXT + "h"
            main = "".join(acc.text)
            size = max(acc.sizes + [st.size(el.get(TEXT + "style-name")) or 0]) or None
            text = "\n".join(s for s in (main, "\n".join(acc.boxes)) if s.strip())
            out.append({"kind": "heading" if heading else "paragraph",
                        "level": int(el.get(TEXT + "outline-level", "1")) if heading else None,
                        "text": text, "images": acc.images, "page_break": acc.page_break, "notes": acc.notes,
                        "lines": ([(l, size) for l in main.split("\n")] if main.strip() else [])
                        + [(l, None) for l in acc.boxes]})
        elif t == TEXT + "list":
            items = [b for li in el for b in _blocks(li, st)]  # list-item / list-header -> p, h, nested list
            out.append(_merge("list", items))
        elif t == TABLE + "table":
            rows = []
            for row in _rows(el):
                cells = [" ".join(" ".join(lines(b["text"])) for b in _blocks(c, st) if b["text"].strip())
                         for c in row if c.tag == TABLE + "table-cell"]
                rows.append({"text": "\t".join(cells), "images": [], "page_break": False, "notes": [],
                             "lines": [("\t".join(cells), None)]})
            out.append(_merge("table", rows))
        elif t in (TEXT + "section", TEXT + "list-item", TEXT + "list-header"):
            out += _blocks(el, st)
        elif t in (DRAW + "frame", DRAW + "g", DRAW + "custom-shape", DRAW + "rect", DRAW + "ellipse"):
            acc = _Acc()
            _drawing(el, acc, st)  # page-anchored shapes sit directly in the body
            out.append({"kind": "paragraph", "level": None, "text": "\n".join(acc.boxes), "images": acc.images,
                        "page_break": False, "notes": [], "lines": [(l, None) for l in acc.boxes]})
        if pending_break and len(out) > n_before:
            out[n_before]["page_break"] = True
            pending_break = False
    return out


def _rows(table):
    """Rows of one table, including header rows and row groups; nested tables stay inside their cells."""
    for ch in table:
        if ch.tag == TABLE + "table-row":
            yield ch
        elif ch.tag in (TABLE + "table-header-rows", TABLE + "table-rows", TABLE + "table-row-group"):
            yield from _rows(ch)


def _merge(kind, blocks):
    return {"kind": kind, "level": None, "text": "\n".join(b["text"] for b in blocks if b["text"].strip()),
            "images": [i for b in blocks for i in b["images"]], "page_break": any(b["page_break"] for b in blocks),
            "notes": [n for b in blocks for n in b["notes"]],
            "lines": [l for b in blocks if b["text"].strip() for l in b["lines"]]}


class _Styles:
    """Paragraph styles that start a new page (fo:break-before / fo:break-after = page), and font sizes in points
    by style name, following parent styles down to the default paragraph style."""

    def __init__(self, *roots):
        self.breaks, self.sizes, self.parents, self.default = set(), {}, {}, None
        for root in roots:
            for s in (root.iter(STYLE + "style") if root is not None else ()):
                name = s.get(STYLE + "name")
                props = s.find(STYLE + "paragraph-properties")
                if props is not None and "page" in (props.get(FO + "break-before"), props.get(FO + "break-after")):
                    self.breaks.add(name)
                text_props = s.find(STYLE + "text-properties")
                if text_props is not None and _pt(text_props.get(FO + "font-size")):  # percentages are skipped
                    self.sizes[name] = _pt(text_props.get(FO + "font-size"))
                if s.get(STYLE + "parent-style-name"):
                    self.parents[name] = s.get(STYLE + "parent-style-name")
            for d in (root.iter(STYLE + "default-style") if root is not None else ()):
                text_props = d.find(STYLE + "text-properties")
                if d.get(STYLE + "family") == "paragraph" and text_props is not None:
                    self.default = _pt(text_props.get(FO + "font-size")) or self.default

    def size(self, name):
        seen = set()
        while name and name not in seen:
            seen.add(name)
            if name in self.sizes:
                return self.sizes[name]
            name = self.parents.get(name)
        return self.default


def _parse(data):
    zf = open_zip(data, "ODT")
    mimetype = part(zf, "mimetype", required=False)
    if mimetype is not None and mimetype.strip() != MIMETYPE:
        raise ReadFailure("not an ODF text document")
    manifest = part(zf, "META-INF/manifest.xml", required=False) or b""
    if b"encryption-data" in manifest:
        raise ReadFailure("encrypted ODT")
    content = xml(zf, "content.xml")
    styles = xml(zf, "styles.xml", required=False)
    body = content.find(f"{OFFICE}body/{OFFICE}text")
    if body is None:
        raise ReadFailure("ODT has no text body")

    st = _Styles(content, styles)
    blocks = drop_empty(_blocks(body, st))
    notes = [n for b in blocks for n in b["notes"]]
    if notes:
        blocks.append({"kind": "footnotes", "level": None, "text": "\n".join(notes), "images": [],
                       "page_break": False, "notes": [], "lines": [(l, None) for n in notes for l in n.split("\n")]})

    page_area, hf = None, []
    if styles is not None:
        layouts = {l.get(STYLE + "name"): l for l in styles.iter(STYLE + "page-layout")}
        masters = list(styles.iter(STYLE + "master-page"))
        if masters:  # ponytail: the first master page's size stands for every page
            props = layouts.get(masters[0].get(STYLE + "page-layout-name"))
            props = props.find(STYLE + "page-layout-properties") if props is not None else None
            if props is not None:
                w, h = _pt(props.get(FO + "page-width")), _pt(props.get(FO + "page-height"))
                page_area = w * h if w and h else None
        for m in masters:
            for el in m:
                kind = el.tag.removeprefix(STYLE)  # header, header-left, header-first, footer, ...
                if kind.startswith(("header", "footer")):
                    hf.append((kind.split("-")[0], "\n".join(b["text"] for b in _blocks(el, st))))

    units = []
    for i, b in enumerate(blocks):
        area = None if page_area is None else round(min(1.0, sum(a for a, _ in b["images"]) / page_area), 4)
        n = chars(b["text"])
        # Header/footer images are not body blocks, so every body picture counts as non-repeated.
        flag, rule = suspect(a / page_area for a, _ in b["images"]) if page_area else (False, None)
        units.append(UnitRecord(index=i + 1, kind=b["kind"], level=b["level"], text=b["text"], native_chars=n,
                                text_area=None, image_area=area, nonrepeated_image_area=area,
                                suspected_unread=flag, suspect_rule=rule, layout=flow_layout(b["lines"])))

    for u, blk in zip(units, blocks):
        u.pictures = [href.removeprefix("./") for _, href in blk["images"] if href and "://" not in href]
    # Only pictures stored in the package are OCR'd; linked (external) images are never fetched.
    sources = ocr.flow_sources(units, blocks, page_area, lambda href: part(zf, href.removeprefix("./")))

    return DocumentRecord(
        format="odt", unit="block", unit_count=len(units), metadata=_metadata(zf), template_lines=[],
        recurring_lines=[], running_lines=running(hf), first_page_lines=opening_lines(blocks), units=units,
        ocr=ocr.run(units, sources) if sources else {}, reader_version=READER_VERSION,
    )


def _metadata(zf):
    root = xml(zf, "meta.xml", required=False)
    meta_el = root.find(OFFICE + "meta") if root is not None else None
    if meta_el is None:
        return {}
    meta = {}
    for key, tag in (("title", DC + "title"), ("subject", DC + "subject"), ("description", DC + "description"),
                     ("author", META + "initial-creator"), ("last_author", DC + "creator"),
                     ("application", META + "generator"), ("created", META + "creation-date"),
                     ("modified", DC + "date")):
        el = meta_el.find(tag)
        if el is not None and el.text and el.text.strip():
            meta[key] = el.text.strip()
    keywords = [k.text.strip() for k in meta_el.findall(META + "keyword") if k.text and k.text.strip()]
    if keywords:
        meta["keywords"] = ", ".join(keywords)
    stats = meta_el.find(META + "document-statistic")
    if stats is not None and stats.get(META + "page-count"):
        meta["pages"] = stats.get(META + "page-count")
    return meta
