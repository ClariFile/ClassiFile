"""Plain-language reasons for suggested names, shared by the app and the review tools (no Qt)."""

FIRST_TEXT = {"page": "on the cover", "slide": "on the title slide", "block": "at the start"}


def similar_reason(count, category):
    """Why a category matches a document: the documents of it the matcher compared with. Never a score."""
    return f"Similar to {count} document{'s' if count != 1 else ''} in {category}"


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _join_places(parts):
    """ "on the cover" + "on most pages" -> "on the cover and most pages" """
    return _join([p if i == 0 or not p.startswith("on ") else p[3:] for i, p in enumerate(parts)])


def page_list(pages):
    """[5, 6, 7, 8, 9] -> "5–9"; [2, 3, 24] -> "2, 3 and 24" (runs of three or more become ranges)."""
    runs, start = [], None
    pages = sorted(set(pages))
    for i, p in enumerate(pages):
        start = p if start is None else start
        if i + 1 == len(pages) or pages[i + 1] != p + 1:
            runs += [f"{start}–{p}"] if p - start >= 2 else [str(x) for x in range(start, p + 1)]
            start = None
    return _join(runs)


def reason_text(evidence, unit="page"):
    """Plain-language reasons for a suggested name, e.g. "on the cover and most pages"."""
    noun = unit if unit in ("page", "slide") else "page"
    parts = []
    for e in evidence:
        src, pages = e["source"], e["pages"]
        if src == "first_page":
            parts.append(FIRST_TEXT.get(unit, "on the cover"))
        elif src == "first_page_ocr":
            parts.append("in a picture " + FIRST_TEXT.get(unit, "on the cover"))
        elif src == "template":
            parts.append(f"on most {noun}s")
        elif src == "recurring":
            parts.append(f"repeated on {noun}s {page_list(pages)}" if len(pages) > 1 else f"on {noun} {pages[0]}")
        elif src == "running":
            parts.append("in the header, footer or slide master")
        elif src == "metadata_title":
            parts.append("in the document's title")
        elif src == "metadata_subject":
            parts.append("in the document's subject")
        elif src == "filename":
            parts.append("in the file name")
        elif src == "keyphrase":
            parts.append("key phrase from the text")
    return _join_places(parts) if parts else ""


def first_page(evidence):
    """The first page (or slide) where a name's evidence appears, or None when it has no page (file name...)."""
    pages = [p for e in evidence for p in (e["pages"] or [])]
    return min(pages) if pages else None
