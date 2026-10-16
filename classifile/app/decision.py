"""The "Needs your decision" page: one row per question, with one primary action each."""
import html
from collections import Counter

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key, top_names
from classifile.app.reasons import reason_text, similar_reason
from classifile.app.widgets import (
    BAR, BUTTON_TEXT_MAX, CHOICES_MAX, FILE_ICON, GROUP, NAME_FIELD_MAX, RELATED, TEXT_MIN, TIGHT,
    CategoryPicker, ElidedLabel, ListRow, box, collapse, format_icon, restyle, scroll_area_of, unfold, wrappable,
    wrapped,
)

TOP = 3
# Why the suggested names were set aside: (button, hint, what the catalog records). Optional.
REASONS = (("Too narrow", "A lesson or a section", "too narrow"), ("Too broad", "", "too broad"),
           ("Wrong topic", "", "wrong topic"), ("Not a real name", "A fragment, a person or a file name",
                                                "not a real name"),
           ("Couldn't read the document", "", "could not read"))
ROW_MARGINS = (RELATED - BAR, GROUP - TIGHT, RELATED, GROUP - TIGHT)   # inside a row, after its bar


def group_items(docs):
    """Waiting documents as decision items. Readable documents whose top suggestion is exactly the same (same
    name key) and whose originals are present form one group item; everything else is a single item, and so is
    every document that existing categories match (its question is its own)."""
    items, groups = [], {}
    for d in docs:
        top = top_names(d["suggestions"], 1)
        if d.get("subject"):                    # no category matches it, and it resembles others: one question
            groups.setdefault(("subject", d["subject"][0]), []).append(d)
        elif d["status"] == "needs_decision" and not d["missing"] and top and not d.get("matches"):
            groups.setdefault(name_key(top[0]["name"]), []).append(d)
        else:
            items.append([d])
    items += groups.values()  # a group of one is a single item
    order = {d["id"]: i for i, d in enumerate(docs)}
    attention = lambda m: 0 if m[0]["status"] in ("failed", "pending") else 1 if m[0]["missing"] else 2
    return sorted(items, key=lambda m: (attention(m), min(order[d["id"]] for d in m)))  # problems first


def card_state(members, categories):
    """Everything a card shows. While this is unchanged, the card is kept exactly as it is."""
    first = members[0]
    if first.get("subject"):
        return ("subject", [(d["id"], d["file_name"]) for d in members], first["subject"][1],
                [top_names(d["suggestions"], 1) for d in members])
    top = top_names(first["suggestions"], 1) if first["status"] == "needs_decision" else []
    existing = categories.get(name_key(top[0]["name"])) if top else None
    return ([(d["id"], d["file_name"]) for d in members], first["status"], first["status_reason"], first["missing"],
            first["source_path"], first["suggestions"], first["unit"],
            existing["name"] if existing else bool(categories), first.get("matches"), first.get("abstained"))


def shorten(name, limit=BUTTON_TEXT_MAX):
    """A category name for a button: the rest ends in "…" (the tooltip has it whole)."""
    return (name if len(name) <= limit else name[:limit - 1] + "…").replace("&", "&&")


def found_text(evidence, unit):
    """Where a suggested name was found, as a sentence: "Found on the cover and most pages"."""
    where = reason_text(evidence, unit)
    return "" if not where else where.capitalize() if where.startswith("key") else f"Found {where}"


def more_button():
    more = QToolButton()
    more.setObjectName("more")
    more.setText("⋯")
    more.setToolTip("More actions")
    more.setAccessibleName("More actions")
    more.setPopupMode(QToolButton.InstantPopup)
    return more


