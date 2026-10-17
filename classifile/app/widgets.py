"""Small shared widgets and the visual style of the main window."""
import sys
import zlib
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

QWIDGETSIZE_MAX = (1 << 24) - 1

from classifile.analysis.candidates import name_key
from classifile.app import ICON_DIR
from classifile.app.preview import PdfPages, thumbnail_png
from classifile.app.tokens import *  # noqa: F401,F403  every size, colour and duration; also passed on to importers
from classifile.reader import READERS

SUPPORTED = ", ".join(e[1:].upper() for e in READERS)
CHEVRON_DOWN = (ICON_DIR.parent / "ui" / "chevron-down.svg").as_posix()
CHEVRON_RIGHT = (ICON_DIR.parent / "ui" / "chevron-right.svg").as_posix()


def box(layout, margins=0, spacing=RELATED):
    """Set a layout's margins (one value or four) and spacing from the shared values; returns the layout."""
    m = (margins,) * 4 if isinstance(margins, int) else margins
    layout.setContentsMargins(*m)
    layout.setSpacing(spacing)
    return layout

THEME = dict(THEMES["light"], name="light")    # the theme in use; use_theme() changes it in place


def style_sheet(t):
    """The window's style sheet for a theme (a THEMES entry): every colour comes from it, none from the system."""
    return f"""
QWidget {{ font-family: "{FONT}"; font-size: {TEXT_BODY}px; color: {t['text']}; accent-color: {t['tick']}; }}
QLabel#pageTitle, QLabel#hero {{ font-size: {TEXT_TITLE}px; font-weight: {WEIGHT_STRONG}; }}
QLabel#heading {{ font-size: {TEXT_HEADING}px; font-weight: {WEIGHT_STRONG}; }}
QLabel#lead {{ font-size: {TEXT_HEADING}px; }}
QLabel#strong {{ font-weight: {WEIGHT_STRONG}; }}
QLabel#secondary, QLabel#processing {{ font-size: {TEXT_SECONDARY}px; color: {t['secondary']}; }}
QLabel#section {{ font-size: {TEXT_CAPTION}px; font-weight: {WEIGHT_STRONG}; color: {t['secondary']};
                 letter-spacing: {SPACED}px; }}
QLabel#brand {{ font-size: {TEXT_HEADING}px; font-weight: {WEIGHT_STRONG}; }}
QPushButton {{ border: {HAIR}px solid {t['control']}; border-radius: {RADIUS_CONTROL}px; background: transparent;
               color: {t['text']}; padding: {RELATED - HAIR}px {GROUP - HAIR}px; min-height: {CONTROL_TEXT}px;
               max-height: {CONTROL_TEXT}px; }}
QPushButton:hover, QToolButton#more:hover {{ background: {t['hover']}; }}
QPushButton:checked {{ background: {t['pressed']}; }}
QPushButton:disabled {{ color: {t['disabled']}; }}
QPushButton#primary {{ background: {t['primary']}; color: {t['on_primary']}; border-color: {t['primary']};
                       font-weight: {WEIGHT_STRONG}; }}
QPushButton#primary:hover {{ background: {t['primary_hover']}; border-color: {t['primary_hover']}; }}
QPushButton#primary:disabled {{ background: {t['disabled_fill']}; color: {t['disabled']};
                                border-color: {t['disabled_fill']}; }}
QToolButton {{ color: {t['text']}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#link, QToolButton#link {{ border-color: transparent; color: {t['text']};
                                      text-decoration: underline; padding: {RELATED - HAIR}px {RELATED - HAIR}px; }}
QToolButton#disclosure {{ background: transparent; border: {HAIR}px solid transparent;
                          border-radius: {RADIUS_CONTROL}px; font-weight: {WEIGHT_STRONG};
                          padding: {RELATED - HAIR}px 0; }}
QToolButton#more {{ border: {HAIR}px solid transparent; border-radius: {RADIUS_CONTROL}px;
                    font-size: {TEXT_HEADING}px; font-weight: {WEIGHT_STRONG}; padding: 0;
                    min-width: {CONTROL - 2 * HAIR}px; max-width: {CONTROL - 2 * HAIR}px;
                    min-height: {CONTROL - 2 * HAIR}px; max-height: {CONTROL - 2 * HAIR}px; }}
QPushButton#icon {{ border-color: transparent; padding: {RELATED - HAIR}px 0; min-width: {CONTROL - 2 * HAIR}px;
                    max-width: {CONTROL - 2 * HAIR}px; }}
QPushButton#quiet {{ border-color: transparent; }}
QPushButton#quiet:checked, QPushButton#accent {{ border-color: {t['control']}; }}
QPushButton#accent {{ font-weight: {WEIGHT_STRONG}; }}
/* Focus changes only the border colour: every control keeps its size. */
QPushButton:focus, QPushButton#link:focus, QPushButton#icon:focus, QPushButton#quiet:focus, QToolButton#more:focus,
QToolButton#disclosure:focus, QLineEdit:focus, QComboBox:focus {{ outline: none; border-color: {t['accent']}; }}
QPushButton#accent:focus {{ border-color: {t['text']}; }}
QPushButton#primary:focus {{ border-color: {t['text']}; }}
QPushButton#nav {{ text-align: left; border: none; background: transparent; color: {t['text']};
                   padding: {NAV_PAD}px {GROUP - BAR}px; border-left: {BAR}px solid transparent; border-radius: 0;
                   max-height: none; }}
QLabel#count {{ font-size: {TEXT_SECONDARY}px; color: {t['secondary']}; }}
QPushButton#nav:checked {{ background: {t['nav']}; border-left: {BAR}px solid {t['accent']}; }}
QPushButton#nav[prominent="true"] {{ border: {HAIR}px solid {t['control']}; border-radius: {RADIUS_CONTROL}px;
                                     margin: 0 {GROUP - TIGHT}px; padding-left: {GROUP - TIGHT}px;
                                     font-weight: {WEIGHT_STRONG}; background: {t['base']}; }}
QPushButton#nav[prominent="true"]:checked {{ background: {t['nav']}; border-left: {BAR}px solid {t['accent']}; }}
QPushButton#nav[prominent="true"]:hover {{ background: {t['hover']}; }}
QFrame#settingsCard {{ background: {t['base']}; border: {HAIR}px solid {t['divider']};
                       border-radius: {RADIUS_PANEL}px; }}
QPushButton#nav:hover {{ background: {t['hover']}; }}
QPushButton#nav:focus {{ background: {t['hover']}; }}
/* The lists keep a border of one colour or none, so focus is seen and nothing moves. */
QTreeView, QListWidget {{ border: {HAIR}px solid transparent; border-radius: {RADIUS_ROW}px;
                          background: {t['base']}; color: {t['text']}; outline: none; }}
QTreeView#categories {{ background: transparent; }}
QTreeView:focus, QListWidget:focus {{ border-color: {t['accent']}; }}
QTreeView::item {{ min-height: {ROW - 2 * HAIR}px; border-bottom: {HAIR}px solid {t['divider']};
                     padding-left: {RELATED}px; color: {t['text']}; }}
QTreeView::item:hover, QListWidget::item:hover {{ background: {t['hover']}; }}
QTreeView#categories::item {{ min-height: {CATEGORY_ROW}px; border-bottom: none;
                              border-left: {BAR}px solid transparent; padding-left: {NAV_PAD}px;
                              padding-right: {GROUP - TIGHT}px; }}
QListWidget::item {{ padding: {RELATED - 2 * HAIR}px {RELATED}px; border-radius: {RADIUS_ROW}px; color: {t['text']}; }}
QFrame#choices {{ border: {HAIR}px solid {t['divider']}; border-radius: {RADIUS_PANEL}px; background: {t['inset']}; }}
QTreeView::item:selected, QListWidget::item:selected {{ background: {t['selection']}; color: {t['text']}; }}
QListWidget::item:selected, QTreeView#categories::item:selected:first, QTreeView::item:selected:first {{
    border-left: {BAR}px solid {t['accent']}; }}
QTreeView::branch:selected {{ background: transparent; }}
QHeaderView, QHeaderView::section {{ background: {t['base']}; }}
QHeaderView::section {{ border: none; border-bottom: {HAIR}px solid {t['divider']};
                        padding: {RELATED}px {RELATED}px; font-size: {TEXT_CAPTION}px;
                        font-weight: {WEIGHT_STRONG}; color: {t['secondary']}; }}
QLineEdit, QComboBox {{ border: {HAIR}px solid {t['control']}; border-radius: {RADIUS_CONTROL}px;
                        padding: {RELATED - HAIR}px {RELATED}px; min-height: {CONTROL_TEXT}px;
                        background: {t['base']}; color: {t['text']};
                        selection-background-color: {t['selection']}; selection-color: {t['text']}; }}
QComboBox {{ padding-left: {GROUP - TIGHT}px; padding-right: {CONTROL}px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: {CONTROL - RELATED}px;
                        border: none; }}
QComboBox::down-arrow {{ image: url({CHEVRON_DOWN}); width: {ICON}px; height: {ICON}px; }}
QComboBox QAbstractItemView {{ background: {t['raised']}; color: {t['text']};
                               border: {HAIR}px solid {t['control']}; border-radius: {RADIUS_CONTROL}px;
                               padding: {TIGHT}px; outline: none; selection-background-color: {t['hover']};
                               selection-color: {t['text']}; }}
QComboBox QAbstractItemView::item {{ min-height: {CATEGORY_ROW}px; padding: 0 {RELATED}px;
                                     border-radius: {RADIUS_ROW}px; }}
QMenu {{ background: {t['raised']}; color: {t['text']}; border: {HAIR}px solid {t['control']}; padding: {TIGHT}px; }}
QMenu::item {{ padding: {RELATED - HAIR}px {GROUP}px; border-radius: {RADIUS_ROW}px; }}
QMenu::item:selected {{ background: {t['hover']}; color: {t['text']}; }}   /* under the mouse: a hover */
QMenu::item:disabled {{ color: {t['disabled']}; }}
QToolTip {{ background: {t['raised']}; color: {t['text']}; border: {HAIR}px solid {t['control']}; }}
QCheckBox, QRadioButton {{ color: {t['text']}; }}
QLineEdit[filled="true"] {{ font-weight: {WEIGHT_STRONG}; }}
QFrame#notice {{ border-radius: {RADIUS_CONTROL}px; background: {t['notice']}; }}
QFrame#toast {{ border-radius: {RADIUS_CONTROL}px; background: {t['toast']}; }}
QFrame#toast QLabel {{ color: {t['on_toast']}; }}
QFrame#toast QPushButton {{ color: {t['on_toast']}; border: {HAIR}px solid {t['on_toast']};
                            background: transparent; }}
QFrame#bulk {{ border-radius: {RADIUS_CONTROL}px; background: {t['bulk']}; }}
/* Rows of the decision and auto-filed lists: the list colour; hover is the hover colour;
   the inspected row has the selection tint and bar; a focused row has the bar alone. The bar is always there
   (transparent), so nothing moves. */
QFrame#row {{ border: none; border-bottom: {HAIR}px solid {t['divider']}; border-left: {BAR}px solid transparent;
              background: {t['base']}; }}
QFrame#row:hover {{ background: {t['hover']}; }}
QFrame#row:focus {{ border-left-color: {t['accent']}; }}
QFrame#row[inspected="true"] {{ background: {t['selection']}; border-left-color: {t['accent']}; }}
QScrollArea, QWidget#qt_scrollarea_viewport, QWidget#qt_scrollarea_viewport > QWidget {{ background: transparent; }}
/* scroll areas and what they hold show the surface they sit on */
QFrame#details {{ border-left: {HAIR}px solid {t['divider']}; background: {t['raised']}; }}
QFrame#sidebar {{ border-right: {HAIR}px solid {t['divider']}; background: {t['sidebar']}; }}
QLabel#card {{ background: {t['base']}; border-radius: {RADIUS_CONTROL}px; padding: {GROUP}px; }}
QLabel#warning {{ color: {t['amber']}; }}
QLabel#error {{ color: {t['red']}; }}
QLabel#tagNew, QLabel#tagExisting {{ border-radius: {RADIUS_TAG}px; padding: {HAIR}px {RELATED}px;
                                     font-size: {TEXT_CAPTION}px; min-height: {TAG}px; max-height: {TAG}px; }}
QLabel#tagNew {{ color: {t['amber']}; border: {HAIR}px solid {t['control']}; }}
QLabel#tagExisting {{ color: {t['secondary']}; border: {HAIR}px solid {t['control']}; }}
QFrame#dropOverlay {{ background: {OVERLAY}; border: {BAR}px dashed {OVERLAY_LINE}; border-radius: {RADIUS_PANEL}px; }}
QFrame#dropOverlay QLabel {{ color: {WHITE}; }}
QFrame#previewOverlay {{ background: {OVERLAY}; }}
QFrame#previewOverlay QLabel {{ color: {WHITE}; }}
"""


