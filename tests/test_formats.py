"""DOCX, PPTX and ODT readers on synthetic packages (tests/office_fixtures.py). Real-file checks are separate."""
import zipfile
from dataclasses import asdict

import pytest

from office_fixtures import ODT_BODY, make_docx, make_odt, make_pptx
from classifile.analysis.candidates import analyze
from classifile.reader import read_document

NEVER = ("Obsolete clause", "Reviewer comment", "PAGE", "Contents entry", "Click to edit")


def _all_text(rec):
    return "\n".join([u.text + (u.notes or "") for u in rec.units] + [r["line"] for r in rec.running_lines]
                     + rec.first_page_lines)


def _texts(rec):
    return [(u.kind, u.text) for u in rec.units]


def test_docx(tmp_path):
    r = read_document(make_docx(tmp_path / "a.docx"))
    rec = r.record
    assert r.status == "ok" and (rec.format, rec.unit, rec.reader_version) == ("docx", "block", "docx-7")
    assert _texts(rec)[:6] == [
        ("title", "Database Systems Handbook"),
        ("heading", "Introduction"),
        ("paragraph", "Keep this sentence. Inserted words.7"),   # tracked deletion and field code skipped
        ("paragraph", "Anchor paragraph\nText box about normalization"),  # once: the VML fallback is skipped
        ("paragraph", "Grouped shape one\nGrouped shape two"),
        ("table", "Cell A1\tCell B1 Nested cell\nCell A2\tCell B2"),
    ]
    assert rec.units[1].level == 1
    picture = rec.units[6]
    assert picture.text == "" and picture.suspected_unread and 0.30 <= picture.nonrepeated_image_area < 0.35
    assert _texts(rec)[7:] == [("heading", "Second Chapter"), ("paragraph", "Content control text"),
                               ("paragraph", "Energy: E=m c 2"), ("footnotes", "Footnote about normal forms.")]
    assert rec.running_lines == [{"line": "Database Systems Handbook - running header", "part": "header"},
                                 {"line": "Course DBS-2041 footer", "part": "footer"}]
    # Opening lines stop at the explicit page break, before the picture and "Second Chapter".
    assert rec.first_page_lines[0] == "Database Systems Handbook" and rec.first_page_lines[-1] == "Cell A2 Cell B2"
    assert rec.metadata["title"] == "Database Systems Handbook"
    assert not any(n in _all_text(rec) for n in NEVER)


def test_pptx(tmp_path):
    r = read_document(make_pptx(tmp_path / "a.pptx"))
    rec = r.record
    assert r.status == "ok" and (rec.format, rec.unit, rec.unit_count) == ("pptx", "slide", 4)
    s1, s2, s3, s4 = rec.units
    assert s1.title == "Network Security Fundamentals" and s2.title == "Firewalls"
    for expected in ("Rule table cell one\tAllow", "Grouped label one", "Grouped label two", "SmartArt step one"):
        assert expected in s2.text
    assert s2.text.count("Alternate content text") == 1   # mc:Fallback skipped
    assert "x=y+1" in s2.text  # equation text from mc:Choice
    assert s2.notes == "Speaker note: explain stateful inspection"  # body placeholder only
    assert (s4.kind, s4.title) == ("hidden slide", "Backup slide")
    # The full-slide background is on 3 of 4 slides: repeated, so it does not count as unread content.
    assert s1.image_area == 1.0 and s1.nonrepeated_image_area == 0 and not s1.suspected_unread
    assert s3.suspected_unread and s3.nonrepeated_image_area == round(6000000 * 4500000 / (9144000 * 6858000), 4)
    assert "NSF course footer" in s1.text  # visible on the slide...
    assert "NSF course footer" not in rec.first_page_lines and not rec.template_lines  # ...but running text
    assert rec.running_lines == [{"line": "NSF course footer", "part": "footer"},
                                 {"line": "Layout brand text", "part": "layout"},
                                 {"line": "Network Security Fundamentals master text", "part": "master"}]
    assert not any(n in _all_text(rec) for n in NEVER)


def test_odt(tmp_path):
    r = read_document(make_odt(tmp_path / "a.odt"))
    rec = r.record
    assert r.status == "ok" and (rec.format, rec.unit, rec.reader_version) == ("odt", "block", "odt-6")
    assert _texts(rec) == [
        ("heading", "Database Systems Handbook"),
        ("paragraph", "Keep this  sentence.\tTabbed after note.Spanned end."),  # note body kept apart
        ("paragraph", "Anchor paragraph\nText box about normalization"),
        ("paragraph", "Grouped shape one\nGrouped shape two"),
        ("list", "First item\nNested item"),
        ("table", "Cell A1\tCell B1\nCell A2\tNested cell"),
        ("paragraph", ""),
        ("heading", "Second Chapter"),
        ("paragraph", "Forced page paragraph"),
        ("paragraph", "Section text"),
        ("footnotes", "Footnote about normal forms."),
    ]
    assert rec.units[6].suspected_unread and rec.units[6].image_area == round(35 / (8.5 * 11), 4)
    assert rec.first_page_lines[-1] == "Cell A2 Nested cell"  # stops at the soft page break
    assert [r["part"] for r in rec.running_lines] == ["header", "footer"]
    assert rec.metadata["keywords"] == "databases, SQL"
    assert not any(n in _all_text(rec) for n in NEVER)


