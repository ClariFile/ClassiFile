"""The two themes: every pair of colours the interface puts together is readable (WCAG contrast ratios).
Text at least 4.5:1; icons, control borders, the focus and selection bars at least 3:1. Dividers between rows
and panels are decorative and not held to 3:1; disabled text is exempt, as WCAG allows. A primary button is told
by its white label (checked), not by its fill against the page.
And the owner's rules: three colours over neutral greys (teal, amber, red), teal only on the primary button, the
selection bar, the focus outline, links and the Approved check; every large surface neutral grey; hover a grey
change."""
import pytest
from test_app import app  # noqa: F401  the QApplication fixture

from classifile.app.tokens import OVERLAY, THEMES, WHITE

SURFACES = ("window", "sidebar", "base", "raised", "inset", "selection", "nav", "hover", "notice", "bulk")
TEXT = 4.5
GRAPHIC = 3.0


def luminance(colour):
    colour = {"white": "#FFFFFF"}.get(colour, colour).lstrip("#")
    channel = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(int(colour[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def pairs(t):
    """(what, foreground, background, least ratio) for everything the style sheet and the icons combine."""
    out = []
    for surface in SURFACES:
        out += [(f"text on {surface}", t["text"], t[surface], TEXT),
                (f"secondary text on {surface}", t["secondary"], t[surface], TEXT)]
    for surface in ("window", "base", "raised", "notice", "selection", "hover"):
        out += [(f"{status} text on {surface}", t[status], t[surface], TEXT) for status in ("amber", "red")]
    for surface in ("window", "base", "raised", "selection", "hover"):
        out.append((f"links (teal) on {surface}", t["link"], t[surface], TEXT))
    out += [("primary button text", t["on_primary"], t["primary"], TEXT),
            ("primary button text, hovered", t["on_primary"], t["primary_hover"], TEXT),
            ("text on a pressed toggle", t["text"], t["pressed"], TEXT),
            ("toast text", t["on_toast"], t["toast"], TEXT),
            ("text on the dark overlays", WHITE, OVERLAY, TEXT)]
    for surface in ("window", "sidebar", "base", "raised", "inset"):
        out += [(f"control border on {surface}", t["control"], t[surface], GRAPHIC),
                (f"focus border on {surface}", t["accent"], t[surface], GRAPHIC),
                (f"a ticked box on {surface}", t["tick"], t[surface], GRAPHIC)]
    for surface in ("selection", "nav", "base", "sidebar", "hover"):
        out.append((f"selection bar beside {surface}", t["accent"], t[surface], GRAPHIC))
    for surface in ("window", "base", "raised", "selection", "hover", "notice"):
        out += [(f"{role} icon on {surface}", t[role], t[surface], GRAPHIC)
                for role in ("amber", "red", "accent", "secondary")]
    out.append(("the mark inside the failed icon", t["base"], t["red"], GRAPHIC))
    return out


@pytest.mark.parametrize("name", sorted(THEMES))
def test_every_text_and_background_pair_is_readable(name):
    failing = [f"{what}: {contrast(fg, bg):.2f} < {least}" for what, fg, bg, least in pairs(THEMES[name])
               if contrast(fg, bg) < least]
    assert not failing, f"{name}: " + "; ".join(failing)


def chroma(colour):
    """How coloured a colour is: the spread of its red, green and blue (0 for a grey)."""
    rgb = [int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return max(rgb) - min(rgb)


@pytest.mark.parametrize("name", sorted(THEMES))
def test_teal_only_where_the_owner_allows_it_and_large_surfaces_are_neutral(name):
    import re

    from classifile.app.widgets import style_sheet

    t = THEMES[name]
    for role in ("window", "sidebar", "base", "raised", "inset", "hover", "pressed", "notice", "bulk", "toast",
                 "divider", "control", "disabled_fill"):
        assert chroma(t[role]) <= 12, f"{name}: {role} {t[role]} is not a neutral grey"
    assert chroma(t["selection"]) <= 24 and t["selection"] == t["nav"]        # a faint tint, with the bar
    assert t["primary"] == "#0F766E" and t["primary_hover"] == "#115E59"      # the same in both themes
    for block in style_sheet(t).split("}"):
        selector, _, body = block.partition("{")
        if t["accent"] in body:                 # focus outlines, selection bars and links only
            assert re.search(r"focus|selected|nav(\[[a-z]+=\"true\"\])*:checked|inspected|#primary|#link", selector), selector.strip()
        if ":hover" in selector:
            assert t["accent"] not in body and t["selection"] not in body, selector.strip()   # hover is grey


def test_the_themes_are_complete_and_the_style_sheet_takes_nothing_from_the_system():
    from classifile.app.widgets import style_sheet

    assert set(THEMES["light"]) == set(THEMES["dark"])                 # every role in both themes
    hues = {k for k, v in THEMES["light"].items() if chroma(v) > 24 and k not in ("selection", "nav")}
    assert hues == {"accent", "link", "primary", "primary_hover", "amber", "red"}   # teal, amber, red: no more
    for name, t in THEMES.items():
        sheet = style_sheet(t)
        assert "palette(" not in sheet and "rgba(" not in sheet, name  # no system palette, no grey mixes
        assert sheet.count("white") == 2, name                         # only the two dark overlays
        assert t["on_primary"] == "#FFFFFF"                             # and the primary buttons' label


def test_switching_the_theme_rebuilds_the_style_sheet_the_palette_and_the_icons(app, make_org):
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from classifile.app import widgets
    from classifile.app.main import MainWindow

    w = MainWindow(make_org(), ask_output_root=False)
    w.show()
    for name in ("dark", "light", "dark"):
        w.set_appearance(name)
        t = THEMES[name]
        assert widgets.THEME["name"] == name and w.styleSheet() == widgets.style_sheet(t)
        assert QApplication.palette().window().color().name().upper() == t["window"]
        assert w.table.palette().text().color().name().upper() == t["text"]       # the Fusion lists too
        icon = widgets.status_icon("needs_decision").pixmap(16, 16).toImage()
        assert icon.pixelColor(8, 8).name().upper() == t["amber"]                 # drawn again in the new colours
        crisp = widgets.status_icon("needs_decision").pixmap(QSize(16, 16), 1.5)
        assert crisp.width() == 24 and crisp.devicePixelRatio() == 1.5           # drawn for the screen's scale
    w.set_appearance("system")
    w.close()


def test_every_settings_option_shows_and_keeps_what_was_picked_at_once(app, make_org, monkeypatch):
    from PySide6.QtGui import QStyleHints

    from classifile.app.main import SETTINGS, MainWindow

    original = QStyleHints.setColorScheme

    def like_windows(hints, scheme):         # on Windows the change redraws the window at once (not off-screen)
        original(hints, scheme)
        hints.colorSchemeChanged.emit(scheme)

    monkeypatch.setattr(QStyleHints, "setColorScheme", like_windows)
    w = MainWindow(make_org(), ask_output_root=False)
    w.show()
    w.show_view(SETTINGS)
    for combo, stored in ((w.appearance, lambda: w.org.catalog.get_setting("appearance")),
                          (w.motion, lambda: w.org.catalog.get_setting("motion")),
                          (w.auto_level, w.org.auto_level),
                          (w.auto_scope, lambda: w.org.catalog.get_setting("auto_scope", "all"))):
        for i in [*range(1, combo.count()), 0]:                       # every option, one pick each
            combo.setCurrentIndex(i)
            combo.activated.emit(i)
            app.processEvents()
            assert combo.currentIndex() == i and stored() == combo.itemData(i), combo.accessibleName()
    for tick, stored in ((w.auto_folders, w.org.auto_folders),
                         (w.close_toggle, lambda: w.org.catalog.get_setting("close_notice") != "off")):
        for _ in range(2):                                            # on, then off: one click each
            tick.click()
            app.processEvents()
            assert tick.isChecked() == stored(), tick.text()
    w.set_appearance("system", save=True)
    w.close()


def test_keyboard_focus_is_one_ring_shown_only_after_tab(app, make_org):
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFrame

    from classifile.app.main import ALL, SETTINGS, MainWindow
    from classifile.app.widgets import keyboard_focus

    keyboard_focus(app)
    w = MainWindow(make_org(), ask_output_root=False)
    w.show()
    w.activateWindow()
    app.processEvents()
    def ring():
        r = w.findChild(QFrame, "focusRing")
        return r.geometry() if r is not None and r.isVisible() else None

    first, second = w.nav[ALL], w.nav[SETTINGS]

    def around(widget):
        return QRect(widget.mapTo(w, widget.rect().topLeft()), widget.size())

    def by_key(widget, reason=Qt.TabFocusReason):
        QTest.keyClick(w, Qt.Key_Shift)                     # a key that does nothing: the keyboard is in use
        widget.setFocus(reason)
        app.processEvents()

    w.search.setFocus(Qt.MouseFocusReason)                  # from somewhere else
    by_key(first)
    assert ring() is not None and ring().contains(around(first)) and ring() != around(first)  # just outside it
    by_key(second)                                          # it follows the keyboard
    assert ring().contains(around(second))
    QTest.mousePress(second, Qt.LeftButton)                 # a click: no ring
    QTest.mouseRelease(second, Qt.LeftButton)
    app.processEvents()
    assert ring() is None
    first.setFocus(Qt.MouseFocusReason)
    first.hide()                                            # Qt moves the focus on "as by Tab": still no ring
    app.processEvents()
    assert ring() is None
    first.show()
    by_key(first)
    by_key(w.search)                                        # a text field shows the focus by its own border
    assert ring() is None
    by_key(first, Qt.ActiveWindowFocusReason)               # back from another window: no ring
    assert ring() is None
    w.close()
