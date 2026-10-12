import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from classifile.app.main import ALL, DECIDE, DOC, SETTINGS, MainWindow  # noqa: E402
from classifile.app.reasons import reason_text  # noqa: E402
from conftest import SAMPLE, EXPECT, source_state  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pump(app, until, timeout=30):
    end = time.monotonic() + timeout
    while not until() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    assert until()


class Recorder:
    """Stands in for the dialogs and outside actions; nothing opens during tests."""

    def __init__(self, w):
        self.opened, self.shown, self.close_answer, self.move_answer, self.folder = [], [], ("close", False), "move", ""
        self.removes, self.closes = 0, 0
        w.open_path = self.opened.append
        w.show_in_folder = self.shown.append
        w.confirm_remove = self._remove
        w.ask_close = self._close
        w.ask_move = lambda n: self.move_answer
        w.pick_folder = lambda title: self.folder

    def _remove(self, n):
        self.removes += 1
        return True

    def _close(self, n):
        self.closes += 1
        return self.close_answer


def _window(make_org, paths=()):
    w = MainWindow(make_org(), ask_output_root=False)
    rec = Recorder(w)
    w.show()  # offscreen; visibility checks then mean what they say
    w.import_paths([str(p) for p in paths])
    return w, rec


def _doc(w, file_name):
    return next(d["id"] for d in w.org.catalog.all_documents() if d["file_name"] == file_name)


def _rows(w):
    return [w.table.topLevelItem(i).text(0) for i in range(w.table.topLevelItemCount())]


def _item(w, title):
    return next(i for i in w.decision.items if i.title.full == title)


def _category_node(w, name):
    return next(w.cats.topLevelItem(i) for i in range(w.cats.topLevelItemCount())
                if w.cats.topLevelItem(i).text(0) == name)


def _notices(w):
    return [text for _, text, _ in w.notices.items] if w.notices.isVisible() else []


def _close(w, rec):
    rec.close_answer = ("close", False)
    w.close()


def test_reasons_are_plain_language():
    assert reason_text([{"source": "first_page", "pages": [1]}, {"source": "template", "pages": [2, 3]}]) == \
        "on the cover and most pages"
    assert reason_text([{"source": "recurring", "pages": [2, 3, 24]}], "slide") == "repeated on slides 2, 3 and 24"
    assert reason_text([{"source": "recurring", "pages": [5, 6, 7, 8, 9]}]) == "repeated on pages 5–9"
    assert reason_text([{"source": "keyphrase", "pages": []}]) == "key phrase from the text"


def test_empty_state_and_settings(app, make_org):
    w, rec = _window(make_org)
    assert w.stack.currentWidget() is w.empty_state and w.empty_add.isVisible()
    assert w.empty_texts == ["Bring some order to your documents.",
                             "Drop files here or choose documents to get started.", "PDF, PPTX, DOCX, ODT.",
                             "Original files stay unchanged. ClassiFile organizes copies."]
    assert w.page_title.full == "All documents" and not w.toolbar.isVisible() and not w.notices.isVisible()
    assert w.nav[DECIDE].text() == "Needs your decision" and w.decide_count.text() == ""  # count only if any
    assert not w.bulk.isVisible() and not w.details.isVisible()
    w.show_view(SETTINGS)
    assert w.stack.currentWidget() is w.settings_page and w.change_root.text() == "Change…"
    assert w.close_toggle.isChecked()
    w.close_toggle.setChecked(False)
    assert w.org.catalog.get_setting("close_notice") == "off"
    texts = " ".join(lab.text() for lab in w.settings_page.findChildren(QLabel))
    assert "Part of ClariFile" in texts and "Integrations" not in texts
    _close(w, rec)


