import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from classifile.app.main import ALL, DECIDE, DOC, RECENT, SETTINGS, MainWindow  # noqa: E402
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
        self.empties, self.delete_answer, self.new_name = [], True, ""
        w.ask_delete_empty = lambda n: self.empties.append(n) or self.delete_answer
        w.ask_new_name = lambda current: self.new_name

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
    return [_cell(w, i, 0) for i in range(w.table.model().rowCount())]


def _cell(w, row, column, role=Qt.DisplayRole):
    """What the document list shows, as the user sees it (after the view, the search and the sort)."""
    return w.table.model().index(row, column).data(role)


def _item(w, title):
    return next(i for i in w.decision.items if i.title.full == title)


def _rows_of(picker):
    return [picker.list.item(i).text() for i in range(picker.list.count())]


def _pick(picker, text, starts=None):
    """Type into a category picker; with `starts`, choose the first row that begins so. Returns the choice."""
    picker.field.setText(text)
    if starts is not None:
        picker.list.setCurrentRow(next(i for i, r in enumerate(_rows_of(picker)) if r.startswith(starts)))
    return picker.current()


def _cats(w):
    """The sidebar's categories in the order shown: {name: the count beside it}."""
    m = w.cats.model()
    return {m.index(i, 0).data(): m.index(i, 1).data() for i in range(m.rowCount())}


