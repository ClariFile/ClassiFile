"""Small shared widgets and the visual style of the main window."""
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key
from classifile.app import ICON_DIR
from classifile.app.preview import PdfPages, thumbnail_png
from classifile.reader import READERS

ICON_TEAL = "#0D9488"     # selection bar, selection tint, focus ring
PRIMARY = "#0F766E"       # primary buttons (white text)
PRIMARY_HOVER = "#115E59"
AMBER = "#D97706"         # waiting
RED = "#DC2626"           # errors
GREEN = "#16A34A"         # approved: filed in a category the user chose
VIOLET = "#6C47FF"        # reserved for SummarEase; unused until it exists
SUPPORTED = ", ".join(e[1:].upper() for e in READERS)
TYPE_COLOR = {".pdf": "#8E6A6A", ".pptx": "#93785A", ".docx": "#5E7392", ".odt": "#5F8570"}  # muted

# One spacing system, in logical pixels (Qt scales them with the display). Layouts and the style use only these.
PAD = 24        # main content padding
SECTION = 24    # between major sections (a heading and what follows it)
PANEL = 20      # inside panels
GROUP = 16      # between separate groups of controls
RELATED = 8     # between related controls; label to field; icon to label
ROW = 44        # document rows
CONTROL = 36    # buttons, fields and icon buttons share one height
DETAILS_WIDTH = 420     # details panel: at least this wide by default, up to DETAILS_MAX on large screens
DETAILS_MIN = 360
DETAILS_MAX = 560
READING_MAX = 1040      # settings never stretch wider than this
CHOICES_MAX = 680       # the "Choose another…" panel of a decision item
PICKER_LIST_MAX = 280   # the category picker's list scrolls beyond this height
PREVIEW_MAX = 560       # tallest details preview; the page is fitted to the panel width below this
CHEVRON_DOWN = (ICON_DIR.parent / "ui" / "chevron-down.svg").as_posix()
CHEVRON_RIGHT = (ICON_DIR.parent / "ui" / "chevron-right.svg").as_posix()
PREVIEW_MIN = 200       # the details preview never shrinks below this; the panel scrolls instead


def box(layout, margins=0, spacing=RELATED):
    """Set a layout's margins (one value or four) and spacing from the shared values; returns the layout."""
    m = (margins,) * 4 if isinstance(margins, int) else margins
    layout.setContentsMargins(*m)
    layout.setSpacing(spacing)
    return layout

STYLE = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 14px; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#secondary, QLabel#processing {{ font-size: 13px; color: palette(placeholder-text); }}
QLabel#section {{ font-size: 12px; font-weight: 600; color: palette(placeholder-text); letter-spacing: 1px; }}
QLabel#brand {{ font-size: 16px; font-weight: 600; }}
QPushButton {{ border: 1px solid rgba(127, 127, 127, 110); border-radius: 6px; background: transparent;
               padding: {RELATED - 1}px {GROUP - 1}px; min-height: 20px; max-height: 20px; }}
QPushButton:hover, QToolButton#more:hover {{ background: rgba(127, 127, 127, 40); }}
QPushButton:checked {{ background: rgba(13, 148, 136, 46); border-color: {ICON_TEAL}; }}
QPushButton:disabled {{ color: palette(placeholder-text); }}
QPushButton#primary {{ background: {PRIMARY}; color: white; border-color: {PRIMARY}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {PRIMARY_HOVER}; border-color: {PRIMARY_HOVER}; }}
QPushButton#primary:disabled {{ background: palette(mid); color: palette(window); border-color: palette(mid); }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#link, QToolButton#link {{ border-color: transparent; color: palette(text);
                                      text-decoration: underline; padding: {RELATED - 1}px {RELATED - 1}px; }}
QToolButton#disclosure {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
                          font-weight: 600; padding: {RELATED - 1}px 0; }}
