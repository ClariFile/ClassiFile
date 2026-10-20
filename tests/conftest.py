import csv
import hashlib
import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "document-organizer-claude-handoff" / "claude-handoff" / "samples"
FIXTURE_MAP = ROOT / "data" / "fixtures.json"


class _Local(dict):
    """Values from the local fixture map; a placeholder when the map is missing (tests using them then skip)."""

    def __missing__(self, key):
        return f"missing-{key}"


def _fixture_map():
    """data/fixtures.json (not tracked) names the development files behind the neutral IDs used in tests, and
    holds the expected values that come from their content, so no file names or document text are committed:
    {"samples": {"S1": "<file name>", ...}, "expect": {"S1.cover_title": "...", ...}}"""
    try:
        return json.loads(FIXTURE_MAP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_MAP = _fixture_map()
# The six sample PDFs: S1 a 38-page lecture deck whose cover title and repeated course line differ; S2 a 17-page
# handout with a slide-software metadata title; S3 an 18-page lecture; S4 a 25-page lecture with image-based pages;
# S5 a 3-page lab guide; S6 a 7-page exercise sheet.
SAMPLE = _Local(_MAP.get("samples", {}))
EXPECT = _Local(_MAP.get("expect", {}))


def _blocked(*a, **k):
    raise RuntimeError("Network access attempted during tests")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


@pytest.fixture(autouse=True)
def ocr_off_unless_marked(request, monkeypatch):
    """OCR costs about 0.7 s per flagged page; only tests marked "ocr" run it. The setting reaches worker processes."""
    if "ocr" not in request.keywords:
        monkeypatch.setenv("CLASSIFILE_OCR", "off")


def _verified_samples():
    if not SAMPLES.is_dir() or not _MAP.get("samples"):
        pytest.skip("sample PDFs or data/fixtures.json not present")
    with open(SAMPLES / "inventory.csv", newline="", encoding="utf-8") as f:
        expected = {r["file"]: r["sha256"] for r in csv.DictReader(f)}
    for name, digest in expected.items():
        actual = hashlib.sha256((SAMPLES / name).read_bytes()).hexdigest()
        assert actual == digest, f"fixture hash mismatch: {name}"
    return expected


@pytest.fixture
def samples(tmp_path):
    """Copies of the six verified sample PDFs in a temp dir; the originals are never touched."""
    names = _verified_samples()
    dest = tmp_path / "samples"
    dest.mkdir()
    for name in names:
        shutil.copyfile(SAMPLES / name, dest / name)
    return dest


def alternate_streams(path):
    """Names of NTFS alternate data streams via FindFirstStreamW; None when not on Windows."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class FIND_STREAM_DATA(ctypes.Structure):
        _fields_ = [("StreamSize", ctypes.c_longlong), ("cStreamName", ctypes.c_wchar * (260 + 36))]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.FindFirstStreamW.restype = wintypes.HANDLE
    k32.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    k32.FindClose.argtypes = [wintypes.HANDLE]
    data = FIND_STREAM_DATA()
    h = k32.FindFirstStreamW(str(path), 0, ctypes.byref(data), 0)
    if h == wintypes.HANDLE(-1).value:
        return []
    names = [data.cStreamName]
    while k32.FindNextStreamW(h, ctypes.byref(data)):
        names.append(data.cStreamName)
    k32.FindClose(h)
    return sorted(names)


def source_state(folder):
    """What the functional gate asserts about sources. Last-access time is reported separately, not asserted."""
    state = {}
    for p in sorted(Path(folder).rglob("*")):
        st = p.stat()
        state[p.name] = {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
            "size": st.st_size, "mtime_ns": st.st_mtime_ns,
            "attributes": getattr(st, "st_file_attributes", None),
            "streams": alternate_streams(p) if p.is_file() else None,
        }
    return state


@pytest.fixture
def make_org(tmp_path):
    """Organizer factory over a temp catalog and output root. Calling it again simulates an app restart."""
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer

    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    opened = []

    def make():
        for c in opened:
            c.close()
        opened.clear()
        cat = Catalog(tmp_path / "data" / "catalog.sqlite3")
        opened.append(cat)
        org = Organizer(cat)
        org.set_output_root(out)
        return org

    yield make
    for c in opened:
        c.close()


@pytest.fixture
def office(tmp_path):
    """Synthetic DOCX, PPTX and ODT files (tests/office_fixtures.py) in their own source folder."""
    from office_fixtures import make_docx, make_odt, make_pptx

    dest = tmp_path / "office"
    dest.mkdir()
    for make, name in ((make_docx, "handbook.docx"), (make_pptx, "security.pptx"), (make_odt, "handbook.odt")):
        make(dest / name)
    return dest


@pytest.fixture
def make_pdf(tmp_path):
    """Generated one-page PDFs with the given words, in a source folder of their own: the copy, recovery and
    learning invariants run without the private sample documents."""
    import pymupdf

    def make(name, text, folder="sources"):
        dest = tmp_path / folder
        dest.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), text)
        doc.save(dest / name)
        doc.close()
        return dest / name
    return make


@pytest.fixture
def filed_pdf(make_pdf, make_org):
    """filed_pdf(org, name, words, category name) -> document id: a generated PDF imported and filed."""
    from classifile.analysis.candidates import name_key
    from classifile.organizer import read_and_analyze

    def file(org, name, text, category):
        path = make_pdf(name, text)
        doc, _ = org.record(path, *read_and_analyze(path))
        cat = org.catalog.category_by_key(name_key(category))
        org.file(doc, cat["id"] if cat else org.create_category(category))
        return doc
    return file
