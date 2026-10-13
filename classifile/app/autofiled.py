"""The "Filed automatically" page: what the app filed by itself, each with its reason. "Looks right" records the
user's confirmation (for one document, or for all the ticked ones); Move to… is the correction."""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from classifile.app.reasons import similar_reason
from classifile.app.widgets import GROUP, PANEL, ElidedLabel, box, format_icon


class AutoItem(QFrame):
    def __init__(self, doc, controller):
        super().__init__()
        self.setObjectName("decision")          # the same row style as a decision item
        self.doc_id = doc["id"]
        self.tick = QCheckBox()
        self.tick.setToolTip("Tick several documents to confirm them together")
        icon = QLabel()
        icon.setPixmap(format_icon(doc["file_name"]).pixmap(20, 20))
        self.title = ElidedLabel(doc["file_name"])
        self.title.setStyleSheet("font-weight: 600;")
        head = box(QHBoxLayout())
        head.addWidget(self.tick)
        head.addWidget(icon)
        head.addWidget(self.title, 1)
        why = json.loads(doc["auto_json"] or "{}").get("documents")
        self.reason = ElidedLabel(f"Filed in {doc['category']}" + (
            f"  ·  {similar_reason(why, doc['category'])}" if why else ""), "secondary")
        self.right = QPushButton("Looks right")
        self.right.setToolTip("Confirm this category. ClassiFile learns from documents you confirm.")
        self.right.clicked.connect(lambda: controller.looks_right([self.doc_id]))
        self.move = QPushButton("Move to…")
        self.move.setToolTip("Wrong category? Choose the right one. Your choice is what ClassiFile learns from.")
        self.move.clicked.connect(lambda: controller.move_docs([self.doc_id]))
        text = box(QVBoxLayout())
        text.addLayout(head)
        text.addWidget(self.reason)
        row = box(QHBoxLayout(self), (0, PANEL, 0, PANEL), GROUP)
        row.addLayout(text, 1)
        row.addWidget(self.right)
        row.addWidget(self.move)


class AutoPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c, self.items, self.state = controller, [], None
        holder = QWidget()
        self.list = box(QVBoxLayout(holder), (0, 0, GROUP, 0), 0)   # room for the scroll bar
        self.list.addStretch(1)                                     # always last; the items go before it
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(holder)
        self.empty = QLabel("Nothing was filed automatically.\nA document that clearly matches one of your "
                            "categories is filed without a question and listed here with the reason.")
        self.empty.setObjectName("secondary")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)            # a long line here would set the least width of every page
        self.all = QCheckBox("Select all")
        self.all.clicked.connect(lambda on: [i.tick.setChecked(on) for i in self.items])
        self.right = QPushButton()                 # for the ticked documents, together
        self.right.setObjectName("primary")
        self.right.clicked.connect(lambda: self.c.looks_right(self.ticked()))
        self.bar = QWidget()
        bar = box(QHBoxLayout(self.bar), spacing=GROUP)
        bar.addWidget(self.all)
        bar.addWidget(self.right)
        bar.addStretch(1)
        v = box(QVBoxLayout(self))
        v.addWidget(self.bar)
        v.addWidget(scroll, 1)
        v.addWidget(self.empty)

    def ticked(self):
        return [i.doc_id for i in self.items if i.tick.isChecked()]

    def _ticks_changed(self):
        n = len(self.ticked())
        self.right.setText(f"Looks right ({n})" if n else "Looks right")
        self.right.setEnabled(bool(n))
        self.all.setChecked(bool(n) and n == len(self.items))

    def show_docs(self, docs):
        """docs: the catalog's rows for the documents the app filed by itself. Rebuilt only when they changed."""
        docs = sorted(docs, key=lambda d: d["filed_at"] or "", reverse=True)   # the latest first
        state = [(d["id"], d["file_name"], d["category"], d["auto_json"]) for d in docs]
        if state == self.state:
            return
        self.state = state
        for item in self.items:
            self.list.removeWidget(item)
            item.hide()
            item.deleteLater()
        self.items = [AutoItem(d, self.c) for d in docs]
        for n, item in enumerate(self.items):
            self.list.insertWidget(n, item)
            item.tick.toggled.connect(self._ticks_changed)
        self.empty.setVisible(not docs)
        self.bar.setVisible(bool(docs))
        self._ticks_changed()
