"""Main window: a quiet sidebar, a document list, the "Needs your decision" page, and details on request.

Run: .venv\\Scripts\\python -m classifile.app
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication, QEasingCurve, QEvent, QItemSelectionModel, QObject, QPoint, QPropertyAnimation, QSize, Qt,
    QUrl, Signal,
)
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter,
    QListView, QStackedWidget, QStyleFactory, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key
from classifile.app import app_icon, make_app
from classifile.app.decision import DecisionPage
from classifile.app.details import DetailsPanel
from classifile.app.widgets import (
    DETAILS_MAX, DETAILS_MIN, DETAILS_WIDTH, GROUP, READING_MAX, PAD, RELATED, ROW, SECTION, STYLE, SUPPORTED, box, DropOverlay, ElidedLabel, Notices, PreviewOverlay, Toast, format_icon, restyle, status_icon,
    status_word, wrappable,
)
from classifile.catalog.db import Catalog
from classifile.organizer import Organizer, is_cloud_synced, read_and_analyze
from classifile.worker import WorkerPool

ALL, DECIDE, RECENT, SETTINGS = "all", "decide", "recent", "settings"
VIEW_TITLES = {ALL: "All documents", DECIDE: "Needs your decision", RECENT: "Recently added", SETTINGS: "Settings"}
RECENT_DAYS = 7
READ_WORKERS = min(4, os.cpu_count() or 2)  # documents read (and OCR'd) at once, each in its own process
WAITING = ("needs_decision", "pending", "failed")
DOC = Qt.UserRole
SIDEBAR_WIDTH = 240
WIDE = 1280          # from here the details panel sits beside the list; narrower, it opens over the list
NARROW = 1024        # below this the sidebar collapses to a menu button
DATE_COLUMN_MIN = 1100
MIN_WINDOW = (900, 560)
SORTS = ("Newest first", "Oldest first", "Name A–Z")


def short_date(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d") if iso else ""


class Bridge(QObject):
    read_done = Signal(str, object)       # path, (result, analysis, summary) | "reading"
    file_done = Signal(str, object)       # doc_id, (outcome, path) or Exception


class MainWindow(QWidget):
    def __init__(self, organizer, ask_output_root=True, workers=None):
        super().__init__()
        self.org = organizer
        self.inflight = {}          # path -> "queued" | "reading"
        self.read_total = 0         # documents in the current reading run, for "Reading 3 of 12…"
        self.filing = {}            # doc_id -> category id, while its copy is being made
        self.batch, self.batch_name, self.new_category = [], "", None
        self.failure = None         # (doc ids, sentence): stays as a notice until those documents are resolved
        self.deferred = []          # "Leave pending": moved to the end of the decision page for this session
        self.view = (ALL, None)     # ("all" | "decide" | "recent" | "settings" | "category", category id)
        self.details_open = False
        self.decide_doc = None      # the waiting document whose details are open beside the decision page
        self.pool = ThreadPoolExecutor(max_workers=READ_WORKERS)
        self.workers = workers or WorkerPool(read_and_analyze, size=READ_WORKERS)
        self.bridge = Bridge()
        self.bridge.read_done.connect(self._read_done)
        self.bridge.file_done.connect(self._file_done)
        self.list_style = QStyleFactory.create("Fusion")  # one selection bar (Windows 11 adds a second)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        self.setMinimumSize(*MIN_WINDOW)
        self.resize(1280, 760)
        self._build()
        self.org.startup()
        expanded = self._setting("ui_expanded", [])
        self.expanded = set(expanded)
        self.refresh()
        if ask_output_root and self.org.output_root is None:
            self.choose_output_root()

    # -- settings stored in the catalog -----------------------------------------------------------------------
    def _setting(self, key, default):
        value = self.org.catalog.get_setting(key)
        return json.loads(value) if value else default

    def _save(self, key, value):
        self.org.catalog.set_setting(key, json.dumps(value))

    # -- dialogs and outside actions (replaced in tests; nothing opens unless the user asks) ------------------
    def pick_folder(self, title):
        return QFileDialog.getExistingDirectory(self, title)

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add documents", filter="Documents (*.pdf *.pptx *.docx *.odt)")
        return paths

    def pick_file(self, file_name, start):
        path, _ = QFileDialog.getOpenFileName(self, f"Locate {file_name}", str(start),
                                              "Documents (*.pdf *.pptx *.docx *.odt)")
        return path

    def ask_category_name(self):
        text, ok = QInputDialog.getText(self, "New category", "Category name:")
        return text if ok else ""

    def confirm_remove(self, n):
        box = QMessageBox(self)
        box.setWindowTitle("Remove from ClassiFile")
        box.setText(f"Remove {n} document{'s' if n > 1 else ''} from ClassiFile?")
        box.setInformativeText("The original file isn't touched. ClassiFile deletes the text and analysis it stored "
                               "for it; adding the file again brings it back.")
        remove = box.addButton("Remove", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is remove

    def ask_close(self, n):
        box = QMessageBox(self)
        box.setWindowTitle("ClassiFile")
        box.setText(f"{n} document{'s' if n > 1 else ''} still need{'' if n > 1 else 's'} a decision. "
                    "They'll stay in the list until you decide.")
        close = box.addButton("Close", QMessageBox.AcceptRole)
        box.addButton("Back to decisions", QMessageBox.RejectRole)
        dont = QCheckBox("Don't show this again")
        box.setCheckBox(dont)
        box.exec()
        return ("close" if box.clickedButton() is close else "back"), dont.isChecked()

    def ask_move(self, n):
        box = QMessageBox(self)
        box.setWindowTitle("Change output folder")
        box.setText(f"Move ClassiFile's {n} cop{'ies' if n > 1 else 'y'} to the new folder?")
        box.setInformativeText("Each copy is copied and verified first; the old one is removed only if it is "
                               "unchanged. Edited copies stay where they are and are flagged. Nothing is overwritten.")
        move = box.addButton("Move copies", QMessageBox.AcceptRole)
        leave = box.addButton("Leave them", QMessageBox.NoRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return "move" if box.clickedButton() is move else "leave" if box.clickedButton() is leave else "cancel"

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_in_folder(self, path):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(Path(path))])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    # -- layout -----------------------------------------------------------------------------------------------
    def _build(self):
        self.sidebar = self._sidebar()
        workspace = QWidget()
        self.workspace = workspace
        self.menu_button = QPushButton("☰")
        self.menu_button.setObjectName("icon")
        self.menu_button.setToolTip("Show the sidebar")
        self.menu_button.clicked.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        self.page_title = ElidedLabel(object_name="pageTitle")
        self.processing = QLabel()
        self.processing.setObjectName("processing")
        self.add_button = QPushButton("Add documents")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self.add_documents)
        head = box(QHBoxLayout(), spacing=GROUP)
        head.addWidget(self.menu_button)
        head.addWidget(self.page_title, 1)
        head.addWidget(self.processing)
        head.addWidget(self.add_button)

        self.notices = Notices()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search documents…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self._fill_list())
        self.sort = QComboBox()
        self.sort.setView(QListView())           # the opened list takes the shared style
        self.sort.addItems(SORTS)
        self.sort.currentIndexChanged.connect(lambda *_: self._fill_list())
        self.details_toggle = QPushButton("Details")
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self.set_details_open)
        self.toolbar = QWidget()
        tools = box(QHBoxLayout(self.toolbar))
        self.search.setMaximumWidth(480)
        tools.addWidget(self.search, 1)
        tools.addStretch(0)
        tools.addWidget(self.sort)
        tools.addSpacing(GROUP - RELATED)       # finding documents | showing details
        tools.addWidget(self.details_toggle)

        self.bulk = self._bulk_bar()
        self.stack = QStackedWidget()
        self.table = self._table()
        self.empty_state = self._empty_state()
        self.decision = DecisionPage(self)
        self.settings_page = self._settings_page()
        for page in (self.table, self.empty_state, self.decision, self.settings_page):
            self.stack.addWidget(page)
        self.details = DetailsPanel(self)
        self.details.setMinimumWidth(DETAILS_MIN)
        self.details.hide()
        self.slide = QPropertyAnimation(self.details, b"pos", self)   # the panel enters from the right edge
        self.slide.setDuration(180)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.finished.connect(self._settle_details)
        self.content = QSplitter(Qt.Horizontal)
        self.content.setChildrenCollapsible(False)
        self.content.addWidget(self.stack)
        self.content.splitterMoved.connect(lambda *_: self._save("ui_details_width", self.details.width()))
        self.content.installEventFilter(self)   # moves and resizes: the details overlay follows

        v = box(QVBoxLayout(workspace), PAD, GROUP)
        v.addLayout(head)
        v.addSpacing(SECTION - GROUP)           # the heading, then the page
        v.addWidget(self.notices)
        v.addWidget(self.toolbar)
        v.addWidget(self.bulk)
        v.addWidget(self.content, 1)

        layout = box(QHBoxLayout(self), spacing=0)
        layout.addWidget(self.sidebar)
        layout.addWidget(workspace, 1)
        self.overlay = DropOverlay(self)
        self.preview_overlay = PreviewOverlay(self)
        self.toast = Toast(self)

    def _sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(SIDEBAR_WIDTH)
        brand_icon = QLabel()
        brand_icon.setPixmap(app_icon().pixmap(20, 20))
        brand = QLabel("ClassiFile")
        brand.setObjectName("brand")
        top = box(QHBoxLayout(), (GROUP, PAD, GROUP, GROUP))
        top.addWidget(brand_icon)
        top.addWidget(brand, 1)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav = {}
        for key in (ALL, DECIDE, RECENT):
            b = QPushButton(VIEW_TITLES[key])
            b.setObjectName("nav")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.show_view(k))
            self.nav_group.addButton(b)
            self.nav[key] = b
        self.decide_count = QLabel()              # right-aligned like the category counts
        self.decide_count.setObjectName("count")
        self.decide_count.setAttribute(Qt.WA_TransparentForMouseEvents)
        count_row = box(QHBoxLayout(self.nav[DECIDE]), (0, 0, GROUP, 0))
        count_row.addStretch(1)
        count_row.addWidget(self.decide_count)
        header = QLabel("CATEGORIES")
        header.setObjectName("section")
        self.add_category = QPushButton("+")
        self.add_category.setObjectName("icon")
        self.add_category.setToolTip("Create a category")
        self.add_category.clicked.connect(self.new_category_clicked)
        cat_head = box(QHBoxLayout(), (GROUP, SECTION, RELATED, RELATED))
        cat_head.addWidget(header, 1)
        cat_head.addWidget(self.add_category)
        self.cats = QTreeWidget()
        self.cats.setObjectName("categories")
        self.cats.setHeaderHidden(True)
        self.cats.setColumnCount(2)
        self.cats.header().setStretchLastSection(False)
        self.cats.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cats.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.cats.setIndentation(14)
        self.cats.setStyle(self.list_style)
        self.cats.setTextElideMode(Qt.ElideRight)
        self.cats.itemClicked.connect(self._category_clicked)
        self.cats.itemExpanded.connect(lambda item: self._remember_expand(item, True))
        self.cats.itemCollapsed.connect(lambda item: self._remember_expand(item, False))
        self.cats_empty = QLabel("No categories yet. Press + to create one, or file a document.")
        self.cats_empty.setObjectName("secondary")
        self.cats_empty.setWordWrap(True)
        self.cats_empty.setContentsMargins(GROUP, 0, GROUP, 0)
        settings = QPushButton("⚙  Settings")
        settings.setObjectName("nav")
        settings.setCheckable(True)
        settings.clicked.connect(lambda: self.show_view(SETTINGS))
        self.nav_group.addButton(settings)
        self.nav[SETTINGS] = settings
        v = box(QVBoxLayout(side), (0, 0, 0, RELATED), 0)
        v.addLayout(top)
        for key in (ALL, DECIDE, RECENT):
            v.addWidget(self.nav[key])
        v.addLayout(cat_head)
        v.addWidget(self.cats_empty)
        v.addWidget(self.cats, 1)
        v.addWidget(settings)
        return side

    def _table(self):
        table = QTreeWidget()
        table.setColumnCount(4)
        table.setHeaderLabels(["Name", "Category", "Status", "Date added"])
        table.setRootIsDecorated(False)
        table.setUniformRowHeights(True)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setIconSize(QSize(16, 16))
        table.setTextElideMode(Qt.ElideRight)
        table.setStyle(self.list_style)
        header = table.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in ((1, 200), (2, 110), (3, 110)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            table.setColumnWidth(col, width)
        header.setStretchLastSection(False)
        table.itemSelectionChanged.connect(self._selection_changed)
        table.itemDoubleClicked.connect(lambda *_: self.activate_selected())
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._context_menu)
        table.installEventFilter(self)
        return table

    def _bulk_bar(self):
        bar = QFrame()
        bar.setObjectName("bulk")
        self.bulk_count = QLabel()
        self.bulk_file = QPushButton("File in…")
        self.bulk_file.clicked.connect(self._bulk_file_clicked)
        self.bulk_remove = QPushButton("Remove")
        self.bulk_remove.clicked.connect(lambda: self.remove_docs(self.selected_ids()))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.table.clearSelection())  # the list is built after this bar
        self.bulk_clear = clear
        self.bulk_field = QLineEdit()
        self.bulk_field.setPlaceholderText("Category name")
        self.bulk_field.setCompleter(QCompleter([], self))
        self.bulk_field.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.bulk_field.completer().setFilterMode(Qt.MatchContains)
        self.bulk_field.textChanged.connect(self._update_bulk_confirm)
        self.bulk_field.returnPressed.connect(self._bulk_confirm)
        self.bulk_tag = QLabel()
        self.bulk_tag.setMinimumWidth(self.bulk_tag.fontMetrics().horizontalAdvance("Existing") + 28)
        self.bulk_tag.setAlignment(Qt.AlignCenter)
        self.bulk_go = QPushButton("File")
        self.bulk_go.setObjectName("primary")
        self.bulk_go.clicked.connect(self._bulk_confirm)
        self.bulk_form = QWidget()               # its own row, so the bar never squeezes the field
        form = box(QHBoxLayout(self.bulk_form))
        form.addWidget(QLabel("File in:"))
        form.addWidget(self.bulk_field, 1)
        form.addWidget(self.bulk_tag, 0, Qt.AlignVCenter)
        form.addWidget(self.bulk_go)
        self.bulk_form.hide()
        self.bulk_tag.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        h = box(QHBoxLayout())
        h.addWidget(self.bulk_count)
        h.addSpacing(GROUP - RELATED)
        h.addWidget(self.bulk_file)
        h.addWidget(self.bulk_remove)
        h.addStretch(1)
        h.addWidget(clear)
        rows = box(QVBoxLayout(bar), (GROUP, RELATED, RELATED, RELATED))
        rows.addLayout(h)
        rows.addWidget(self.bulk_form)
        bar.hide()
        return bar

    def _empty_state(self):
        page = QWidget()
        title = QLabel("Bring some order to your documents.")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        lines = [QLabel("Drop files here or choose documents to get started."), QLabel(f"{SUPPORTED}."),
                 QLabel("Original files stay unchanged. ClassiFile organizes copies.")]
        self.empty_add = QPushButton("Add documents")
        self.empty_add.setObjectName("primary")
        self.empty_add.clicked.connect(self.add_documents)
        v = box(QVBoxLayout(page))
        v.addStretch(1)
        v.addWidget(title, 0, Qt.AlignCenter)
        v.addWidget(lines[0], 0, Qt.AlignCenter)
        v.addSpacing(SECTION - RELATED)
        v.addWidget(self.empty_add, 0, Qt.AlignCenter)
        v.addSpacing(SECTION - RELATED)
        for label in lines[1:]:
            label.setObjectName("secondary")
            v.addWidget(label, 0, Qt.AlignCenter)
        v.addStretch(2)
        self.empty_texts = [title.text()] + [l.text() for l in lines]
        return page

    def _settings_page(self):
        outer = QWidget()
        page = QWidget()
        page.setMaximumWidth(READING_MAX * 2 // 3)
        box(QHBoxLayout(outer)).addWidget(page, 1, Qt.AlignLeft | Qt.AlignTop)
        out = QLabel("OUTPUT FOLDER")
        out.setObjectName("section")
        self.root_label = QLabel()
        self.root_label.setWordWrap(True)
        self.root_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.change_root = QPushButton("Change…")
        self.change_root.clicked.connect(self.change_output_root)
        row = box(QHBoxLayout(), spacing=GROUP)
        row.addWidget(self.root_label, 1)
        row.addWidget(self.change_root)
        behaviour = QLabel("WHEN CLOSING")
        behaviour.setObjectName("section")
        self.close_toggle = QCheckBox("Ask before closing when documents are waiting")
        self.close_toggle.toggled.connect(
            lambda on: self.org.catalog.set_setting("close_notice", "on" if on else "off"))
        about = QLabel("ABOUT")
        about.setObjectName("section")
        about_text = QLabel("ClassiFile organizes copies of your documents into categories; original files stay "
                            "unchanged. Part of ClariFile.")
        about_text.setWordWrap(True)
        v = box(QVBoxLayout(page))
        v.addWidget(out)
        v.addLayout(row)
        v.addSpacing(SECTION)
        v.addWidget(behaviour)
        v.addWidget(self.close_toggle)
        v.addSpacing(SECTION)
        v.addWidget(about)
        v.addWidget(about_text)
        v.addStretch(1)
        return outer

    # -- views ------------------------------------------------------------------------------------------------
    def show_view(self, key, category=None):
        self.view = (key, category)
        if key in self.nav:
            self.nav[key].setChecked(True)
        else:
            checked = self.nav_group.checkedButton()
            if checked:
                self.nav_group.setExclusive(False)
                checked.setChecked(False)
                self.nav_group.setExclusive(True)
        if key != "category":
            self.cats.clearSelection()
        self.refresh()

    def _category_clicked(self, item, column):
        doc_id = item.data(0, DOC)
        cat = item.data(0, Qt.UserRole + 1)
        if doc_id:  # a document under its category: show the category with that document selected
            self.show_view("category", item.parent().data(0, Qt.UserRole + 1))
            self.select_docs([doc_id])
            return
        if cat:
            self.show_view("category", cat)

    def _remember_expand(self, item, expanded):
        cat = item.data(0, Qt.UserRole + 1)
        if cat:
            (self.expanded.add if expanded else self.expanded.discard)(cat)
            self._save("ui_expanded", sorted(self.expanded))

    def review(self):
        self.show_view(DECIDE)

    # -- data for the views -----------------------------------------------------------------------------------
    def waiting(self):
        return [d for d in self.org.catalog.documents(None) if d["status"] in WAITING]

    def decision_docs(self):
        docs = []
        for d in self.waiting():
            analysis = self.org.catalog.analysis(d["id"]) or {}
            docs.append(dict(d) | {"missing": d["status"] == "needs_decision" and self.org.original_missing(d["id"]),
                                   "suggestions": analysis.get("suggestions", []),
                                   "unit": analysis.get("unit", "page")})
        return sorted(docs, key=lambda d: d["id"] in self.deferred)

    def _rows(self):
        key, cat = self.view
        if key == "category":
            docs = [dict(d) for d in self.org.catalog.documents(cat)]
        elif key == RECENT:
            since = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).isoformat(timespec="seconds")
            ids = {d["id"] for d in self.org.catalog.recent_documents(since)}
            docs = [d for d in self.org.catalog.all_documents() if d["id"] in ids]
        else:
            docs = self.org.catalog.all_documents()
        inflight = [{"id": None, "file_name": Path(p).name, "status": st, "category": None, "imported_at": None,
                     "status_reason": None} for p, st in self.inflight.items()] if key in (ALL, RECENT) else []
        q = self.search.text().strip().casefold()
        rows = [r for r in inflight + docs if not q or q in r["file_name"].casefold()]
        order = self.sort.currentText()
        if order == "Name A–Z":
            rows.sort(key=lambda r: r["file_name"].casefold())
        else:
            rows.sort(key=lambda r: (r["imported_at"] is not None, r["imported_at"] or ""),
                      reverse=order == "Newest first")
            if order == "Newest first":
                rows.sort(key=lambda r: r["id"] is not None)  # documents still being read first
        return rows

    def document_row(self, doc_id):
        return next((d for d in self.org.catalog.all_documents() if d["id"] == doc_id), None)

    def existing_category(self, name):
        return self.org.catalog.category_by_key(name_key(name)) if name else None

    def display_name(self, name):
        existing = self.existing_category(name)
        return existing["name"] if existing else name

    def category_names(self):
        return [c["name"] for c in self.org.catalog.categories()]

    def first_lines(self, doc_id):
        return self.org.catalog.first_page_lines(doc_id)

    def short_date(self, iso):
        return short_date(iso)

    def filed_copy(self, doc_id):
        row = self.document_row(doc_id)
        if row and row["status"] == "filed" and row["copy_path"] and Path(row["copy_path"]).exists():
            return Path(row["copy_path"])
        return None

    def preview_source(self, doc_id):
        """The filed copy when there is one (the original may have moved since), else the original."""
        return self.filed_copy(doc_id) or Path(self.org.catalog.document(doc_id)["source_path"])

    # -- refresh ----------------------------------------------------------------------------------------------
    def refresh(self, select_docs=None):
        waiting = self.waiting()
        n = len(waiting)
        if self.decide_doc not in [d["id"] for d in waiting]:
            self.decide_doc = None  # filed or removed: its details close
        self.setWindowTitle(f"ClassiFile — {n} waiting" if n else "ClassiFile")
        self.decide_count.setText(str(n) if n else "")
        self._fill_categories()
        self._show_root()
        key, cat = self.view
        if key == "category" and not self.org.catalog.category(cat):
            self.view = key, cat = (ALL, None)
        if key in self.nav:
            self.nav[key].setChecked(True)
        empty = not self.org.catalog.all_documents() and not self.inflight
        count = len(waiting) if key == DECIDE else None
        if key == "category":
            title = self.org.catalog.category(cat)["name"]
            count = len(self.org.catalog.documents(cat))
        else:
            title = VIEW_TITLES[key]
        if key in (ALL, RECENT):
            count = len(self._rows()) if not self.search.text().strip() else None
        self.page_title.setText(title + (f" · {count}" if count and key != SETTINGS else ""))
        self.toolbar.setVisible(key not in (DECIDE, SETTINGS) and not empty)
        if key == SETTINGS:
            self.stack.setCurrentWidget(self.settings_page)
            self.close_toggle.blockSignals(True)
            self.close_toggle.setChecked(self.org.catalog.get_setting("close_notice") != "off")
            self.close_toggle.blockSignals(False)
        elif key == DECIDE:
            self.stack.setCurrentWidget(self.decision)
            self.decision.show_items(self.decision_docs())
        elif empty:
            self.stack.setCurrentWidget(self.empty_state)
        else:
            self.stack.setCurrentWidget(self.table)
            self._fill_list(select_docs)
        self._show_processing()
        self._show_notices(waiting)
        self._selection_changed()

    def _fill_categories(self):
        cats = self.org.catalog.categories()
        current = self.view[1] if self.view[0] == "category" else None
        self.cats.blockSignals(True)
        self.cats.clear()
        for c in cats:
            docs = self.org.catalog.documents(c["id"])
            node = QTreeWidgetItem([c["name"], str(len(docs))])
            node.setData(0, Qt.UserRole + 1, c["id"])
            node.setToolTip(0, c["name"])
            node.setForeground(1, self.palette().placeholderText())
            node.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.cats.addTopLevelItem(node)
            for d in docs:
                child = QTreeWidgetItem([d["file_name"]])
                child.setIcon(0, format_icon(d["file_name"]))
                child.setData(0, DOC, d["id"])
                child.setToolTip(0, d["file_name"])
                node.addChild(child)
            node.setExpanded(c["id"] in self.expanded)
            if c["id"] == current:
                node.setSelected(True)
        self.cats.blockSignals(False)
        self.cats_empty.setVisible(not cats)
        names = [c["name"] for c in cats]
        self.bulk_field.completer().model().setStringList(names)

    def _fill_list(self, select_docs=None):
        keep = set(select_docs if select_docs is not None else self.selected_ids())
        self.table.blockSignals(True)
        self.table.clear()
        for r in self._rows():
            status = "filing" if r["id"] in self.filing else r["status"]
            filed = status == "filed"
            item = QTreeWidgetItem([r["file_name"], r["category"] or "—", "" if filed else status_word(status),
                                    short_date(r["imported_at"])])
            item.setIcon(0, format_icon(r["file_name"]))
            if not filed:
                item.setIcon(2, status_icon(status))
            item.setToolTip(0, r["file_name"])
            if r.get("status_reason"):
                item.setToolTip(2, r["status_reason"])
            item.setData(0, DOC, r["id"])
            item.setSizeHint(0, QSize(0, ROW))
            if r["id"] is None:
                item.setFlags(Qt.ItemIsEnabled)
            self.table.addTopLevelItem(item)
            if r["id"] in keep:
                item.setSelected(True)
        self.table.blockSignals(False)
        self._apply_breakpoints()

    def _show_processing(self):
        if self.inflight:
            done = max(0, self.read_total - len(self.inflight))
            self.processing.setText(f"Reading {min(done + 1, self.read_total)} of {self.read_total} documents…")
        else:
            self.processing.setText("")
            self.read_total = 0
        self.processing.setVisible(bool(self.inflight))

    def _show_notices(self, waiting):
        notices = []
        unreadable = [d for d in waiting if d["status"] in ("failed", "pending")]
        if self.failure:
            ids, text = self.failure
            if any(d["id"] in ids for d in waiting):
                notices.append(("error", text, "Review", self.review))
            else:
                self.failure = None  # resolved: filed or removed (locating or retrying clears it too)
        if unreadable:
            n = len(unreadable)
            notices.append(("error", f"{n} document{'s' if n > 1 else ''} couldn't be read.", "Review", self.review))
        missing = [d for d in waiting if d["status"] == "needs_decision" and self.org.original_missing(d["id"])]
        if missing and not self.failure:
            n = len(missing)
            notices.append(("warning", f"{n} document{'s have' if n > 1 else ' has'} moved since it was added. "
                            "Locate the original to file it.", "Review", self.review))
        ready = len(waiting) - len(unreadable)
        if ready and self.view[0] != DECIDE:
            notices.append(("info", f"{ready} document{'s need' if ready > 1 else ' needs'} your decision.",
                            "Review", self.review))
        self.notices.show_notices(notices[:3])

    # -- selection and the details panel ----------------------------------------------------------------------
    def selected_ids(self):
        return [i.data(0, DOC) for i in self.table.selectedItems() if i.data(0, DOC)]

    def select_docs(self, ids):
        self.table.blockSignals(True)
        self.table.clearSelection()
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            if item.data(0, DOC) in ids:
                item.setSelected(True)
                self.table.setCurrentItem(item, 0, QItemSelectionModel.NoUpdate)
        self.table.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self):
        ids = self.selected_ids() if self.stack.currentWidget() is self.table else []
        self.bulk.setVisible(len(ids) > 1)
        if len(ids) > 1:
            docs = [self.org.catalog.document(i) for i in ids]
            ready = [d for d in docs if d["status"] == "needs_decision"]
            self.bulk_count.setText(f"{len(ids)} selected")
            self.bulk_file.setEnabled(bool(ready))
            self.bulk_file.setToolTip("" if ready else "Only documents waiting for a decision can be filed.")
            self.bulk_remove.setEnabled(any(d["status"] in WAITING for d in docs))
        else:
            self.bulk_form.hide()
        if self.details_open and len(ids) == 1:
            self.details.show_doc(ids[0])
        self._place_details()

    def set_details_open(self, open_):
        ids = self.selected_ids()
        self.details_open = bool(open_ and ids)
        self.details_toggle.blockSignals(True)
        self.details_toggle.setChecked(self.details_open)
        self.details_toggle.blockSignals(False)
        if self.details_open:
            self.details.show_doc(ids[0])
        self._place_details()

    def show_details(self, doc_id):
        if self.view[0] == DECIDE:  # stays on the page: the pages open beside the item and its buttons
            self.decide_doc = doc_id
            self.details.show_doc(doc_id)
            return self._place_details()
        if self.view[0] == SETTINGS:
            self.show_view(ALL)
        self.select_docs([doc_id])
        self.set_details_open(True)

    def close_details(self):
        self.decide_doc = None
        self.set_details_open(False)

    def _place_details(self):
        """Wide windows: the panel sits beside the list. Narrower: it opens over the list. On the decision page it
        is always beside the items, so their buttons and the category field stay in reach."""
        page = self.stack.currentWidget()
        show = (self.details_open and page is self.table) or (self.decide_doc is not None and page is self.decision)
        wide = self.width() >= WIDE or page is self.decision
        was_hidden = self.details.isHidden()
        if not show:
            self.details.hide()
            return
        if wide and self.details.parent() is not self.content:
            self.content.addWidget(self.details)
            default = max(DETAILS_WIDTH, min(DETAILS_MAX, self.content.width() * 3 // 10))
            width = max(DETAILS_MIN, self._setting("ui_details_width", default))
            self.content.setSizes([max(300, self.content.width() - width), width])
        elif not wide and self.details.parent() is not self.workspace:
            self.details.setParent(self.workspace)
        self.details.show()
        if not wide:
            g = self.content.geometry()
            width = max(DETAILS_MIN, min(DETAILS_WIDTH, g.width() - PAD))
            self.details.setGeometry(g.right() + 1 - width, g.top(), width, g.height())
            self.details.raise_()
        if was_hidden:  # slides in at its final size, so the page picture is drawn once
            QCoreApplication.sendPostedEvents(self.content, QEvent.LayoutRequest)  # the splitter places it now
            self.slide.stop()
            self.slide.setStartValue(QPoint(self.details.parentWidget().width(), self.details.y()))
            self.slide.setEndValue(self.details.pos())
            self.slide.start()

    def _settle_details(self):
        """After a slide: back where the layout wants it, in case the window changed on the way."""
        if self.details.parent() is self.content:
            self.content.refresh()
        elif self.details.isVisible():
            self._place_details()

    def expand_preview(self, doc_id, page=0):
        d = self.org.catalog.document(doc_id)
        self.preview_overlay.open(d["file_name"], self.preview_source(doc_id), self.first_lines(doc_id), page)

    # -- responsive breakpoints -------------------------------------------------------------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_breakpoints()
        for overlay in (self.overlay, self.preview_overlay):
            if overlay.isVisible():
                overlay.setGeometry(self.rect().adjusted(16, 16, -16, -16) if overlay is self.overlay else self.rect())
        if self.toast.isVisible():
            self.toast.place()

    def _apply_breakpoints(self):
        narrow = self.width() < NARROW
        if narrow != getattr(self, "_was_narrow", None):
            self.sidebar.setVisible(not narrow)
            self._was_narrow = narrow
        self.menu_button.setVisible(narrow)
        self.table.setColumnHidden(3, self.width() < DATE_COLUMN_MIN)
        # Category grows with the window so wide screens don't leave a long empty gap after short names.
        self.table.setColumnWidth(1, max(200, min(380, self.table.viewport().width() // 4)))
        self._place_details()

    # -- output folder ----------------------------------------------------------------------------------------
    def choose_output_root(self):
        path = self.pick_folder("Choose the output folder for organized copies")
        if path:
            self.org.set_output_root(path)
        self._show_root()

    def change_output_root(self):
        path = self.pick_folder("Choose a new output folder")
        if not path or (self.org.output_root and Path(path).resolve() == self.org.output_root):
            return
        to_move = self.org.copies_to_move(path) if self.org.output_root else []
        answer = self.ask_move(len(to_move)) if to_move else "leave"
        if answer == "cancel":
            return
        # ponytail: the move runs on the UI thread; a background job when large folders make the window wait.
        report = self.org.set_output_root(path, move=answer == "move")
        counts = {k: sum(1 for _, o in report if o == k) for k in ("moved", "edited", "missing", "failed")}
        msg = "Output folder changed."
        if answer == "move":
            msg += f" Moved {counts['moved']} cop{'y' if counts['moved'] == 1 else 'ies'}."
            if counts["edited"]:
                msg += f" {counts['edited']} edited cop{'y' if counts['edited'] == 1 else 'ies'} stayed where" \
                       " they were and are flagged."
            if counts["missing"] or counts["failed"]:
                msg += f" {counts['missing'] + counts['failed']} could not be moved and stayed where they were."
        self.toast.show_message(msg)
        self.refresh()

    def _show_root(self):
        root = self.org.output_root
        note = "  (inside a cloud-synced folder)" if root and is_cloud_synced(root) else ""
        self.root_label.setText(f"{wrappable(root)}{note}" if root else "Not chosen yet")
        self.change_root.setText("Change…" if root else "Choose…")

    # -- adding documents and drag-and-drop -------------------------------------------------------------------
    def add_documents(self):
        self.import_paths(self.pick_files())

    @staticmethod
    def _drag_paths(e):
        return [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.overlay.show_for(self._drag_paths(e))

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.overlay.hide()

    def dropEvent(self, e):
        self.overlay.hide()
        self.import_paths(self._drag_paths(e))

    def import_paths(self, paths):
        refused = []
        for p in paths:
            p = str(Path(p).resolve())
            reason = self.org.check_import(p)
            if reason:
                refused.append(f"{Path(p).name} ({reason})")
            elif p not in self.inflight:
                self.inflight[p] = "queued"
                self.read_total += 1
                self.pool.submit(self._read_job, p)
        if refused:
            self.toast.show_message("Not added: " + "; ".join(refused), ms=8000)
        if self.view[0] in (SETTINGS, "category"):
            self.view = (ALL, None)
        self.refresh()

    def _read_job(self, path):
        self.bridge.read_done.emit(path, "reading")
        try:
            out = self.workers.run(path)  # crashes and timeouts come back as failed results
        except Exception as e:  # never semantic evidence; reason carries no document text
            out = RuntimeError(f"internal error ({type(e).__name__})")
        self.bridge.read_done.emit(path, out)

    def _read_done(self, path, out):
        if out == "reading":
            if path in self.inflight:
                self.inflight[path] = "reading"
            self.refresh()
            return
        self.inflight.pop(path, None)
        if isinstance(out, Exception):
            self.toast.show_message(f"{Path(path).name} couldn't be read.")
        else:
            doc_id, note = self.org.record(path, *out)
            if doc_id is None:
                self.toast.show_message(f"{Path(path).name} couldn't be read ({note}).")
            elif note == "already imported":
                self.toast.show_message(f"{Path(path).name} is already in ClassiFile.")
        self.refresh()

    # -- filing -----------------------------------------------------------------------------------------------
    def file_docs(self, ids, name):
        """File waiting documents in a category (created if new). Only these documents; never a rule or alias."""
        docs = [self.org.catalog.document(i) for i in ids]
        docs = [d for d in docs if d and d["status"] == "needs_decision" and d["id"] not in self.filing
                and not self.org.original_missing(d["id"])]
        name = " ".join(name.split())
        if not docs or not name:
            return
        if self.failure and set(self.failure[0]) & {d["id"] for d in docs}:
            self.failure = None  # a new attempt; a new failure replaces it
        if self.org.output_root is None:
            self.failure = ([d["id"] for d in docs], "Choose an output folder in Settings first.")
            self.refresh()
            return
        existing = self.existing_category(name)
        try:
            cat_id = existing["id"] if existing else self.org.create_category(name)
        except ValueError as e:
            self.toast.show_message(str(e).capitalize())
            return
        self.batch, self.batch_name = [], name
        self.new_category = None if existing else cat_id  # removed again if every copy fails
        for d in docs:
            self.filing[d["id"]] = cat_id
        for d in docs:
            self.pool.submit(self._file_job, d["id"], cat_id)
        self.refresh()

    def _file_job(self, doc_id, cat_id):
        try:
            out = self.org.file(doc_id, cat_id)
        except Exception as e:
            out = e if isinstance(e, ValueError) or type(e).__name__ == "CopyError" else RuntimeError(
                f"Something went wrong while filing ({type(e).__name__}). Try again.")
        self.bridge.file_done.emit(doc_id, out)

    def _file_done(self, doc_id, out):
        cat_id = self.filing.pop(doc_id, None)
        self.batch.append((doc_id, out))
        if any(c == cat_id for c in self.filing.values()):  # wait for the rest of this filing action
            self.refresh()
            return
        cat = self.org.catalog.category(cat_id)
        cat_name = cat["name"] if cat else self.batch_name
        ok = [i for i, o in self.batch if not isinstance(o, Exception)]
        bad = [(i, o) for i, o in self.batch if isinstance(o, Exception)]
        discarded = bool(not ok and cat_id == self.new_category and self.org.discard_unused_category(cat_id))
        if bad:
            first_name = self.org.catalog.document(bad[0][0])["file_name"]
            reason = bad[0][1]
            if discarded:
                text = (f"The new category '{cat_name}' wasn't created, because "
                        + (f"{first_name} couldn't be filed. " if len(bad) == 1
                           else f"none of the {len(bad)} documents could be filed. ") + f"{reason}")
            else:
                text = (f"{first_name} wasn't filed. {reason}" if len(bad) == 1
                        else f"{len(bad)} documents weren't filed. {reason}")
            self.failure = ([i for i, _ in bad], text)
        if ok:
            what = self.org.catalog.document(ok[0])["file_name"] if len(ok) == 1 else f"{len(ok)} documents"
            self.toast.show_message(f"Filed {what} in {cat_name}", "Show",
                                    lambda c=cat_id, d=ok: self._show_filed(c, d))
        self.batch = []
        self.refresh()

    def _show_filed(self, cat_id, ids):
        if self.org.catalog.category(cat_id):
            self.show_view("category", cat_id)
            self.select_docs(ids)

    def leave_pending(self, ids):
        self.deferred = [i for i in self.deferred if i not in ids] + list(ids)
        self.toast.show_message("Left pending. It stays here until you decide.")
        self.refresh()

    # -- removing, locating, opening --------------------------------------------------------------------------
    def remove_docs(self, ids):
        docs = [d for d in (self.org.catalog.document(i) for i in ids) if d and d["status"] in WAITING]
        if not docs or not self.confirm_remove(len(docs)):
            return
        try:
            self.org.remove([d["id"] for d in docs])
        except ValueError as e:
            self.toast.show_message(str(e).capitalize())
            return
        self.toast.show_message(f"Removed {len(docs)} document{'s' if len(docs) > 1 else ''} from ClassiFile. "
                                "The original files weren't touched.")
        self.refresh(select_docs=[])

    def locate_doc(self, doc_id):
        d = self.org.catalog.document(doc_id)
        start = Path(d["source_path"]).parent
        path = self.pick_file(d["file_name"], start if start.exists() else Path.home())
        if not path:
            return
        try:
            self.org.locate(doc_id, path)
        except ValueError as e:
            self.failure = ([doc_id], f"{d['file_name']}: {e}")
            self.refresh()
            return
        if self.failure and doc_id in self.failure[0]:
            self.failure = None
        self.toast.show_message(f"Found {d['file_name']}. You can file it now.")
        self.refresh()
        if self.details_open:
            self.details.show_doc(doc_id)

    def open_doc(self, doc_id):
        path = self.filed_copy(doc_id)
        if path:
            self.open_path(path)

    def show_doc_in_folder(self, doc_id):
        path = self.filed_copy(doc_id)
        if path:
            self.show_in_folder(path)

    def activate_selected(self):
        ids = self.selected_ids()
        if len(ids) != 1:
            return
        if self.filed_copy(ids[0]):
            self.open_doc(ids[0])
        elif self.org.catalog.document(ids[0])["status"] in WAITING:
            self.show_view(DECIDE)

    def new_category_clicked(self):
        name = " ".join(self.ask_category_name().split())
        if not name:
            return
        try:
            self.org.create_category(name)
        except ValueError as e:
            self.toast.show_message(str(e).capitalize())
            return
        self.toast.show_message(f"Created category {name}")
        self.refresh()

    def _context_menu(self, pos):
        menu = self.context_menu(self.selected_ids())
        if menu:
            menu.exec(self.table.viewport().mapToGlobal(pos))

    def context_menu(self, ids):
        if not ids:
            return None
        menu = QMenu(self)
        single = ids[0] if len(ids) == 1 else None
        if single and self.filed_copy(single):
            menu.addAction("Open", lambda: self.open_doc(single))
            menu.addAction("Show in folder", lambda: self.show_doc_in_folder(single))
        if single:
            menu.addAction("Details", lambda: self.set_details_open(True))
        docs = [self.org.catalog.document(i) for i in ids]
        if single and docs[0]["status"] == "needs_decision" and self.org.original_missing(single):
            menu.addAction("Locate file…", lambda: self.locate_doc(single))
        if any(d["status"] in WAITING for d in docs):
            menu.addAction("Remove from ClassiFile", lambda: self.remove_docs(ids))
        return menu

    # -- bulk filing --------------------------------------------------------------------------------------------
    def _bulk_file_clicked(self):
        self.bulk_form.setVisible(not self.bulk_form.isVisible())
        if self.bulk_form.isVisible():
            self.bulk_field.setFocus()
            self._update_bulk_confirm()

    def _update_bulk_confirm(self):
        name = " ".join(self.bulk_field.text().split())
        self.bulk_field.setProperty("filled", bool(name))
        restyle(self.bulk_field)
        existing = self.existing_category(name)
        self.bulk_tag.setVisible(bool(name))
        self.bulk_tag.setText("Existing" if existing else "New")
        self.bulk_tag.setObjectName("tagExisting" if existing else "tagNew")
        restyle(self.bulk_tag)
        self.bulk_go.setText("File" if existing or not name else "Create && file")
        self.bulk_go.setEnabled(bool(name))

    def _bulk_confirm(self):
        name = self.bulk_field.text()
        if name.strip():
            self.file_docs(self.selected_ids(), name)
            self.bulk_field.clear()
            self.bulk_form.hide()

    # -- keyboard: Space = details, Enter = open or decide, Delete = remove, Esc = close ---------------------
    def eventFilter(self, obj, e):
        if obj is getattr(self, "content", None) and e.type() in (QEvent.Move, QEvent.Resize):
            if self.details.isVisible() and self.details.parent() is self.workspace:
                self._place_details()
            return False
        if obj is self.table and e.type() == QEvent.KeyPress:
            key = e.key()
            if key == Qt.Key_Space:
                self.set_details_open(not self.details_open)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.activate_selected()
                return True
            if key == Qt.Key_Delete:
                self.remove_docs(self.selected_ids())
                return True
            if key == Qt.Key_Escape and self.details_open:
                self.close_details()
                return True
        return super().eventFilter(obj, e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self.preview_overlay.isVisible():
                self.preview_overlay.hide()
            elif self.details.isVisible():
                self.close_details()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        n = len(self.waiting())
        if n and self.org.catalog.get_setting("close_notice") != "off":
            choice, dont_show = self.ask_close(n)
            if dont_show:
                self.org.catalog.set_setting("close_notice", "off")
            if choice == "back":
                e.ignore()
                self.show_view(DECIDE)
                return
        self.details.preview.close_pdf()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.workers.close()
        super().closeEvent(e)


def main():
    app = make_app(sys.argv)
    w = MainWindow(Organizer(Catalog.open_default()))
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