QToolButton#more {{ border: 1px solid rgba(127, 127, 127, 110); border-radius: 6px; font-size: 20px;
                    font-weight: 700; padding: 0; min-width: {CONTROL - 2}px; max-width: {CONTROL - 2}px;
                    min-height: {CONTROL - 2}px; max-height: {CONTROL - 2}px; }}
QPushButton#icon {{ border-color: transparent; padding: {RELATED - 1}px 0; min-width: {CONTROL - 2}px;
                    max-width: {CONTROL - 2}px; }}
/* Focus changes only the border colour: every control keeps its size. */
QPushButton:focus, QPushButton#link:focus, QPushButton#icon:focus, QToolButton#more:focus,
QToolButton#disclosure:focus, QLineEdit:focus, QComboBox:focus {{ outline: none; border-color: {ICON_TEAL}; }}
QPushButton#primary:focus {{ border-color: palette(text); }}
QPushButton#nav {{ text-align: left; border: none; background: transparent; padding: 10px {GROUP - 3}px;
                   border-left: 3px solid transparent; border-radius: 0; max-height: none; }}
QLabel#count {{ font-size: 13px; color: palette(placeholder-text); }}
QPushButton#nav:checked {{ background: rgba(13, 148, 136, 40); border-left: 3px solid {ICON_TEAL}; }}
QPushButton#nav:hover {{ background: rgba(127, 127, 127, 30); }}
QTreeView, QListWidget {{ border: none; background: transparent; outline: none; }}
QTreeView::item {{ min-height: {ROW - 2}px; border-bottom: 1px solid rgba(127, 127, 127, 40);
                     padding-left: {RELATED}px; }}
QTreeView#categories::item {{ min-height: 32px; border-bottom: none; border-left: 3px solid transparent;
                              padding-left: {GROUP - 6}px; padding-right: {GROUP - 4}px; }}
QListWidget::item {{ padding: 6px {RELATED}px; border-radius: 4px; }}
QListWidget::item:hover {{ background: rgba(127, 127, 127, 30); }}
QFrame#choices {{ border: 1px solid rgba(127, 127, 127, 60); border-radius: 8px; background: rgba(127, 127, 127, 18); }}
QTreeView::item:selected, QListWidget::item:selected {{ background: rgba(13, 148, 136, 46);
    color: palette(text); }}
QListWidget::item:selected, QTreeView#categories::item:selected:first, QTreeView::item:selected:first {{
    border-left: 3px solid {ICON_TEAL}; }}
QTreeView::branch:selected {{ background: transparent; }}
QHeaderView::section {{ background: transparent; border: none; border-bottom: 1px solid rgba(127, 127, 127, 60);
                        padding: {RELATED}px {RELATED}px; font-size: 12px; font-weight: 600;
                        color: palette(placeholder-text); }}
QLineEdit, QComboBox {{ border: 1px solid rgba(127, 127, 127, 90); border-radius: 6px; padding: 7px {RELATED}px;
                        min-height: 20px; background: palette(base); }}
QComboBox {{ padding-left: 12px; padding-right: {CONTROL}px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: {CONTROL - RELATED}px;
                        border: none; }}
QComboBox::down-arrow {{ image: url({CHEVRON_DOWN}); width: 16px; height: 16px; }}
QComboBox QAbstractItemView {{ background: palette(base); color: palette(text); border: 1px solid rgba(127, 127, 127, 90);
                               border-radius: 6px; padding: 4px; outline: none;
                               selection-background-color: rgba(13, 148, 136, 46); selection-color: palette(text); }}
QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 {RELATED}px; border-radius: 4px; }}
QLineEdit[filled="true"] {{ border: 1px solid {ICON_TEAL}; font-weight: 600; }}
QFrame#notice {{ border-radius: 6px; background: rgba(127, 127, 127, 28); }}
QFrame#notice QLabel {{ font-size: 15px; }}
QFrame#toast {{ border-radius: 6px; background: palette(text); }}
QFrame#toast QLabel {{ color: palette(window); font-size: 14px; }}
QFrame#toast QPushButton {{ color: palette(window); border: 1px solid palette(window); background: transparent; }}
QFrame#bulk {{ border-radius: 6px; background: rgba(13, 148, 136, 30); }}
QFrame#decision {{ border-bottom: 1px solid rgba(127, 127, 127, 60); }}
QFrame#details {{ border-left: 1px solid rgba(127, 127, 127, 60); background: palette(window); }}
QFrame#sidebar {{ border-right: 1px solid rgba(127, 127, 127, 60); }}
QLabel#card {{ background: palette(base); border-radius: 6px; padding: {GROUP}px; }}
QLabel#warning {{ color: {AMBER}; }}
QLabel#error {{ color: {RED}; }}
QLabel#tagNew, QLabel#tagExisting {{ border-radius: 10px; padding: 1px {RELATED}px; font-size: 12px;
                                     min-height: 18px; max-height: 18px; }}
QLabel#tagNew {{ color: {AMBER}; border: 1px solid {AMBER}; }}
QLabel#tagExisting {{ color: {ICON_TEAL}; border: 1px solid {ICON_TEAL}; }}
QFrame#dropOverlay {{ background: #111827; border: 3px dashed {ICON_TEAL}; border-radius: 12px; }}
QFrame#dropOverlay QLabel {{ color: white; }}
QFrame#previewOverlay {{ background: #111827; }}
QFrame#previewOverlay QLabel {{ color: white; }}
"""


def restyle(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def wrappable(path):
    """A path with invisible break points after each separator, so long paths wrap instead of widening a window."""
    return str(path).replace("\\", "\\​").replace("/", "/​")


_ICONS = {}


def format_icon(file_name):
    """A 16 px page glyph in a muted colour per format."""
    ext = Path(file_name).suffix.lower()
    if ext not in _ICONS:
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        colour = QColor(TYPE_COLOR.get(ext, "#6B7280"))
        p.setPen(QPen(colour, 1.4))
        p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 50))
        p.drawPolygon([QPointF(3, 1.5), QPointF(10, 1.5), QPointF(13.5, 5), QPointF(13.5, 14.5), QPointF(3, 14.5)])
        p.drawLine(QPointF(5.5, 8), QPointF(11, 8))
        p.drawLine(QPointF(5.5, 11), QPointF(11, 11))
        p.end()
        _ICONS[ext] = QIcon(pix)
    return _ICONS[ext]


STATUS = {  # an icon plus a word, never colour alone
    # ponytail: every filed document was filed by the user's own choice so far. When automatic filing arrives
    # (CP4), take this word from the membership's provenance: machine-assigned is not approved.
    "filed": ("Approved", GREEN, "check"),
    "needs_decision": ("Waiting", AMBER, "dot"),
    "queued": ("Reading", "#9CA3AF", "ring"),
    "reading": ("Reading", "#9CA3AF", "ring"),
    "filing": ("Filing", "#9CA3AF", "ring"),
    "failed": ("Failed", RED, "alert"),
    "pending": ("Failed", RED, "alert"),
}


def status_icon(status):
    key = ("status", status)
    if key not in _ICONS:
        _, colour, shape = STATUS.get(status, ("", "#9CA3AF", "ring"))
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(colour)
        if shape == "dot":
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QRectF(4, 4, 8, 8))
        elif shape == "ring":
            p.setPen(QPen(c, 1.6))
            p.drawEllipse(QRectF(3.5, 3.5, 9, 9))
        elif shape == "check":
            p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(3.5, 8.5), QPointF(6.8, 11.5), QPointF(12.5, 4.5)])
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawPolygon([QPointF(8, 2), QPointF(14.5, 14), QPointF(1.5, 14)])
            p.setPen(QPen(QColor("white"), 1.6))
            p.drawLine(QPointF(8, 6.5), QPointF(8, 10))
            p.drawPoint(QPointF(8, 12.2))
        p.end()
        _ICONS[key] = QIcon(pix)
    return _ICONS[key]


def status_word(status):
    return STATUS.get(status, ("",))[0]


class ElidedLabel(QLabel):
    """One line that ends in "…" when it doesn't fit; the full text shows on hover."""

    def __init__(self, text="", object_name=None):
        super().__init__()
        self.full = ""
        if object_name:
            self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):
        self.full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        QLabel.setText(self, self.fontMetrics().elidedText(self.full, Qt.ElideRight, max(20, self.width())))


