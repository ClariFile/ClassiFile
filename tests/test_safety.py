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
    assert org.learning_audit() == {"documents": 6, "families": 6, "unreadable": 1, "conflicts": 0, "related": 0}
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
        assert org.learning_audit() == {"documents": 6, "families": 6, "unreadable": 1, "conflicts": 0, "related": 0}
        active = json.loads(org.catalog.active_matcher()["bundle_json"])
        assert set(active["documents"]) == {str(garden), str(travel)}      # Recipes taught nothing it kept
        assert org.matching_status()["since"] == 0

    check(org)
    check(make_org())                                                       # and the same after a restart


def _teach(org, make_pdf, filed_pdf):
    """Garden and Travel filed by the user, Recipes learned from a folder of the user's; matching trained on all."""
    from classifile.organizer import read_and_analyze

    for cat, texts in {"Garden": ("compost soil seedling", "mulch pruning hedge", "tomato greenhouse watering"),
                       "Travel": ("hotel booking passport", "flight luggage visa", "train ticket timetable")}.items():
        for n, words in enumerate(texts):
            filed_pdf(org, f"{cat}{n}.pdf", words, cat)
    recipes = org.category_for("Recipes")
    for n, words in enumerate(("garlic onion simmer", "flour butter oven", "pepper roast dough")):
        path = make_pdf(f"r{n}.pdf", words, folder="mine/Recipes")
        assert org.learn(path, *read_and_analyze(path), recipes, path.parent) == "learned"
    assert org.update_matching()["outcome"] == "updated"
    return path.parent


def test_an_update_paused_before_publication_cannot_bring_back_forgotten_examples(make_org, make_pdf, filed_pdf,
                                                                                   monkeypatch):
    """designImp2 item 1: Forget lands while an update is learning; the update is refused at publication, in the
    same transaction as the check, and the forgotten examples are in no version, also after a restart."""
    import json
    import threading

    from classifile import matching

    org = make_org()
    folder = _teach(org, make_pdf, filed_pdf)
    gone = set(org.catalog.example_documents(str(folder)))
    filed_pdf(org, "Garden3.pdf", "rake shovel compost", "Garden")      # something new to learn
    paused, go, train = threading.Event(), threading.Event(), matching.train
    updater = []

    def slow_train(texts, labels):
        if threading.current_thread() in updater:
            paused.set()
            go.wait(10)
        return train(texts, labels)

    monkeypatch.setattr(matching, "train", slow_train)
    result = {}
    t = threading.Thread(target=lambda: result.update(org.update_matching()))
    updater.append(t)
    t.start()
    assert paused.wait(10)                                               # it has read everything, examples too
    assert org.forget_folder(folder) == 3
    go.set()
    t.join(10)
    assert result["outcome"] == "newer choices"

    def check(org):
        for row in org.catalog.all("SELECT bundle_json FROM matchers"):
            assert not gone & set(json.loads(row["bundle_json"])["training"])
        assert org.catalog.active_matcher() is not None                  # the last valid version stays usable

    check(org)
    check(make_org())


def test_removing_a_learned_example_imported_for_filing_removes_what_it_taught(make_org, make_pdf, filed_pdf):
    """designImp2 item 2: learn, update, import the same bytes, leave it waiting, remove it."""
    import hashlib
    import json

    from classifile.organizer import read_and_analyze

    org = make_org()
    folder = _teach(org, make_pdf, filed_pdf)
    path = folder / "r0.pdf"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    doc, _ = org.record(path, *read_and_analyze(path))                  # the example, now waiting to be filed
    assert org.catalog.document(doc)["status"] == "needs_decision"
    assert doc not in org.catalog.explicit_labels()                     # an open question teaches nothing (B4)
    org._terms(doc)
    org.remove([doc])

    def check(org):
        for row in org.catalog.all("SELECT bundle_json FROM matchers"):
            assert doc not in json.loads(row["bundle_json"])["training"]
        assert doc not in org._counts and doc not in org.catalog.explicit_labels()
        assert org.learning_audit()["documents"] == 8                    # 6 filed, 2 examples left

    check(org)
    check(make_org())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before      # the original is untouched


