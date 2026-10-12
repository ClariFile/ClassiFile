"""The interface acceptance checks of docs/UI_PROPOSAL.md (section 7), run off-screen on a made-up catalog.

Usage: python -m tools.check_ui [--scale 1.25]

Without --scale it runs at 100%, then starts itself again at 125% and 150% (the scale must be set before Qt
starts). Each run opens the real window on 60 categories and a few documents (two with 120-character names), at
1024x640, 1280x720, 1536x864 and 1920x1080, and prints one line per check: ok, FAIL with what was found, or
"not checked" with the reason. It exits with 1 when something failed.
What a script cannot judge is said so: whether focus can be seen, and anything that needs real hands.
Nothing outside a temporary folder is written; no real document is read.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SIZES = ((1024, 640), (1280, 720), (1536, 864), (1920, 1080))
LONG = "A very long file name that keeps going well past what any column or card could show in one line " + "x" * 20
CATEGORIES, IMPORTS = 60, 20


def build(base):
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer, read_and_analyze
    from tools.measure_ui import make_pdf, title
    for name in ("src", "out", "more"):
        (base / name).mkdir(parents=True)
    org = Organizer(Catalog(base / "data" / "catalog.sqlite3"))
    org.set_output_root(base / "out")
    cats = [org.create_category(f"Category {n:02d} {title(n)}") for n in range(CATEGORIES)]
    names = [f"{LONG} {n}.pdf" for n in (1, 2)] + [f"Notes {n:02d} {title(n)}.pdf" for n in range(10)]
    assert len(names[0]) >= 120
    for n, name in enumerate(names):
        make_pdf(base / "src" / name, title(100 + n))
        doc, _ = org.record(base / "src" / name, *read_and_analyze(base / "src" / name))
        if n % 2 == 0:                          # one long name is filed, the other waits
            org.file(doc, cats[n])
    for n in range(IMPORTS):
        make_pdf(base / "more" / f"Extra {n:02d}.pdf", title(300 + n))
    org.catalog.close()


def run(base):
    """[(check, problems or None when it could not be checked, note)]."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QFont, QFontDatabase, QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QAbstractScrollArea, QApplication, QScrollArea

    from classifile.app import decision, make_app
    from classifile.app.main import ALL, DECIDE, DOC, SETTINGS, MainWindow
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer

    app = make_app([])
    fonts = Path(os.environ.get("WINDIR", "")) / "Fonts"
    if (fonts / "segoeui.ttf").is_file():       # off-screen Qt has only wide fallback fonts: use the real ones
        for f in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf"):
            QFontDatabase.addApplicationFont(str(fonts / f))
        app.setFont(QFont("Segoe UI", 10))
    w = MainWindow(Organizer(Catalog(base / "data" / "catalog.sqlite3")), ask_output_root=False)
    w.ask_close = lambda n: ("close", False)
    opened, menus = [], []
    w.open_path = opened.append
    w.confirm_remove = lambda n: False
    w.show()
    results = []

    def pump(until=lambda: False, timeout=0.5):
        end = time.monotonic() + timeout
        while True:
            app.processEvents()
            if until() or time.monotonic() > end:
                return
            time.sleep(0.01)

    def doc_id(name):
        return next(d["id"] for d in w.org.catalog.all_documents() if d["file_name"] == name)

    def card(name):
        return next(i for i in w.decision.items if i.title.full == name)

    def layout_problems():
        found = []
        for area in w.findChildren(QAbstractScrollArea):
            bar = area.horizontalScrollBar()
            if area.isVisible() and bar.isVisible() and bar.maximum() > 0:
                found.append(f"sideways scrolling in the {area.objectName() or type(area).__name__}")
        for b in w.findChildren(QAbstractButton):
            if not b.isVisible() or b.window() is not w:
                continue
            text = b.text().replace("&&", "&")
            if b.width() < b.fontMetrics().horizontalAdvance(text):
                found.append(f"button narrower than its text: {text!r}")
            parent, scrolled = b.parentWidget(), False
            while parent is not None:           # a parent clips what sticks out of it
                at = b.mapTo(parent, QPoint(0, 0))
                area = parent.parentWidget()    # inside a scrolling area, being above or below the view is fine
                scrolled = scrolled or (isinstance(area, QAbstractScrollArea) and area.viewport() is parent)
                out_x = at.x() < 0 or at.x() + b.width() > parent.width()
                out_y = not scrolled and (at.y() < 0 or at.y() + b.height() > parent.height())
                if out_x or out_y:
                    found.append(f"clipped: {text!r}")
                    break
                if parent is w:
                    break
                parent = parent.parentWidget()
        return sorted(set(found))

    def shortened(label, name):
        """Ends in "…" unless the whole name fits; the full name on hover either way."""
        fits = label.fontMetrics().horizontalAdvance(name) <= label.width()
        return label.toolTip() == name and (label.text() == name if fits else label.text().endswith("…"))

    long_filed, long_waiting = f"{LONG} 1.pdf", f"{LONG} 2.pdf"
    first_cat = w.org.catalog.categories()[0]["id"]

    # -- sizes: nothing clipped, no sideways scrolling, no button narrower than its text; long names ----------------
    for size in SIZES:
        w.resize(*size)
        pump(lambda: (w.width(), w.height()) == size)
        found = []

        def look(view):
            pump(timeout=0.25)                  # the details panel slides in
            found.extend(f"{view}: {p}" for p in layout_problems())

        w.close_details()
        w.show_view(ALL)
        look("All documents")
        row = next(r for r in range(w.filter.rowCount()) if w.filter.index(r, 0).data() == long_filed)
        index = w.filter.index(row, 0)
        if w.table.visualRect(index).right() > w.table.columnViewportPosition(1):
            found.append("All documents: the long name runs into the next column")
        if index.data(Qt.ToolTipRole) != long_filed:
            found.append("All documents: the long name has no full-name tip")
        w.select_docs([doc_id(long_filed)])
        w.set_details_open(True)
        look("list with details")
        if not shortened(w.details.title, long_filed):
            found.append("details: the long name is not shortened with its full name on hover")
        w.close_details()
        w.show_view("category", first_cat)
        look("a category")
        w.show_view(DECIDE)
        look("Needs your decision")
        item = card(long_waiting)
        if not shortened(item.title, long_waiting):
            found.append("decision card: the long name is not shortened with its full name on hover")
        if len({i.width() for i in w.decision.items}) != 1:
            found.append("decision cards: the long name changed a card's width")
        item.toggle_expanded()
        look("a card's choices open")
        w.show_details(item.ids[0])
        look("decision page with details")
        item.toggle_expanded()
        w.close_details()
        w.show_view(SETTINGS)
        look("Settings")
        results.append((f"{size[0]}x{size[1]}: nothing clipped, no sideways scrolling, buttons fit, long names end in …",
                        found, ""))
    w.resize(1536, 864)
    pump(lambda: w.width() == 1536)

    # -- 60 categories: the sidebar scrolls and keeps its place ---------------------------------------------------------
    w.show_view(ALL)
    bar = w.cats.verticalScrollBar()
    pump(lambda: bar.maximum() > 0)
    found = [] if bar.maximum() > 0 else ["the sidebar does not scroll"]
    bar.setValue(bar.maximum() // 2)
    at = bar.value()
    w.cats.clicked.emit(w.cats.indexAt(QPoint(20, w.cats.viewport().height() // 2)))
    pump()
    if w.view[0] != "category" or bar.value() != at:
        found.append(f"a click moved the sidebar from {at} to {bar.value()}")
    w.org.create_category("Zz one more")
    w.refresh()
    pump()
    if bar.value() != at:
        found.append(f"a refresh moved the sidebar from {at} to {bar.value()}")
    results.append(("60 categories: the sidebar scrolls and keeps its place", found, ""))
    results.append(("\"Find category…\" filters the sidebar", None, "not built yet (phase 5)"))

    # -- Details ten times quickly ------------------------------------------------------------------------------------------
    w.show_view(ALL)
    w.select_docs([doc_id(long_filed)])
    found = []
    for clicks in (10, 11):
        for _ in range(clicks):
            w.details_toggle.click()
        pump(lambda: w.slide.state() != w.slide.State.Running, 1.0)
        if w.slide.state() == w.slide.State.Running:
            found.append(f"still moving a second after {clicks} clicks")
        if w.details.isVisible() != w.details_toggle.isChecked() or w.details.isVisible() != (clicks % 2 == 1):
            found.append(f"after {clicks} clicks the panel is {'open' if w.details.isVisible() else 'closed'}")
    w.close_details()
    results.append(("Details clicked ten times quickly: the panel matches the last click, no backlog", found, ""))

    # -- keyboard -----------------------------------------------------------------------------------------------------------
    found = []
    w.show_view(ALL)
    w.table.setFocus()
    QTest.keySequence(w.table, QKeySequence(QKeySequence.Find))
    if not w.search.hasFocus():
        found.append("Ctrl+F does not reach the search field")
    QTest.keyClicks(w.search, "notes 03")
    if w.filter.rowCount() != 1 or w.result_count.text() != f"1 of {w.filter.total()}":
        found.append("typing in the search field does not narrow the list to the match")
    QTest.keyClick(w.search, Qt.Key_Escape)
    if w.search.text():
        found.append("Esc does not clear the search")
    seen, widget = [], w.search
    for _ in range(80):                         # Tab through the window
        QTest.keyClick(QApplication.focusWidget() or widget, Qt.Key_Tab)
        widget = QApplication.focusWidget()
        if widget in seen:
            break
        seen.append(widget)
    wanted = {"the sort list": w.sort, "the Details switch": w.details_toggle, "the document list": w.table,
              "Add documents": w.add_button, "the views": w.nav_group.checkedButton(), "New category (+)":
              w.add_category, "the categories": w.cats}
    found += [f"Tab does not reach {name}" for name, target in wanted.items() if target not in seen]
    w.nav_group.checkedButton().setFocus()      # the views are one group: the arrow keys move between them
    for _ in range(3):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Down)
    if w.view[0] != SETTINGS:
        found.append(f"the arrow keys do not walk the views down to Settings (ended on {w.view[0]})")
    w.show_view(ALL)
    w.select_docs([doc_id(long_filed)])
    w.table.setFocus()
    QTest.keyClick(w.table, Qt.Key_Space)
    if not w.details.isVisible():
        found.append("Space does not open details")
    QTest.keyClick(w.table, Qt.Key_Escape)
    if w.details.isVisible():
        found.append("Esc does not close details")
    QTest.keyClick(w.table, Qt.Key_Return)
    if len(opened) != 1:
        found.append("Enter does not open a filed document")
    w.context_menu = lambda ids: menus.append(("documents", ids))        # returns None: nothing pops up
    w.category_menu = lambda cat: menus.append(("category", cat)) or type("Menu", (), {"exec": lambda s, p: None})()
    QTest.keyClick(w.table, Qt.Key_Menu)
    w.cats.setFocus()
    w.cats.setCurrentIndex(w.cats.model().index(0, 0))
    QTest.keyClick(w.cats, Qt.Key_Return)
    if w.view != ("category", w.cats.model().index(0, 0).data(DOC)):
        found.append("Enter on a category does not open it")
    QTest.keyClick(w.cats, Qt.Key_Menu)
    menu_keys = {kind for kind, _ in menus}
    w.show_view(DECIDE)
    pump()
    item = w.decision.items[0]
    if not item.hasFocus():
        found.append("opening the decision page does not put the focus on the first card")
    QTest.keyClick(item, Qt.Key_Return)
    if not item.expanded.isVisible() or not item.picker.field.hasFocus():
        found.append("Enter on a card does not open its choices with the cursor in the field")
    QTest.keyClicks(item.picker.field, "category 07")
    if not item.picker.current() or not item.confirm.isEnabled():
        found.append("typing in a card's field does not choose the matching category")
    QTest.keyClick(item.picker.field, Qt.Key_Escape)
    if item.expanded.isVisible():
        found.append("Esc does not close a card's choices")
    reached = []
    for _ in range(12):
        QTest.keyClick(QApplication.focusWidget() or item, Qt.Key_Tab)
        reached.append(QApplication.focusWidget())
    found += [f"Tab does not reach a card's {name}" for name, target in
              (("main button", item.primary), ("⋯ menu", item.more_menu), ("Details", item.details))
              if target.isVisible() and target not in reached]
    results.append(("Keyboard: search, lists, details, opening, categories and decision cards", found, ""))
    results.append(("Keyboard: the menu key opens the document and category menus (move, rename, delete)",
                    None if menu_keys != {"documents", "category"} else [],
                    "" if menu_keys == {"documents", "category"} else
                    "the menu key cannot be pressed off-screen; try Shift+F10 on a row by hand"))
    results.append(("Keyboard: focus is always visible", None, "a script cannot see it; and the two lists draw no "
                    "focus mark of their own (style sheet: outline none), which phase 3 has to settle"))

    # -- a card in use while 20 documents are imported -------------------------------------------------------------
    w.show_view(DECIDE)
    w.resize(1280, 640)                         # short: the page scrolls
    area = w.decision.findChild(QScrollArea).verticalScrollBar()
    pump(lambda: area.maximum() > 0)
    item = w.decision.items[2]
    if not item.expanded.isVisible():
        item.toggle_expanded()
    item.picker.field.setText("my draft")
    pump()
    area.setValue(area.maximum() // 2)
    item.picker.field.setFocus()
    item.picker.field.setCursorPosition(3)
    pump()
    at, built, make = area.value(), [], decision.DecisionItem.__init__

    def counting(self, *a, **k):
        built.append(1)
        make(self, *a, **k)
    decision.DecisionItem.__init__ = counting
    w.import_paths([str(p) for p in sorted((base / "more").iterdir())])
    pump(lambda: not w.inflight, 120)
    pump()
    decision.DecisionItem.__init__ = make
    found = []
    if item not in w.decision.items or len(built) != IMPORTS:
        found.append(f"{len(built)} cards were built for {IMPORTS} imports, or the card in use was replaced")
    if not item.expanded.isVisible() or item.picker.field.text() != "my draft":
        found.append("the open panel or the typed text was lost")
    if not item.picker.field.hasFocus() or item.picker.field.cursorPosition() != 3:
        found.append("the cursor left the field or moved")
    if area.value() != at:
        found.append(f"the page scrolled from {at} to {area.value()}")
    results.append((f"Typing in a card while {IMPORTS} documents import: text, panel, cursor and scroll stay", found, ""))
    results.append(("Reduce motion: every change is instant", None, "not built yet (phase 4)"))
    results.append(("Light theme", None, "not checked: off-screen drawing cannot read the system theme (phase 3)"))
    w.close()
    w.org.catalog.close()
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scale", type=float, help="display scaling for this run only, e.g. 1.25")
    a = ap.parse_args(argv)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["CLASSIFILE_OCR"] = "off"
    if a.scale:
        os.environ["QT_SCALE_FACTOR"] = str(a.scale)
    base = Path(tempfile.mkdtemp(prefix="classifile-check-"))
    try:
        build(base)
        results = run(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)   # only the temporary folder this run made
    print(f"Scaling {int((a.scale or 1) * 100)}%")
    for check, found, note in results:
        print(f"  {'not checked' if found is None else 'FAIL' if found else 'ok':<12}{check}"
              + (f" ({note})" if note else ""))
        for line in found or ():
            print(f"{'':14}- {line}")
    failed = any(found for _, found, _ in results)
    sys.stdout.flush()
    if not a.scale:                             # the other scalings need a fresh Qt each
        for scale in ("1.25", "1.5"):
            failed |= subprocess.run([sys.executable, "-m", "tools.check_ui", "--scale", scale]).returncode != 0
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
