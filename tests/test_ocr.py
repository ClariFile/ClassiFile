"""Selective OCR (B3/E8). These run real Tesseract OCR; they assert structure and words from synthetic images only."""
import shutil

import pymupdf
import pytest

from office_fixtures import IMAGE_TEXT, make_docx, make_odt, make_pptx
from classifile.organizer import Organizer, read_and_analyze
from classifile.reader import ocr, read_document
from conftest import EXPECT, SAMPLE  # noqa: E402

pytestmark = pytest.mark.ocr


def _picture_page(doc):
    page = doc.new_page(width=600, height=200)  # the picture's own proportions, so it fills the page
    page.insert_image(page.rect, stream=IMAGE_TEXT)


def _scanned_pdf(path):
    """Page 1: native text only. Page 2: the words exist only inside a full-page picture."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Native text page with plenty of characters. " * 10)
    _picture_page(doc)
    doc.save(path)
    return path


def _has_words(text):
    return text and "diagram" in text.casefold() and "legend" in text.casefold()


def test_pdf_ocr_reads_only_suspected_pages(tmp_path):
    rec = read_document(_scanned_pdf(tmp_path / "scan.pdf")).record
    native, scanned = rec.units
    assert (native.suspected_unread, native.ocr_status, native.ocr_text) == (False, None, None)
    assert scanned.suspected_unread and scanned.ocr_status == "done" and _has_words(scanned.ocr_text)
    assert scanned.text.strip() == ""  # OCR text is kept apart from native text
    assert rec.ocr["available"] and rec.ocr["language"] == "eng"


@pytest.mark.parametrize("make, name, unit", [(make_docx, "a.docx", 7), (make_pptx, "a.pptx", 3), (make_odt, "a.odt", 7)])
def test_office_ocr_reads_pictures_of_suspected_units(tmp_path, make, name, unit):
    rec = read_document(make(tmp_path / name)).record
    flagged = [u for u in rec.units if u.ocr_status]
    assert [u.index for u in flagged] == [unit]
    assert flagged[0].ocr_status == "done" and _has_words(flagged[0].ocr_text)


def test_unavailable_deferred_and_unreadable_images(tmp_path, monkeypatch):
    path = _scanned_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(ocr, "tessdata", lambda: None)
    r = read_document(path)
    assert r.status == "ok" and r.record.units[1].ocr_status == "unavailable" and not r.record.ocr["available"]
    monkeypatch.undo()
    monkeypatch.setattr(ocr, "OCR_BUDGET_SECONDS", -1)
    assert read_document(path).record.units[1].ocr_status == "deferred"
    monkeypatch.undo()
    emf_like = read_document(make_docx(tmp_path / "x.docx", image=b"not an image format MuPDF reads"))
    assert emf_like.status == "ok" and emf_like.record.units[6].ocr_status == "no_readable_image"


def test_sample_known_pages(samples):
    units = read_document(samples / SAMPLE["S4"]).record.units
    assert units[7].ocr_status == "done" and len("".join(units[7].ocr_text.split())) > 100   # page 8
    # Page 20, the first rule's documented miss (diagram text only inside a picture on a text-heavy page), is read.
    assert units[19].suspected_unread and units[19].ocr_status == "done"


def test_summary_and_catalog_carry_ocr(tmp_path, make_org):
    src = tmp_path / "src"
    src.mkdir()
    path = _scanned_pdf(src / "scan.pdf")
    result, analysis, summary = read_and_analyze(path)
    assert summary["flags"]["ocr"] == {"done": [2]} and summary["flags"]["unresolved_gaps"] == []
    assert any("diagram" in k["phrase"] for k in summary["keyphrases"])
    org = make_org()
    doc_id, _ = org.record(path, result, analysis, summary)
    row = org.catalog.one("SELECT ocr_status, ocr_text FROM extraction_units WHERE unit_index = 2")
    assert row["ocr_status"] == "done" and _has_words(row["ocr_text"])
    assert org.catalog.one("SELECT ocr_json FROM extractions")[0]


def test_single_page_scan_is_flagged_and_read(tmp_path):
    doc = pymupdf.open()
    _picture_page(doc)
    doc.save(tmp_path / "receipt.pdf")
    (unit,) = read_document(tmp_path / "receipt.pdf").record.units
    assert unit.suspected_unread and unit.ocr_status == "done" and _has_words(unit.ocr_text)


def test_photo_ocr_junk_stays_out_of_the_summary(tmp_path):
    import random

    from classifile.reader.ocr import PHOTO_MAX_FLAT_SHARE, flat_share

    rng = random.Random(7)
    photo = pymupdf.Pixmap(pymupdf.csRGB, 800, 600, bytes(rng.getrandbits(8) for _ in range(800 * 600 * 3)), False)
    assert flat_share(photo) < PHOTO_MAX_FLAT_SHARE  # continuous tone: photo-like
    native = "Holiday report on the network upgrade project. " * 6
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), native)
    page.insert_image(pymupdf.Rect(72, 200, 472, 500), pixmap=photo)
    doc.save(tmp_path / "photo.pdf")
    result, _, summary = read_and_analyze(tmp_path / "photo.pdf")
    unit = result.record.units[0]
    assert unit.suspected_unread and unit.ocr_status == "no_text" and unit.ocr_text is None
    assert unit.ocr_discarded_chars > 0 and summary["flags"]["ocr_text_discarded"] == [1]
    native_words = set(unit.text.casefold().replace(".", "").split())  # no keyphrase word may come from OCR
    assert {w for k in summary["keyphrases"] for w in k["phrase"].split()} <= native_words


def test_text_pictures_are_not_photo_like():
    from classifile.reader.ocr import PHOTO_MAX_FLAT_SHARE, flat_share

    doc = pymupdf.open()
    _picture_page(doc)
    assert flat_share(doc[0].get_pixmap(dpi=150)) > PHOTO_MAX_FLAT_SHARE


def test_ocr_layout_positions_lines_and_marks_kept(tmp_path):
    doc = pymupdf.open()
    _picture_page(doc)
    doc.save(tmp_path / "scan.pdf")
    (unit,) = read_document(tmp_path / "scan.pdf").record.units
    (pic,) = unit.ocr_layout
    assert pic["picture"] == 0 and all(abs(a - b) < 1 for a, b in zip(pic["region"], [0, 0, 600, 200]))  # points
    lines = [l for b in pic["blocks"] for l in b["lines"]]
    assert lines and all(0 <= v <= 1 for l in lines for v in l["bbox"]) and all(0 < l["size"] < 1 for l in lines)
    assert all(l["kept"] for l in lines if _has_words(l["text"]))


def test_a_picture_shown_twice_is_read_once(tmp_path, monkeypatch):
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page().insert_text((72, 72), "Native text page with plenty of characters. " * 10)
    _picture_page(doc)
    _picture_page(doc)
    doc.save(tmp_path / "twice.pdf")
    calls, real = [], ocr.ocr_pixmap
    monkeypatch.setattr(ocr, "ocr_pixmap", lambda *a, **k: calls.append(1) or real(*a, **k))
    units = read_document(tmp_path / "twice.pdf").record.units
    assert len(calls) == 1 and _has_words(units[4].ocr_text) and units[4].ocr_text == units[5].ocr_text
    assert units[4].ocr_layout[0]["blocks"][0] is not units[5].ocr_layout[0]["blocks"][0]  # each unit has its own
