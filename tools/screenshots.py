"""Screenshots of the main window with a made-up library: no real document, name or person appears in them.

Usage: python -m tools.screenshots OUT [--size 1280x720] [--theme light|dark] [--views all,decide,...]

Builds a temporary catalog of made-up household documents (garden, recipes, travel, car, and a few photography
notes no category covers), files most of them as the user would, lets matching learn, and saves one PNG per
view in OUT: empty, all, category, decide, decide-details, auto, auto-details, settings, settings-advanced, help,
about, learn (the dialog) and tour. For the README (docs/images) and for before-and-after checks of the layout.
Nothing outside a temporary folder and OUT is written.
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

SUBJECTS = {
    "Garden": "tomato soil compost seedling pruning mulch harvest watering greenhouse",
    "Recipes": "flour butter oven simmer garlic onion recipe bake dough",
    "Travel": "passport flight hotel itinerary luggage booking airport visa",
    "Car": "engine tyre brake service mileage insurance garage oil",
}
FILES = {
    "Garden": ["Tomato care", "Compost guide", "Spring planting plan", "Pruning roses", "Greenhouse watering"],
    "Recipes": ["Sourdough bread", "Garlic soup", "Weekend baking list", "Onion tart", "Butter biscuits"],
    "Travel": ["Summer trip itinerary", "Hotel booking", "Visa checklist", "Airport parking", "Packing list"],
    "Car": ["Service record", "Tyre quotes", "Insurance renewal", "Brake repair invoice", "Oil change notes"],
}
NEW_SUBJECT = ("Photography", "aperture shutter lens exposure tripod focus portrait landscape",
               ["Camera settings", "Night photos", "Lens comparison"])
VIEWS = ("empty", "all", "category", "decide", "decide-details", "auto", "auto-details", "settings",
         "settings-advanced", "help", "about", "learn", "tour", "report")


def make_pdf(path, title, words, n):
    """A short two-page document about one subject, in plain sentences."""
    import pymupdf
    w = words.split()
    d = pymupdf.open()
    for page in range(2):
        p = d.new_page()
        if page == 0:
            p.insert_text((72, 110), title, fontsize=22)
        lines = [" ".join(w[(n + page + i + k) % len(w)] for k in range(5)).capitalize() + "." for i in range(12)]
        p.insert_text((72, 160), "\n".join(lines), fontsize=11, lineheight=1.6)
    d.save(path)
    d.close()


def build(base):
    """The made-up library: 4 categories of 4 documents the user filed, then 5 more that arrive later."""
    from classifile import matching
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer, read_and_analyze
    for name in ("src", "out", "later", "mine"):
        (base / name).mkdir(parents=True)
    org = Organizer(Catalog(base / "data" / "catalog.sqlite3"))
    org.set_output_root(base / "out")
    for subject, names in FILES.items():
        cat = org.create_category(subject)
        for n, name in enumerate(names[:4]):
            path = base / "src" / f"{name}.pdf"
            make_pdf(path, name, SUBJECTS[subject], n)
            doc, _ = org.record(path, *read_and_analyze(path))
            org.file(doc, cat)
        (base / "mine" / subject).mkdir()
    org.update_matching()
    later = [(s, names[4]) for s, names in FILES.items()] + [(NEW_SUBJECT[0], n) for n in NEW_SUBJECT[2]]
    for n, (subject, name) in enumerate(later):
        path = base / "later" / f"{name}.pdf"
        make_pdf(path, name, SUBJECTS.get(subject, NEW_SUBJECT[1]), n + 7)
        doc, _ = org.record(path, *read_and_analyze(path))
        if subject in ("Garden", "Travel"):
            org.file_automatically(doc)         # filed by the app: listed in Filed automatically
    for subject in ("Old receipts", "New folder"):
        (base / "mine" / subject).mkdir()
    for subject, names in FILES.items():        # an organized folder of the user's, for the Learn dialog
        for name in names[:2]:
            make_pdf(base / "mine" / subject / f"{name} (old).pdf", name, SUBJECTS[subject], 3)
    make_pdf(base / "mine" / "New folder" / "Untitled.pdf", "Untitled", "misc note page", 1)
    org.catalog.close()
    return matching


def render(out, size=(1280, 720), theme="light", views=VIEWS):
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from classifile.app import make_app
    from classifile.app.guide import ReportDialog, TourDialog
    from classifile.app.learn import LearnDialog
    from classifile.app.main import ABOUT, ALL, AUTO, DECIDE, HELP, SETTINGS, MainWindow, problem_report
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer

    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or make_app([])
    app.setStyle("windows11")
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf", "SegoeIcons.ttf", "segmdl2.ttf"):
        if (fonts / name).exists():             # the offscreen platform has no fonts of its own
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Segoe UI", 10))

    def pump(seconds=0.6):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.03)

    def window(base):
        org = Organizer(Catalog(base / "data" / "catalog.sqlite3"))
        if not (base / "out").exists():
            (base / "out").mkdir(parents=True)
            org.set_output_root(base / "out")
        w = MainWindow(org, ask_output_root=False)
        w.ask_close = lambda n: ("close", False)
        w.set_appearance(theme)
        w.resize(*size)
        w.show()
        pump()
        return w

    def mask(w):
        """The temporary folders hold the user's account name: Settings shows made-up folders instead."""
        w.root_label.setText(r"C:\Users\You\Documents\ClassiFile")
        w.tech.setText(w.tech.text().split("\n")[0] + "\n" + r"Data folder: C:\Users\You\AppData\Local\ClassiFile")

    def shot(w, name):
        if name in views:
            pump()
            w.grab().save(str(out / f"{name}.png"))

    with tempfile.TemporaryDirectory(prefix="classifile-shots-", ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        w = window(tmp / "empty")
        shot(w, "empty")
        w.close()
        w.org.catalog.close()
        build(tmp / "lib")
        w = window(tmp / "lib")
        w.show_view(ALL)
        shot(w, "all")
        cat = next(c["id"] for c in w.org.catalog.categories() if c["name"] == "Recipes")
        w.show_view("category", cat)
        shot(w, "category")
        w.show_view(DECIDE)
        shot(w, "decide")
        first = w.waiting_docs[0]["id"] if w.waiting_docs else None
        if first:
            w.show_details(first)
            shot(w, "decide-details")
            w.close_details()
        w.show_view(AUTO)
        shot(w, "auto")
        filed = [i.doc_id for i in w.auto_page.items] if hasattr(w.auto_page, "items") else []
        if filed:
            w.show_details(filed[0])
            shot(w, "auto-details")
            w.close_details()
        w.show_view(SETTINGS)
        mask(w)
        shot(w, "settings")
        w.advanced.toggle.setChecked(True)
        mask(w)
        pump()
        w.settings_page.verticalScrollBar().setValue(w.settings_page.verticalScrollBar().maximum())
        shot(w, "settings-advanced")
        w.show_view(HELP)
        shot(w, "help")
        w.show_view(ABOUT)
        shot(w, "about")
        if "learn" in views:
            found = w.org.scan_folder(tmp / "lib" / "mine")
            d = LearnDialog(w, tmp / "lib" / "mine", found, {c["name_key"]: c["name"] for c in w.org.catalog.categories()})
            d.show()
            pump()
            d.grab().save(str(out / "learn.png"))
            d.close()
        if "tour" in views:
            t = TourDialog(w, learn=True)
            t.show()
            pump()
            t.grab().save(str(out / "tour.png"))
            t.close()
        if "report" in views:
            r = ReportDialog(w, problem_report(w.org.catalog))
            r.show()
            pump()
            r.grab().save(str(out / "report.png"))
            r.close()
        w.close()
        w.org.catalog.close()
        pump(0.2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--theme", choices=("light", "dark"), default="light")
    ap.add_argument("--views", default=",".join(VIEWS))
    a = ap.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["CLASSIFILE_OCR"] = "off"        # made-up text only: nothing to read in pictures
    render(a.out, tuple(int(x) for x in a.size.split("x")), a.theme, a.views.split(","))
    print(f"Saved to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
