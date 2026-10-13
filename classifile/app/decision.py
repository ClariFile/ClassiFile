"""The "Needs your decision" page: one item per question, with one primary action each."""
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key, top_names
from classifile.app.reasons import reason_text, similar_reason
from classifile.app.widgets import (
    CHOICES_MAX, GROUP, PANEL, RELATED, CategoryPicker, ElidedLabel, box, format_icon, restyle,
)

TOP = 3
TEXT_MIN = 320  # a card's buttons sit at its right only while the name and the suggestion keep this much room
MATCH_MIN = 520  # the same for a card that offers matching categories: their buttons and reasons need more
# Why the suggested names were set aside: (button, hint, what the catalog records). Optional.
REASONS = (("Too narrow", "A lesson or a section", "too narrow"), ("Too broad", "", "too broad"),
           ("Wrong topic", "", "wrong topic"), ("Not a real name", "A fragment, a person or a file name",
                                                "not a real name"),
           ("Couldn't read the document", "", "could not read"))


def group_items(docs):
    """Waiting documents as decision items. Readable documents whose top suggestion is exactly the same (same
    name key) and whose originals are present form one group item; everything else is a single item, and so is
    every document that existing categories match (its question is its own)."""
    items, groups = [], {}
    for d in docs:
        top = top_names(d["suggestions"], 1)
        if d["status"] == "needs_decision" and not d["missing"] and top and not d.get("matches"):
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
    top = top_names(first["suggestions"], 1) if first["status"] == "needs_decision" else []
    existing = categories.get(name_key(top[0]["name"])) if top else None
    return ([(d["id"], d["file_name"]) for d in members], first["status"], first["status_reason"], first["missing"],
            first["source_path"], first["suggestions"], first["unit"],
            existing["name"] if existing else bool(categories), first.get("matches"), first.get("abstained"))