STYLE = style_sheet(THEMES["light"])   # for the tools' own windows; the main window follows the theme in use

PALETTE_ROLES = {   # what the Qt palette (and so the Fusion lists and native controls) takes from a theme
    QPalette.Window: "window", QPalette.WindowText: "text", QPalette.Base: "base", QPalette.AlternateBase: "hover",
    QPalette.Text: "text", QPalette.Button: "raised", QPalette.ButtonText: "text", QPalette.BrightText: "on_primary",
    QPalette.PlaceholderText: "secondary", QPalette.Highlight: "selection", QPalette.HighlightedText: "text",
    QPalette.ToolTipBase: "raised", QPalette.ToolTipText: "text", QPalette.Link: "link",
    QPalette.LinkVisited: "link", QPalette.Light: "raised", QPalette.Midlight: "divider", QPalette.Mid: "control",
    QPalette.Dark: "control", QPalette.Shadow: "divider", QPalette.Accent: "tick",
}


def qt_palette(t):
    """The Qt palette for a theme: what native drawing (ticks, scroll bars, the Fusion lists, dialogs) uses."""
    p = QPalette()
    for role, key in PALETTE_ROLES.items():
        p.setColor(role, QColor(t[key]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(t["disabled"]))
    return p


def use_theme(name):
    """Make "light" or "dark" the theme in use: the icons are drawn again from it. The caller applies
    style_sheet(THEME) and qt_palette(THEME). Returns THEME."""
    THEME.clear()
    THEME.update(THEMES[name], name=name)
    _ICONS.clear()
    return THEME


def restyle(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


MOTION = {"preference": "system"}   # Settings: "system" (follow Windows), "reduce" or "full"


def set_motion(preference):
    """Settings, "Motion": follow Windows, or reduce or keep motion whatever Windows says."""
    MOTION["preference"] = preference if preference in ("reduce", "full") else "system"


def reduced_motion():
    """Every change is instant: Settings says so, or (following Windows) its "Animation effects" is off
    (Settings > Accessibility > Visual effects)."""
    if MOTION["preference"] != "system":
        return MOTION["preference"] == "reduce"
    if sys.platform != "win32":
        return False
    import ctypes
    on = ctypes.c_int(1)
    ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)  # SPI_GETCLIENTAREAANIMATION
    return bool(ok) and not on.value


def motion(ms):
    """A duration, or 0 when the system asks for reduced motion."""
    return 0 if reduced_motion() else ms


class SmoothScroll(QObject):
    """A mouse wheel glides every list and page to its new place instead of jumping (instant with reduced motion).
    Touchpads already scroll smoothly and are left alone, as are Ctrl+wheel and sideways scrolling."""

    def __init__(self, parent):
        super().__init__(parent)
        self.glides = {}                # scroll bar -> (its animation, the place it is heading for)

    def eventFilter(self, obj, e):
        if e.type() != QEvent.Wheel or e.phase() != Qt.NoScrollPhase or e.modifiers() or not e.angleDelta().y():
            return False
        area = obj.parent()             # only once the wheel reaches a list's or page's own viewport
        if not isinstance(area, QAbstractScrollArea) or area.viewport() is not obj or not motion(MOTION_SCROLL):
            return False
        if isinstance(area, QAbstractItemView):
            area.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)  # by item, a list can only jump
        bar = area.verticalScrollBar()
        if bar.maximum() == bar.minimum():
            return False
        glide, target = self.glides.get(bar, (None, bar.value()))
        if glide is None:
            glide = QPropertyAnimation(bar, b"value", bar)
            glide.setEasingCurve(QEasingCurve.OutCubic)
            glide.setDuration(MOTION_SCROLL)
            bar.destroyed.connect(lambda *_, b=bar: self.glides.pop(b, None))
        if glide.state() != QPropertyAnimation.Running:
            target = bar.value()        # the user may have dragged the bar meanwhile
        step = QApplication.wheelScrollLines() * bar.singleStep() * e.angleDelta().y() / 120
        target = max(bar.minimum(), min(bar.maximum(), round(target - step)))
        self.glides[bar] = glide, target
        glide.stop()
        glide.setStartValue(bar.value())
        glide.setEndValue(target)
        glide.start()
        return True


