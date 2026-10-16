"""Help, About and the first-run tour (decision record 2.9): plain words about what ClassiFile does and never does.
The pages use the whole window; their text keeps a readable line length."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from classifile import __version__
from classifile.app.widgets import GROUP, PAD, PANEL, READABLE, RELATED, SECTION, SUPPORTED, TIGHT, box
SOURCE = "https://github.com/ClariFile/ClassiFile"

_HELP = [
    ("What ClassiFile does",
     "ClassiFile sorts your documents into categories by what they say, not by their file names. It puts a copy of "
     f"each document in the category's folder inside your output folder. It reads {SUPPORTED} files."),
    ("Adding documents",
     "Drop files on the window or press Add documents. ClassiFile reads each one (pictures of text too) and then "
     "either files it or asks you."),
    ("Automatic filing",
     "When one category is clearly the best fit and already holds 3 documents you confirmed, ClassiFile files the "
     "document by itself. Otherwise it asks. Settings, Automatic filing, sets how sure it must be; Strict is the "
     "default."),
    ("Needs your decision",
     "Documents ClassiFile is unsure about wait here. Each shows the categories that fit best: choose one, or type "
     "a new name. Details shows the document's pages and why a category was suggested."),
    ("Filed automatically and “Looks right”",
     "Everything ClassiFile filed by itself is listed in Filed automatically, with the reason. Press Looks right "
     "when it is right: ClassiFile learns from that. If it is wrong, use Move to…."),
    ("Move to…",
     "Move to… puts a document in another category. ClassiFile makes the new copy first and removes the old copy "
     "only if you haven't changed it. Moving teaches ClassiFile too."),
    ("New folders",
     "When at least three waiting documents share a subject that none of your categories covers, ClassiFile can "
     "create a folder for them by itself and names it. Rename it with one click. You can switch this off in "
     "Settings."),
    ("Check these",
     "Sometimes a filed document reads much more like another category. It is listed under Check these, at the "
     "top of Needs your decision. Choose Keep here or Move to…; nothing is moved for you."),
    ("Learning from your folders",
     "If you already keep documents in folders, use Settings, Learn from my existing folders. Each folder becomes "
     "a category and its documents become examples. Your files are only read: nothing is moved or copied. You can "
     "untick and rename folders first, and forget a folder later."),
    ("How ClassiFile learns",
     "It learns from what you file, confirm and move, and from your examples. It updates by itself after every 10 "
     "of them, and keeps the old version if the new one does worse."),
    ("What never happens",
     "Your original files are never changed, moved, renamed or deleted. Nothing is written into any document. "
     "Nothing is sent over the internet: ClassiFile works entirely on your computer."),
]

_ABOUT = [
    ("ClassiFile", f"Version {__version__}. ClassiFile organizes copies of your documents into categories, by "
                   "their content, so you can find them again without sorting them by hand."),
    ("How it works",
     "It reads the text of each document, compares it with the documents already in each category, and files it "
     "when one category is clearly the best fit. When it isn't sure, it asks you, and it learns from your answers."),
    ("Privacy",
     "Everything happens on your computer. ClassiFile makes no internet connection. It never changes your original "
     "files and never writes anything into a document; it works on copies."),
    ("ClariFile",
     "ClassiFile is part of the ClariFile suite. Its companion, SummarEase, will summarize documents and pasted "
     "text at several levels of detail. Each app works on its own."),
    ("Licences and credits",
     "ClassiFile is free software under the GNU Affero General Public License, version 3 (AGPL-3.0). It is built "
     "with PyMuPDF by Artifex (AGPL-3.0), Qt for Python by The Qt Company (LGPL-3.0) and the Tesseract OCR "
     "engine (Apache License 2.0)."),
    ("Source", f"The source code is at <a href=\"{SOURCE}\">{SOURCE}</a>."),
]


# Each page: captioned sections, each a card of topics in the order its caption lists them.
def _sections(topics, groups):
    by = dict(topics)
    return [(caption, [(h, by[h]) for h in heads]) for caption, heads in groups]


HELP = _sections(_HELP, [
    ("Getting started", ["What ClassiFile does", "Adding documents", "Learning from your folders"]),
    ("Filing", ["Automatic filing", "Needs your decision", "Check these", "New folders"]),
    ("Correcting and learning", ["Filed automatically and “Looks right”", "Move to…", "How ClassiFile learns"]),
    ("Your files", ["What never happens"]),
])
ABOUT = _sections(_ABOUT, [
    ("Overview", ["ClassiFile", "How it works", "Privacy"]),
    ("The ClariFile suite", ["ClariFile"]),
    ("Licences", ["Licences and credits", "Source"]),
])


def text_page(title, sections, extra=None):
    """A page of captioned sections, each a card of headed paragraphs (the Settings card style), in one readable
    column on a page as wide as the window. sections: [(caption, [(heading, text)])]. title: a lead line under the
    page's own title (None for none); extra: a widget placed after it (buttons)."""
    outer = QScrollArea()
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.NoFrame)
    page = QWidget()
    page.setContentsMargins(0, 0, GROUP, PAD)   # room for the scroll bar, and below the last card
    outer.setWidget(page)
    column = QWidget()
    column.setMaximumWidth(READABLE + 2 * PANEL)    # the cards' text keeps a readable line length
    v = box(QVBoxLayout(column), spacing=RELATED)
    if title:
        lead = QLabel(title)
        lead.setObjectName("heading")
        lead.setWordWrap(True)
        v.addWidget(lead)
    if extra is not None:
        v.addWidget(extra, 0, Qt.AlignLeft)
    for n, (caption, topics) in enumerate(sections):
        if n or title or extra is not None:
            v.addSpacing(SECTION - RELATED)
        c = QLabel(caption.upper())
        c.setObjectName("section")
        v.addWidget(c)
        card = QFrame()
        card.setObjectName("settingsCard")
        inside = box(QVBoxLayout(card), PANEL, TIGHT)
        for k, (heading, text) in enumerate(topics):
            if k:
                inside.addSpacing(GROUP)
            h = QLabel(heading)
            h.setObjectName("heading")
            p = QLabel(text)
            p.setWordWrap(True)
            p.setTextFormat(Qt.RichText if "<a " in text else Qt.PlainText)
            p.setOpenExternalLinks(True)        # only when the user clicks: ClassiFile itself connects to nothing
            p.setTextInteractionFlags(Qt.TextBrowserInteraction)
            p.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            inside.addWidget(h)
            inside.addWidget(p)
        v.addWidget(card)
    v.addStretch(1)
    row = box(QHBoxLayout(page))
    row.addWidget(column, 1)
    row.addStretch(0)
    outer.texts = [title or ""] + [t for _, topics in sections for s in topics for t in s]
    return outer


