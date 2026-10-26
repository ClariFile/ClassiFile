"""Plain-language reasons for suggested names, shared by the app and the review tools (no Qt)."""

FIRST_TEXT = {"page": "on the cover", "slide": "on the title slide", "block": "at the start"}


def similar_reason(count, category, words=(), best=True):
    """Why a category is offered for a document: what the matcher compared it with (the category's examples, as
    one average: it says nothing about each of them) and the words the document shares most with them (2 to 4;
    one says too little to show). The other choices, offered so there are three (B2), say they are weaker, and
    say so when they share no words at all. Never a score."""
    examples = f"{count} example{'s' if count != 1 else ''}"
    shared = f"; shares {', '.join(words[:4])}" if len(words) >= 2 else "" if words else "; no words in common"
    return f"{'Best match' if best else 'Weaker match'}: compared with {examples} in {category}{shared}"


def unread_text(units, unit="page"):
    """Where a waiting document holds pictures nothing could read (Catalog.unread_units), and what follows."""
    noun = unit if unit in ("page", "slide") else None
    where = f"on {noun}{'s' if len(units) > 1 else ''} {page_list(units)}" if noun else "in this document"
    return (f"⚠ Some pictures {where} couldn't be read, so ClassiFile won't file it by itself. Look at them in "
            "Details and choose, or Read again from ⋯.")


def new_folder_reason(words):
    """Why the app created a folder by itself for a group of documents (decision record B2, 2.6)."""
    shared = f"they share {', '.join(words[:4])}" if words else "they share a subject"
    return f"No folder matched these documents, and {shared}"


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