class Collapsible(QWidget):
    """A section that starts collapsed: a header button and its content."""

    def __init__(self, title, content):
        super().__init__()
        self.title = title
        self.toggle = QToolButton()
        self.toggle.setObjectName("disclosure")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setIcon(QIcon(CHEVRON_RIGHT))
        self.toggle.setIconSize(QSize(16, 16))
        self.toggle.setText(title)
        self.toggle.toggled.connect(self.set_open)
        self.content = content
        content.hide()
        v = box(QVBoxLayout(self), spacing=0)
        v.addWidget(self.toggle, 0, Qt.AlignLeft)
        v.addWidget(content)

    def set_open(self, open_):
        self.toggle.setIcon(QIcon(CHEVRON_DOWN if open_ else CHEVRON_RIGHT))
        self.content.setVisible(open_)


class Notices(QWidget):
    """The one notice area at the top of the workspace: an icon, one plain sentence and an action."""

    def __init__(self):
        super().__init__()
        self.box = box(QVBoxLayout(self))
        self.items = []

    def show_notices(self, notices):
        """notices: [(kind "error" | "warning" | "info", text, action label or None, callback)]."""
        if [n[:3] for n in notices] == self.items and self.box.count() == len(notices):
            return self.setVisible(bool(notices))   # the same notices: nothing is rebuilt
        while self.box.count():
            old = self.box.takeAt(0).widget()
            old.hide()  # hidden at once; deleting happens later and must not leave it overlapping
            old.deleteLater()
        self.items = []
        for kind, text, action, callback in notices:
            frame = QFrame()
            frame.setObjectName("notice")
            h = box(QHBoxLayout(frame), (GROUP, RELATED, RELATED, RELATED), GROUP)
            icon = QLabel()
            icon.setPixmap(status_icon("failed" if kind == "error" else "needs_decision").pixmap(20, 20))
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("error" if kind == "error" else "")
            frame.setParent(self)
            label.setParent(frame)
            label.ensurePolished()                  # measure with the notice font, not the default
            label.setMaximumWidth(label.fontMetrics().horizontalAdvance(text) + GROUP)  # wraps only when short
            h.addWidget(icon)
            h.addSpacing(RELATED - GROUP)       # icon to label
            h.addWidget(label, 1)
            if action:
                button = QPushButton(action)
                button.clicked.connect(callback)
                h.addWidget(button)
            h.addStretch(1)
            self.box.addWidget(frame)
            self.items.append((kind, text, action))
        self.setVisible(bool(notices))