def smooth_scrolling(app):
    """Every wheel turn in the app glides (SmoothScroll); once per application."""
    if not hasattr(app, "smooth_scroll"):
        app.smooth_scroll = SmoothScroll(app)
        app.installEventFilter(app.smooth_scroll)
    return app.smooth_scroll


def unfold(widget, then=None):
    """Show a hidden widget, growing it to its full height over a moment; then() when it has its full height."""
    widget.show()
    duration = motion(MOTION_QUICK)
    if not duration:
        return then and then()
    grow = QPropertyAnimation(widget, b"maximumHeight", widget)
    grow.setDuration(duration)
    grow.setStartValue(0)
    grow.setEndValue(widget.sizeHint().height())
    grow.setEasingCurve(QEasingCurve.OutCubic)
    grow.finished.connect(lambda: (widget.setMaximumHeight(QWIDGETSIZE_MAX), then and then()))
    grow.start(QPropertyAnimation.DeleteWhenStopped)


def collapse(widget, then):
    """A row that has gone (a document filed): it folds to nothing over a moment, then then(). Instant with
    reduced motion. It takes no clicks or focus meanwhile."""
    duration = motion(MOTION_LEAVE)
    if not duration or not widget.isVisible():
        return then()
    widget.setAttribute(Qt.WA_TransparentForMouseEvents)   # not disabled: that would move the focus along
    for w in [widget] + widget.findChildren(QWidget):
        w.setFocusPolicy(Qt.NoFocus)
    fold = QPropertyAnimation(widget, b"maximumHeight", widget)
    fold.setDuration(duration)
    fold.setStartValue(widget.height())
    fold.setEndValue(0)
    fold.setEasingCurve(QEasingCurve.InCubic)
    fold.finished.connect(then)
    fold.start(QPropertyAnimation.DeleteWhenStopped)


