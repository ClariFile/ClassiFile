import hashlib
from pathlib import Path

import pytest

from classifile.copies import engine
from classifile.copies.engine import is_temp_name, sanitize_folder_name
from classifile.organizer import read_and_analyze


@pytest.mark.parametrize("name,folder", [
    ("C", "C"), ("C++", "C++"), ("C#", "C#"), ("C/C++", "C_C++"), ("a\\b", "a_b"), ('Q: "why"?', "Q_ _why__"),
    ("CON", "CON_"), ("con.txt", "con.txt_"), ("LPT1", "LPT1_"), ("Notes. ", "Notes"), ("...", "_"),
    ("Console", "Console"), ("  Data   Mining  ", "Data Mining"),
])
def test_sanitize_folder_name(name, folder):
    assert sanitize_folder_name(name) == folder


def _import(org, path):
    return org.record(path, *read_and_analyze(path))[0]


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_verified_copy_and_no_overwrite(pdfs, make_org):
    org = make_org()
    doc = _import(org, pdfs / "S2.pdf")
    cat = org.create_category("C++")
    dest = org.output_root / "C++"
    dest.mkdir()
    unrelated = dest / "S2.pdf"
    unrelated.write_bytes(b"user's own unrelated file")

    outcome, path = org.file(doc, cat)
    assert outcome == "published" and path.name == f"{'S2.pdf'.rsplit('.', 1)[0]} (2).pdf"
    assert path.read_bytes() == (pdfs / "S2.pdf").read_bytes()
    assert unrelated.read_bytes() == b"user's own unrelated file"
    assert org.catalog.document(doc)["status"] == "filed"

    # Same snapshot, same category: "already filed", no second copy.
    assert org.file(doc, cat)[0] == "already filed"
    assert sorted(p.name for p in dest.iterdir()) == [f"{'S2.pdf'.rsplit('.', 1)[0]} (2).pdf", "S2.pdf"]


def test_source_changed_since_import_fails_without_partial_files(pdfs, make_org):
    org = make_org()
    src = pdfs / "S2.pdf"
    doc = _import(org, src)
    cat = org.create_category("C++")
    data = src.read_bytes()
    src.write_bytes(data + b"%changed")  # the user edits the source after import (test copy only)
    with pytest.raises(engine.CopyError, match="has changed since it was imported. Import it again"):
        org.file(doc, cat)
    assert not (org.output_root / "C++").exists()  # the folder this attempt created is gone again
    d = org.catalog.document(doc)
    assert d["status"] == "needs_decision" and "has changed since it was imported" in d["status_reason"]
    assert org.catalog.active_primary(doc) is None and org.catalog.documents(cat) == []


def _output_files(root):
    return sorted(p for p in Path(root).rglob("*") if p.is_file())


@pytest.mark.parametrize("crash_at", ["mid-write", "before-publish", "after-publish"])
def test_crash_recovery(pdfs, make_org, crash_at, monkeypatch):
    org = make_org()
    doc = _import(org, pdfs / "S1.pdf")
    cat = org.create_category("Course B")
    dest = org.output_root / "Course B"
    dest.mkdir()
    # Unrecorded files that recovery must never remove, including one that looks like an app temp file.
    stranger_tmp = dest / ".classifile-0123456789abcdef.tmp"
    stranger_tmp.write_bytes(b"not ours")
    (dest / "notes.txt").write_bytes(b"user notes")

    real = engine.make_copy
    monkeypatch.setattr("classifile.organizer.make_copy", lambda *a, **k: real(*a, **k, _crash_at=crash_at))
    with pytest.raises(engine._Crash):
        org.file(doc, cat)
    monkeypatch.undo()

    org = make_org()  # restart: new connection, then startup recovery
    report = org.startup()
    assert [outcome for _, outcome in report] == (["published"] if crash_at == "after-publish" else ["failed"])

    # No partial or app temp files remain, except the unrecorded stranger, which was left alone.
    assert [p for p in dest.iterdir() if is_temp_name(p)] == [stranger_tmp]
    assert stranger_tmp.read_bytes() == b"not ours" and (dest / "notes.txt").read_bytes() == b"user notes"

    if crash_at != "after-publish":  # never filed: the document waits again and the abandoned category is gone
        assert org.catalog.document(doc)["status"] == "needs_decision" and org.catalog.category(cat) is None
        cat = org.create_category("Course B")
    # Re-choosing gives exactly one copy, consistent with the catalog.
    org.file(doc, cat)
    sha = _sha(pdfs / "S1.pdf")
    copies_on_disk = [p for p in _output_files(org.output_root) if _sha(p) == sha]
    published = org.catalog.copies("published")
    assert len(copies_on_disk) == 1 and len(published) == 1
    assert Path(published[0]["path"]) == copies_on_disk[0] and published[0]["hash_at_creation"] == sha
    assert org.catalog.copies("planned") == []
    assert org.catalog.document(doc)["status"] == "filed"


def test_missing_published_copy_is_flagged(pdfs, make_org):
    org = make_org()
    doc = _import(org, pdfs / "S2.pdf")
    _, path = org.file(doc, org.create_category("C++"))
    path.unlink()  # the user deleted the app copy
    org = make_org()
    org.startup()
    assert [c["status"] for c in org.catalog.copies()] == ["missing"]


