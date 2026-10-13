import hashlib
import sys

import pymupdf
import pytest

from conftest import SAMPLE, EXPECT, alternate_streams, source_state
from classifile.organizer import read_and_analyze

PLACEMENT = {
    SAMPLE["S4"]: "Course A",
    SAMPLE["S1"]: "Course B",
    SAMPLE["S5"]: "Course A",
    SAMPLE["S6"]: "Course B",
    SAMPLE["S2"]: "C++",
    SAMPLE["S3"]: "PHP",
}


def _import_all(org, folder):
    ids = {}
    for name in PLACEMENT:
        path = folder / name
        assert org.check_import(path) is None
        ids[name], note = org.record(path, *read_and_analyze(path))
        assert note is None
    return ids


def _file_all(org, ids):
    cats = {}
    for name, cat_name in PLACEMENT.items():
        if cat_name not in cats:
            cats[cat_name] = org.create_category(cat_name)
        org.file(ids[name], cats[cat_name])


def test_sources_preserved_through_full_import(samples, make_org):
    before = source_state(samples)
    atimes = {p.name: p.stat().st_atime_ns for p in samples.iterdir()}
    org = make_org()
    _file_all(org, _import_all(org, samples))
    org = make_org()
    org.startup()
    assert source_state(samples) == before  # hash, size, mtime, attributes, streams, and the file listing
    changed_atime = [n for n, t in atimes.items() if (samples / n).stat().st_atime_ns != t]
    print(f"\nlast-access time changed (reported only, not asserted): {changed_atime or 'none'}")


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS alternate data streams")
def test_stream_detection_works(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    assert alternate_streams(f) == ["::$DATA"]
    with open(f"{f}:extra", "wb") as s:  # on a scratch file, never a source
        s.write(b"y")
    assert alternate_streams(f) == ["::$DATA", ":extra:$DATA"]


def _snapshot(org):
    cats = [(c["id"], c["name"], c["folder_name"]) for c in org.catalog.categories()]
    docs = {c[0]: [(d["id"], d["file_name"], d["status"]) for d in org.catalog.documents(c[0])] for c in cats}
    inbox = [(d["id"], d["file_name"], d["status"]) for d in org.catalog.documents(None)]
    return cats, docs, inbox


def test_persistence_across_reopen(samples, make_org):
    org = make_org()
    ids = _import_all(org, samples)
    org.file(ids[SAMPLE["S2"]], org.create_category("C++"))
    org.create_category("PHP")
    before = _snapshot(org)
    analysis = org.catalog.analysis(ids[SAMPLE["S1"]])
    org = make_org()
    org.startup()
    assert _snapshot(org) == before
    assert org.catalog.analysis(ids[SAMPLE["S1"]]) == analysis
    assert org.catalog.schema_version == 9
    assert {d[2] for d in before[2]} == {"needs_decision"} and len(before[2]) == 5


def test_duplicate_import_and_hash_is_not_identity(samples, make_org):
    org = make_org()
    ids = _import_all(org, samples)
    path = samples / SAMPLE["S2"]
    assert org.record(path, *read_and_analyze(path)) == (ids[SAMPLE["S2"]], "already imported")
    assert len(set(ids.values())) == 6 and all(len(i) == 36 for i in ids.values())  # UUIDs, not hashes


def test_import_checks(samples, make_org, tmp_path):
    org = make_org()
    inside = org.output_root / "C++" / "copy.pdf"
    inside.parent.mkdir()
    inside.write_bytes((samples / SAMPLE["S2"]).read_bytes())
    assert org.check_import(inside) == "already in the output folder"
    assert org.check_import(samples / "inventory.csv") is not None
    # Output root inside the source's folder is refused.
    parent_source = tmp_path / "loose.pdf"
    parent_source.write_bytes((samples / SAMPLE["S2"]).read_bytes())
    assert org.check_import(parent_source) == "the output folder is inside this file's folder"


def test_category_names(make_org):
    org = make_org()
    ids = {n: org.create_category(n) for n in ("C", "C++", "C#", "C/C++")}
    folders = {org.catalog.category(i)["folder_name"] for i in ids.values()}
    assert folders == {"C", "C++", "C#", "C_C++"}
    with pytest.raises(ValueError):
        org.create_category("  c++ ")  # normalized equality with an existing name
    other = org.create_category("C?C++")  # different name, same sanitized folder -> suffix, never shared
    assert org.catalog.category(other)["folder_name"] == "C_C++ (2)"


def test_failed_documents_are_recorded_and_cannot_be_filed(make_org, tmp_path):
    org = make_org()
    src = tmp_path / "src"
    src.mkdir()
    bad = src / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7 not really")
    doc, note = org.record(bad, *read_and_analyze(bad))
    assert note is None and org.catalog.document(doc)["status"] == "failed"
    with pytest.raises(ValueError):
        org.file(doc, org.create_category("X"))
    assert not (org.output_root / "X").exists()


def test_office_formats_full_import_preserves_sources(office, make_org):
    before = source_state(office)
    org = make_org()
    cat = org.create_category("Mixed")
    for path in sorted(office.iterdir()):
        assert org.check_import(path) is None
        doc, note = org.record(path, *read_and_analyze(path))
        assert note is None and org.catalog.document(doc)["status"] == "needs_decision"
        assert org.file(doc, cat)[0] == "published"
        assert (org.output_root / "Mixed" / path.name).read_bytes() == path.read_bytes()
    assert source_state(office) == before
    formats = {r["format"]: r["record_version"] for r in org.catalog.all("SELECT format, record_version FROM extractions")}
    assert formats == {"docx": 6, "pptx": 6, "odt": 6}
    summaries = org.catalog.all("SELECT summary_json FROM extractions")
    assert all(s["summary_json"] for s in summaries)


def test_failed_read_is_retried_on_reimport_but_not_a_failed_copy(make_org, tmp_path):
    from classifile.worker import failure

    org = make_org()
    src = tmp_path / "src"
    src.mkdir()
    path = src / "slow.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Timed out once")
    doc.save(path)
    doc_id, note = org.record(path, *failure(path, "reading timed out"))
    assert note is None and org.catalog.document(doc_id)["status_reason"] == "reading timed out"
    assert org.record(path, *read_and_analyze(path)) == (doc_id, "read again")
    assert org.catalog.document(doc_id)["status"] == "needs_decision"
    assert org.catalog.one("SELECT COUNT(*) FROM extractions")[0] == 1
    assert org.record(path, *read_and_analyze(path)) == (doc_id, "already imported")