def slide_away(widget, parent):
    """A closing panel: it is hidden at once (nothing waits for the motion), and a picture of it slides out
    to the right edge of parent, then goes."""
    duration = motion(MOTION_STANDARD)
    if duration and widget.isVisible():
        ghost = QLabel(parent)
        ghost.setPixmap(widget.grab())
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
        ghost.setGeometry(widget.geometry().translated(widget.parentWidget().mapTo(parent, QPoint(0, 0))))
        ghost.show()
        ghost.raise_()
        away = QPropertyAnimation(ghost, b"pos", ghost)
        away.setDuration(duration)
        away.setEndValue(QPoint(parent.width(), ghost.y()))
        away.setEasingCurve(QEasingCurve.InCubic)
        away.finished.connect(ghost.deleteLater)
        away.start()
    widget.hide()


def scroll_area_of(widget):
    area = widget.parentWidget()
    while area is not None and not isinstance(area, QScrollArea):
        area = area.parentWidget()
    return area


class ListRow(QFrame):
    """A row of the decision and auto-filed lists (subclasses set self.ids). A click on the row itself, not on
    its buttons or tick, inspects the document: its details open beside the list. Inspecting never files or
    confirms anything. Up and Down move to the row above or below; details, when open, follow."""

    def __init__(self, controller):
        super().__init__()
        self.setObjectName("row")
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.StrongFocus)
        self.c, self.inspected = controller, False

    def set_inspected(self, doc_id):
        on = doc_id is not None and doc_id in self.ids
        if on != self.inspected:
            self.inspected = on
            self.setProperty("inspected", on)
            restyle(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.c.show_details(self.ids[0])
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Up, Qt.Key_Down):
            layout = self.parentWidget().layout()
            rows = [w for w in (layout.itemAt(i).widget() for i in range(layout.count()))
                    if isinstance(w, ListRow) and w.isVisible()]
            at = rows.index(self) + (1 if e.key() == Qt.Key_Down else -1)
            if 0 <= at < len(rows):
                rows[at].setFocus(Qt.OtherFocusReason)
                scroll_area_of(self).ensureWidgetVisible(rows[at], 0, 0)
                if self.c.inspected is not None:
                    self.c.show_details(rows[at].ids[0])
        else:
            super().keyPressEvent(e)


