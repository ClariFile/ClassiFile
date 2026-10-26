"""File-safety invariants on generated documents only, so they run in every checkout (no private samples)."""
import hashlib
from pathlib import Path

import pytest

from classifile.copies import engine


def _files(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_a_resumed_move_makes_the_new_copy_again_before_the_old_one_goes(make_org, filed_pdf):
    org = make_org()
    doc = filed_pdf(org, "notes.pdf", "garden soil compost seedling", "First")
    second = org.create_category("Second")
    with pytest.raises(engine._Crash):
        org.move(doc, second, _crash_at="after-switch")
    (org.output_root / "Second" / "notes.pdf").unlink()        # the new copy is gone before the restart
    org = make_org()
    org.startup()
    assert _files(org.output_root / "Second") == ["notes.pdf"]  # made again, from the old copy
    assert _files(org.output_root / "First") == []
    sha = org.catalog.document(doc)["sha256"]
    assert hashlib.sha256((org.output_root / "Second" / "notes.pdf").read_bytes()).hexdigest() == sha
    assert org.catalog.document(doc)["status"] == "filed" and org.catalog.pending_moves() == []


@pytest.mark.parametrize("spoil", ["edited", "gone"])
def test_an_old_copy_stays_while_its_replacement_is_missing_or_edited(make_org, filed_pdf, tmp_path, spoil):
    org = make_org()
    doc = filed_pdf(org, "notes.pdf", "garden soil compost seedling", "First")
    old = org.catalog.document_copies(doc)[0]
    new_root = tmp_path / "new-out"
    new_root.mkdir()
    engine.make_copy(org.catalog, doc, old["snapshot_sha256"], old["path"], old["category_id"], new_root, reuse=False)
    twin = new_root / "First" / "notes.pdf"                    # a change of output folder stopped after publishing
    if spoil == "edited":
        twin.write_bytes(twin.read_bytes() + b"% edited")
    else:
        twin.unlink()
    engine.recover(org.catalog, new_root)                       # the next start, with the new output folder
    assert Path(old["path"]).exists()                           # the last good copy is never removed
    assert org.catalog.one("SELECT status FROM copies WHERE id = ?", old["id"])[0] == "published"


def test_retiring_needs_a_verified_twin(make_org, filed_pdf):
    org = make_org()
    doc = filed_pdf(org, "notes.pdf", "garden soil compost seedling", "First")
    c = org.catalog.document_copies(doc)[0]
    assert engine._retire_old_copy(org.catalog, c, org.create_category("Elsewhere")) == "kept"
    assert (org.output_root / "First" / "notes.pdf").exists()


def test_a_file_in_the_way_of_a_category_folder_can_be_retried_without_a_restart(make_org, make_pdf):
    from classifile.organizer import read_and_analyze

    org = make_org()
    path = make_pdf("notes.pdf", "garden soil compost seedling")
    doc, _ = org.record(path, *read_and_analyze(path))
    cat = org.create_category("Garden")
    blocker = org.output_root / "Garden"
    blocker.write_text("someone else's file")                   # a file where the folder should be
    for _ in range(2):                                          # the same plain answer every time, no stuck state
        with pytest.raises(engine.CopyError, match="in the way"):
            org.file(doc, cat)
        assert org.catalog.active_primary(doc) is None and org.catalog.document(doc)["status"] == "needs_decision"
    assert blocker.read_text() == "someone else's file"          # never touched
    blocker.unlink()                                            # the user moved it away
    org.file(doc, cat)
    assert _files(org.output_root / "Garden") == ["notes.pdf"] and org.catalog.document(doc)["status"] == "filed"


def test_one_session_per_catalog_and_other_catalogs_open_freely(tmp_path):
    from classifile.app.main import catalog_lock

    first = catalog_lock(tmp_path / "a" / "catalog.sqlite3")
    assert first is not None
    assert catalog_lock(tmp_path / "a" / "catalog.sqlite3") is None          # a second session is declined
    other = catalog_lock(tmp_path / "b" / "catalog.sqlite3")
    assert other is not None                                                # another catalog is independent
    first.unlock()
    again = catalog_lock(tmp_path / "a" / "catalog.sqlite3")                # free again once the first has ended
    assert again is not None
    again.unlock()
    other.unlock()


def test_forget_removes_what_matching_learned_and_rebuilds_from_the_rest(make_org, make_pdf):
    import json

    from classifile.organizer import read_and_analyze

    org = make_org()
    folders = {"Garden": ("zyxquorp compost soil seedling", "zyxquorp mulch soil pruning"),
               "Travel": ("hotel booking passport flight", "flight luggage hotel visa"),
               "Recipes": ("garlic simmer onion oven", "butter flour oven dough")}
    examples = {}
    for name, texts in folders.items():
        cat = org.category_for(name)
        for n, words in enumerate(texts):
            path = make_pdf(f"{name}{n}.pdf", words, folder=f"mine/{name}")
            assert org.learn(path, *read_and_analyze(path), cat, path.parent) == "learned"
        examples[name] = path.parent
    org.update_matching()
    assert "zyxquorp" in json.loads(org.catalog.active_matcher()["bundle_json"])["idf"]
    gone = org.catalog.example_documents(str(examples["Garden"]))
    assert org.forget_folder(examples["Garden"]) == 2
    def check(org):
        rows = org.catalog.all("SELECT status, trigger, bundle_json FROM matchers ORDER BY version")
        assert [r["status"] for r in rows] == ["forgotten", "active"] and rows[1]["trigger"] == "forget"
        assert all("zyxquorp" not in r["bundle_json"] and not set(gone) & set(json.loads(r["bundle_json"])["training"])
                   for r in rows)                               # in no version, used or kept
        assert not set(gone) & set(org._counts) and org.catalog.texts().keys().isdisjoint(gone)
        assert len(json.loads(rows[1]["bundle_json"])["documents"]) == 2       # the other examples still teach
        assert org.catalog.category_by_key("garden")                          # the category stays

    check(org)
    check(make_org())                                           # also after a restart


def test_family_members_filed_apart_teach_nothing_until_resolved(make_org, filed_pdf):
    org = make_org()
    a = filed_pdf(org, "lecture.pdf", "garden soil compost seedling", "Garden")
    b = filed_pdf(org, "lecture-v2.pdf", "garden soil compost seedling mulch", "Travel")   # its twin, filed apart
    c = filed_pdf(org, "hotel.pdf", "hotel booking passport", "Travel")
    sha = lambda d: org.catalog.document(d)["sha256"]
    org.catalog.set_family_labels({sha(a): "F1", sha(b): "F1"})
    assert set(org.catalog.explicit_labels()) == {c} and org.catalog.family_conflicts() == {a, b}
    assert set(org.evaluation_inputs()[1]) == {c}                # the evaluation reads the same definition
    org.move(b, org.catalog.active_primary(a)["category_id"])   # the owner resolves it
    assert set(org.catalog.explicit_labels()) == {a, b, c} and org.catalog.family_conflicts() == set()


def test_learning_follows_choices_corrections_also_and_forget_across_a_restart(make_org, filed_pdf, make_pdf):
    """The whole learning sequence (designImp review): choose, train, correct, update, "also belongs to", learn
    from a folder and forget it, restart; only the user's latest primary choices teach, and the counts say so."""
    import json

    from classifile.organizer import read_and_analyze

    org = make_org()
    words = {"Garden": ["compost soil seedling", "mulch pruning hedge", "greenhouse tomato watering"],
             "Travel": ["hotel booking passport", "flight luggage visa", "train ticket timetable"]}
    docs = {(cat, n): filed_pdf(org, f"{cat}{n}.pdf", w, cat) for cat, ws in words.items() for n, w in enumerate(ws)}
    blank = filed_pdf(org, "blank.pdf", "", "Travel")                       # no readable words: teaches nothing
    assert org.update_matching()["outcome"] == "updated"
    assert org.learning_audit() == {"documents": 6, "families": 6, "unreadable": 1, "conflicts": 0}
    garden, travel = (org.catalog.category_by_key(k)["id"] for k in ("garden", "travel"))

    moved = docs[("Garden", 2)]
    org.move(moved, travel)                                                 # the user's correction
    assert org.matching_status()["since"] == 1 and org.update_matching()["outcome"] in ("updated", "kept previous")
    newest = org.catalog.all("SELECT bundle_json FROM matchers ORDER BY version DESC LIMIT 1")[0]["bundle_json"]
    assert json.loads(newest)["training"][str(moved)] == travel             # the latest choice is what it learned

    labels = org.catalog.explicit_labels()
    org.also(docs[("Travel", 0)], garden)                                   # a second copy, not a second label
    assert org.catalog.explicit_labels() == labels and org.matching_status()["since"] == 0
    assert org.update_matching()["outcome"] == "up to date"

    recipes = org.category_for("Recipes")
    for n, w in enumerate(["garlic onion simmer", "flour butter oven"]):
        path = make_pdf(f"r{n}.pdf", w, folder="mine/Recipes")
        assert org.learn(path, *read_and_analyze(path), recipes, path.parent) == "learned"
    assert org.learning_audit()["documents"] == 8
    assert org.forget_folder(path.parent) == 2
    def check(org):
        assert org.catalog.explicit_labels() == labels and blank in labels
        assert org.learning_audit() == {"documents": 6, "families": 6, "unreadable": 1, "conflicts": 0}
        active = json.loads(org.catalog.active_matcher()["bundle_json"])
        assert set(active["documents"]) == {str(garden), str(travel)}      # Recipes taught nothing it kept
        assert org.matching_status()["since"] == 0

    check(org)
    check(make_org())                                                       # and the same after a restart
