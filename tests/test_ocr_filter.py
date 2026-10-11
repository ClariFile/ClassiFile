"""The summary ignores OCR junk from photos and decorations. Synthetic pictures only."""
import random

import pymupdf
import pytest

from classifile.reader.ocr import _wordlike, usable_ocr_text
from classifile.reader import ocr


@pytest.mark.parametrize("token, ok", [
    ("Translation", True), ("router", True), ("TCP", True), ("APIs", True), ("IPv4", True), ("192.168.1.1", True),
    ("10GB", True), ("well-known", True), ("of", True), ("NetworkSih", True), ("audio", False),
    ("LSSo", False), ("ooSSoo", False), ("oeLe", False), ("eeeeo-ee", False), ("oe2aoo8", False),
    ("oe", False), ("|", False), ("ooo", False), ("Peoeee", False),
])
def test_wordlike(token, ok):
    assert _wordlike(token) is ok


def test_junk_lines_are_dropped_and_real_lines_kept():
    assert usable_ocr_text("Lo\n|\n7\nne\nmm *\nNetwork Address Translation table\n_'\nHp Soa") == \
        "Network Address Translation table"
    assert usable_ocr_text("eeoe oo\nooeeoo\naeeoeoeeeoooo\n2oFeeeoea.a") == ""
    assert usable_ocr_text("") == "" and usable_ocr_text(None) == ""
    # Stray bars and dots do not sink a real line; slash-joined words count as words.
    assert usable_ocr_text("| think that ...\n| believe/suppose that...\n| a\n_ + _ +") == \
        "| think that ...\n| believe/suppose that..."


def _page(draw, w=900, h=600):
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    draw(page)
    return page.get_pixmap(dpi=150)


def _shapes(page, rng):
    for _ in range(60):
        x, y = rng.uniform(0, 850), rng.uniform(0, 550)
        page.draw_rect(pymupdf.Rect(x, y, x + rng.uniform(5, 120), y + rng.uniform(5, 80)),
                       color=(rng.random(),) * 3, fill=(rng.random(), rng.random(), rng.random()))


@pytest.mark.ocr
def test_real_ocr_on_synthetic_pictures():
    rng = random.Random(7)
    folder = ocr.tessdata()
    if folder is None:
        pytest.skip("Tesseract not installed")
    noise = pymupdf.Pixmap(pymupdf.csRGB, 800, 600, bytes(rng.getrandbits(8) for _ in range(800 * 600 * 3)), False)
    lines = _page(lambda p: [p.draw_line((rng.uniform(0, 900), rng.uniform(0, 600)),
                                         (rng.uniform(0, 900), rng.uniform(0, 600)), width=rng.uniform(0.5, 4))
                             for _ in range(80)])
    for junk in (noise, lines, _page(lambda p: _shapes(p, rng))):
        raw = ocr.ocr_pixmap(junk, folder)
        # ponytail: a token rule cannot tell every all-caps fragment from a word; almost all junk must go.
        assert len(usable_ocr_text(raw).split()) <= max(2, 0.25 * len(raw.split()))

    def text_over_shapes(page):
        _shapes(page, rng)
        page.insert_text((60, 300), "Network Address Translation table", fontsize=30)

    assert "Translation" in usable_ocr_text(ocr.ocr_pixmap(_page(text_over_shapes), folder))
    prose = "The router forwards packets between networks. Each interface has an IP address. " * 3
    raw = ocr.ocr_pixmap(_page(lambda p: p.insert_textbox(pymupdf.Rect(40, 40, 860, 560), prose, fontsize=18)), folder)
    assert len(usable_ocr_text(raw).split()) >= 0.9 * len(raw.split())