def test_odt_style_page_break_ends_opening_lines(tmp_path):
    body = '<text:p>Cover line</text:p><text:p text:style-name="P1">Next page</text:p>'
    rec = read_document(make_odt(tmp_path / "b.odt", body=body)).record
    assert rec.first_page_lines == ["Cover line"]


def test_records_are_reproducible(tmp_path):
    for make, name in ((make_docx, "a.docx"), (make_pptx, "a.pptx"), (make_odt, "a.odt")):
        path = make(tmp_path / name)
        assert asdict(read_document(path).record) == asdict(read_document(path).record)


def test_analysis_uses_running_lines_and_unit(tmp_path):
    rec = read_document(make_pptx(tmp_path / "a.pptx")).record
    a = analyze(rec, "a.pptx")
    by_name = {s.name: [e.source for e in s.evidence] for s in a.suggestions}
    assert by_name["NSF Course Footer"] == ["running"]
    assert by_name["Network Security Fundamentals"] == ["first_page"]
    assert a.unit == "slide"


def _zip(path, parts):
    with zipfile.ZipFile(path, "x") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


SECRET = "Secret body text"


@pytest.mark.parametrize("name, data, reason", [
    ("corrupt.docx", f"PK not a zip {SECRET}".encode(), "corrupt or unreadable DOCX"),
    ("enc.pptx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + SECRET.encode(), "encrypted or legacy-format Office file"),
    ("nobody.docx", {"word/other.xml": "<x/>"}, "required part missing"),
    ("doctype.docx", {"word/document.xml": f'<!DOCTYPE x [<!ENTITY e "{SECRET}">]><x>&e;</x>'},
     "XML part declares a DOCTYPE"),
    ("bad.odt", {"content.xml": f"<unclosed>{SECRET}"}, "malformed XML part"),
    ("sheet.odt", {"mimetype": "application/vnd.oasis.opendocument.spreadsheet"}, "not an ODF text document"),
    ("noslides.pptx", {"ppt/presentation.xml": '<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
                                               'presentationml/2006/main"/>'}, "PPTX has no slides"),
])
def test_failures_have_fixed_reasons_without_text(tmp_path, name, data, reason):
    path = tmp_path / name
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        _zip(path, data)
    r = read_document(path)
    assert (r.status, r.reason, r.record) == ("failed", reason, None)
    assert r.sha256 and SECRET not in r.reason


def test_encrypted_odt(tmp_path):
    r = read_document(make_odt(tmp_path / "e.odt", body=ODT_BODY, manifest_extra="<manifest:encryption-data/>"))
    assert (r.status, r.reason) == ("failed", "encrypted ODT")


def test_units_list_their_pictures(tmp_path):
    from classifile.reader.common import package_part

    docx = read_document(make_docx(tmp_path / "a.docx")).record
    assert [u.pictures for u in docx.units if u.pictures] == [["word/media/image1.png"]]
    pptx = read_document(make_pptx(tmp_path / "a.pptx")).record
    assert pptx.units[0].pictures == ["ppt/media/bg.png"] and pptx.units[2].pictures == ["ppt/media/image1.png"]
    odt = read_document(make_odt(tmp_path / "a.odt")).record
    assert [u.pictures for u in odt.units if u.pictures] == [["Pictures/a.png"]]
    assert package_part(tmp_path / "a.odt", "Pictures/a.png").startswith(b"\x89PNG")


def _layout_text(u):
    return "\n".join(l["text"] for b in u.layout["blocks"] for l in b["lines"])


def test_layout_keeps_lines_blocks_positions_and_sizes(tmp_path):
    docx = read_document(make_docx(tmp_path / "a.docx")).record
    sizes = {u.text.split("\n")[0]: {l["size"] for b in u.layout["blocks"] for l in b["lines"]} for u in docx.units}
    assert sizes["Database Systems Handbook"] == {28.0}         # Title style
    assert sizes["Keep this sentence. Inserted words.7"] == {16.0}  # direct run formatting
    assert sizes["Content control text"] == {11.0}              # document default
    assert docx.units[0].layout["blocks"][0]["bbox"] is None    # DOCX stores no positions
    pptx = read_document(make_pptx(tmp_path / "a.pptx")).record
    s2 = pptx.units[1].layout
    assert (s2["width"], s2["height"]) == (720.0, 540.0)
    assert s2["blocks"][0]["lines"] == [{"text": "Firewalls", "bbox": None, "size": 44.0}]
    group = [b for b in s2["blocks"] if b["lines"][0]["text"] == "Grouped label one"][0]
    assert group["bbox"] == [0.0, 0.0, 78.7, 39.4]              # child space scaled by the group transform
    odt = read_document(make_odt(tmp_path / "a.odt")).record
    assert {l["size"] for l in odt.units[0].layout["blocks"][0]["lines"]} == {18.0}  # via the parent style
    assert {l["size"] for l in odt.units[2].layout["blocks"][0]["lines"]} == {12.0, None}  # default; text box


def test_layout_lines_rebuild_the_categorizer_text_exactly(tmp_path):
    for make, name in ((make_docx, "a.docx"), (make_pptx, "a.pptx"), (make_odt, "a.odt")):
        for u in read_document(make(tmp_path / name)).record.units:
            assert _layout_text(u) == u.text, (name, u.index)
