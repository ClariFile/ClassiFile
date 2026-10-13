"""The "Filed automatically" page: what the app filed by itself, each with its reason and a Move to… button."""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from classifile.app.reasons import similar_reason
from classifile.app.widgets import GROUP, PANEL, ElidedLabel, box, format_icon


class AutoItem(QFrame):
    def __init__(self, doc, controller):
        super().__init__()
        self.setObjectName("decision")          # the same row style as a decision item
        self.doc_id = doc["id"]
        icon = QLabel()
        icon.setPixmap(format_icon(doc["file_name"]).pixmap(20, 20))
        self.title = ElidedLabel(doc["file_name"])
        self.title.setStyleSheet("font-weight: 600;")
        head = box(QHBoxLayout())
        head.addWidget(icon)
        head.addWidget(self.title, 1)
        why = json.loads(doc["auto_json"] or "{}").get("documents")
        self.reason = ElidedLabel(f"Filed in {doc['category']}" + (
            f"  ·  {similar_reason(why, doc['category'])}" if why else ""), "secondary")
        self.move = QPushButton("Move to…")
        self.move.setToolTip("Wrong category? Choose the right one. Your choice is what ClassiFile learns from.")
        self.move.clicked.connect(lambda: controller.move_docs([self.doc_id]))
        text = box(QVBoxLayout())
        text.addLayout(head)
        text.addWidget(self.reason)
        row = box(QHBoxLayout(self), (0, PANEL, 0, PANEL), GROUP)
        row.addLayout(text, 1)
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
        v = box(QVBoxLayout(self))
        v.addWidget(scroll, 1)
        v.addWidget(self.empty)

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
        self.empty.setVisible(not docs)
