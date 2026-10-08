"""Checks on the user's real files in data/real-samples (not committed; skipped when absent).

Copies only; assertions are structural and never quote document text.
"""
import shutil
from collections import Counter
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from conftest import ROOT, source_state
from classifile.organizer import read_and_analyze
from classifile.reader import READERS
from classifile.reader import odt as R
from classifile.reader import ooxml as O

REAL = ROOT / "data" / "real-samples"
FILES = sorted(p for p in REAL.rglob("*") if p.suffix.lower() in READERS) if REAL.is_dir() else []
# Image titles/descriptions (alt text) are not visible body text; Word often generates them.
NOT_BODY = R._SKIP | {R.SVG + "title", R.SVG + "desc"}


# OOXML text runs (DrawingML, WordprocessingML, Office Math) outside skipped subtrees.
OOXML_TEXT = {O.A + "t", O.W + "t", O.M + "t"}
OOXML_SKIP = {O.MC + "Fallback", O.W + "del", O.W + "moveFrom", O.W + "instrText", O.W + "delInstrText"}


def _ooxml_chars(el):
    if el.tag in OOXML_SKIP:
        return 0
    n = len("".join((el.text or "").split())) if el.tag in OOXML_TEXT else 0
    return n + sum(_ooxml_chars(c) for c in el)


def _visible_chars(el):
    if el.tag in NOT_BODY:
        return 0
    n = len("".join((el.text or "").split()))
    return n + sum(_visible_chars(c) + len("".join((c.tail or "").split())) for c in el)


@pytest.fixture(scope="module")
def copies(tmp_path_factory):
    before = source_state(REAL)
    dest = tmp_path_factory.mktemp("real")
    out = []
    for i, p in enumerate(FILES):
        out.append(dest / f"{i:02d}{p.suffix.lower()}")
        shutil.copyfile(p, out[-1])
    yield out
    assert source_state(REAL) == before


@pytest.mark.skipif(not FILES, reason="no real samples in data/real-samples")
def test_real_files_read_and_body_text_is_complete(copies):
    for path in copies:
        result, analysis, summary = read_and_analyze(path)
        assert result.status == "ok", (path.name, result.reason)
        assert summary["summary_version"] and analysis.unit == result.record.unit
        if path.suffix == ".odt":
            body = ET.fromstring(zipfile.ZipFile(path).read("content.xml")).find(f"{R.OFFICE}body/{R.OFFICE}text")
            assert sum(u.native_chars for u in result.record.units) == _visible_chars(body), path.name
        elif path.suffix == ".docx":
            z = zipfile.ZipFile(path)
            raw = sum(_ooxml_chars(ET.fromstring(z.read(n))) for n in ("word/document.xml", "word/footnotes.xml",
                                                                         "word/endnotes.xml") if n in z.namelist())
            assert sum(u.native_chars for u in result.record.units) == raw, path.name
        elif path.suffix == ".pptx":
            z = zipfile.ZipFile(path)
            pres = ET.fromstring(z.read("ppt/presentation.xml"))
            slide_rels = O.rels(z, "ppt/presentation.xml")
            names = [slide_rels[s.get(O.R + "id")][1] for s in pres.iter(O.P + "sldId")]
            raw = [_ooxml_chars(ET.fromstring(z.read(n))) for n in names]
            assert [u.native_chars for u in result.record.units] == raw, path.name


@pytest.mark.skipif(not FILES, reason="no real samples in data/real-samples")
def test_real_files_layout_matches_text(copies):
    for path in copies:
        for u in read_and_analyze(path)[0].record.units:
            layout = [l["text"] for b in u.layout["blocks"] for l in b["lines"]]
            if path.suffix == ".pdf":
                # PyMuPDF's plain-text and structured outputs can differ by a stray character (seen once: a digit
                # in plain text only); the layout must match the page text otherwise.
                a, b = Counter("".join(u.text.split())), Counter("".join("".join(layout).split()))
                assert sum(((a - b) + (b - a)).values()) <= max(2, sum(a.values()) // 100), (path.name, u.index)
            else:
                assert "\n".join(layout) == u.text, (path.name, u.index)
