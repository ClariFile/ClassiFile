from office_fixtures import make_docx, make_pptx
from classifile.analysis.candidates import analyze
from classifile.analysis.summary import LONG_DOC_CHARS, summarize
from classifile.organizer import read_and_analyze
from classifile.reader import DocumentRecord, UnitRecord


def _summary(path):
    return read_and_analyze(path)[2]


def test_docx_summary(tmp_path):
    s = _summary(make_docx(tmp_path / "handbook.docx"))
    assert s["title"] == {"text": "Database Systems Handbook", "source": "metadata_title"}
    assert {"label": "manual", "cue": "handbook", "source": "title"} in s["purpose"]
    assert [o["text"] for o in s["outline"]] == ["Database Systems Handbook", "Introduction", "Second Chapter"]
    assert s["flags"]["suspected_unread_units"] == [7] and s["flags"]["ocr"] == {"disabled": [7]}
    assert s["flags"]["unresolved_gaps"] == [7]
    assert s["self_description_candidates"][0]["name"] == "Database Systems Handbook"
    assert s["keyphrases"] and all(d["unit"] >= 1 for d in s["digest"])
    assert "Obsolete" not in str(s) and s["sections"] == []


def test_pptx_summary_uses_slide_titles_and_notes(tmp_path):
    s = _summary(make_pptx(tmp_path / "security.pptx"))
    assert s["title"] == {"text": "Network Security Fundamentals", "source": "slide_title"}  # metadata is boilerplate
    assert [o["text"] for o in s["outline"]] == ["Network Security Fundamentals", "Firewalls", "Backup slide"]
    assert any("stateful inspection" in k["phrase"] for k in s["keyphrases"])  # speaker notes count


def _record(units):
    return DocumentRecord(format="docx", unit="block", unit_count=len(units), metadata={}, template_lines=[],
                          recurring_lines=[], running_lines=[], first_page_lines=[], units=units)


def _unit(i, text, kind="paragraph", level=None):
    return UnitRecord(index=i, kind=kind, level=level, text=text, native_chars=len(text), text_area=None,
                      image_area=None, nonrepeated_image_area=None, suspected_unread=False, suspect_rule=None)


def test_long_documents_get_sections_at_headings():
    para = "Relational algebra defines selection and projection over relations in the database. " * 40
    units, i = [], 0
    for chapter in ("Storage", "Indexing", "Transactions", "Recovery"):
        i += 1
        units.append(_unit(i, chapter, "heading", 1))
        for _ in range(4):
            i += 1
            units.append(_unit(i, para))
    rec = _record(units)
    assert sum(len(u.text) for u in units) > LONG_DOC_CHARS
    s = summarize(rec, analyze(rec, "book.docx"), "book.docx")
    assert [sec["heading"] for sec in s["sections"]] == ["Storage", "Indexing", "Transactions", "Recovery"]
    assert s["sections"][1]["units"] == [6, 10]
    assert len({d["text"] for d in s["digest"]}) == len(s["digest"])  # no repeated sentences


def test_language_flags():
    burmese = _record([_unit(1, "မြန်မာဘာသာစကား စာရွက်စာတမ်း " * 20)])
    assert summarize(burmese, None, "x.docx")["flags"]["language"]["flag"] == "non_latin_script"
    german = _record([_unit(1, "Datenbanksysteme speichern Relationen und Tabellen effizient " * 10)])
    assert summarize(german, None, "x.docx")["flags"]["language"]["flag"] == "possibly_not_english"
    english = _record([_unit(1, "The database stores the tables and the indexes that are used by the queries. " * 5)])
    assert "language" not in summarize(english, None, "x.docx")["flags"]


def test_summary_is_deterministic(tmp_path):
    path = make_docx(tmp_path / "a.docx")
    assert _summary(path) == _summary(path)


def test_untitled_slides_use_their_first_line_in_the_outline(tmp_path):
    rec = read_and_analyze(make_pptx(tmp_path / "s.pptx"))[0].record
    rec.units[1].title = None  # as in decks built from plain text boxes
    s = summarize(rec, analyze(rec, "s.pptx"), "s.pptx")
    assert [o["text"] for o in s["outline"]][1] == "Firewalls"