class Toast(QFrame):
    """A short success message at the bottom right, with an optional action."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.label = QLabel()
        self.action = QPushButton()
        self.action.hide()
        h = box(QHBoxLayout(self), (GROUP, RELATED, RELATED, RELATED), GROUP)
        h.addWidget(self.label)
        h.addWidget(self.action)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self._callback = None
        self.action.clicked.connect(lambda: self._callback and self._callback())
        self.slide = QPropertyAnimation(self, b"pos", self)
        self.slide.setDuration(200)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.hide()

    def show_message(self, text, action=None, callback=None, ms=5000):
        self.label.setText(text)
        self._callback = callback
        self.action.setText(action or "")
        self.action.setVisible(bool(action))
        self.adjustSize()
        self.slide.stop()
        self.place()
        if self.isHidden():  # up from below the window's bottom edge, in the right corner
            self.slide.setStartValue(QPoint(self.x(), self.parent().height()))
            self.slide.setEndValue(self.pos())
            self.slide.start()
        self.raise_()
        self.show()
        self.timer.start(ms)

    def place(self):
        parent = self.parent().rect()
        self.move(parent.right() - self.width() - 24, parent.bottom() - self.height() - 24)


class CategoryPicker(QWidget):
    """The one way to choose a category (filing, Move to…, several documents at once): a search field over the
    existing categories, each with its document count, recently used ones first and the rest alphabetically;
    suggested names as "New: …" rows; and a separate last row that creates the typed name, shown only when
    nothing matches it exactly. Typing alone never creates a category. Up/Down, Enter and Esc work."""

    changed = Signal()    # the chosen row changed
    activated = Signal()  # Enter, or a double click on a row
    cancelled = Signal()  # Esc
    PROMPT = "Search categories, or type a new name"

    def __init__(self):
        super().__init__()
        self.field = QLineEdit()
        self.field.setPlaceholderText(self.PROMPT)
        self.field.setClearButtonEnabled(True)
        self.field.textChanged.connect(lambda *_: self._fill())
        self.list = QListWidget()               # as tall as its rows up to a limit, then it scrolls
        self.list.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.list.setMinimumWidth(200)          # a long name ends in "…" (hover shows it) and never widens the page
        self.list.setMaximumHeight(PICKER_LIST_MAX)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(lambda *_: self.changed.emit())
        self.list.itemDoubleClicked.connect(lambda *_: self.activated.emit())
        for w in (self.field, self.list):
            w.installEventFilter(self)
        self.empty = QLabel("No categories yet. Type a name to create the first one.")
        self.empty.setObjectName("secondary")
        self._categories, self._suggestions, self._rows = [], [], []
        v = box(QVBoxLayout(self))
        for w in (self.field, self.list, self.empty):
            v.addWidget(w)
        self._fill()

    def set_choices(self, categories, recent=(), suggestions=()):
        """categories: [(id, name, documents)]; recent: ids, latest first; suggestions: [(name, where found)],
        offered as new categories unless a category of that name exists."""
        by_id = {c[0]: c for c in categories}
        first = [by_id[i] for i in recent if i in by_id]
        self._categories = first + sorted((c for c in categories if c not in first), key=lambda c: c[1].casefold())
        taken = {name_key(c[1]) for c in categories}
        self._suggestions = [s for s in suggestions if name_key(s[0]) not in taken]
        self._fill()

    def current(self):
        """("existing", category id, name) | ("new", None, name) | None."""
        row = self.list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _fill(self):
        keep = self.current()
        text = " ".join(self.field.text().split())
        q = text.casefold()
        rows = [(f"{name} · {count}", ("existing", cat_id, name)) for cat_id, name, count in self._categories
                if q in name.casefold()]
        rows += [(f"New: {name}" + (f"\n    {found}" if found else ""), ("new", None, name))
                 for name, found in self._suggestions if q in name.casefold()]
        known = {name_key(c[1]) for c in self._categories} | {name_key(s[0]) for s in self._suggestions}
        if text and name_key(text) not in known:
            rows.append((f"Create category '{text}'", ("new", None, text)))
        self.list.blockSignals(True)
        self.list.clear()
        for label, choice in rows:
            item = QListWidgetItem(label)
            item.setToolTip(choice[2])
            self.list.addItem(item)
        self._rows = [choice for _, choice in rows]
        # What was chosen stays chosen. Otherwise typing picks the first existing category, never a row that creates.
        self.list.setCurrentRow(self._rows.index(keep) if keep in self._rows else next(
            (i for i, r in enumerate(self._rows) if q and r[0] == "existing"), -1))
        self.list.blockSignals(False)
        self.list.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        self.changed.emit()

    def eventFilter(self, obj, e):
        if e.type() == QEvent.KeyPress:
            key = e.key()
            if key in (Qt.Key_Down, Qt.Key_Up) and obj is self.field and self._rows:
                step = 1 if key == Qt.Key_Down else -1
                self.list.setCurrentRow(max(0, min(len(self._rows) - 1, self.list.currentRow() + step)))
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self.current():
                    self.activated.emit()
                return True
            if key == Qt.Key_Escape:
                self.cancelled.emit()
                return True
        return super().eventFilter(obj, e)


class PickerDialog(QDialog):
    """The category picker in a small window: Move to… and filing several documents at once."""

    def __init__(self, parent, title, verb, on_choice):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.verb, self.on_choice = verb, on_choice
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.picker = CategoryPicker()
        self.confirm = QPushButton(verb)
        self.confirm.setObjectName("primary")
        self.confirm.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        for b in (self.confirm, cancel):
            b.setAutoDefault(False)             # Enter belongs to the picker
        buttons = box(QHBoxLayout())
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.confirm)
        v = box(QVBoxLayout(self), PANEL, GROUP)
        v.addWidget(heading)
        v.addWidget(self.picker)
        v.addStretch(1)
        v.addLayout(buttons)
        self.picker.changed.connect(self._update)
        self.picker.activated.connect(self._accept)
        self.picker.cancelled.connect(self.reject)
        self._update()

    def _update(self):
        choice = self.picker.current()
        self.confirm.setEnabled(bool(choice))
        self.confirm.setText(f"Create && {self.verb.lower()}" if choice and choice[0] == "new" else self.verb)

    def _accept(self):
        choice = self.picker.current()
        if choice:
            self.accept()
            self.on_choice(*choice)


class DropOverlay(QFrame):
    """Covers the window while files are dragged over it."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("dropOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.title = QLabel("Drop files here to import")
        self.title.setStyleSheet("font-size: 32px; font-weight: 600;")
        self.formats = QLabel(f"Supported: {SUPPORTED}")
        self.formats.setStyleSheet("font-size: 16px;")
        self.skipped = QLabel()
        self.skipped.setStyleSheet("font-size: 15px;")
        self.skipped.setWordWrap(True)
        v = QVBoxLayout(self)
        v.addStretch(1)
        for w in (self.title, self.formats, self.skipped):
            w.setAlignment(Qt.AlignCenter)
            v.addWidget(w)
        v.addStretch(1)
        self.hide()

    def show_for(self, paths):
        skipped = [Path(p).name or str(p) for p in paths if Path(p).suffix.lower() not in READERS or Path(p).is_dir()]
        self.skipped.setText(("Will be skipped (not a supported file): " + ", ".join(skipped)) if skipped else "")
        self.skipped.setVisible(bool(skipped))
        self.setGeometry(self.parent().rect().adjusted(16, 16, -16, -16))
        self.raise_()
        self.show()