def test_catalog_migrates_v1_pdf_rows(tmp_path, monkeypatch):
    from classifile.catalog import db

    path = tmp_path / "old.sqlite3"
    monkeypatch.setattr(db, "MIGRATIONS", db.MIGRATIONS[:1])
    old = db.Catalog(path)
    with old.db:
        old.db.execute("INSERT INTO documents VALUES ('d', 'needs_decision', NULL, 't', 't')")
        old.db.execute("INSERT INTO snapshots VALUES (1, 'd', 'h', 1, 'p', 'f.pdf', 't')")
        old.db.execute("INSERT INTO extractions (id, snapshot_id, reader_version, record_version, status, page_count,"
                       " created_at) VALUES (1, 1, 'pdf-1', 1, 'ok', 1, 't')")
        old.db.execute("INSERT INTO extraction_pages VALUES (1, 1, 'text', 4, 0.5, 0.1, 0.1, 0, NULL)")
    old.close()
    monkeypatch.undo()
    cat = db.Catalog(path)
    assert cat.schema_version == len(db.MIGRATIONS) == 9
    e = cat.one("SELECT format, unit, unit_count, record_version FROM extractions")
    assert tuple(e) == ("pdf", "page", 1, 1)  # old rows keep their record version
    u = cat.one("SELECT unit_index, kind, text, text_area FROM extraction_units")
    assert tuple(u) == (1, "page", "text", 0.5)
    cat.close()


def test_remove_refuses_filed_documents(samples, make_org):
    org = make_org()
    ids = _import_all(org, samples)
    org.file(ids[SAMPLE["S2"]], org.create_category("C++"))
    with pytest.raises(ValueError):
        org.remove([ids[SAMPLE["S2"]]])
    assert org.catalog.document(ids[SAMPLE["S2"]])["status"] == "filed"