def test_inferred_families_teach_and_are_shown_owner_families_decide(make_org, filed_pdf, tmp_path):
    """designImp2 item 6: owner-confirmed twins filed apart are left out (above); documents that only share a file
    name are one family for the evaluation, still teach, and are listed; the owner's ids overrule the name."""
    from classifile import evaluation

    org = make_org()
    a = filed_pdf(org, "notes.pdf", "compost soil seedling mulch", "Garden")
    (tmp_path / "sources").rename(tmp_path / "first")                  # a second "notes.pdf" in another folder
    b = filed_pdf(org, "notes.pdf", "hotel booking passport flight", "Travel")
    labels = org.catalog.explicit_labels()
    assert {a, b} <= set(labels)                                         # a shared name is no proof: both teach
    groups = org.evaluation_inputs()[2]
    assert groups[a] == groups[b]                                        # held out together, to be safe
    assert org.learning_audit()["related"] == 2
    sha = lambda d: org.catalog.document(d)["sha256"]
    org.catalog.set_family_labels({sha(a): "F1", sha(b): "F2"})          # the owner says they are not one family
    org._audit = (None, None)
    assert org.evaluation_inputs()[2][a] != org.evaluation_inputs()[2][b]
    assert org.learning_audit()["related"] == 0 and org.catalog.family_conflicts() == set()
    assert evaluation.file_stem("notes.pdf") == "notes"


def test_a_catalog_lost_after_a_backup_comes_back_with_its_learning_and_copies(make_org, filed_pdf, tmp_path):
    """designImp2 item 12: back up while open, lose the catalog, restore at the next start: labels, examples' and
    copies' ownership are back; a copy edited since is flagged when next looked at; nothing is overwritten."""
    from classifile.catalog import db

    org = make_org()
    a = filed_pdf(org, "a.pdf", "compost soil seedling", "Garden")
    b = filed_pdf(org, "b.pdf", "hotel booking passport", "Travel")
    labels, copies = org.catalog.explicit_labels(), org.catalog.copies("published")
    backup = tmp_path / "backups" / "catalog.sqlite3"
    backup.parent.mkdir()
    org.catalog.backup(backup)
    with pytest.raises(ValueError):
        org.catalog.backup(backup)                                     # never over an existing file
    assert db.check_backup(backup) is None
    (backup.parent / "notes.txt").write_text("not a catalog")
    assert db.check_backup(backup.parent / "notes.txt") == "This isn't a ClassiFile catalog."

    path = org.catalog.path
    org.catalog.close()
    path.unlink()                                                      # the catalog is lost
    Path(copies[0]["path"]).write_bytes(b"edited by the user")         # and a copy was edited meanwhile
    open_again = make_org()                                            # a new, empty catalog started meanwhile
    assert open_again.catalog.explicit_labels() == {}
    open_again.catalog.close()
    db.stage_restore(backup, path.parent)
    kept = db.apply_restore(path)                                      # at the next start, before opening
    assert kept.startswith("catalog before restore") and (path.parent / kept).is_file()   # the empty one is kept
    org = make_org()
    assert org.catalog.explicit_labels() == labels and len(org.catalog.copies("published")) == 2
    org.flag_missing_copy(copies[0]["document_id"])
    assert {c["status"] for c in org.catalog.copies()} == {"published", "edited"}   # flagged, never adopted
    assert db.apply_restore(path) is None                              # nothing staged: nothing happens


def test_readiness_counts_confirmed_documents_and_families_per_category(make_org, filed_pdf):
    """designImp2, better categorization: three near-copies are one family, not broad evidence."""
    from classifile.app.main import readiness_text

    org = make_org()
    for n in range(3):
        filed_pdf(org, f"lecture-{n}.pdf", "compost soil seedling mulch pruning", "Garden")
    filed_pdf(org, "hotel.pdf", "hotel booking passport", "Travel")
    assert org.readiness() == [("Garden", 3, 1, 0), ("Travel", 1, 1, 0)]
    assert readiness_text(org.readiness()) == ("Garden: 3 confirmed in 1 family\n"
                                               "Travel: 1 confirmed (filed into by itself from 3)")
