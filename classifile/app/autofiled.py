"""The "Filed automatically" page: what the app filed by itself, as an aligned list of name, category and review
status. A click on a row inspects it (details open beside the list; that confirms nothing). "Looks right" records
the user's confirmation, for one document or for all the ticked ones; Move to… is the correction. A row the user
has just reviewed stays where it is, with its new status, until the page is left, so no row slides under the
mouse. Folders the app created and named by itself (decision record B2, 2.6) are listed above the documents, with
their key words and a one-click Rename, until the user renames them."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from classifile.app.decision import full_width
from classifile.app.reasons import new_folder_reason
from classifile.app.widgets import (
    BAR, COLUMNS_MIN, FILE_ICON, GROUP, RELATED, STATUS_COLUMN, TIGHT, ElidedLabel, ListRow, box, format_icon,
    status_icon,
)

REVIEW = {"machine-assigned": ("Not reviewed", "queued"), "user-confirmed": ("Confirmed", "filed"),
          "user-corrected": ("Moved by you", "filed")}
NAME_STRETCH, CATEGORY_STRETCH = 3, 2


def retained(widget):
    """Hidden, it keeps its room: the columns of every row stay lined up."""
    policy = widget.sizePolicy()
    policy.setRetainSizeWhenHidden(True)
    widget.setSizePolicy(policy)
    return widget


def action_buttons():
    right = QPushButton("Looks right")
    right.setObjectName("accent")
    move = QPushButton("Move to…")
    move.setObjectName("quiet")
    actions = QWidget()
    h = box(QHBoxLayout(actions))
    h.addWidget(retained(right))
    h.addWidget(retained(move))
    return actions, right, move


class AutoItem(ListRow):
    def __init__(self, doc, controller):
        super().__init__(controller)
        self.doc_id, self.ids, self.narrow, self.state = doc["id"], [doc["id"]], False, None
        self.tick = retained(QCheckBox())
        self.tick.setToolTip("Tick several documents to confirm them together")
        self.tick.setAccessibleName(f"Select {doc['file_name']}")
        icon = QLabel()
        icon.setPixmap(format_icon(doc["file_name"]).pixmap(FILE_ICON, FILE_ICON))
        self.title = ElidedLabel(doc["file_name"], "strong")
        self.filed_in = QLabel("Filed in")      # on the second line only: the column header says it otherwise
        self.filed_in.setObjectName("secondary")
        self.category = ElidedLabel()
        self.status_icon = QLabel()
        self.status_word = QLabel()
        self.status_word.setObjectName("secondary")
        self.status = QWidget()
        h = box(QHBoxLayout(self.status), spacing=TIGHT)
        h.addWidget(self.status_icon)
        h.addWidget(self.status_word, 1)
        self.status.setFixedWidth(STATUS_COLUMN)
        self.actions, self.right, self.move = action_buttons()
        self.right.setToolTip("Confirm this category. ClassiFile learns from documents you confirm.")
        self.move.setToolTip("Wrong category? Choose the right one. Your choice is what ClassiFile learns from.")
        self.right.clicked.connect(lambda: controller.auto_page.review([self.doc_id]))
        self.move.clicked.connect(lambda: controller.auto_page.correct([self.doc_id]))
        self.top = box(QHBoxLayout(), spacing=RELATED)
        for w, stretch in ((self.tick, 0), (icon, 0), (self.title, NAME_STRETCH), (self.category, CATEGORY_STRETCH),
                           (self.status, 0), (self.actions, 0)):
            self.top.addWidget(w, stretch)
        self.second = QWidget()                 # narrow: the category and status under the name
        self.sub = box(QHBoxLayout(self.second), (self.tick.sizeHint().width() + FILE_ICON + 2 * RELATED, 0, 0, 0),
                       TIGHT)
        self.sub.addWidget(self.filed_in)
        v = box(QVBoxLayout(self), (RELATED - BAR, RELATED, RELATED, RELATED), TIGHT)
        v.addLayout(self.top)
        v.addWidget(self.second)
        self.second.hide()
        self.fill(doc)

    def fill(self, doc):
        """Show the document as the catalog has it now; the row itself (tick, focus) stays."""
        state = (doc["category"], doc["provenance"], doc.get("app_named"))
        if state == self.state:
            return
        self.state = state
        self.category.setText(doc["category"] + (" · New" if doc.get("app_named") else ""))
        word, icon = REVIEW.get(doc["provenance"], ("Filed by you", "filed"))
        self.status_word.setText(word)
        self.status_icon.setPixmap(status_icon(icon).pixmap(16, 16))
        reviewed = doc["provenance"] != "machine-assigned"
        self.search_text = f"{doc['file_name']} {doc['category']}".casefold()
        if reviewed:
            self.tick.setChecked(False)
        for w in (self.tick, self.right, self.move):
            w.setVisible(not reviewed)

    @property
    def reviewed(self):
        return self.state[1] != "machine-assigned"

    def set_narrow(self, narrow):
        """Narrow: name and buttons on the first line; where it was filed, and its status, on the second."""
        if narrow == self.narrow:
            return
        self.narrow = narrow
        for w in (self.category, self.status):
            self.top.removeWidget(w)
            self.sub.removeWidget(w)
        if narrow:
            self.sub.addWidget(self.category, 1)
            self.sub.addWidget(self.status)
        else:
            self.top.insertWidget(3, self.category, CATEGORY_STRETCH)
            self.top.insertWidget(4, self.status)
        self.second.setVisible(narrow)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not self.reviewed:
            self.tick.toggle()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.c.show_details(self.doc_id)    # inspecting; confirming takes "Looks right"
        else:
            super().keyPressEvent(e)


class FolderItem(QFrame):
    """A folder the app created and named by itself: its name, marked as such, how many documents it holds, the
    words they share, and Rename… (one click; the folder keeps its documents)."""

    def __init__(self, cat_id, controller):
        super().__init__()
        self.cat_id, self.state = cat_id, None
        self.setObjectName("row")
        self.name = ElidedLabel(object_name="strong")
        tag = QLabel("New (named by ClassiFile)")
        tag.setObjectName("secondary")
        self.about = QLabel()
        self.about.setObjectName("secondary")
        self.about.setWordWrap(True)
        self.rename = QPushButton("Rename…")
        self.rename.setObjectName("accent")
        self.rename.setToolTip("Give this folder your own name. Its documents stay in it.")
        self.rename.clicked.connect(lambda: controller.rename_category(self.cat_id))
        top = box(QHBoxLayout(), spacing=RELATED)
        top.addWidget(self.name, 1)
        top.addWidget(tag)
        text = box(QVBoxLayout(), spacing=TIGHT)
        text.addLayout(top)
        text.addWidget(self.about)
        h = box(QHBoxLayout(self), (RELATED, RELATED, RELATED, RELATED), GROUP)
        h.addLayout(text, 1)
        h.addWidget(self.rename, 0, Qt.AlignVCenter)

    def fill(self, name, count, words):
        if (name, count, words) != self.state:
            self.state = (name, count, words)
            self.name.setText(name)
            self.rename.setAccessibleName(f"Rename {name}")
            self.about.setText(f"{count} document{'s' if count != 1 else ''} · {new_folder_reason(words)}.")


class AutoPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c, self.items, self.query, self.inspected, self.narrow = controller, [], "", None, False
        self.reviewed = set()                   # reviewed on this page since it was opened: they stay in view
        self.order = {}                         # doc_id -> when it was first listed: rows keep their places
        self.folders = []                       # FolderItems: the folders the app named, until renamed
        self.folder_box = QWidget()
        folder_caption = QLabel("NEW FOLDERS")
        folder_caption.setObjectName("section")
        self.folder_list = box(QVBoxLayout(self.folder_box), (0, 0, GROUP, GROUP), TIGHT)
        self.folder_list.addWidget(folder_caption)
        self.folder_box.hide()
        self.all = QCheckBox("Select all")
        self.all.clicked.connect(lambda on: [i.tick.setChecked(on) for i in self.items if not i.reviewed])
        self.count = QLabel()
        self.count.setObjectName("secondary")
        self.right = QPushButton()              # for the ticked documents, together; shown only when there are some
        self.right.setObjectName("primary")
        self.right.clicked.connect(lambda: self.review(self.ticked()))
        self.clear = QPushButton("Clear")
        self.clear.setObjectName("quiet")
        self.clear.clicked.connect(lambda: [i.tick.setChecked(False) for i in self.items])
        self.bar = QWidget()
        bar = box(QHBoxLayout(self.bar), (RELATED, 0, 0, 0), GROUP)
        for w in (self.all, self.count, self.right, self.clear):
            bar.addWidget(retained(w))          # the bar keeps its height: the list never jumps on the first tick
        bar.addStretch(1)
        self.header = QWidget()                 # the column names, lined up with the rows below
        h = box(QHBoxLayout(self.header), (RELATED, 0, RELATED, 0), RELATED)
        h.addWidget(retained(QCheckBox()))
        icon = QLabel()
        icon.setPixmap(format_icon(".pdf").pixmap(FILE_ICON, FILE_ICON))
        h.addWidget(retained(icon))
        for text, stretch in (("Name", NAME_STRETCH), ("Category", CATEGORY_STRETCH), ("Status", 0)):
            label = QLabel(text)
            label.setObjectName("column")           # like the column names of the document list
            h.addWidget(label, stretch)
            if not stretch:
                label.setFixedWidth(STATUS_COLUMN)
        caption = label.sizeHint().height()
        h.addWidget(retained(action_buttons()[0]))
        for i in range(h.count()):              # spacers only: never seen, never focused
            w = h.itemAt(i).widget()
            if w is not None and w.objectName() != "column":
                w.hide()
        self.header.setFixedHeight(caption)
        holder = QWidget()
        self.list = box(QVBoxLayout(holder), (0, 0, GROUP, 0), 0)   # room for the scroll bar
        self.list.addStretch(1)                                     # always last; the rows go before it
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(holder)
        self.empty = QLabel("Nothing was filed automatically.\nA document that clearly matches one of your "
                            "categories is filed without a question and listed here for you to review.")
        self.empty.setObjectName("secondary")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)            # a long line here would set the least width of every page
        for w in (self.bar, self.header):       # never what sets the least width of the page
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.top = box(QVBoxLayout(), (0, 0, GROUP, 0), RELATED)
        self.top.addWidget(self.bar)
        self.top.addWidget(self.header)
        v = box(QVBoxLayout(self), spacing=0)
        v.addWidget(self.folder_box)
        v.addLayout(self.top)
        v.addWidget(scroll, 1)
        v.addWidget(self.empty)

    # -- the user's actions ------------------------------------------------------------------------------------
    def review(self, ids):
        """Looks right: confirmed; the rows stay, marked Confirmed."""
        self.reviewed.update(ids)
        self.c.looks_right(ids)

    def correct(self, ids):
        self.reviewed.update(ids)
        self.c.move_docs(ids)

    def leave(self):
        """The page was left: what was reviewed on it goes from the list at the next visit."""
        self.reviewed.clear()

    # -- the rows ----------------------------------------------------------------------------------------------
    def ticked(self):
        return [i.doc_id for i in self.items if i.tick.isChecked()]

    def awaiting(self):
        return sum(1 for i in self.items if not i.reviewed)

    def _ticks_changed(self):
        n, open_ = len(self.ticked()), [i for i in self.items if not i.reviewed]
        self.count.setText(f"{n} selected")
        self.right.setText(f"Looks right ({n})")
        for w in (self.count, self.right, self.clear):
            w.setVisible(bool(n))
        self.all.setChecked(bool(n) and n == len(open_))
        self.all.setEnabled(bool(open_))

    def show_docs(self, docs):
        """docs: the catalog's rows for the documents the app filed by itself, and those reviewed on this page
        since it was opened. Rows are updated in place: ticks, focus and the scroll position stay."""
        for d in docs:
            self.order.setdefault(d["id"], d["filed_at"] or "")
        docs = sorted(sorted(docs, key=lambda d: (d["file_name"].casefold(), d["id"])),   # the latest first;
                      key=lambda d: self.order[d["id"]], reverse=True)     # the same second: by name
        old = {i.doc_id: i for i in self.items}
        items = []
        for d in docs:
            item = old.pop(d["id"], None)
            if item is None:
                item = AutoItem(d, self.c)
                item.set_narrow(self.narrow)
                item.set_inspected(self.inspected)
                item.tick.toggled.connect(self._ticks_changed)
            item.fill(d)
            items.append(item)
        for gone in old.values():
            self.list.removeWidget(gone)
            gone.hide()
            gone.deleteLater()
        for n, item in enumerate(items):
            if self.list.itemAt(n).widget() is not item:
                self.list.removeWidget(item)
                self.list.insertWidget(n, item)
                item.setVisible(self._matches(item))
        self.items = items
        self.empty.setVisible(not items and not self.folders)
        for w in (self.bar, self.header):
            w.setVisible(bool(items))
        self.header.setVisible(bool(items) and not self.narrow)
        self._ticks_changed()

    def show_folders(self, folders):
        """folders: [(category id, name, documents, key words)] of the folders the app named, newest first."""
        old = {f.cat_id: f for f in self.folders}
        self.folders = []
        for n, (cat_id, name, count, words) in enumerate(folders):
            item = old.pop(cat_id, None) or FolderItem(cat_id, self.c)
            item.fill(name, count, tuple(words))
            if self.folder_list.indexOf(item) != n + 1:
                self.folder_list.insertWidget(n + 1, item)
            self.folders.append(item)
        for gone in old.values():
            self.folder_list.removeWidget(gone)
            gone.hide()
            gone.deleteLater()
        self.folder_box.setVisible(bool(self.folders))
        self.empty.setVisible(not self.items and not self.folders)

    def set_inspected(self, doc_id):
        if doc_id != self.inspected:
            self.inspected = doc_id
            for item in self.items:
                item.set_inspected(doc_id)

    def row_of(self, doc_id):
        return next((i for i in self.items if i.doc_id == doc_id), None)

    def _matches(self, item):
        return not self.query or self.query in item.search_text

    def set_query(self, query):
        self.query = query.strip().casefold()
        for item in self.items:
            if item.isHidden() == self._matches(item):
                item.setVisible(self._matches(item))

    def shown_documents(self):
        return sum(1 for i in self.items if self._matches(i))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        full_width(self.list)
        full_width(self.top)
        narrow = self.width() - self.list.contentsMargins().right() < COLUMNS_MIN
        if narrow != self.narrow:
            self.narrow = narrow
            for item in self.items:
                item.set_narrow(narrow)
            self.header.setVisible(bool(self.items) and not narrow)
