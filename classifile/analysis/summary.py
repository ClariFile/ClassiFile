"""Hidden internal summary (decision record B6): a structured, extractive record per snapshot.

Never shown to the user and never written into any document. Rule-based only; no summary method or citation
guarantees faithfulness. All constants are provisional and documented here.
  - keyphrases: RAKE-style (phrases split at stopwords and punctuation, scored by word degree/frequency,
    weighted by the square root of the phrase count);
  - digest: up to DIGEST_SENTENCES sentences with the highest keyphrase-word density, in document order;
  - sections: only when the text exceeds LONG_DOC_CHARS; a section starts at a level-1 heading once the
    current one holds MIN_SECTION_CHARS, or anywhere once it holds SECTION_CHARS.
"""
import math
import re
from collections import Counter

from classifile.analysis.candidates import is_boilerplate_title
from classifile.reader import unread_gap

SUMMARY_VERSION = "summary-5"   # 5: unresolved gaps include pictures OCR left unread
KEYPHRASES = 12
MAX_PHRASE_WORDS = 4
DIGEST_SENTENCES = 5
SENTENCE_WORDS = (4, 60)
MAX_SENTENCE_CHARS = 300
MAX_OUTLINE = 200
MAX_ENTITIES = 10
LONG_DOC_CHARS = 40_000
SECTION_CHARS = 20_000
MIN_SECTION_CHARS = 2_000
MIN_LANGUAGE_WORDS = 50
MIN_ENGLISH_STOPWORD_SHARE = 0.15   # English prose runs at roughly 0.4; lists and slides lower
MAX_NON_LATIN_SHARE = 0.3

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below between
both but by can could did do does doing down during each either etc few for from further had has have having he
her here hers herself him himself his how i if in into is it its itself just may me might more most must my
myself no nor not now of off on once only or other our ours ourselves out over own per same shall she should so
some such than that the their theirs them themselves then there these they this those through thus to too under
until up upon us use used using very via was we were what when where which while who whom why will with within
without would yet you your yours yourself yourselves
""".split())

# Document-purpose cues (a word in the title, opening lines or file name). Provisional; E1 revisits purpose.
PURPOSE_CUES = {
    "lecture": "lecture", "lectures": "lecture", "lab": "lab", "laboratory": "lab", "practical": "lab",
    "exercise": "exercise", "exercises": "exercise", "assignment": "assignment", "homework": "assignment",
    "tutorial": "tutorial", "quiz": "assessment", "exam": "assessment", "examination": "assessment",
    "syllabus": "syllabus", "invoice": "invoice", "receipt": "receipt", "report": "report", "minutes": "minutes",
    "agenda": "agenda", "proposal": "proposal", "contract": "contract", "agreement": "contract",
    "manual": "manual", "handbook": "manual", "guide": "guide", "thesis": "thesis", "dissertation": "thesis",
    "resume": "resume", "cv": "resume", "letter": "letter", "notes": "notes", "slides": "slides",
}

ENTITY_PATTERNS = {
    "email": r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b",
    "url": r"\bhttps?://[^\s<>\"')\]]+|\bwww\.[^\s<>\"')\]]+",
    "date": r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b"
            r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b"
            r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    "code": r"\b[A-Z]{2,5}[- ]?\d{3,5}[A-Z]?\b",                 # course or product codes such as ABC-1234
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b",
    "money": r"[$€£¥]\s?\d[\d,]*(?:\.\d{2})?\b|\b\d[\d,]*(?:\.\d{2})?\s?(?:USD|EUR|GBP|MMK|Ks)\b",
}
_ENTITIES = {k: re.compile(p) for k, p in ENTITY_PATTERNS.items()}
_SPLIT = re.compile(r"[.,;:!?()\[\]{}\"“”‘’…•▪●◦|/\\<>=*\n\t–—]+")
_WORD = re.compile(r"[^\W_][\w+#'’-]*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def _unit_text(u):
    """Native text, speaker notes and OCR text (the reader has already removed OCR junk)."""
    return "\n".join(t for t in (u.text, u.notes, u.ocr_text) if t)


def keyphrases(text, k=KEYPHRASES):
    phrases = []
    for chunk in _SPLIT.split(text):
        cur = []
        for w in _WORD.findall(chunk):
            lw = w.casefold()
            if lw in STOPWORDS or len(lw) < 2 or lw.replace(".", "").isdigit():
                if cur:
                    phrases.append(tuple(cur))
                cur = []
            else:
                cur.append(lw)
        if cur:
            phrases.append(tuple(cur))
    phrases = [p for p in phrases if len(p) <= MAX_PHRASE_WORDS]
    freq, degree = Counter(), Counter()
    for p in phrases:
        for w in p:
            freq[w] += 1
            degree[w] += len(p)
    counts = Counter(phrases)
    scored = {p: sum(degree[w] / freq[w] for w in p) * math.sqrt(n) for p, n in counts.items()}
    return [{"phrase": " ".join(p), "count": counts[p], "score": round(s, 3)}
            for p, s in sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def digest(units, phrases, k=DIGEST_SENTENCES):
    words = {w for p in phrases for w in p["phrase"].split()}
    candidates, seen = [], set()
    for u in units:
        for s in _SENTENCE.split(_unit_text(u)):
            s = " ".join(s.split())
            n = len(_WORD.findall(s))
            if not (SENTENCE_WORDS[0] <= n <= SENTENCE_WORDS[1]) or len(s) > MAX_SENTENCE_CHARS or s.casefold() in seen:
                continue
            seen.add(s.casefold())
            hits = sum(1 for w in _WORD.findall(s) if w.casefold() in words)
            if hits:
                candidates.append((hits / math.sqrt(n), len(candidates), u.index, s))
    best = sorted(candidates, key=lambda c: (-c[0], c[1]))[:k]
    return [{"text": s, "unit": unit} for _, _, unit, s in sorted(best, key=lambda c: c[1])]


def entities(units):
    found = {}
    for u in units:
        text = _unit_text(u)
        for kind, rx in _ENTITIES.items():
            for m in rx.finditer(text):
                e = found.setdefault(kind, {}).setdefault(m.group(0), {"value": m.group(0), "count": 0, "unit": u.index})
                e["count"] += 1
    return {kind: sorted(vals.values(), key=lambda e: -e["count"])[:MAX_ENTITIES] for kind, vals in found.items()}


def outline(record):
    template = {t["example"] for t in record.template_lines} | {r["line"] for r in record.running_lines}
    out = []
    for u in record.units:
        if u.kind in ("title", "heading"):
            text, level = u.text.split("\n")[0], 0 if u.kind == "title" else u.level
        elif u.title:
            text, level = u.title.split("\n")[0], 1
        elif u.kind in ("page", "slide", "hidden slide"):
            # ponytail: the first non-template, non-running line of a page or untitled slide stands in for its heading.
            first = next((l for l in (" ".join(x.split()) for x in u.text.splitlines())
                          if l and l not in template and any(c.isalpha() for c in l)), None)
            if not first or len(first) > 80:
                continue
            text, level = first, 1
        else:
            continue
        text = " ".join(text.split())
        if not out or out[-1]["text"] != text:  # one entry for a heading repeated on consecutive pages
            out.append({"text": text, "unit": u.index, "level": level})
    return out[:MAX_OUTLINE]


def _title(record, analysis):
    meta = " ".join(str(record.metadata.get("title") or "").split())
    if meta and not is_boilerplate_title(meta):
        return {"text": meta, "source": "metadata_title"}
    for u in record.units:
        if u.kind == "title" or u.title:
            return {"text": " ".join((u.title or u.text).split()), "source": "title_style" if u.kind == "title" else "slide_title"}
    for s in analysis.suggestions if analysis else ():
        if any(e.source == "first_page" for e in s.evidence):
            return {"text": s.name, "source": "first_page"}
    return None


def _purpose(record, file_name, title):
    found = []
    for source, text in [("title", title["text"] if title else ""), ("file_name", file_name),
                         *(("first_page", l) for l in record.first_page_lines[:10])]:
        for w in _WORD.findall(text.replace("_", " ")):
            label = PURPOSE_CUES.get(w.casefold())
            if label and (label, source) not in [(f["label"], f["source"]) for f in found]:
                found.append({"label": label, "cue": w.casefold(), "source": source})
    return found


def _flags(record, text):
    ocr = {}
    for u in record.units:
        if u.ocr_status:
            ocr.setdefault(u.ocr_status, []).append(u.index)
    flags = {"suspected_unread_units": [u.index for u in record.units if u.suspected_unread],
             "ocr": ocr,
             # Suspected gaps OCR did not resolve; decisions made while they remain are provisional (B3).
             "unresolved_gaps": [u.index for u in record.units
                                 if unread_gap(u.suspected_unread, u.ocr_status, u.ocr_pictures)],
             # OCR read something, but all of it looked like junk (photos, decorations) and was discarded.
             "ocr_text_discarded": [u.index for u in record.units if u.ocr_discarded_chars and not u.ocr_text]}
    if not any(c.isalpha() for u in record.units for c in u.text):
        flags["no_native_text"] = True
    words = [w.casefold() for w in _WORD.findall(text)]
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return flags
    non_latin = sum(1 for c in letters if ord(c) > 0x24F) / len(letters)
    if non_latin > MAX_NON_LATIN_SHARE:
        flags["language"] = {"flag": "non_latin_script", "rule": f"non_latin_letter_share_above_{MAX_NON_LATIN_SHARE}"}
    elif len(words) >= MIN_LANGUAGE_WORDS and sum(w in STOPWORDS for w in words) / len(words) < MIN_ENGLISH_STOPWORD_SHARE:
        flags["language"] = {"flag": "possibly_not_english",
                             "rule": f"english_stopword_share_below_{MIN_ENGLISH_STOPWORD_SHARE}"}
    return flags


def _sections(units):
    sections, cur, size = [], [], 0
    for u in units:
        n = len(_unit_text(u))
        starts = u.kind in ("title", "heading") and (u.level or 1) <= 1 and size >= MIN_SECTION_CHARS
        if cur and (starts or size >= SECTION_CHARS):
            sections.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += n
    if cur:
        sections.append(cur)
    out = []
    for sec in sections:
        text = "\n".join(_unit_text(u) for u in sec)
        phrases = keyphrases(text, 6)
        heading = next((u.text.split("\n")[0] for u in sec if u.kind in ("title", "heading")), None)
        out.append({"units": [sec[0].index, sec[-1].index], "heading": heading, "keyphrases": phrases,
                    "digest": digest(sec, phrases, 3)})
    return out


def summarize(record, analysis, file_name):
    text = "\n".join(_unit_text(u) for u in record.units)
    title = _title(record, analysis)
    phrases = keyphrases(text)
    return {
        "summary_version": SUMMARY_VERSION,
        "title": title,
        "self_description_candidates": [{"name": s.name, "sources": [e.source for e in s.evidence]}
                                        for s in (analysis.suggestions[:5] if analysis else [])],
        "purpose": _purpose(record, file_name, title),
        "outline": outline(record),
        "keyphrases": phrases,
        "entities": entities(record.units),
        "digest": digest(record.units, phrases),
        "flags": _flags(record, text),
        "sections": _sections(record.units) if len(text) > LONG_DOC_CHARS else [],
    }
