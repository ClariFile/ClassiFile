"""Rule-based category-name suggestions with evidence. No ML. Suggestions only; the user decides.

Evidence weights are simple, provisional and documented here (E6/E7 revisit them):
  first_page 2, template 2, recurring 2 (a template line is not also counted as recurring),
  first_page_ocr 1 (a line read from a picture on the cover or title slide),
  running 2 (DOCX/ODT headers and footers, PPTX master and layout text),
  metadata_title 1, metadata_subject 1, filename 1 (support only: a file name never suggests a name by itself).
"first_page" is the first page or slide (its first six qualifying lines), or the first qualifying opening line of
a DOCX/ODT: those have no cover page, and the lines after the first are headings and body text.
A suggestion's score is the sum of the weights of its distinct sources. Scores are ranking aids,
not probabilities. Equal scores mean comparable evidence: the analysis does not pick a winner.
Organisation lines (University, Faculty, Department, School, College, Institute) describe the publisher, not the
document, so they rank after every other candidate (provisional, like the weights).

Names must be clean and short, never cut-off sentences (provisional rules, revisited with the user's name reviews):
  - cover lines wrapped mid-sentence are joined before use;
  - a numbered list on the cover (two or more lines "1. ...", "2. ...") is the document's contents, not its name;
  - fragments ending in a connecting word (and, of, the, to, for, with, ...) or a comma are rejected, and so are
    lines that read like sentences ("is", "are", "was" or "were" as the verb);
  - names of 2 to 5 words are preferred: other lengths rank as if their evidence weighed 1 less;
  - names are shown in Title Case; acronyms (OSI, TCP/IP) and names with symbols or inner capitals (C++, IPv4,
    JavaScript) keep their form;
  - when nothing on the cover, in headers or in the metadata qualifies, key phrases of the text (native and
    cleaned OCR text) are suggested;
  - rejected: unbalanced brackets or quotes, and names that are only a generic section word (Outline,
    Introduction, Summary, Example, Solution, ...); "Lecture", "Chapter", "Week", "Lab", "Unit" or "Part" with a
    number in any form (also "Lecture (5") is instance-level; a bare code (capital letters and digits, such as
    "ABC-1234"), a line with an IP address, quoted data, and an academic rank alone ("Associate Professor");
  - demoted below the top three (shown under "More"): people's names (the Author metadata, a title or honorific
    such as Dr., Prof., Daw or U, or a line next to "Lecturer", "Presented by", "Prepared by", "Instructor"),
    institution lines, and lines whose only evidence is repeating on some pages. Those are mostly section
    headings; their score is unchanged, so this does not settle which self-description is dominant (E7).
"""
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

ANALYZER_VERSION = "rules-8"
WEIGHTS = {"keyphrase": 1, "first_page": 2, "first_page_ocr": 1, "template": 2, "recurring": 2, "running": 2, "metadata_title": 1, "metadata_subject": 1, "filename": 1}
FIRST_PAGE_LINES = 6    # only the first few qualifying first-page lines are candidates
FLOW_START_LINES = 1    # DOCX/ODT have no cover page: after the first qualifying line come headings and body text
MAX_SUGGESTIONS = 12
MAX_NAME_CHARS = 80
MAX_NAME_WORDS = 8
PREFERRED_WORDS = (2, 5)
KEYPHRASE_SUGGESTIONS = 3

_UNIT = (r"lecture|lect|lec|l|week|wk|chapter|chap|ch|lab|unit|part|session|tutorial|tut|quiz|exercises?|ex"
         r"|section|sec|module|mod|topic|assignment|hw|homework|page|slide|day|class|no|invoice|inv|receipt|order")
_MONTH = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
# Instance identifiers: never category names on their own.
INSTANCE_PATTERNS = [
    rf"\b(?:{_UNIT})\s*[-.#:(\[]?\s*\d+[a-z]?(?:\.\d+)*(?:\s+of\s+\d+)?\b",      # Lecture -9, L-2, Lecture (5, Page 1 of 7
    r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b",   # dates
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH})[a-z]*\.?,?\s+\d{{2,4}}\b",
    rf"\b(?:{_MONTH})[a-z]*\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{2,4}}\b",
    r"(?<![\w.-])\d+(?:\.\d+){1,2}\.?(?![\w.-])",                               # 4.2, 4.2.1 (not IPs)
]
_INSTANCE = re.compile("|".join(f"(?:{p})" for p in INSTANCE_PATTERNS), re.I)
_LIST_ITEM = re.compile(r"^\d{1,2}[.)]\s*\S")       # "1. Sampling", "2) Scope"
_EDGE_NUMBER = re.compile(r"^\d+[.)]?\s+|\s+\d+$")  # leading "4. " / trailing page numbers

