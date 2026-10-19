"""GUI-independent workflow: import checks -> read + analyze -> record -> user decision -> verified copy."""
import os
import sys
from pathlib import Path

from classifile import evaluation, matching
from classifile.analysis.candidates import analyze, name_key, top_names
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


def in_program_folder(path):
    """True inside the installed app's own folder, where an update replaces files and an uninstall removes them."""
    if not getattr(sys, "frozen", False):
        return False
    return Path(path).resolve().is_relative_to(Path(sys.executable).resolve().parent)


class Organizer:
    def __init__(self, catalog):
        self.catalog = catalog
        self._matcher = False       # False: not loaded yet; None: no usable model; else (version row, Matcher)
        self._ranked = {}           # doc_id -> its categories ranked by the model in use
        self._counts = {}           # doc_id -> matching.terms() of its stored text
        self._words = {}            # (model version, doc_id, category id) -> the key words a card gives
        self._groups = (None, [])   # the last new_subject_groups() question and its answer

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
        if in_program_folder(path):
            raise ValueError("output folder is inside ClassiFile's program folder")
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
        # An "also belongs to" that stopped before its copy was made is undone: no membership without a copy.
        for m in self.catalog.all(
                "SELECT m.document_id, m.category_id FROM memberships m WHERE m.role = 'secondary' AND m.status ="
                " 'active' AND NOT EXISTS (SELECT 1 FROM copies c WHERE c.document_id = m.document_id AND"
                " c.category_id = m.category_id AND c.status NOT IN ('failed', 'planned'))"):
            self.catalog.remove_secondary(m["document_id"], m["category_id"])
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
            if self.catalog.document(doc_id)["status"] == "example":   # learned from a folder; now to be filed
                self.catalog.update_source_path(doc_id, Path(path).resolve())
                self.catalog.set_document_status(doc_id, "needs_decision")
                return doc_id, None
            # A failed read (e.g. a timeout) is retried by importing the same bytes again; a failed copy is not.
            if self.catalog.document(doc_id)["status"] in ("failed", "pending") and not self.catalog.active_primary(doc_id):
                self.catalog.replace_extraction(doc_id, result, analysis, summary)
                return doc_id, "read again"
            return doc_id, "already imported"
        return self.catalog.add_document(result, Path(path).resolve(), analysis, summary), None

    # -- "Learn from my existing folders" (decision record 2.9) -------------------------------------------------
    def scan_folder(self, root):
        """The user's organized folder, as proposed categories: [(subfolder, [its supported files, in any folder
        below it])], subfolders without one left out. Only the folder listing is read. Raises ValueError with a
        plain reason."""
        root, out = Path(root).resolve(), self.output_root
        if out and root.is_relative_to(out):
            raise ValueError("This is ClassiFile's output folder. Choose the folder where you keep your own documents.")
        try:
            subs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: (p.name.casefold(), p.name))
            found = [(sub, sorted(p for p in sub.rglob("*") if p.suffix.lower() in READERS and p.is_file()
                                  and not (out and p.resolve().is_relative_to(out)))) for sub in subs]
        except OSError:
            raise ValueError("ClassiFile couldn't read this folder.") from None
        return [(sub, files) for sub, files in found if files]

    def category_for(self, name):
        """The category a learned folder goes to: an existing one of that name, otherwise a new one."""
        existing = self.catalog.category_by_key(name_key(" ".join(name.split())))
        return existing["id"] if existing else self.create_category(name)

    def learn(self, path, result, analysis, summary, cat_id, folder):
        """Keep a file read from the user's own folder as their example of a category (record 2.9): its text is
        stored for learning; the file is never moved, copied or changed. Returns "learned", "known" (its bytes are
        in ClassiFile already) or "unread"."""
        if result.sha256 is None or result.status != "ok":
            return "unread"
        if self.catalog.snapshot_by_hash(result.sha256):
            return "known"
        self.catalog.add_document(result, Path(path).resolve(), analysis, summary, example=(cat_id, str(folder)))
        return "learned"

    def forget_folder(self, folder):
        """Forget the examples learned from one of the user's folders: the text ClassiFile stored for them goes;
        the files and the categories stay. Returns how many were forgotten."""
        ids = self.catalog.example_documents(str(folder))
        self.remove(ids)
        return len(ids)

    def create_category(self, name, by="user"):
        """by "machine": an automatic new folder (B2, record 2.6), marked as named by the app until renamed."""
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
        return self.catalog.add_category(name, name_key(name), folder, created_by=by)

    def file(self, doc_id, cat_id, provenance="user-confirmed", auto=None):
        """Primary placement plus verified copy: the user's choice, unless file_automatically() says otherwise.
        Returns (outcome, path).
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
        self.catalog.add_primary(doc_id, cat_id, provenance, auto)
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
                self.catalog.remove_secondary(doc_id, cat_id)   # it also belonged there: now it is its own
                if _crash_at == "after-switch":
                    raise _Crash
            keep = {cat_id} | {c for c, _ in self.catalog.secondary_categories(doc_id)}
            for c in self.catalog.document_copies(doc_id):
                if c["category_id"] not in keep:        # the copies of "also belongs to" stay where they are
                    _retire_old_copy(self.catalog, c)
        except CopyError:
            self.catalog.end_move(doc_id)
            raise
        self.catalog.end_move(doc_id)
        return "edited" if edited() > before else "moved"

    def also(self, doc_id, cat_id):
        """ "Also belongs to" (A6, B5): a secondary membership with its own verified copy, made from the verified
        primary copy or from the original. The primary category does not change. Returns the copy's path."""
        doc, primary = self.catalog.document(doc_id), self.catalog.active_primary(doc_id)
        if doc is None or doc["status"] != "filed" or not primary:
            raise ValueError("Only filed documents can also belong to another category.")
        if cat_id == primary["category_id"] or cat_id in dict(self.catalog.secondary_categories(doc_id)):
            raise ValueError("This document is already in that category.")
        root = self.output_root
        if root is None or not root.is_dir():
            raise CopyError(f"The output folder {root} can't be found. Choose it again with Change…")
        source = self._verified_copy(doc, primary["category_id"]) or Path(doc["source_path"])
        if not source.is_file():
            raise CopyError("Neither the filed copy nor the original file can be found, so no second copy was made.")
        self.catalog.add_secondary(doc_id, cat_id)
        try:
            return make_copy(self.catalog, doc_id, doc["sha256"], source, cat_id, root)[1]
        except CopyError:
            self.catalog.remove_secondary(doc_id, cat_id)   # never half-done: no membership without a copy
            raise

    def confirm(self, doc_ids):
        """ "Looks right": the user confirms placements the app made by itself, so they become training examples.
        Returns how many were confirmed."""
        return sum(self.catalog.confirm_primary(d) for d in doc_ids)

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

    # -- matching to existing categories by content (decision record B4, CP3) ---------------------------------
    def matcher(self):
        """(version row, Matcher) for the model in use, or None when there is none this version can read."""
        if self._matcher is False:
            row = self.catalog.active_matcher()
            bundle = json.loads(row["bundle_json"]) if row else {}
            usable = (bundle.get("representation"), bundle.get("scorer")) == (matching.REPRESENTATION, matching.SCORER)
            self._matcher, self._ranked = ((row, matching.Matcher(bundle)) if usable else None), {}
        return self._matcher

    def matches(self, doc_id, live):
        """The existing categories that fit a waiting document best: up to three (category id, documents of that
        category the model was trained on, the words the document shares most with it), best first. Empty when
        there is no model, or when no category is a good match: the abstention baseline (E4). live: ids of the
        categories that exist now."""
        if not self.matcher():
            return []
        _, model = self.matcher()
        ranked = self._rank(doc_id, live)
        return [(c, model.bundle["documents"][c], self.key_words(doc_id, c))
                for c, _ in ranked[:3]] if model.good(ranked) else []

    def key_words(self, doc_id, cat_id):
        """The words a document shares most with a category, for the model in use (there must be one)."""
        row, model = self.matcher()
        key = (row["version"], doc_id, cat_id)
        if key not in self._words:
            self._words[key] = model.key_words(self._terms(doc_id), cat_id)
        return self._words[key]

    def _rank(self, doc_id, live):
        """The existing categories ranked for a document by the model in use (there must be one)."""
        if doc_id not in self._ranked:      # once per document and model: the stored text is read and scored
            self._ranked[doc_id] = self.matcher()[1].rank_counts(self._terms(doc_id))
        return [(c, s) for c, s in self._ranked[doc_id] if c in live]

    def _terms(self, doc_id):
        if doc_id not in self._counts:
            self._counts[doc_id] = matching.terms(self.catalog.texts(doc_id).get(doc_id, ""))
        return self._counts[doc_id]

    def new_subject_groups(self, doc_ids):
        """Groups among waiting documents that match no existing category (B2): [(document ids, the key words
        they share)], each of at least two documents. Nothing is filed or created here: a group is a question."""
        if len(doc_ids) < 2 or not self.matcher():
            return []
        row, model = self.matcher()
        asked = (row["version"], tuple(sorted(doc_ids)))
        if asked != self._groups[0]:        # the same documents and model: the same groups, not worked out again
            vectors = matching.group_vectors({d: self._terms(d) for d in doc_ids}, model.bundle)
            self._groups = (asked, [(g, matching.shared_words([vectors[d] for d in g]))
                                    for g in matching.similar_groups(vectors, matching.GROUP_LEVEL)])
        return self._groups[1]

    # -- automatic filing (decision record A0, B2) --------------------------------------------------------------
    def auto_level(self):
        """The level in use: a name in matching.LEVELS, or "off"."""
        return self.catalog.get_setting("auto_level", matching.AUTO_DEFAULT)

    def set_auto_level(self, name):
        """Change the level; the change is kept on record."""
        if name != "off" and name not in matching.LEVELS:
            raise ValueError("unknown level")
        if name != self.auto_level():
            self.catalog.change_setting("auto_level", name)

    def auto_scope(self):
        """Selected-category mode (A5): the ids of the categories the user ticked, the only ones filed into
        automatically; None when every category may be."""
        if self.catalog.get_setting("auto_scope", "all") != "selected":
            return None
        live = {c["id"] for c in self.catalog.categories()}
        return set(json.loads(self.catalog.get_setting("auto_selected", "[]"))) & live

    def set_auto_scope(self, selected):
        """selected: the ticked category ids, or None for all categories. Changes are kept on record."""
        mode = "all" if selected is None else "selected"
        if mode != self.catalog.get_setting("auto_scope", "all"):
            self.catalog.change_setting("auto_scope", mode)
        ticked = json.dumps(sorted(selected or ()))
        if selected is not None and ticked != self.catalog.get_setting("auto_selected", "[]"):
            self.catalog.change_setting("auto_selected", ticked)

    def auto_choice(self, doc_id):
        """Where a waiting document would be filed without a question: (category id, what that rests on), or None
        when it waits for the user. It is filed only when its best category leads the second by the level in use,
        and that category holds enough documents the user confirmed (placements the app made do not count)."""
        level, doc = matching.LEVELS.get(self.auto_level()), self.catalog.document(doc_id)
        if level is None or not self.matcher() or doc is None or doc["status"] != "needs_decision":
            return None
        row, model = self.matcher()
        ranked = self._rank(doc_id, {c["id"] for c in self.catalog.categories()})
        if not ranked or matching.lead(ranked) < level:
            return None
        best, scope = ranked[0][0], self.auto_scope()
        if scope is not None and best not in scope:     # best among all categories, never among the ticked only:
            return None                                 # a selection cannot manufacture confidence (B1)
        if list(self.catalog.explicit_labels().values()).count(best) < matching.AUTO_MIN_CONFIRMED:
            return None
        return best, {"version": row["version"], "level": level, "documents": model.bundle["documents"][best],
                      "words": self.key_words(doc_id, best)}

    def file_automatically(self, doc_id):
        """File a waiting document by itself when its match is clear (auto_choice): the normal verified copy,
        recorded as machine-assigned with what it rests on. Such a placement never trains the matcher (A7).
        Returns the category id, or None when the document waits for the user. Raises CopyError like file()."""
        choice = self.auto_choice(doc_id)
        if choice is None:
            return None
        self.file(doc_id, choice[0], provenance="machine-assigned", auto=choice[1])
        return choice[0]

    # -- automatic new folders (decision record A4, B2, record 2.6) --------------------------------------------
    def auto_folders(self):
        """Automatic new folders are switched on (off until the user has seen the development replay)."""
        return self.catalog.get_setting("auto_folders", "off") == "on"

    def set_auto_folders(self, on):
        """Switch automatic new folders on or off; the change is kept on record."""
        if ("on" if on else "off") != self.catalog.get_setting("auto_folders", "off"):
            self.catalog.change_setting("auto_folders", "on" if on else "off")

    def folder_groups(self, doc_ids):
        """The folders the app would create by itself among these waiting documents: [(ids, key words, name)].
        Only in automatic mode (a level other than Off, all categories: selected-category mode asks first, A5)
        with automatic new folders switched on. Only documents no existing category matches, in groups of at
        least matching.FOLDER_MIN at matching.FOLDER_LEVEL; smaller groups stay questions and a single document
        waits. A group with no free name stays a question: a name equal to an existing category is never reused or
        merged into (B1)."""
        if not (self.auto_folders() and self.auto_level() != "off" and self.auto_scope() is None and self.matcher()):
            return []
        cats = self.catalog.categories()
        live = {c["id"] for c in cats}
        unmatched = [d for d in doc_ids if (self.catalog.document(d) or {"status": ""})["status"] == "needs_decision"
                     and not self.original_missing(d) and not self.matches(d, live)]
        if len(unmatched) < matching.FOLDER_MIN:
            return []
        model = self.matcher()[1]
        vectors = matching.group_vectors({d: self._terms(d) for d in unmatched}, model.bundle)
        taken, out = {c["name_key"] for c in cats}, []
        for ids in [g for g in matching.similar_groups(vectors, matching.FOLDER_LEVEL) if len(g) >= matching.FOLDER_MIN]:
            name = matching.group_name([top_names((self.catalog.analysis(d) or {}).get("suggestions", []))
                                        for d in ids], taken)
            if name:
                taken.add(name_key(name))
                out.append((ids, matching.shared_words([vectors[d] for d in ids]), name))
        return out

    def create_folders(self, doc_ids):
        """Create the folder_groups() folders and file their documents there: the normal verified copies,
        machine-assigned (they never train the matcher until the user confirms them). Returns [(category id,
        filed ids)]. A folder whose copies all fail is removed again; its documents keep waiting."""
        made = []
        for ids, words, name in self.folder_groups(doc_ids):
            try:
                cat_id = self.create_category(name, by="machine")
            except ValueError:
                continue
            auto = {"version": self.matcher()[0]["version"], "new_folder": True, "words": words}
            filed = []
            for d in ids:
                try:
                    self.file(d, cat_id, provenance="machine-assigned", auto=auto)
                    filed.append(d)
                except (CopyError, ValueError):
                    pass
            if filed:
                made.append((cat_id, filed))
            else:
                self.discard_unused_category(cat_id)
        return made

    def matching_status(self):
        """{"version", "created_at", "documents", "categories", "since"} for the model in use (since: documents
        filed or moved after it was trained), or {"since"} alone when there is none."""
        labels = self.catalog.explicit_labels()
        if not self.matcher():
            return {"since": len(labels)}
        row, model = self.matcher()
        trained = model.bundle["training"]
        return {k: row[k] for k in ("version", "created_at", "documents", "categories")} | {
            "since": sum(trained.get(d) != c for d, c in labels.items())}

    def update_due(self):
        """Matching updates by itself (A7, record 2.6) once this many confirmations or moves were made since the
        last version was trained, kept or not: a rejected version is not retried at every filing. The first version
        comes the same way, once that many are filed in at least two categories."""
        last = self.catalog.latest_matcher()
        labels = self.catalog.explicit_labels()
        if last is None:                    # the first version too (record A7): once there is something to tell apart
            return len(labels) >= matching.AUTO_UPDATE_EVERY and len(set(labels.values())) >= 2
        trained = json.loads(last["bundle_json"])["training"]
        return sum(trained.get(d) != c for d, c in labels.items()) >= matching.AUTO_UPDATE_EVERY

    def evaluation_inputs(self):
        """(counts, labels, groups) for classifile.evaluation, from the catalog as it is now: the terms() of every
        document with readable text, the user's explicit choices, and the families they are held out by (the
        owner's family labels where recorded, tools.evaluate --set-families)."""
        counts = {d: matching.terms(t) for d, t in self.catalog.texts().items()}
        owner = self.catalog.family_labels()
        files = {r["document_id"]: (r["sha256"], r["file_name"], owner.get(r["sha256"], ""))
                 for r in self.catalog.all("SELECT document_id, sha256, file_name FROM snapshots ORDER BY id")}
        labels = self.catalog.explicit_labels()
        return counts, labels, {d: d for d in labels} | evaluation.families(counts, files)

    def check_level(self):
        """The level the update check counts automatic filings at: the one in use, or Strict when it is off."""
        return matching.LEVELS.get(self.auto_level(), matching.LEVELS[matching.AUTO_DEFAULT])

    def update_matching(self, trigger="user"):
        """Retrain on the documents the user filed (A7), on request or by itself (trigger "automatic"). The new
        version and the one in use are measured on the same full evaluation (classifile.evaluation: every
        family held out in turn, each version replayed on its own training); the new one replaces the one in use
        only if it files no more documents wrongly at the level in use and puts the user's category first no less
        often (evaluation.no_worse). Either way it is recorded with both results, and the documents to check
        ("Check these").
        Returns {"outcome": "updated" | "kept previous" | "up to date", "version", "documents", "categories",
        "check"}. Raises ValueError with a plain reason when there is too little to learn from."""
        counts, labels, groups = self.evaluation_inputs()
        if len({c for d, c in labels.items() if counts.get(d)}) < 2:
            raise ValueError("Matching needs filed documents in at least two categories.")
        self._matcher = False               # read the catalog's state, not a remembered one
        current = self.matcher()
        live, level = {c["id"] for c in self.catalog.categories()}, self.check_level()
        rows = evaluation.evaluate(counts, labels, groups, live=live)
        found = {"level": level, "new": evaluation.summary(rows, level), "check": evaluation.mismatches(rows)}
        if current and current[1].bundle["training"] == labels:
            stored = json.loads(current[0]["check_json"] or "{}")
            if stored.get("check") != found["check"] or stored.get("level") != level:
                self.catalog.set_matcher_check(current[0]["version"], stored | found)  # measured as it is now
            return {"outcome": "up to date", "version": current[0]["version"],
                    "documents": current[0]["documents"], "categories": current[0]["categories"], "check": None}
        if current:
            found["previous"] = evaluation.summary(
                evaluation.evaluate(counts, labels, groups, current[1].bundle["training"], live), level)
        keep = current is None or evaluation.no_worse(found["new"], found["previous"])
        texts = self.catalog.texts()
        bundle = matching.train(texts, labels)
        version = self.catalog.add_matcher(bundle, found, keep, trigger)
        self._matcher = False
        return {"outcome": "updated" if keep else "kept previous",
                "version": version if keep else current[0]["version"],
                "documents": sum(bundle["documents"].values()), "categories": len(bundle["documents"]),
                "check": found}

    # -- "Check these": filed documents whose content matches another folder by a wide margin -----------------
    def to_check(self):
        """[(document id, file name, its category, the category its content matches, margin)] from the last
        evaluation (Catalog.to_check): still filed where they were measured, not kept there by the user. Nothing is
        ever moved by itself."""
        return self.catalog.to_check()

    def keep_here(self, doc_ids):
        """The user keeps these documents in their category: recorded, and not asked again while they stay there."""
        for d in doc_ids:
            cat = self.catalog.active_primary(d)
            if cat:
                self.catalog.keep_here(d, cat["category_id"])

    def discard_unused_category(self, cat_id):
        """A category with no documents (e.g. created for a filing that failed) is removed again."""
        return self.catalog.discard_unused_category(cat_id)