class Preview(QWidget):
    """A page preview: PDF pages fitted to the width with page navigation, else the stored thumbnail or a card of
    the first lines. Page images only; no text views and no other programs."""

    expand_requested = Signal()

    def __init__(self, expandable=True, fit_width=False):
        super().__init__()
        self.pdf, self.page, self.source = None, 0, None
        self.fit_width = fit_width
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setWordWrap(True)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.image)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.prev = QPushButton("‹")
        self.prev.setObjectName("icon")
        self.prev.setToolTip("Previous page")
        self.prev.clicked.connect(lambda: self.show_page(self.page - 1))
        self.next = QPushButton("›")
        self.next.setObjectName("icon")
        self.next.setToolTip("Next page")
        self.next.clicked.connect(lambda: self.show_page(self.page + 1))
        self.page_label = QLabel()
        self.page_label.setObjectName("secondary")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.expand = QPushButton("Expand")
        self.expand.clicked.connect(self.expand_requested)
        if not expandable:                      # hide(), never show(): shown without a parent it is a window
            self.expand.hide()
        self.note = QLabel()
        self.note.setObjectName("secondary")
        self.note.setWordWrap(True)
        nav = box(QHBoxLayout())
        nav.addStretch(1)
        nav.addWidget(self.prev)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next)
        nav.addStretch(1)
        nav.addWidget(self.expand)
        self.nav = QWidget()
        self.nav.setLayout(nav)
        v = box(QVBoxLayout(self))
        v.addWidget(self.scroll, 1)
        v.addWidget(self.nav)
        v.addWidget(self.note)

    def close_pdf(self):
        if self.pdf:
            self.pdf.close()
        self.pdf = None

    def show_document(self, source, first_lines, note=""):
        """source: the file to preview (the filed copy, or the original). first_lines: for the card."""
        if source == self.source and self.pdf:
            return self.show_page(self.page)
        self.close_pdf()
        self.source, self.page = source, 0
        self.image.setPixmap(QPixmap())
        self.image.setObjectName("")
        self.note.setText(note)
        if source is None or not Path(source).exists():
            self.image.setText(f"The original file is no longer at {wrappable(source)}." if source else "")
            self.nav.hide()
            return
        if Path(source).suffix.lower() == ".pdf":
            try:
                self.pdf = PdfPages(source)
            except Exception:
                self.image.setText("This PDF can't be previewed.")
                self.nav.hide()
                return
            self.show_page(0)
            return
        png = thumbnail_png(source)
        self.nav.setVisible(self.expand.isVisible())
        self.prev.hide()
        self.next.hide()
        self.page_label.setText("")
        if png:
            self._set(png)
        else:  # no stored thumbnail and no other programs: the first lines as a card
            self.image.setObjectName("card")
            self.image.setText("\n".join(first_lines[:10]) or "No preview")
            restyle(self.image)

    def show_page(self, index):
        if not self.pdf:
            return
        self.page = max(0, min(self.pdf.count - 1, index))
        width = max(200, self.scroll.viewport().width() - 8)
        self._set(self.pdf.png(self.page, width))
        self.page_label.setText(f"Page {self.page + 1} of {self.pdf.count}")
        self.prev.show()
        self.next.show()
        self.prev.setEnabled(self.page > 0)
        self.next.setEnabled(self.page < self.pdf.count - 1)
        self.nav.show()

    def _set(self, png):
        pix = QPixmap()
        pix.loadFromData(png)
        area = self.scroll.viewport().size()  # the whole page fits: no scrolling inside the preview
        width = max(40, area.width() - RELATED)
        height = PREVIEW_MAX if self.fit_width else max(40, area.height() - RELATED)
        fits = pix.width() <= width and pix.height() <= height
        pix = pix if fits else pix.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image.setPixmap(pix)
        if self.fit_width:  # no empty bands above and below the page
            self.scroll.setFixedHeight(pix.height() + RELATED)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.pdf:
            self.show_page(self.page)

    def showEvent(self, e):
        super().showEvent(e)
        if self.pdf:  # sized while hidden: fit again now that the real size is known
            self.show_page(self.page)


class PreviewOverlay(QFrame):
    """A large preview over the whole window; Esc or Close returns."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("previewOverlay")
        self.title = ElidedLabel()
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        close = QPushButton("Close (Esc)")
        close.clicked.connect(self.hide)
        head = QHBoxLayout()
        head.addWidget(self.title, 1)
        head.addWidget(close)
        self.preview = Preview(expandable=False)
        v = box(QVBoxLayout(self), (PAD, GROUP, PAD, GROUP), GROUP)
        v.addLayout(head)
        v.addWidget(self.preview, 1)
        self.hide()

    def open(self, name, source, first_lines, page=0):
        self.title.setText(name)
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self.preview.source = None
        self.preview.show_document(source, first_lines)
        self.preview.show_page(page)
        self.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        elif e.key() in (Qt.Key_PageDown, Qt.Key_Right):
            self.preview.show_page(self.preview.page + 1)
        elif e.key() in (Qt.Key_PageUp, Qt.Key_Left):
            self.preview.show_page(self.preview.page - 1)
        else:
            super().keyPressEvent(e)

    def hideEvent(self, e):
        self.preview.close_pdf()
        super().hideEvent(e)