# Prerequisite / reference / see-also contexts: such lines are mentions, not self-descriptions.
_MENTION_HEADING = re.compile(
    r"^(references?|prerequisites?|pre-requisites?|see also|further reading|recommended reading|bibliography"
    r"|required (knowledge|background)|related courses?)\s*:?$", re.I)
_MENTION_LINE = re.compile(
    r"^((prerequisites?|pre-requisites?|references?|source|textbook|cf\.?)\s*[:\-–]"
    r"|(see also|refer to|requires|adapted from|based on)\b)", re.I)

# Application boilerplate titles, including localized "PowerPoint Presentation" forms.
_BOILERPLATE = re.compile(
    r"^(untitled|document\s*\d*|presentation\s*\d*|slide\s*\d+|microsoft (word|powerpoint|excel)\b.*)$"
    r"|^(\S+\s+){0,3}\S*power\s*point\S*(\s+\S+){0,3}$", re.I)

_BULLETS = re.compile(r"[-]|^[\s•▪●◦·■□✓➢*\-–—>]+")
# Questions, sentences and code/command lines are not names. "#" only counts after a digit or ")",
# so "C#" survives while "R1#" and "(config)#" do not.
_NOT_A_NAME = re.compile(r"\?$|^(\S+\s+){3,}.*\.$|[<>{};=$]|[\d)]#"
                         r"|^[A-Z]{2,6}-?\d{3,6}$|\b\d{1,3}(\.\d{1,3}){3}\b|^[\"“']")  # codes, IPs, quoted data
_ORGANISATION = re.compile(
    r"\b(university|faculty|department|school|college|institute)\s+of\b"
    r"|\b(university|college|institute|school)$|^(the\s+)?(university|faculty|department)\b", re.I)
_HONORIFIC = re.compile(r"^(?i:dr|prof|professor|mr|mrs|ms|miss|daw|sir)\.?\s+\S|^U\s+[A-Z]")
_ROLE = re.compile(r"\b(lecturer|presented by|prepared by|submitted by|supervised by|instructor|tutor)\b", re.I)
_ROLE_ONLY = re.compile(r"^\W*(lecturer|presented by|prepared by|submitted by|supervised by|instructor|tutor"
                        r"|(associate |assistant )?professor)\W*$", re.I)
GENERIC_SECTIONS = {"outline", "contents", "table of contents", "introduction", "summary", "conclusion",
                    "conclusions", "references", "exercises", "exercise", "quiz", "quizzes", "questions", "answers",
                    "agenda", "objectives", "example", "examples", "solution", "solutions", "output",
                    "expected output", "sample output", "advantages", "disadvantages"}
_CONNECTOR_END = re.compile(
    r"(\b(and|of|the|to|for|with|a|an|in|on|or|by|from|at|as|into|than|that|which)|,)$", re.I)
_SENTENCE_VERB = re.compile(r"\s(is|are|was|were)\s", re.I)
_TERMINAL = (".", ":", "?", "!", ";")
_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with", "vs"}
_EQUIVALENTS = [(re.compile(r"\s*&\s*"), " and ")]  # explicit list; punctuation otherwise significant


@dataclass
class Evidence:
    source: str
    pages: list = field(default_factory=list)


@dataclass
class Suggestion:
    name: str
    score: int
    evidence: list
    demoted: str | None = None  # "person", "institution" or "repeated": never in the top three, only under "More"


@dataclass
class Analysis:
    suggestions: list
    instance_markers: list   # [{"text", "source"}]
    mentions: list           # [{"text", "source", "page"}] -- internal only, never shown in logs
    unit: str = "page"       # what evidence "pages" count: page | slide | block
    analyzer_version: str = ANALYZER_VERSION

    def to_dict(self):
        return asdict(self)


def is_organisation_line(name):
    return bool(_ORGANISATION.search(name))


def is_boilerplate_title(value):
    return bool(_BOILERPLATE.match(value))


