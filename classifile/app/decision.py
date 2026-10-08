"""The "Needs your decision" page: one item per question, with one primary action each."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key, top_names
from classifile.app.reasons import reason_text
from classifile.app.widgets import (
    GROUP, PANEL, READING_MAX, RELATED, ElidedLabel, Preview, box, format_icon, restyle,
)

TOP = 3


def group_items(docs):
    """Waiting documents as decision items. Readable documents whose top suggestion is exactly the same (same
    name key) and whose originals are present form one group item; everything else is a single item."""
    items, groups = [], {}
    for d in docs:
        top = top_names(d["suggestions"], 1)
        if d["status"] == "needs_decision" and not d["missing"] and top:
            groups.setdefault(name_key(top[0]["name"]), []).append(d)
        else:
            items.append([d])
    items += groups.values()  # a group of one is a single item
    order = {d["id"]: i for i, d in enumerate(docs)}
    attention = lambda m: 0 if m[0]["status"] in ("failed", "pending") else 1 if m[0]["missing"] else 2
    return sorted(items, key=lambda m: (attention(m), min(order[d["id"]] for d in m)))  # problems first


class DecisionItem(QFrame):
    def __init__(self, docs, controller):
        super().__init__()
        self.setObjectName("decision")
        self.setFocusPolicy(Qt.StrongFocus)
        self.docs, self.c = docs, controller
        self.ids = [d["id"] for d in docs]
        first = docs[0]
        self.group = len(docs) > 1
        top = top_names(first["suggestions"], TOP) if first["status"] == "needs_decision" else []
        self.best = top[0]["name"] if top else ""

        icon = QLabel()
        icon.setPixmap(format_icon(first["file_name"]).pixmap(20, 20))
        self.title = ElidedLabel(f"{len(docs)} documents with the same suggestion" if self.group
                                 else first["file_name"])
        self.title.setStyleSheet("font-weight: 600;")
        head = box(QHBoxLayout())
        head.addWidget(icon)
        head.addWidget(self.title, 1)

        self.line = QLabel()
        self.line.setWordWrap(True)
        self.names = QLabel()
        self.names.setObjectName("secondary")
        self.names.setWordWrap(True)
        if self.group:
            shown = [d["file_name"] for d in docs[:6]]
            more = len(docs) - len(shown)
            self.names.setText(", ".join(shown) + (f" and {more} more" if more else ""))
        self.names.setVisible(self.group)

        self.primary = QPushButton()
        self.primary.setObjectName("primary")
        self.primary.clicked.connect(self.primary_action)
        self.choose = QPushButton("Choose another…")
        self.choose.setObjectName("link")
        self.choose.clicked.connect(self.toggle_expanded)
        self.pending = QPushButton("Leave pending")
        self.pending.setObjectName("link")
        self.pending.clicked.connect(lambda: self.c.leave_pending(self.ids))
        self.remove = QPushButton("Remove from ClassiFile")
        self.remove.setObjectName("link")
        self.remove.clicked.connect(lambda: self.c.remove_docs(self.ids))
        self.more_menu = QToolButton()
        self.more_menu.setObjectName("more")
        self.more_menu.setText("⋯")
        self.more_menu.setToolTip("More actions")
        self.more_menu.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        if not self.group:
            menu.addAction("Details", lambda: self.c.show_details(first["id"]))
        menu.addAction("Remove from ClassiFile", lambda: self.c.remove_docs(self.ids))
        self.more_menu.setMenu(menu)
        actions = box(QHBoxLayout())
        actions.addWidget(self.primary)
        actions.addSpacing(GROUP - RELATED)     # the primary action stands apart from the others
        for w in (self.choose, self.pending, self.remove):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(self.more_menu)

        self.expanded = self._expanded_area(top)
        v = box(QVBoxLayout(self), (0, PANEL, 0, PANEL))
        v.addLayout(head)
        v.addWidget(self.line)
        v.addWidget(self.names)
        v.addSpacing(RELATED)                   # description, then the controls
        v.addLayout(actions)
        v.addWidget(self.expanded)
        self._configure(first, top)

    # -- what the item asks ------------------------------------------------------------------------------------
    def _configure(self, first, top):
        problem = first["status"] in ("failed", "pending")
        if problem:
            self.line.setText(f"⚠ This document couldn't be read: {first['status_reason'] or 'unknown reason'}.")
            self.line.setObjectName("error")
            self._only(self.remove)
        elif first["missing"]:
            self.line.setText("⚠ The original file has moved. Locate it to file this document.")
            self.line.setObjectName("warning")
            self.primary.setText("Locate file…")
            self.primary.clicked.disconnect()
            self.primary.clicked.connect(lambda: self.c.locate_doc(first["id"]))
            self._only(self.primary, self.remove)
            self.line.setToolTip(f"It was at {first['source_path']}")
        else:
            if self.best:
                existing = self.c.existing_category(self.best)
                self.line.setText(f"Suggested category: {existing['name']}" if existing
                                  else f"Suggested new category: {self.best}")
                self.primary.setText("File" if existing else "Create && file")
                self.primary.setToolTip(f"File in '{existing['name']}'" if existing
                                        else f"Create category '{self.best}' and file")
            else:
                self.line.setText("No suggested name. Choose a category.")
                self.primary.setText("Choose…")
            if first["status_reason"]:
                self.line.setText(self.line.text() + f"\nLast attempt: {first['status_reason']}")
            self.remove.hide()
        restyle(self.line)

    def _only(self, *keep):
        for w in (self.primary, self.choose, self.pending, self.remove):
            w.setVisible(w in keep)

    # -- "Choose another…" -------------------------------------------------------------------------------------
    def _expanded_area(self, top):
        area = QWidget()
        self.sugg = QListWidget()
        self.sugg.setMaximumHeight(150)
        self.sugg.setWordWrap(True)
        self.sugg.itemClicked.connect(lambda item: self.field.setText(item.data(Qt.UserRole)))
        self.more_button = QPushButton()
        self.more_button.setObjectName("link")
        self.more_button.clicked.connect(self._toggle_more)
        self.all_suggestions = self.docs[0]["suggestions"] if not self.group else []
        self.show_all = False
        self.field = QLineEdit()
        self.field.setPlaceholderText("Category name")
        self.field.setCompleter(QCompleter(self.c.category_names(), self))
        self.field.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.field.completer().setFilterMode(Qt.MatchContains)
        self.field.textChanged.connect(self._update_confirm)
        self.field.returnPressed.connect(self.confirm_action)
        self.tag = QLabel()
        self.tag.setAlignment(Qt.AlignCenter)
        self.tag.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tag.setMinimumWidth(self.tag.fontMetrics().horizontalAdvance("Existing") + 28)
        self.tag.hide()
        self.confirm = QPushButton("File")
        self.confirm.setObjectName("primary")
        self.confirm.clicked.connect(self.confirm_action)
        row = box(QHBoxLayout())
        row.addWidget(QLabel("File in:"))
        row.addWidget(self.field, 1)
        row.addWidget(self.tag, 0, Qt.AlignVCenter)
        row.addWidget(self.confirm)
        self.preview = Preview(expandable=False)
        self.preview.setFixedHeight(220)
        left = box(QVBoxLayout())
        left.addWidget(self.sugg)
        left.addWidget(self.more_button, 0, Qt.AlignLeft)
        left.addSpacing(RELATED)
        left.addLayout(row)
        h = box(QHBoxLayout(area), (0, GROUP, 0, 0), GROUP)
        h.addLayout(left, 3)
        h.addWidget(self.preview, 2)
        self.sugg.setVisible(not self.group)
        self.more_button.setVisible(not self.group)
        self.preview.setVisible(not self.group)
        area.hide()
        return area

    def _fill_suggestions(self):
        self.sugg.clear()
        top = top_names(self.all_suggestions, TOP)
        rest = [s for s in self.all_suggestions if s not in top]
        for s in top + (rest if self.show_all else []):
            reason = reason_text(s["evidence"], self.docs[0]["unit"])
            item = QListWidgetItem(s["name"] + (f"\n    {reason}" if reason else ""))
            item.setData(Qt.UserRole, s["name"])
            self.sugg.addItem(item)
        self.more_button.setText("Fewer" if self.show_all else f"More ({len(rest)})")
        self.more_button.setVisible(bool(rest) and not self.group)

    def _toggle_more(self):
        self.show_all = not self.show_all
        self._fill_suggestions()

    def toggle_expanded(self):
        open_ = not self.expanded.isVisible()
        self.expanded.setVisible(open_)
        self.choose.setText("Hide choices" if open_ else "Choose another…")
        if open_:
            self._fill_suggestions()
            self.field.setText(self.c.display_name(self.best))
            if not self.group:
                d = self.docs[0]
                self.preview.show_document(self.c.preview_source(d["id"]), self.c.first_lines(d["id"]))
            self.field.setFocus()

    def _update_confirm(self):
        name = " ".join(self.field.text().split())
        self.field.setProperty("filled", bool(name))
        restyle(self.field)
        if not name:
            self.tag.hide()
            self.confirm.setText("File")
            self.confirm.setEnabled(False)
            return
        existing = self.c.existing_category(name)
        self.tag.setText("Existing" if existing else "New")
        self.tag.setObjectName("tagExisting" if existing else "tagNew")
        restyle(self.tag)
        self.tag.show()
        self.confirm.setText("File" if existing else "Create && file")
        self.confirm.setToolTip(f"File in '{existing['name']}'" if existing else f"Create category '{name}' and file")
        self.confirm.setEnabled(True)

    # -- actions -----------------------------------------------------------------------------------------------
    def primary_action(self):
        if self.best:
            self.c.file_docs(self.ids, self.best)
        else:
            self.toggle_expanded()

    def confirm_action(self):
        name = " ".join(self.field.text().split())
        if name and self.confirm.isEnabled():
            self.c.file_docs(self.ids, name)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # The small preview needs room; when the item is narrow the choices get the space (Details shows pages).
        self.preview.setVisible(not self.group and self.width() >= 760)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.primary.isVisible() and self.primary.isEnabled():
            self.primary.click()
        elif e.key() == Qt.Key_Delete:
            self.c.remove_docs(self.ids)
        else:
            super().keyPressEvent(e)


class DecisionPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.items = []
        self.holder = QWidget()
        self.holder.setMaximumWidth(READING_MAX)    # readable on large screens; the scroll area keeps it left
        self.list = box(QVBoxLayout(self.holder), (0, 0, GROUP, 0), 0)  # room for the scroll bar
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.holder)
        self.empty = QLabel("Nothing needs your decision right now.")
        self.empty.setObjectName("secondary")
        self.empty.setAlignment(Qt.AlignCenter)
        v = box(QVBoxLayout(self))
        v.addWidget(scroll, 1)
        v.addWidget(self.empty)

    def show_items(self, docs):
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        self.items = [DecisionItem(members, self.c) for members in group_items(docs)]
        for item in self.items:
            self.list.addWidget(item)
            item.show()  # now, not after the next layout pass
        self.list.addStretch(1)
        self.empty.setVisible(not self.items)
        if self.items:
            self.items[0].setFocus()
