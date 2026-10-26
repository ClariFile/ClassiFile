import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget  # noqa: E402

from classifile.app.main import (  # noqa: E402
    ABOUT, ALL, DECIDE, DOC, HELP, RECENT, SETTINGS, MainWindow, problem_report, safe_reason,
)
from classifile.app.guide import ReportDialog  # noqa: E402
from classifile.app.widgets import GROUP, PANEL, QWIDGETSIZE_MAX, RELATED, reduced_motion  # noqa: E402
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


def _drawn(app, preview):
    """Wait for the page service's answer: previews are drawn in a worker process, off the interface thread."""
    _pump(app, lambda: not preview.busy)


def _doc(w, file_name):
    return next(d["id"] for d in w.org.catalog.all_documents() if d["file_name"] == file_name)


def _rows(w):
    return [_cell(w, i, 0) for i in range(w.table.model().rowCount())]


def _cell(w, row, column, role=Qt.DisplayRole):
    """What the document list shows, as the user sees it (after the view, the search and the sort)."""
    return w.table.model().index(row, column).data(role)


def _item(w, title):
    return next(i for i in w.decision.items if i.title.full == title)


def _said(item):
    """What a decision row offers, in one line: "Suggested category: X", or the sentence it says instead."""
    return f"{item.kind.text()} {item.category.full}" if item.suggestion.isVisibleTo(item) else item.line.text()


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
    assert "Integrations" not in texts and "Part of ClariFile" not in texts     # About has its own page
    assert not w.advanced.content.isVisible()                                   # versions and logs: closed
    w.advanced.toggle.click()
    assert w.advanced.content.isVisible() and "catalog schema" in w.tech.text()
    _pump(app, lambda: w.advanced.content.maximumHeight() == QWIDGETSIZE_MAX, timeout=2)   # grown to its height
    for key, page, words in ((HELP, w.help_page, "What never happens"), (ABOUT, w.about_page, "AGPL-3.0")):
        w.nav[key].click()
        assert w.stack.currentWidget() is page and not w.toolbar.isVisible()
        assert any(words in t for t in page.texts)
    assert "github.com/ClariFile/ClassiFile" in " ".join(w.about_page.texts)
    w.resize(1536, 864)             # no empty band at the right (record A10): cards reach the page's right edge
    for key, page in ((HELP, w.help_page), (ABOUT, w.about_page), (SETTINGS, w.settings_page)):
        w.show_view(key)
        QApplication.processEvents()
        right = page.mapTo(w, page.rect().topRight()).x()
        cards = [c for c in page.findChildren(QFrame, "settingsCard") if c.isVisible()]
        assert cards and all(right - c.mapTo(w, c.rect().topRight()).x() <= 2 * GROUP for c in cards), key
        def beside(lab, c):     # a control to the label's right in its row (a list, a Change… button)
            r = lab.geometry().translated(lab.parentWidget().mapTo(c, QPoint(0, 0)))
            return any(o.isVisible() and not isinstance(o, QLabel) and o.parentWidget() is lab.parentWidget()
                       and o.x() > lab.geometry().right() and o.geometry().translated(
                           o.parentWidget().mapTo(c, QPoint(0, 0))).intersects(r.adjusted(0, 0, 10000, 0))
                       for o in lab.parentWidget().findChildren(QWidget))
        narrow = [lab.text()[:40] for c in cards for lab in c.findChildren(QLabel)     # and their text fills them
                  if lab.isVisible() and lab.wordWrap() and not beside(lab, c) and c.mapTo(w, c.rect().topRight()).x()
                  - lab.mapTo(w, lab.rect().topRight()).x() > PANEL + 2]
        assert not narrow, (key, narrow)
        cut = [lab.text()[:40] for lab in page.findChildren(QLabel)       # and no wrapped text has its lines cut off
               if lab.isVisible() and lab.wordWrap() and lab.height() < lab.heightForWidth(lab.width())]
        assert not cut, (key, cut)
    long = "A long notice that has to wrap across the whole width of the window. " * 6
    w.notices.show_notices([("warning", long, "Review", lambda: None), ("quiet", "Short.", None, None)])
    QApplication.processEvents()        # notice text runs to its action button, or to the notice's edge
    for frame in [w.notices.box.itemAt(i).widget() for i in range(w.notices.box.count())]:
        lab = next(lab for lab in frame.findChildren(QLabel) if lab.text())     # not the icon
        buttons = frame.findChildren(QPushButton)
        edge = buttons[0].geometry().left() if buttons else frame.contentsRect().right()
        assert edge - lab.geometry().right() <= 2 * GROUP, lab.text()[:40]
        assert lab.height() >= lab.heightForWidth(lab.width())                    # no lines cut off
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
    assert _said(cst) == f"Suggested new category: {cover}" and cst.reason.full.startswith("Found on the cover")
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
    d = w.details
    assert (d.category.caption.text(), d.category.value.text()) == ("Filed in", course)   # done, not suggested
    assert d.name.value.text() == SAMPLE["S1"] and d.same_name.isVisible() and not d.copy_name.isVisible()
    assert d.state.value.text().startswith("Filed by you · 20")
    assert d.why.isVisible() and course in d.why.text()           # the reason is shown; the paths are folded
    assert not d.locations.isVisible()
    d.locations_section.toggle.click()
    locations = d.locations.text().replace("​", "")
    assert f"Filed copy: {out}" in locations and "Original: " in locations
    w.details.open_button.click()
    w.details.folder_button.click()
    QTest.keyClick(w.table, Qt.Key_Return)                          # Enter opens a filed copy
    assert rec.opened == [out, out] and rec.shown == [out]
    QTest.keyClick(w.table, Qt.Key_Space)
    assert not w.details.isVisible()
    _close(w, rec)


def test_group_item_files_only_the_listed_documents(app, pdfs, make_org, tmp_path):
    data = (pdfs / "S2.pdf").read_bytes()
    src = tmp_path / "src"
    src.mkdir()
    stem = "S2.pdf".rsplit(".", 1)[0]
    first, second, later = src / "S2.pdf", src / f"{stem} (handout).pdf", src / f"{stem} (again).pdf"
    first.write_bytes(data)
    second.write_bytes(data + b"\n% another copy\n")
    later.write_bytes(data + b"\n% a third copy\n")
    w, rec = _window(make_org, [first, second, pdfs / "S1.pdf"])
    _pump(app, lambda: not w.inflight)
    w.review()
    group = _item(w, "2 documents with the same suggestion")
    assert group.group and group.names.isVisible() and "S2.pdf" in group.names.text()
    assert second.name in group.names.text() and len(w.decision.items) == 2
    pages = group.details.menu().actions()                          # Details: each document of the group
    assert not group.details.isHidden() and sorted(a.text() for a in pages) == sorted(["S2.pdf", second.name])
    pages[1].trigger()
    assert w.details.isVisible() and w.details.doc_id == w.inspected == group.ids[1]
    w.close_details()
    best = group.best
    group.choose.click()                                            # one picker for the group
    assert [r.split("\n")[0] for r in _rows_of(group.picker)] == [f"New: {best}"]
    group.primary.click()
    _pump(app, lambda: not w.filing)
    cat = w.org.catalog.category_by_key(best.casefold())
    assert sorted(d["file_name"] for d in w.org.catalog.documents(cat["id"])) == sorted([second.name, "S2.pdf"])
    assert w.toast.label.text() == f"Filed 2 documents in {best}"
    assert [d["file_name"] for d in w.waiting()] == ["S1.pdf"]
    w.import_paths([str(later)])                                    # no rule was made: the next one still asks
    _pump(app, lambda: not w.inflight)
    assert w.org.catalog.document(_doc(w, later.name))["status"] == "needs_decision"
    assert len(w.org.catalog.documents(cat["id"])) == 2
    _close(w, rec)


def test_missing_original_on_decision_page_and_locate(app, pdfs, make_org, tmp_path):
    src, moved = tmp_path / "Downloads", tmp_path / "Documents"
    src.mkdir()
    moved.mkdir()
    original = src / "handout 3,2024.pdf"
    original.write_bytes((pdfs / "S2.pdf").read_bytes())
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
    other.write_bytes((pdfs / "S1.pdf").read_bytes())
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


def test_failed_filing_leaves_nothing_half_done_and_the_error_stays(app, pdfs, make_org, tmp_path):
    (tmp_path / "src").mkdir()
    original = tmp_path / "src" / "handout 3,2024.pdf"
    original.write_bytes((pdfs / "S2.pdf").read_bytes())
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
    assert not w.toast.label.text().startswith("Filed")            # only the import's summary was said
    w.show_view(ALL)
    w.refresh()
    assert w.notices.items[0][0] == "error"                        # errors stay until resolved
    report = problem_report(w.org.catalog)          # Help, "Copy problem report": no names, paths or document text
    text = " ".join(t for (t,) in w.org.catalog.all("SELECT text FROM extraction_units"))
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 20]
    assert lines and not any(ln in report for ln in lines)
    assert original.stem not in report and str(tmp_path) not in report and "Course Notes" not in report
    assert "the original file had moved" in report and "needs_decision 1" in report
    assert safe_reason("encrypted PDF") == "encrypted PDF" and "C:" not in safe_reason("corrupt or unreadable C:\\x")
    dialog = ReportDialog(w, report)                # shown in full first; Copy goes to the clipboard only
    dialog.copy.click()
    assert dialog.text.toPlainText() == report == QApplication.clipboard().text()
    dialog.close()
    w.remove_docs([_doc(w, original.name)])
    assert not _notices(w)
    _close(w, rec)