class DecisionItem(ListRow):
    """One question: the document, what is suggested and why on quiet lines under it, one main action. The other
    matching categories stay one click away on a quiet line (decision record B2); everything else is under
    "Choose another…" and ⋯. A click on the row itself only inspects it."""

    def __init__(self, docs, controller, categories=None):
        """categories: {name key: category} as the catalog has them now (asked for when not given)."""
        super().__init__(controller)
        self.docs = docs
        self.ids = [d["id"] for d in docs]
        first = docs[0]
        self.group = len(docs) > 1
        top = top_names(first["suggestions"], TOP) if first["status"] == "needs_decision" else []
        self.best = top[0]["name"] if top else ""
        # [(category name, documents it was compared with, words shared with them)]: the existing categories that
        # match best, if any do
        self.matches = first.get("matches") or []
        if self.matches:
            self.best = self.matches[0][0]

        icon = QLabel()
        icon.setPixmap(format_icon(first["file_name"]).pixmap(FILE_ICON, FILE_ICON))
        self.title = ElidedLabel(f"{len(docs)} documents with the same suggestion" if self.group
                                 else first["file_name"], "strong")
        self.number = QLabel()                  # the item's place in the list, set by the page
        self.number.setObjectName("secondary")
        self.number.setMinimumWidth(self.number.fontMetrics().horizontalAdvance("99.") + TIGHT)
        self.number.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.kind = QLabel()                    # "Suggested category:", then the name in bold
        self.kind.setObjectName("secondary")
        self.category = ElidedLabel(object_name="strong")
        self.suggestion = QWidget()
        row = box(QHBoxLayout(self.suggestion), spacing=TIGHT)
        row.addWidget(self.kind)
        row.addWidget(self.category, 1)
        self.line = QLabel()                    # problems and other whole sentences; wraps
        wrapped(self.line)
        self.reason = ElidedLabel(object_name="secondary")
        self.names = QLabel()
        self.names.setObjectName("secondary")
        wrapped(self.names)
        if self.group:
            shown = [d["file_name"] for d in docs[:6]]
            more = len(docs) - len(shown)
            self.names.setText(", ".join(shown) + (f" and {more} more" if more else ""))

        self.primary = QPushButton()
        self.primary.setObjectName("primary")
        self.primary.clicked.connect(self.primary_action)
        # The second and third matching categories: one click each (decision record B2), as quiet links that wrap.
        self.others = QLabel("Or file in: " + " · ".join(
            f'<a href="{n}">{html.escape(m[0])}</a>' for n, m in enumerate(self.matches) if n))
        self.others.setObjectName("secondary")
        wrapped(self.others)
        self.others.setTextFormat(Qt.RichText)
        self.others.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        self.others.setToolTip("\n".join(f"File in '{name}'. {similar_reason(n, name, words)}."
                                         for name, n, words in self.matches[1:]))
        self.others.setAccessibleName("Or file in another matching category")
        self.others.linkActivated.connect(lambda n: self.c.file_docs(self.ids, self.matches[int(n)][0]))
        self.choose = QPushButton("Choose another…")
        self.choose.setObjectName("quiet")
        self.choose.clicked.connect(self.toggle_expanded)
        self.remove = QPushButton("Remove from ClassiFile")
        self.remove.clicked.connect(lambda: self.c.remove_docs(self.ids))
        self.details = QPushButton("Details")
        self.details.setObjectName("quiet")
        self.details.setToolTip("Show or hide this document's pages and details beside the list")
        self.details.setCheckable(True)         # pressed while this document's details are open
        self.details.clicked.connect(
            lambda on: self.c.show_details(first["id"]) if on else self.c.close_details())
        if self.group:                          # a group: Details lists each document, to open its pages
            self.details.setCheckable(False)
            self.details.clicked.disconnect()
            self.details.setToolTip("Show one of these documents' pages and details beside the list")
            pages = QMenu(self.details)
            for d in docs:
                pages.addAction(d["file_name"], lambda i=d["id"]: self.c.show_details(i))
            self.details.setMenu(pages)
        self.more_menu = more_button()
        menu = QMenu(self)
        # A row keeps one main action, "Choose another…" and "Details"; the rest is under ⋯, at the row's end.
        self.pending = menu.addAction("Leave pending", lambda: self.c.leave_pending(self.ids))
        menu.addAction("Remove from ClassiFile", lambda: self.c.remove_docs(self.ids))
        self.more_menu.setMenu(menu)

        self.action_bar = QWidget()             # at the right of the text, or under it when room is short;
        self.actions = box(QBoxLayout(QBoxLayout.LeftToRight, self.action_bar))   # narrower still, on two lines
        self.quiet = box(QHBoxLayout())
        for w in (self.choose, self.details, self.more_menu):
            self.quiet.addWidget(w)
        self.quiet.addStretch(1)
        self.actions.addWidget(self.primary, 0, Qt.AlignLeft)
        self.actions.addWidget(self.remove, 0, Qt.AlignLeft)
        self.actions.addLayout(self.quiet)
        text = box(QVBoxLayout(), spacing=TIGHT)
        text.addWidget(self.title)
        for w in (self.suggestion, self.line, self.reason, self.names, self.others):
            text.addWidget(w)
            w.hide()                            # hide(), never show(): shown without a parent it is a window
        text.addStretch(1)
        self.body = box(QBoxLayout(QBoxLayout.LeftToRight), spacing=GROUP)  # description, then the controls
        self.body.addLayout(text, 1)
        self.body.addWidget(self.action_bar, 0, Qt.AlignVCenter)
        self.all_suggestions = top[:1] if self.group else first["suggestions"]
        self.one_click = False                  # the primary button files at once (else it opens the choices)
        self.expanded = self._expanded_area()
        column = box(QVBoxLayout(), spacing=RELATED)
        column.addLayout(self.body)
        column.addWidget(self.expanded)
        lead = box(QHBoxLayout(), spacing=RELATED)
        lead.addWidget(self.number)
        lead.addWidget(icon)
        lead_column = box(QVBoxLayout())
        lead_column.addLayout(lead)
        lead_column.addStretch(1)
        v = box(QHBoxLayout(self), ROW_MARGINS, RELATED)
        v.addLayout(lead_column)
        v.addLayout(column, 1)
        categories = controller.categories_by_key() if categories is None else categories
        existing = categories.get(name_key(self.best)) if self.best else None
        self.search_text = " ".join([d["file_name"] for d in docs] + [existing["name"] if existing else self.best]
                                    + [m[0] for m in self.matches]).casefold()   # what the search looks at
        self._configure(first, top, existing, bool(categories))

    # -- what the item asks ------------------------------------------------------------------------------------
    @staticmethod
    def _say(label, text):
        label.setText(text)
        label.setVisible(bool(text))

    def _suggest(self, kind, name, reason=""):
        self.kind.setText(kind)
        self.category.setText(name)
        self.suggestion.show()
        self._say(self.reason, reason)

    def _configure(self, first, top, existing, any_categories):
        if first["status"] in ("failed", "pending"):
            self._say(self.line, "⚠ This document couldn't be read: "
                      f"{wrappable(first['status_reason'] or 'unknown reason')}.")
            self.line.setObjectName("error")
            self.primary.setText("Retry")
            self.primary.setToolTip("Read the original file again")
            self.primary.clicked.disconnect()
            self.primary.clicked.connect(lambda: self.c.retry_docs(self.ids))
            self._only(self.primary, self.remove)
        elif first["missing"]:
            self._say(self.line, "⚠ The original file has moved. Locate it to file this document.")
            self.line.setObjectName("warning")
            self.primary.setText("Locate file…")
            self.primary.clicked.disconnect()
            self.primary.clicked.connect(lambda: self.c.locate_doc(first["id"]))
            self._only(self.primary, self.remove)
            self.line.setToolTip(f"It was at {first['source_path']}")
        else:
            found = found_text(top[0]["evidence"], first["unit"]) if top else ""
            if len(first["suggestions"]) == 1:
                found += ("  ·  " if found else "") + "Only one suggestion found"
            self.names.setVisible(self.group)
            if self.matches:    # decided from the content; new names stay under "Choose another…" (A0)
                self._suggest("Suggested category:", self.best, similar_reason(self.matches[0][1], self.best,
                                                                               self.matches[0][2]))
                self.others.setVisible(len(self.matches) > 1)
                self.primary.setText(f"File in {shorten(self.best)}")
                self.primary.setToolTip(f"File in '{self.best}'")
                self.one_click = True
            elif existing:
                self._suggest("Suggested category:", existing["name"], found)
                self.primary.setText(f"File in {shorten(existing['name'])}")
                self.primary.setToolTip(f"File in '{existing['name']}'")
                self.one_click = True
            elif self.best and not any_categories:  # the very first category: one click is enough
                self._suggest("Suggested new category:", self.best, found)
                self.primary.setText("Create && file")
                self.primary.setToolTip(f"Create category '{self.best}' and file")
                self.one_click = True
            else:  # categories exist: a new one is never created with one click (decision record B2)
                none = "No close match among your categories" if first.get("abstained") else ""
                if self.best:
                    self._suggest("Suggested new category:", self.best, none or found)
                else:
                    self._say(self.line, (f"{none}. " if none else "") + "No suggested name. Choose a category.")
                self.primary.setText("Choose category…")
                self.choose.hide()
            if first["status_reason"]:
                self._say(self.line, (self.line.text() + "\n" if self.line.text() else "")
                          + f"Last attempt: {wrappable(first['status_reason'])}")
            self.remove.hide()
        restyle(self.line)

    def _only(self, *keep):
        for w in (self.primary, self.choose, self.pending, self.remove):
            w.setVisible(w in keep)

    # -- where the buttons are ---------------------------------------------------------------------------------
    def set_inspected(self, doc_id):
        """doc_id: the document whose details are open (None: closed). Its Details button stays pressed."""
        super().set_inspected(doc_id)
        self.details.setChecked(doc_id == self.ids[0])

    def _arrange(self):
        """The buttons at the right of the text while it keeps enough room; under it otherwise, and on two lines
        (the main action, then the others) when even that is too narrow."""
        shown = [w for w in (self.primary, self.remove) if not w.isHidden()]
        wide = sum(w.sizeHint().width() + RELATED for w in shown) + self.quiet.sizeHint().width()
        room = self.width() - self.number.minimumWidth() - FILE_ICON - 4 * RELATED
        side = room - wide >= TEXT_MIN
        for layout, flat in ((self.body, side), (self.actions, side or room >= wide)):
            direction = QBoxLayout.LeftToRight if flat else QBoxLayout.TopToBottom
            if layout.direction() != direction:
                layout.setDirection(direction)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._arrange()

    # -- the choices: one picker, the suggested names as "New: …" rows -------------------------------------------
    def _expanded_area(self):
        area = QFrame()
        area.setObjectName("choices")
        area.setMaximumWidth(CHOICES_MAX)
        self.picker = CategoryPicker()
        self.picker.changed.connect(self._update_confirm)
        self.picker.activated.connect(self.confirm_action)
        self.picker.cancelled.connect(self.toggle_expanded)
        self.show_all, self.rejected = False, False
        self.more_button = QPushButton()
        self.more_button.setObjectName("link")
        self.more_button.clicked.connect(self._toggle_more)
        self.none_fit = QPushButton("None of these fit — type my own")
        self.none_fit.setObjectName("link")
        self.none_fit.clicked.connect(self._none_fit)
        links = box(QHBoxLayout())
        links.addWidget(self.more_button)
        links.addWidget(self.none_fit)
        links.addStretch(1)
        self.reasons = QWidget()                # shown after "None of these fit": optional, one click
        self.reason_group = QButtonGroup(self)
        grid = box(QGridLayout(self.reasons))
        grid.addWidget(QLabel("What was wrong with the suggestions? (optional)"), 0, 0, 1, 3)
        for n, (label, hint, key) in enumerate(REASONS):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setToolTip(hint)
            b.setProperty("reason", key)
            self.reason_group.addButton(b)
            grid.addWidget(b, 1 + n // 3, n % 3)
        self.confirm = QPushButton("File")
        self.confirm.setObjectName("primary")
        self.confirm.clicked.connect(self.confirm_action)
        bottom = box(QHBoxLayout())
        bottom.addWidget(self.confirm)
        bottom.addStretch(1)
        v = box(QVBoxLayout(area), GROUP)
        v.addWidget(self.picker)
        v.addLayout(links)
        v.addWidget(self.reasons)
        v.addLayout(bottom)
        self.reasons.hide()
        area.hide()
        return area

    def _fill_choices(self):
        top = top_names(self.all_suggestions, TOP)
        rest = [s for s in self.all_suggestions if s not in top]
        offered = [] if self.rejected else top + (rest if self.show_all else [])
        cats, recent = self.c.picker_choices()
        ids = {name_key(name): i for i, name, _ in cats}
        first = [ids[name_key(m[0])] for m in self.matches if name_key(m[0]) in ids]   # the matches lead
        self.picker.set_choices(cats, first + [i for i in recent if i not in first], suggestions=[
            (s["name"], reason_text(s["evidence"], self.docs[0]["unit"])) for s in offered])
        self.more_button.setText("Fewer" if self.show_all else f"More ({len(rest)})")
        self.more_button.setVisible(bool(rest) and not self.rejected)
        self.none_fit.setVisible(bool(top or rest) and not self.rejected)
        self.reasons.setVisible(self.rejected)

    def refresh_choices(self):
        """The categories changed while the choices were open: the list follows; what is typed and chosen stays."""
        if self.expanded.isVisible():
            self._fill_choices()

    def _toggle_more(self):
        self.show_all = not self.show_all
        self._fill_choices()
        self._reveal()

    def _reveal(self):
        """Scroll the page so the choices just opened are in view: the whole row when it fits, else from its
        top. Nothing moves when it is in view already."""
        area = scroll_area_of(self)
        if area is None:
            return
        QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)  # the row has its new height now
        top = self.mapTo(area.widget(), self.rect().topLeft()).y()
        bar = area.verticalScrollBar()
        bar.setValue(min(top, max(bar.value(), top + self.height() - area.viewport().height())))

    def _none_fit(self):
        """The suggested names are set aside: the user types the category they want."""
        self.rejected = True
        self.picker.field.clear()
        self.picker.field.setPlaceholderText("Type the category you want")
        self._fill_choices()
        self.picker.field.setFocus()
        self._reveal()

    def toggle_expanded(self):
        open_ = not self.expanded.isVisible()
        focus = QApplication.focusWidget()
        inside = focus is not None and self.isAncestorOf(focus)
        self.choose.setText("Hide choices" if open_ else "Choose another…")
        if open_:
            self._fill_choices()
            unfold(self.expanded, self._reveal)
            self.picker.field.setFocus()
        else:
            self.expanded.hide()
            if inside:
                self.setFocus()                 # the field went away: the keyboard stays on this row

    def _update_confirm(self):
        choice = self.picker.current()
        self.confirm.setEnabled(bool(choice))  # nothing is filed until a category is chosen
        new = bool(choice) and choice[0] == "new"
        self.confirm.setText("Create && file" if new else "File")
        self.confirm.setToolTip("" if not choice else f"Create category '{choice[2]}' and file" if new
                                else f"File in '{choice[2]}'")

    # -- actions -----------------------------------------------------------------------------------------------
    def primary_action(self):
        if self.one_click:
            self.c.file_docs(self.ids, self.best)
        else:
            self.toggle_expanded()

    def confirm_action(self):
        choice = self.picker.current()
        if not choice:
            return
        feedback = None
        if self.rejected and name_key(choice[2]) not in {name_key(s["name"]) for s in self.all_suggestions}:
            checked = self.reason_group.checkedButton()
            feedback = checked.property("reason") if checked else ""
        self.c.file_docs(self.ids, choice[2], feedback)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.primary.isVisible() and self.primary.isEnabled():
            self.primary.click()
        elif e.key() == Qt.Key_Delete:
            self.c.remove_docs(self.ids)
        else:
            super().keyPressEvent(e)


