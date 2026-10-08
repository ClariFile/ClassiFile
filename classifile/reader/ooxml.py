"""DOCX and PPTX reading with the standard library (zip + ElementTree). Read-only; imports nothing from classifile.

Covered: body text, tables (nested flattened), text boxes, grouped shapes, SmartArt text, equations, headers/footers,
slide master/layout text, speaker notes, footnotes/endnotes, core metadata. Tracked deletions, field codes and
mc:Fallback duplicates are skipped. Comments are not document content and are not read.
"""
import posixpath
import re

from . import ocr
from .common import (
    DC, REPEATED_SHARE, DocumentRecord, ReadFailure, UnitRecord, chars, drop_empty, flow_layout, line_stats, lines,
    ocr_worthy, open_zip, opening_lines, part, read_snapshot, running, suspect, xml,
)

DOCX_READER_VERSION = "docx-5"
PPTX_READER_VERSION = "pptx-5"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
A14 = "{http://schemas.microsoft.com/office/drawing/2010/main}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
DCT = "{http://purl.org/dc/terms/}"
EP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
TWIP_EMU = 635


def rels(zf, part_name):
    """{rId: (type, target part)} for one part; external targets are ignored."""
    d, base = posixpath.split(part_name)
    root = xml(zf, posixpath.join(d, "_rels", base + ".rels"), required=False)
    out = {}
    for r in (root.iter(REL) if root is not None else ()):
        target = r.get("Target", "")
        if r.get("TargetMode") == "External" or not target:
            continue
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(d, target))
        out[r.get("Id")] = (r.get("Type", "").rsplit("/", 1)[-1], path)
    return out


def core_metadata(zf):
    meta = {}
    for name, fields in (
        ("docProps/core.xml", (("title", DC + "title"), ("subject", DC + "subject"), ("author", DC + "creator"),
                               ("keywords", CP + "keywords"), ("description", DC + "description"),
                               ("created", DCT + "created"), ("modified", DCT + "modified"))),
        ("docProps/app.xml", (("application", EP + "Application"), ("pages", EP + "Pages"), ("slides", EP + "Slides"))),
    ):
        root = xml(zf, name, required=False)
        for key, tag in (fields if root is not None else ()):
            el = root.find(tag)
            if el is not None and el.text and el.text.strip():
                meta[key] = el.text.strip()
    return meta


def _math_text(el):
    """Office Math -> its run text in order. ponytail: linear text; fraction and script structure is not kept."""
    return " ".join("".join(t.text or "" for t in r.iter(M + "t")) for r in el.iter(M + "r")).strip()


def _choice(el):
    """mc:AlternateContent -> the first mc:Choice (mc:Fallback repeats the same content)."""
    return el.find(MC + "Choice")


# == DOCX ==========================================================================================
_W_SKIP = {W + "pPr", W + "rPr", W + "del", W + "moveFrom", W + "instrText", W + "delInstrText", W + "sectPr",
           W + "tblPr", W + "trPr", W + "tcPr", W + "tblGrid", MC + "Fallback"}


def read_docx(path, **kw):
    return read_snapshot(path, _parse_docx, "DOCX", **kw)


class _Para:
    def __init__(self):
        self.text, self.boxes, self.images, self.page_break, self.sizes = [], [], [], False, []


def _w_inline(el, acc, styles):
    for ch in el:
        t = ch.tag
        if t in _W_SKIP:
            continue
        if t == W + "t":
            acc.text.append(ch.text or "")
        elif t == W + "tab":
            acc.text.append("\t")
        elif t in (W + "br", W + "cr"):
            acc.page_break |= ch.get(W + "type") == "page"
            acc.text.append("\n")
        elif t == W + "lastRenderedPageBreak":
            acc.page_break = True
        elif t in (M + "oMath", M + "oMathPara"):
            acc.text.append(_math_text(ch))
        elif t == W + "noBreakHyphen":
            acc.text.append("-")
        elif t == W + "txbxContent":  # text boxes, including those inside grouped shapes
            for b in _w_blocks(ch, styles):
                acc.boxes.extend(lines(b["text"]))
                acc.images.extend(b["images"])
        elif t == MC + "AlternateContent":
            c = _choice(ch)
            if c is not None:
                _w_inline(c, acc, styles)
        elif t in (WP + "inline", WP + "anchor"):
            ext, blip = ch.find(WP + "extent"), ch.find(".//" + A + "blip")
            if ext is not None and blip is not None:  # (area in EMU², relationship ID of the image part)
                acc.images.append((int(ext.get("cx", 0)) * int(ext.get("cy", 0)), blip.get(R + "embed")))
            _w_inline(ch, acc, styles)
        elif t == W + "r":
            sz = ch.find(f"{W}rPr/{W}sz")
            if sz is not None and (sz.get(W + "val") or "").isdigit():
                acc.sizes.append(int(sz.get(W + "val")) / 2)  # half-points
            _w_inline(ch, acc, styles)
        else:
            _w_inline(ch, acc, styles)