def title_case(name):
    """Title Case for display, keeping acronyms and words with symbols, digits or inner capitals as they are."""
    words = name.split()
    shouting = sum(w.isupper() for w in words) == len(words) and len(words) > 1  # the whole line is in capitals
    out = []
    for i, w in enumerate(words):
        core = w.strip("()[]\"'.,:;")
        if i and core.lower() in _SMALL_WORDS:
            out.append(w.lower())
        elif shouting and (len(core) <= 3 or not core.isalpha()):
            out.append(w)                                      # OSI, TCP/IP, C++ in an all-caps line
        elif shouting:
            out.append(w[:1].upper() + w[1:].lower())
        elif (core.isupper() and len(core) > 1) or not core.isalpha() or any(c.isupper() for c in core[1:]):
            out.append(w)                                      # OSI, C++, IPv4, TCP/IP, JavaScript
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def _join_wrapped(lines):
    """Cover lines wrapped mid-sentence, joined: a line ending in a connecting word or a comma, or followed by a
    line that starts in lowercase, continues on the next line."""
    out = []
    for line in lines:
        if out and not out[-1].rstrip().endswith(_TERMINAL) and (
                _CONNECTOR_END.search(out[-1].rstrip()) or line[:1].islower()):
            out[-1] = out[-1].rstrip() + " " + line.lstrip()
        else:
            out.append(line)
    return out


def name_key(name):
    """Normalized form for equality checks: case and whitespace, plus the explicit equivalence list.
    Equal keys are a candidate match, never proof."""
    s = name
    for pat, rep in _EQUIVALENTS:
        s = pat.sub(rep, s)
    return " ".join(s.split()).casefold()


def _unbalanced(s):
    return any(s.count(a) != s.count(b) for a, b in ("()", "[]", "{}")) or s.count('"') % 2 == 1


def top_names(suggestions, n=3):
    """The top suggestions: never people's names or institution lines (Suggestion objects or stored dicts)."""
    demoted = lambda s: s.get("demoted") if isinstance(s, dict) else s.demoted
    return [s for s in suggestions if not demoted(s)][:n]


def _people(lines, author):
    """Keys of first-page lines that are people's names: next to a role word, or the role line itself."""
    keys = set()
    for i, line in enumerate(lines):
        if _ROLE_ONLY.match(line):  # "Presented by" / "Lecturer" alone: the neighbouring lines are the person
            keys.update(name_key(l) for l in lines[max(0, i - 1):i + 2] if l is not line)
        elif _ROLE.search(line):
            keys.add(name_key(line))
    return keys


def _is_person(name, people, author):
    key = name_key(name)
    a = name_key(author) if author else ""
    return bool(key in people or _HONORIFIC.match(name)
                or (a and (key == a or (len(a.split()) > 1 and a in key) or (len(key.split()) > 1 and key in a))))


def _clean(text, source, markers):
    """Strip bullets and instance identifiers; return a candidate name or None."""
    s = " ".join(_BULLETS.sub(" ", text).split())
    if _NOT_A_NAME.search(s):
        return None
    for m in _INSTANCE.finditer(s):
        markers.append({"text": m.group(0).strip(), "source": source})
    s = _INSTANCE.sub(" ", s)
    s = _EDGE_NUMBER.sub(" ", " ".join(s.split()))
    if _CONNECTOR_END.search(s.rstrip(" -–—:;.()[]_")) or _SENTENCE_VERB.search(f" {s} "):
        return None  # a cut-off fragment or a sentence, not a name
    if _unbalanced(s) or _ROLE_ONLY.match(s):
        return None  # a stray bracket or quote marks a fragment; a role word alone ("Lecturer") is a label
    s = " ".join(s.strip(" -–—:;,.()[]_").split())
    s = " ".join(_EDGE_NUMBER.sub(" ", s).strip(" -–—:;,.()[]_").split())  # "L2-1 System ..." -> "System ..."
    if _unbalanced(s) or s.casefold().strip(" .:") in GENERIC_SECTIONS:
        return None  # trimming can take one half of a pair: "(Networking) Basics"
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2 or len(s) > MAX_NAME_CHARS or len(s.split()) > MAX_NAME_WORDS:
        return None
    # ponytail: a lowercase start marks a body fragment ("network", "ports using ..."); titles rarely start lowercase.
    if letters[0].islower() or _NOT_A_NAME.search(s):  # again: trimming can leave only a code ("ABC-1234 L2")
        return None
    return s