def test_preview_without_other_programs(samples, office):
    from classifile.app.preview import first_page_png

    assert first_page_png(samples / SAMPLE["S2"]).startswith(b"\x89PNG")
    assert first_page_png(office / "security.pptx") is None  # no stored thumbnail: the window shows a text card


def test_locate_checks_the_content_hash(samples, make_org, tmp_path):
    org = make_org()
    src = tmp_path / "a"
    src.mkdir()
    path = src / "notes.pdf"
    path.write_bytes((samples / SAMPLE["S2"]).read_bytes())
    doc, _ = org.record(path, *read_and_analyze(path))
    moved = tmp_path / "b" / "renamed.pdf"
    moved.parent.mkdir()
    path.rename(moved)
    assert org.original_missing(doc)
    different = tmp_path / "b" / "other.pdf"
    different.write_bytes((samples / SAMPLE["S1"]).read_bytes())
    with pytest.raises(ValueError, match="another version"):
        org.locate(doc, different)
    assert org.locate(doc, moved) == moved.resolve() and not org.original_missing(doc)
    inside = org.output_root / "copy.pdf"
    inside.write_bytes(moved.read_bytes())
    with pytest.raises(ValueError, match="inside the output folder"):
        org.locate(doc, inside)


# -- regrouping: move, rename, delete (decision record B5) -----------------------------------------------------------
def _filed(samples, make_org, names=("S2", "S3")):
    org = make_org()
    ids = _import_all(org, samples)
    cat = org.create_category("First")
    for s in names:
        org.file(ids[SAMPLE[s]], cat)
    return org, ids, cat