def test_bulk_bar_context_menu_keyboard_and_search(app, pdfs, make_org):
    names = ["S2.pdf", "S1.pdf", "S4.pdf"]
    w, rec = _window(make_org, [pdfs / n for n in names])
    _pump(app, lambda: not w.inflight)
    assert sorted(_rows(w)) == sorted(names) and w.page_title.full == "All documents · 3"
    assert {_cell(w, i, 2) for i in range(3)} == {"Waiting"}       # icon plus a word
    w.search.setText("s4")                                        # search filters by name
    assert _rows(w) == ["S4.pdf"]
    w.search.clear()

    w.select_docs([_doc(w, "S2.pdf"), _doc(w, "S1.pdf")])
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
    assert {_cell(w, i, 2) for i in range(3)} == {"Approved", "Waiting"}   # filed by the user's choice

    filed = _doc(w, "S2.pdf")
    w.select_docs([filed])
    assert not w.bulk.isVisible()
    actions = [a.text() for a in w.context_menu([filed]).actions()]
    assert actions == ["Open", "Show in folder", "Details", "Also belongs to…", "Move to…"]  # never removed here
    waiting = _doc(w, "S4.pdf")
    actions = [a.text() for a in w.context_menu([waiting]).actions()]
    assert actions == ["Details", "Remove from ClassiFile"]
    w.select_docs([waiting])
    QTest.keyClick(w.table, Qt.Key_Return)                         # Enter on a waiting document: decide
    assert w.view[0] == DECIDE
    _close(w, rec)


def test_remove_waiting_documents(app, pdfs, make_org):
    before = source_state(pdfs)
    w, rec = _window(make_org, [pdfs / "S2.pdf", pdfs / "S1.pdf"])
    _pump(app, lambda: not w.inflight)
    gone = _doc(w, "S2.pdf")
    w.select_docs([gone])
    QTest.keyClick(w.table, Qt.Key_Delete)                         # Delete removes, after the confirmation
    assert rec.removes == 1 and "weren't touched" in w.toast.label.text()
    assert w.org.catalog.document(gone) is None and w.org.catalog.one("SELECT COUNT(*) FROM extractions")[0] == 1
    assert source_state(pdfs) == before                         # originals untouched
    w.import_paths([str(pdfs / "S2.pdf")])                     # importing again brings it back
    _pump(app, lambda: not w.inflight)
    w.select_docs([d["id"] for d in w.waiting()])
    w.bulk_remove.click()                                          # multi-select remove
    assert w.waiting() == [] and w.windowTitle() == "ClassiFile" and not _notices(w)
    assert w.stack.currentWidget() is w.empty_state                # back to the empty state
    _close(w, rec)


