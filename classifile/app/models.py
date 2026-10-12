"""The document list and the sidebar's categories as models that are updated in place.

A view over one of these keeps its selection and scroll position when the catalog changes: sync() touches only
the rows that differ. Sorting, the current view (all, recent, one category) and the search are a filter over the
rows already loaded, so a search key or a change of view reads nothing from the catalog.
"""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QGuiApplication

from classifile.app.widgets import ROW, format_icon, status_icon, status_word

DOC = Qt.UserRole          # a document's id (None while it is still being read) or a category's id
ALL, RECENT, CATEGORY = "all", "recent", "category"
SORTS = ("Newest first", "Oldest first", "Name A–Z")


class RowsModel(QAbstractTableModel):
    """Rows (dicts with a "key") shown through cell(row, column, role)."""
    HEADERS = ()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows, self.at = [], {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        return self.HEADERS[section] if orientation == Qt.Horizontal and role == Qt.DisplayRole else None

    def data(self, index, role=Qt.DisplayRole):
        return self.cell(self.rows[index.row()], index.column(), role) if index.isValid() else None

    def get(self, key):
        i = self.at.get(key)
        return None if i is None else self.rows[i]

    def sync(self, rows):
        """Rows that are gone leave, changed ones are redrawn, new ones join at the end (the views sort)."""
        new = {r["key"]: r for r in rows}
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i]["key"] not in new:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self.rows[i]
                self.endRemoveRows()
        self.at = {r["key"]: i for i, r in enumerate(self.rows)}
        last = len(self.HEADERS) - 1
        for key, r in new.items():
            i = self.at.get(key)
            if i is not None and self.rows[i] != r:
                self.rows[i] = r
                self.dataChanged.emit(self.index(i, 0), self.index(i, last))
        added = [r for key, r in new.items() if key not in self.at]
        if added:
            self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(added) - 1)
            self.rows += added
            self.endInsertRows()
            self.at = {r["key"]: i for i, r in enumerate(self.rows)}


class DocumentModel(RowsModel):
    """Every document, and the files still being read (id None). Rows carry "shown_status"."""
    HEADERS = ("Name", "Category", "Status", "Date added")

    def cell(self, r, column, role):
        status = r["shown_status"]
        if role == Qt.DisplayRole:
            return (r["file_name"], r["category"] or "—", status_word(status), r["date"])[column]
        if role == Qt.DecorationRole:
            return format_icon(r["file_name"]) if column == 0 else status_icon(status) if column == 2 else None
        if role == Qt.ToolTipRole:
            return r["file_name"] if column == 0 else (r.get("status_reason") or None) if column == 2 else None
        if role == Qt.SizeHintRole:
            return QSize(0, ROW)
        if role == DOC:
            return r["id"]
        return None

    def flags(self, index):
        if index.isValid() and self.rows[index.row()]["id"] is None:
            return Qt.ItemIsEnabled            # still being read: nothing to select yet
        return super().flags(index)


class DocumentFilter(QSortFilterProxyModel):
    """Which documents the list shows, and in what order: the view, the search text and the sort."""

    def __init__(self, model):
        super().__init__(model)
        self.view, self.category, self.since, self.query, self.order = ALL, None, "", "", SORTS[0]
        self.setSourceModel(model)
        self.setDynamicSortFilter(True)
        self.sort(0)

    def show(self, view=None, category=None, since=None, query=None, order=None):
        """Change what is shown; anything not given stays. Without a new order nothing is sorted again: only the
        rows that come or go are touched."""
        shown = (self.view if view is None else view, self.category if view is None else category,
                 self.since if since is None else since, self.query if query is None else query.strip().casefold())
        if order is not None and order != self.order:
            self.order = order
            (self.view, self.category, self.since, self.query) = shown
            self.invalidate()
        elif shown != (self.view, self.category, self.since, self.query):
            self.beginFilterChange()
            (self.view, self.category, self.since, self.query) = shown
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def in_view(self, r):
        if self.view == CATEGORY:
            return r["id"] is not None and r.get("category_id") == self.category
        if self.view == RECENT:
            return r["id"] is None or (r["imported_at"] or "") >= self.since
        return True

    def matches(self, r):
        """The search looks at the file name and the category."""
        return not self.query or self.query in r["file_name"].casefold() \
            or self.query in (r["category"] or "").casefold()

    def total(self):
        """Documents in the view, whatever the search says."""
        return sum(1 for r in self.sourceModel().rows if self.in_view(r))

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        return self.in_view(r) and self.matches(r)

    def lessThan(self, left, right):
        rows = self.sourceModel().rows
        a, b = rows[left.row()], rows[right.row()]
        name = lambda r: (r["file_name"].casefold(), str(r["key"]))
        if self.order == "Name A–Z":
            return name(a) < name(b)
        at_a, at_b = a["imported_at"] or "", b["imported_at"] or ""
        if self.order == "Oldest first":
            return (at_a, name(a)) < (at_b, name(b))
        if (a["id"] is None) != (b["id"] is None):
            return a["id"] is None             # newest first: what is still being read comes before everything
        return at_a > at_b if at_a != at_b else name(a) < name(b)


class CategoryModel(RowsModel):
    """The sidebar: a category's name and how many documents it holds."""
    HEADERS = ("", "")      # never shown; a title would only widen the count column

    def cell(self, r, column, role):
        if role == Qt.DisplayRole:
            return r["name"] if column == 0 else str(r["count"])
        if role == Qt.ToolTipRole:
            return r["name"]
        if role == Qt.TextAlignmentRole and column == 1:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and column == 1:
            return QGuiApplication.palette().placeholderText()   # quieter than the name
        if role == DOC:
            return r["key"]
        return None


def sorted_by_name(model):
    """A filter over the categories: A to Z, ignoring case. (The sidebar's find field will narrow it later.)"""
    proxy = QSortFilterProxyModel(model)
    proxy.setSourceModel(model)
    proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
    proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
    proxy.setDynamicSortFilter(True)
    proxy.sort(0)
    return proxy
