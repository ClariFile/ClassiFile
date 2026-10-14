"""The two themes: every pair of colours the interface puts together is readable (WCAG contrast ratios).
Text at least 4.5:1; icons, control borders, the focus and selection bars at least 3:1. Dividers between rows
and panels are decorative and not held to 3:1; disabled text is exempt, as WCAG allows."""
import pytest
from test_app import app  # noqa: F401  the QApplication fixture

from classifile.app.tokens import CATEGORY_COLORS, OVERLAY, THEMES, TYPE_COLOR, UNKNOWN_TYPE, WHITE

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
        out += [(f"{status} text on {surface}", t[status], t[surface], TEXT) for status in ("amber", "red", "green")]
    for surface in ("base", "raised", "window"):
        out.append((f"accent text (tags) on {surface}", t["accent"], t[surface], TEXT))
    out += [("primary button text", t["on_primary"], t["primary"], TEXT),
            ("primary button text, hovered", t["on_primary"], t["primary_hover"], TEXT),
            ("selected text in a field", t["on_primary"], t["accent"], TEXT),
            ("toast text", t["on_toast"], t["toast"], TEXT),
            ("text on the dark overlays", WHITE, OVERLAY, TEXT)]
    for surface in ("window", "sidebar", "base", "raised", "inset"):
        out += [(f"control border on {surface}", t["control"], t[surface], GRAPHIC),
                (f"focus border on {surface}", t["accent"], t[surface], GRAPHIC),
                (f"primary button on {surface}", t["primary"], t[surface], GRAPHIC)]
    for surface in ("selection", "nav", "base", "sidebar", "hover"):
        out.append((f"selection bar beside {surface}", t["accent"], t[surface], GRAPHIC))
    for surface in ("window", "base", "raised", "selection", "hover", "notice"):
        out += [(f"{role} icon on {surface}", t[role], t[surface], GRAPHIC)
                for role in ("amber", "red", "green", "secondary", "accent")]
    out.append(("the mark inside the failed icon", t["base"], t["red"], GRAPHIC))
    for surface in ("window", "sidebar", "base", "raised", "selection", "nav", "hover"):
        out += [(f"category dot {c} on {surface}", c, t[surface], GRAPHIC) for c in CATEGORY_COLORS]
        out += [(f"format glyph {c} on {surface}", c, t[surface], GRAPHIC)
                for c in list(TYPE_COLOR.values()) + [UNKNOWN_TYPE]]
    return out


@pytest.mark.parametrize("name", sorted(THEMES))
def test_every_text_and_background_pair_is_readable(name):
    failing = [f"{what}: {contrast(fg, bg):.2f} < {least}" for what, fg, bg, least in pairs(THEMES[name])
               if contrast(fg, bg) < least]
    assert not failing, f"{name}: " + "; ".join(failing)


def test_the_themes_are_complete_and_the_style_sheet_takes_nothing_from_the_system():
    from classifile.app.widgets import style_sheet

    assert set(THEMES["light"]) == set(THEMES["dark"])                 # every role in both themes
    assert len(set(CATEGORY_COLORS)) == 8
    for name, t in THEMES.items():
        sheet = style_sheet(t)
        assert "palette(" not in sheet and "rgba(" not in sheet, name  # no system palette, no grey mixes
        assert sheet.count("white") == 2, name                         # only the two dark overlays
    assert THEMES["light"]["on_primary"] == "#FFFFFF"                  # white text on light primary buttons only


def test_switching_the_theme_rebuilds_the_style_sheet_the_palette_and_the_icons(app, make_org):
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
    assert widgets.category_dot("same id").cacheKey() and widgets.category_color("same id") == \
        widgets.category_color("same id") in CATEGORY_COLORS                      # one colour per category, always
    w.set_appearance("system")
    w.close()