def test_decision_page_two_step_filing_toast_and_details(app, samples, make_org):
    names = [SAMPLE["S1"], SAMPLE["S2"], SAMPLE["S3"]]
    w, rec = _window(make_org, [samples / n for n in names])
    assert w.processing.isVisible() and w.processing.text() == "Reading 1 of 3 documents…"
    _pump(app, lambda: not w.inflight)
    assert not w.processing.isVisible()
    assert w.windowTitle() == "ClassiFile — 3 waiting" and w.nav[DECIDE].text() == "Needs your decision"
    assert w.decide_count.text() == "3"
    assert w.notices.items == [("info", "3 documents need your decision.", "Review")]
    assert w.cats.topLevelItemCount() == 0                          # only categories the user created

    w.review()
    assert w.stack.currentWidget() is w.decision and len(w.decision.items) == 3 and not _notices(w)
    cst = _item(w, SAMPLE["S1"])
    cover, course = EXPECT["S1.cover_title"], EXPECT["S1.course_line"]   # from the local fixture map
    assert cst.line.text() == f"Suggested new category: {cover}"
    assert cst.primary.text() == "Create && file" and cst.choose.isVisible() and cst.pending.isVisible()
    cst.choose.click()                                              # expands in place
    # two names now: lines that only repeat on some pages are under "More"
    assert cst.expanded.isVisible() and cst.sugg.count() == 2 and cst.more_button.isVisible()
    assert f"{cover}\n    on the cover" in [cst.sugg.item(i).text() for i in range(2)]
    assert cst.field.text() == cover and cst.field.property("filled") is True
    cst.more_button.click()
    nde = next(i for i in range(cst.sugg.count()) if cst.sugg.item(i).text().startswith(course))
    cst.sugg.itemClicked.emit(cst.sugg.item(nde))                   # a click only fills the field
    assert cst.field.text() == course
    assert cst.confirm.text() == "Create && file" and cst.tag.text() == "New"
    assert cst.confirm.toolTip() == f"Create category '{course}' and file"
    assert w.org.catalog.categories() == [] and len(w.waiting()) == 3  # nothing filed yet

    QTest.keyClick(cst.field, Qt.Key_Return)                        # Enter files
    _pump(app, lambda: not w.filing)
    out = w.org.output_root / course / SAMPLE["S1"]
    assert out.exists() and len(w.decision.items) == 2
    assert w.toast.isVisible() and w.toast.label.text() == f"Filed {SAMPLE['S1']} in {course}"
    assert w.toast.action.text() == "Show"
    node = _category_node(w, course)
    assert node.text(1) == "1" and node.childCount() == 1

    lec = _item(w, SAMPLE["S3"])                     # an existing category, typed differently
    lec.choose.click()
    lec.field.setText(course.lower())
    assert lec.tag.text() == "Existing" and lec.confirm.text() == "File"
    w.toast.action.click()                                          # Show: the category, the document selected
    assert w.view[0] == "category" and [w.org.catalog.document(i)["file_name"] for i in w.selected_ids()] == \
        [SAMPLE["S1"]]
    assert not w.details.isVisible()                                # details only on request
    QTest.keyClick(w.table, Qt.Key_Space)
    assert w.details.isVisible() and w.details.title.full == SAMPLE["S1"]
    facts = w.details.facts.text()
    assert f"Category: {course}" in facts and "Filed: 20" in facts
    assert not w.details.locations.isVisible() and not w.details.why.isVisible()  # collapsed sections
    w.details.locations_section.toggle.click()
    locations = w.details.locations.text().replace("​", "")
    assert f"Copy: {out}" in locations and "Original: " in locations
    w.details.why_section.toggle.click()
    assert course in w.details.why.text()
    w.details.open_button.click()
    w.details.folder_button.click()
    QTest.keyClick(w.table, Qt.Key_Return)                          # Enter opens a filed copy
    assert rec.opened == [out, out] and rec.shown == [out]
    QTest.keyClick(w.table, Qt.Key_Space)
    assert not w.details.isVisible()
    _close(w, rec)


def test_group_item_files_only_the_listed_documents(app, samples, make_org, tmp_path):
    data = (samples / SAMPLE["S2"]).read_bytes()
    src = tmp_path / "src"
    src.mkdir()
    stem = SAMPLE["S2"].rsplit(".", 1)[0]
    first, second, later = src / SAMPLE["S2"], src / f"{stem} (handout).pdf", src / f"{stem} (again).pdf"
    first.write_bytes(data)
    second.write_bytes(data + b"\n% another copy\n")
    later.write_bytes(data + b"\n% a third copy\n")
    w, rec = _window(make_org, [first, second, samples / SAMPLE["S1"]])
    _pump(app, lambda: not w.inflight)
    w.review()
    group = _item(w, "2 documents with the same suggestion")
    assert group.group and group.names.isVisible() and SAMPLE["S2"] in group.names.text()
    assert second.name in group.names.text() and len(w.decision.items) == 2
    best = group.best
    group.choose.click()                                            # one field for the group; no per-file preview
    assert not group.sugg.isVisible() and not group.preview.isVisible() and group.field.text() == best
    group.primary.click()
    _pump(app, lambda: not w.filing)
    cat = w.org.catalog.category_by_key(best.casefold())
    assert sorted(d["file_name"] for d in w.org.catalog.documents(cat["id"])) == sorted([second.name, SAMPLE["S2"]])
    assert w.toast.label.text() == f"Filed 2 documents in {best}"
    assert [d["file_name"] for d in w.waiting()] == [SAMPLE["S1"]]
    w.import_paths([str(later)])                                    # no rule was made: the next one still asks
    _pump(app, lambda: not w.inflight)
    assert w.org.catalog.document(_doc(w, later.name))["status"] == "needs_decision"
    assert len(w.org.catalog.documents(cat["id"])) == 2
    _close(w, rec)