def test_close_notice_and_its_setting(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S2.pdf", pdfs / "S1.pdf"])
    _pump(app, lambda: not w.inflight)
    w.file_docs([_doc(w, "S2.pdf")], "Programming")
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


def test_drop_overlay(app, pdfs, make_org, tmp_path):
    w, rec = _window(make_org)
    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    _drag(w, [pdfs / "S2.pdf", notes], "enter")
    assert w.overlay.isVisible() and w.overlay.title.text() == "Drop files here to import"
    assert "PDF, PPTX, DOCX, ODT" in w.overlay.formats.text() and "notes.txt" in w.overlay.skipped.text()
    w.dragLeaveEvent(QDragLeaveEvent())
    assert not w.overlay.isVisible()
    _drag(w, [pdfs / "S2.pdf"], "enter")
    assert not w.overlay.skipped.isVisible()
    _drag(w, [pdfs / "S2.pdf"], "drop")
    assert not w.overlay.isVisible() and w.inflight
    assert _rows(w) == ["S2.pdf"] and _cell(w, 0, 2) in ("Reading", "Waiting")
    _pump(app, lambda: not w.inflight)
    assert _rows(w) == ["S2.pdf"]
    _close(w, rec)


def test_details_preview_and_expand(app, pdfs, office, make_org):
    w, rec = _window(make_org, [pdfs / "S4.pdf", office / "security.pptx"])
    _pump(app, lambda: not w.inflight)
    w.select_docs([_doc(w, "S4.pdf")])
    w.details_toggle.click()
    p = w.details.preview
    _drawn(app, p)
    assert w.details.isVisible() and not p.image.pixmap().isNull()
    assert p.page_label.text() == "Page 1 of 3" and not p.prev.isEnabled()
    p.next.click()
    assert p.page_label.text() == "Page 2 of 3" and p.prev.isEnabled()      # at once, before the picture
    _drawn(app, p)
    assert not w.details.open_button.isVisible()                   # nothing to open before filing
    p.expand.click()
    big = w.preview_overlay
    _drawn(app, big.preview)
    assert big.isVisible() and big.preview.page_label.text() == "Page 2 of 3"
    QTest.keyClick(big, Qt.Key_PageDown)
    assert big.preview.page_label.text() == "Page 3 of 3"
    QTest.keyClick(big, Qt.Key_Escape)
    assert not big.isVisible() and w.details.isVisible()
    w.select_docs([_doc(w, "security.pptx")])                      # no stored thumbnail: a plain sentence
    _drawn(app, p)
    assert not p.nav.isVisible() or not p.next.isVisible()
    assert p.image.text() == "No page picture is stored in this file."    # never the document's text (A10)
    assert "Open" in p.note.text()
    _close(w, rec)


def test_change_output_folder_moves_copies(app, pdfs, make_org, tmp_path):
    w, rec = _window(make_org, [pdfs / "S2.pdf", pdfs / "S1.pdf"])
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
    assert (new_root / "Courses" / old[1].name).read_bytes() == (pdfs / old[1].name).read_bytes()
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


def test_responsive_breakpoints_and_elided_names(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S5.pdf"])
    _pump(app, lambda: not w.inflight)
    w.resize(400, 300)
    _pump(app, lambda: (w.width(), w.height()) == (900, 560))      # never smaller than the minimum
    assert w.sidebar.isHidden() and w.menu_button.isVisible()      # narrower than 1024: a menu button
    w.menu_button.click()
    assert w.sidebar.isVisible()
    w.select_docs([_doc(w, "S5.pdf")])
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
    assert _cell(w, 0, 0, Qt.ToolTipRole) == "S5.pdf"
    _close(w, rec)


def test_details_open_beside_the_decision_page(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S4.pdf"])
    _pump(app, lambda: not w.inflight)
    w.resize(1024, 700)
    w.review()
    item = _item(w, "S4.pdf")
    item.details.click()                                           # too narrow for both: over the list, a way back
    assert w.details.parent() is w.workspace and w.details.back.isVisible() and item.inspected
    assert (w.details.category.caption.text(), w.details.category.value.text()) == ("Suggested new category", item.best)
    w.details.back.click()
    assert not w.details.isVisible() and not item.inspected and item.hasFocus()   # back on the row it looked at
    w.resize(1920, 1000)                                           # test fonts are wide: room for both
    w.review()
    item = _item(w, "S4.pdf")
    right = lambda: item.more_menu.mapTo(item, item.more_menu.rect().topRight()).x()
    _pump(app, lambda: item.width() > 1040 and right() >= item.width() - 2 * RELATED)
    assert item.width() >= w.decision.width() - 2 * GROUP - 2 * RELATED   # the whole width, on wide screens too
    side = lambda: item.action_bar.y() < item.suggestion.geometry().bottom()
    assert side()                                                  # beside the name and the suggestion
    assert item.number.text() == "1." and not item.details.isChecked()
    item.details.click()
    _pump(app, lambda: w.details.isVisible() and w.details.parent() is w.content)
    assert item.details.isChecked() and item.inspected and side()  # room for both: nothing moves
    item.details.click()                                           # Details again closes them
    assert not w.details.isVisible() and not item.details.isChecked() and w.inspected is None
    QTest.mouseClick(item.title, Qt.LeftButton)                    # a click on the row inspects it, files nothing
    assert w.view[0] == DECIDE and w.stack.currentWidget() is w.decision   # no jump to the document list
    assert w.details.isVisible() and w.details.title.full == "S4.pdf" and not w.filing
    assert w.details.preview.page_label.text() == "Page 1 of 3"
    assert w.details.parent() is w.content                         # beside the rows
    assert w.slide.state() == w.slide.State.Running or reduced_motion()   # it slides in from the right edge
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


def test_details_width_does_not_depend_on_scrolling(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S4.pdf"])
    _pump(app, lambda: not w.inflight)
    w.select_docs([_doc(w, "S4.pdf")])
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


def test_no_stray_windows_appear(app, pdfs, make_org, tmp_path):
    from PySide6.QtCore import QEvent, QObject

    (tmp_path / "src").mkdir()
    twin = tmp_path / "src" / ("S2.pdf".rsplit(".", 1)[0] + " (handout).pdf")  # groups with S2
    twin.write_bytes((pdfs / "S2.pdf").read_bytes() + b"\n% another copy\n")

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
        w, rec = _window(make_org, [pdfs / "S2.pdf", pdfs / "S5.pdf", twin])
        _pump(app, lambda: not w.inflight)
        w.review()
        assert any(i.group for i in w.decision.items)
        for item in list(w.decision.items):
            item.choose.click()
        _item(w, "S5.pdf").details.click()
        w.leave_pending([_doc(w, "S5.pdf")])                   # any action redraws the items
        w.show_view(ALL)
        w.select_docs([_doc(w, "S5.pdf")])
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


def test_the_decision_page_stays_where_it_is_after_filing(app, pdfs, make_org):
    from PySide6.QtWidgets import QScrollArea

    w, rec = _window(make_org, [pdfs / f"{s}.pdf" for s in ("S1", "S2", "S3", "S4", "S5", "S6")])
    _pump(app, lambda: not w.inflight)
    w.resize(1280, 600)                                            # short: the items need scrolling
    w.review()
    bar = w.decision.findChild(QScrollArea).verticalScrollBar()
    _pump(app, lambda: bar.maximum() > 0)
    area = w.decision.findChild(QScrollArea)
    last = w.decision.items[-1]                                    # its choices would open below the window:
    bar.setValue(bar.maximum() // 2)
    (last.choose if last.choose.isVisible() else last.primary).click()
    below = lambda: last.expanded.mapTo(area.viewport(), last.expanded.rect().bottomLeft()).y()
    _pump(app, lambda: 0 < below() <= area.viewport().height())    # the page scrolls them into view
    assert last.expanded.isVisible()
    last.toggle_expanded()
    bar.setValue(0)
    item = w.decision.items[1]
    item.choose.click()
    _pick(item.picker, "My Category", "Create category")
    at = bar.value()
    item.confirm.click()                                           # the focused field goes away with its item
    assert bar.value() == at
    _pump(app, lambda: not w.filing)
    assert bar.value() == at and bar.maximum() > at                # not dragged to the bottom
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


def test_no_one_click_creation_once_categories_exist(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / f"{s}.pdf" for s in ("S1", "S3", "S4")])
    _pump(app, lambda: not w.inflight)
    w.review()
    assert {i.primary.text() for i in w.decision.items} == {"Create && file"}    # no categories yet
    first = _item(w, "S4.pdf")
    best = first.best
    first.primary.click()
    _pump(app, lambda: not w.filing)
    assert [c["name"] for c in w.org.catalog.categories()] == [best]
    for item in w.decision.items:                                  # from now on a new category takes a choice
        assert item.primary.text() == "Choose category…" and not item.choose.isVisible() and item.best
    item = _item(w, "S3.pdf")
    QTest.keyClick(item, Qt.Key_Return)                            # Enter on the item only opens the choices
    assert item.expanded.isVisible() and len(w.org.catalog.categories()) == 1 and not w.filing
    assert _rows_of(item.picker)[0] == f"{best} · 1" and _rows_of(item.picker)[1].startswith(f"New: {item.best}")
    w.org.create_category(item.best)                               # the top suggestion names an existing category
    w.refresh()
    item = _item(w, "S3.pdf")
    assert item.primary.text() == f"File in {item.best}" and item.choose.isVisible()
    assert _said(item) == f"Suggested category: {item.best}"
    item.primary.click()
    _pump(app, lambda: not w.filing)
    assert w.org.catalog.document(_doc(w, "S3.pdf"))["status"] == "filed"
    _close(w, rec)


def test_none_of_these_fit_records_the_rejection(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S1.pdf", pdfs / "S4.pdf"])
    _pump(app, lambda: not w.inflight)
    w.review()
    item = _item(w, "S1.pdf")
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
    assert rows == [(_doc(w, "S1.pdf"), "rules-8", "too narrow", cat["id"])]
    other = _item(w, "S4.pdf")                                               # no reason given; no rejection
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
    item = w.decision.items[0]
    assert _said(item) == "Suggested new category: Thermal Expansion"
    assert item.reason.full == "Found on the cover  ·  Only one suggestion found"
    _close(w, rec)


def test_move_rename_and_delete_from_the_window(app, pdfs, make_org):
    before = source_state(pdfs)
    names = ["S1.pdf", "S2.pdf", "S3.pdf"]
    w, rec = _window(make_org, [pdfs / n for n in names])
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
    assert source_state(pdfs) == before                         # the originals: untouched throughout
    _close(w, rec)


def test_sidebar_keeps_its_place_and_details_stay_on(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S4.pdf", pdfs / "S5.pdf"])
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
    assert "Select a document" in w.details.hint.text() and not w.details.locations_section.isVisible()
    w.select_docs([_doc(w, "S4.pdf")])
    _drawn(app, w.details.preview)
    assert w.details.title.full == "S4.pdf" and w.details.preview.page_label.text() == "Page 1 of 3"
    assert w.details.locations_section.isVisible()
    w.show_view(RECENT)                                            # still on, on another page
    w.select_docs([_doc(w, "S5.pdf")])
    assert w.details.isVisible() and w.details.title.full == "S5.pdf"
    w.select_docs([])
    assert w.details.isVisible() and w.details.title.full == "Details"
    w.details_toggle.click()
    assert not w.details.isVisible()
    _close(w, rec)


def test_a_card_in_use_survives_background_reads(app, pdfs, make_org):
    from classifile.app import decision

    w, rec = _window(make_org, [pdfs / "S1.pdf", pdfs / "S2.pdf"])
    _pump(app, lambda: not w.inflight)
    w.org.create_category("Elsewhere")
    w.review()
    item = _item(w, "S1.pdf")
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
        w.import_paths([str(pdfs / "S3.pdf"), str(pdfs / "S4.pdf")])
        _pump(app, lambda: not w.inflight)
    finally:
        decision.DecisionItem.__init__ = make
        w.org.catalog.db.set_trace_callback(None)
    assert len(w.decision.items) == 4 and len(built) == 2          # only the two new cards were made
    assert refreshes == [{}, {"recheck": False}, {"recheck": False}]   # once per document read, not twice
    assert _item(w, "S1.pdf") is item and item.expanded.isVisible()
    assert item.picker.field.text() == "my draft" and item.picker.field.cursorPosition() == 3
    assert item.picker.field.hasFocus()

    statements.clear()                                             # a refresh costs the same whatever the size
    w.org.catalog.db.set_trace_callback(statements.append)
    w.refresh()
    w.org.catalog.db.set_trace_callback(None)
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 6   # with "Check these"
    assert _item(w, "S1.pdf") is item and item.picker.field.text() == "my draft"

    w.org.create_category("Brand New")                             # the open list follows the catalog
    w.refresh()
    assert _item(w, "S1.pdf") is item and item.picker.field.text() == "my draft"
    item.picker.field.setText("brand")
    assert _rows_of(item.picker) == ["Brand New · 0", "Create category 'brand'"]
    w.show_view(ALL)                                               # leaving the page and coming back: still there
    w.review()
    assert _item(w, "S1.pdf") is item and item.expanded.isVisible() and item.picker.field.text() == "brand"
    w.leave_pending(item.ids)                                      # moved to the end, not rebuilt
    assert w.decision.items[-1] is item and item.expanded.isVisible()
    _close(w, rec)


def test_search_name_and_category_count_and_keys(app, pdfs, make_org):
    names = ["S1.pdf", "S2.pdf", "S4.pdf"]
    w, rec = _window(make_org, [pdfs / n for n in names])
    _pump(app, lambda: not w.inflight)
    w.file_docs([_doc(w, "S1.pdf")], "Quantum Optics")
    _pump(app, lambda: not w.filing)
    w.show_view(ALL)
    assert w.search.placeholderText() == "Search all documents…" and not w.result_count.isVisible()
    statements = []
    w.org.catalog.db.set_trace_callback(statements.append)
    w.search.setText("QUANT")                                      # the category matches too
    assert _rows(w) == ["S1.pdf"] and w.result_count.text() == "1 of 3" and w.result_count.isVisible()
    assert w.page_title.full == "All documents · 3"                # the heading keeps the whole count
    w.search.setText("s4")
    assert _rows(w) == ["S4.pdf"]
    w.search.setText("no such thing")
    assert statements == []                                        # a key reads nothing from the catalog
    w.org.catalog.db.set_trace_callback(None)
    assert w.stack.currentWidget() is w.no_match and w.result_count.text() == "0 of 3"
    assert w.no_match_text.text() == "Nothing here matches “no such thing”."
    w.clear_search.click()
    assert w.search.text() == "" and w.stack.currentWidget() is w.table and len(_rows(w)) == 3

    w.select_docs([_doc(w, "S4.pdf")])
    w.set_details_open(True)
    QTest.keySequence(w.table, QKeySequence(QKeySequence.Find))    # Ctrl+F puts the cursor in the field
    assert w.search.hasFocus()
    QTest.keyClicks(w.search, "s4")
    QTest.keyClick(w.search, Qt.Key_Escape)                        # Esc clears the text first
    assert w.search.text() == "" and w.details.isVisible()
    QTest.keyClick(w.search, Qt.Key_Escape)                        # and then closes details
    assert not w.details.isVisible()

    w.search.setText("s4")
    _click_category(w, "Quantum Optics")                           # another view: no hidden text filters it
    assert w.search.text() == "" and w.search.placeholderText() == "Search Quantum Optics…"
    assert _rows(w) == ["S1.pdf"] and w.page_title.full == "Quantum Optics · 1"
    w.show_view(RECENT)
    assert w.search.placeholderText() == "Search recently added…" and len(_rows(w)) == 3

    w.review()                                                     # the same field on the decision page
    assert w.toolbar.isVisible() and not w.sort.isVisible() and not w.details_toggle.isVisible()  # per row instead
    assert w.search.placeholderText() == "Search these documents…"
    first = w.decision.items[0]
    first.details.click()                                          # on: beside that row's document
    assert w.details.isVisible() and w.inspected == first.ids[0] == w.details.doc_id and first.details.isChecked()
    first.details.click()
    assert w.inspected is None and not w.details_open and not first.details.isChecked()
    cards = list(w.decision.items)
    w.search.setText("S4.pdf"[:6].upper())
    shown = [c for c in cards if c.isVisible()]
    assert w.decision.items == cards and shown == [_item(w, "S4.pdf")]   # hidden, not rebuilt
    assert w.result_count.text() == "1 of 2" and w.page_title.full == "Needs your decision · 2"
    w.search.setText("no such thing")
    assert w.stack.currentWidget() is w.no_match
    QTest.keyClick(w.search, Qt.Key_Escape)
    assert w.stack.currentWidget() is w.decision and all(c.isVisible() for c in cards)
    w.show_view(SETTINGS)
    assert not w.toolbar.isVisible()
    _close(w, rec)


def test_the_list_is_updated_in_place(app, pdfs, make_org):
    names = ["S1.pdf", "S2.pdf", "S4.pdf"]
    w, rec = _window(make_org, [pdfs / n for n in names])
    _pump(app, lambda: not w.inflight)

    w.sort.setCurrentText("Name A–Z")
    assert _rows(w) == sorted(names, key=str.casefold)
    doc = _doc(w, "S2.pdf")
    w.select_docs([doc])
    resets = []
    w.docs.modelReset.connect(lambda: resets.append(1))
    w.file_docs([_doc(w, "S1.pdf")], "Quantum Optics")         # another row changes; this one stays selected
    _pump(app, lambda: not w.filing)
    w.refresh()
    assert w.selected_ids() == [doc] and resets == []
    assert _cell(w, _rows(w).index("S1.pdf"), 1) == "Quantum Optics"
    assert w.document_row(doc)["file_name"] == "S2.pdf" and w.document_row("no such id") is None
    w.sort.setCurrentText("Newest first")                          # what is still being read comes first
    w.import_paths([str(pdfs / "S5.pdf")])
    assert _rows(w)[0] == "S5.pdf" and _cell(w, 0, 2) == "Reading" and w.selected_ids() == [doc]
    _pump(app, lambda: not w.inflight)
    assert _cell(w, _rows(w).index("S5.pdf"), 2) == "Waiting" and len(_rows(w)) == 4
    _close(w, rec)


def test_the_list_fits_beside_the_details_panel(app, pdfs, make_org):
    w, rec = _window(make_org, [pdfs / "S4.pdf", pdfs / "S5.pdf"])
    _pump(app, lambda: not w.inflight)
    w.resize(1280, 720)
    _pump(app, lambda: w.width() == 1280 and not w.table.isColumnHidden(3))
    w.select_docs([_doc(w, "S5.pdf")])
    w.set_details_open(True)                                       # beside the list: the list gets narrow
    _pump(app, lambda: w.table.isColumnHidden(3))                  # so the date column goes
    assert w.details.parent() is w.content and w.table.horizontalScrollBar().maximum() == 0
    w.close_details()
    _pump(app, lambda: not w.table.isColumnHidden(3))

    w.org.create_category("Elsewhere")                             # with a category, Enter opens the choices
    w.review()                                                     # Esc in a card's field: the keyboard stays on the card
    item = _item(w, "S4.pdf")
    QTest.keyClick(item, Qt.Key_Return)
    assert item.expanded.isVisible() and item.picker.field.hasFocus()
    QTest.keyClick(item.picker.field, Qt.Key_Escape)
    assert not item.expanded.isVisible() and item.hasFocus()
    _close(w, rec)


def test_cards_offer_the_best_matching_categories_once_matching_is_updated(app, make_org, tmp_path):
    from test_matching import SUBJECTS, _add, _pdf
    from classifile.organizer import read_and_analyze

    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        for subject in SUBJECTS:
            _add(org, src, subject, n)
    known = org.catalog.document(_add(org, src, "Networks", 7, file_it=False))["file_name"]
    _pdf(src / "unknown.pdf", "zebra giraffe antelope savanna migration herd", 1)   # none of the three subjects
    org.record(src / "unknown.pdf", *read_and_analyze(src / "unknown.pdf"))
    org.set_auto_level("off")                                      # this test is about the cards: everything asks

    w, rec = _window(make_org)
    w.review()
    assert all(not i.matches for i in w.decision.items)            # nothing is learned until the user asks
    w.show_view(SETTINGS)
    assert "hasn't learned your categories yet" in w.matching_label.text()
    assert "once 10 documents are filed in at least two categories: 9 so far, in 3 categories" in         w.matching_label.text() and "Update matching starts it now" in w.matching_label.text()
    w.matching_button.click()
    assert not w.matching_button.isEnabled()                       # off the interface thread
    _pump(app, lambda: w.matching_button.isEnabled())
    assert w.toast.label.text() == "Matching updated (version 1): 9 documents in 3 categories."
    assert w.matching_label.text().startswith("Learned from 9 documents in 3 categories on ")
    assert "matching version 1" in w.tech.text()                      # the version: in Advanced
    assert "Matching can learn from 9 documents you filed, confirmed or gave as examples" in w.tech.text()
    assert "Left out" not in w.tech.text()
    assert w.matching_label.text().endswith("Nothing was filed or moved since.")

    w.review()
    item, other = _item(w, known), _item(w, "unknown.pdf")
    assert item.matches[0][:2] == ("Networks", 3) and len(item.matches) == 3   # ranked, the best first
    assert _said(item) == "Suggested category: Networks" and item.primary.text() == "File in Networks"
    words = item.reason.full.removeprefix("Similar to 3 documents in Networks (").removesuffix(")").split(", ")
    assert 2 <= len(words) <= 4 and set(words) <= set(SUBJECTS["Networks"].split())   # the words it shares
    assert item.others.isVisible() and item.others.text().count("<a ") == 2   # the other two: quiet, one click
    shown = " ".join([item.reason.full, item.others.text(), item.others.toolTip(), item.primary.text()])
    assert "%" not in shown and not any(a.isdigit() and b == "." for a, b in zip(shown, shown[1:]))  # no scores
    assert item.choose.isVisible() and not item.expanded.isVisible()       # new names only under "Choose another…"
    item.choose.click()
    assert _rows_of(item.picker)[:3] == [f"{name} · {n}" for name, n, _ in item.matches]   # the matches lead
    item.toggle_expanded()
    assert not other.matches and not other.others.isVisible()              # no category fits: a new name instead
    assert _said(other).startswith("Suggested new category: ")
    assert other.reason.full == "No close match among your categories"
    assert other.primary.text() == "Choose category…"

    second = item.matches[1][0]
    item.others.linkActivated.emit("1")                            # any of the three files with one click
    _pump(app, lambda: not w.filing)
    assert w.toast.label.text() == f"Filed {known} in {second}"
    assert [d["file_name"] for d in w.waiting()] == ["unknown.pdf"]
    w.show_view(SETTINGS)
    assert "1 document filed or moved since: it learns them by itself at 10" in w.matching_label.text()
    w.matching_button.click()
    _pump(app, lambda: w.matching_button.isEnabled())
    assert w.toast.label.text().startswith("Matching updated (version 2): 10 documents in 3 categories; your "
                                           "category first for ")
    assert "(the version before: " in w.matching_log.text()          # both results, in Settings too
    w.matching_button.click()
    _pump(app, lambda: w.matching_button.isEnabled())
    assert w.toast.label.text() == "Matching is already up to date."
    _close(w, rec)


def test_a_clear_match_is_filed_automatically_and_listed_with_its_reason(app, make_org, tmp_path):
    from classifile import matching
    from classifile.app.main import AUTO, AUTO_LEVELS
    from test_matching import SUBJECTS, _add, _pdf

    assert {name for name, _ in AUTO_LEVELS} == set(matching.LEVELS) | {"off"}
    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    for n in range(2):
        _add(org, src, "Poetry", n)                                # too few confirmed documents to file into
    org.update_matching()
    for name, subject, n in (("clear.pdf", "Networks", 7), ("small.pdf", "Poetry", 6), ("later.pdf", "Algebra", 5)):
        _pdf(src / name, SUBJECTS[subject], n)
    _pdf(src / "torn.pdf", "matrix router vector packet eigenvalue switch", 0)   # two subjects at once

    w, rec = _window(make_org, [src / "clear.pdf", src / "small.pdf", src / "torn.pdf"])
    _pump(app, lambda: not w.inflight and not w.filing and not w.auto_running)
    assert w.toast.label.text() == "Filed 1 automatically · 2 need you" and w.toast.action.text() == "Review"
    assert sorted(d["file_name"] for d in w.waiting()) == ["small.pdf", "torn.pdf"]   # these two ask the user
    assert w.auto_count.text() == "1" and w.decide_count.text() == "2"
    row = next(r for r in range(w.filter.rowCount()) if _cell(w, r, 0) == "clear.pdf")
    assert _cell(w, row, 2) == "Filed automatically" and _cell(w, row, 1) == "Networks"   # not "Approved"

    w.toast.action.click()                                         # Review: the two that need the user
    assert w.view[0] == "decide"
    w.show_view(AUTO)                                              # what the app filed by itself
    assert w.view[0] == AUTO and w.stack.currentWidget() is w.auto_page
    assert w.page_title.full == "Filed automatically · 1" and w.toolbar.isVisible() and not w.sort.isVisible()
    item = w.auto_page.items[0]
    assert item.title.full == "clear.pdf" and item.category.full == "Networks"
    assert item.status_word.text() == "Not reviewed"
    QTest.mouseClick(item.title, Qt.LeftButton)                    # a click inspects; it confirms nothing
    d = w.details
    assert d.isVisible() and d.title.full == "clear.pdf" and item.inspected
    assert (d.category.caption.text(), d.category.value.text()) == ("Filed in", "Networks")
    assert d.state.value.text().startswith("Filed automatically · not reviewed yet")
    assert d.why.text().startswith("Filed automatically. Similar to 3 documents in Networks (")   # with key words
    assert w.org.catalog.document_row(_doc(w, "clear.pdf"))["provenance"] == "machine-assigned"
    QTest.keyClick(item, Qt.Key_Escape)
    assert not d.isVisible() and item.hasFocus()
    w.review()
    small = _item(w, "small.pdf")
    assert small.matches[0][:2] == ("Poetry", 2) and small.primary.text() == "File in Poetry"   # waits, with the three

    w.show_view(AUTO)
    w.auto_page.items[0].move.click()                              # one click to the picker: the user's correction
    dialog = w.picker_dialog
    assert dialog.windowTitle() == "Move 1 document to…"
    assert _pick(dialog.picker, "alg")[2] == "Algebra"
    dialog.confirm.click()
    _pump(app, lambda: not w.moving)
    assert [i.status_word.text() for i in w.auto_page.items] == ["Moved by you"]   # it stays where it was
    assert not w.auto_page.items[0].move.isVisible() and w.auto_count.text() == ""
    w.show_view(ALL)
    w.show_view(AUTO)                                              # once the page is left, it goes
    assert w.auto_page.items == [] and w.auto_page.empty.isVisible() and not w.toolbar.isVisible()
    moved = w.org.catalog.document_row(_doc(w, "clear.pdf"))
    assert (moved["category"], moved["provenance"]) == ("Algebra", "user-corrected")

    w.show_view(SETTINGS)
    assert w.auto_level.currentData() == "strict"                  # the level the owner chose
    w.auto_level.setCurrentIndex(w.auto_level.findData("off"))
    w.auto_level.activated.emit(w.auto_level.currentIndex())
    w.import_paths([str(src / "later.pdf")])
    _pump(app, lambda: not w.inflight and not w.filing and not w.auto_running)
    assert "later.pdf" in [d["file_name"] for d in w.waiting()]    # switched off: everything waits
    w.show_view(SETTINGS)
    w.auto_level.setCurrentIndex(w.auto_level.findData("strict"))
    w.auto_level.activated.emit(w.auto_level.currentIndex())       # back on: the waiting documents are looked at again
    _pump(app, lambda: not w.filing and not w.auto_running)
    assert "later.pdf" not in [d["file_name"] for d in w.waiting()] and w.auto_count.text() == "1"
    assert [r["value"] for r in w.org.catalog.all("SELECT value FROM setting_changes ORDER BY id")] == ["off", "strict"]
    _close(w, rec)


def test_a_new_subject_is_one_question_and_the_third_confirmed_document_unlocks_filing(app, make_org, tmp_path):
    from classifile.app.decision import SubjectItem
    from test_matching import SUBJECTS, _add, _pdf

    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    org.update_matching()
    for n in range(6):
        _pdf(src / f"poem-{n}.pdf", SUBJECTS["Poetry"], n)
    _pdf(src / "zoo.pdf", "zebra giraffe antelope savanna migration herd", 1)

    w, rec = _window(make_org, [src / f"poem-{n}.pdf" for n in range(3)] + [src / "zoo.pdf"])
    _pump(app, lambda: not w.inflight and not w.auto_running)
    w.review()
    group = next(i for i in w.decision.items if isinstance(i, SubjectItem))
    assert len(w.decision.items) == 2 and group.title.full == "3 documents look like one new subject"
    assert group.line.text().startswith("Shared key words: ")       # the reason comes first
    assert set(group.line.text().split(": ")[1].split(", ")) <= set(SUBJECTS["Poetry"].split())
    assert group.field.text() == "" and not group.confirm.isEnabled()   # the user names it: nothing is pre-filled
    assert group.name_links and w.org.catalog.category_by_key("poetry") is None   # nothing was created
    group.name_links[0].click()                                     # a suggested name is only an offer
    assert group.field.text() == group.name_links[0].toolTip() and group.confirm.isEnabled()
    first, second, third = (_doc(w, f"poem-{n}.pdf") for n in range(3))
    group.detail_links[third].click()                               # each document's pages, on request
    assert w.details.isVisible() and w.details.title.full == "poem-2.pdf"
    w.close_details()
    group.ticks[third].setChecked(False)                            # left out before confirming
    group.field.setText("Poetry")
    assert group.confirm.text() == "Create && file 2 documents"
    assert group.confirm.toolTip() == "Create category 'Poetry' and file 2 documents"
    QTest.keyClick(group.field, Qt.Key_Return)
    _pump(app, lambda: not w.filing)
    poetry = w.org.catalog.category_by_key("poetry")
    assert sorted(d["id"] for d in w.org.catalog.documents(poetry["id"])) == sorted([first, second])
    assert w.org.catalog.explicit_labels()[first] == poetry["id"]   # filed by the user: a label
    assert sorted(d["file_name"] for d in w.waiting()) == ["poem-2.pdf", "zoo.pdf"]   # the unticked one still waits
    assert not any(isinstance(i, SubjectItem) for i in w.decision.items)   # two unlike documents: no group

    w.show_view(SETTINGS)
    w.matching_button.click()                                       # the model learns the new category
    _pump(app, lambda: w.matching_button.isEnabled() and not w.filing and not w.auto_running)
    assert "poem-2.pdf" in [d["file_name"] for d in w.waiting()]    # Poetry holds 2 confirmed documents: it waits
    w.import_paths([str(src / "poem-3.pdf")])
    _pump(app, lambda: not w.inflight and not w.filing and not w.auto_running)
    w.review()
    assert _item(w, "poem-2.pdf").matches[0][0] == "Poetry" and _item(w, "poem-3.pdf").matches[0][0] == "Poetry"
    _item(w, "poem-2.pdf").primary.click()                          # the third confirmed document...
    _pump(app, lambda: not w.filing and not w.auto_running and "poem-3.pdf" not in
          [d["file_name"] for d in w.waiting()])
    row = w.org.catalog.document_row(_doc(w, "poem-3.pdf"))         # ...and the other one is filed without a question
    assert (row["category"], row["provenance"]) == ("Poetry", "machine-assigned")
    assert [d["file_name"] for d in w.waiting()] == ["zoo.pdf"]
    _close(w, rec)


def test_looks_right_selected_categories_and_also_belongs_to_in_the_window(app, make_org, tmp_path):
    from classifile.app.main import AUTO
    from test_matching import SUBJECTS, _add, _pdf

    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    org.update_matching()
    for name, subject, n in (("a1.pdf", "Algebra", 5), ("a2.pdf", "Algebra", 6), ("n1.pdf", "Networks", 7),
                             ("n2.pdf", "Networks", 8)):
        _pdf(src / name, SUBJECTS[subject], n)

    w, rec = _window(make_org)
    assert w.mode_label.text() == "Filing into all categories" and w.mode_link.text() == "Change"
    w.mode_link.click()                                             # the link leads to where it is set
    assert w.view[0] == SETTINGS and w.auto_scope.currentData() == "all" and not w.auto_ticks.isVisible()
    w.auto_scope.setCurrentIndex(w.auto_scope.findData("selected"))
    w.auto_scope.activated.emit(w.auto_scope.currentIndex())
    assert w.auto_ticks.isVisible() and [b.text() for b in w.scope_boxes] == ["Algebra", "Networks"]
    assert w.mode_label.text() == "Filing into 0 selected categories"
    w.scope_boxes[0].click()                                        # only Algebra
    assert w.mode_label.text() == "Filing into 1 selected category"
    w.import_paths([str(src / "a1.pdf"), str(src / "n1.pdf")])
    _pump(app, lambda: not w.inflight and not w.filing and not w.auto_running)
    assert [d["file_name"] for d in w.waiting()] == ["n1.pdf"]      # Networks is not ticked: it asks
    w.show_view(SETTINGS)
    w.auto_scope.setCurrentIndex(w.auto_scope.findData("all"))
    w.auto_scope.activated.emit(w.auto_scope.currentIndex())        # all again: the waiting one is looked at again
    _pump(app, lambda: not w.filing and not w.auto_running)
    assert w.waiting() == [] and w.mode_label.text() == "Filing into all categories"

    w.import_paths([str(src / "a2.pdf"), str(src / "n2.pdf")])
    _pump(app, lambda: not w.inflight and not w.filing and not w.auto_running)
    w.show_view(AUTO)
    page = w.auto_page
    assert len(page.items) == 4 and page.bar.isVisible() and not page.right.isVisible()   # nothing ticked
    one = next(i for i in page.items if i.title.full == "a1.pdf")
    at = page.items.index(one)
    one.right.click()                                               # "Looks right" for one document
    assert w.toast.label.text().startswith("Confirmed 1 document.") and page.awaiting() == 3
    assert page.items.index(one) == at and one.status_word.text() == "Confirmed"   # in its place, marked
    assert not one.right.isVisible() and not one.tick.isVisible() and w.auto_count.text() == "3"
    assert w.org.catalog.document_row(_doc(w, "a1.pdf"))["provenance"] == "user-confirmed"
    rest = [i for i in page.items if not i.reviewed]
    for item in rest[:2]:
        item.tick.setChecked(True)
    assert page.right.text() == "Looks right (2)" and page.right.isVisible() and page.count.text() == "2 selected"
    QTest.mouseClick(rest[2].title, Qt.LeftButton)                  # inspecting another one leaves the ticks alone
    assert w.details.title.full == rest[2].title.full and rest[2].inspected and page.ticked() == [
        i.doc_id for i in rest[:2]]
    before = list(page.items)
    w.refresh()                                                     # a background update: ticks and details stay
    assert page.items == before
    assert page.ticked() == [i.doc_id for i in rest[:2]] and w.details.isVisible() and rest[2].inspected
    above = page.items[page.items.index(rest[2]) - 1]
    QTest.keyClick(rest[2], Qt.Key_Up)                              # the arrows walk the rows; details follow
    assert w.details.title.full == above.title.full and above.hasFocus()
    w.search.setText(rest[0].title.full)                            # the page's search
    assert [i for i in page.items if i.isVisible()] == [rest[0]] and w.result_count.text() == "1 of 4"
    w.search.setText("no such thing")
    assert w.stack.currentWidget() is w.no_match
    w.search.clear()
    page.all.click()                                                # or all of them at once
    assert page.right.text() == "Looks right (3)"
    page.right.click()
    assert page.awaiting() == 0 and w.auto_count.text() == ""
    assert w.toast.label.text().startswith("Confirmed 3 documents.")
    assert all(i.status_word.text() == "Confirmed" for i in page.items) and not page.right.isVisible()
    assert len(w.org.catalog.explicit_labels()) == 10               # they are training examples now
    w.show_view(ALL)
    assert _cell(w, next(r for r in range(w.filter.rowCount()) if _cell(w, r, 0) == "n2.pdf"), 2) == "Approved"

    doc = _doc(w, "n2.pdf")
    menu = w.context_menu([doc])
    next(a for a in menu.actions() if a.text() == "Also belongs to…").trigger()
    dialog = w.picker_dialog
    assert dialog.windowTitle() == "1 document also belongs to…" and dialog.confirm.text() == "Add"
    assert _pick(dialog.picker, "alg")[2] == "Algebra"
    dialog.confirm.click()
    _pump(app, lambda: not w.moving)
    assert w.toast.label.text() == "1 document also in Algebra."
    assert (w.org.output_root / "Algebra" / "n2.pdf").exists() and (w.org.output_root / "Networks" / "n2.pdf").exists()
    assert _cats(w) == {"Algebra": "6", "Networks": "5"}             # counted in both
    _click_category(w, "Algebra")
    assert "n2.pdf" in [_cell(w, r, 0) for r in range(w.filter.rowCount())]   # listed where it also belongs
    w.select_docs([doc])
    w.set_details_open(True)
    assert w.details.category.value.text() == "Networks" and w.details.also.value.text() == "Algebra"
    w.show_view(SETTINGS)
    w.auto_level.setCurrentIndex(w.auto_level.findData("off"))
    w.auto_level.activated.emit(w.auto_level.currentIndex())
    assert w.mode_label.text() == "Automatic filing is off"
    _close(w, rec)


def test_the_preview_draws_once_after_a_resize_and_keeps_recent_pages(app, make_org, tmp_path):
    import pymupdf

    (tmp_path / "src").mkdir()
    path = tmp_path / "src" / "three pages.pdf"
    d = pymupdf.open()
    for n in range(3):
        d.new_page().insert_text((72, 100), f"Made-up page {n + 1} about tides and harbours.", fontsize=14)
    d.save(path)
    d.close()
    w, rec = _window(make_org, [path])
    _pump(app, lambda: not w.inflight)
    w.resize(1900, 800)                                            # wide: the list has room to give
    w.select_docs([_doc(w, path.name)])
    w.set_details_open(True)
    p = w.details.preview
    _pump(app, lambda: p.page_label.text() == "Page 1 of 3" and not p.settle.isActive() and not p.busy
          and w.slide.state() != w.slide.State.Running)
    assert w.auto_page.minimumSizeHint().width() < 400             # no page's wording sets the least width
    drawn, widths = p.draws, set()
    list_width, panel_width = w.content.sizes()
    for step in range(1, 21):                                      # the divider dragged in 20 steps
        w.content.setSizes([list_width - 6 * step, panel_width + 6 * step])
        app.processEvents()
        widths.add(p.width())
    assert len(widths) > 10 and p.draws == drawn                   # the picture was only scaled: nothing drawn
    assert p.settle.isActive()
    _pump(app, lambda: not p.settle.isActive())
    _drawn(app, p)
    assert p.draws == drawn + 1                                    # drawn once, at the size it ended on
    p.next.click()
    _drawn(app, p)
    assert p.page_label.text() == "Page 2 of 3" and p.draws == drawn + 2
    p.prev.click()                                                 # a page already drawn at this size is kept
    assert p.page_label.text() == "Page 1 of 3" and not p.busy and p.draws == drawn + 2
    p.next.click()
    assert not p.busy and p.draws == drawn + 2
    w.show_view(SETTINGS)                                          # Settings: the whole page, controls at the right
    _pump(app, lambda: w.settings_page.isVisible())
    assert w.change_root.geometry().right() > w.settings_page.width() - 40
    _close(w, rec)


def test_sizes_colours_and_durations_are_named_once_in_the_token_module():
    import re
    from pathlib import Path

    import classifile.app as package
    from classifile.app import tokens

    literal = re.compile(r"#[0-9A-Fa-f]{6}\b|rgba?\(|\b\d+px\b|setStyleSheet\((?!STYLE\)|style_sheet\()|setDuration\(\d|ms=\d")
    for path in sorted(Path(package.__file__).parent.glob("*.py")):
        if path.name in ("tokens.py", "smoke.py"):                  # the tokens themselves; the CP0 smoke window
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not literal.search(line), f"{path.name}:{n} holds a size, colour or duration of its own"
    assert {tokens.TEXT_CAPTION, tokens.TEXT_SECONDARY, tokens.TEXT_BODY, tokens.TEXT_HEADING, tokens.TEXT_TITLE} \
        == {12, 13, 14, 16, 22}                                     # five text sizes, no others
    assert {tokens.RADIUS_ROW, tokens.RADIUS_CONTROL, tokens.RADIUS_PANEL, tokens.RADIUS_TAG} == {4, 6, 8, 10}


def test_every_button_has_a_name_light_and_dark_and_leave_pending_is_in_the_menu(app, make_org, tmp_path):
    from PySide6.QtWidgets import QAbstractButton
    from classifile.app.main import AUTO
    from classifile.organizer import read_and_analyze
    from test_matching import SUBJECTS, _add, _pdf

    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    org.update_matching()
    org.file_automatically(_add(org, src, "Networks", 7, False))
    org.set_auto_level("off")
    _add(org, src, "Algebra", 8, False)
    for n in range(2):
        _pdf(src / f"poem-{n}.pdf", SUBJECTS["Poetry"], n)
        org.record(src / f"poem-{n}.pdf", *read_and_analyze(src / f"poem-{n}.pdf"))

    w, rec = _window(make_org)

    def unnamed():
        return [b.text() or type(b).__name__ for b in w.findChildren(QAbstractButton)
                if b.isVisible() and not any(c.isalpha() for c in b.text()) and not b.accessibleName()]

    for view in (ALL, DECIDE, AUTO, SETTINGS):                      # a screen reader never reads a bare symbol
        w.show_view(view)
        if view == ALL:
            w.select_docs([_doc(w, "networks-7.pdf")])
            w.set_details_open(True)
        assert unnamed() == [], view
    assert w.search.accessibleName() == "Search" and w.sort.accessibleName() == "Sort the list"

    w.review()
    card = _item(w, "algebra-8.pdf")
    assert [b.text() for b in card.findChildren(QAbstractButton) if b.isVisible() and b.text() != "⋯"] == \
        ["File in Algebra", "Choose another…", "Details"]          # the rest is under "more", at the row's end
    assert card.more_menu.x() > card.details.x() and "Networks" in card.others.text()
    assert [a.text() for a in card.more_menu.menu().actions()] == ["Leave pending", "Remove from ClassiFile"]
    card.pending.trigger()
    assert w.toast.label.text() == "Left pending. It stays here until you decide."
    assert w.decision.items[-1].title.full == "algebra-8.pdf"       # moved to the end, still waiting
    group = w.decision.items[0]
    assert group.group and [a.text() for a in group.more_menu.menu().actions()] == \
        ["Leave pending", "Remove from ClassiFile"]

    w.show_view(SETTINGS)
    assert w.appearance.currentData() == "system"
    asked = []
    hints = type(app.styleHints())
    real, hints.setColorScheme = hints.setColorScheme, lambda self, scheme: asked.append(scheme)
    try:                                                            # off-screen there is no scheme to switch:
        for name in ("dark", "light"):                              # what the window asks Qt for is what is checked
            w.appearance.setCurrentIndex(w.appearance.findData(name))
            w.appearance.activated.emit(w.appearance.currentIndex())
    finally:
        hints.setColorScheme = real
    assert asked == [Qt.ColorScheme.Dark, Qt.ColorScheme.Light]
    assert w.org.catalog.get_setting("appearance") == "light"
    _close(w, rec)
    again, rec = _window(make_org)                                  # remembered at the next start
    again.show_view(SETTINGS)
    assert again.appearance.currentData() == "light"
    again.appearance.setCurrentIndex(again.appearance.findData("system"))
    again.appearance.activated.emit(again.appearance.currentIndex())
    _close(again, rec)


def test_reduced_motion_makes_every_change_instant(app, pdfs, make_org, monkeypatch):
    from classifile.app import widgets

    monkeypatch.setattr(widgets, "reduced_motion", lambda: True)   # Windows' "Animation effects" switched off
    w, rec = _window(make_org, [pdfs / "S4.pdf"])
    _pump(app, lambda: not w.inflight)
    w.resize(1920, 1000)
    w.review()
    item = _item(w, "S4.pdf")
    item.details.click()
    assert w.details.isVisible() and w.slide.state() != w.slide.State.Running
    w.close_details()
    ghosts = [c for c in w.workspace.children() if isinstance(c, QLabel) and
              c.testAttribute(Qt.WA_TransparentForMouseEvents)]
    assert not w.details.isVisible() and ghosts == []              # no picture of the panel slides away
    item.choose.click()
    assert item.expanded.isVisible() and item.expanded.maximumHeight() == widgets.QWIDGETSIZE_MAX
    _close(w, rec)


def test_a_wheel_turn_glides_and_is_instant_with_reduced_motion(app, monkeypatch):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QScrollArea, QWidget
    from classifile.app import widgets

    glide = widgets.smooth_scrolling(app)
    assert widgets.smooth_scrolling(app) is glide                  # one filter, however often it is asked for
    area = QScrollArea()
    tall = QWidget()
    tall.setFixedHeight(5000)
    area.setWidget(tall)
    area.resize(300, 300)
    area.show()
    bar = area.verticalScrollBar()

    def wheel(phase=Qt.NoScrollPhase):
        e = QWheelEvent(QPointF(10, 10), QPointF(area.viewport().mapToGlobal(QPoint(10, 10))), QPoint(0, 0),
                        QPoint(0, -120), Qt.NoButton, Qt.NoModifier, phase, False)
        QApplication.sendEvent(area.viewport(), e)

    monkeypatch.setattr(widgets, "reduced_motion", lambda: False)
    wheel()
    step = QApplication.wheelScrollLines() * bar.singleStep()
    assert bar.value() < step                                      # not there at once: it glides
    _pump(app, lambda: bar.value() == step, timeout=2)
    wheel()
    wheel()                                                        # quick turns add up
    _pump(app, lambda: bar.value() == 3 * step, timeout=2)
    monkeypatch.setattr(widgets, "reduced_motion", lambda: True)
    wheel()
    assert bar.value() == 4 * step                                 # Qt's own jump, at once
    monkeypatch.setattr(widgets, "reduced_motion", lambda: False)
    wheel(Qt.ScrollUpdate)                                         # a touchpad: already smooth, left to Qt
    assert bar.value() == 5 * step
    area.close()


def test_buttons_fade_and_sink_under_the_mouse_only_and_never_with_reduced_motion(app, monkeypatch):
    from PySide6.QtCore import QPointF
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QEnterEvent, QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton, QWidget
    from classifile.app import widgets

    assert widgets.button_motion(app) is widgets.button_motion(app)     # one filter for the app
    page = QWidget()
    plain, primary, toggle = QPushButton("Plain", page), QPushButton("Add documents", page), QPushButton("On", page)
    primary.setObjectName("primary")
    toggle.setCheckable(True)
    toggle.setChecked(True)
    for i, b in enumerate((plain, primary, toggle)):
        b.setGeometry(10, 10 + 50 * i, 160, 36)
    page.show()

    def hover(b, on):
        QApplication.sendEvent(b, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)) if on
                               else QEvent(QEvent.Leave))

    def mouse(b, kind):
        QApplication.sendEvent(b, QMouseEvent(kind, QPointF(5, 5), QPointF(5, 5), Qt.LeftButton,
                                              Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton,
                                              Qt.NoModifier))

    monkeypatch.setattr(widgets, "reduced_motion", lambda: False)
    sheet = widgets.style_sheet(widgets.THEME)
    for b, kind in ((plain, "plain"), (primary, "primary")):
        hover(b, True)
        assert b.property("fade").startswith(kind)                     # on its way to the hover colour,
        assert f'[fade="{kind}{widgets.FADE_STEPS}"]' in sheet          # in steps of the window's style sheet
        _pump(app, lambda: b.property("fade") is None, timeout=2)      # there: the style sheet's :hover holds it
        hover(b, False)
        assert b.property("fade") is not None
        _pump(app, lambda: b.property("fade") is None, timeout=2)
    hover(toggle, True)
    assert toggle.property("fade") is None                             # a checked button is left to the style sheet
    mouse(plain, QEvent.MouseButtonPress)
    assert isinstance(plain.graphicsEffect(), widgets._Sink)           # it sinks
    _pump(app, lambda: plain.graphicsEffect().scale < 1, timeout=2)
    assert plain.graphicsEffect().scale >= widgets.PRESS_SCALE
    mouse(plain, QEvent.MouseButtonRelease)
    _pump(app, lambda: plain.graphicsEffect() is None, timeout=2)      # back, and drawn as itself again
    plain.setFocus()
    QTest.keyClick(plain, Qt.Key_Space)
    assert plain.graphicsEffect() is None                              # a key press never animates
    monkeypatch.setattr(widgets, "reduced_motion", lambda: True)
    hover(plain, True)
    mouse(plain, QEvent.MouseButtonPress)
    assert plain.property("fade") is None and plain.graphicsEffect() is None   # colours change, nothing moves
    mouse(plain, QEvent.MouseButtonRelease)
    page.close()


def test_the_sidebar_hides_slides_back_and_stays_as_left(app, make_org):
    from PySide6.QtWidgets import QPushButton
    from classifile.app import widgets

    w, rec = _window(make_org)
    w.resize(1536, 864)
    _pump(app, lambda: w.width() == 1536)
    assert w.sidebar.isVisible() and not w.menu_button.isVisible()
    hide = next(b for b in w.sidebar.findChildren(QPushButton) if b.accessibleName() == "Hide the sidebar")
    w.set_motion("full")
    hide.click()
    ghosts = [c for c in w.children() if isinstance(c, QLabel) and c.testAttribute(Qt.WA_TransparentForMouseEvents)]
    assert w.sidebar.isHidden() and w.menu_button.isVisible() and ghosts   # a picture of it slides out left
    _pump(app, lambda: w.workspace.x() == 0)                           # the page has the whole width at once
    w.menu_button.click()
    assert w.sidebar.isVisible() and not w.menu_button.isVisible()
    _pump(app, lambda: w.sidebar.x() == 0 and w.workspace.x() == w.sidebar.width(), timeout=2)
    hide.click()
    _close(w, rec)
    w2, rec = _window(make_org)                                        # the next start: still hidden
    w2.resize(1536, 864)
    _pump(app, lambda: w2.width() == 1536)
    assert w2.sidebar.isHidden() and w2.menu_button.isVisible()
    w2.set_motion("reduce")
    w2.menu_button.click()
    assert w2.sidebar.isVisible() and w2.sidebar.x() == 0              # at once with reduced motion
    widgets.set_motion("system")
    _close(w2, rec)


def test_new_folders_by_itself_with_one_summary_and_a_one_click_rename(app, make_org, tmp_path):
    from classifile.app.main import AUTO
    from test_matching import SUBJECTS, _add, _pdf

    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    org.update_matching()
    org.set_auto_folders(True)
    poems = [src / f"poem-{n}.pdf" for n in range(3)]
    for n, path in enumerate(poems):
        _pdf(path, SUBJECTS["Poetry"], n)
    _pdf(src / "clear.pdf", SUBJECTS["Networks"], 7)
    _pdf(src / "zoo.pdf", "zebra giraffe antelope savanna migration herd", 1)
    w, rec = _window(make_org, poems + [src / "clear.pdf", src / "zoo.pdf"])
    _pump(app, lambda: w.run is None and not w.inflight and not w.moving)
    assert w.toast.label.text() == "Filed 4 automatically · 1 new folder · 1 needs you"   # one line for the import
    assert w.toast.action.text() == "Review" and w.mode_label.text().endswith("new folders on")
    new = next(c for c in w.org.catalog.categories() if c["app_named"])
    assert _cats(w)[new["name"]] == "New · 3"                          # marked in the sidebar
    w.show_view(AUTO)
    folder, = w.auto_page.folders
    assert folder.isVisible() and folder.name.full == new["name"] and folder.about.text().startswith(
        "3 documents · No folder matched these documents, and they share ")
    rec_name = "Poems"
    w.ask_new_name = lambda current: rec_name
    folder.rename.click()                                              # one click, then the name
    _pump(app, lambda: not w.moving)
    assert w.org.catalog.category(new["id"])["name"] == "Poems" and not w.auto_page.folders
    assert _cats(w)["Poems"] == "3"
    _close(w, rec)


def test_retry_find_category_motion_and_the_matching_log(app, make_org, tmp_path, monkeypatch):
    from classifile import matching
    from classifile.app import widgets
    from classifile.app.main import SETTINGS
    from test_matching import _add

    org, src = make_org(), tmp_path / "src"
    for n in range(2):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    org.update_matching()
    for n in range(9):
        org.create_category(f"Topic {n}")
    broken = src / "broken.docx"
    broken.write_bytes(b"PK not a zip")
    w, rec = _window(make_org, [broken])
    _pump(app, lambda: not w.inflight and w.run is None)
    w.review()
    item = _item(w, "broken.docx")
    assert item.primary.text() == "Retry" and item.primary.isVisible()     # read again from the original
    item.primary.click()
    assert str(broken.resolve()) in w.inflight
    _pump(app, lambda: not w.inflight and w.run is None)
    assert [d["status"] for d in w.org.catalog.all_documents() if d["file_name"] == "broken.docx"] == ["failed"]

    assert w.find_category.isVisible() and len(_cats(w)) == 11         # many categories: a find field
    w.find_category.setText("netw")
    assert list(_cats(w)) == ["Networks"] and w.view[0] == "decide"    # the open view stays
    w.find_category.setText("nothing like it")
    assert _cats(w) == {} and w.cats_none.isVisible()
    w.find_category.clear()
    assert len(_cats(w)) == 11 and not w.cats_none.isVisible()

    w.show_view(SETTINGS)
    w.motion.setCurrentIndex(w.motion.findData("reduce"))
    w.motion.activated.emit(w.motion.currentIndex())
    assert widgets.reduced_motion() and w.org.catalog.get_setting("motion") == "reduce"
    assert w.matching_log.text().startswith("Version 1 · ") and "by you" in w.matching_log.text()

    monkeypatch.setattr(matching, "AUTO_UPDATE_EVERY", 2)
    _add(w.org, src, "Algebra", 5)
    _add(w.org, src, "Networks", 6)
    w.show_view("all")
    w.update_if_due()                                                  # what filing, Looks right and moves call
    _pump(app, lambda: not w.updating)
    assert any(n.startswith("Matching updated by itself: version 2") for n in _notices(w))   # a note at the top
    w.show_view(SETTINGS)
    assert w.matching_log.text().startswith("Version 2 · ") and "by itself" in w.matching_log.text()
    assert not w.update_note                                           # seen: the note goes
    widgets.set_motion("system")
    _close(w, rec)


def test_a_filed_row_folds_away_and_goes_at_once_with_reduced_motion(app, pdfs, make_org):
    from shiboken6 import isValid

    from classifile.app import widgets
    from classifile.app.main import SETTINGS

    w, rec = _window(make_org, [pdfs / f"{s}.pdf" for s in ("S1", "S2", "S3")])
    _pump(app, lambda: not w.inflight)
    for preference, folding in (("full", True), ("reduce", False)):
        w.set_motion(preference)
        w.review()
        item = w.decision.items[0]
        item.choose.click()
        _pick(item.picker, f"Folder {preference}", "Create category")
        item.confirm.click()
        item = w.decision.row_of(item.ids[0])                          # its row while the copy is made
        _pump(app, lambda: not w.filing)
        there = lambda: isValid(item) and w.decision.list.indexOf(item) >= 0
        assert there() == folding                                      # folding where it was, or gone at once
        assert item not in w.decision.items and [i.number.text() for i in w.decision.items][:1] == ["1."]
        _pump(app, lambda: not there())                                # and then it is gone
    w.show_view(SETTINGS)
    assert w.motion.currentData() == "reduce"
    widgets.set_motion("system")
    _close(w, rec)


def test_check_these_on_the_decision_page_keep_here_and_move(app, make_org, tmp_path):
    from test_matching import _add, _flag

    org, src = make_org(), tmp_path / "src"
    algebra = [_add(org, src, "Algebra", n) for n in range(3)]
    for n in range(3):
        _add(org, src, "Networks", n)
    org.update_matching()
    _flag(org, *algebra[:2])
    w, rec = _window(make_org)
    assert w.decide_count.text() == "2"                               # two questions, nothing waiting
    assert _notices(w) == ["2 filed documents to check."]               # the notice counts what the sidebar counts
    w.show_view(DECIDE)
    checks = w.decision.checks
    assert [c.name.full for c in checks] == ["algebra-0.pdf", "algebra-1.pdf"] and w.decision.check_box.isVisible()
    assert checks[0].about.text() == "In Algebra. Its content matches Networks much more closely."
    assert not w.decision.empty.isVisible() and w.page_title.full == "Needs your decision · 2"
    checks[0].details.click()                                         # a filed document's pages, from its row
    assert w.details.isVisible() and w.inspected == algebra[0] == w.details.doc_id and checks[0].details.isChecked()
    w.refresh()                                                       # stays open: it is a row of this page
    assert w.inspected == algebra[0] and w.details.isVisible()
    checks[0].details.click()
    assert w.inspected is None and not checks[0].details.isChecked()
    picked = []
    w.pick_category = lambda title, verb, on_choice: picked.append((title, verb))
    checks[1].move.click()
    assert picked == [("Move 1 document to…", "Move")]               # the user chooses; nothing moves by itself
    checks[0].keep.click()
    assert w.toast.label.text() == "Kept where it is. ClassiFile won't ask about it again."
    assert [c.doc_id for c in w.decision.checks] == [algebra[1]] and w.decide_count.text() == "1"
    assert w.org.catalog.explicit_labels()[algebra[0]] == w.org.catalog.category_by_key("algebra")["id"]
    _close(w, rec)


def test_tour_steps_and_learning_from_existing_folders_in_the_window(app, make_org, tmp_path, monkeypatch):
    from classifile.app.guide import TOUR, TourDialog
    tour = TourDialog(None, learn=True)
    assert tour.next.text() == "Next" and not tour.back.isVisibleTo(tour) and tour.skip.isVisibleTo(tour)
    for _ in TOUR[1:]:
        tour.go(1)
    assert tour.next.text() == "Get started" and tour.learn.isVisibleTo(tour) and not tour.skip.isVisibleTo(tour)
    tour.learn.click()
    assert tour.learn_chosen and tour.result() == TourDialog.Accepted

    import pymupdf
    mine = tmp_path / "mine"
    words = {"Algebra": "matrix vector eigenvalue determinant", "Networks": "router packet subnet ethernet",
             "New folder": "anything at all here"}
    for folder, text in words.items():
        (mine / folder).mkdir(parents=True)
        for n in range(3):
            d = pymupdf.open()
            d.new_page().insert_text((72, 72), f"{text} {text} part {n}", fontsize=11)
            d.save(mine / folder / f"{n}.pdf")
            d.close()
    before = source_state(mine)
    w, rec = _window(make_org)
    asked = []
    w.pick_folder = lambda title: str(mine)

    def untick_and_rename(root, found):
        asked.append([(sub.name, len(files)) for sub, files in found])
        return [("Linear algebra" if sub.name == "Algebra" else sub.name, sub, files) for sub, files in found
                if sub.name != "New folder"]                # the user unticks one and renames one
    w.ask_learn = untick_and_rename
    w.learn_folders()
    assert asked == [[("Algebra", 3), ("Networks", 3), ("New folder", 3)]]
    assert w.processing.isVisible() and "Learning from your folders" in w.processing.text()
    _pump(app, lambda: w.learning is None and not w.moving)
    assert sorted(_cats(w)) == ["Linear algebra", "Networks"]
    assert w.stack.currentWidget() is w.empty_state                         # examples are never listed
    assert source_state(mine) == before and not list(w.org.output_root.iterdir())
    w.show_view(SETTINGS)
    rows = [l.text() for l in w.learned.findChildren(QLabel)]
    assert rows == ["Algebra → Linear algebra · 3 documents", "Networks → Networks · 3 documents"]
    assert w.org.matcher() is not None                                      # learned from them at once
    forget = [b for b in w.learned.findChildren(QPushButton) if b.text() == "Forget"]
    forget[0].click()
    assert [l.text() for l in w.learned.findChildren(QLabel)] == [
        "Networks → Networks · 3 documents"]
    assert source_state(mine) == before
    _close(w, rec)


def test_two_filing_actions_at_once_keep_their_own_messages_and_feedback(app, make_org, make_pdf):
    from classifile.organizer import read_and_analyze

    w, rec = _window(make_org)
    ids = {}
    for name, words in (("a1.pdf", "garden soil compost"), ("a2.pdf", "garden seedling mulch"),
                        ("b1.pdf", "travel hotel booking")):
        path = make_pdf(name, words)
        ids[name], _ = w.org.record(path, *read_and_analyze(path))
    w.refresh()
    jobs, said = {}, []
    w.pool.submit = lambda fn, doc_id, cat_id: jobs.__setitem__(doc_id, (fn, doc_id, cat_id))
    w.toast.show_message = lambda text, *a, **k: said.append(text)
    w.file_docs([ids["a1.pdf"], ids["a2.pdf"]], "Alpha", feedback="")   # the suggestions set aside, no reason
    w.file_docs([ids["b1.pdf"]], "Beta")
    for name in ("a1.pdf", "b1.pdf", "a2.pdf"):                          # finished in this order
        fn, *args = jobs[ids[name]]
        fn(*args)
    assert said == ["Filed b1.pdf in Beta", "Filed 2 documents in Alpha"]
    alpha = w.org.catalog.category_by_key("alpha")["id"]
    rows = w.org.catalog.all("SELECT document_id, category_id FROM suggestion_feedback ORDER BY document_id")
    assert sorted((r["document_id"], r["category_id"]) for r in rows) == sorted(
        [(ids["a1.pdf"], alpha), (ids["a2.pdf"], alpha)])                 # none against Beta
    assert w.actions == {} and w.filing == {}
    _close(w, rec)


def test_a_missing_filed_copy_is_shown_and_can_be_made_again(app, make_org, filed_pdf):
    org = make_org()
    doc = filed_pdf(org, "notes.pdf", "garden soil compost seedling", "Garden")
    copy = org.output_root / "Garden" / "notes.pdf"
    copy.unlink()                                               # the user deleted the filed copy
    w, rec = _window(make_org)                                  # the next start flags it
    w.org.startup()
    w.refresh()
    w.show_view(ALL)
    assert _cell(w, _rows(w).index("notes.pdf"), 2) == "Filed copy missing"
    w.show_details(doc)
    assert w.details.restore_button.isVisible() and "no longer where" in w.details.state.value.text()
    copy.write_text("something else now")                       # an unrelated file appeared at the old place
    w.restore_copy(doc)
    assert copy.read_text() == "something else now"             # never adopted, never overwritten
    new = w.org.output_root / "Garden" / "notes (2).pdf"
    assert new.exists() and _cell(w, _rows(w).index("notes.pdf"), 2) == "Approved"
    assert not w.details.restore_button.isVisible()
    _close(w, rec)


def test_office_files_without_a_stored_picture_show_no_document_text(app, office):
    from classifile.app.widgets import Preview

    preview = Preview()
    for path in office.iterdir():                               # the generated files carry no thumbnail
        preview.show_document(path)
        _drawn(app, preview)
        shown = preview.image.text()
        assert shown == "No page picture is stored in this file.", path.name


def test_the_open_choices_reach_the_cards_right_edge(app, make_org, make_pdf):
    from classifile.organizer import read_and_analyze

    w, rec = _window(make_org)
    w.resize(1536, 864)
    path = make_pdf("notes.pdf", "garden soil compost seedling")
    w.org.record(path, *read_and_analyze(path))
    w.refresh()
    w.show_view(DECIDE)
    item = w.decision.items[0]
    item.toggle_expanded()
    item.none_fit.click()                                       # the reasons too
    _pump(app, lambda: item.expanded.maximumHeight() > 10 ** 6)  # unfolded
    app.processEvents()
    right = lambda widget: widget.mapTo(item, widget.rect().topRight()).x()
    assert abs(right(item.expanded) - right(item.more_menu)) <= 2      # no empty band at the right (owner's rule)
    assert item.expanded.width() > 900                                  # the old 680 cap is gone
    _close(w, rec)


@pytest.mark.parametrize("how", ["hang", "crash"])
def test_a_preview_that_hangs_or_crashes_never_stops_the_window(app, make_pdf, how):
    import preview_probe
    from classifile.app.widgets import Preview, page_service
    from classifile.worker import Worker

    path = make_pdf("notes.pdf", "garden soil compost seedling")
    service = page_service()
    real = service.worker
    service.worker = Worker(getattr(preview_probe, how), timeout=1, on_failure=lambda request, reason: None)
    try:
        preview = Preview()
        started = time.monotonic()
        preview.show_document(path)
        assert time.monotonic() - started < 0.5 and preview.busy        # the window went on at once
        _drawn(app, preview)
        assert preview.image.text() == "This PDF can't be previewed."
    finally:
        service.worker.stop()
        service.worker = real
    preview.show_document(None)
    preview.show_document(path)                                          # the real one draws again
    _drawn(app, preview)
    assert not preview.image.pixmap().isNull() and preview.page_label.text() == "Page 1 of 1"
