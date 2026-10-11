"""Label units one at a time. Backspace goes back to the previous unit; every answer is saved at once.

Usage:
  python -m tools.label_window [data/page_labels.csv]            E8: is there content the normal text misses?
                                                                  Y yes, N no, S skip
  python -m tools.label_window --quality [data/ocr_quality.csv]  OCR quality: G good, P partly, B bad, S skip;
                                                                  D = the greyed (dropped) lines had real text
  python -m tools.label_window --names [data/name_review.csv]    Suggested names, one file per screen:
                                                                  1/2/3 mark good names, Enter, 0 none, S skip

The E8 pass shows the rendered page (PDFs) or the unit's pictures next to the unit's normal text, and never shows
whether the rule flagged the unit or what OCR found. The quality pass shows the pictures and the text OCR read,
with the lines the junk filter drops greyed out. Answers are appended to <sheet>.answers.csv, so labelling can
stop and resume at any time; skipped units come back after the unanswered ones. Sources are read from temporary
copies; data/final-eval is refused.
"""
import html
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QTextEdit, QVBoxLayout,
    QWidget,
)

from classifile.app import make_app
from classifile.app.preview import PdfPages, first_page_png
from classifile.organizer import read_and_analyze
from classifile.reader import read_document
from classifile.reader.common import package_part
from classifile.worker import WorkerPool
from tools import refuse_final_eval
from tools.ocr_quality import DEFAULT_OUT as QUALITY_SHEET
from tools.name_review import BETTER, FILE_ANSWER
from tools.name_review import DEFAULT_OUT as NAMES_SHEET
from tools.ocr_quality import DROPPED
from tools.page_labels import DEFAULT_OUT, append_answer, read_answers, read_rows

PICTURE_WIDTH = 760
MODES = {
    "unread": {
        "title": "ClassiFile — page labels",
        "question": "Does this unit carry meaningful content that its normal text misses "
                    "(text or information inside pictures)?",
        "keys": {Qt.Key_Y: "yes", Qt.Key_N: "no", Qt.Key_S: "skip"},
        "answered": ("yes", "no"),
        "help": "Y = yes    N = no    S = skip    Backspace = back",
    },
    "quality": {
        "title": "ClassiFile — OCR quality",
        "question": "How well did OCR read the text in these pictures? Greyed, struck-through lines are dropped "
                    "as junk and never used.",
        "keys": {Qt.Key_G: "good", Qt.Key_P: "partly", Qt.Key_B: "bad", Qt.Key_S: "skip"},
        "answered": ("good", "partly", "bad"),
        "help": "G = good    P = partly    B = bad    S = skip    "
                "D = the greyed lines contained real text    Backspace = back",
    },
}