def analyze(record, file_name):
    found = {}  # key -> Suggestion, insertion order = first seen
    markers, mentions = [], []

    def add(text, source, pages=()):
        name = _clean(text, source, markers)
        if not name:
            return
        key = name_key(name)
        s = found.setdefault(key, Suggestion(title_case(name), 0, []))
        if source in [e.source for e in s.evidence]:
            return
        s.evidence.append(Evidence(source, list(pages)))
        s.score += WEIGHTS[source]

    in_mention_block, taken = False, 0
    cover = _join_wrapped(record.first_page_lines)
    author = " ".join(str(record.metadata.get("author") or "").split())
    people = _people(cover, author)
    limit = FLOW_START_LINES if record.unit == "block" else FIRST_PAGE_LINES
    outline = sum(bool(_LIST_ITEM.match(l)) for l in cover) >= 2  # a numbered list on the cover is its contents
    for line in cover:
        if outline and _LIST_ITEM.match(line):
            continue
        if _MENTION_HEADING.match(line):
            # ponytail: a mention heading covers the rest of page 1; per-block scoping when layout is recorded.
            in_mention_block = True
        if in_mention_block or _MENTION_LINE.match(line):
            mentions.append({"text": line, "source": "first_page", "page": 1})
            continue
        if taken < limit and _clean(line, "first_page", []):
            add(line, "first_page", [1])
            taken += 1
        else:
            _clean(line, "first_page", markers)  # still record instance markers such as "Lecture -9"

    # A title that exists only inside a picture on the cover or title slide (cleaned OCR text; weighs less).
    # Two real words at least, and not a piece of a line already found: OCR also reads fragments of native text.
    if record.unit != "block" and record.units and record.units[0].ocr_text:
        native = list(found)
        for line in record.units[0].ocr_text.splitlines()[:limit]:
            name = _clean(line, "first_page_ocr", []) or ""
            words = sum(len(w) >= 3 and w.isalpha() for w in name.split())
            if words >= 2 and not any(name_key(name) in k for k in native):
                add(line, "first_page_ocr", [1])

    template_keys = set()
    for t in record.template_lines:
        template_keys.add(t["example"])
        add(t["example"], "template", t["pages"])
    for r in record.recurring_lines:
        if r["line"] not in template_keys and not _MENTION_LINE.match(r["line"]):
            add(r["line"], "recurring", r["pages"])
    for r in record.running_lines:
        if not _MENTION_LINE.match(r["line"]):
            add(r["line"], "running")

    for field_name, source in (("title", "metadata_title"), ("subject", "metadata_subject")):
        value = " ".join(str(record.metadata.get(field_name) or "").split())
        if value and not is_boilerplate_title(value):
            add(value, source)

    stem = Path(file_name).stem.replace("_", " ")
    stem = re.sub(r"[()\[\]{}]", " ", stem)
    stem = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", stem)
    # The file name never suggests a category (decision record B1). It only supports a name the content already
    # gave; its instance markers ("L2", "Lecture 5") are still recorded.
    if name_key(_clean(stem, "filename", markers) or "") in found:
        add(stem, "filename")

    def mark(s):
        s.demoted = ("person" if _is_person(s.name, people, author)
                     else "institution" if is_organisation_line(s.name)
                     else "repeated" if [e.source for e in s.evidence] == ["recurring"] else None)

    for s in found.values():
        mark(s)
    qualifies = [s for s in found.values() if not s.demoted and any(e.source != "filename" for e in s.evidence)]
    if not qualifies:  # nothing on the cover, in headers or in the metadata: the text's key phrases instead
        from classifile.analysis.summary import keyphrases
        text = "\n".join(t for u in record.units for t in (u.text, u.ocr_text) if t)  # OCR text is already cleaned
        taken, phrases = 0, keyphrases(text, 12)
        for lo in (PREFERRED_WORDS[0], 1):  # 2-5 word phrases first; single words only when there are none
            for k in phrases:
                if taken < KEYPHRASE_SUGGESTIONS and lo <= len(k["phrase"].split()) <= PREFERRED_WORDS[1]:
                    before = len(found)
                    add(k["phrase"].capitalize(), "keyphrase")
                    taken += len(found) > before
            for s in found.values():
                mark(s)
            if taken:
                break

    def rank(s):
        n = len(s.name.split())
        preferred = PREFERRED_WORDS[0] <= n <= PREFERRED_WORDS[1]
        # stable: ties keep first-seen order; people's names and institution lines come after everything else
        return s.demoted is not None, -(s.score - (0 if preferred else 1))

    ranked = sorted(found.values(), key=rank)
    return Analysis(ranked[:MAX_SUGGESTIONS], _dedupe(markers), mentions, record.unit)


def _dedupe(markers):
    return [dict(t) for t in dict.fromkeys(tuple(m.items()) for m in markers)]