def _click_category(w, name):
    m = w.cats.model()
    w.cats.clicked.emit(m.index(list(_cats(w)).index(name), 0))


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
    assert _cats(w) == {}                                           # only categories the user created

    w.review()
    assert w.stack.currentWidget() is w.decision and len(w.decision.items) == 3 and not _notices(w)
    cst = _item(w, SAMPLE["S1"])
    cover, course = EXPECT["S1.cover_title"], EXPECT["S1.course_line"]   # from the local fixture map
    assert cst.line.text() == f"Suggested new category: {cover}"
    assert cst.primary.text() == "Create && file" and cst.choose.isVisible() and cst.pending.isVisible()
    cst.choose.click()                                              # expands in place
    # two names now: lines that only repeat on some pages are under "More"
    assert cst.expanded.isVisible() and len(_rows_of(cst.picker)) == 2 and cst.more_button.isVisible()
    assert f"New: {cover}\n    on the cover" in _rows_of(cst.picker)
    assert cst.picker.current() is None and not cst.confirm.isEnabled()  # nothing is chosen for the user
    cst.more_button.click()
    cst.picker.list.setCurrentRow(next(i for i, r in enumerate(_rows_of(cst.picker))
                                       if r.startswith(f"New: {course}")))  # choosing a row files nothing
    assert cst.picker.current() == ("new", None, course)
    assert cst.confirm.text() == "Create && file" and cst.confirm.isEnabled()
    assert cst.confirm.toolTip() == f"Create category '{course}' and file"
    assert w.org.catalog.categories() == [] and len(w.waiting()) == 3  # nothing filed yet

    QTest.keyClick(cst.picker.field, Qt.Key_Return)                 # Enter files
    _pump(app, lambda: not w.filing)
    out = w.org.output_root / course / SAMPLE["S1"]
    assert out.exists() and len(w.decision.items) == 2
    assert w.toast.isVisible() and w.toast.label.text() == f"Filed {SAMPLE['S1']} in {course}"
    assert w.toast.action.text() == "Show"
    assert _cats(w) == {course: "1"}                                # a name and its count: documents are in the list
    assert not w.cats.model().hasChildren(w.cats.model().index(0, 0)) and not w.cats.rootIsDecorated()

    lec = _item(w, SAMPLE["S3"])                     # a category exists now: no new one with one click
    assert lec.primary.text() == "Choose category…" and not lec.choose.isVisible()
    lec.primary.click()
    assert lec.expanded.isVisible() and _rows_of(lec.picker)[0] == f"{course} · 1"  # existing first, with counts
    assert _pick(lec.picker, course.lower()) == ("existing", w.org.catalog.categories()[0]["id"], course)
    assert lec.confirm.text() == "File" and _rows_of(lec.picker) == [f"{course} · 1"]  # typed differently: no "Create"
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
    group.choose.click()                                            # one picker for the group
    assert [r.split("\n")[0] for r in _rows_of(group.picker)] == [f"New: {best}"]
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
    _pick(item.picker, "Course Notes", "Create category")
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
    w.org.original_missing = lambda doc_id, source_path=None: False   # it moves between the check and the copy
    original.unlink()
    _item(w, original.name).choose.click()
    item = _item(w, original.name)
    _pick(item.picker, "Course Notes", "Create category")
    item.confirm.click()
    _pump(app, lambda: not w.filing)
    expected = f"The original file is no longer at {original}. Import it again from its new location."
    assert w.notices.items[0] == ("error", f"The new category 'Course Notes' wasn't created, because "
                                  f"{original.name} couldn't be filed. {expected}", "Review")
    assert w.org.catalog.categories() == [] and _cats(w) == {}      # no empty category left
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
    assert {_cell(w, i, 2) for i in range(3)} == {"Waiting"}       # icon plus a word
    w.search.setText("l-2")                                        # search filters by name
    assert _rows(w) == [SAMPLE["S4"]]
    w.search.clear()

    w.select_docs([_doc(w, SAMPLE["S2"]), _doc(w, SAMPLE["S1"])])
    assert w.bulk.isVisible() and w.bulk_count.text() == "2 selected"
    actions = [a.text() for a in w.context_menu(w.selected_ids()).actions()]
    assert actions == ["Remove from ClassiFile"]
    assert w.bulk_file.isEnabled() and not w.bulk_move.isEnabled()  # nothing filed yet
    w.bulk_file.click()                                            # the same picker, in a small window
    dialog = w.picker_dialog
    assert dialog.windowTitle() == "File 2 documents in…" and not dialog.confirm.isEnabled()
    dialog.picker.field.setText("Networking")
    assert dialog.picker.current() is None                         # typing never creates a category by itself
    QTest.keyClick(dialog.picker.field, Qt.Key_Return)             # so Enter does nothing yet
    assert dialog.isVisible() and w.org.catalog.categories() == []
    QTest.keyClick(dialog.picker.field, Qt.Key_Down)               # down to "Create category 'Networking'"
    assert dialog.confirm.text() == "Create && file"
    QTest.keyClick(dialog.picker.field, Qt.Key_Return)
    _pump(app, lambda: not w.filing)
    assert w.toast.label.text() == "Filed 2 documents in Networking"
    cat = w.org.catalog.category_by_key("networking")
    assert len(w.org.catalog.documents(cat["id"])) == 2 and _cats(w) == {"Networking": "2"}
    assert {_cell(w, i, 2) for i in range(3)} == {"", "Waiting"}   # no status once filed

    filed = _doc(w, SAMPLE["S2"])
    w.select_docs([filed])
    assert not w.bulk.isVisible()
    actions = [a.text() for a in w.context_menu([filed]).actions()]
    assert actions == ["Open", "Show in folder", "Details", "Move to…"]  # filed documents can't be removed here
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


