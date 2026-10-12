"""How long the window takes to do its everyday work, on a made-up catalog (docs/UI_PROPOSAL.md, section 1).

Usage: python -m tools.measure_ui [--base DIR] [--json FILE]

Builds 200 one-page-title PDFs (140 filed in 30 categories, 60 waiting) and 20 more to import, in DIR (a temporary
folder by default, removed afterwards), then opens the real window off-screen at 1536x864 and times:
  - importing 20 documents while "Needs your decision" is showing: decision cards built, and how long the
    interface thread was busy (it cannot answer the mouse or keyboard meanwhile);
  - one refresh of each page and of the sidebar, with the database statements it ran;
  - one search key (nine are typed: most leave the list as it is, the last one halves it);
  - whether text typed in a decision card, its open panel, the cursor and the scroll position survive the imports.
Times include the layout and painting a change causes. They describe this machine and this catalog only.
No real document is read; nothing outside DIR is written.
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

WORDS = ("Signal", "Matrix", "Vector", "Thermal", "Optical", "Quantum", "Linear", "Discrete", "Network", "Memory",
         "Process", "Kernel", "Circuit", "Protein", "Market", "Ledger", "Harbor", "Glacier", "Pollen", "Meadow")
DOCUMENTS, FILED, CATEGORIES, IMPORTS = 200, 140, 30, 20


def title(n):
    return f"{WORDS[n % 20]} {WORDS[(n // 20) % 20]} Studies {n:03d}"


def make_pdf(path, text):
    import pymupdf
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 120), text, fontsize=22)
    p.insert_text((72, 160), "Notes prepared for the weekly session", fontsize=11)
    d.new_page().insert_text((72, 100), "The second page explains the idea in a few plain sentences.", fontsize=11)
    d.save(path)
    d.close()


def build(base):
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer, read_and_analyze
    for name in ("src", "out", "more"):
        (base / name).mkdir(parents=True)
    org = Organizer(Catalog(base / "data" / "catalog.sqlite3"))
    org.set_output_root(base / "out")
    cats = [org.create_category(f"{WORDS[i % 20]} {'Systems' if i < 20 else 'Methods'}") for i in range(CATEGORIES)]
    for n in range(DOCUMENTS):
        path = base / "src" / f"Lecture {n:03d} - {title(n)} with a fairly long file name.pdf"
        make_pdf(path, title(n))
        doc, _ = org.record(path, *read_and_analyze(path))
        if n < FILED:
            org.file(doc, cats[n % CATEGORIES])
    for n in range(DOCUMENTS, DOCUMENTS + IMPORTS):
        make_pdf(base / "more" / f"Lecture {n:03d} - {title(n)}.pdf", title(n))
    org.catalog.close()


def measure(base):
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QScrollArea

    from classifile.app import decision, make_app
    from classifile.app.main import ALL, DECIDE, MainWindow
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
    w.resize(1536, 864)
    w.show()
    stalls = []

    def pump(until=lambda: True, timeout=300):
        """Run the event loop until the condition holds, noting how long each turn kept the thread."""
        end = time.monotonic() + timeout
        while True:
            t = time.perf_counter()
            app.processEvents()
            stalls.append((time.perf_counter() - t) * 1000)
            if until() or time.monotonic() > end:
                return
            time.sleep(0.005)

    statements = []
    w.org.catalog.db.set_trace_callback(statements.append)

    def timed(fn, n=7):
        """(median milliseconds of fn() and the layout and painting it causes, SQL statements of one run)."""
        ms = []
        for _ in range(n):
            statements.clear()
            t = time.perf_counter()
            fn()
            app.processEvents()
            ms.append((time.perf_counter() - t) * 1000)
        return round(statistics.median(ms), 1), len(statements)

    pump()
    cat = w.org.catalog
    out = {"documents": len(cat.all_documents()), "waiting": len(w.waiting()), "categories": len(cat.categories())}
    w.show_view(ALL)
    pump()
    out["refresh_all_documents"] = timed(w.refresh)
    out["sidebar"] = timed(w._fill_categories)
    keys = []
    for n in range(1, len("lecture 1") + 1):
        statements.clear()
        t = time.perf_counter()
        w.search.setText("lecture 1"[:n])
        app.processEvents()
        keys.append(((time.perf_counter() - t) * 1000, len(statements)))
    w.search.clear()
    out["search_key"] = (round(statistics.median(k[0] for k in keys), 1), max(k[1] for k in keys))
    out["search_key_slowest"] = (round(max(k[0] for k in keys), 1), max(k[1] for k in keys))  # the list changed
    w.show_view("category", cat.categories()[0]["id"])
    pump()
    out["refresh_category"] = timed(w.refresh)
    w.show_view(DECIDE)
    pump()
    out["decision_cards"] = len(w.decision.items)
    out["refresh_decision_page"] = timed(w.refresh, 5)

    # a card in use while 20 documents are imported
    built = []
    make = decision.DecisionItem.__init__

    def counting(self, *a, **k):
        built.append(1)
        make(self, *a, **k)
    decision.DecisionItem.__init__ = counting
    bar = w.decision.findChild(QScrollArea).verticalScrollBar()
    item = w.decision.items[12]
    doc = item.ids[0]
    item.toggle_expanded()
    item.picker.field.setText("my draft")
    pump()
    bar.setValue(bar.maximum() // 3)
    item.picker.field.setFocus()
    item.picker.field.setCursorPosition(3)
    pump()
    at = bar.value()
    del stalls[:]
    t = time.perf_counter()
    w.import_paths([str(p) for p in sorted((base / "more").iterdir())])
    pump(lambda: not w.inflight)
    pump()
    wall = time.perf_counter() - t
    decision.DecisionItem.__init__ = make
    same = next((i for i in w.decision.items if i.ids == [doc]), None)
    out["imports"] = {"documents": IMPORTS, "cards_built": len(built), "busy_s": round(sum(stalls) / 1000, 2),
                      "longest_stall_ms": round(max(stalls)), "wall_s": round(wall, 1),
                      "waiting_after": len(w.waiting())}
    out["draft"] = {"same_card": same is item, "panel_open": bool(same and same.expanded.isVisible()),
                    "text": same.picker.field.text() if same else None,
                    "cursor": same.picker.field.cursorPosition() if same else None,
                    "focus_in_field": bool(same and same.picker.field.hasFocus()),
                    "scroll_before": at, "scroll_after": bar.value()}
    w.close()
    return out


def report(out):
    i, d = out["imports"], out["draft"]
    kept = d["panel_open"] and d["text"] == "my draft" and d["focus_in_field"] and d["cursor"] == 3 \
        and d["scroll_before"] == d["scroll_after"]
    row = lambda name, key: f"  {name:<34}{out[key][0]:>8} ms  {out[key][1]:>4} statements"
    return "\n".join([
        f"{out['documents']} documents ({out['waiting']} waiting, {out['decision_cards']} decision cards),"
        f" {out['categories']} categories",
        f"{i['documents']} imports while on the decision page: {i['cards_built']} cards built; interface busy"
        f" {i['busy_s']} s of {i['wall_s']} s; longest stall {i['longest_stall_ms']} ms",
        row("Refresh: Needs your decision", "refresh_decision_page"),
        row("Refresh: All documents", "refresh_all_documents"),
        row("Refresh: a category", "refresh_category"),
        row("Sidebar", "sidebar"),
        row("One search key (median of 9)", "search_key"),
        row("One search key (slowest)", "search_key_slowest"),
        f"A card in use during the imports: {'kept' if kept else 'not kept'} (panel open {d['panel_open']},"
        f" text {d['text']!r}, cursor {d['cursor']}, focus {d['focus_in_field']},"
        f" scroll {d['scroll_before']} -> {d['scroll_after']})"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, help="an empty or new folder to build in (kept afterwards)")
    ap.add_argument("--json", type=Path, help="also write the numbers here")
    a = ap.parse_args(argv)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["CLASSIFILE_OCR"] = "off"
    base = a.base or Path(tempfile.mkdtemp(prefix="classifile-measure-"))
    if base.exists() and any(base.iterdir()):
        sys.exit(f"Refusing: {base} is not empty.")
    try:
        build(base)
        out = measure(base)
    finally:
        if not a.base:
            shutil.rmtree(base, ignore_errors=True)   # only the temporary folder this run made
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(report(out))


if __name__ == "__main__":
    main()
