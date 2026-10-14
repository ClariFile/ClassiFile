"""Main window: a quiet sidebar, a document list, the "Needs your decision" page, and details on request.

Run: .venv\\Scripts\\python -m classifile.app
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication, QEasingCurve, QEvent, QItemSelection, QItemSelectionModel, QObject, QPoint,
    QPropertyAnimation, QSize, Qt, QTimer, QUrl, Signal,
)
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLayout, QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter,
    QListView, QScrollArea, QStackedWidget, QStyleFactory, QTreeView, QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key
from classifile.app import app_icon, make_app
from classifile.app.autofiled import AutoPage
from classifile.app.decision import DecisionPage
from classifile.app.details import DetailsPanel
from classifile.app.models import DOC, SORTS, CategoryModel, DocumentFilter, DocumentModel, sorted_by_name
from classifile.app.widgets import (
    CHECKLIST_MAX, DATE_COLUMN_MIN, PANEL, TIGHT, DETAILS_MAX, DETAILS_MIN, DETAILS_WIDTH, FILE_ICON, GROUP, LIST_MIN, MIN_WINDOW,
    MOTION_STANDARD, NARROW, PAD, RELATED, SEARCH_MAX, SECTION, SIDEBAR_WIDTH, SUPPORTED, TOAST, TOAST_LONG,
    WIDE, WINDOW, box, motion, qt_palette, set_motion, slide_away, style_sheet, use_theme,
    DropOverlay, ElidedLabel, Notices, PickerDialog, PreviewOverlay, Toast, wrappable,
)
from classifile.copies.engine import CopyError
from classifile.catalog.db import Catalog
from classifile.organizer import Organizer, is_cloud_synced, read_and_analyze
from classifile.worker import WorkerPool

ALL, DECIDE, RECENT, SETTINGS, AUTO = "all", "decide", "recent", "settings", "auto"
VIEW_TITLES = {ALL: "All documents", DECIDE: "Needs your decision", RECENT: "Recently added", SETTINGS: "Settings",
               AUTO: "Filed automatically"}
AUTO_LEVELS = (("off", "Off: always ask me"), ("very strict", "Very strict"), ("strict", "Strict"),
               ("balanced", "Balanced"), ("lenient", "Lenient"))   # matching.LEVELS, as Settings words them
RECENT_DAYS = 7
READ_WORKERS = min(4, os.cpu_count() or 2)  # documents read (and OCR'd) at once, each in its own process
WAITING = ("needs_decision", "pending", "failed")
APPEARANCES = (("system", "Follow Windows", Qt.ColorScheme.Unknown), ("light", "Light", Qt.ColorScheme.Light),
               ("dark", "Dark", Qt.ColorScheme.Dark))
MOTIONS = (("system", "Follow Windows"), ("reduce", "Reduce motion"), ("full", "Full motion"))
FIND_CATEGORY_FROM = 11     # "Find category…" above the sidebar's list from this many categories
SEARCH_HINTS = {ALL: "Search all documents…", RECENT: "Search recently added…", DECIDE: "Search these documents…",
                AUTO: "Search these documents…"}


@lru_cache(maxsize=4096)
def short_date(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d") if iso else ""


@lru_cache(maxsize=4096)
def stored_analysis(text):
    """A document's stored analysis, parsed once per distinct text. Shared: never change what it returns."""
    return json.loads(text) if text else {}


def settings_card(title, sentence, *parts):
    """One Settings topic as a titled panel: a heading, a plain sentence (optional), then its rows and controls."""
    card = QFrame()
    card.setObjectName("settingsCard")
    v = box(QVBoxLayout(card), PANEL, RELATED)
    heading = QLabel(title)
    heading.setObjectName("heading")
    v.addWidget(heading)
    if sentence:
        about = QLabel(sentence)
        about.setObjectName("secondary")
        about.setWordWrap(True)
        about.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        v.addWidget(about)
    v.addSpacing(TIGHT)
    for part in parts:
        v.addLayout(part) if isinstance(part, QLayout) else v.addWidget(part)
    return card


def recent_since():
    return (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).isoformat(timespec="seconds")


class Bridge(QObject):
    read_done = Signal(str, object)       # path, (result, analysis, summary) | "reading"
    file_done = Signal(str, object)       # doc_id, (outcome, path) or Exception
    job_done = Signal(object, object)     # what to call in the window, with what a background job returned


