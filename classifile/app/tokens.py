"""Design tokens: every size, colour and duration of the interface is named here, once (docs/UI_PROPOSAL.md,
section 4). The style sheet and the widgets use these names; no other interface module holds such a value.
Sizes are logical pixels (Qt scales them with the display); durations are milliseconds."""

# -- colour ---------------------------------------------------------------------------------------------------
# Two complete themes: every surface, text, line, accent and status colour is named for light and for dark. The
# style sheet and the Qt palette are built from the theme in use (widgets.use_theme), so nothing comes from the
# system palette and nothing mixes greys over it. tests/test_theme.py checks the contrast of every pair: text at
# least 4.5:1, icons and control borders at least 3:1. Dividers between rows and panels are decorative lines and
# are not held to 3:1. Teal appears only on the primary button, the selection bar, the focus outline and links;
# everything else is neutral grey, and hover is a grey change.
THEMES = {
    "light": {
        "window": "#F6F7F9",        # the page behind everything
        "sidebar": "#EEF1F4",
        "base": "#FFFFFF",          # lists, rows, fields
        "raised": "#FFFFFF",        # details, the choices panel, menus, dialogs
        "inset": "#F6F7F9",         # a panel inside a row (the choices)
        "text": "#111827",
        "secondary": "#4B5563",     # captions, counts, reasons
        "disabled": "#6B7280",
        "divider": "#D9DEE5",       # lines between rows and panels (decorative)
        "control": "#82868C",       # the outline of buttons, fields and ticks (neutral grey)
        "tick": "#4B5563",          # a ticked box: neutral, like every control
        "accent": "#0F766E",        # teal: the selection bar and the focus outline
        "link": "#0F766E",          # teal links in text
        "primary": "#0F766E",       # primary buttons, the one filled teal
        "primary_hover": "#115E59",
        "on_primary": "#FFFFFF",
        "selection": "#E0F2EF",     # the inspected row and selected items: a faint teal tint, with the bar
        "nav": "#E0F2EF",           # the current view in the sidebar
        "hover": "#EAEEF2",         # a light grey change, never teal
        "pressed": "#E2E6EB",       # a toggle that is on
        "notice": "#E8EDF2",
        "bulk": "#E8EDF2",          # the bar for several selected documents
        "disabled_fill": "#E5E7EB",
        "toast": "#26292E",
        "on_toast": "#F9FAFB",
        "amber": "#AA4F09",         # waiting
        "red": "#B91C1C",           # errors
        "green": "#14793A",         # approved
    },
    "dark": {                       # neutral charcoal: no tint in the backgrounds
        "window": "#1C1E21",
        "sidebar": "#18191C",
        "base": "#212428",
        "raised": "#272A2F",
        "inset": "#272A2F",
        "text": "#E6E8EB",
        "secondary": "#A0A6AD",
        "disabled": "#7A8087",
        "divider": "#33373D",
        "control": "#777A7F",
        "tick": "#A0A6AD",
        "accent": "#2B9C8E",
        "link": "#38A899",          # the bar's teal, a step lighter: 4.5:1 on the raised panels and the selection
        "primary": "#0F766E",
        "primary_hover": "#115E59",
        "on_primary": "#FFFFFF",
        "selection": "#223234",     # about 12% of the bar's teal over the list
        "nav": "#223234",
        "hover": "#2A2E33",
        "pressed": "#33373D",
        "notice": "#272A2F",
        "bulk": "#272A2F",
        "disabled_fill": "#2E3238",
        "toast": "#3A3F46",
        "on_toast": "#E6E8EB",
        "amber": "#D29922",
        "red": "#EA756F",           # #E5534B lightened: it was under 4.5:1 on the raised panels and the selection
        "green": "#57AB5A",
    },
}
WHITE = "white"             # only on the dark overlays (primary buttons take on_primary, white in both themes)
OVERLAY = "#16181B"         # the drop and full-preview overlays: dark neutral charcoal in both themes
OVERLAY_LINE = "#9CA3AF"    # the drop overlay's dashed outline: grey, not glowing
VIOLET = "#6C47FF"          # reserved for SummarEase; unused until it exists
# The format glyph beside a file name, and a category's dot: the same in both themes, readable on every surface
TYPE_COLOR = {".pdf": "#9A7878", ".pptx": "#977B5C", ".docx": "#6C81A0", ".odt": "#618872"}
UNKNOWN_TYPE = "#79808F"
CATEGORY_COLORS = ("#BB6868", "#9E7947", "#83833B", "#41904E", "#3F8C85", "#5583B2", "#8276C1", "#B75EB7")   # muted