def test_missing_original_on_decision_page_and_locate(app, samples, make_org, tmp_path):
    src, moved = tmp_path / "Downloads", tmp_path / "Documents"
    src.mkdir()
    moved.mkdir()
    original = src / "handout 3,2024.pdf"
    original.write_bytes((samples / SAMPLE["S2"]).read_bytes())
    w, rec = _window(make_org, [original])
    _pump(app, lambda: not w.inflight)
    original.rename(moved / original.name)                         # the user moved it
    doc = _doc(w, original.name)
    w.refresh()
    assert any("has moved since it was added" in n for n in _notices(w))
    w.review()
    item = _item(w, original.name)
    assert item.line.text() == "⚠ The original file has moved. Locate it to file this document."
    assert item.primary.text() == "Locate file…" and item.remove.isVisible()
    assert not item.choose.isVisible() and not item.pending.isVisible()  # filing is not offered
    w.file_docs([doc], "Course Notes")                         # and refused if asked anyway
    assert w.org.catalog.categories() == [] and not w.filing

    other = moved / "other.pdf"                                    # a different file: refused, with advice
    other.write_bytes((samples / SAMPLE["S1"]).read_bytes())
    w.pick_file = lambda name, start: str(other)
    item.primary.click()
    assert any("Import it as a new document instead" in n for n in _notices(w))
    assert w.org.catalog.document(doc)["source_path"] == str(original)

    w.pick_file = lambda name, start: str(moved / original.name)   # the same file at its new place
    _item(w, original.name).primary.click()
    assert w.org.catalog.document(doc)["source_path"] == str((moved / original.name).resolve())
    assert "You can file it now" in w.toast.label.text() and not _notices(w)
    item = _item(w, original.name)
    assert item.primary.text() == "Create && file" and item.choose.isVisible()
    item.choose.click()
    item.field.setText("Course Notes")
    item.confirm.click()
    _pump(app, lambda: not w.filing)
    assert (w.org.output_root / "Course Notes" / original.name).exists()
    _close(w, rec)


def test_failed_filing_leaves_nothing_half_done_and_the_error_stays(app, samples, make_org, tmp_path):
    (tmp_path / "src").mkdir()
    original = tmp_path / "src" / "handout 3,2024.pdf"
    original.write_bytes((samples / SAMPLE["S2"]).read_bytes())
    w, rec = _window(make_org, [original])
    _pump(app, lambda: not w.inflight)
    w.review()
    w.org.original_missing = lambda doc_id: False                  # it moves between the check and the copy
    original.unlink()
    _item(w, original.name).choose.click()
    item = _item(w, original.name)
    item.field.setText("Course Notes")
    item.confirm.click()
    _pump(app, lambda: not w.filing)
    expected = f"The original file is no longer at {original}. Import it again from its new location."
    assert w.notices.items[0] == ("error", f"The new category 'Course Notes' wasn't created, because "
                                  f"{original.name} couldn't be filed. {expected}", "Review")
    assert w.org.catalog.categories() == [] and w.cats.topLevelItemCount() == 0  # no empty category left
    assert len(w.waiting()) == 1 and not (w.org.output_root / "Course Notes").exists()
    assert not w.toast.isVisible()
    w.show_view(ALL)
    w.refresh()
    assert w.notices.items[0][0] == "error"                        # errors stay until resolved
    w.remove_docs([_doc(w, original.name)])
    assert not _notices(w)
    _close(w, rec)


