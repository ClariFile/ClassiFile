"""The details panel: opened only on request (a row, Details, the right-click menu or Space). Who the document is
and where it is (or would be) filed come first, then its pages, then why, then the full paths."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from classifile.analysis.candidates import name_key, top_names
from classifile.app.reasons import new_folder_reason, reason_text, similar_reason
from classifile.app.widgets import (
    GROUP, PANEL, RELATED, TIGHT, Collapsible, ElidedLabel, Preview, box, wrappable, wrapped,
)



def review_state(row):
    """How a filed document got where it is, in words (from the membership's provenance)."""
    if row.get("provenance") == "machine-assigned":
        return "Filed automatically · not reviewed yet"
    if row.get("provenance") == "user-corrected":
        return "Moved here by you"
    return "Filed automatically · confirmed by you" if row.get("auto_json") else "Filed by you"


def _wrapped_label(object_name=None):
    label = wrapped(QLabel())
    label.setTextFormat(Qt.PlainText)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if object_name:
        label.setObjectName(object_name)
    return label


class Field(QWidget):
    """A caption over its value; the value wraps and can be selected."""

    def __init__(self, caption, strong=False):
        super().__init__()
        self.caption = QLabel(caption)
        self.caption.setObjectName("secondary")
        self.value = _wrapped_label("strong" if strong else None)
        box(QVBoxLayout(self), spacing=TIGHT // 2).addWidget(self.caption)
        self.layout().addWidget(self.value)

    def set(self, value, caption=None):
        if caption:
            self.caption.setText(caption)
        self.value.setText(value or "")
        self.setVisible(bool(value))


class DetailsPanel(QFrame):
    def __init__(self, controller):
        super().__init__()
        self.setObjectName("details")
        self.c = controller
        self.doc_id = None
        self.shown = None       # set by the window: what it last asked for, so an unchanged document isn't redrawn
        self.back = QPushButton("‹ Back to list")   # shown while the panel lies over the list
        self.back.setObjectName("quiet")
        self.back.clicked.connect(self.c.close_details)
        self.back.hide()
        self.title = ElidedLabel()
        self.title.setObjectName("heading")
        close = QPushButton("✕")
        close.setObjectName("icon")
        close.setToolTip("Close details (Esc)")
        close.setAccessibleName("Close details")
        close.clicked.connect(self.c.close_details)
        head = box(QHBoxLayout())
        head.addWidget(self.back)
        head.addWidget(self.title, 1)
        head.addWidget(close)
        self.hint = _wrapped_label("secondary")
        self.name = Field("File name")
        self.same_name = QLabel("Filed under the same name.")
        self.same_name.setObjectName("secondary")
        self.copy_name = Field("Filed as")
        self.category = Field("Category", strong=True)
        self.also = Field("Also in")
        self.state = Field("Status")
        fields = box(QVBoxLayout(), spacing=RELATED)
        for w in (self.name, self.same_name, self.copy_name, self.category, self.also, self.state):
            fields.addWidget(w)
        self.preview = Preview(fit_width=True)
        self.preview.expand_requested.connect(lambda: self.c.expand_preview(self.doc_id, self.preview.page))
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(lambda: self.c.open_doc(self.doc_id))
        self.folder_button = QPushButton("Show in folder")
        self.folder_button.clicked.connect(lambda: self.c.show_doc_in_folder(self.doc_id))
        self.locate_button = QPushButton("Locate file…")
        self.locate_button.clicked.connect(lambda: self.c.locate_doc(self.doc_id))
        buttons = box(QHBoxLayout())
        for b in (self.open_button, self.folder_button, self.locate_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.why_caption = QLabel("WHY THIS CATEGORY")
        self.why_caption.setObjectName("section")
        self.why = _wrapped_label()
        self.locations = _wrapped_label()
        self.locations_section = Collapsible("File locations", self.locations)
        body = QWidget()                        # scrolls when the window is short; the heading stays
        v = box(QVBoxLayout(body), (PANEL, 0, PANEL, PANEL), GROUP)
        v.addWidget(self.hint)
        v.addLayout(fields)
        why = box(QVBoxLayout(), spacing=TIGHT)  # before the preview: seen without scrolling
        why.addWidget(self.why_caption)
        why.addWidget(self.why)
        v.addLayout(why)
        v.addWidget(self.preview)
        v.addLayout(buttons)
        v.addWidget(self.locations_section)
        v.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Always there: a bar that came and went changed the width, the page picture was fitted again at
        # another height, and the bar went or came again (the panel bounced when a section was opened).
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll = scroll
        scroll.setWidget(body)
        outer = box(QVBoxLayout(self), (0, PANEL, 0, 0), GROUP)
        head.setContentsMargins(PANEL, 0, PANEL, 0)
        outer.addLayout(head)
        outer.addWidget(scroll, 1)

    def set_overlay(self, over):
        """over: the panel lies over the list (a narrow window), so it says how to get back."""
        self.back.setVisible(over)

    def _all_parts(self):
        return (self.name, self.same_name, self.copy_name, self.category, self.also, self.state, self.open_button,
                self.folder_button, self.locate_button, self.why_caption, self.why, self.locations_section)

    def show_nothing(self):
        """Open with no document selected: say what to do."""
        self.doc_id, self.shown = None, None
        self.title.setText("Details")
        self.preview.show_document(None, [])
        self.hint.setText("Select a document to see its pages and details here.")
        self.hint.show()
        for w in self._all_parts():
            w.hide()

    def show_doc(self, doc_id):
        if doc_id != self.doc_id:
            self.scroll.verticalScrollBar().setValue(0)     # another document starts at its top
        self.doc_id, self.shown = doc_id, None
        d = self.c.document_row(doc_id)
        if d is None:
            return
        self.hint.hide()
        self.locations_section.show()
        self.title.setText(d["file_name"])
        filed = d["status"] == "filed"
        missing = not filed and self.c.org.original_missing(doc_id)
        waiting = next((w for w in self.c.waiting_docs if w["id"] == doc_id), None) if not filed else None
        copy = Path(d["copy_path"]).name if filed and d.get("copy_path") else None
        self.name.set(d["file_name"])
        self.same_name.setVisible(copy == d["file_name"])
        self.copy_name.set(copy if copy != d["file_name"] else None)
        if filed:
            self.category.set(d["category"] + (" · New (named by ClassiFile)" if d.get("app_named") else ""),
                              "Filed in")
            self.also.set(", ".join(name for _, name in self.c.org.catalog.secondary_categories(doc_id)))
            state = review_state(d)
            if d.get("filed_at"):
                state += f" · {self.c.short_date(d['filed_at'])}"
            if d.get("copy_status") == "edited":
                state += "\nThis copy was changed after filing and is flagged."
        else:
            suggested = self._suggested(waiting)
            new = bool(suggested) and not waiting.get("matches") and self.c.existing_category(suggested) is None
            self.category.set(suggested, "Suggested new category" if new and waiting["suggestions"]
                              else "Suggested category")
            self.also.set(None)
            state = ("Waiting for your decision · not filed yet" if d["status"] == "needs_decision"
                     else f"Couldn't be read: {wrappable(d['status_reason'] or 'unknown reason')}")
            if missing:
                state += "\nThe original file has moved. Locate it to file this document."
        self.state.set(state)
        self.preview.show_document(self.c.preview_source(doc_id), self.c.first_lines(doc_id),
                                   "" if filed or d["file_name"].lower().endswith(".pdf")
                                   else "File it, then use Open to see the full document.")
        has_copy = filed and self.c.filed_copy(doc_id) is not None
        self.open_button.setVisible(has_copy)
        self.folder_button.setVisible(has_copy)
        self.locate_button.setVisible(missing)
        locations = [f"Original: {wrappable(d['source_path'])}"]
        if d.get("copy_path"):
            locations.append(f"Filed copy: {wrappable(d['copy_path'])}")
        self.locations.setText("\n".join(locations))
        self.why.setText(self._why(d, waiting))
        for w in (self.why_caption, self.why):
            w.setVisible(bool(self.why.text()))

    @staticmethod
    def _suggested(waiting):
        """What the document's row offers to file it in: the best matching category, else the top suggested name."""
        if not waiting or waiting["status"] != "needs_decision":
            return None
        if waiting.get("matches"):
            return waiting["matches"][0][0]
        top = top_names(waiting["suggestions"], 1)
        return top[0]["name"] if top else "No suggestion: choose a category"

    def _why(self, d, waiting):
        if d["status"] == "filed":
            auto = json.loads(d.get("auto_json") or "{}")
            if auto.get("new_folder"):
                return f"Filed automatically in a new folder. {new_folder_reason(auto.get('words', []))}."
            if auto.get("documents"):
                return f"Filed automatically. {similar_reason(auto['documents'], d['category'], auto.get('words', ()))}."
            analysis = self.c.org.catalog.analysis(d["id"]) or {}
            match = next((s for s in analysis.get("suggestions", [])
                          if name_key(s["name"]) == name_key(d["category"] or "")), None)
            reason = reason_text(match["evidence"], analysis.get("unit", "page")) if match else ""
            return (f"“{d['category']}” was suggested because it appears {reason}." if reason
                    else f"You chose “{d['category']}”.")
        if not waiting:
            return ""
        lines = [f"{similar_reason(n, name, words)}." for name, n, words in waiting.get("matches") or ()]
        lines += [f"{s['name']}: {reason_text(s['evidence'], waiting['unit']) or 'no page reference'}"
                  for s in top_names(waiting["suggestions"])]
        return "\n".join(lines)