class Sources:
    """Temporary copies of the source files, each read once. With a worker pool, reads run in a separate
    process (OCR included) and are prefetched in the background."""

    def __init__(self, workers=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.copies, self.records = {}, {}
        self.workers = workers
        self.prefetch = ThreadPoolExecutor(max_workers=1) if workers else None

    def copy(self, source):
        if source not in self.copies:
            refuse_final_eval(source)
            self.copies[source] = Path(self.tmp.name) / f"{len(self.copies):04d}{Path(source).suffix.lower()}"
            shutil.copyfile(source, self.copies[source])
        return self.copies[source]

    def _read(self, source):
        copy = self.copy(source)
        return self.workers.run(copy)[0].record if self.workers else read_document(copy).record

    def start(self, sources):
        for s in dict.fromkeys(sources):
            self.copy(s)
            if self.prefetch:
                self.records[s] = self.prefetch.submit(self._read, s)

    def ready(self, source):
        r = self.records.get(source)
        return r is not None and (not hasattr(r, "done") or r.done())

    def unit(self, source, index):
        if source not in self.records:
            self.records[source] = self._read(source)
        rec = self.records[source]
        rec = rec.result() if hasattr(rec, "result") else rec
        return rec.units[index - 1] if rec else None

    def pictures(self, source, unit, ocr_regions=False):
        """PNG bytes to show: the whole page for PDFs, else each picture (None where it cannot be drawn).
        ocr_regions: for PDFs, only the regions OCR read, so the answer is about them and not the page's other text."""
        path = self.copy(source)
        if path.suffix == ".pdf":
            with pymupdf.open(path) as d:
                page = d[unit.index - 1]
                clips = [lay["region"] for lay in unit.ocr_layout if lay.get("region")] if ocr_regions else []
                return ([page.get_pixmap(dpi=110, clip=c).tobytes("png") for c in clips]
                        or [page.get_pixmap(dpi=110).tobytes("png")])
        out = []
        for ref in unit.pictures:
            try:
                with pymupdf.open(stream=package_part(path, ref)) as d:
                    out.append(d[0].get_pixmap(dpi=96).tobytes("png"))
            except Exception:  # e.g. EMF/WMF
                out.append(None)
        return out

    def close(self):
        if self.prefetch:
            self.prefetch.shutdown(wait=False, cancel_futures=True)
        if self.workers:
            self.workers.close()
        self.tmp.cleanup()


def ocr_html(unit):
    """What OCR read, with the lines the junk filter dropped greyed out and struck through."""
    if not unit.ocr_raw_text:
        return ("<i>[OCR found no text in this unit's pictures]</i>" if unit.ocr_status
                else "<i>[OCR did not run on this unit]</i>")
    kept = set((unit.ocr_text or "").splitlines())
    lines = []
    for line in unit.ocr_raw_text.splitlines():
        if " ".join(line.split()):
            lines.append(html.escape(line) if " ".join(line.split()) in kept else
                         f'<span style="color:#999;text-decoration:line-through">{html.escape(line)}</span>')
    return "<br>".join(lines)


class LabelWindow(QWidget):
    def __init__(self, labels, mode="unread", workers=None):
        super().__init__()
        self.labels, self.mode, self.cfg = Path(labels), mode, MODES[mode]
        refuse_final_eval(self.labels)
        rows = read_rows(self.labels)
        for r in rows:
            if r.get("source"):
                refuse_final_eval(r["source"])
        self.answers = read_answers(self.labels)
        self.dropped = read_answers(self.labels, kind=DROPPED)
        self.rows = rows
        self.todo = [r for r in rows if r.get("unit") and r.get("label_source") != "auto"
                     and r.get("kind") != "no suggestion"]
        fresh = [r for r in self.todo if self._answer(r) is None]
        skipped = [r for r in self.todo if self._answer(r) == "skip"]
        self.queue, self.pos, self.history = fresh + skipped, 0, []
        self.sources = Sources(workers)
        self.sources.start(r["source"] for r in self.queue)
        self._build()
        self.show_current()

    def _answer(self, r):
        return self.answers.get((r["file"], r["unit"]))

    def _build(self):
        self.setWindowTitle(self.cfg["title"])
        self.resize(1300, 850)
        self.header = QLabel()
        self.question = QLabel(self.cfg["question"])
        self.question.setWordWrap(True)
        self.note = QLabel()
        self.pictures = QVBoxLayout()
        holder = QWidget()
        holder.setLayout(self.pictures)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFocusPolicy(Qt.NoFocus)  # keys go to the window
        body = QHBoxLayout()
        body.addWidget(scroll, 3)
        body.addWidget(self.text, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(self.question)
        layout.addLayout(body, 1)
        layout.addWidget(self.note)
        layout.addWidget(QLabel(self.cfg["help"]))

    def labelled(self):
        return sum(1 for r in self.todo if self._answer(r) in self.cfg["answered"])

    def _loading(self):
        r = self.queue[self.pos] if self.pos < len(self.queue) else None
        return r is not None and self.sources.prefetch is not None and not self.sources.ready(r["source"])

    def show_current(self):
        while self.pictures.count():
            self.pictures.takeAt(0).widget().deleteLater()
        self.note.clear()
        if self.pos >= len(self.queue):
            left = len(self.todo) - self.labelled()
            self.header.setText(f"Done: {self.labelled()} of {len(self.todo)} labelled"
                                + (f", {left} skipped (shown again next time)." if left else ".")
                                + " Tell Claude when you have finished.")
            self.text.clear()
            return
        r = self.queue[self.pos]
        self.header.setText(f"Item {self.todo.index(r) + 1} of {len(self.todo)}  ·  {self.labelled()} answered  —  "
                            f"{r['file']}  ·  {r['kind']} {r['unit']}")
        answer = self._answer(r)
        dropped = " · greyed lines marked as real text" if self.dropped.get((r["file"], r["unit"])) == "yes" else ""
        self.note.setText(f"Your answer: {answer if answer in self.cfg['answered'] else 'not answered yet'}{dropped}")
        if self._loading():
            self.text.setPlainText("Reading this document (with OCR)…")
            QTimer.singleShot(300, self.show_current)
            return
        unit = self.sources.unit(r["source"], int(r["unit"]))
        for png in self.sources.pictures(r["source"], unit, ocr_regions=self.mode == "quality"):
            label = QLabel()
            if png is None:
                label.setText("[this picture's format cannot be shown]")
            else:
                pix = QPixmap()
                pix.loadFromData(png)
                label.setPixmap(pix.scaledToWidth(min(PICTURE_WIDTH, pix.width()), Qt.SmoothTransformation))
            self.pictures.addWidget(label)
        if self.mode == "quality":
            self.text.setHtml(ocr_html(unit))
        else:
            text = unit.text + (f"\n\n— Speaker notes —\n{unit.notes}" if unit.notes else "")
            self.text.setPlainText(text.strip() or "[no normal text]")

    def keyPressEvent(self, e):
        keys = self.cfg["keys"]
        if self._loading():
            return
        if e.key() in keys and self.pos < len(self.queue):
            r = self.queue[self.pos]
            append_answer(self.labels, r["file"], r["unit"], keys[e.key()])
            self.answers[(r["file"], r["unit"])] = keys[e.key()]
            self.history.append(self.pos)
            self.pos += 1
            self.show_current()
        elif e.key() == Qt.Key_D and self.mode == "quality" and self.pos < len(self.queue):
            r = self.queue[self.pos]
            append_answer(self.labels, r["file"], r["unit"], "yes", kind=DROPPED)
            self.dropped[(r["file"], r["unit"])] = "yes"
            self.note.setText(self.note.text().split(" · ")[0] + " · greyed lines marked as real text")
        elif e.key() == Qt.Key_Backspace and self.history:
            self.pos = self.history.pop()  # the next answer is appended and replaces this one
            self.show_current()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self.sources.close()
        super().closeEvent(e)


class NameReviewWindow(QWidget):
    """One screen per file: its top three names with their reasons, and the user's marks."""

    HELP = ("Which of these would be a good category name for this document? Press 1, 2 or 3 to mark each good "
            "name (press again to unmark), then Enter. Press 0 if none is good. Press S to skip if you're unsure.")

    def __init__(self, labels):
        super().__init__()
        self.labels = Path(labels)
        refuse_final_eval(self.labels)
        rows = read_rows(self.labels)
        for r in rows:
            refuse_final_eval(r["source"])
        self.answers = read_answers(self.labels)
        files = {}
        for r in rows:
            if r["kind"] == "name":
                files.setdefault(r["file"], []).append(r)
        self.files = list(files.items())
        self.sources = Sources()
        self.pdf, self.page, self.marks, self.history = None, 0, set(), []
        self._build()
        self.pos = self._next_unanswered(-1)
        self.show_current()

    def _answered(self, i):
        f, names = self.files[i]
        return any(self.answers.get((f, r["unit"])) in ("good", "bad") for r in names)

    def _next_unanswered(self, after):
        order = list(range(after + 1, len(self.files))) + list(range(0, after + 1))
        fresh = [i for i in order if not self._answered(i) and self.answers.get((self.files[i][0], FILE_ANSWER)) != "skip"]
        skipped = [i for i in order if not self._answered(i) and i not in fresh]
        return (fresh + skipped + [len(self.files)])[0]

    def _build(self):
        self.setWindowTitle("ClassiFile — name review")
        self.resize(1300, 850)
        self.progress = QLabel()
        font = self.progress.font()
        font.setBold(True)
        self.progress.setFont(font)
        self.help = QLabel(self.HELP)
        self.help.setWordWrap(True)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.image)
        self.prev = QPushButton("‹ Previous")
        self.prev.clicked.connect(lambda: self.show_page(self.page - 1))
        self.next = QPushButton("Next ›")
        self.next.clicked.connect(lambda: self.show_page(self.page + 1))
        for b in (self.prev, self.next):
            b.setFocusPolicy(Qt.NoFocus)
        self.page_label = QLabel()
        self.page_label.setAlignment(Qt.AlignCenter)
        nav = QHBoxLayout()
        nav.addWidget(self.prev)
        nav.addWidget(self.page_label, 1)
        nav.addWidget(self.next)
        left = QVBoxLayout()
        left.addWidget(scroll, 1)
        left.addLayout(nav)
        self.names = QListWidget()
        self.names.setFocusPolicy(Qt.NoFocus)
        self.names.setWordWrap(True)
        self.names.itemClicked.connect(self._jump)
        self.better = QLineEdit()
        self.better.setPlaceholderText("Optional: a better name, if none fits (Tab to reach, Enter to save)")
        self.better.installEventFilter(self)
        right = QVBoxLayout()
        right.addWidget(QLabel("Suggested names (click a name to see where it appears):"))
        right.addWidget(self.names, 1)
        right.addWidget(QLabel("Better name:"))
        right.addWidget(self.better)
        body = QHBoxLayout()
        body.addLayout(left, 3)
        body.addLayout(right, 2)
        v = QVBoxLayout(self)
        v.addWidget(self.progress)
        v.addWidget(self.help)
        v.addLayout(body, 1)
        v.addWidget(QLabel("1 / 2 / 3 = mark or unmark    Enter = save and next    0 = none is good    S = skip    "
                           "Backspace = previous file    PageUp / PageDown = pages"))

    def current(self):
        return self.files[self.pos] if self.pos < len(self.files) else None

    def show_current(self):
        if self.pdf:
            self.pdf.close()
            self.pdf = None
        cur = self.current()
        if cur is None:
            done = sum(self._answered(i) for i in range(len(self.files)))
            self.progress.setText(f"Done: {done} of {len(self.files)} files reviewed. Tell Claude when you have finished.")
            self.names.clear()
            self.image.clear()
            return
        f, names = cur
        self.progress.setText(f"File {self.pos + 1} of {len(self.files)}  —  {f}")
        self.marks = {r["unit"] for r in names if self.answers.get((f, r["unit"])) == "good"}
        self.better.setText(self.answers.get((f, BETTER)) or "")
        copy = self.sources.copy(names[0]["source"])
        self.page = 0
        if copy.suffix == ".pdf":
            try:
                self.pdf = PdfPages(copy)
            except Exception:
                self.pdf = None
        if self.pdf:
            self.show_page(0)
        else:  # no paging without other programs: the stored thumbnail, or the first lines
            png = first_page_png(copy, width=PICTURE_WIDTH)
            if png:
                pix = QPixmap()
                pix.loadFromData(png)
                self.image.setPixmap(pix)
            else:
                rec = self.sources.unit(names[0]["source"], 1)
                self.image.setText(rec.text[:600] if rec else "No preview")
            self.page_label.setText("Page images are shown for PDFs; this format shows its first page only.")
            self.prev.setEnabled(False)
            self.next.setEnabled(False)
        self._show_names()
        self.setFocus()

    def _show_names(self):
        f, names = self.current()
        answered = any(self.answers.get((f, r["unit"])) in ("good", "bad") for r in names)
        self.names.clear()
        for r in names:
            mark = "✓ good" if r["unit"] in self.marks else ("✗ not good" if answered else "")
            where = f" (page {r['page']})" if r["page"] else ""
            item = QListWidgetItem(f"{r['unit']}.  {r['name']}    {mark}\n      {r['reason'] or 'no page reference'}{where}")
            item.setData(Qt.UserRole, r)
            self.names.addItem(item)

    def show_page(self, index):
        if not self.pdf:
            return
        self.page = max(0, min(self.pdf.count - 1, index))
        pix = QPixmap()
        pix.loadFromData(self.pdf.png(self.page, PICTURE_WIDTH))
        self.image.setPixmap(pix)
        self.page_label.setText(f"Page {self.page + 1} of {self.pdf.count}")
        self.prev.setEnabled(self.page > 0)
        self.next.setEnabled(self.page < self.pdf.count - 1)

    def _jump(self, item):
        r = item.data(Qt.UserRole)
        if r["page"] and self.pdf:
            self.show_page(int(r["page"]) - 1)

    def _save(self, none_good=False):
        f, names = self.current()
        if none_good:
            self.marks = set()
        for r in names:
            answer = "good" if r["unit"] in self.marks else "bad"
            append_answer(self.labels, f, r["unit"], answer)
            self.answers[(f, r["unit"])] = answer
        better = " ".join(self.better.text().split())
        if better or self.answers.get((f, BETTER)):
            append_answer(self.labels, f, BETTER, better)
            self.answers[(f, BETTER)] = better
        self._advance()

    def _advance(self):
        self.history.append(self.pos)
        self.pos = self._next_unanswered(self.pos)
        self.show_current()

    def eventFilter(self, obj, e):
        if obj is self.better and e.type() == QEvent.KeyPress:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.current():
                self._save()
                return True
            if e.key() == Qt.Key_Escape:
                self.setFocus()
                return True
        return super().eventFilter(obj, e)

    def keyPressEvent(self, e):
        key, cur = e.key(), self.current()
        if key in (Qt.Key_PageDown, Qt.Key_PageUp):
            self.show_page(self.page + (1 if key == Qt.Key_PageDown else -1))
        elif key == Qt.Key_Backspace and self.history:
            self.pos = self.history.pop()  # answers stay editable; saving again replaces them
            self.show_current()
        elif cur and key in (Qt.Key_1, Qt.Key_2, Qt.Key_3):
            rank = str(key - Qt.Key_0)
            if any(r["unit"] == rank for r in cur[1]):
                self.marks ^= {rank}
                self._show_names()
        elif cur and key in (Qt.Key_Return, Qt.Key_Enter):
            self._save()
        elif cur and key == Qt.Key_0:
            self._save(none_good=True)
        elif cur and key == Qt.Key_S:
            append_answer(self.labels, cur[0], FILE_ANSWER, "skip")
            self.answers[(cur[0], FILE_ANSWER)] = "skip"
            self._advance()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.pdf:
            self.pdf.close()
        self.sources.close()
        super().closeEvent(e)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    mode = "quality" if "--quality" in args else "names" if "--names" in args else "unread"
    args = [a for a in args if a not in ("--quality", "--names")]
    labels = Path(args[0]) if args else {"quality": QUALITY_SHEET, "names": NAMES_SHEET}.get(mode, DEFAULT_OUT)
    if not labels.exists():
        sys.exit(f"No sheet at {labels}.")
    if mode in ("unread", "names"):
        os.environ["CLASSIFILE_OCR"] = "off"  # these passes show pages and names, never OCR output
    app = make_app(sys.argv[:1])
    if mode == "names":
        w = NameReviewWindow(labels)
    else:
        w = LabelWindow(labels, mode, workers=WorkerPool(read_and_analyze, size=1) if mode == "quality" else None)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
