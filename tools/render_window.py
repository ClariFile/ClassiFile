"""Offscreen renders of the main window for checking the layout, from copies of the development samples.

Usage: python -m tools.render_window [--out data] [--size 1280x720] [--scale 1.25]

Saves render-empty.png, render-list.png, render-decision.png (with a missing original and a group item),
render-decision-expanded.png, render-decision-details.png, render-dropdown-open.png, render-details.png, render-drop-overlay.png and render-1024x640.png at --size.
With --scale: render-scale-<N>-list.png, -decision.png, -decision-expanded.png, -decision-details.png and -details.png at --size
(logical pixels; the images are larger by the scale factor).
Renders use the Windows 11 style with a dark palette modelled on Windows' dark theme (offscreen rendering cannot
read the system theme, so colours are an approximation). Everything happens in a temporary folder with its own
catalog; the samples are only copied.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "document-organizer-claude-handoff" / "claude-handoff" / "samples"
FIXTURE_MAP = ROOT / "data" / "fixtures.json"   # local, not tracked: neutral IDs -> sample file names


def sample_names():
    """S1 (a deck that gets filed), S2 (a handout that gets a second version) and S5 (a lab guide whose copy moves)."""
    try:
        names = json.loads(FIXTURE_MAP.read_text(encoding="utf-8"))["samples"]
        return names["S1"], names["S2"], names["S5"]
    except (OSError, ValueError, KeyError):
        sys.exit(f"Renders need the sample PDFs and {FIXTURE_MAP} (see tests/conftest.py).")


def dark_palette():
    from PySide6.QtGui import QColor, QPalette
    p = QPalette()
    for role, colour in ((QPalette.Window, "#202020"), (QPalette.WindowText, "#FFFFFF"), (QPalette.Base, "#1C1C1C"),
                         (QPalette.AlternateBase, "#2B2B2B"), (QPalette.Text, "#FFFFFF"), (QPalette.Button, "#2D2D2D"),
                         (QPalette.ButtonText, "#FFFFFF"), (QPalette.Light, "#3C3C3C"), (QPalette.Midlight, "#353535"),
                         (QPalette.Mid, "#4A4A4A"), (QPalette.Dark, "#141414"), (QPalette.Shadow, "#000000"),
                         (QPalette.ToolTipBase, "#2B2B2B"), (QPalette.ToolTipText, "#FFFFFF"),
                         (QPalette.PlaceholderText, "#A8A8A8"), (QPalette.Highlight, "#0D9488"),
                         (QPalette.HighlightedText, "#FFFFFF"), (QPalette.Link, "#5EEAD4")):
        p.setColor(role, QColor(colour))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#7A7A7A"))
    return p


def render(out, scale=None, size=(1280, 720)):
    from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QFont, QFontDatabase, QPainter
    from classifile.app import make_app
    from classifile.app.main import ALL, DECIDE, MainWindow
    from classifile.catalog.db import Catalog
    from classifile.organizer import Organizer

    out.mkdir(parents=True, exist_ok=True)
    app = make_app([])
    app.setStyle("windows11")
    app.setPalette(dark_palette())
    for name in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf", "SegoeIcons.ttf", "segmdl2.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.exists():  # the offscreen platform has no fonts of its own
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI", 10))

    def pump(until=lambda: False, timeout=0.6):
        end = time.monotonic() + timeout
        while not until() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.05)
        app.processEvents()

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "src").mkdir()
        (work / "out").mkdir()
        catalog = Catalog(work / "catalog.sqlite3")
        org = Organizer(catalog)
        org.set_output_root(work / "out")
        w = MainWindow(org, ask_output_root=False)
        w.ask_close = lambda n: ("close", False)
        w.resize(*size)
        w.show()
        pump()
        if scale is None:
            w.grab().save(str(out / "render-empty.png"))
        deck, handout, lab = sample_names()
        for p in SAMPLES.glob("*.pdf"):
            shutil.copyfile(p, work / "src" / p.name)
        # Two versions of one handout (same text, different bytes) share a suggestion: a group item.
        data = (SAMPLES / handout).read_bytes()
        (work / "src" / f"{Path(handout).stem} (handout).pdf").write_bytes(data + b"\n% handout copy\n")
        moved = work / "src" / "handout 3,2024.pdf"
        moved.write_bytes((SAMPLES / lab).read_bytes() + b"\n% another copy\n")
        w.import_paths([str(p) for p in sorted((work / "src").glob("*.pdf"))])
        pump(lambda: not w.inflight, 120)
        moved.unlink()  # this original moved after it was added
        cst = next(d["id"] for d in w.waiting() if d["file_name"] == deck)
        top = (w.org.catalog.analysis(cst) or {}).get("suggestions") or [{"name": "Course Notes"}]
        w.file_docs([cst], top[0]["name"])
        pump(lambda: not w.filing, 30)
        w.toast.hide()
        w.refresh()
        pump()
        prefix = f"render-scale-{int(scale * 100)}-" if scale is not None else "render-"
        w.grab().save(str(out / f"{prefix}list.png"))
        w.sort.showPopup()  # the opened list is its own window: paint it onto the window image
        pump()
        shot, popup = w.grab(), w.sort.view().window()
        painter = QPainter(shot)
        painter.drawPixmap(w.mapFromGlobal(popup.mapToGlobal(QPoint(0, 0))), popup.grab())
        painter.end()
        shot.save(str(out / f"{prefix}dropdown-open.png"))
        w.sort.hidePopup()
        w.show_view(DECIDE)
        pump()
        w.grab().save(str(out / f"{prefix}decision.png"))
        item = next(i for i in w.decision.items if not i.group and not i.docs[0]["missing"])
        item.toggle_expanded()
        pump()
        w.grab().save(str(out / f"{prefix}decision-expanded.png"))
        w.show_details(item.ids[0])  # beside the item, on the same page
        pump()
        w.grab().save(str(out / f"{prefix}decision-details.png"))
        w.show_view(ALL)
        w.show_details(cst)
        pump()
        w.grab().save(str(out / f"{prefix}details.png"))
        if scale is not None:
            w.close()
            catalog.close()
            return out
        w.close_details()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(work / "src" / handout)), QUrl.fromLocalFile(str(work / "notes.txt"))])
        w.dragEnterEvent(QDragEnterEvent(QPoint(400, 300), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
        pump()
        w.grab().save(str(out / "render-drop-overlay.png"))
        w.overlay.hide()
        w.resize(1024, 640)
        pump()
        w.grab().save(str(out / "render-1024x640.png"))
        w.close()
        catalog.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    ap.add_argument("--scale", type=float, help="display scaling, e.g. 1.25 or 1.5")
    ap.add_argument("--size", default="1280x720", help="window size in logical pixels, e.g. 1536x864")
    a = ap.parse_args(argv)
    size = tuple(int(v) for v in a.size.lower().split("x"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("CLASSIFILE_OCR", "off")
    if a.scale:
        os.environ["QT_SCALE_FACTOR"] = str(a.scale)  # must be set before the application starts
    print(render(a.out.resolve(), a.scale, size))


if __name__ == "__main__":
    sys.exit(main())