def test_move_copies_verified_no_overwrite_edited_stay(pdfs, make_org, tmp_path):
    org = make_org()
    cat = org.create_category("Courses")
    for name in ("S2.pdf", "S1.pdf", "S3.pdf"):
        org.file(_import(org, pdfs / name), cat)
    old_root = org.output_root
    edited = old_root / "Courses" / "S1.pdf"
    edited.write_bytes(edited.read_bytes() + b"edit")
    new_root = tmp_path / "new"
    (new_root / "Courses").mkdir(parents=True)
    unrelated = new_root / "Courses" / "S2.pdf"
    unrelated.write_bytes(b"someone else's file")

    report = dict(org.set_output_root(new_root, move=True))
    assert sorted(report.values()) == ["edited", "moved", "moved"]
    assert unrelated.read_bytes() == b"someone else's file"                # never overwritten
    assert (new_root / "Courses" / f"{'S2.pdf'.rsplit('.', 1)[0]} (2).pdf").read_bytes() == (pdfs / "S2.pdf").read_bytes()
    assert edited.exists() and not (new_root / "Courses" / "S1.pdf").exists()
    assert not (old_root / "Courses" / "S2.pdf").exists()
    org.startup()                                                         # the next start: still consistent
    assert {c["status"] for c in org.catalog.copies()} == {"published", "moved", "edited"}
    assert all(org.catalog.document(d["id"])["status"] == "filed" for d in org.catalog.documents(cat))


def test_interrupted_move_is_finished_at_startup(pdfs, make_org, tmp_path):
    org = make_org()
    cat = org.create_category("Courses")
    org.file(_import(org, pdfs / "S2.pdf"), cat)
    (old,) = org.catalog.copies("published")
    new_root = tmp_path / "new"
    new_root.mkdir()
    # The new copy was published, then the process stopped before the old one was retired.
    engine.make_copy(org.catalog, old["document_id"], old["snapshot_sha256"], old["path"], cat, new_root, reuse=False)
    org.catalog.set_setting("output_root", str(new_root.resolve()))
    org.startup()  # what the next app start does
    assert not Path(old["path"]).exists()
    assert sorted(c["status"] for c in org.catalog.copies()) == ["moved", "published"]


def test_missing_original_leaves_nothing_half_done(pdfs, make_org, tmp_path):
    org = make_org()
    src = tmp_path / "Downloads"
    src.mkdir()
    path = src / "handout 3,2024.pdf"
    path.write_bytes((pdfs / "S2.pdf").read_bytes())
    doc = _import(org, path)
    path.unlink()                                        # the user moved the original after importing it
    cat = org.create_category("Course Notes")
    with pytest.raises(engine.CopyError) as e:
        org.file(doc, cat)
    assert str(e.value) == f"The original file is no longer at {path}. Import it again from its new location."
    d = org.catalog.document(doc)
    assert d["status"] == "needs_decision" and d["status_reason"] == str(e.value)
    assert org.catalog.active_primary(doc) is None and org.catalog.documents(cat) == []
    assert not (org.output_root / "Course Notes").exists()
    assert org.discard_unused_category(cat) and org.catalog.category(cat) is None  # no empty category left


def test_startup_repairs_an_earlier_half_done_filing(pdfs, make_org):
    org = make_org()
    doc = _import(org, pdfs / "S2.pdf")
    cat = org.create_category("Course Notes")
    # The state an older version left behind: a membership with only a failed copy attempt.
    org.catalog.add_primary(doc, cat, "user-confirmed")
    org.catalog.plan_copy(doc, org.catalog.document(doc)["sha256"], cat, org.output_root / ".classifile-x.tmp")
    org.catalog.run("UPDATE copies SET status = 'failed'")
    org.catalog.set_document_status(doc, "failed", "copy failed (FileNotFoundError)")
    org.startup()
    d = org.catalog.document(doc)
    assert d["status"] == "needs_decision" and "Choose a category again" in d["status_reason"]
    assert org.catalog.active_primary(doc) is None and org.catalog.category(cat) is None


def test_program_folder_is_refused_as_output_folder(make_org, tmp_path, monkeypatch):
    """In the installed app, its own folder (where an update replaces files) is never an output folder."""
    org = make_org()
    program = tmp_path / "Programs" / "ClassiFile"
    (program / "out").mkdir(parents=True)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(program / "ClassiFile.exe"))
    for inside in (program, program / "out"):
        with pytest.raises(ValueError, match="program folder"):
            org.set_output_root(inside)
    org.set_output_root(tmp_path / "Programs")                         # beside it is fine
    assert org.output_root == (tmp_path / "Programs").resolve()


def test_data_dir_override_keeps_the_catalog_apart(tmp_path, monkeypatch):
    """CLASSIFILE_DATA_DIR (the portable test copy's launcher sets it) moves the catalog out of the usual folder."""
    from classifile.catalog.db import Catalog, default_data_dir
    monkeypatch.setenv("CLASSIFILE_DATA_DIR", str(tmp_path / "test-data"))
    assert default_data_dir() == tmp_path / "test-data"
    Catalog.open_default().close()
    assert (tmp_path / "test-data" / "catalog.sqlite3").is_file()