# -- spacing --------------------------------------------------------------------------------------------------
PAD = 24        # main content padding
SECTION = 24    # between major sections (a heading and what follows it)
PANEL = 20      # inside panels
GROUP = 16      # between separate groups of controls
RELATED = 8     # between related controls; label to field; icon to label
TIGHT = 4       # inside small things: list padding, tags
HAIR = 1        # borders and lines
NAV_PAD = 10    # above and below a view's name in the sidebar; left of a category's name
BAR = 2         # the selection bar at the left of a row; the drop overlay's dashes

# -- text -----------------------------------------------------------------------------------------------------
FONT = "Segoe UI"
TEXT_CAPTION = 12
TEXT_SECONDARY = 13
TEXT_BODY = 14
TEXT_HEADING = 16
TEXT_TITLE = 22
WEIGHT_STRONG = 600     # headings, file names and primary buttons; everything else is 400
SPACED = 1              # letter spacing of section captions

# -- radii ----------------------------------------------------------------------------------------------------
RADIUS_ROW = 4          # rows and list items
RADIUS_CONTROL = 6      # buttons, fields, notices
RADIUS_PANEL = 8        # panels, cards and overlays
RADIUS_TAG = 10

# -- sizes ----------------------------------------------------------------------------------------------------
ROW = 44                # document rows
CATEGORY_ROW = 32       # sidebar rows and dropdown rows
CONTROL = 36            # buttons, fields and icon buttons share one height
CONTROL_TEXT = 20       # the text line inside a control
TAG = 18
ICON = 16               # icons in text
FILE_ICON = 20          # the format glyph beside a file name
SIDEBAR_WIDTH = 240
WINDOW = (1280, 760)    # the window's size at first start
MIN_WINDOW = (900, 560)
WIDE = 1280             # from here the details panel sits beside the list; narrower, it opens over the list
NARROW = 1024           # below this the sidebar collapses to a menu button
DETAILS_WIDTH = 420     # details panel: at least this wide by default, up to DETAILS_MAX on large screens
DETAILS_MIN = 360
DETAILS_MAX = 560
CHOICES_MAX = 680       # the "Choose another…" panel of a decision item
SEARCH_MAX = 480        # the search field
NAME_FIELD_MAX = 340    # the name field of a new-subject question
DIALOG_MIN = 440        # the category picker's own window
READABLE = 720          # the widest a paragraph of running text gets on a full-width page: about 75 characters
LEARN_LIST_MAX = 360    # the folders of "Learn from my existing folders" scroll beyond this height
PICKER_LIST_MIN = 200   # a long category name ends in "…" and never widens the picker
PICKER_LIST_MAX = 280   # the category picker's list scrolls beyond this height
CHECKLIST_MAX = 220     # the ticks of selected-category mode scroll beyond this height
PREVIEW_MAX = 560       # tallest details preview; the page is fitted to the panel width below this
PREVIEW_MIN = 200       # the details preview never shrinks below this; the panel scrolls instead
TEXT_MIN = 320          # a card's buttons sit at its right only while its text keeps this much room
LIST_MIN = 520          # decision and auto-filed lists: details sit beside them only while they keep this much
BUTTON_TEXT_MAX = 20    # characters of a category name inside a button; the rest ends in "…"
STATUS_COLUMN = 150     # the review status column of the auto-filed list
COLUMNS_MIN = 780       # narrower, that list puts the category and status on a second line in each row
DATE_COLUMN_MIN = 760   # the document list itself: narrower (the details panel beside it), no date column
PREVIEW_KEEP = 8        # drawn pages kept, so paging back draws nothing

# -- motion ---------------------------------------------------------------------------------------------------
MOTION_STANDARD = 180   # the details panel sliding in and out
MOTION_QUICK = 120      # a row's choices opening
MOTION_PANEL = 200      # the toast
MOTION_LEAVE = 150      # a filed row folding away
MOTION_SCROLL = 160     # a list or page gliding after a wheel turn
PREVIEW_SETTLE = 150    # after the last resize step, before the page is drawn again at its new size
TOAST = 5000            # how long a message stays
TOAST_LONG = 10000      # a message that says something went wrong, or more than one thing
