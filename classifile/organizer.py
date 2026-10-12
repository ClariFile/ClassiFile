"""GUI-independent workflow: import checks -> read + analyze -> record -> user decision -> verified copy."""
import os
from pathlib import Path

from classifile.analysis.candidates import analyze, name_key
from classifile.analysis.summary import summarize
import json

from classifile.copies.engine import (
    CopyError, _Crash, _retire_old_copy, make_copy, move_copies, recover, sanitize_folder_name, settle_category,
)
from classifile.reader import READERS, read_document, sha256_file

CLOUD_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud drive", "iclouddrive", "box sync")


def is_cloud_synced(path):
    """Heuristic note only; nothing is special-cased yet."""
    p = str(Path(path).resolve()).casefold()
    roots = [os.environ.get(k) for k in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")]
    return any(r and p.startswith(str(Path(r).resolve()).casefold()) for r in roots) or any(
        m in part for part in Path(p).parts for m in CLOUD_MARKERS)


def read_and_analyze(path):
    """Pure work for a worker process: no catalog access. Returns (result, analysis, hidden summary)."""
    result = read_document(path)
    if result.status != "ok":
        return result, None, None
    name = Path(path).name
    analysis = analyze(result.record, name)
    return result, analysis, summarize(result.record, analysis, name)


class Organizer:
    def __init__(self, catalog):
        self.catalog = catalog

    @property
    def output_root(self):
        root = self.catalog.get_setting("output_root")
        return Path(root) if root else None

    def set_output_root(self, path, move=False):
        """Choose the output folder. With move=True, ClassiFile's existing copies are moved into it by the
        verified-copy rules (edited copies stay and are flagged). Returns [(copy_id, outcome)] for the move."""
        path = Path(path).resolve()
        if not path.is_dir():
            raise ValueError("output folder does not exist")
        report = move_copies(self.catalog, path) if move else []
        self.catalog.set_setting("output_root", str(path))
        return report

    def copies_to_move(self, new_root):
        """Published copies that are not already inside new_root."""
        new_root = Path(new_root).resolve()
        return [c for c in self.catalog.copies("published") if not Path(c["path"]).resolve().is_relative_to(new_root)]

    def remove(self, doc_ids):
        """Remove waiting documents from ClassiFile: their stored text and analysis go; originals are untouched."""
        for doc_id in doc_ids:
            self.catalog.remove_document(doc_id)

    def startup(self):
        """Recover interrupted copies and reconcile document statuses with copy records."""
        report = recover(self.catalog, self.output_root)
        for m in self.catalog.pending_moves():  # a move that had started is finished, or dropped if it cannot be
            try:
                self.move(m["document_id"], m["category_id"])
            except (CopyError, ValueError):
                self.catalog.end_move(m["document_id"])
        if self.output_root:
            for cat_id in self._renaming():      # a rename that had started: the rest of its copies follow
                if self.catalog.category(cat_id):
                    settle_category(self.catalog, cat_id, self.output_root)
            self.catalog.set_setting("renaming", "[]")
        for d in self.catalog.all("SELECT d.id, d.status, m.category_id FROM documents d JOIN memberships m"
                                  " ON m.document_id = d.id AND m.role = 'primary' AND m.status = 'active'"):
            row = self.catalog.document(d["id"])
            if self.catalog.published_copy(row["sha256"], d["category_id"]) or self.catalog.one(
                    "SELECT 1 FROM copies WHERE snapshot_sha256 = ? AND category_id = ? AND status = 'edited'",
                    row["sha256"], d["category_id"]):  # an edited copy is still the filed copy
                if d["status"] != "filed":
                    self.catalog.set_document_status(d["id"], "filed")
            elif not self.catalog.one("SELECT 1 FROM copies WHERE document_id = ? AND category_id = ? AND status IN"
                                      " ('missing', 'moved')", d["id"], d["category_id"]):
                # Never filed (the copy failed or the run stopped): undo the half-done placement.
                self.catalog.remove_primary(d["id"])
                self.catalog.set_document_status(d["id"], "needs_decision",
                                                 "The last filing didn't finish. Choose a category again.")
        # Categories left behind by a filing that failed or stopped: a failed copy attempt and no documents.
        for row in self.catalog.all("SELECT DISTINCT category_id FROM copies WHERE status = 'failed'"):
            self.catalog.discard_unused_category(row["category_id"])
        return report

    def check_import(self, path):
        """None if the file may be imported, else a reason."""
        path = Path(path).resolve()
        root = self.output_root
        if path.suffix.lower() not in READERS:
            return "unsupported file type (PDF, PPTX, DOCX and ODT are supported)"
        if not path.is_file():
            return "not a file"
        if root is None:
            return "choose an output folder first"
        if path.is_relative_to(root):
            return "already in the output folder"
        if root.is_relative_to(path.parent):
            return "the output folder is inside this file's folder"
        return None

    def record(self, path, result, analysis, summary=None):
        """Persist a read result. Returns (doc_id or None, note)."""
        if result.sha256 is None:
            return None, result.reason  # nothing identifiable to record
        known = self.catalog.snapshot_by_hash(result.sha256)
        if known:
            doc_id = known["document_id"]
            # A failed read (e.g. a timeout) is retried by importing the same bytes again; a failed copy is not.
            if self.catalog.document(doc_id)["status"] == "failed" and not self.catalog.active_primary(doc_id):
                self.catalog.replace_extraction(doc_id, result, analysis, summary)
                return doc_id, "read again"
            return doc_id, "already imported"
        return self.catalog.add_document(result, Path(path).resolve(), analysis, summary), None

    def create_category(self, name):
        name = " ".join(name.split())
        if not name:
            raise ValueError("category name is empty")
        if self.catalog.category_by_key(name_key(name)):
            raise ValueError("a category with this name already exists; choose it from the list")
        folder = base = sanitize_folder_name(name)
        n = 2
        while self.catalog.folder_taken(folder):
            folder = f"{base} ({n})"
            n += 1
        return self.catalog.add_category(name, name_key(name), folder)

    def file(self, doc_id, cat_id):
        """User-confirmed primary placement plus verified copy. Returns (outcome, path).
        Nothing is recorded unless the copy succeeds: on failure the document stays waiting, with a plain reason."""
        doc = self.catalog.document(doc_id)
        current = self.catalog.active_primary(doc_id)
        if current and current["category_id"] != cat_id:
            raise ValueError("This document is already filed. Use Move to… to change its category.")
        if current and doc["status"] == "filed":
            return make_copy(self.catalog, doc_id, doc["sha256"], doc["source_path"], cat_id, self.output_root)
        if doc["status"] in ("pending", "failed"):
            raise ValueError("This document couldn't be read, so it can't be filed. Remove it, or import it again.")
        root = self.output_root
        source = Path(doc["source_path"])
        problem = None
        if root is None or not root.is_dir():
            problem = (f"The output folder {root} can't be found. Choose it again with Change…" if root
                       else "Choose an output folder first.")
        elif not source.is_file():
            problem = f"The original file is no longer at {source}. Import it again from its new location."
        if problem:
            self.catalog.set_document_status(doc_id, "needs_decision", problem)
            raise CopyError(problem)
        folder = root / self.catalog.category(cat_id)["folder_name"]
        folder_existed = folder.exists()
        self.catalog.add_primary(doc_id, cat_id, "user-confirmed")
        try:
            outcome, path = make_copy(self.catalog, doc_id, doc["sha256"], source, cat_id, root)
        except CopyError as e:
            self.catalog.remove_primary(doc_id)  # never half-done: no membership without a copy
            if not folder_existed:
                try:
                    folder.rmdir()  # only the folder this attempt created, and only while it is empty
                except OSError:
                    pass
            self.catalog.set_document_status(doc_id, "needs_decision", str(e))
            raise
        self.catalog.set_document_status(doc_id, "filed")
        return outcome, path

    # -- regrouping: move, rename, delete (decision record B5) -------------------------------------------------
    def _verified_copy(self, doc, cat_id):
        """The document's published copy in a category, if the file is still exactly what was filed. A copy that
        is gone or was edited is flagged and never used."""
        c = self.catalog.published_copy(doc["sha256"], cat_id)
        if not c:
            return None
        path = Path(c["path"])
        if not path.exists():
            self.catalog.update_copy(c["id"], status="missing")
            return None
        if sha256_file(path) != c["hash_at_creation"]:
            self.catalog.update_copy(c["id"], status="edited")
            return None
        return path

    def move(self, doc_id, cat_id, _crash_at=None):
        """Replace a filed document's primary category. The new copy is made from a verified copy (or from the
        original if its hash still matches) and verified; only then does the placement change (user-corrected) and
        the old copy go, and only if it is unchanged: an edited copy stays and is flagged.
        Returns "moved" | "edited" (an edited copy stayed behind) | "same"."""
        doc = self.catalog.document(doc_id)
        current = self.catalog.active_primary(doc_id)
        if doc is None or doc["status"] != "filed" or not current:
            raise ValueError("Only filed documents can be moved.")
        root = self.output_root
        if root is None or not root.is_dir():
            raise CopyError(f"The output folder {root} can't be found. Choose it again with Change…")
        if current["category_id"] == cat_id and not self.catalog.one(
                "SELECT 1 FROM moves WHERE document_id = ?", doc_id):
            return "same"
        edited = lambda: len(self.catalog.document_copies(doc_id, "edited"))
        before = edited()
        self.catalog.start_move(doc_id, cat_id)  # the intent first: startup finishes a move that stopped
        try:
            if current["category_id"] != cat_id:
                if not self._verified_copy(doc, cat_id):  # a copy already there is used only if it verifies
                    source = self._verified_copy(doc, current["category_id"]) or Path(doc["source_path"])
                    if not source.is_file():
                        raise CopyError("Neither the filed copy nor the original file can be found, so the "
                                        "document stays where it is.")
                    make_copy(self.catalog, doc_id, doc["sha256"], source, cat_id, root)
                if _crash_at == "after-copy":
                    raise _Crash
                self.catalog.replace_primary(doc_id, cat_id, "user-corrected")
                if _crash_at == "after-switch":
                    raise _Crash
            for c in self.catalog.document_copies(doc_id):
                if c["category_id"] != cat_id:
                    _retire_old_copy(self.catalog, c)
        except CopyError:
            self.catalog.end_move(doc_id)
            raise
        self.catalog.end_move(doc_id)
        return "edited" if edited() > before else "moved"

    def _renaming(self):
        return json.loads(self.catalog.get_setting("renaming", "[]"))

    def rename_category(self, cat_id, name, _crash_at=None):
        """Rename a category; only ClassiFile's copies move into the renamed folder.
        Returns the old folders that still hold other files (left in place)."""
        name = " ".join(name.split())
        cat = self.catalog.category(cat_id)
        if not name:
            raise ValueError("category name is empty")
        other = self.catalog.category_by_key(name_key(name))
        if other and other["id"] != cat_id:
            raise ValueError(f"A category named '{other['name']}' already exists. To combine them, move the "
                             "documents there instead.")
        folder = cat["folder_name"]
        base = sanitize_folder_name(name)
        if base.casefold() != folder.casefold():  # ponytail: a change of case only keeps the folder's spelling
            folder, n = base, 2
            while self.catalog.folder_taken(folder):
                folder, n = f"{base} ({n})", n + 1
        self.catalog.set_setting("renaming", json.dumps(self._renaming() + [cat_id]))  # startup finishes it
        self.catalog.rename_category(cat_id, name, name_key(name), folder)
        leftover = settle_category(self.catalog, cat_id, self.output_root, _crash_at) if self.output_root else []
        self.catalog.set_setting("renaming", json.dumps([c for c in self._renaming() if c != cat_id]))
        return leftover

    def delete_category(self, cat_id):
        """Delete a category that holds no documents. Its folder is removed only if it is empty.
        Returns the folder if it stayed (it holds other files), else None."""
        cat = self.catalog.category(cat_id)
        self.catalog.delete_category(cat_id)  # refuses while documents are in it
        folder = self.output_root / cat["folder_name"] if self.output_root else None
        if folder is None or not folder.is_dir():
            return None
        try:
            folder.rmdir()
            return None
        except OSError:
            return folder

    def original_missing(self, doc_id, source_path=None):
        """source_path: where the catalog says the original is, when the caller has it already."""
        return not Path(source_path or self.catalog.document(doc_id)["source_path"]).is_file()

    def locate(self, doc_id, path):
        """Point a document at its original's new location, if it is the same file (same content hash).
        Only reads the file. Raises ValueError with a plain reason otherwise."""
        path = Path(path).resolve()
        doc = self.catalog.document(doc_id)
        if not path.is_file():
            raise ValueError(f"There's no file at {path}.")
        if self.output_root and path.is_relative_to(self.output_root):
            raise ValueError("That file is inside the output folder. Choose the original, not a filed copy.")
        try:
            same = sha256_file(path) == doc["sha256"]
        except OSError:
            raise ValueError(f"ClassiFile couldn't read {path}. Check that it isn't open elsewhere, then try again.")
        if not same:
            raise ValueError("That file's content is different from the one imported, so it's another version. "
                             "Import it as a new document instead.")
        self.catalog.update_source_path(doc_id, path)
        if doc["status"] == "needs_decision":
            self.catalog.set_document_status(doc_id, "needs_decision", None)  # the "no longer at" note is resolved
        return path

    def discard_unused_category(self, cat_id):
        """A category with no documents (e.g. created for a filing that failed) is removed again."""
        return self.catalog.discard_unused_category(cat_id)
