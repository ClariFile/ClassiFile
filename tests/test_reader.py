from dataclasses import asdict

import pymupdf
import pytest

from classifile.reader import RECORD_VERSION, read_pdf
from classifile.reader import common as reader_common
from conftest import EXPECT, SAMPLE  # noqa: E402

FIXED_REASONS = {
    "source could not be opened", "empty file", "corrupt or unreadable PDF", "encrypted PDF", "PDF has no pages",
    "source changed during reading", "too large",
}


def test_reproducible_record(samples):
    a, b = read_pdf(samples / SAMPLE["S1"]), read_pdf(samples / SAMPLE["S1"])
    assert a.status == "ok" and asdict(a.record) == asdict(b.record)
    assert a.record.record_version == RECORD_VERSION and a.record.reader_version


def test_columns_stay_separate_lecture7_page9(samples):
    page9 = read_pdf(samples / SAMPLE["S3"]).record.units[8]
    assert "global $hello" in page9.text and "function hello()" in page9.text
    assert not [l for l in page9.text.splitlines() if "global $hello" in l and "function hello()" in l]


def test_template_lines_42(samples):
    rec = read_pdf(samples / SAMPLE["S2"]).record
    assert EXPECT["S2.template_line"] in [t["line"].casefold() for t in rec.template_lines]


def test_suspected_unread_l2_page8(samples):
    p = read_pdf(samples / SAMPLE["S4"]).record.units[7]
    assert p.suspected_unread and p.suspect_rule == reader_common.SUSPECT_RULE


def test_l2_page20_former_known_miss_is_flagged(samples):
    # The first rule (< 300 native chars and >= 30% picture area) missed this page: the addressing diagram's
    # text exists only inside the picture on a text-heavy page. The E8 rule flags any picture >= 5% of the page.
    p = read_pdf(samples / SAMPLE["S4"]).record.units[19]
    assert p.suspected_unread and p.native_chars >= 300


def test_page_observations_present(samples):
    rec = read_pdf(samples / SAMPLE["S2"]).record
    assert rec.unit_count == len(rec.units) == 17
    assert rec.metadata["title"] == "PowerPoint 프레젠테이션"
    p = rec.units[3]
    assert p.index == 4 and p.kind == "page" and p.native_chars > 0 and 0 <= p.text_area <= 1
    assert p.nonrepeated_image_area <= p.image_area <= 1
    assert rec.first_page_lines and all(r["pages"] == sorted(r["pages"]) for r in rec.recurring_lines)


def _pdf(path, **save):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Secret body text")
    doc.save(path, **save)
    return path


def test_failures_have_fixed_reasons_without_text(tmp_path, monkeypatch):
    (tmp_path / "empty.pdf").write_bytes(b"")
    (tmp_path / "corrupt.pdf").write_bytes(b"%PDF-1.7 Secret body text garbage")
    enc = _pdf(tmp_path / "enc.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    results = {
        "empty": read_pdf(tmp_path / "empty.pdf"),
        "corrupt": read_pdf(tmp_path / "corrupt.pdf"),
        "encrypted": read_pdf(enc),
        "missing": read_pdf(tmp_path / "nope.pdf"),
        "large": read_pdf(_pdf(tmp_path / "ok.pdf"), max_bytes=10),
    }
    assert results["encrypted"].reason == "encrypted PDF"
    assert results["large"].status == "pending" and results["large"].reason == "too large"
    assert results["large"].sha256  # still a proper snapshot; never a rejection or deletion
    for name, r in results.items():
        assert r.reason in FIXED_REASONS and "Secret" not in r.reason, name
        assert r.status in ("failed", "pending") and r.record is None

    monkeypatch.setattr(reader_common, "sha256_file", lambda p: "0" * 64)
    r = read_pdf(tmp_path / "ok.pdf")
    assert (r.status, r.reason, r.record) == ("failed", "source changed during reading", None)


def test_long_documents_are_read(tmp_path):
    doc = pymupdf.open()
    for i in range(600):
        doc.new_page().insert_text((72, 72), f"Page {i}")
    doc.save(tmp_path / "long.pdf")
    r = read_pdf(tmp_path / "long.pdf")
    assert r.status == "ok" and r.record.unit_count == 600