class MainWindow(QWidget):
    def __init__(self, organizer, ask_output_root=True, workers=None):
        super().__init__()
        self.org = organizer
        self.inflight = {}          # path -> "queued" | "reading"
        self.read_total = 0         # documents in the current reading run, for "Reading 3 of 12…"
        self.read_results = []      # finished reads not recorded yet: taken one per turn of the event loop
        self.filing = {}            # doc_id -> category id, while its copy is being made
        self.batch, self.batch_name, self.new_category = [], "", None
        self.auto_batch = []        # (doc_id, category id) the app has just filed by itself, until it says so
        self.auto_running = 0       # automatic filings under way
        self.failure = None         # (doc ids, sentence): stays as a notice until those documents are resolved
        self.run = None             # the import under way: what it read, filed and created, for one summary
        self.updating = False       # matching is updating by itself in the background
        self.update_note = None     # the note at the top after matching updated by itself (A7, record 2.6)
        self.feedback = {}          # doc_id -> reason ("" = none given): the suggested names were set aside
        self.moving = 0             # moves and renames under way (they copy files, so they run off this thread)
        self.picker_dialog = None
        self.deferred = []          # "Leave pending": moved to the end of the decision page for this session
        self.view = (ALL, None)     # ("all" | "decide" | "recent" | "settings" | "category", category id)
        self.details_open = False
        self.inspected = None       # the document whose details are open beside the decision or auto-filed page
        self.missing = {}           # waiting doc_id -> its original is not where it was (looked for on request)
        self.waiting_docs = []      # the waiting documents as of the last refresh, with what their cards show
        self.doc_rows = []          # every document as of the last refresh
        self.entered = None         # the view the last refresh showed
        self.since = recent_since() # "Recently added" starts here; set again whenever a view is opened
        self.pool = ThreadPoolExecutor(max_workers=READ_WORKERS)
        self.workers = workers or WorkerPool(read_and_analyze, size=READ_WORKERS)
        self.bridge = Bridge()
        self.bridge.read_done.connect(self._read_done)
        self.bridge.file_done.connect(self._file_done)
        self.bridge.job_done.connect(lambda done, result: done(result))
        self.list_style = QStyleFactory.create("Fusion")  # one selection bar (Windows 11 adds a second)
        self.set_appearance(self.org.catalog.get_setting("appearance", "system"))
        QApplication.styleHints().colorSchemeChanged.connect(lambda *_: self.apply_theme())   # Windows changed
        set_motion(self.org.catalog.get_setting("motion", "system"))
        self.setAcceptDrops(True)
        self.setMinimumSize(*MIN_WINDOW)
        self.resize(*WINDOW)
        self._build()
        self.apply_theme()
        self.org.startup()
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

    def ask_new_name(self, current):
        text, ok = QInputDialog.getText(self, "Rename category", "New name:", text=current)
        return text if ok else ""

    def ask_delete_empty(self, n):
        """After a move: asked once for all the categories it left empty."""
        text = "1 category is now empty. Delete it?" if n == 1 else f"{n} categories are now empty. Delete them?"
        return QMessageBox.question(self, "Empty categories", text) == QMessageBox.Yes

    def pick_category(self, title, verb, on_choice):
        """The category picker in its own small window; on_choice(kind, category id or None, name)."""
        self.picker_dialog = PickerDialog(self, title, verb, on_choice)
        self.picker_dialog.picker.set_choices(*self.picker_choices())
        self.picker_dialog.finished.connect(self.picker_dialog.deleteLater)
        self.picker_dialog.open()
        self.picker_dialog.picker.field.setFocus()

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
        self.menu_button.setAccessibleName("Show the sidebar")
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
        self.mode_label = QLabel()                # the automatic-filing mode in use, always in view
        self.mode_label.setObjectName("secondary")
        self.mode_link = QPushButton("Change")
        self.mode_link.setObjectName("link")
        self.mode_link.setToolTip("Automatic filing is set in Settings")
        self.mode_link.clicked.connect(lambda: self.show_view(SETTINGS))
        mode = box(QHBoxLayout(), spacing=0)
        mode.addWidget(self.mode_label)
        mode.addWidget(self.mode_link)
        head.addLayout(mode)
        head.addWidget(self.processing)
        head.addWidget(self.add_button)

        self.notices = Notices()
        self.search = QLineEdit()             # one field per page, always here; it filters what is loaded
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search")
        self.search.textChanged.connect(lambda *_: self._search_changed())
        self.search.installEventFilter(self)  # Esc clears it first
        QShortcut(QKeySequence.Find, self, activated=self.focus_search)
        self.result_count = QLabel()          # "3 of 7", while a search is on
        self.result_count.setObjectName("secondary")
        self.sort = QComboBox()
        self.sort.setView(QListView())           # the opened list takes the shared style
        self.sort.addItems(SORTS)
        self.sort.setAccessibleName("Sort the list")
        self.sort.currentIndexChanged.connect(lambda *_: self.filter.show(order=self.sort.currentText()))
        self.details_toggle = QPushButton("Details")
        self.details_toggle.setToolTip("Show the selected document's pages and details beside the list (Space)")
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self.set_details_open)
        self.toolbar = QWidget()
        tools = box(QHBoxLayout(self.toolbar))
        self.search.setMaximumWidth(SEARCH_MAX)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.result_count)
        tools.addStretch(0)
        tools.addWidget(self.sort)
        tools.addSpacing(GROUP - RELATED)       # finding documents | showing details
        tools.addWidget(self.details_toggle)

        self.bulk = self._bulk_bar()
        self.stack = QStackedWidget()
        self.table = self._table()
        self.empty_state = self._empty_state()
        self.decision = DecisionPage(self)
        self.auto_page = AutoPage(self)
        self.settings_page = self._settings_page()
        self.no_match = self._no_match_page()
        for page in (self.table, self.empty_state, self.decision, self.auto_page, self.settings_page, self.no_match):
            self.stack.addWidget(page)
        self.details = DetailsPanel(self)
        self.details.setMinimumWidth(DETAILS_MIN)
        self.details.hide()
        self.slide = QPropertyAnimation(self.details, b"pos", self)   # the panel enters from the right edge
        self.slide.setDuration(MOTION_STANDARD)
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
        brand_icon.setPixmap(app_icon().pixmap(FILE_ICON, FILE_ICON))
        brand = QLabel("ClassiFile")
        brand.setObjectName("brand")
        top = box(QHBoxLayout(), (GROUP, PAD, GROUP, GROUP))
        top.addWidget(brand_icon)
        top.addWidget(brand, 1)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav = {}
        for key in (ALL, DECIDE, AUTO, RECENT):
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
        self.auto_count = QLabel()                # how many documents the app filed by itself
        self.auto_count.setObjectName("count")
        self.auto_count.setAttribute(Qt.WA_TransparentForMouseEvents)
        count_row = box(QHBoxLayout(self.nav[AUTO]), (0, 0, GROUP, 0))
        count_row.addStretch(1)
        count_row.addWidget(self.auto_count)
        header = QLabel("CATEGORIES")
        header.setObjectName("section")
        self.add_category = QPushButton("+")
        self.add_category.setObjectName("icon")
        self.add_category.setToolTip("Create a category")
        self.add_category.setAccessibleName("Create a category")
        self.add_category.clicked.connect(self.new_category_clicked)
        cat_head = box(QHBoxLayout(), (GROUP, SECTION, RELATED, RELATED))
        cat_head.addWidget(header, 1)
        cat_head.addWidget(self.add_category)
        self.cat_model = CategoryModel(self)      # names with counts; the documents are in the main list
        self.cat_sorted = sorted_by_name(self.cat_model)
        self.cats = QTreeView()
        self.cats.setObjectName("categories")
        self.cats.setModel(self.cat_sorted)
        self.cats.setHeaderHidden(True)
        self.cats.setRootIsDecorated(False)
        self.cats.setItemsExpandable(False)
        self.cats.setIndentation(0)
        self.cats.setUniformRowHeights(True)
        self.cats.header().setStretchLastSection(False)
        self.cats.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cats.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.cats.setStyle(self.list_style)
        self.cats.setTextElideMode(Qt.ElideRight)
        self.cats.clicked.connect(self._category_clicked)
        self.cats.activated.connect(self._category_clicked)   # Enter
        self.cats.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cats.customContextMenuRequested.connect(self._category_menu_at)
        self.find_category = QLineEdit()          # only with many categories (docs/UI_PROPOSAL.md, phase 5)
        self.find_category.setPlaceholderText("Find category…")
        self.find_category.setAccessibleName("Find category")
        self.find_category.setClearButtonEnabled(True)
        self.find_category.textChanged.connect(lambda text: self.cat_sorted.setFilterFixedString(text.strip()))
        self.find_category.hide()
        self.cats_none = QLabel()                 # nothing matches what was typed
        self.cats_none.setObjectName("secondary")
        self.cats_none.setWordWrap(True)
        self.cats_none.setContentsMargins(GROUP, 0, GROUP, 0)
        self.cats_none.hide()
        self.find_category.textChanged.connect(lambda *_: self._show_found_categories())
        self.cats_empty = QLabel("No categories yet. Press + to create one, or file a document.")
        self.cats_empty.setObjectName("secondary")
        self.cats_empty.setWordWrap(True)
        self.cats_empty.setContentsMargins(GROUP, 0, GROUP, 0)
        settings = QPushButton("⚙  Settings")
        settings.setObjectName("nav")
        settings.setProperty("prominent", True)  # outlined and set apart: easy to find
        settings.setToolTip("Automatic filing, new folders, learning, output folder and appearance")
        settings.setCheckable(True)
        settings.clicked.connect(lambda: self.show_view(SETTINGS))
        self.nav_group.addButton(settings)
        self.nav[SETTINGS] = settings
        v = box(QVBoxLayout(side), (0, 0, 0, RELATED), 0)
        v.addLayout(top)
        for key in (ALL, DECIDE, AUTO, RECENT):
            v.addWidget(self.nav[key])
        v.addLayout(cat_head)
        find = box(QHBoxLayout(), (GROUP, 0, GROUP, RELATED))
        find.addWidget(self.find_category)
        v.addLayout(find)
        v.addWidget(self.cats_empty)
        v.addWidget(self.cats_none)
        v.addWidget(self.cats, 1)
        v.addSpacing(RELATED)
        v.addWidget(settings)
        return side

    def _table(self):
        self.docs = DocumentModel(self)           # every document; the view, search and sort are a filter over it
        self.filter = DocumentFilter(self.docs)
        table = QTreeView()
        table.setModel(self.filter)
        table.setRootIsDecorated(False)
        table.setItemsExpandable(False)
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
        table.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())
        table.doubleClicked.connect(lambda *_: self.activate_selected())
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._context_menu)
        table.installEventFilter(self)
        table.viewport().installEventFilter(self)   # its width decides the columns
        return table

    def _bulk_bar(self):
        bar = QFrame()
        bar.setObjectName("bulk")
        self.bulk_count = QLabel()
        self.bulk_file = QPushButton("File in…")
        self.bulk_file.clicked.connect(self._bulk_file_clicked)
        self.bulk_move = QPushButton("Move to…")
        self.bulk_move.clicked.connect(lambda: self.move_docs(self.selected_ids()))
        self.bulk_remove = QPushButton("Remove")
        self.bulk_remove.clicked.connect(lambda: self.remove_docs(self.selected_ids()))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.table.clearSelection())  # the list is built after this bar
        self.bulk_clear = clear
        h = box(QHBoxLayout())
        h.addWidget(self.bulk_count)
        h.addSpacing(GROUP - RELATED)
        for b in (self.bulk_file, self.bulk_move, self.bulk_remove):
            h.addWidget(b)
        h.addStretch(1)
        h.addWidget(clear)
        rows = box(QVBoxLayout(bar), (GROUP, RELATED, RELATED, RELATED))
        rows.addLayout(h)
        bar.hide()
        return bar

    def _empty_state(self):
        page = QWidget()
        title = QLabel("Bring some order to your documents.")
        title.setObjectName("pageTitle")
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

    def _no_match_page(self):
        page = QWidget()
        self.no_match_text = QLabel()
        self.no_match_text.setObjectName("secondary")
        self.clear_search = QPushButton("Clear search")
        self.clear_search.clicked.connect(self.search.clear)
        v = box(QVBoxLayout(page), spacing=GROUP)
        v.addStretch(1)
        v.addWidget(self.no_match_text, 0, Qt.AlignCenter)
        v.addWidget(self.clear_search, 0, Qt.AlignCenter)
        v.addStretch(2)
        return page

    def _settings_page(self):
        outer = QScrollArea()                   # scrolls when the window is short, so nothing is cut
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.NoFrame)
        page = QWidget()                        # as wide as the page, like the others: text left, controls right
        page.setMinimumWidth(0)
        page.setContentsMargins(0, 0, GROUP, 0) # room for the scroll bar
        outer.setWidget(page)
        self.root_label = QLabel()
        self.root_label.setWordWrap(True)
        self.root_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.change_root = QPushButton("Change…")
        self.change_root.clicked.connect(self.change_output_root)
        row = box(QHBoxLayout(), spacing=GROUP)
        row.addWidget(self.root_label, 1)
        row.addWidget(self.change_root)
        self.appearance = QComboBox()             # light, dark, or what Windows is set to
        self.appearance.setView(QListView())
        self.appearance.setAccessibleName("Appearance")
        for name, words, _ in APPEARANCES:
            self.appearance.addItem(words, name)
        self.appearance.activated.connect(lambda *_: self.set_appearance(self.appearance.currentData(), save=True))
        look_row = box(QHBoxLayout(), spacing=GROUP)
        look_row.addWidget(QLabel("Light or dark"), 1)
        look_row.addWidget(self.appearance)
        self.motion = QComboBox()                 # Reduce motion: every change instant
        self.motion.setView(QListView())
        self.motion.setAccessibleName("Motion")
        for name, words in MOTIONS:
            self.motion.addItem(words, name)
        self.motion.activated.connect(lambda *_: self.set_motion(self.motion.currentData()))
        motion_row = box(QHBoxLayout(), spacing=GROUP)
        motion_row.addWidget(QLabel("Motion (panels that slide, rows that fold away)"), 1)
        motion_row.addWidget(self.motion)
        self.close_toggle = QCheckBox("Ask before closing when documents are waiting")
        self.close_toggle.toggled.connect(
            lambda on: self.org.catalog.set_setting("close_notice", "on" if on else "off"))
        self.matching_label = QLabel()
        self.matching_label.setWordWrap(True)
        self.matching_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.matching_button = QPushButton("Update matching")
        self.matching_button.setToolTip("Learn again from the documents you filed. The new version is checked, and "
                                        "the previous one is kept if it did better.")
        self.matching_button.clicked.connect(self.update_matching)
        match_row = box(QHBoxLayout(), spacing=GROUP)
        match_row.addWidget(self.matching_label, 1)
        match_row.addWidget(self.matching_button, 0, Qt.AlignTop)
        self.matching_log = QLabel()              # the last versions: when, by whom, what the check found
        self.matching_log.setObjectName("secondary")
        self.matching_log.setWordWrap(True)
        self.matching_log.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.auto_folders = QCheckBox("Create new folders by itself")
        self.auto_folders.setToolTip("Off until you turn it on")
        self.auto_folders.toggled.connect(self.set_auto_folders)
        folders_text = QLabel("When at least three waiting documents match none of your categories and clearly share "
                              "a subject, ClassiFile creates a folder for them and names it; rename it with one click "
                              "in Filed automatically. Two alike, or one alone, stay a question for you. In "
                              "\u201cOnly the ones I tick\u201d mode ClassiFile always asks first.")
        folders_text.setObjectName("secondary")
        folders_text.setWordWrap(True)
        folders_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.auto_level = QComboBox()             # the level of automatic filing; every change is recorded
        self.auto_level.setView(QListView())
        for name, words in AUTO_LEVELS:
            self.auto_level.addItem(words, name)
        self.auto_level.setAccessibleName("Automatic filing level")
        self.auto_level.activated.connect(lambda *_: self.set_auto_level(self.auto_level.currentData()))
        auto_text = QLabel("How sure ClassiFile must be before it files by itself")
        auto_text.setWordWrap(True)
        auto_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        auto_row = box(QHBoxLayout(), spacing=GROUP)
        auto_row.addWidget(auto_text, 1)
        auto_row.addWidget(self.auto_level, 0, Qt.AlignTop)
        self.auto_scope = QComboBox()             # selected-category mode (decision record A5)
        self.auto_scope.setView(QListView())
        self.auto_scope.addItem("All categories", "all")
        self.auto_scope.addItem("Only the ones I tick", "selected")
        self.auto_scope.setAccessibleName("File automatically into")
        self.auto_scope.activated.connect(lambda *_: self.set_auto_scope())
        scope_text = QLabel("Which categories it may file into")
        scope_row = box(QHBoxLayout(), spacing=GROUP)
        scope_row.addWidget(scope_text, 1)
        scope_row.addWidget(self.auto_scope)
        self.auto_ticks = QScrollArea()           # one tick per category; shown in selected-category mode
        self.auto_ticks.setWidgetResizable(True)
        self.auto_ticks.setFrameShape(QFrame.NoFrame)
        self.auto_ticks.setMaximumHeight(CHECKLIST_MAX)
        self.scope_boxes = []
        about_text = QLabel("ClassiFile organizes copies of your documents into categories; original files stay "
                            "unchanged. Part of ClariFile.")
        about_text.setWordWrap(True)
        # One titled panel per topic, the most used first: a heading, a plain sentence, then the controls.
        v = box(QVBoxLayout(page), spacing=GROUP)
        v.addWidget(settings_card(
            "Automatic filing", "A document is filed without a question when one category is clearly ahead of the "
            "others and already holds 3 documents you confirmed. Stricter levels ask you more often and make fewer "
            "mistakes.", auto_row, scope_row, self.auto_ticks, self.auto_folders, folders_text))
        v.addWidget(settings_card(
            "Learning", "ClassiFile learns from the documents you file, confirm or move. It updates by itself after "
            "every 10 of them, and keeps the previous version if the new one does worse.",
            match_row, self.matching_log))
        v.addWidget(settings_card("Output folder", "Copies of your documents are filed here. The originals are "
                                  "never changed.", row))
        v.addWidget(settings_card("Appearance", "", look_row, motion_row))
        v.addWidget(settings_card("When closing", "", self.close_toggle))
        v.addWidget(settings_card("About", "", about_text))
        v.addStretch(1)
        return outer

    # -- views ------------------------------------------------------------------------------------------------
    def show_view(self, key, category=None):
        self._clear_search()        # no hidden text ever filters a page
        if key != self.view[0]:
            self.inspected = None   # another page: its details close
            if self.view[0] == AUTO:
                self.auto_page.leave()
        self.view, self.since = (key, category), recent_since()
        if key == SETTINGS:
            self.update_note = None             # the log is in view
        if key in self.nav:
            self.nav[key].setChecked(True)
        else:
            checked = self.nav_group.checkedButton()
            if checked:
                self.nav_group.setExclusive(False)
                checked.setChecked(False)
                self.nav_group.setExclusive(True)
        self.refresh()

    def _clear_search(self):
        self.search.blockSignals(True)   # the refresh that follows applies it
        self.search.clear()
        self.search.blockSignals(False)

    def _category_clicked(self, index):
        cat = index.siblingAtColumn(0).data(DOC)
        if cat:
            self.show_view("category", cat)

    def review(self):
        self.show_view(DECIDE)

    # -- data for the views -----------------------------------------------------------------------------------
    def waiting(self):
        return [d for d in self.org.catalog.documents(None) if d["status"] in WAITING]

    def decision_docs(self, recheck=True, cats=None):
        """The waiting documents with what their cards show, from one query. recheck: look on disk for every
        original again; otherwise only for documents not looked for yet. cats: the categories as they are now.
        Once matching is in use, a document's stored text is read and scored the first time it is seen."""
        names = {c["id"]: c["name"] for c in (self.org.catalog.categories() if cats is None else cats)}
        matching = bool(self.org.matcher())
        docs = []
        for d in self.org.catalog.waiting_documents():
            if d["status"] not in WAITING:
                continue
            analysis = stored_analysis(d["analysis_json"])
            if d["status"] != "needs_decision":
                missing = False
            elif recheck or d["id"] not in self.missing:
                missing = self.missing[d["id"]] = self.org.original_missing(d["id"], d["source_path"])
            else:
                missing = self.missing[d["id"]]
            d = dict(d)
            del d["analysis_json"]
            ready = d["status"] == "needs_decision" and not missing
            matches = [(names[c], n, w) for c, n, w in self.org.matches(d["id"], names)] if ready and matching else []
            docs.append(d | {"missing": missing, "suggestions": analysis.get("suggestions", []),
                             "unit": analysis.get("unit", "page"), "matches": matches,
                             "abstained": ready and matching and not matches})
        self.missing = {d["id"]: d["missing"] for d in docs}
        by_id = {d["id"]: d for d in docs}
        for ids, words in self.org.new_subject_groups([d["id"] for d in docs if d["abstained"]]):
            for i in ids:                       # the documents no category matches that resemble one another
                by_id[i]["subject"] = (ids[0], tuple(words))
        return sorted(docs, key=lambda d: d["id"] in self.deferred)

    def document_row(self, doc_id):
        return self.org.catalog.document_row(doc_id)

    def categories_by_key(self):
        return {c["name_key"]: c for c in self.org.catalog.categories()}

    def existing_category(self, name):
        return self.org.catalog.category_by_key(name_key(name)) if name else None

    def display_name(self, name):
        existing = self.existing_category(name)
        return existing["name"] if existing else name

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
    def refresh(self, select_docs=None, recheck=True):
        """Bring the window in line with the catalog, in place: rows, cards and counts that did not change are
        left alone, so what is typed, opened, selected or scrolled to stays. Five queries, whatever the size.
        recheck: look on disk for the waiting documents' originals again (a background read ending is no reason)."""
        cats = self._fill_categories()
        self.waiting_docs = waiting = self.decision_docs(recheck, cats)
        n = len(waiting)
        self.setWindowTitle(f"ClassiFile — {n} waiting" if n else "ClassiFile")
        self.decide_count.setText(str(n) if n else "")
        if self.view[0] == "category" and self.cat_model.get(self.view[1]) is None:
            self.view = (ALL, None)  # the category was deleted
        key = self.view[0]
        if key in self.nav:
            self.nav[key].setChecked(True)
        self._select_category()
        self._fill_list(self.org.catalog.all_documents())
        reviewed = self.auto_page.reviewed      # reviewed on the page just now: listed until it is left
        filed_by_app = [r for r in self.doc_rows if r["status"] == "filed" and (
            r["provenance"] == "machine-assigned" or r["id"] in reviewed)]
        self.auto_page.show_docs(filed_by_app)
        self.auto_page.show_folders(self._named_folders(cats))
        awaiting = self.auto_page.awaiting()
        self.auto_count.setText(str(awaiting) if awaiting else "")
        rows = [d["id"] for d in waiting] if key == DECIDE else [r["id"] for r in filed_by_app] if key == AUTO else []
        if self.inspected not in rows:
            self.inspected = None   # filed, removed or moved away: its details close
        if select_docs is not None:
            self.select_docs(select_docs)
        if key == SETTINGS:
            self._show_root()
            self._show_matching()
            self.auto_level.setCurrentIndex(self.auto_level.findData(self.org.auto_level()))
            self.appearance.setCurrentIndex(self.appearance.findData(
                self.org.catalog.get_setting("appearance", "system")))
            self.motion.setCurrentIndex(self.motion.findData(self.org.catalog.get_setting("motion", "system")))
            self.auto_folders.blockSignals(True)
            self.auto_folders.setChecked(self.org.auto_folders())
            self.auto_folders.blockSignals(False)
            self._show_scope(cats)
            self.close_toggle.blockSignals(True)
            self.close_toggle.setChecked(self.org.catalog.get_setting("close_notice") != "off")
            self.close_toggle.blockSignals(False)
        elif key == DECIDE:
            self.decision.show_items(waiting, {c["name_key"]: c for c in cats},
                                     [(r["key"], r["name"], r["count"]) for r in self.cat_model.rows],
                                     enter=self.entered != DECIDE)
        if key == SETTINGS or self.entered is None:
            self._show_mode()                   # it changes only in Settings: not asked for at every refresh
        self.entered = key
        self._show_page()
        self._show_processing()
        self._show_notices(waiting)
        self._selection_changed()

    def _show_page(self):
        """The page, its title and the search for the current view and search text. Reads nothing from the
        catalog, so a search key costs only this."""
        key, cat = self.view
        q = self.search.text().strip()
        if key in (ALL, RECENT, "category"):
            self.filter.show(key, cat, since=self.since, query=q)
        empty = not self.docs.rows
        title, total = VIEW_TITLES.get(key), None
        if key == "category":
            title = self.cat_model.get(cat)["name"]
        if key == DECIDE:
            total = len(self.waiting_docs)
            self.decision.set_query(q)
            shown = self.decision.shown_documents()
        elif key == AUTO:
            total = self.auto_page.awaiting()
            self.auto_page.set_query(q)
            shown = self.auto_page.shown_documents()
        elif key != SETTINGS:
            total, shown = self.filter.total(), self.filter.rowCount()
        self.page_title.setText(title + (f" · {total}" if total else ""))
        searchable = key != SETTINGS and not empty and (key not in (DECIDE, AUTO) or bool(shown or q))
        self.toolbar.setVisible(searchable)
        for w in (self.sort, self.details_toggle):
            w.setVisible(key not in (DECIDE, AUTO))     # rows open their own details there
        self.search.setPlaceholderText(SEARCH_HINTS.get(key) or f"Search {title}…")
        searching = bool(q) and searchable
        if key == AUTO:
            total = len(self.auto_page.items)
        self.result_count.setText(f"{shown} of {total}" if searching else "")
        self.result_count.setVisible(searching)
        if key == SETTINGS:
            page = self.settings_page
        elif searching and not shown:
            self.no_match_text.setText(f"Nothing here matches “{q}”.")
            page = self.no_match
        elif key == DECIDE:
            page = self.decision
        elif key == AUTO:
            page = self.auto_page
        else:
            page = self.empty_state if empty else self.table
        self.stack.setCurrentWidget(page)
        if page is self.table:
            self._apply_breakpoints()

    def _search_changed(self):
        self._show_page()
        self._selection_changed()

    def focus_search(self):
        """Ctrl+F."""
        if self.toolbar.isVisible():
            self.search.setFocus()
            self.search.selectAll()

    def _fill_categories(self):
        """The sidebar's categories with their counts, from two queries, updated in place. Returns the categories."""
        counts = self.org.catalog.category_counts()
        cats = self.org.catalog.categories()
        self.cat_model.sync([{"key": c["id"], "name": c["name"], "count": counts.get(c["id"], 0),
                              "new": bool(c["app_named"])} for c in cats])
        self.cats_empty.setVisible(not cats)
        many = len(cats) >= FIND_CATEGORY_FROM
        if not many and self.find_category.text():
            self.find_category.clear()          # no hidden text ever filters the list
        self.find_category.setVisible(many)
        self._show_found_categories()
        return cats

    def _show_found_categories(self):
        """The sidebar's find field: "No category matches …" when nothing does; the view open stays open."""
        q = self.find_category.text().strip()
        none = bool(q) and not self.cat_sorted.rowCount()
        self.cats_none.setText(f"No category matches \u201c{q}\u201d." if none else "")
        self.cats_none.setVisible(none)

    def _named_folders(self, cats):
        """[(category id, name, documents, key words)] of the folders the app created and named by itself."""
        out = []
        for c in sorted((c for c in cats if c["app_named"]), key=lambda c: c["created_at"], reverse=True):
            mine = [r for r in self.doc_rows if r.get("category_id") == c["id"]]
            words = next((json.loads(r["auto_json"]).get("words", []) for r in mine if r.get("auto_json")), [])
            out.append((c["id"], c["name"], len(mine), words))
        return out

    def _select_category(self):
        row = self.cat_model.at.get(self.view[1]) if self.view[0] == "category" else None
        selection = self.cats.selectionModel()
        if row is None:
            selection.clear()
            return
        index = self.cat_sorted.mapFromSource(self.cat_model.index(row, 0))
        if not selection.isSelected(index):  # never scrolled to: the list stays where the user left it
            selection.select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def _fill_list(self, docs=None):
        """The list's rows: the catalog's documents (those of the last refresh when none are given) and the files
        still being read. Only rows that differ are touched."""
        if docs is not None:
            self.doc_rows = docs
        shown = lambda r: ("filing" if r["id"] in self.filing else
                           "auto" if r["status"] == "filed" and r["provenance"] == "machine-assigned" else r["status"])
        rows = [dict(r) | {"key": r["id"], "date": short_date(r["imported_at"]), "shown_status": shown(r)}
                for r in self.doc_rows]
        rows += [{"key": ("reading", p), "id": None, "file_name": Path(p).name, "status": st, "shown_status": st,
                  "category": None, "category_id": None, "imported_at": None, "date": "", "status_reason": None}
                 for p, st in self.inflight.items()]
        self.docs.sync(rows)

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
        unreadable = [d for d in waiting if d["status"] in ("failed", "pending")]   # waiting: decision_docs()
        if self.failure:
            ids, text = self.failure
            if any(d["id"] in ids for d in waiting):
                notices.append(("error", text, "Review", self.review))
            else:
                self.failure = None  # resolved: filed or removed (locating or retrying clears it too)
        if unreadable:
            n = len(unreadable)
            notices.append(("error", f"{n} document{'s' if n > 1 else ''} couldn't be read.", "Review", self.review))
        missing = [d for d in waiting if d["missing"]]
        if missing and not self.failure:
            n = len(missing)
            notices.append(("warning", f"{n} document{'s have' if n > 1 else ' has'} moved since it was added. "
                            "Locate the original to file it.", "Review", self.review))
        if self.update_note:
            notices.append(("info", self.update_note, "OK", self._dismiss_update_note))
        ready = len(waiting) - len(unreadable)
        if ready and self.view[0] != DECIDE:    # on the auto-filed page a quiet line: that page is for reviewing
            notices.append(("quiet" if self.view[0] == AUTO else "info",
                            f"{ready} document{'s need' if ready > 1 else ' needs'} your decision.",
                            "Review", self.review))
        self.notices.show_notices(notices[:3])

    # -- selection and the details panel ----------------------------------------------------------------------
    def selected_ids(self):
        rows = sorted(self.table.selectionModel().selectedRows(0), key=lambda i: i.row())
        return [i.data(DOC) for i in rows if i.data(DOC)]

    def select_docs(self, ids):
        chosen, last = QItemSelection(), None
        for row in range(self.filter.rowCount()):
            index = self.filter.index(row, 0)
            if index.data(DOC) in ids:
                chosen.select(index, index)
                last = index
        selection = self.table.selectionModel()
        selection.select(chosen, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        if last is not None:
            selection.setCurrentIndex(last, QItemSelectionModel.NoUpdate)
        self._selection_changed()

    def _selection_changed(self):
        ids = self.selected_ids() if self.stack.currentWidget() is self.table else []
        self.bulk.setVisible(len(ids) > 1)
        if len(ids) > 1:
            docs = [self.docs.get(i) for i in ids]
            ready = [d for d in docs if d["status"] == "needs_decision"]
            self.bulk_count.setText(f"{len(ids)} selected")
            self.bulk_file.setEnabled(bool(ready))
            self.bulk_file.setToolTip("" if ready else "Only documents waiting for a decision can be filed.")
            self.bulk_move.setEnabled(any(d["status"] == "filed" for d in docs))
            self.bulk_move.setToolTip("" if self.bulk_move.isEnabled() else "Only filed documents can be moved.")
            self.bulk_remove.setEnabled(any(d["status"] in WAITING for d in docs))
        if self.details_open and self.stack.currentWidget() is self.table and len(ids) < 2:
            self._show_in_details(ids[0] if ids else None)
        self._place_details()

    def _show_in_details(self, doc_id):
        """Show a document (or the hint to select one) in the details panel, unless it shows just that already:
        an unchanged document is not read or drawn again."""
        state = ("nothing",) if doc_id is None else (doc_id, self.docs.get(doc_id), self.missing.get(doc_id))
        if self.details.shown != state:
            self.details.show_nothing() if doc_id is None else self.details.show_doc(doc_id)
            self.details.shown = state

    def set_details_open(self, open_):
        """Details (the document's pages and facts) stay on, on every list page, until switched off."""
        ids = self.selected_ids()
        self.details_open = bool(open_)
        self.details_toggle.blockSignals(True)
        self.details_toggle.setChecked(self.details_open)
        self.details_toggle.blockSignals(False)
        if self.details_open:
            self._show_in_details(ids[0] if ids else None)
        self._place_details()

    def show_details(self, doc_id):
        if self.view[0] in (DECIDE, AUTO):  # stays on the page: the details open beside the rows and their buttons
            if (self.inspected, self.details.doc_id) != (doc_id, doc_id) or self.details.isHidden():
                self.inspected = doc_id
                self.details.show_doc(doc_id)   # the list is not touched: it keeps its scroll position
            return self._place_details()
        if self.view[0] == SETTINGS:
            self.show_view(ALL)
        self.select_docs([doc_id])
        self.set_details_open(True)

    def close_details(self):
        page, inspected = self.stack.currentWidget(), self.inspected
        self.inspected = None
        self.set_details_open(False)
        row = page.row_of(inspected) if inspected and page in (self.decision, self.auto_page) else None
        if row is not None and row.isVisible():
            row.setFocus()                      # the keyboard goes back to the row it was looking at

    def _place_details(self):
        """Beside the list while both stay comfortable to use; otherwise over the list, with a way back. The
        document list goes by the window's width; the decision and auto-filed lists by the room they keep."""
        page = self.stack.currentWidget()
        rows = page in (self.decision, self.auto_page)
        for p in (self.decision, self.auto_page):
            p.set_inspected(self.inspected if p is page else None)
        show = (self.details_open and page is self.table) or (self.inspected is not None and rows)
        wide = self.content.width() - DETAILS_MIN >= LIST_MIN if rows else self.width() >= WIDE
        was_hidden = self.details.isHidden()
        if not show:
            if not was_hidden:
                slide_away(self.details, self.workspace)
            return
        if wide and self.details.parent() is not self.content:
            self.content.addWidget(self.details)
            default = max(DETAILS_WIDTH, min(DETAILS_MAX, self.content.width() * 3 // 10))
            width = max(DETAILS_MIN, self._setting("ui_details_width", default))
            if rows:                            # the list keeps its room
                width = min(width, self.content.width() - LIST_MIN)
            self.content.setSizes([max(300, self.content.width() - width), width])
        elif not wide and self.details.parent() is not self.workspace:
            self.details.setParent(self.workspace)
        self.details.set_overlay(not wide)
        self.details.show()
        if not wide:
            g = self.content.geometry()
            width = max(DETAILS_MIN, min(DETAILS_WIDTH, g.width() - PAD))
            self.details.setGeometry(g.right() + 1 - width, g.top(), width, g.height())
            self.details.raise_()
        if was_hidden:  # slides in at its final size, so the page picture is drawn once
            QCoreApplication.sendPostedEvents(self.content, QEvent.LayoutRequest)  # the splitter places it now
            self.slide.stop()
            self.slide.setDuration(motion(MOTION_STANDARD))
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
        self._fit_columns()
        self._place_details()

    def _fit_columns(self):
        """The list's columns for the room it has now; the details panel beside it takes some. Category grows
        with the list so wide screens don't leave a long empty gap after short names."""
        width = self.table.viewport().width()
        self.table.setColumnHidden(3, width < DATE_COLUMN_MIN)
        self.table.setColumnWidth(1, max(140, min(380, width // 4)))

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
                if self.run is None:
                    self.run = {"docs": [], "auto": set(), "unread": 0}
                self.inflight[p] = "queued"
                self.read_total += 1
                self.pool.submit(self._read_job, p)
        if refused:
            self.toast.show_message("Not added: " + "; ".join(refused), ms=TOAST_LONG)
        if self.view[0] in (SETTINGS, "category"):
            self._clear_search()
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
        if out == "reading":  # only its row and the "Reading 3 of 12…" line change: nothing is read or rebuilt
            if path in self.inflight:
                self.inflight[path] = "reading"
                self._fill_list()
            self._show_processing()
            return
        self.read_results.append((path, out))
        if len(self.read_results) == 1:
            QTimer.singleShot(0, self._record_next)

    def _record_next(self):
        """One finished read per turn of the event loop: when many end together, the mouse and keyboard are
        answered between them."""
        if not self.read_results:
            return
        path, out = self.read_results.pop(0)
        if self.read_results:
            QTimer.singleShot(0, self._record_next)
        self.inflight.pop(path, None)
        run = self.run if self.run is not None else {"docs": [], "auto": set(), "unread": 0}
        if isinstance(out, Exception):
            self.toast.show_message(f"{Path(path).name} couldn't be read.")
            run["unread"] += 1
        else:
            doc_id, note = self.org.record(path, *out)
            if doc_id is None:
                self.toast.show_message(f"{Path(path).name} couldn't be read ({note}).")
                run["unread"] += 1
            elif note == "already imported":
                self.toast.show_message(f"{Path(path).name} is already in ClassiFile.")
            else:
                run["docs"].append(doc_id)
                self.file_automatically([doc_id])   # a clear match is filed without a question (A0)
        self.refresh(recheck=False)  # once per document; what the user is doing in the window stays
        self._run_step()

    # -- filing -----------------------------------------------------------------------------------------------
    def file_docs(self, ids, name, feedback=None):
        """File waiting documents in a category (created if new). Only these documents; never a rule or alias.
        feedback: the suggested names were set aside ("" or one of the fixed reasons); None when they were not."""
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
            if feedback is not None:
                self.feedback[d["id"]] = feedback
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
            self.refresh(recheck=False)
            return
        cat = self.org.catalog.category(cat_id)
        cat_name = cat["name"] if cat else self.batch_name
        ok = [i for i, o in self.batch if not isinstance(o, Exception)]
        bad = [(i, o) for i, o in self.batch if isinstance(o, Exception)]
        for i, _ in self.batch:
            reason = self.feedback.pop(i, None)
            if reason is not None and i in ok:
                self.org.catalog.add_feedback(i, cat_id, reason or None)
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
        if ok:
            self.recheck_waiting()
            self.update_if_due()
        self.refresh()

    # -- automatic filing (decision record A0, B2) ------------------------------------------------------------
    def file_automatically(self, ids):
        """File those of these waiting documents whose match is clear, off this thread. The others wait."""
        for doc_id in ids:
            choice = None if doc_id in self.filing else self.org.auto_choice(doc_id)
            if choice:
                self.filing[doc_id] = choice[0]
                self.auto_running += 1
                self.pool.submit(self._auto_job, doc_id)

    def _auto_job(self, doc_id):
        try:
            out = self.org.file_automatically(doc_id)
        except Exception as e:          # the document stays waiting, with the reason on its card
            out = e
        self.bridge.job_done.emit(lambda result, d=doc_id: self._auto_done(d, result), out)

    def _auto_done(self, doc_id, cat_id):
        self.filing.pop(doc_id, None)
        self.auto_running -= 1
        filed = cat_id and not isinstance(cat_id, Exception)
        if filed and self.run is not None and doc_id in self.run["docs"]:
            self.run["auto"].add(doc_id)        # said in the import's summary
        elif filed:
            self.auto_batch.append((doc_id, cat_id))
        if self.auto_batch and not self.auto_running:      # said once, when all of them are done
            ids, cats = [d for d, _ in self.auto_batch], {c for _, c in self.auto_batch}
            where = self.org.catalog.category(self.auto_batch[0][1])["name"] if len(cats) == 1 else None
            what = self.org.catalog.document(ids[0])["file_name"] if len(ids) == 1 else f"{len(ids)} documents"
            self.toast.show_message(f"Filed {what} automatically" + (f" in {where}" if where else ""), "Show",
                                    lambda: self.show_view(AUTO))
            self.auto_batch = []
        self.refresh(recheck=False)
        self._run_step()

    # -- after an import: new folders, then one summary (decision record B2, 2.6) -----------------------------
    def _run_step(self):
        """Once every document of the import is read and the clear matches are filed: the folders the app creates
        by itself (when switched on), then one line that says what happened."""
        run = self.run
        if run is None or self.inflight or self.read_results or self.auto_running or run.get("creating"):
            return
        if "folders" not in run:
            ids = [d["id"] for d in self.waiting() if d["status"] == "needs_decision" and d["id"] not in self.filing]
            if not self.org.auto_folders() or len(ids) < 2:
                run["folders"] = []
            else:
                run["creating"] = True

                def done(result):
                    self.moving -= 1
                    run["creating"] = False
                    run["folders"] = [] if isinstance(result, Exception) else result
                    self.refresh(recheck=False)
                    self._run_step()

                self._background(lambda: self.org.create_folders(ids), done)
                return
        self.run = None
        self.import_summary(run)

    def import_summary(self, run):
        """ "Filed 12 automatically · 1 new folder · 3 need you", with Review."""
        status = {d: (self.org.catalog.document(d) or {"status": ""})["status"] for d in run["docs"]}
        in_folders = sum(len(ids) for _, ids in run["folders"])
        filed, folders = len(run["auto"]) + in_folders, len(run["folders"])
        need = sum(s == "needs_decision" for s in status.values())
        unread = run["unread"] + sum(s in ("failed", "pending") for s in status.values())
        parts = ([f"Filed {filed} automatically"] if filed else []) + (
            [f"{folders} new folder{'s' if folders != 1 else ''}"] if folders else []) + (
            [f"{need} need{'s' if need == 1 else ''} you"] if need else []) + (
            [f"{unread} couldn't be read"] if unread else [])
        if parts:
            target = DECIDE if need or unread else AUTO
            self.toast.show_message(" · ".join(parts), "Review", lambda: self.show_view(target), ms=TOAST_LONG)

    def set_motion(self, name):
        """Settings, "Motion": follow Windows, reduce (every change instant) or keep motion."""
        self.org.catalog.set_setting("motion", name)
        set_motion(name)

    def set_auto_folders(self, on):
        """Settings: automatic new folders on or off (recorded); waiting documents are looked at again."""
        self.org.set_auto_folders(on)
        self._show_mode()
        if on and self.run is None:
            self.run = {"docs": [], "auto": set(), "unread": 0}
            self._run_step()

    def set_appearance(self, name, save=False):
        """Light, dark, or as Windows is set: the theme is applied whole (apply_theme)."""
        scheme = next((s for n, _, s in APPEARANCES if n == name), Qt.ColorScheme.Unknown)
        self.appearance_name = name
        QApplication.styleHints().setColorScheme(scheme)    # the title bar and Windows' own drawing follow
        if save:
            self.org.catalog.set_setting("appearance", name)
        if hasattr(self, "stack"):
            self.apply_theme()

    def apply_theme(self):
        """Make the chosen theme the one in use, everywhere: the style sheet and the Qt palette are built again
        from it (the Fusion lists and native controls use the palette), and every icon and row is drawn again, so
        nothing keeps the old colours."""
        name = getattr(self, "appearance_name", "system")
        dark = name == "dark" or (name == "system" and
                                  QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        if getattr(self, "theme_applied", None) == ("dark" if dark else "light"):
            return
        theme = use_theme("dark" if dark else "light")
        self.theme_applied = theme["name"]
        palette = qt_palette(theme)
        QApplication.setPalette(palette)
        self.list_style.polish(palette)
        for view in (self.table, self.cats):
            view.setPalette(palette)
        self.setStyleSheet(style_sheet(theme))
        self.docs.redraw()
        self.cat_model.redraw()
        for item in self.decision.items:        # rows draw their icons once: built again on the next refresh
            item.state = None
        for item in self.auto_page.items:
            item.state = None
        self.notices.show_notices([])
        self.refresh(recheck=False)

    def recheck_waiting(self):
        """Look at the waiting documents again: the level, the selection or the model changed, or the user
        confirmed documents and a category may now hold the three it takes to be filed into."""
        self.file_automatically([d["id"] for d in self.waiting()])

    def set_auto_level(self, name):
        """The level chosen in Settings: recorded, then the waiting documents are looked at again."""
        self.org.set_auto_level(name)
        self._show_mode()
        self.recheck_waiting()
        self.refresh()

    def set_auto_scope(self):
        """ "All categories" or "Only the ones I tick", as Settings shows them now: recorded, then re-checked."""
        ticked = {b.property("category") for b in self.scope_boxes if b.isChecked()}
        self.org.set_auto_scope(ticked if self.auto_scope.currentData() == "selected" else None)
        self._show_mode()
        self.recheck_waiting()
        self.refresh()

    def _show_scope(self, cats):
        scope = self.org.auto_scope()
        self.auto_scope.setCurrentIndex(0 if scope is None else 1)
        self.auto_ticks.setVisible(scope is not None)
        shown = [(c["id"], c["name"], bool(scope) and c["id"] in scope) for c in cats]
        if shown == [(b.property("category"), b.text().replace("&&", "&"), b.isChecked()) for b in self.scope_boxes]:
            return                              # as it is: a tick in use is not rebuilt under the mouse
        holder = QWidget()
        column = box(QVBoxLayout(holder), (GROUP, 0, 0, 0))
        self.scope_boxes = []
        for cat_id, name, on in shown:
            b = QCheckBox(name.replace("&", "&&"))
            b.setProperty("category", cat_id)
            b.setChecked(on)                    # before it is connected: filling is not the user ticking
            b.toggled.connect(lambda *_: self.set_auto_scope())
            column.addWidget(b)
            self.scope_boxes.append(b)
        column.addStretch(1)
        self.auto_ticks.setWidget(holder)

    def _show_mode(self):
        """The line at the top of the window: what automatic filing does now."""
        scope = self.org.auto_scope()
        if self.org.auto_level() == "off":
            text = "Automatic filing is off"
        elif scope is None:
            text = "Filing into all categories"
        else:
            text = f"Filing into {len(scope)} selected categor{'y' if len(scope) == 1 else 'ies'}"
        if scope is None and self.org.auto_level() != "off" and self.org.auto_folders():
            text += " · new folders on"
        self.mode_label.setText(text)

    def looks_right(self, ids):
        """The user confirms what the app filed by itself: these documents become training examples."""
        n = self.org.confirm(ids)
        if n:
            self.toast.show_message(f"Confirmed {n} document{'s' if n != 1 else ''}. ClassiFile learns from "
                                    f"{'them' if n != 1 else 'it'}.")
            self.recheck_waiting()
            self.update_if_due()
        self.refresh()

    def also_docs(self, ids):
        ids = [i for i in ids if (self.org.catalog.document(i) or {"status": ""})["status"] == "filed"]
        if ids:
            what = "1 document" if len(ids) == 1 else f"{len(ids)} documents"
            self.pick_category(f"{what} also belong{'s' if len(ids) == 1 else ''} to…", "Add",
                               lambda kind, cat_id, name: self._also(ids, cat_id, name))

    def _also(self, ids, cat_id, name):
        """A second verified copy in another category; the documents' own category stays."""
        created = cat_id is None
        try:
            cat_id = cat_id or self.org.create_category(name)
        except ValueError as e:
            self.toast.show_message(str(e).capitalize())
            return

        def job():
            added, problems = 0, []
            for i in ids:
                try:
                    self.org.also(i, cat_id)
                    added += 1
                except (CopyError, ValueError) as e:
                    problems.append(str(e))
            return added, problems

        def done(result):
            self.moving -= 1
            added, problems = result if not isinstance(result, Exception) else (0, [
                f"Something went wrong while copying ({type(result).__name__}). Try again."])
            if created and not added:
                self.org.discard_unused_category(cat_id)
            cat = self.org.catalog.category(cat_id)
            text = (f"{added} document{'s' if added != 1 else ''} also in {cat['name'] if cat else name}."
                    if added else "")
            if problems:
                text += f" {len(problems)} not added. {problems[0]}"
            self.toast.show_message(text.strip(), ms=TOAST_LONG if problems else TOAST)
            self.refresh()

        self._background(job, done)

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
        if self.details.isVisible() and self.details.doc_id == doc_id:
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
        if any(d["status"] == "filed" for d in docs):
            menu.addAction("Also belongs to…", lambda: self.also_docs(ids))
            menu.addAction("Move to…", lambda: self.move_docs(ids))
        if any(d["status"] in WAITING for d in docs):
            menu.addAction("Remove from ClassiFile", lambda: self.remove_docs(ids))
        return menu

    # -- filing several documents, moving, renaming and deleting categories ----------------------------------
    def picker_choices(self):
        """What the category picker shows: [(id, name, documents)] and the recently used ids."""
        counts = self.org.catalog.category_counts()
        return ([(c["id"], c["name"], counts.get(c["id"], 0)) for c in self.org.catalog.categories()],
                self.org.catalog.recent_categories())

    def _bulk_file_clicked(self):
        ids = [i for i in self.selected_ids() if self.org.catalog.document(i)["status"] == "needs_decision"]
        if ids:
            self.pick_category(f"File {len(ids)} document{'s' if len(ids) > 1 else ''} in…", "File",
                               lambda kind, cat_id, name: self.file_docs(ids, name))

    # -- matching (decision record B4): updated only on request, versioned and checked -------------------------
    def _show_matching(self):
        m = self.org.matching_status()
        since = m["since"]
        if "version" not in m:
            text = ("ClassiFile hasn't learned your categories yet. It learns from the documents you filed, then "
                    "offers the categories that fit a new document best."
                    + (f" {since} filed document{'s are' if since != 1 else ' is'} ready to learn from." if since
                       else ""))
        else:
            text = (f"Version {m['version']}: learned from {m['documents']} documents in {m['categories']} "
                    f"categories on {short_date(m['created_at'])}. "
                    + (f"{since} document{'s' if since != 1 else ''} filed or moved since." if since
                       else "Nothing was filed or moved since."))
        self.matching_label.setText(text)
        lines = []
        for r in self.org.catalog.matcher_log():
            found = json.loads(r["check_json"]) if r["check_json"] else None
            who = "by itself" if r["trigger"] == "automatic" else "by you"
            what = {"active": "in use", "previous": "replaced"}.get(r["status"], "not kept: it did worse")
            check = (f"; on {found['documents']} documents filed since, your category first for {found['new']} "
                     f"(the version before: {found['previous']})" if found and found["documents"] else "")
            lines.append(f"Version {r['version']} · {short_date(r['created_at'])} · {who} · {r['documents']} "
                         f"documents · {what}{check}")
        self.matching_log.setText("\n".join(lines))
        self.matching_log.setVisible(bool(lines))

    def update_matching(self):
        self.matching_button.setEnabled(False)
        self.matching_button.setText("Updating…")

        def done(result):
            self.moving -= 1
            self.matching_button.setEnabled(True)
            self.matching_button.setText("Update matching")
            if isinstance(result, ValueError):
                text = str(result)
            elif isinstance(result, Exception):
                text = f"Something went wrong while updating matching ({type(result).__name__}). Try again."
            elif result["outcome"] == "up to date":
                text = "Matching is already up to date."
            else:
                found = result["check"]
                since = found and f"{found['documents']} document{'s' if found['documents'] != 1 else ''} filed since"
                if result["outcome"] == "kept previous":
                    text = (f"Kept version {result['version']}: the new one did worse on the {since} (your category "
                            f"first for {found['new']}, against {found['previous']}).")
                else:
                    text = (f"Matching updated (version {result['version']}): {result['documents']} documents in "
                            f"{result['categories']} categories."
                            + (f" On the {since}, it put your category first for {found['new']}; the previous "
                               f"version for {found['previous']}." if found and found["documents"] else ""))
            self.toast.show_message(text, ms=TOAST_LONG)
            self.recheck_waiting()              # with what it knows now
            self.refresh()

        self._background(self.org.update_matching, done)

    def update_if_due(self):
        """Learning by itself (A7, record 2.6): after every 10 confirmations or moves, matching updates in the
        background with its usual check; the previous version stays if the new one does worse."""
        if self.updating or not self.org.update_due():
            return
        self.updating = True

        def done(result):
            self.moving -= 1
            self.updating = False
            if isinstance(result, Exception) or result["outcome"] == "up to date":
                return                          # too little to learn from yet: tried again at the next one
            if result["outcome"] == "updated":
                self.update_note = (f"Matching updated by itself: version {result['version']}, learned from "
                                    f"{result['documents']} documents in {result['categories']} categories.")
            else:
                self.update_note = (f"Matching tried a new version by itself and kept version {result['version']}, "
                                    "which did better.")
            self.recheck_waiting()
            self.refresh()

        self._background(lambda: self.org.update_matching("automatic"), done)

    def _dismiss_update_note(self):
        self.update_note = None
        self.refresh()

    def retry_docs(self, ids):
        """Read documents that couldn't be read again, from their originals."""
        docs = [d for d in (self.org.catalog.document(i) for i in ids) if d and d["status"] in ("failed", "pending")]
        if docs:
            self.import_paths([d["source_path"] for d in docs])

    def _background(self, job, done):
        """Run job() off this thread, then done(result or the exception) in the window."""
        def run():
            try:
                result = job()
            except Exception as e:
                result = e
            self.bridge.job_done.emit(done, result)
        self.moving += 1
        self.pool.submit(run)

    def move_docs(self, ids):
        ids = [i for i in ids if (self.org.catalog.document(i) or {"status": ""})["status"] == "filed"]
        if ids:
            what = "1 document" if len(ids) == 1 else f"{len(ids)} documents"
            self.pick_category(f"Move {what} to…", "Move", lambda kind, cat_id, name: self._move(ids, cat_id, name))

    def _move(self, ids, cat_id, name):
        created = cat_id is None
        try:
            cat_id = cat_id or self.org.create_category(name)
        except ValueError as e:
            self.toast.show_message(str(e).capitalize())
            return
        sources = {self.org.catalog.active_primary(i)["category_id"] for i in ids} - {cat_id}

        def job():
            moved, edited, problems = [], 0, []
            for i in ids:
                try:
                    outcome = self.org.move(i, cat_id)
                except (CopyError, ValueError) as e:
                    problems.append(str(e))
                    continue
                except Exception as e:
                    problems.append(f"Something went wrong while moving ({type(e).__name__}). Try again.")
                    continue
                moved.append(i)
                edited += outcome == "edited"
            return moved, edited, problems

        def done(result):
            self.moving -= 1
            moved, edited, problems = result if not isinstance(result, Exception) else ([], 0, [
                f"Something went wrong while moving ({type(result).__name__}). Try again."])
            if created and not moved:
                self.org.discard_unused_category(cat_id)
            cat = self.org.catalog.category(cat_id)
            text = f"Moved {len(moved)} document{'s' if len(moved) != 1 else ''} to {cat['name'] if cat else name}."
            if edited:
                text += (" 1 copy was changed after filing: it stays in its old folder and is flagged." if edited == 1
                         else f" {edited} copies were changed after filing: they stay in their old folders, flagged.")
            if problems:
                text += f" {len(problems)} couldn't be moved. {problems[0]}"
            self.toast.show_message(text, ms=TOAST_LONG if edited or problems else TOAST)
            self.recheck_waiting()
            if moved:
                self.update_if_due()
            self.refresh(select_docs=[])
            counts = self.org.catalog.category_counts()
            empty = [c for c in sources if not counts.get(c)]
            if empty and self.ask_delete_empty(len(empty)):  # asked once, for all of them
                self.delete_categories(empty, quiet=True)

        self._background(job, done)

    def delete_categories(self, cat_ids, quiet=False):
        kept, deleted = [], 0
        for cat_id in cat_ids:
            try:
                folder = self.org.delete_category(cat_id)
            except ValueError:
                self.toast.show_message("This category still holds documents. Move them to another category first.")
                continue
            deleted += 1
            if folder:
                kept.append(folder)
        self._show_mode()                       # a ticked category may be gone
        if kept:
            self.toast.show_message(
                f"Deleted. Other files remain in {wrappable(kept[0])}"
                + (f" and {len(kept) - 1} more folder{'s' if len(kept) > 2 else ''}" if len(kept) > 1 else "")
                + ", so " + ("it was" if len(kept) == 1 else "they were") + " left in place.", ms=TOAST_LONG)
        elif deleted and not quiet:
            self.toast.show_message("Deleted the category." if deleted == 1 else f"Deleted {deleted} categories.")
        self.refresh()

    def rename_category(self, cat_id):
        cat = self.org.catalog.category(cat_id)
        name = " ".join(self.ask_new_name(cat["name"]).split())
        if not name or name == cat["name"]:
            return

        def done(result):
            self.moving -= 1
            if isinstance(result, Exception):
                self.toast.show_message(str(result) if isinstance(result, ValueError) else
                                        f"Something went wrong while renaming ({type(result).__name__}). Try again.",
                                        ms=TOAST_LONG)
            elif result:
                self.toast.show_message(f"Renamed to {name}. Other files remain in {wrappable(result[0])}, so that "
                                        "folder was left in place.", ms=TOAST_LONG)
            else:
                self.toast.show_message(f"Renamed to {name}.")
            self.refresh()

        self._background(lambda: self.org.rename_category(cat_id, name), done)

    def category_menu(self, cat_id):
        menu = QMenu(self)
        menu.addAction("Rename category…", lambda: self.rename_category(cat_id))
        delete = menu.addAction("Delete category", lambda: self.delete_categories([cat_id]))
        delete.setEnabled(not self.org.catalog.category_counts().get(cat_id))  # only when it holds no documents
        return menu

    def _category_menu_at(self, pos):
        cat_id = self.cats.indexAt(pos).siblingAtColumn(0).data(DOC)
        if cat_id:
            self.category_menu(cat_id).exec(self.cats.viewport().mapToGlobal(pos))

    # -- keyboard: Space = details, Enter = open or decide, Delete = remove, Esc = close, Ctrl+F = search ---
    def eventFilter(self, obj, e):
        if obj is getattr(self, "content", None) and e.type() in (QEvent.Move, QEvent.Resize):
            if self.details.isVisible() and self.details.parent() is self.workspace:
                self._place_details()
            return False
        if obj is getattr(self, "search", None) and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
            if self.search.text():      # Esc clears the search first; the next one closes details
                self.search.clear()
                return True
            return False
        if e.type() == QEvent.Resize and hasattr(self, "table") and obj is self.table.viewport():
            self._fit_columns()         # the details panel opened or closed beside the list
            return False
        if obj is getattr(self, "table", None) and e.type() == QEvent.KeyPress:
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
            if key == Qt.Key_Escape and self._escape():
                return True
        return super().eventFilter(obj, e)

    def _escape(self):
        """Esc: the full-size preview, then the search text, then the details panel. False when none was there."""
        if self.preview_overlay.isVisible():
            self.preview_overlay.hide()
        elif self.search.text():
            self.search.clear()
        elif self.details.isVisible():
            self.close_details()
        else:
            return False
        return True

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._escape()
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
        self.read_results.clear()
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