TOUR = [
    ("Welcome to ClassiFile",
     "ClassiFile sorts copies of your documents into categories by what they say. Your original files are never "
     "changed, and nothing is sent over the internet."),
    ("Start with what you have",
     "Drop documents on the window, or press Add documents. If you already keep documents in folders, ClassiFile "
     "can learn from them first: Learn from my existing folders."),
    ("It files when it is sure",
     "Once a category holds 3 documents you confirmed, ClassiFile files clear matches by itself. You'll find them "
     "in Filed automatically: press Looks right, or Move to… if one is wrong."),
    ("It asks when it isn't",
     "Documents it is unsure about wait in Needs your decision, with the categories that fit best. Help, in the "
     "sidebar, explains everything again."),
]


class TourDialog(QDialog):
    """The first-run tour: four short steps, Back and Next, and a way out at every step. learn: called when the user
    chooses to learn from their folders at the end."""

    def __init__(self, parent, learn=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to ClassiFile")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.learn_chosen = False
        self.steps = QStackedWidget()
        for i, (title, text) in enumerate(TOUR, start=1):
            step = QWidget()
            s = box(QVBoxLayout(step), spacing=RELATED)
            count = QLabel(f"Step {i} of {len(TOUR)}")
            count.setObjectName("secondary")
            heading = QLabel(title)
            heading.setObjectName("heading")
            body = QLabel(text)
            body.setWordWrap(True)
            s.addWidget(count)
            s.addWidget(heading)
            s.addWidget(body)
            s.addStretch(1)
            self.steps.addWidget(step)
        self.skip = QPushButton("Skip")
        self.skip.clicked.connect(self.reject)
        self.back = QPushButton("Back")
        self.back.clicked.connect(lambda: self.go(-1))
        self.learn = QPushButton("Learn from my existing folders…")
        self.learn.clicked.connect(self._learn)
        self.learn.setVisible(learn is not None)
        self.next = QPushButton()
        self.next.setObjectName("primary")
        self.next.clicked.connect(lambda: self.go(1))
        buttons = box(QHBoxLayout(), spacing=RELATED)
        buttons.addWidget(self.skip)
        buttons.addStretch(1)
        buttons.addWidget(self.back)
        buttons.addWidget(self.learn)
        buttons.addWidget(self.next)
        v = box(QVBoxLayout(self), PANEL, GROUP)
        v.addWidget(self.steps, 1)
        v.addLayout(buttons)
        self.has_learn = learn is not None
        self.go(0)

    def go(self, step):
        i = self.steps.currentIndex() + step
        if i >= self.steps.count():
            return self.accept()
        self.steps.setCurrentIndex(i)
        last = i == self.steps.count() - 1
        self.back.setVisible(i > 0)
        self.skip.setVisible(not last)
        self.learn.setVisible(last and self.has_learn)
        self.next.setText("Get started" if last else "Next")

    def _learn(self):
        self.learn_chosen = True
        self.accept()
