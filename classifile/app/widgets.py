"""Small shared widgets and the visual style of the main window."""
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPainterPath, QPalette, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

QWIDGETSIZE_MAX = (1 << 24) - 1

from classifile.analysis.candidates import name_key
from classifile.app import ICON_DIR
from classifile import pages
from classifile.worker import Worker
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
QLabel#column {{ font-size: {TEXT_CAPTION}px; font-weight: {WEIGHT_STRONG}; color: {t['secondary']}; }}
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
QPushButton#link, QToolButton#link {{ border-color: transparent; color: {t['link']};
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
/* Keyboard focus is one ring for every control (FocusRing), shown only after Tab; nothing else draws focus.
   A text field also shows where typing goes, by its border, however it got the focus. */
QPushButton:focus, QToolButton:focus, QComboBox:focus, QCheckBox:focus, QRadioButton:focus {{ outline: none; }}
QLineEdit:focus {{ border-color: {t['accent']}; }}
QFrame#focusRing {{ border: {RING}px solid {t['accent']}; border-radius: {RADIUS_CONTROL + RING}px;
                    background: transparent; }}
QPushButton#nav {{ text-align: left; border: none; background: transparent; color: {t['text']};
                   padding: {NAV_PAD}px {GROUP - BAR}px; border-left: {BAR}px solid transparent; border-radius: 0;
                   max-height: none; }}
QLabel#count {{ font-size: {TEXT_SECONDARY}px; color: {t['secondary']}; }}
QPushButton#nav:checked {{ background: {t['nav']}; border-left: {BAR}px solid {t['accent']}; }}
/* Help, About and Settings at the foot: one rounded shape, the same width, icon and text place; Settings keeps an
   outline to be easy to find. Selected is one teal outline with the tint, never a bar inside an outline. */
QPushButton#nav[foot="true"] {{ margin: 0 {RELATED}px; padding: {NAV_PAD - HAIR}px {RELATED - HAIR}px;
                               border: {HAIR}px solid transparent; border-radius: {RADIUS_CONTROL}px; }}
QPushButton#nav[foot="true"][prominent="true"] {{ border-color: {t['control']}; background: {t['base']};
                                                 font-weight: {WEIGHT_STRONG}; }}
QPushButton#nav[foot="true"]:hover {{ background: {t['hover']}; }}
QPushButton#nav[foot="true"]:checked {{ background: {t['nav']}; border-color: {t['accent']}; }}
QFrame#catBox {{ background: {t['window']}; border: {HAIR}px solid {t['divider']};
                 border-radius: {RADIUS_PANEL}px; }}   /* a step lighter than the sidebar, a hairline edge */
QFrame#settingsCard {{ background: {t['base']}; border: {HAIR}px solid {t['divider']};
                       border-radius: {RADIUS_PANEL}px; }}
QPushButton#nav:hover {{ background: {t['hover']}; }}
/* The lists keep a border of one colour or none, so focus is seen and nothing moves. */
QTreeView, QListWidget {{ border: {HAIR}px solid transparent; border-radius: {RADIUS_ROW}px;
                          background: {t['base']}; color: {t['text']}; outline: none; }}
QTreeView#categories {{ background: transparent; }}
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
                        padding: {RELATED}px {RELATED}px {RELATED}px {RELATED + TIGHT}px; font-size: {TEXT_CAPTION}px;
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
   the inspected row has the selection tint and bar. The bar is always there (transparent), so nothing moves. */
QFrame#row {{ border: none; border-bottom: {HAIR}px solid {t['divider']}; border-left: {BAR}px solid transparent;
              background: {t['base']}; }}