class SubjectItem(ListRow):
    """One question for several waiting documents that match no existing category and resemble one another
    (decision record B2). The user names the new category once and can untick documents first. Nothing is created
    or filed until then, and nothing here ever goes into an existing category unless the user types its name."""
    group, matches = True, ()

    def __init__(self, docs, controller):
        super().__init__(controller)
        self.docs = docs
        self.ids = [d["id"] for d in docs]
        words = docs[0]["subject"][1]
        self.number = QLabel()
        self.number.setObjectName("secondary")
        self.title = ElidedLabel(f"{len(docs)} documents look like one new subject", "strong")
        self.more_menu = more_button()
        menu = QMenu(self)
        self.pending = menu.addAction("Leave pending", lambda: self.c.leave_pending(self.ids))
        menu.addAction("Remove from ClassiFile", lambda: self.c.remove_docs(self.ids))
        self.more_menu.setMenu(menu)
        head = box(QHBoxLayout())
        head.addWidget(self.number)
        head.addWidget(self.title, 1)
        head.addWidget(self.more_menu)
        self.line = QLabel("Shared key words: " + ", ".join(words) if words
                           else "These documents use many of the same words.")
        self.line.setObjectName("secondary")
        wrapped(self.line)
        rows = box(QGridLayout())
        rows.setColumnStretch(1, 1)
        self.ticks, self.detail_links = {}, {}
        for n, d in enumerate(docs):            # each document: a tick, its file name, and its pages on request
            tick = QCheckBox()
            tick.setChecked(True)
            tick.setToolTip("Untick to leave this document out")
            tick.setAccessibleName(f"Include {d['file_name']}")
            tick.toggled.connect(self._update)
            link = QPushButton("Details")
            link.setObjectName("quiet")
            link.setAccessibleName(f"Details of {d['file_name']}")
            link.clicked.connect(lambda _=False, i=d["id"]: self.c.show_details(i))
            rows.addWidget(tick, n, 0)
            rows.addWidget(ElidedLabel(d["file_name"]), n, 1)
            rows.addWidget(link, n, 2)
            self.ticks[d["id"]], self.detail_links[d["id"]] = tick, link
        self.field = QLineEdit()                # empty: subject names are usually not written in the documents
        self.field.setPlaceholderText("Type a name for the new category")
        self.field.setMaximumWidth(NAME_FIELD_MAX)
        self.field.textChanged.connect(self._update)
        self.field.returnPressed.connect(self.confirm_action)
        self.confirm = QPushButton()
        self.confirm.setObjectName("primary")
        self.confirm.clicked.connect(self.confirm_action)
        self.field.setAccessibleName("Name of the new category")
        name_row = box(QHBoxLayout())
        name_row.addWidget(self.field, 1)
        name_row.addWidget(self.confirm)
        name_row.addStretch(0)
        names = Counter(s["name"] for d in docs for s in top_names(d["suggestions"], 1))
        self.name_links = []
        suggested = box(QHBoxLayout())
        hint = QLabel("Suggested names, if one fits:")
        hint.setObjectName("secondary")
        suggested.addWidget(hint)
        for name, _ in names.most_common(TOP):  # optional: a click only fills the field
            b = QPushButton(shorten(name, 32))
            b.setObjectName("link")
            b.setToolTip(name)
            b.clicked.connect(lambda _=False, name=name: self.field.setText(name))
            suggested.addWidget(b)
            self.name_links.append(b)
        suggested.addStretch(1)
        v = box(QVBoxLayout(self), ROW_MARGINS, TIGHT)
        v.addLayout(head)
        v.addWidget(self.line)
        v.addSpacing(RELATED - TIGHT)
        v.addLayout(rows)
        v.addSpacing(RELATED)
        v.addLayout(name_row)
        if self.name_links:
            v.addLayout(suggested)
        self.search_text = " ".join([d["file_name"] for d in docs] + list(words)).casefold()
        self._update()

    def ticked(self):
        return [i for i, tick in self.ticks.items() if tick.isChecked()]

    def _update(self):
        n, name = len(self.ticked()), " ".join(self.field.text().split())
        existing = self.c.existing_category(name)
        self.confirm.setEnabled(bool(n and name))   # nothing is created until the user has typed the name
        what = f"{n} document{'s' if n != 1 else ''}"
        self.confirm.setText(f"File {what} in it" if existing else f"Create && file {what}")
        self.confirm.setToolTip("" if not (n and name) else f"File {what} in '{existing['name']}'" if existing
                                else f"Create category '{name}' and file {what}")

    def confirm_action(self):
        name = " ".join(self.field.text().split())
        if name and self.ticked():
            self.c.file_docs(self.ticked(), name)   # only the ticked documents; the others keep waiting

    def refresh_choices(self):
        self._update()                          # a category of the typed name may exist now

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.field.setFocus()
        else:
            super().keyPressEvent(e)