def test_bulk_bar_context_menu_keyboard_and_search(app, samples, make_org):
    names = [SAMPLE["S2"], SAMPLE["S1"], SAMPLE["S4"]]
    w, rec = _window(make_org, [samples / n for n in names])
    _pump(app, lambda: not w.inflight)
    assert sorted(_rows(w)) == sorted(names) and w.page_title.full == "All documents · 3"
    assert {w.table.topLevelItem(i).text(2) for i in range(3)} == {"Waiting"}   # icon plus a word
    w.search.setText("l-2")                                        # search filters by name
    assert _rows(w) == [SAMPLE["S4"]]
    w.search.clear()

    w.select_docs([_doc(w, SAMPLE["S2"]), _doc(w, SAMPLE["S1"])])
    assert w.bulk.isVisible() and w.bulk_count.text() == "2 selected"
    actions = [a.text() for a in w.context_menu(w.selected_ids()).actions()]
    assert actions == ["Remove from ClassiFile"]
    w.bulk_file.click()
    w.bulk_field.setText("Networking")
    assert w.bulk_go.text() == "Create && file" and w.bulk_tag.text() == "New"
    QTest.keyClick(w.bulk_field, Qt.Key_Return)
    _pump(app, lambda: not w.filing)
    assert w.toast.label.text() == "Filed 2 documents in Networking"
    cat = w.org.catalog.category_by_key("networking")
    assert len(w.org.catalog.documents(cat["id"])) == 2 and _category_node(w, "Networking").text(1) == "2"
    assert {w.table.topLevelItem(i).text(2) for i in range(3)} == {"", "Waiting"}  # no status once filed

    filed = _doc(w, SAMPLE["S2"])
    w.select_docs([filed])
    assert not w.bulk.isVisible()
    actions = [a.text() for a in w.context_menu([filed]).actions()]
    assert actions == ["Open", "Show in folder", "Details"]        # filed documents can't be removed here
    waiting = _doc(w, SAMPLE["S4"])
    actions = [a.text() for a in w.context_menu([waiting]).actions()]
    assert actions == ["Details", "Remove from ClassiFile"]
    w.select_docs([waiting])
    QTest.keyClick(w.table, Qt.Key_Return)                         # Enter on a waiting document: decide
    assert w.view[0] == DECIDE
    _close(w, rec)


def test_remove_waiting_documents(app, samples, make_org):
    before = source_state(samples)
    w, rec = _window(make_org, [samples / SAMPLE["S2"], samples / SAMPLE["S1"]])
    _pump(app, lambda: not w.inflight)
    gone = _doc(w, SAMPLE["S2"])
    w.select_docs([gone])
    QTest.keyClick(w.table, Qt.Key_Delete)                         # Delete removes, after the confirmation
    assert rec.removes == 1 and "weren't touched" in w.toast.label.text()
    assert w.org.catalog.document(gone) is None and w.org.catalog.one("SELECT COUNT(*) FROM extractions")[0] == 1
    assert source_state(samples) == before                         # originals untouched
    w.import_paths([str(samples / SAMPLE["S2"])])                     # importing again brings it back
    _pump(app, lambda: not w.inflight)
    w.select_docs([d["id"] for d in w.waiting()])
    w.bulk_remove.click()                                          # multi-select remove
    assert w.waiting() == [] and w.windowTitle() == "ClassiFile" and not _notices(w)
    assert w.stack.currentWidget() is w.empty_state                # back to the empty state
    _close(w, rec)