QFrame#row:hover {{ background: {t['hover']}; }}
QFrame#row[inspected="true"] {{ background: {t['selection']}; border-left-color: {t['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: {SCROLLBAR}px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: {SCROLLBAR}px; margin: 0; }}
QScrollBar::handle {{ background: {t['control']}; border-radius: {(SCROLLBAR - 2 * TIGHT) // 2}px; }}
QScrollBar::handle:vertical {{ min-height: {CONTROL}px; margin: {TIGHT}px; }}
QScrollBar::handle:horizontal {{ min-width: {CONTROL}px; margin: {TIGHT}px; }}
QScrollBar::handle:hover, QScrollBar::handle:pressed {{ background: {t['secondary']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
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


class FocusRing(QObject):
    """Where the keyboard is: one rounded ring in the accent colour around the focused control, the same for every
    control. It appears when a key moves the focus and follows the focus while the keyboard is in use; a click or
    a switch back from another window hides it, as a browser's focus-visible does. Qt gives a focus that moves on
    from a hidden control (a filed row folding away) the same reason as Tab, so what counts is a key pressed since
    the last click, not the reason. Text fields are left to their own border. The ring is drawn above the window
    and takes no clicks; it follows the control when it moves, scrolls or changes size, and shows only its
    visible part."""

    def __init__(self, parent):
        super().__init__(parent)
        self.target = self.ring = None
        self.keys = False               # a key was pressed since the last click or window switch

    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.KeyPress:
            self.keys = True
        elif t == QEvent.FocusIn and isinstance(obj, QWidget):
            if e.reason() in (Qt.MouseFocusReason, Qt.ActiveWindowFocusReason):
                self.keys = False
            self.follow(obj if self.keys else None)
        elif self.target is not None and t in (QEvent.Move, QEvent.Resize, QEvent.Hide, QEvent.Show)                 and obj is not self.ring and isinstance(obj, QWidget)                 and (obj is self.target or obj.isAncestorOf(self.target)):
            self.place()
        elif t == QEvent.MouseButtonPress:
            self.keys = False
            if self.target is not None:
                self.follow(None)
        return False

    def follow(self, widget):
        if isinstance(widget, (QLineEdit, QAbstractScrollArea)) and not isinstance(widget, QAbstractItemView):
            widget = None               # text fields and pages show the focus themselves
        self.target = widget
        self.place()

    def place(self):
        w = self.target
        try:
            shown = w.visibleRegion().boundingRect() if w is not None and w.isVisible() else QRect()
            window = w.window() if w is not None else None
        except RuntimeError:            # the control was deleted meanwhile
            shown, window, self.target = QRect(), None, None
        ring = self.ring
        try:
            if ring is not None and (shown.isEmpty() or ring.parent() is not window):
                ring.hide()
        except RuntimeError:            # its window was closed
            ring = self.ring = None
        if shown.isEmpty():
            return
        if ring is None or ring.parent() is not window:
            ring = self.ring = window.findChild(QFrame, "focusRing") or QFrame(window)
            ring.setObjectName("focusRing")
            ring.setAttribute(Qt.WA_TransparentForMouseEvents)
            ring.setFocusPolicy(Qt.NoFocus)
        gap = RING + 1                  # the ring sits just outside the control, never over its border
        ring.setGeometry(QRect(w.mapTo(window, shown.topLeft()), shown.size()).adjusted(-gap, -gap, gap, gap))
        ring.show()
        ring.raise_()


def keyboard_focus(app):
    """The focus ring (FocusRing) for every window of the app; once per application."""
    if not hasattr(app, "focus_ring"):
        app.focus_ring = FocusRing(app)
        app.installEventFilter(app.focus_ring)
    return app.focus_ring


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
    fold.setEasingCurve(QEasingCurve.OutQuint)      # an exit starts at once: ease-in would feel slow
    fold.finished.connect(then)
    fold.start(QPropertyAnimation.DeleteWhenStopped)


def slide_away(widget, parent):
    """A closing panel: it is hidden at once (nothing waits for the motion), and a picture of it slides out
    to the right edge of parent, then goes. Quicker than the panel's arrival: the user is done with it."""
    duration = motion(MOTION_LEAVE)
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
        away.setEasingCurve(QEasingCurve.OutQuint)
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


def wrapped(label):
    """A label that wraps and never widens its row: a long word or path wraps or is cut, never scrolls sideways.
    Running text on a page uses it too, so it fills the card's whole width (record A10: no empty band at the right;
    never cap text with setMaximumWidth, which also cuts off its last lines)."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


def wrappable(path):
    """A path with invisible break points after each separator, so long paths wrap instead of widening a window."""
    return str(path).replace("\\", "\\​").replace("/", "/​")


_ICONS = {}


class _Painted(QIconEngine):
    """An icon drawn on a 16-unit square at whatever size and screen scale it is shown: sharp at 125% and 150%,
    where a 16 px picture would be stretched and blurred."""

    def __init__(self, draw):
        super().__init__()
        self.draw = draw

    def paint(self, p, rect, mode, state):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(rect.topLeft())
        p.scale(rect.width() / 16, rect.height() / 16)
        self.draw(p)
        p.restore()

    def pixmap(self, size, mode, state):
        pix = QPixmap(size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        self.paint(p, QRect(QPoint(), size), mode, state)
        p.end()
        return pix

    def scaledPixmap(self, size, mode, state, scale):
        pix = self.pixmap(size * scale, mode, state)
        pix.setDevicePixelRatio(scale)
        return pix

    def clone(self):
        return _Painted(self.draw)


def painted(key, draw):
    """The icon drawn by draw(painter), kept until the theme changes."""
    if key not in _ICONS:
        _ICONS[key] = QIcon(_Painted(draw))
    return _ICONS[key]


def foot_icon(kind):
    """The glyphs of Help ("?" in a ring), About ("i" in a ring) and Settings (a gear), in the secondary grey."""
    def draw(p):
        pen = QPen(QColor(THEME["secondary"]), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        if kind == "settings":
            p.drawEllipse(QPointF(8, 8), 4.2, 4.2)
            p.drawEllipse(QPointF(8, 8), 1.6, 1.6)
            pen.setWidthF(2.2)
            p.setPen(pen)
            for n in range(8):              # the teeth
                t = QTransform().translate(8, 8).rotate(45 * n)
                p.drawLine(t.map(QPointF(0, -5.6)), t.map(QPointF(0, -6.6)))
            return
        p.drawEllipse(QPointF(8, 8), 6.5, 6.5)
        if kind == "help":
            path = QPainterPath(QPointF(6, 6.3))
            path.cubicTo(QPointF(6, 3.6), QPointF(10.2, 3.6), QPointF(10.2, 6.3))
            path.cubicTo(QPointF(10.2, 8), QPointF(8, 8), QPointF(8, 9.6))
            p.drawPath(path)
            p.drawPoint(QPointF(8, 12))
        else:
            p.drawLine(QPointF(8, 7.3), QPointF(8, 11.6))
            p.drawPoint(QPointF(8, 4.8))
    return painted(("foot", kind), draw)


def format_icon(file_name):
    """A page glyph beside a file name, in the secondary grey: the extension in the name tells the format."""
    def draw(p):
        p.setPen(QPen(QColor(THEME["secondary"]), 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolygon([QPointF(3.5, 1.5), QPointF(10, 1.5), QPointF(13, 4.5), QPointF(13, 14.5), QPointF(3.5, 14.5)])
        p.drawLine(QPointF(6, 8), QPointF(10.5, 8))
        p.drawLine(QPointF(6, 11), QPointF(10.5, 11))
    return painted("page", draw)


STATUS = {  # an icon plus a word, never colour alone; the colour is a role of the theme in use
    "filed": ("Approved", "accent", "check"),
    "auto": ("Filed automatically", "secondary", "check"),   # machine-assigned: not the user's approval
    "copy_missing": ("Filed copy missing", "amber", "alert"),   # filed, but its copy is not where it was put
    "needs_decision": ("Waiting", "amber", "dot"),
    "queued": ("Reading", "secondary", "ring"),
    "reading": ("Reading", "secondary", "ring"),
    "filing": ("Filing", "secondary", "ring"),
    "failed": ("Failed", "red", "alert"),
    "pending": ("Failed", "red", "alert"),
}


def status_icon(status):
    _, role, shape = STATUS.get(status, ("", "secondary", "ring"))

    def draw(p):
        c = QColor(THEME[role])
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
    return painted(("status", status), draw)


def status_word(status):
    return STATUS.get(status, ("",))[0]


def edged(pix):
    """A copy of a page picture with a hairline edge in the divider colour, one screen pixel wide."""
    pix = QPixmap(pix)
    scale = pix.devicePixelRatio()
    pix.setDevicePixelRatio(1)                  # drawn in the picture's own pixels
    p = QPainter(pix)
    p.setPen(QColor(THEME["divider"]))
    p.drawRect(pix.rect().adjusted(0, 0, -1, -1))
    p.end()
    pix.setDevicePixelRatio(scale)
    return pix


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
            h = box(QHBoxLayout(frame), (BAR, 0, 0, 0) if quiet else (GROUP, RELATED, RELATED, RELATED),
                    TIGHT if quiet else GROUP)  # quiet: the link follows its sentence
            icon = QLabel()
            icon.setPixmap(status_icon("failed" if kind == "error" else "needs_decision").pixmap(FILE_ICON, FILE_ICON))
            label = wrapped(QLabel(text))           # fills the row: only its action button stops it short
            label.setObjectName("error" if kind == "error" else "secondary" if quiet else "")
            frame.setParent(self)
            label.setParent(frame)
            h.addWidget(icon)
            h.addSpacing(RELATED - h.spacing())     # icon to label
            h.addWidget(label, 1)
            if action:
                button = QPushButton(action)
                button.setObjectName("link" if quiet else "")
                button.clicked.connect(callback)
                h.addWidget(button)
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


class PageService(QObject):
    """Page pictures drawn in one worker process (classifile.pages.serve), off the interface thread: a damaged or
    slow file can neither freeze nor end the window, and a page not drawn within PREVIEW_TIMEOUT stops its process
    (a new one starts with the next request). One request at a time, answered through done. One per application
    (page_service); the process is started at once, so the first preview does not wait for it."""

    done = Signal(object, object)               # the request's token, its answer (None: failed or timed out)

    def __init__(self):
        super().__init__()
        self.worker = Worker(pages.serve, timeout=PREVIEW_TIMEOUT / 1000, on_failure=lambda request, reason: None)
        self.queue = None                       # the thread that waits on the process, started with a request
        self.ask(None, ("ping",))

    def ask(self, token, request):
        if self.queue is None:                  # first use, or again after stop()
            from concurrent.futures import ThreadPoolExecutor
            self.queue = ThreadPoolExecutor(1)
        self.queue.submit(lambda: self.done.emit(token, self.worker.run(request)))

    def stop(self):
        if self.queue is not None:
            self.queue.shutdown(wait=False, cancel_futures=True)
            self.queue = None
        self.worker.stop()


def page_service():
    app = QApplication.instance()
    if getattr(app, "page_service", None) is None:
        app.page_service = PageService()
        app.aboutToQuit.connect(app.page_service.stop)
    return app.page_service


class Preview(QWidget):
    """A page preview: PDF pages fitted to the width with page navigation, else the stored thumbnail. Page images
    only; no text views and no other programs. Pictures come from the page service, so the window never waits for
    one: until a page arrives, the one before stays (stretched to the new size while resizing)."""

    expand_requested = Signal()

    def __init__(self, expandable=True, fit_width=False):
        super().__init__()
        self.count, self.page, self.source = None, 0, None     # count: pages of the PDF shown (None: no PDF)
        self.waiting, self.asked = None, 0      # the request this preview waits for: (number, what to do with it)
        self.service = page_service()
        self.service.done.connect(self._answer)
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

    @property
    def busy(self):
        """A picture was asked for and has not arrived."""
        return self.waiting is not None

    def _ask(self, request, then):
        self.asked += 1                         # a newer request makes any answer to an older one stale
        self.waiting = (self.asked, then)
        self.service.ask((id(self), self.asked), request)

    def _answer(self, token, out):
        if token is None or token[0] != id(self) or self.waiting is None or token[1] != self.waiting[0]:
            return                              # another preview's, or one this preview no longer waits for
        then, self.waiting = self.waiting[1], None
        then(out)

    def close_pdf(self):
        self.count, self.waiting = None, None
        self.drawn = {}
        self.settle.stop()

    def _unavailable(self, text):
        self.image.setPixmap(QPixmap())
        self.image.setObjectName("card")
        self.image.setText(text)
        restyle(self.image)

    def show_document(self, source, note="", page=0):
        """source: the file to preview (the filed copy, or the original). Page pictures only: without one, a
        plain sentence, never the document's text (viewing text belongs to SummarEase, record A10). page: the
        PDF page to open at."""
        if source == self.source and self.count:
            return self.show_page(page or self.page)
        self.close_pdf()
        self.source, self.page = source, page
        self.image.setPixmap(QPixmap())
        self.image.setObjectName("")
        self.note.setText(note)
        if source is None or not Path(source).exists():
            self.image.setText(f"The original file is no longer at {wrappable(source)}." if source else "")
            self.nav.hide()
            return
        if Path(source).suffix.lower() == ".pdf":
            self.nav.hide()
            self._ask(("count", str(source)), self._got_count)
            return
        self.nav.setVisible(self.expand.isVisible())
        self.prev.hide()
        self.next.hide()
        self.page_label.setText("")
        self._ask(("thumbnail", str(source)), self._got_thumbnail)

    def _got_count(self, n):
        if not isinstance(n, int) or n < 1:
            return self._unavailable("This PDF can't be previewed.")
        self.count = n
        self.show_page(self.page)

    def _got_thumbnail(self, png):
        if png:
            self._set(png)
        else:   # no stored thumbnail (or it couldn't be read), and no other programs are started for one
            self._unavailable("No page picture is stored in this file.")

    def show_page(self, index):
        if not self.count:
            return
        self.page = max(0, min(self.count - 1, index))
        self.page_label.setText(f"Page {self.page + 1} of {self.count}")
        self.prev.show()
        self.next.show()
        self.prev.setEnabled(self.page > 0)
        self.next.setEnabled(self.page < self.count - 1)
        self.nav.show()
        size = (max(200, self.scroll.viewport().width() - 8), self.devicePixelRatioF())  # the screen's own pixels
        kept = self.drawn.pop(self.page, None)
        if kept is not None:
            self.drawn[self.page] = kept        # the latest last; the oldest go
            if kept[0] == size:
                self.waiting = None             # what was asked for before is no longer wanted
                return self._fit(kept[1])
            self._fit(kept[1], resizing=True)   # stretched until it is drawn at the new size
        page = self.page
        self._ask(("page", str(self.source), page, round(size[0] * size[1])),
                  lambda out: self._got_page(page, size, out))

    def _got_page(self, page, size, out):
        if not out:
            return self._unavailable("This page can't be previewed.")
        pix = QPixmap()
        pix.loadFromData(out)
        pix.setDevicePixelRatio(size[1])
        self.draws += 1
        self.drawn.pop(page, None)
        self.drawn[page] = (size, pix)
        for old in list(self.drawn)[:-PREVIEW_KEEP]:
            del self.drawn[old]
        self.image.setObjectName("")
        restyle(self.image)
        self._fit(pix)

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
        size, scale = pix.deviceIndependentSize(), pix.devicePixelRatio()
        if resizing or size.width() > width or size.height() > height:
            pix = pix.scaled(round(width * scale), round(height * scale), Qt.KeepAspectRatio,
                             Qt.FastTransformation if resizing else Qt.SmoothTransformation)
            pix.setDevicePixelRatio(scale)
        self.image.setPixmap(edged(pix))
        if self.fit_width:  # no empty bands above and below the page
            self.scroll.setFixedHeight(round(pix.deviceIndependentSize().height()) + RELATED)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.count and self.shown is not None:
            self._fit(self.shown, resizing=True)    # no drawing per step
            self.settle.start()

    def showEvent(self, e):
        super().showEvent(e)
        if self.count:  # sized while hidden: fit again now that the real size is known
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

    def open(self, name, source, page=0):
        self.title.setText(name)
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self.preview.source = None
        self.preview.show_document(source, page=page)
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