def full_width(layout):
    """A list uses the whole width of its page (record 2.9), keeping GROUP at its right for the scroll bar."""
    m = layout.contentsMargins()
    layout.setContentsMargins(m.left(), m.top(), GROUP, m.bottom())


class CheckItem(ListRow):
    """A document the user filed whose content matches another category by a wide margin ("Check these"):
    where it is, what it matches, Keep here (recorded, not asked again), Move to… and Details. Nothing moves by
    itself."""

    def __init__(self, doc_id, controller):
        super().__init__(controller)
        self.doc_id, self.ids, self.state, self.search_text = doc_id, [doc_id], None, ""
        self.icon = QLabel()
        self.name = ElidedLabel(object_name="strong")
        self.about = QLabel()
        self.about.setObjectName("secondary")
        self.about.setWordWrap(True)
        self.move = QPushButton("Move to…")
        self.move.setObjectName("accent")
        self.move.setToolTip("Choose the category it belongs in. Its copy moves; the original is never touched.")
        self.move.clicked.connect(lambda: controller.move_docs([self.doc_id]))
        self.keep = QPushButton("Keep here")
        self.keep.setObjectName("quiet")
        self.keep.setToolTip("It belongs where it is. ClassiFile won't ask about it again.")
        self.keep.clicked.connect(lambda: controller.keep_here([self.doc_id]))
        self.details = QPushButton("Details")
        self.details.setObjectName("quiet")
        self.details.setToolTip("Show or hide this document's pages and details beside the list")
        self.details.setCheckable(True)         # pressed while this document's details are open
        self.details.clicked.connect(
            lambda on: controller.show_details(self.doc_id) if on else controller.close_details())
        text = box(QVBoxLayout(), spacing=TIGHT)
        text.addWidget(self.name)
        text.addWidget(self.about)
        buttons = box(QHBoxLayout(), spacing=RELATED)
        for b in (self.move, self.keep, self.details):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.body = box(QBoxLayout(QBoxLayout.LeftToRight), spacing=RELATED)   # under the text when room is short
        self.body.addLayout(text, 1)
        self.body.addLayout(buttons)
        h = box(QHBoxLayout(self), (RELATED, RELATED, RELATED, RELATED), GROUP)
        h.addWidget(self.icon, 0, Qt.AlignTop)
        h.addLayout(self.body, 1)

    def set_inspected(self, doc_id):
        super().set_inspected(doc_id)
        self.details.setChecked(doc_id == self.doc_id)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        wide = sum(b.sizeHint().width() + RELATED for b in (self.move, self.keep, self.details))
        side = self.width() - FILE_ICON - 4 * RELATED - wide >= TEXT_MIN
        direction = QBoxLayout.LeftToRight if side else QBoxLayout.TopToBottom
        if self.body.direction() != direction:
            self.body.setDirection(direction)

    def fill(self, file_name, here, other):
        if (file_name, here, other) != self.state:
            self.state = (file_name, here, other)
            self.icon.setPixmap(format_icon(file_name).pixmap(FILE_ICON, FILE_ICON))
            self.name.setText(file_name)
            self.about.setText(f"In {here}. Its content matches {other} much more closely.")
            self.keep.setAccessibleName(f"Keep {file_name} in {here}")
            self.move.setAccessibleName(f"Move {file_name} to another category")
            self.search_text = f"{file_name} {here} {other}".casefold()


class DecisionPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.items, self.query, self.version, self.inspected = [], "", None, None
        self.checks = []                            # CheckItems: filed documents to check, above the questions
        self.holder = QWidget()
        outer = box(QVBoxLayout(self.holder), (0, 0, GROUP, 0), 0)     # room for the scroll bar
        self.check_box = QWidget()
        caption = QLabel("CHECK THESE")
        caption.setObjectName("section")
        why = QLabel("You filed these yourself, but their content matches another category much more closely. "
                     "Nothing moves unless you choose.")
        why.setObjectName("secondary")
        why.setWordWrap(True)
        self.check_list = box(QVBoxLayout(self.check_box), (0, 0, 0, GROUP), TIGHT)
        self.check_list.addWidget(caption)
        self.check_list.addWidget(why)
        self.check_box.hide()
        outer.addWidget(self.check_box)
        self.list = box(QVBoxLayout(), spacing=0)
        outer.addLayout(self.list, 1)
        self.list.addStretch(1)                     # always last; the rows go before it
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.holder)
        self.empty = QLabel("Nothing needs your decision right now.")
        self.empty.setObjectName("secondary")
        self.empty.setAlignment(Qt.AlignCenter)
        v = box(QVBoxLayout(self))
        v.addWidget(scroll, 1)
        v.addWidget(self.empty)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        full_width(self.holder.layout())

    def show_checks(self, checks):
        """checks: [(document id, file name, its category's name, the category its content matches)]."""
        old = {i.doc_id: i for i in self.checks}
        self.checks = []
        for n, (doc_id, file_name, here, other) in enumerate(checks):
            item = old.pop(doc_id, None) or CheckItem(doc_id, self.c)
            item.fill(file_name, here, other)
            if self.check_list.indexOf(item) != n + 2:
                self.check_list.insertWidget(n + 2, item)
            item.setVisible(self._matches(item))
            self.checks.append(item)
        for gone in old.values():
            self.check_list.removeWidget(gone)
            gone.hide()
            gone.deleteLater()
        self.check_box.setVisible(bool(self.checks))
        self.empty.setVisible(not self.items and not self.checks)

    def show_items(self, docs, categories=None, version=None, enter=False):
        """Bring the rows in line with the waiting documents, in place. A row whose question is unchanged is
        kept, with whatever is typed, opened or focused in it; only new and changed ones are built.
        categories: {name key: category}; version: anything that changes when the category list or its counts
        do; enter: the page has just been opened (the first row takes the focus)."""
        categories = self.c.categories_by_key() if categories is None else categories
        focus = QApplication.focusWidget()
        at = next((n for n, i in enumerate(self.items) if focus and (i is focus or i.isAncestorOf(focus))), None)
        old = {tuple(i.ids): i for i in self.items}
        items, kept = [], []
        for members in group_items(docs):
            state = card_state(members, categories)
            item = old.get(tuple(d["id"] for d in members))
            if item is not None and item.state == state:
                del old[tuple(item.ids)]
                kept.append(item)
            else:
                item = (SubjectItem(members, self.c) if members[0].get("subject")
                        else DecisionItem(members, self.c, categories))
                item.state = state
                item.set_inspected(self.inspected)
            items.append(item)
        refocus = at is not None and self.items[at] in old.values()
        if refocus:
            focus.clearFocus()  # hiding the focused row hands focus down the list, and the page scrolls after it
        for gone in old.values():
            gone.setProperty("leaving", True)       # folds away where it is (instant with reduced motion)
            collapse(gone, lambda g=gone: (self.list.removeWidget(g), g.hide(), g.deleteLater()))
        for n, item in enumerate(items):
            item.number.setText(f"{n + 1}.")
            if self.list.itemAt(self._slot(n)).widget() is not item:
                self.list.removeWidget(item)
                self.list.insertWidget(self._slot(n), item)
                item.setVisible(self._matches(item))  # now, not after the next layout pass
        if version != self.version:
            for item in kept:
                item.refresh_choices()
        self.items, self.version = items, version
        self.empty.setVisible(not items and not self.checks)
        shown = [i for i in items if self._matches(i)]
        if shown and (refocus or (enter and at is None)):
            target = items[min(at or 0, len(items) - 1)]
            (target if target in shown else shown[0]).setFocus()  # where the user was, not back at the top

    def _slot(self, n):
        """The place in the list of the n-th row, counting past rows that are folding away."""
        at = seen = 0
        while at < self.list.count() - 1:
            w = self.list.itemAt(at).widget()
            if not (w is not None and w.property("leaving")):
                if seen == n:
                    break
                seen += 1
            at += 1
        return at

    def set_inspected(self, doc_id):
        """The document whose details are open beside the page (None: closed): its row is marked."""
        if doc_id != self.inspected:
            self.inspected = doc_id
            for item in self.checks + self.items:
                item.set_inspected(doc_id)

    def row_of(self, doc_id):
        return next((i for i in self.checks + self.items if doc_id in i.ids), None)

    def _matches(self, item):
        return not self.query or self.query in item.search_text

    def set_query(self, query):
        """The page's search: rows that don't match are hidden, not rebuilt."""
        self.query = query.strip().casefold()
        for item in self.items + self.checks:
            match = self._matches(item)
            if item.isHidden() == match:    # only the rows whose answer changed
                item.setVisible(match)

    def shown_documents(self):
        return (sum(len(i.ids) for i in self.items if self._matches(i))
                + sum(1 for i in self.checks if self._matches(i)))
