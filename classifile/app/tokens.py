"""Design tokens: every size, colour and duration of the interface is named here, once (docs/UI_PROPOSAL.md,
section 4). The style sheet and the widgets use these names; no other interface module holds such a value.
Sizes are logical pixels (Qt scales them with the display); durations are milliseconds."""

# -- colour ---------------------------------------------------------------------------------------------------
# Everything not named here comes from the system palette, so light and dark both work.
TEAL = "#0D9488"            # accent: selection bar, selection tint, focus
PRIMARY = "#0F766E"         # primary buttons (white text)
PRIMARY_HOVER = "#115E59"
AMBER = "#D97706"           # waiting
RED = "#DC2626"             # errors
GREEN = "#16A34A"           # approved: filed in a category the user chose
VIOLET = "#6C47FF"          # reserved for SummarEase; unused until it exists
WHITE = "white"             # text on a primary button and on the dark overlays
MUTED = "#9CA3AF"           # status icons for work under way
UNKNOWN_TYPE = "#6B7280"    # the page glyph of a format without a colour of its own
OVERLAY = "#111827"         # the drop and full-preview overlays: dark in both themes
TYPE_COLOR = {".pdf": "#8E6A6A", ".pptx": "#93785A", ".docx": "#5E7392", ".odt": "#5F8570"}  # muted, per format
GREY = "127, 127, 127"      # the one grey, mixed over either theme at the strengths below
BORDER = f"rgba({GREY}, 110)"       # control borders
FIELD_BORDER = f"rgba({GREY}, 90)"  # fields and dropdown lists
HAIRLINE = f"rgba({GREY}, 60)"      # separators between rows and panels
ROW_LINE = f"rgba({GREY}, 40)"      # the lines between list rows; hover on buttons
HOVER = f"rgba({GREY}, 30)"         # hover on rows and navigation
TINT = f"rgba({GREY}, 28)"          # notices
PANEL_TINT = f"rgba({GREY}, 18)"    # the choices panel
TEAL_TINT = "rgba(13, 148, 136, 46)"    # selection and pressed toggles (TEAL, faint)
TEAL_NAV = "rgba(13, 148, 136, 40)"     # the current view in the sidebar
TEAL_BAR = "rgba(13, 148, 136, 30)"     # the bar for several selected documents

# -- spacing --------------------------------------------------------------------------------------------------
PAD = 24        # main content padding
SECTION = 24    # between major sections (a heading and what follows it)
PANEL = 20      # inside panels
GROUP = 16      # between separate groups of controls
RELATED = 8     # between related controls; label to field; icon to label
TIGHT = 4       # inside small things: list padding, tags
HAIR = 1        # borders and lines
NAV_PAD = 10    # above and below a view's name in the sidebar; left of a category's name
BAR = 3         # the selection bar at the left of a row; the drop overlay's dashes

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
PICKER_LIST_MIN = 200   # a long category name ends in "…" and never widens the picker
PICKER_LIST_MAX = 280   # the category picker's list scrolls beyond this height
CHECKLIST_MAX = 220     # the ticks of selected-category mode scroll beyond this height
PREVIEW_MAX = 560       # tallest details preview; the page is fitted to the panel width below this
PREVIEW_MIN = 200       # the details preview never shrinks below this; the panel scrolls instead
TEXT_MIN = 320          # a card's buttons sit at its right only while its text keeps this much room
LIST_MIN = 520          # decision and auto-filed lists: details sit beside them only while they keep this much
LIST_MAX = 1120         # those lists stop growing here, so a name and its buttons stay close on wide screens
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
PREVIEW_SETTLE = 150    # after the last resize step, before the page is drawn again at its new size
TOAST = 5000            # how long a message stays
TOAST_LONG = 10000      # a message that says something went wrong, or more than one thing