def readable(label):
    """A wrapped label kept to a readable line length (READABLE) on a full-width page, returned in a row of its own
    to add instead of the label. Straight in a vertical layout, Qt works out the wrapped height for the layout's
    whole width, not the capped one, and the last lines are cut off; in a row the height follows the width the
    label really gets."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    label.setMaximumWidth(READABLE)
    row = box(QHBoxLayout())
    row.addWidget(label, 1)
    row.addStretch(0)
    return row


def wrapped(label):
    """A label that wraps and never widens its row: a long word or path wraps or is cut, never scrolls sideways."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


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
        colour = QColor(TYPE_COLOR.get(ext, UNKNOWN_TYPE))
        p.setPen(QPen(colour, 1.4))
        p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 50))
        p.drawPolygon([QPointF(3, 1.5), QPointF(10, 1.5), QPointF(13.5, 5), QPointF(13.5, 14.5), QPointF(3, 14.5)])
        p.drawLine(QPointF(5.5, 8), QPointF(11, 8))
        p.drawLine(QPointF(5.5, 11), QPointF(11, 11))
        p.end()
        _ICONS[ext] = QIcon(pix)
    return _ICONS[ext]


STATUS = {  # an icon plus a word, never colour alone; the colour is a role of the theme in use
    "filed": ("Approved", "green", "check"),
    "auto": ("Filed automatically", "secondary", "check"),   # machine-assigned: not the user's approval
    "needs_decision": ("Waiting", "amber", "dot"),
    "queued": ("Reading", "secondary", "ring"),
    "reading": ("Reading", "secondary", "ring"),
    "filing": ("Filing", "secondary", "ring"),
    "failed": ("Failed", "red", "alert"),
    "pending": ("Failed", "red", "alert"),
}