def test_close_notice_and_its_setting(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S2"], samples / SAMPLE["S1"]])
    _pump(app, lambda: not w.inflight)
    w.file_docs([_doc(w, SAMPLE["S2"])], "Programming")
    _pump(app, lambda: not w.filing)
    rec.close_answer = ("back", False)
    w.close()
    assert w.isVisible() and rec.closes == 1 and w.view[0] == DECIDE  # back to the decisions
    rec.close_answer = ("close", True)                             # Close, and don't show this again
    w.close()
    assert not w.isVisible() and w.org.catalog.get_setting("close_notice") == "off"
    w2 = MainWindow(w.org, ask_output_root=False)
    rec2 = Recorder(w2)
    w2.show()
    assert _cats(w2) == {"Programming": "1"}
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
    assert _rows(w) == [SAMPLE["S2"]] and _cell(w, 0, 2) in ("Reading", "Waiting")
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
    assert not w.cats_empty.isVisible() and _cats(w) == {"Course Notes": "0"}
    w.add_category.click()                                         # the same name again is refused
    assert "already exists" in w.toast.label.text() and len(w.org.catalog.categories()) == 1
    w.org.startup()                                                # an empty category the user made stays
    assert len(w.org.catalog.categories()) == 1
    _click_category(w, "Course Notes")
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
    assert _cell(w, 0, 0, Qt.ToolTipRole) == SAMPLE["S5"]
    _close(w, rec)


def test_details_open_beside_the_decision_page(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S4"]])
    _pump(app, lambda: not w.inflight)
    w.resize(1024, 700)
    w.review()
    _item(w, SAMPLE["S4"]).details.click()
    assert w.details.parent() is w.content                         # beside the items even in a narrow window
    w.close_details()
    w.resize(1920, 1000)                                           # test fonts are wide: room for both
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
    _pick(item.picker, "My Category", "Create category")
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


def test_no_stray_windows_appear(app, samples, make_org, tmp_path):
    from PySide6.QtCore import QEvent, QObject

    (tmp_path / "src").mkdir()
    twin = tmp_path / "src" / (SAMPLE["S2"].rsplit(".", 1)[0] + " (handout).pdf")  # groups with S2
    twin.write_bytes((samples / SAMPLE["S2"]).read_bytes() + b"\n% another copy\n")

    class Watch(QObject):
        """Records every widget shown as a window of its own (a widget shown before it has a parent is one)."""
        def __init__(self):
            super().__init__()
            self.seen = []

        def eventFilter(self, obj, e):
            if e.type() == QEvent.Show and obj.isWidgetType() and obj.isWindow():
                self.seen.append(type(obj).__name__)
            return False

    watch = Watch()
    app.installEventFilter(watch)
    try:
        w, rec = _window(make_org, [samples / SAMPLE["S2"], samples / SAMPLE["S5"], twin])
        _pump(app, lambda: not w.inflight)
        w.review()
        assert any(i.group for i in w.decision.items)
        for item in list(w.decision.items):
            item.choose.click()
        _item(w, SAMPLE["S5"]).details.click()
        w.leave_pending([_doc(w, SAMPLE["S5"])])                   # any action redraws the items
        w.show_view(ALL)
        w.select_docs([_doc(w, SAMPLE["S5"])])
        w.set_details_open(True)
        w.select_docs([d["id"] for d in w.waiting()])              # the bar for several documents
        w.bulk_file.click()                                        # the picker's own window: the only other one
        w.picker_dialog.reject()
        w.show_view(SETTINGS)
        w.refresh()
        assert watch.seen == ["MainWindow", "PickerDialog"]
    finally:
        app.removeEventFilter(watch)
    _close(w, rec)


def test_the_decision_page_stays_where_it_is_after_filing(app, samples, make_org):
    from PySide6.QtWidgets import QScrollArea

    w, rec = _window(make_org, [samples / SAMPLE[s] for s in ("S1", "S2", "S3", "S4", "S5", "S6")])
    _pump(app, lambda: not w.inflight)
    w.resize(1280, 600)                                            # short: the items need scrolling
    w.review()
    bar = w.decision.findChild(QScrollArea).verticalScrollBar()
    _pump(app, lambda: bar.maximum() > 0)
    item = w.decision.items[1]
    item.choose.click()
    _pick(item.picker, "My Category", "Create category")
    item.confirm.click()                                           # the focused field goes away with its item
    assert bar.value() == 0
    _pump(app, lambda: not w.filing)
    assert bar.value() == 0 and bar.maximum() > 0                  # not dragged to the bottom
    assert w.decision.items[1].hasFocus()                          # the next item took its place
    assert w.toast.isVisible() and w.toast.parent() is w           # the message slides in over the corner
    _pump(app, lambda: w.toast.slide.state() != w.toast.slide.State.Running)
    assert w.toast.geometry().bottom() < w.height() and w.toast.geometry().right() < w.width()
    _close(w, rec)


def test_category_picker_rows_and_keys(app):
    from classifile.app.widgets import CategoryPicker

    p = CategoryPicker()
    assert p.empty.text().startswith("No categories yet") and p.current() is None
    cats = [("a", "Networks", 7), ("b", "algebra", 0), ("c", "Discrete Mathematics", 3), ("d", "Writing", 1)]
    p.set_choices(cats, recent=["d", "c"], suggestions=[("Sampling Theorem", "on the cover"), ("networks", "")])
    assert _rows_of(p) == ["Writing · 1", "Discrete Mathematics · 3", "algebra · 0", "Networks · 7",
                           "New: Sampling Theorem\n    on the cover"]   # recent first, then A–Z; no "New" twin
    assert p.current() is None
    p.field.setText("MATH")                                        # anywhere in the name, ignoring case
    assert _rows_of(p) == ["Discrete Mathematics · 3", "Create category 'MATH'"]
    assert p.current() == ("existing", "c", "Discrete Mathematics")    # typing chooses only what exists
    p.field.setText("  writing ")
    assert _rows_of(p) == ["Writing · 1"]                          # an exact match: no row to create it again
    p.field.setText("Thermodynamics")
    assert _rows_of(p) == ["Create category 'Thermodynamics'"] and p.current() is None
    seen = []
    p.activated.connect(lambda: seen.append("enter"))
    p.cancelled.connect(lambda: seen.append("esc"))
    QTest.keyClick(p.field, Qt.Key_Return)                         # nothing chosen: Enter does nothing
    QTest.keyClick(p.field, Qt.Key_Down)
    assert p.current() == ("new", None, "Thermodynamics")
    QTest.keyClick(p.field, Qt.Key_Return)
    QTest.keyClick(p.field, Qt.Key_Escape)
    assert seen == ["enter", "esc"]
    p.field.setText("s")
    QTest.keyClick(p.field, Qt.Key_Down)
    QTest.keyClick(p.field, Qt.Key_Down)
    QTest.keyClick(p.field, Qt.Key_Up)
    assert p.current() == ("existing", "a", "Networks")           # typing chose the first; down, down, up


def test_no_one_click_creation_once_categories_exist(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE[s] for s in ("S1", "S3", "S4")])
    _pump(app, lambda: not w.inflight)
    w.review()
    assert {i.primary.text() for i in w.decision.items} == {"Create && file"}    # no categories yet
    first = _item(w, SAMPLE["S4"])
    best = first.best
    first.primary.click()
    _pump(app, lambda: not w.filing)
    assert [c["name"] for c in w.org.catalog.categories()] == [best]
    for item in w.decision.items:                                  # from now on a new category takes a choice
        assert item.primary.text() == "Choose category…" and not item.choose.isVisible() and item.best
    item = _item(w, SAMPLE["S3"])
    QTest.keyClick(item, Qt.Key_Return)                            # Enter on the item only opens the choices
    assert item.expanded.isVisible() and len(w.org.catalog.categories()) == 1 and not w.filing
    assert _rows_of(item.picker)[0] == f"{best} · 1" and _rows_of(item.picker)[1].startswith(f"New: {item.best}")
    w.org.create_category(item.best)                               # the top suggestion names an existing category
    w.refresh()
    item = _item(w, SAMPLE["S3"])
    assert item.primary.text() == f"File in {item.best}" and item.choose.isVisible()
    assert item.line.text().startswith(f"Suggested category: {item.best}")
    item.primary.click()
    _pump(app, lambda: not w.filing)
    assert w.org.catalog.document(_doc(w, SAMPLE["S3"]))["status"] == "filed"
    _close(w, rec)


def test_none_of_these_fit_records_the_rejection(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S1"], samples / SAMPLE["S4"]])
    _pump(app, lambda: not w.inflight)
    w.review()
    item = _item(w, SAMPLE["S1"])
    item.choose.click()
    assert item.none_fit.isVisible() and item.none_fit.text() == "None of these fit — type my own"
    assert not item.reasons.isVisible()
    item.picker.field.setText("something")
    item.none_fit.click()
    assert item.picker.field.text() == "" and item.picker.field.placeholderText() == "Type the category you want"
    assert item.picker.field.hasFocus() and _rows_of(item.picker) == []          # the suggested names are gone
    assert item.reasons.isVisible() and not item.none_fit.isVisible() and not item.more_button.isVisible()
    assert [b.text() for b in item.reason_group.buttons()] == [
        "Too narrow", "Too broad", "Wrong topic", "Not a real name", "Couldn't read the document"]
    assert not item.confirm.isEnabled() and item.pending.isVisible()             # no filing without a category
    item.confirm.click()
    assert not w.filing and w.org.catalog.categories() == []
    item.reason_group.buttons()[0].click()                                       # optional, one click
    _pick(item.picker, "Networks", "Create category")
    item.confirm.click()
    _pump(app, lambda: not w.filing)
    cat = w.org.catalog.category_by_key("networks")
    rows = [tuple(r) for r in w.org.catalog.all(
        "SELECT document_id, analyzer_version, reason, category_id FROM suggestion_feedback")]
    assert rows == [(_doc(w, SAMPLE["S1"]), "rules-8", "too narrow", cat["id"])]
    other = _item(w, SAMPLE["S4"])                                               # no reason given; no rejection
    other.primary.click()
    _pick(other.picker, "net")
    other.confirm.click()
    _pump(app, lambda: not w.filing)
    assert w.org.catalog.one("SELECT COUNT(*) FROM suggestion_feedback")[0] == 1
    assert len(w.org.catalog.documents(cat["id"])) == 2
    _close(w, rec)


def test_only_one_suggestion_is_said(app, make_org, tmp_path):
    import pymupdf

    src = tmp_path / "src"
    src.mkdir()
    doc = pymupdf.open()
    for n in range(2):
        doc.new_page().insert_text((72, 100), "Thermal Expansion" if n == 0 else "it gets longer when heated", fontsize=20)
    doc.save(src / "x.pdf")
    doc.close()
    w, rec = _window(make_org, [src / "x.pdf"])
    _pump(app, lambda: not w.inflight)
    w.review()
    assert w.decision.items[0].line.text() == "Suggested new category: Thermal Expansion  ·  Only one suggestion found"
    _close(w, rec)


def test_move_rename_and_delete_from_the_window(app, samples, make_org):
    before = source_state(samples)
    names = [SAMPLE["S1"], SAMPLE["S2"], SAMPLE["S3"]]
    w, rec = _window(make_org, [samples / n for n in names])
    _pump(app, lambda: not w.inflight)
    ids = [_doc(w, n) for n in names]
    for i, cat in zip(ids, ("One", "Two", "Three")):               # one category per document, as it happened
        w.file_docs([i], cat)
        _pump(app, lambda: not w.filing)
    w.toast.hide()
    w.select_docs(ids[:2])
    assert w.bulk_move.isEnabled() and not w.bulk_file.isEnabled()
    w.bulk_move.click()
    dialog = w.picker_dialog
    assert dialog.windowTitle() == "Move 2 documents to…"
    assert _rows_of(dialog.picker) == ["Three · 1", "Two · 1", "One · 1"]   # most recently used first
    assert _pick(dialog.picker, "thr")[2] == "Three" and dialog.confirm.text() == "Move"
    dialog.confirm.click()
    _pump(app, lambda: not w.moving)
    three = w.org.catalog.category_by_key("three")
    assert sorted(d["file_name"] for d in w.org.catalog.documents(three["id"])) == sorted(names)
    assert w.toast.label.text() == "Moved 2 documents to Three."
    assert rec.empties == [2]                                      # asked once, for both empty categories
    assert [c["name"] for c in w.org.catalog.categories()] == ["Three"]
    assert sorted(p.name for p in w.org.output_root.iterdir()) == ["Three"]
    provenance = [r[0] for r in w.org.catalog.all(
        "SELECT provenance FROM memberships WHERE status = 'active' ORDER BY document_id")]
    assert sorted(provenance) == ["user-confirmed", "user-corrected", "user-corrected"]

    menu = w.category_menu(three["id"])
    assert [a.text() for a in menu.actions()] == ["Rename category…", "Delete category"]
    assert not menu.actions()[1].isEnabled()                       # it holds documents
    rec.new_name = "Networking"
    menu.actions()[0].trigger()
    _pump(app, lambda: not w.moving)
    assert w.toast.label.text() == "Renamed to Networking." and _cats(w)["Networking"] == "3"
    assert sorted(p.name for p in (w.org.output_root / "Networking").iterdir()) == sorted(names)
    assert not (w.org.output_root / "Three").exists()

    rec.delete_answer = False
    w.context_menu([ids[0]]).actions()[-1].trigger()               # Move to…, into a new category
    dialog = w.picker_dialog
    _pick(dialog.picker, "Elsewhere", "Create category")
    assert dialog.confirm.text() == "Create && move"
    dialog.confirm.click()
    _pump(app, lambda: not w.moving)
    assert rec.empties == [2]                                      # nothing was left empty: no question
    w.org.create_category("Unused")
    w.refresh()
    unused = w.org.catalog.category_by_key("unused")["id"]
    w.category_menu(unused).actions()[1].trigger()
    assert "Unused" not in [c["name"] for c in w.org.catalog.categories()]
    assert w.toast.label.text() == "Deleted the category."
    assert source_state(samples) == before                         # the originals: untouched throughout
    _close(w, rec)


def test_sidebar_keeps_its_place_and_details_stay_on(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S4"], samples / SAMPLE["S5"]])
    _pump(app, lambda: not w.inflight)
    for n in range(40):
        w.org.create_category(f"Category {n:02d}")
    w.refresh()
    bar = w.cats.verticalScrollBar()
    _pump(app, lambda: bar.maximum() > 0)
    bar.setValue(bar.maximum())
    at = bar.value()
    _click_category(w, "Category 38")
    for _ in range(10):
        app.processEvents()
    assert w.view[0] == "category" and bar.value() == at > 0       # it stays where it was scrolled
    w.refresh()
    for _ in range(10):
        app.processEvents()
    assert bar.value() == at

    w.show_view(ALL)
    w.details_toggle.click()                                       # nothing selected: it opens and says what to do
    assert w.details.isVisible() and w.details.title.full == "Details"
    assert "Select a document" in w.details.facts.text() and not w.details.locations_section.isVisible()
    w.select_docs([_doc(w, SAMPLE["S4"])])
    assert w.details.title.full == SAMPLE["S4"] and w.details.preview.page_label.text() == "Page 1 of 25"
    assert w.details.locations_section.isVisible()
    w.show_view(RECENT)                                            # still on, on another page
    w.select_docs([_doc(w, SAMPLE["S5"])])
    assert w.details.isVisible() and w.details.title.full == SAMPLE["S5"]
    w.select_docs([])
    assert w.details.isVisible() and w.details.title.full == "Details"
    w.details_toggle.click()
    assert not w.details.isVisible()
    _close(w, rec)


def test_a_card_in_use_survives_background_reads(app, samples, make_org):
    from classifile.app import decision

    w, rec = _window(make_org, [samples / SAMPLE["S1"], samples / SAMPLE["S2"]])
    _pump(app, lambda: not w.inflight)
    w.org.create_category("Elsewhere")
    w.review()
    item = _item(w, SAMPLE["S1"])
    item.primary.click()                                           # the choices open; something is typed
    item.picker.field.setText("my draft")
    item.picker.field.setCursorPosition(3)
    assert item.picker.field.hasFocus() and item.expanded.isVisible()
    built, refreshes, make, refresh = [], [], decision.DecisionItem.__init__, w.refresh
    decision.DecisionItem.__init__ = lambda self, *a, **k: (built.append(1), make(self, *a, **k))[1]
    w.refresh = lambda *a, **k: (refreshes.append(k), refresh(*a, **k))[1]
    statements = []
    w.org.catalog.db.set_trace_callback(statements.append)
    try:
        w.import_paths([str(samples / SAMPLE["S3"]), str(samples / SAMPLE["S4"])])
        _pump(app, lambda: not w.inflight)
    finally:
        decision.DecisionItem.__init__ = make
        w.org.catalog.db.set_trace_callback(None)
    assert len(w.decision.items) == 4 and len(built) == 2          # only the two new cards were made
    assert refreshes == [{}, {"recheck": False}, {"recheck": False}]   # once per document read, not twice
    assert _item(w, SAMPLE["S1"]) is item and item.expanded.isVisible()
    assert item.picker.field.text() == "my draft" and item.picker.field.cursorPosition() == 3
    assert item.picker.field.hasFocus()

    statements.clear()                                             # a refresh costs the same whatever the size
    w.org.catalog.db.set_trace_callback(statements.append)
    w.refresh()
    w.org.catalog.db.set_trace_callback(None)
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 5
    assert _item(w, SAMPLE["S1"]) is item and item.picker.field.text() == "my draft"

    w.org.create_category("Brand New")                             # the open list follows the catalog
    w.refresh()
    assert _item(w, SAMPLE["S1"]) is item and item.picker.field.text() == "my draft"
    item.picker.field.setText("brand")
    assert _rows_of(item.picker) == ["Brand New · 0", "Create category 'brand'"]
    w.show_view(ALL)                                               # leaving the page and coming back: still there
    w.review()
    assert _item(w, SAMPLE["S1"]) is item and item.expanded.isVisible() and item.picker.field.text() == "brand"
    w.leave_pending(item.ids)                                      # moved to the end, not rebuilt
    assert w.decision.items[-1] is item and item.expanded.isVisible()
    _close(w, rec)


def test_search_name_and_category_count_and_keys(app, samples, make_org):
    names = [SAMPLE["S1"], SAMPLE["S2"], SAMPLE["S4"]]
    w, rec = _window(make_org, [samples / n for n in names])
    _pump(app, lambda: not w.inflight)
    w.file_docs([_doc(w, SAMPLE["S1"])], "Quantum Optics")
    _pump(app, lambda: not w.filing)
    w.show_view(ALL)
    assert w.search.placeholderText() == "Search all documents…" and not w.result_count.isVisible()
    statements = []
    w.org.catalog.db.set_trace_callback(statements.append)
    w.search.setText("QUANT")                                      # the category matches too
    assert _rows(w) == [SAMPLE["S1"]] and w.result_count.text() == "1 of 3" and w.result_count.isVisible()
    assert w.page_title.full == "All documents · 3"                # the heading keeps the whole count
    w.search.setText("l-2")
    assert _rows(w) == [SAMPLE["S4"]]
    w.search.setText("no such thing")
    assert statements == []                                        # a key reads nothing from the catalog
    w.org.catalog.db.set_trace_callback(None)
    assert w.stack.currentWidget() is w.no_match and w.result_count.text() == "0 of 3"
    assert w.no_match_text.text() == "Nothing here matches “no such thing”."
    w.clear_search.click()
    assert w.search.text() == "" and w.stack.currentWidget() is w.table and len(_rows(w)) == 3

    w.select_docs([_doc(w, SAMPLE["S4"])])
    w.set_details_open(True)
    QTest.keySequence(w.table, QKeySequence(QKeySequence.Find))    # Ctrl+F puts the cursor in the field
    assert w.search.hasFocus()
    QTest.keyClicks(w.search, "l-2")
    QTest.keyClick(w.search, Qt.Key_Escape)                        # Esc clears the text first
    assert w.search.text() == "" and w.details.isVisible()
    QTest.keyClick(w.search, Qt.Key_Escape)                        # and then closes details
    assert not w.details.isVisible()

    w.search.setText("l-2")
    _click_category(w, "Quantum Optics")                           # another view: no hidden text filters it
    assert w.search.text() == "" and w.search.placeholderText() == "Search Quantum Optics…"
    assert _rows(w) == [SAMPLE["S1"]] and w.page_title.full == "Quantum Optics · 1"
    w.show_view(RECENT)
    assert w.search.placeholderText() == "Search recently added…" and len(_rows(w)) == 3

    w.review()                                                     # the same field on the decision page
    assert w.toolbar.isVisible() and not w.sort.isVisible() and not w.details_toggle.isVisible()
    assert w.search.placeholderText() == "Search these documents…"
    cards = list(w.decision.items)
    w.search.setText(SAMPLE["S4"][:6].upper())
    shown = [c for c in cards if c.isVisible()]
    assert w.decision.items == cards and shown == [_item(w, SAMPLE["S4"])]   # hidden, not rebuilt
    assert w.result_count.text() == "1 of 2" and w.page_title.full == "Needs your decision · 2"
    w.search.setText("no such thing")
    assert w.stack.currentWidget() is w.no_match
    QTest.keyClick(w.search, Qt.Key_Escape)
    assert w.stack.currentWidget() is w.decision and all(c.isVisible() for c in cards)
    w.show_view(SETTINGS)
    assert not w.toolbar.isVisible()
    _close(w, rec)


def test_the_list_is_updated_in_place(app, samples, make_org):
    names = [SAMPLE["S1"], SAMPLE["S2"], SAMPLE["S4"]]
    w, rec = _window(make_org, [samples / n for n in names])
    _pump(app, lambda: not w.inflight)

    w.sort.setCurrentText("Name A–Z")
    assert _rows(w) == sorted(names, key=str.casefold)
    doc = _doc(w, SAMPLE["S2"])
    w.select_docs([doc])
    resets = []
    w.docs.modelReset.connect(lambda: resets.append(1))
    w.file_docs([_doc(w, SAMPLE["S1"])], "Quantum Optics")         # another row changes; this one stays selected
    _pump(app, lambda: not w.filing)
    w.refresh()
    assert w.selected_ids() == [doc] and resets == []
    assert _cell(w, _rows(w).index(SAMPLE["S1"]), 1) == "Quantum Optics"
    assert w.document_row(doc)["file_name"] == SAMPLE["S2"] and w.document_row("no such id") is None
    w.sort.setCurrentText("Newest first")                          # what is still being read comes first
    w.import_paths([str(samples / SAMPLE["S5"])])
    assert _rows(w)[0] == SAMPLE["S5"] and _cell(w, 0, 2) == "Reading" and w.selected_ids() == [doc]
    _pump(app, lambda: not w.inflight)
    assert _cell(w, _rows(w).index(SAMPLE["S5"]), 2) == "Waiting" and len(_rows(w)) == 4
    _close(w, rec)


def test_the_list_fits_beside_the_details_panel(app, samples, make_org):
    w, rec = _window(make_org, [samples / SAMPLE["S4"], samples / SAMPLE["S5"]])
    _pump(app, lambda: not w.inflight)
    w.resize(1280, 720)
    _pump(app, lambda: w.width() == 1280 and not w.table.isColumnHidden(3))
    w.select_docs([_doc(w, SAMPLE["S5"])])
    w.set_details_open(True)                                       # beside the list: the list gets narrow
    _pump(app, lambda: w.table.isColumnHidden(3))                  # so the date column goes
    assert w.details.parent() is w.content and w.table.horizontalScrollBar().maximum() == 0
    w.close_details()
    _pump(app, lambda: not w.table.isColumnHidden(3))

    w.org.create_category("Elsewhere")                             # with a category, Enter opens the choices
    w.review()                                                     # Esc in a card's field: the keyboard stays on the card
    item = _item(w, SAMPLE["S4"])
    QTest.keyClick(item, Qt.Key_Return)
    assert item.expanded.isVisible() and item.picker.field.hasFocus()
    QTest.keyClick(item.picker.field, Qt.Key_Escape)
    assert not item.expanded.isVisible() and item.hasFocus()
    _close(w, rec)