def _files(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else None


def test_move_replaces_the_primary_category(samples, make_org):
    before = source_state(samples)
    org, ids, first = _filed(samples, make_org)
    doc, other = ids[SAMPLE["S2"]], ids[SAMPLE["S3"]]
    second = org.create_category("Second")
    assert org.move(doc, second) == "moved"
    assert _files(org.output_root / "Second") == [SAMPLE["S2"]] and _files(org.output_root / "First") == [SAMPLE["S3"]]
    assert [d["id"] for d in org.catalog.documents(second)] == [doc]
    assert [d["id"] for d in org.catalog.documents(first)] == [other]
    rows = org.catalog.all("SELECT category_id, provenance, status FROM memberships WHERE document_id = ? ORDER BY id", doc)
    assert [tuple(r) for r in rows] == [(first, "user-confirmed", "superseded"), (second, "user-corrected", "active")]
    assert org.move(doc, second) == "same" and org.catalog.pending_moves() == []
    assert org.move(doc, first) == "moved"                      # back again: the latest explicit choice wins
    assert _files(org.output_root / "First") == sorted([SAMPLE["S2"], SAMPLE["S3"]])
    with pytest.raises(ValueError):
        org.move(ids[SAMPLE["S1"]], second)                     # a waiting document is filed, not moved
    assert source_state(samples) == before                      # originals: untouched by any of it


def test_move_leaves_an_edited_copy_in_place_and_never_overwrites(samples, make_org):
    org, ids, first = _filed(samples, make_org, names=("S2",))
    doc = ids[SAMPLE["S2"]]
    old = org.output_root / "First" / SAMPLE["S2"]
    old.write_bytes(old.read_bytes() + b"\n% my notes\n")       # the user edited the filed copy
    second = org.create_category("Second")
    stranger = org.output_root / "Second" / SAMPLE["S2"]
    stranger.parent.mkdir()
    stranger.write_bytes(b"someone else's file")
    assert org.move(doc, second) == "edited"                    # made from the original, whose hash still matches
    assert old.read_bytes().endswith(b"% my notes\n")           # the edited copy stays, flagged
    assert org.catalog.one("SELECT status FROM copies WHERE path = ?", str(old))[0] == "edited"
    assert stranger.read_bytes() == b"someone else's file"      # never overwritten: the copy took another name
    new = org.catalog.documents(second)[0]["copy_path"]
    assert new != str(stranger) and hashlib.sha256(open(new, "rb").read()).hexdigest() == org.catalog.document(doc)["sha256"]


@pytest.mark.parametrize("crash_at", ["after-copy", "after-switch"])
def test_an_interrupted_move_finishes_at_startup(samples, make_org, crash_at):
    from classifile.copies import engine

    org, ids, first = _filed(samples, make_org, names=("S2",))
    doc, second = ids[SAMPLE["S2"]], org.create_category("Second")
    with pytest.raises(engine._Crash):
        org.move(doc, second, _crash_at=crash_at)
    assert _files(org.output_root / "First") == [SAMPLE["S2"]]  # the old copy is never gone before the end
    org = make_org()                                            # the app starts again
    org.startup()
    assert org.catalog.pending_moves() == []
    assert _files(org.output_root / "Second") == [SAMPLE["S2"]] and _files(org.output_root / "First") == []
    assert [d["id"] for d in org.catalog.documents(second)] == [doc] and org.catalog.documents(first) == []
    assert org.catalog.document(doc)["status"] == "filed"


def test_rename_moves_only_the_apps_copies(samples, make_org):
    before = source_state(samples)
    org, ids, first = _filed(samples, make_org)
    other = org.output_root / "First" / "my own notes.txt"
    other.write_text("not ClassiFile's")
    taken = org.create_category("Taken")
    with pytest.raises(ValueError, match="move the documents there instead"):
        org.rename_category(first, " taken ")
    leftover = org.rename_category(first, "Renamed")
    assert leftover == [org.output_root / "First"] and _files(org.output_root / "First") == ["my own notes.txt"]
    assert _files(org.output_root / "Renamed") == sorted([SAMPLE["S2"], SAMPLE["S3"]])
    cat = org.catalog.category(first)
    assert (cat["name"], cat["folder_name"]) == ("Renamed", "Renamed")
    assert all(d["copy_path"].startswith(str(org.output_root / "Renamed")) for d in org.catalog.documents(first))
    assert org.rename_category(first, "RENAMED") == []          # a change of case only: the folder is the same one
    assert org.catalog.category(first)["folder_name"] == "Renamed"
    other.unlink()
    assert org.rename_category(first, "Again") == [] and not (org.output_root / "Renamed").exists()
    assert not (org.output_root / "First").exists() or _files(org.output_root / "First") == []
    assert source_state(samples) == before and taken


def test_an_interrupted_rename_finishes_at_startup(samples, make_org):
    from classifile.copies import engine

    org, ids, first = _filed(samples, make_org)
    with pytest.raises(engine._Crash):
        org.rename_category(first, "Renamed", _crash_at="between-copy-and-retire")
    both = len(_files(org.output_root / "First")) + len(_files(org.output_root / "Renamed"))
    assert both == 3                                            # one document is in both folders; none is lost
    org = make_org()
    org.startup()
    assert _files(org.output_root / "Renamed") == sorted([SAMPLE["S2"], SAMPLE["S3"]])
    assert not (org.output_root / "First").exists() and org.catalog.get_setting("renaming") == "[]"
    assert len(org.catalog.documents(first)) == 2


def test_delete_only_an_empty_category_and_only_an_empty_folder(samples, make_org):
    org, ids, first = _filed(samples, make_org, names=("S2",))
    with pytest.raises(ValueError):
        org.delete_category(first)                              # it holds a document
    second = org.create_category("Second")
    org.move(ids[SAMPLE["S2"]], second)
    (org.output_root / "First" / "kept.txt").write_text("mine")
    assert org.delete_category(first) == org.output_root / "First"   # not empty: the folder stays
    assert [c["name"] for c in org.catalog.categories()] == ["Second"]
    assert org.catalog.category(first)["name"] == "First"       # the earlier placement still names it
    again = org.create_category("First")                        # the name is free again
    assert org.catalog.category(again)["folder_name"] == "First"
    third = org.create_category("Third")
    (org.output_root / "Third").mkdir()
    assert org.delete_category(third) is None and not (org.output_root / "Third").exists()