class DecisionItem(QFrame):
    def __init__(self, docs, controller, categories=None):
        """categories: {name key: category} as the catalog has them now (asked for when not given)."""
        super().__init__()
        self.setObjectName("decision")
        self.setFocusPolicy(Qt.StrongFocus)
        self.docs, self.c = docs, controller
        self.ids = [d["id"] for d in docs]
        first = docs[0]
        self.group = len(docs) > 1
        top = top_names(first["suggestions"], TOP) if first["status"] == "needs_decision" else []
        self.best = top[0]["name"] if top else ""
        # [(category name, documents it was compared with)]: the existing categories that match best, if any do
        self.matches = first.get("matches") or []
        if self.matches:
            self.best = self.matches[0][0]

        icon = QLabel()
        icon.setPixmap(format_icon(first["file_name"]).pixmap(20, 20))
        self.title = ElidedLabel(f"{len(docs)} documents with the same suggestion" if self.group
                                 else first["file_name"])
        self.title.setStyleSheet("font-weight: 600;")
        self.number = QLabel()                  # the item's place in the list, set by the page
        self.number.setObjectName("secondary")
        self.head = box(QHBoxLayout())          # "more" comes first: the same place on every item

        self.line = QLabel()
        self.line.setWordWrap(True)
        self.names = QLabel()
        self.names.setObjectName("secondary")
        self.names.setWordWrap(True)
        if self.group:
            shown = [d["file_name"] for d in docs[:6]]
            more = len(docs) - len(shown)
            self.names.setText(", ".join(shown) + (f" and {more} more" if more else ""))
        if not self.group:                      # hide(), never show(): shown without a parent it is a window
            self.names.hide()

        self.primary = QPushButton()
        self.primary.setObjectName("primary")
        self.primary.clicked.connect(self.primary_action)
        self.match_rows = QWidget()             # one row per matching category: a one-click button, then why
        rows = box(QGridLayout(self.match_rows))
        rows.setColumnStretch(1, 1)
        self.match_buttons = []
        for n, (name, count) in enumerate(self.matches):
            button = QPushButton() if n else self.primary     # the best match is the card's main action
            shown = name if len(name) <= 32 else name[:31] + "…"
            button.setText(f"File in {shown}".replace("&", "&&"))
            button.setToolTip(f"File in '{name}'")
            if n:
                button.clicked.connect(lambda _=False, name=name: self.c.file_docs(self.ids, name))
            rows.addWidget(button, n, 0)
            rows.addWidget(ElidedLabel(similar_reason(count, name), "secondary"), n, 1)
            self.match_buttons.append(button)
        if not self.matches:
            self.match_rows.hide()
        self.choose = QPushButton("Choose another…")
        self.choose.clicked.connect(self.toggle_expanded)
        self.pending = QPushButton("Leave pending")
        self.pending.clicked.connect(lambda: self.c.leave_pending(self.ids))
        self.remove = QPushButton("Remove from ClassiFile")
        self.remove.clicked.connect(lambda: self.c.remove_docs(self.ids))
        self.more_menu = QToolButton()
        self.more_menu.setObjectName("more")
        self.more_menu.setText("⋯")
        self.more_menu.setToolTip("More actions")
        self.more_menu.setPopupMode(QToolButton.InstantPopup)
        self.details = QPushButton("Details")
        self.details.setToolTip("Show or hide this document's pages beside this list")
        self.details.setCheckable(True)         # pressed while this document's details are open
        self.details.clicked.connect(
            lambda on: self.c.show_details(first["id"]) if on else self.c.close_details())
        if self.group:
            self.details.hide()
        menu = QMenu(self)
        for d in docs if self.group else ():    # a group: each member's pages
            menu.addAction(f"Details: {d['file_name']}", lambda i=d["id"]: self.c.show_details(i))
        menu.addAction("Remove from ClassiFile", lambda: self.c.remove_docs(self.ids))
        self.more_menu.setMenu(menu)
        for w in (self.more_menu, self.number, icon):
            self.head.addWidget(w)
        self.head.addWidget(self.title, 1)
        self.actions = box(QHBoxLayout())
        if not self.matches:
            self.actions.addWidget(self.primary)
        for w in (self.choose, self.pending, self.remove, self.details):
            self.actions.addWidget(w)
        self.actions.addStretch(1)

        self.all_suggestions = top[:1] if self.group else first["suggestions"]
        self.one_click = False                  # the primary button files at once (else it opens the choices)
        self.expanded = self._expanded_area()
        text = box(QVBoxLayout())
        text.addLayout(self.head)
        text.addWidget(self.line)
        text.addWidget(self.names)
        text.addWidget(self.match_rows)
        text.addStretch(1)
        self.stacked = False                    # details are open beside the page: the buttons go underneath
        self.body = box(QBoxLayout(QBoxLayout.LeftToRight), spacing=GROUP)  # description, then the controls
        self.body.addLayout(text, 1)
        self.body.addLayout(self.actions)
        v = box(QVBoxLayout(self), (0, PANEL, 0, PANEL))
        v.addLayout(self.body)
        choices = box(QHBoxLayout(), (0, RELATED, 0, 0))
        choices.addWidget(self.expanded, 100)   # up to its widest, at the left
        choices.addStretch(1)
        v.addLayout(choices)
        categories = controller.categories_by_key() if categories is None else categories
        existing = categories.get(name_key(self.best)) if self.best else None
        self.search_text = " ".join([d["file_name"] for d in docs] + [existing["name"] if existing else self.best]
                                    + [name for name, _ in self.matches]).casefold()   # what the search looks at
        self._configure(first, existing, bool(categories))

    # -- what the item asks ------------------------------------------------------------------------------------
    def _configure(self, first, existing, any_categories):
        problem = first["status"] in ("failed", "pending")
        if problem:
            self.line.setText(f"⚠ This document couldn't be read: {first['status_reason'] or 'unknown reason'}.")
            self.line.setObjectName("error")
            self._only(self.remove)
        elif first["missing"]:
            self.line.setText("⚠ The original file has moved. Locate it to file this document.")
            self.line.setObjectName("warning")
            self.primary.setText("Locate file…")
            self.primary.clicked.disconnect()
            self.primary.clicked.connect(lambda: self.c.locate_doc(first["id"]))
            self._only(self.primary, self.remove)
            self.line.setToolTip(f"It was at {first['source_path']}")
        else:
            only = "  ·  Only one suggestion found" if len(first["suggestions"]) == 1 else ""
            none = "No close match among your categories.  " if first.get("abstained") else ""
            if self.matches:    # decided from the content; new names stay under "Choose another…" (A0)
                self.line.setText("Best matches among your categories:")
                self.one_click = True
            elif existing:
                self.line.setText(f"Suggested category: {existing['name']}{only}")
                shown = existing["name"] if len(existing["name"]) <= 32 else existing["name"][:31] + "…"
                self.primary.setText(f"File in {shown}".replace("&", "&&"))
                self.primary.setToolTip(f"File in '{existing['name']}'")
                self.one_click = True
            elif self.best and not any_categories:  # the very first category: one click is enough
                self.line.setText(f"Suggested new category: {self.best}{only}")
                self.primary.setText("Create && file")
                self.primary.setToolTip(f"Create category '{self.best}' and file")
                self.one_click = True
            else:  # categories exist: a new one is never created with one click (decision record B2)
                self.line.setText(f"{none}Suggested new category: {self.best}{only}" if self.best
                                  else f"{none}No suggested name. Choose a category.")
                self.primary.setText("Choose category…")
                self.choose.hide()
            if first["status_reason"]:
                self.line.setText(self.line.text() + f"\nLast attempt: {first['status_reason']}")
            self.remove.hide()
        restyle(self.line)

    def _only(self, *keep):
        for w in (self.primary, self.choose, self.pending, self.remove):
            w.setVisible(w in keep)

    # -- where the buttons are ---------------------------------------------------------------------------------
    def set_details(self, doc_id):
        """doc_id: the document whose details are open beside the page (None: closed)."""
        self.stacked = doc_id is not None
        self.details.setChecked(doc_id == self.ids[0])
        self._arrange()

    def _arrange(self):
        """The buttons at the right of the card, using its full width; under the description while details are
        open beside the page, or when the card is too narrow for both."""
        room = self.width() - self.actions.sizeHint().width()
        side = not self.stacked and room >= (MATCH_MIN if self.matches else TEXT_MIN)
        direction = QBoxLayout.LeftToRight if side else QBoxLayout.TopToBottom
        if self.body.direction() != direction:
            self.body.setDirection(direction)

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
        self.picker.set_choices(*self.c.picker_choices(), suggestions=[
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
        """Scroll the page so the choices just opened are in view: the whole card when it fits, else from its
        top. Nothing moves when it is in view already."""
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area is None:
            return
        QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)  # the card has its new height now
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
        self.expanded.setVisible(open_)
        self.choose.setText("Hide choices" if open_ else "Choose another…")
        if open_:
            self._fill_choices()
            self.picker.field.setFocus()
            self._reveal()
        elif inside:
            self.setFocus()                     # the field went away: the keyboard stays on this card

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


class DecisionPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.items, self.query, self.version, self.details_doc = [], "", None, None
        self.holder = QWidget()                     # as wide as the page: each card's buttons are at its right
        self.list = box(QVBoxLayout(self.holder), (0, 0, GROUP, 0), 0)  # room for the scroll bar
        self.list.addStretch(1)                     # always last; the cards go before it
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

    def show_items(self, docs, categories=None, version=None, enter=False):
        """Bring the cards in line with the waiting documents, in place. A card whose question is unchanged is
        kept, with whatever is typed, opened or focused in it; only new and changed ones are built.
        categories: {name key: category}; version: anything that changes when the category list or its counts
        do; enter: the page has just been opened (the first card takes the focus)."""
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
                item = DecisionItem(members, self.c, categories)
                item.state = state
                item.set_details(self.details_doc)
            items.append(item)
        refocus = at is not None and self.items[at] in old.values()
        if refocus:
            focus.clearFocus()  # hiding the focused item hands focus down the list, and the page scrolls after it
        for gone in old.values():
            self.list.removeWidget(gone)
            gone.hide()
            gone.deleteLater()
        for n, item in enumerate(items):
            item.number.setText(f"{n + 1}.")
            if self.list.itemAt(n).widget() is not item:
                self.list.removeWidget(item)
                self.list.insertWidget(n, item)
                item.setVisible(self._matches(item))  # now, not after the next layout pass
        if version != self.version:
            for item in kept:
                item.refresh_choices()
        self.items, self.version = items, version
        self.empty.setVisible(not items)
        shown = [i for i in items if self._matches(i)]
        if shown and (refocus or (enter and at is None)):
            target = items[min(at or 0, len(items) - 1)]
            (target if target in shown else shown[0]).setFocus()  # where the user was, not back at the top

    def set_details(self, doc_id):
        """The document whose details are open beside the page (None: closed). The cards put their buttons under
        the description while they are, and that document's Details button stays pressed."""
        if doc_id != self.details_doc:
            self.details_doc = doc_id
            for item in self.items:
                item.set_details(doc_id)

    def _matches(self, item):
        return not self.query or self.query in item.search_text

    def set_query(self, query):
        """The page's search: cards that don't match are hidden, not rebuilt."""
        self.query = query.strip().casefold()
        for item in self.items:
            match = self._matches(item)
            if item.isHidden() == match:    # only the cards whose answer changed
                item.setVisible(match)

    def shown_documents(self):
        return sum(len(i.ids) for i in self.items if self._matches(i))