def test_close_notice_and_remembered_categories(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S2"], samples / SAMPLE["S1"]])
    _pump(app, lambda: not w.inflight)
    w.file_docs([_doc(w, SAMPLE["S2"])], "Programming")
    _pump(app, lambda: not w.filing)
    _category_node(w, "Programming").setExpanded(True)
    rec.close_answer = ("back", False)
    w.close()
    assert w.isVisible() and rec.closes == 1 and w.view[0] == DECIDE  # back to the decisions
    rec.close_answer = ("close", True)                             # Close, and don't show this again
    w.close()
    assert not w.isVisible() and w.org.catalog.get_setting("close_notice") == "off"
    w2 = MainWindow(w.org, ask_output_root=False)
    rec2 = Recorder(w2)
    w2.show()
    assert _category_node(w2, "Programming").isExpanded()           # what was expanded is remembered
    w2.show_view(SETTINGS)
    assert not w2.close_toggle.isChecked()
    w2.close()
    assert rec2.closes == 0 and not w2.isVisible()


def _drag(w, paths, kind):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    if kind == "enter":
        w.dragEnterEvent(QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    else:
        w.dropEvent(QDropEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))


def test_drop_overlay(app, samples, make_org, tmp_path):
    w, rec = _window(make_org)
    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    _drag(w, [samples / SAMPLE["S2"], notes], "enter")
    assert w.overlay.isVisible() and w.overlay.title.text() == "Drop files here to import"
    assert "PDF, PPTX, DOCX, ODT" in w.overlay.formats.text() and "notes.txt" in w.overlay.skipped.text()
    w.dragLeaveEvent(QDragLeaveEvent())
    assert not w.overlay.isVisible()
    _drag(w, [samples / SAMPLE["S2"]], "enter")
    assert not w.overlay.skipped.isVisible()
    _drag(w, [samples / SAMPLE["S2"]], "drop")
    assert not w.overlay.isVisible() and w.inflight
    assert _rows(w) == [SAMPLE["S2"]] and w.table.topLevelItem(0).text(2) in ("Reading", "Waiting")
    _pump(app, lambda: not w.inflight)
    assert _rows(w) == [SAMPLE["S2"]]
    _close(w, rec)


def test_details_preview_and_expand(app, samples, office, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S4"], office / "security.pptx"])
    _pump(app, lambda: not w.inflight)
    w.select_docs([_doc(w, SAMPLE["S4"])])
    w.details_toggle.click()
    p = w.details.preview
    assert w.details.isVisible() and not p.image.pixmap().isNull()
    assert p.page_label.text() == "Page 1 of 25" and not p.prev.isEnabled()
    p.next.click()
    assert p.page_label.text() == "Page 2 of 25" and p.prev.isEnabled()
    assert not w.details.open_button.isVisible()                   # nothing to open before filing
    p.expand.click()
    big = w.preview_overlay
    assert big.isVisible() and big.preview.page_label.text() == "Page 2 of 25"
    QTest.keyClick(big, Qt.Key_PageDown)
    assert big.preview.page_label.text() == "Page 3 of 25"
    QTest.keyClick(big, Qt.Key_Escape)
    assert not big.isVisible() and w.details.isVisible()
    w.select_docs([_doc(w, "security.pptx")])                      # no stored thumbnail: the first-lines card
    assert not p.nav.isVisible() or not p.next.isVisible()
    assert p.image.objectName() == "card" and "Network Security Fundamentals" in p.image.text()
    assert "Open" in p.note.text()
    _close(w, rec)


def test_change_output_folder_moves_copies(app, samples, make_org, tmp_path):
    w, rec = _window(make_org, [samples / SAMPLE["S2"], samples / SAMPLE["S1"]])
    _pump(app, lambda: not w.inflight)
    w.file_docs([d["id"] for d in w.waiting()], "Courses")
    _pump(app, lambda: not w.filing)
    old_root = w.org.output_root
    old = sorted((old_root / "Courses").iterdir())
    edited = old[0]
    edited.write_bytes(edited.read_bytes() + b"user edit")         # this copy was changed after filing
    new_root = tmp_path / "new-out"
    new_root.mkdir()
    rec.folder = str(new_root)
    w.show_view(SETTINGS)
    w.change_root.click()
    assert w.org.output_root == new_root.resolve()
    assert edited.exists() and not old[1].exists()                 # edited copy stays; the other moved
    assert (new_root / "Courses" / old[1].name).read_bytes() == (samples / old[1].name).read_bytes()
    assert "Moved 1 copy" in w.toast.label.text() and "1 edited copy stayed" in w.toast.label.text()
    assert str(new_root.resolve()) in w.root_label.text().replace("​", "")
    assert sorted(c["status"] for c in w.org.catalog.copies()) == ["edited", "moved", "published"]
    _close(w, rec)


def test_new_category_button_and_empty_hint(app, make_org):
    w, rec = _window(make_org)
    assert w.cats_empty.isVisible()
    assert w.cats_empty.text() == "No categories yet. Press + to create one, or file a document."
    w.ask_category_name = lambda: "  Course   Notes "
    w.add_category.click()
    assert [c["name"] for c in w.org.catalog.categories()] == ["Course Notes"]
    assert not w.cats_empty.isVisible() and _category_node(w, "Course Notes").text(1) == "0"
    w.add_category.click()                                         # the same name again is refused
    assert "already exists" in w.toast.label.text() and len(w.org.catalog.categories()) == 1
    w.org.startup()                                                # an empty category the user made stays
    assert len(w.org.catalog.categories()) == 1
    w.cats.itemClicked.emit(_category_node(w, "Course Notes"), 0)
    assert w.view[0] == "category" and w.page_title.full == "Course Notes"
    _close(w, rec)


def test_responsive_breakpoints_and_elided_names(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S5"]])
    _pump(app, lambda: not w.inflight)
    w.resize(400, 300)
    _pump(app, lambda: (w.width(), w.height()) == (900, 560))      # never smaller than the minimum
    assert w.sidebar.isHidden() and w.menu_button.isVisible()      # narrower than 1024: a menu button
    w.menu_button.click()
    assert w.sidebar.isVisible()
    w.select_docs([_doc(w, SAMPLE["S5"])])
    w.set_details_open(True)
    assert w.details.isVisible() and w.details.parent() is w.workspace   # over the list
    assert w.table.isColumnHidden(3)                               # no date column when narrow
    w.resize(1920, 1080)
    _pump(app, lambda: w.width() == 1920)
    assert w.sidebar.isVisible() and not w.menu_button.isVisible()
    assert w.details.isVisible() and w.details.parent() is w.content     # beside the list
    assert not w.table.isColumnHidden(3)
    w.resize(1100, 700)
    _pump(app, lambda: w.width() == 1100)
    assert w.details.parent() is w.workspace and w.sidebar.isVisible()
    w.close_details()
    for button in (w.add_button, w.details_toggle):                # button text is never clipped
        assert button.width() >= button.sizeHint().width()
    heights = {x.sizeHint().height() for x in (w.add_button, w.details_toggle, w.sort, w.search)}
    assert len(heights) == 1                                       # dropdown, field and buttons share one height
    from classifile.app.widgets import CHEVRON_DOWN, CHEVRON_RIGHT
    assert all(os.path.isfile(c) for c in (CHEVRON_DOWN, CHEVRON_RIGHT)) and "chevron-down" in w.styleSheet()
    w.page_title.resize(60, 20)
    assert w.page_title.text().endswith("…") and w.page_title.toolTip() == "All documents · 1"
    assert w.table.topLevelItem(0).toolTip(0) == SAMPLE["S5"]
    _close(w, rec)


def test_details_open_beside_the_decision_page(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S4"]])
    _pump(app, lambda: not w.inflight)
    w.resize(1024, 700)
    w.review()
    _item(w, SAMPLE["S4"]).details.click()
    assert w.details.parent() is w.content                         # beside the items even in a narrow window
    w.close_details()
    w.resize(1280, 700)
    w.review()
    item = _item(w, SAMPLE["S4"])
    item.details.click()
    assert w.view[0] == DECIDE and w.stack.currentWidget() is w.decision   # no jump to the document list
    assert w.details.isVisible() and w.details.title.full == SAMPLE["S4"]
    assert w.details.preview.page_label.text() == "Page 1 of 25"
    assert w.details.parent() is w.content                         # beside the items, never over them
    assert w.slide.state() == w.slide.State.Running                # it slides in from the right edge
    _pump(app, lambda: w.slide.state() != w.slide.State.Running)
    item.choose.click()
    _pump(app, lambda: item.confirm.isVisible())
    right = item.confirm.mapTo(w.content, item.confirm.rect().topRight()).x()
    assert right < w.details.x() and w.details.geometry().right() < w.content.width()  # both in view at once
    item.field.setText("My Category")
    item.confirm.click()
    _pump(app, lambda: not w.filing)
    assert w.view[0] == DECIDE and not w.details.isVisible()       # filed: its details close, the page stays
    _close(w, rec)


def test_details_width_does_not_depend_on_scrolling(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S4"]])
    _pump(app, lambda: not w.inflight)
    w.select_docs([_doc(w, SAMPLE["S4"])])
    w.set_details_open(True)
    viewport, widths = w.details.scroll.viewport(), set()
    for height in (1000, 560):                                     # everything fits; an opened section must scroll
        w.resize(1280, height)
        _pump(app, lambda: w.height() == height)
        w.details.locations_section.toggle.click()
        for _ in range(20):
            app.processEvents()
        widths.add(viewport.width())
    # A scroll bar that comes and goes changes the width; the page is then fitted again at another height, and
    # the bar goes or comes again: the panel bounced when a section was opened.
    assert len(widths) == 1
    _close(w, rec)