def _p_style(p):
    style = p.find(f"{W}pPr/{W}pStyle")
    return style.get(W + "val") if style is not None else None


def _w_kind(p, styles):
    ppr = p.find(W + "pPr")
    name, outline = styles.kind(_p_style(p))
    direct = ppr.find(W + "outlineLvl") if ppr is not None else None
    if direct is not None:
        outline = direct.get(W + "val")
    if name == "title":
        return "title", None
    if outline is not None and outline.isdigit() and int(outline) < 9:
        return "heading", int(outline) + 1
    m = re.fullmatch(r"heading (\d)", name)
    return ("heading", int(m.group(1))) if m else ("paragraph", None)


def _w_blocks(container, styles):
    """Body-level blocks: [{"kind", "level", "text", "images", "page_break"}]."""
    out = []
    for el in container:
        t = el.tag
        if t == W + "p":
            acc = _Para()
            _w_inline(el, acc, styles)
            ppr = el.find(W + "pPr")
            pbb = ppr.find(W + "pageBreakBefore") if ppr is not None else None
            if pbb is not None and pbb.get(W + "val") not in ("0", "false"):
                acc.page_break = True
            kind, level = _w_kind(el, styles)
            main = "".join(acc.text)
            size = max(acc.sizes) if acc.sizes else styles.size(_p_style(el))
            text = "\n".join(s for s in (main, "\n".join(acc.boxes)) if s.strip())
            out.append({"kind": kind, "level": level, "text": text, "images": acc.images,
                        "page_break": acc.page_break,
                        "lines": ([(l, size) for l in main.split("\n")] if main.strip() else [])
                        + [(l, None) for l in acc.boxes]})
        elif t == W + "tbl":
            rows, images, pb = [], [], False
            for tr in el.findall(W + "tr"):
                cells = []
                for tc in tr.findall(W + "tc"):
                    sub = _w_blocks(tc, styles)
                    cells.append(" ".join(" ".join(lines(b["text"])) for b in sub if b["text"].strip()))
                    images += [i for b in sub for i in b["images"]]
                    pb |= any(b["page_break"] for b in sub)
                rows.append("\t".join(cells))
            out.append({"kind": "table", "level": None, "text": "\n".join(r for r in rows if r.strip()),
                        "images": images, "page_break": pb, "lines": [(r, None) for r in rows if r.strip()]})
        elif t == W + "sdt":
            content = el.find(W + "sdtContent")
            if content is not None:
                out += _w_blocks(content, styles)
        elif t in (W + "customXml", W + "ins", W + "moveTo"):
            out += _w_blocks(el, styles)
        elif t == MC + "AlternateContent":
            c = _choice(el)
            if c is not None:
                out += _w_blocks(c, styles)
    return out


def _half_points(el):
    v = el.get(W + "val") if el is not None else None
    return int(v) / 2 if v and v.isdigit() else None


