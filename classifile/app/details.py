"""The details panel: opened only on request (Details, the right-click menu or Space)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from classifile.analysis.candidates import name_key, top_names
from classifile.app.reasons import reason_text
from classifile.app.widgets import GROUP, PANEL, RELATED, Collapsible, ElidedLabel, Preview, box, wrappable


def _wrapped_label():
    label = QLabel()
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class DetailsPanel(QFrame):
    def __init__(self, controller):
        super().__init__()
        self.setObjectName("details")
        self.c = controller
        self.doc_id = None
        self.title = ElidedLabel()
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        close = QPushButton("✕")
        close.setObjectName("icon")
        close.setToolTip("Close details (Space)")
        close.clicked.connect(self.c.close_details)
        head = box(QHBoxLayout())
        head.addWidget(self.title, 1)
        head.addWidget(close)
        self.preview = Preview(fit_width=True)
        self.preview.expand_requested.connect(lambda: self.c.expand_preview(self.doc_id, self.preview.page))
        self.facts = _wrapped_label()
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
        self.locations = _wrapped_label()
        self.locations_section = Collapsible("File locations", self.locations)
        self.why = _wrapped_label()
        self.why_section = Collapsible("Why this category?", self.why)
        body = QWidget()                        # scrolls when the window is short; the heading stays
        v = box(QVBoxLayout(body), (PANEL, 0, PANEL, PANEL), GROUP)
        v.addWidget(self.preview)
        v.addWidget(self.facts)
        v.addLayout(buttons)
        sections = box(QVBoxLayout(), spacing=0)  # the two collapsed sections belong together
        sections.addWidget(self.locations_section)
        sections.addWidget(self.why_section)
        v.addSpacing(RELATED)                   # actions, then the sections
        v.addLayout(sections)
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
        # CP3's "Belongs to" actions will be added here; nothing is shown before they work.

    def show_doc(self, doc_id):
        self.doc_id = doc_id
        d = self.c.document_row(doc_id)
        if d is None:
            return
        self.title.setText(d["file_name"])
        self.preview.show_document(self.c.preview_source(doc_id), self.c.first_lines(doc_id),
                                   "" if d["status"] == "filed" or d["file_name"].lower().endswith(".pdf")
                                   else "File it, then use Open to see the full document.")
        filed = d["status"] == "filed"
        missing = not filed and self.c.org.original_missing(doc_id)
        facts = [f"Category: {d['category']}" if d.get("category") else "Category: —"]
        if filed:
            facts.append(f"Filed: {self.c.short_date(d['filed_at'])}" if d.get("filed_at") else "Filed")
            if d.get("copy_status") == "edited":
                facts.append("This copy was changed after filing and is flagged.")
        else:
            facts.append("Waiting for a decision" if d["status"] == "needs_decision"
                         else f"Couldn't be read: {d['status_reason'] or 'unknown reason'}")
            if missing:
                facts.append("The original file has moved.")
        self.facts.setText("\n".join(facts))
        has_copy = filed and self.c.filed_copy(doc_id) is not None
        self.open_button.setVisible(has_copy)
        self.folder_button.setVisible(has_copy)
        self.locate_button.setVisible(missing)
        locations = []
        if d.get("copy_path"):
            locations.append(f"Copy: {wrappable(d['copy_path'])}")
        locations.append(f"Original: {wrappable(d['source_path'])}")
        self.locations.setText("\n".join(locations))
        analysis = self.c.org.catalog.analysis(doc_id) or {}
        suggestions, unit = analysis.get("suggestions", []), analysis.get("unit", "page")
        if filed:
            match = next((s for s in suggestions if name_key(s["name"]) == name_key(d["category"] or "")), None)
            reason = reason_text(match["evidence"], unit) if match else ""
            self.why.setText(f"“{d['category']}” was suggested because it appears {reason}." if reason
                             else f"You chose “{d['category']}”.")
        else:
            lines = [f"{s['name']}: {reason_text(s['evidence'], unit) or 'no page reference'}"
                     for s in top_names(suggestions)]
            self.why.setText("\n".join(lines) or "No suggested names.")
        self.why_section.setVisible(bool(suggestions) or filed)