def status_icon(status):
    key = ("status", status)
    if key not in _ICONS:
        _, role, shape = STATUS.get(status, ("", "secondary", "ring"))
        colour = THEME[role]
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
            p.setPen(QPen(QColor(THEME["base"]), 1.6))   # the mark in the list's own colour
            p.drawLine(QPointF(8, 6.5), QPointF(8, 10))
            p.drawPoint(QPointF(8, 12.2))
        p.end()
        _ICONS[key] = QIcon(pix)
    return _ICONS[key]


def category_color(cat_id):
    """A category's colour: one of CATEGORY_COLORS, the same for that category always (from its id, so a rename
    keeps it), readable on every surface of both themes."""
    return CATEGORY_COLORS[zlib.crc32(str(cat_id).encode()) % len(CATEGORY_COLORS)]


def category_dot(cat_id):
    """A small round dot in the category's colour, beside its name."""
    colour = category_color(cat_id)
    key = ("dot", colour)
    if key not in _ICONS:
        pix = QPixmap(ICON, ICON)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(colour))
        p.drawEllipse(QRectF(ICON / 4, ICON / 4, ICON / 2, ICON / 2))
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
        """notices: [(kind "error" | "warning" | "info" | "quiet", text, action label or None, callback)].
        "quiet": one line without a panel, its action a link, for a page that is about something else."""
        if [n[:3] for n in notices] == self.items and self.box.count() == len(notices):
            return self.setVisible(bool(notices))   # the same notices: nothing is rebuilt
        while self.box.count():
            old = self.box.takeAt(0).widget()
            old.hide()  # hidden at once; deleting happens later and must not leave it overlapping
            old.deleteLater()
        self.items = []
        for kind, text, action, callback in notices:
            quiet = kind == "quiet"
            frame = QFrame()
            frame.setObjectName("" if quiet else "notice")
            h = box(QHBoxLayout(frame), (BAR, 0, 0, 0) if quiet else (GROUP, RELATED, RELATED, RELATED), GROUP)
            icon = QLabel()
            icon.setPixmap(status_icon("failed" if kind == "error" else "needs_decision").pixmap(FILE_ICON, FILE_ICON))
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("error" if kind == "error" else "secondary" if quiet else "")
            frame.setParent(self)
            label.setParent(frame)
            label.ensurePolished()                  # measure with the notice font, not the default
            label.setMaximumWidth(label.fontMetrics().horizontalAdvance(text) + GROUP)  # wraps only when short
            h.addWidget(icon)
            h.addSpacing(RELATED - GROUP)       # icon to label
            h.addWidget(label, 1)
            if action:
                button = QPushButton(action)
                button.setObjectName("link" if quiet else "")
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
        self.slide.setDuration(MOTION_PANEL)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.hide()

    def show_message(self, text, action=None, callback=None, ms=TOAST):
        self.label.setText(text)
        self._callback = callback
        self.action.setText(action or "")
        self.action.setVisible(bool(action))
        self.adjustSize()
        self.slide.stop()
        self.slide.setDuration(motion(MOTION_PANEL))
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
        self.list.setMinimumWidth(PICKER_LIST_MIN)          # a long name ends in "…" (hover shows it) and never widens the page
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
        self.setMinimumWidth(DIALOG_MIN)
        self.verb, self.on_choice = verb, on_choice
        heading = QLabel(title)
        heading.setObjectName("heading")
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
        self.title.setObjectName("hero")
        self.formats = QLabel(f"Supported: {SUPPORTED}")
        self.formats.setObjectName("lead")
        self.skipped = QLabel()
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
        self.drawn, self.shown, self.draws = {}, None, 0   # page -> (width, picture); the one shown; drawings made
        self.settle = QTimer(self)              # one drawing when the resizing has stopped
        self.settle.setSingleShot(True)
        self.settle.setInterval(PREVIEW_SETTLE)
        self.settle.timeout.connect(lambda: self.show_page(self.page))
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
        self.prev.setAccessibleName("Previous page")
        self.prev.clicked.connect(lambda: self.show_page(self.page - 1))
        self.next = QPushButton("›")
        self.next.setObjectName("icon")
        self.next.setToolTip("Next page")
        self.next.setAccessibleName("Next page")
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
        self.drawn = {}
        self.settle.stop()

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
        kept = self.drawn.pop(self.page, None)
        if kept is None or kept[0] != width:    # not drawn at this size yet
            pix = QPixmap()
            pix.loadFromData(self.pdf.png(self.page, width))
            kept = (width, pix)
            self.draws += 1
        self.drawn[self.page] = kept            # the latest last; the oldest go
        for old in list(self.drawn)[:-PREVIEW_KEEP]:
            del self.drawn[old]
        self._fit(kept[1])
        self.page_label.setText(f"Page {self.page + 1} of {self.pdf.count}")
        self.prev.show()
        self.next.show()
        self.prev.setEnabled(self.page > 0)
        self.next.setEnabled(self.page < self.pdf.count - 1)
        self.nav.show()

    def _set(self, png):
        pix = QPixmap()
        pix.loadFromData(png)
        self._fit(pix)

    def _fit(self, pix, resizing=False):
        """Show a drawn picture fitted to the room there is. resizing: a step of a resize, where the picture
        already drawn is stretched or shrunk quickly; the real drawing follows when the resizing stops."""
        self.shown = pix
        area = self.scroll.viewport().size()  # the whole page fits: no scrolling inside the preview
        width = max(40, area.width() - RELATED)
        height = PREVIEW_MAX if self.fit_width else max(40, area.height() - RELATED)
        fits = pix.width() <= width and pix.height() <= height
        if resizing or not fits:
            pix = pix.scaled(width, height, Qt.KeepAspectRatio,
                             Qt.FastTransformation if resizing else Qt.SmoothTransformation)
        self.image.setPixmap(pix)
        if self.fit_width:  # no empty bands above and below the page
            self.scroll.setFixedHeight(pix.height() + RELATED)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.pdf and self.shown is not None:
            self._fit(self.shown, resizing=True)    # no drawing per step
            self.settle.start()

    def showEvent(self, e):
        super().showEvent(e)
        if self.pdf:  # sized while hidden: fit again now that the real size is known
            self.show_page(self.page)


class PreviewOverlay(QFrame):
    """A large preview over the whole window; Esc or Close returns."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("previewOverlay")
        self.title = ElidedLabel(object_name="heading")
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