class _WStyles:
    """Paragraph styles: name and outline level (headings), and font size following basedOn and the defaults."""

    def __init__(self, root):
        self.info, self.default_id = {}, None
        for s in (root.iter(W + "style") if root is not None else ()):
            name, outline, based = s.find(W + "name"), s.find(f"{W}pPr/{W}outlineLvl"), s.find(W + "basedOn")
            # ponytail: outline levels are not inherited through basedOn; built-in headings carry their own.
            self.info[s.get(W + "styleId")] = (
                (name.get(W + "val", "") if name is not None else "").casefold(),
                outline.get(W + "val") if outline is not None else None,
                _half_points(s.find(f"{W}rPr/{W}sz")), based.get(W + "val") if based is not None else None)
            if s.get(W + "type") == "paragraph" and s.get(W + "default") in ("1", "true"):
                self.default_id = s.get(W + "styleId")
        self.default_size = _half_points(root.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr/{W}sz")) \
            if root is not None else None

    def kind(self, style_id):
        return self.info.get(style_id or self.default_id, ("", None, None, None))[:2]

    def size(self, style_id):
        sid, seen = style_id or self.default_id, set()
        while sid in self.info and sid not in seen:
            seen.add(sid)
            if self.info[sid][2]:
                return self.info[sid][2]
            sid = self.info[sid][3]
        return self.default_size


def _parse_docx(data):
    zf = open_zip(data, "DOCX")
    styles = _WStyles(xml(zf, "word/styles.xml", required=False))
    doc = xml(zf, "word/document.xml")
    body = doc.find(W + "body")
    if body is None:
        raise ReadFailure("DOCX has no body")

    pg = body.find(f"{W}sectPr/{W}pgSz")  # ponytail: the final section's page size stands for all sections
    page_area = None
    if pg is not None and pg.get(W + "w") and pg.get(W + "h"):
        page_area = float(pg.get(W + "w")) * TWIP_EMU * float(pg.get(W + "h")) * TWIP_EMU

    blocks = drop_empty(_w_blocks(body, styles))
    for part_name, kind in (("word/footnotes.xml", "footnotes"), ("word/endnotes.xml", "endnotes")):
        root = xml(zf, part_name, required=False)
        notes = []
        for n in (root if root is not None else ()):
            if n.get(W + "type") in (None, "normal"):
                notes += [b["text"] for b in _w_blocks(n, styles) if b["text"].strip()]
        if notes:
            blocks.append({"kind": kind, "level": None, "text": "\n".join(notes), "images": [], "page_break": False,
                           "lines": [(l, None) for n in notes for l in n.split("\n")]})

    units = []
    for i, b in enumerate(blocks):
        area = None if page_area is None else round(min(1.0, sum(a for a, _ in b["images"]) / page_area), 4)
        n = chars(b["text"])
        # Header/footer images are not body blocks, so every body image counts as non-repeated.
        flag, rule = suspect(a / page_area for a, _ in b["images"]) if page_area else (False, None)
        units.append(UnitRecord(index=i + 1, kind=b["kind"], level=b["level"], text=b["text"], native_chars=n,
                                text_area=None, image_area=area, nonrepeated_image_area=area,
                                suspected_unread=flag, suspect_rule=rule, layout=flow_layout(b["lines"])))

    doc_rels = rels(zf, "word/document.xml")
    for u, b in zip(units, blocks):
        u.pictures = [doc_rels[rid][1] for _, rid in b["images"] if rid in doc_rels]
    sources = ocr.flow_sources(units, blocks, page_area, lambda rid: part(zf, doc_rels[rid][1]))

    hf = sorted((n for n in zf.namelist() if re.fullmatch(r"word/(header|footer)\d*\.xml", n)),
                key=lambda n: (n.startswith("word/footer"), n))
    run = running((re.match(r"word/(header|footer)", n).group(1),
                   "\n".join(b["text"] for b in _w_blocks(xml(zf, n), styles))) for n in hf)

    return DocumentRecord(
        format="docx", unit="block", unit_count=len(units), metadata=core_metadata(zf), template_lines=[],
        recurring_lines=[], running_lines=run, first_page_lines=opening_lines(blocks), units=units,
        ocr=ocr.run(units, sources) if sources else {}, reader_version=DOCX_READER_VERSION,
    )


# == PPTX ==========================================================================================
def read_pptx(path, **kw):
    return read_snapshot(path, _parse_pptx, "PPTX", **kw)


def _a_paras(tx_body):
    """DrawingML text body -> [(paragraph text, largest run size in points or None)]."""
    if tx_body is None:
        return []
    paras = []
    for p in tx_body.findall(A + "p"):
        s, sizes = [], []
        for ch in p:
            if ch.tag in (A + "r", A + "fld"):
                s.append(ch.findtext(A + "t") or "")
                rpr = ch.find(A + "rPr")
                if rpr is not None and rpr.get("sz"):
                    sizes.append(int(rpr.get("sz")) / 100)
            elif ch.tag == A + "br":
                s.append("\n")
            elif ch.tag == A14 + "m":  # Office Math equation inside the paragraph
                s.append(_math_text(ch))
        paras.append(("".join(s), max(sizes) if sizes else None))
    return paras


def _a_text(tx_body):
    """DrawingML text body -> text, one line per paragraph."""
    return "\n".join(t for t, _ in _a_paras(tx_body))


IDENTITY = (0.0, 0.0, 1.0, 1.0)  # child-to-slide transform: X = tx + sx * x, Y = ty + sy * y (EMU)
EMU_PT = 12700


def _geom(xfrm, tf):
    """(area in slide EMU², box in slide points) of a shape, or (None, None) when it has no own geometry."""
    off, ext = (xfrm.find(A + "off"), xfrm.find(A + "ext")) if xfrm is not None else (None, None)
    if ext is None:
        return None, None  # ponytail: placeholder geometry inherited from the layout is not resolved
    tx, ty, sx, sy = tf
    x, y = (int(off.get("x", 0)), int(off.get("y", 0))) if off is not None else (0, 0)
    cx, cy = int(ext.get("cx", 0)), int(ext.get("cy", 0))
    box = [tx + sx * x, ty + sy * y, tx + sx * (x + cx), ty + sy * (y + cy)]
    return cx * cy * sx * sy, [round(v / EMU_PT, 1) for v in box]


def _group_tf(xf, tf):
    """Transform for a group's children: their chOff/chExt space is mapped onto the group's off/ext box."""
    if xf is None:
        return tf
    off, ext, choff, chext = (xf.find(A + n) for n in ("off", "ext", "chOff", "chExt"))
    if None in (off, ext, choff, chext) or not int(chext.get("cx", 0)) or not int(chext.get("cy", 0)):
        return tf
    tx, ty, sx, sy = tf
    kx, ky = int(ext.get("cx")) / int(chext.get("cx")), int(ext.get("cy")) / int(chext.get("cy"))
    return (tx + sx * (int(off.get("x", 0)) - int(choff.get("x", 0)) * kx),
            ty + sy * (int(off.get("y", 0)) - int(choff.get("y", 0)) * ky), sx * kx, sy * ky)


def _shape(text, ph, geom, pic=None, paras=None):
    area, box = geom
    return {"text": text, "ph": ph, "area": area, "bbox": box, "pic": pic,
            "paras": paras if paras is not None else [(l, None) for l in text.split("\n")]}


def _p_shapes(tree, part_rels, zf, tf=IDENTITY):
    """Shapes in drawing order: {"text", "ph", "area", "bbox", "pic", "paras"} (pic = image part or None)."""
    out = []
    for el in tree:
        t = el.tag
        if t == P + "sp":
            ph = el.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
            paras = _a_paras(el.find(P + "txBody"))
            out.append(_shape("\n".join(p for p, _ in paras), None if ph is None else ph.get("type", "body"),
                              _geom(el.find(f"{P}spPr/{A}xfrm"), tf), paras=paras))
        elif t == P + "grpSp":
            out += _p_shapes(el, part_rels, zf, _group_tf(el.find(f"{P}grpSpPr/{A}xfrm"), tf))
        elif t == P + "graphicFrame":
            gd = el.find(f"{A}graphic/{A}graphicData")
            text = ""
            if gd is not None and gd.find(A + "tbl") is not None:
                text = "\n".join("\t".join(" ".join(lines(_a_text(tc.find(A + "txBody")))) for tc in tr.findall(A + "tc"))
                                 for tr in gd.find(A + "tbl").findall(A + "tr"))
            elif gd is not None and gd.find(DGM + "relIds") is not None:  # SmartArt: text lives in the data part
                target = part_rels.get(gd.find(DGM + "relIds").get(R + "dm"), (None, None))[1]
                data = xml(zf, target, required=False) if target else None
                if data is not None:
                    text = "\n".join(_a_text(pt.find(DGM + "t")) for pt in data.iter(DGM + "pt"))
            # ponytail: chart text (titles, labels) is not read yet.
            out.append(_shape(text, None, _geom(el.find(P + "xfrm"), tf)))
        elif t == P + "pic":
            blip = el.find(f"{P}blipFill/{A}blip")
            target = part_rels.get(blip.get(R + "embed"), (None, None))[1] if blip is not None else None
            out.append(_shape("", None, _geom(el.find(f"{P}spPr/{A}xfrm"), tf), pic=target or "?"))
        elif t == MC + "AlternateContent":
            c = _choice(el)
            if c is not None:
                out += _p_shapes(c, part_rels, zf, tf)
    return out


_RUNNING_PH = {"ftr", "dt", "sldNum", "hdr"}


def _sp_tree(root):
    tree = root.find(f"{P}cSld/{P}spTree")
    return tree if tree is not None else ()


def _parse_pptx(data):
    zf = open_zip(data, "PPTX")
    pres_name = "ppt/presentation.xml"
    pres = xml(zf, pres_name)
    pres_rels = rels(zf, pres_name)
    size = pres.find(P + "sldSz")
    slide_area = int(size.get("cx")) * int(size.get("cy")) if size is not None else None
    slide_names = [pres_rels[s.get(R + "id")][1] for s in pres.iter(P + "sldId") if s.get(R + "id") in pres_rels]
    if not slide_names:
        raise ReadFailure("PPTX has no slides")

    slides, layouts = [], {}
    for name in slide_names:
        root = xml(zf, name)
        srels = rels(zf, name)
        shapes = _p_shapes(_sp_tree(root), srels, zf)
        notes = ""
        for kind, target in srels.values():
            if kind == "notesSlide":
                nroot = xml(zf, target, required=False)
                if nroot is not None:
                    notes = "\n".join(s["text"] for s in _p_shapes(_sp_tree(nroot), {}, zf) if s["ph"] == "body")
            elif kind == "slideLayout":
                layouts.setdefault(target, None)
        slides.append((root.get("show") != "0", shapes, notes))

    # Images on at least half the slides (same image part) count as repeated, as for PDFs.
    pic_slides = {}
    for i, (_, shapes, _) in enumerate(slides):
        for s in shapes:
            if s["pic"]:
                pic_slides.setdefault(s["pic"], set()).add(i)
    repeated = max(2, len(slides) * REPEATED_SHARE)  # one slide cannot make an image "repeated"

    def frac(areas):
        if slide_area is None:
            return None
        return round(min(1.0, sum(a for a in areas if a) / slide_area), 4)

    # Footer, date and slide-number placeholders are running text: kept in the slide text, but the line
    # statistics and first-slide lines use the rest, and the footers are reported as running lines.
    units, texts, footers = [], [], []
    for i, (shown, shapes, notes) in enumerate(slides):
        text = "\n".join(s["text"] for s in shapes if s["text"].strip())
        texts.append("\n".join(s["text"] for s in shapes if s["text"].strip() and s["ph"] not in _RUNNING_PH))
        footers += [("footer", s["text"]) for s in shapes if s["ph"] == "ftr"]
        title = "\n".join(s["text"] for s in shapes if s["ph"] in ("title", "ctrTitle") and s["text"].strip())
        n = chars(text)
        nonrep = frac(s["area"] for s in shapes if s["pic"] and len(pic_slides[s["pic"]]) < repeated)
        flag, rule = suspect(s["area"] / slide_area for s in shapes
                             if s["pic"] and s["area"] and slide_area and len(pic_slides[s["pic"]]) < repeated)
        units.append(UnitRecord(
            index=i + 1, kind="slide" if shown else "hidden slide", text=text, native_chars=n,
            text_area=frac(s["area"] for s in shapes if s["text"].strip()),
            image_area=frac(s["area"] for s in shapes if s["pic"]), nonrepeated_image_area=nonrep,
            suspected_unread=flag, suspect_rule=rule, title=title or None, notes=notes or None,
            pictures=[s["pic"] for s in shapes if s["pic"] and s["pic"] != "?"],
            layout={"width": round(int(size.get("cx")) / EMU_PT, 1) if size is not None else None,
                    "height": round(int(size.get("cy")) / EMU_PT, 1) if size is not None else None,
                    "blocks": [{"bbox": s["bbox"], "lines": [{"text": line, "bbox": None, "size": pt}
                                                             for para, pt in s["paras"] for line in para.split("\n")]}
                               for s in shapes if s["text"].strip()]}))

    # Text placed on layouts and masters (not placeholders) shows on every slide that uses them.
    parts, masters = [], {}
    for layout in layouts:
        lroot = xml(zf, layout, required=False)
        if lroot is None:
            continue
        parts += [("layout", s["text"]) for s in _p_shapes(_sp_tree(lroot), {}, zf) if s["ph"] is None]
        for kind, target in rels(zf, layout).values():
            if kind == "slideMaster":
                masters.setdefault(target, None)
    for master in masters:
        mroot = xml(zf, master, required=False)
        if mroot is not None:
            parts += [("master", s["text"]) for s in _p_shapes(_sp_tree(mroot), {}, zf) if s["ph"] is None]

    # Suspected slides: OCR their non-repeated pictures (repeated ones are backgrounds and logos).
    sources = {}
    for u, (_, shapes, _) in zip(units, slides):
        if u.suspected_unread:
            sources[u.index] = [lambda t=s["pic"]: ocr.render_image(part(zf, t)) for s in shapes
                                if s["pic"] and len(pic_slides[s["pic"]]) < repeated
                                and s["area"] and slide_area and ocr_worthy(s["area"] / slide_area)]

    template, recurring = line_stats(texts)
    return DocumentRecord(
        format="pptx", unit="slide", unit_count=len(units), metadata=core_metadata(zf), template_lines=template,
        recurring_lines=recurring, running_lines=running(footers + parts), first_page_lines=lines(texts[0]),
        units=units, ocr=ocr.run(units, sources) if sources else {}, reader_version=PPTX_READER_VERSION,
    )
