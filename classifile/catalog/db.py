"""SQLite catalog in the app's data folder. Stable IDs; content hashes identify bytes, never documents."""
import json
import os
import sqlite3
import sys
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

APP_NAME = "ClassiFile"

MIGRATIONS = [
    # v1
    """
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE documents (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,          -- needs_decision | filed | failed | pending
        status_reason TEXT,            -- fixed strings only, never document text
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE snapshots (
        id INTEGER PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id),
        sha256 TEXT NOT NULL UNIQUE,
        size INTEGER NOT NULL,
        source_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        imported_at TEXT NOT NULL
    );
    CREATE TABLE extractions (
        id INTEGER PRIMARY KEY,
        snapshot_id INTEGER NOT NULL UNIQUE REFERENCES snapshots(id),
        reader_version TEXT,
        record_version INTEGER,
        status TEXT NOT NULL,
        reason TEXT,
        page_count INTEGER,
        metadata_json TEXT,
        template_lines_json TEXT,
        recurring_lines_json TEXT,
        first_page_lines_json TEXT,
        analyzer_version TEXT,
        analysis_json TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE extraction_pages (
        extraction_id INTEGER NOT NULL REFERENCES extractions(id),
        page INTEGER NOT NULL,
        text TEXT NOT NULL,
        native_chars INTEGER NOT NULL,
        text_area REAL NOT NULL,
        image_area REAL NOT NULL,
        nonrepeated_image_area REAL NOT NULL,
        suspected_unread INTEGER NOT NULL,
        suspect_rule TEXT,
        PRIMARY KEY (extraction_id, page)
    );
    CREATE TABLE categories (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_key TEXT NOT NULL UNIQUE,
        folder_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        description TEXT,
        level TEXT NOT NULL,           -- series | purpose | subject | user-defined
        created_by TEXT NOT NULL,      -- user | machine
        created_at TEXT NOT NULL
    );
    CREATE TABLE memberships (
        id INTEGER PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id),
        category_id TEXT NOT NULL REFERENCES categories(id),
        role TEXT NOT NULL CHECK (role IN ('primary', 'secondary')),
        provenance TEXT NOT NULL CHECK (provenance IN ('machine-assigned', 'user-confirmed', 'user-corrected')),
        status TEXT NOT NULL,          -- active | removed
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX one_active_primary ON memberships(document_id) WHERE role = 'primary' AND status = 'active';
    CREATE TABLE membership_events (
        id INTEGER PRIMARY KEY,
        membership_id INTEGER NOT NULL REFERENCES memberships(id),
        event TEXT NOT NULL,
        provenance TEXT,
        at TEXT NOT NULL
    );
    CREATE TABLE copies (
        id INTEGER PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id),
        snapshot_sha256 TEXT NOT NULL,
        category_id TEXT NOT NULL REFERENCES categories(id),
        path TEXT,                     -- intended/final path; set before publishing
        temp_path TEXT,
        status TEXT NOT NULL,          -- planned | published | failed | missing | edited | moved
        hash_at_creation TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    # v2: extraction record version 2 (PDF, PPTX, DOCX, ODT units) and the hidden internal summary
    """
    ALTER TABLE extractions RENAME COLUMN page_count TO unit_count;
    ALTER TABLE extractions ADD COLUMN format TEXT;
    ALTER TABLE extractions ADD COLUMN unit TEXT;          -- page | slide | block
    ALTER TABLE extractions ADD COLUMN running_lines_json TEXT;
    ALTER TABLE extractions ADD COLUMN summary_version TEXT;
    ALTER TABLE extractions ADD COLUMN summary_json TEXT;  -- internal only; never shown or written into documents
    UPDATE extractions SET format = 'pdf', unit = 'page' WHERE reader_version LIKE 'pdf-%';
    CREATE TABLE extraction_units (
        extraction_id INTEGER NOT NULL REFERENCES extractions(id),
        unit_index INTEGER NOT NULL,
        kind TEXT NOT NULL,
        level INTEGER,
        title TEXT,
        text TEXT NOT NULL,
        notes TEXT,
        native_chars INTEGER NOT NULL,
        text_area REAL,                -- NULL where the format has no page geometry
        image_area REAL,
        nonrepeated_image_area REAL,
        suspected_unread INTEGER NOT NULL,
        suspect_rule TEXT,
        PRIMARY KEY (extraction_id, unit_index)
    );
    INSERT INTO extraction_units (extraction_id, unit_index, kind, text, native_chars, text_area, image_area,
                                  nonrepeated_image_area, suspected_unread, suspect_rule)
        SELECT extraction_id, page, 'page', text, native_chars, text_area, image_area, nonrepeated_image_area,
               suspected_unread, suspect_rule FROM extraction_pages;
    DROP TABLE extraction_pages;
    """,
    # v3: OCR observations (extraction record version 3)
    """
    ALTER TABLE extraction_units ADD COLUMN ocr_status TEXT;
    ALTER TABLE extraction_units ADD COLUMN ocr_text TEXT;  -- internal only; never written into any document
    ALTER TABLE extractions ADD COLUMN ocr_json TEXT;
    """,
    # v4: picture references per unit (extraction record version 4)
    """
    ALTER TABLE extraction_units ADD COLUMN pictures TEXT;  -- JSON list of package paths
    """,
    # v5: OCR junk filter observation (extraction record version 5)
    """
    ALTER TABLE extraction_units ADD COLUMN ocr_discarded_chars INTEGER;
    ALTER TABLE extraction_units ADD COLUMN ocr_raw_text TEXT;  -- internal only; never written into any document
    """,
    # v6: layout for readable formatting later (extraction record version 6)
    """
    ALTER TABLE extraction_units ADD COLUMN layout TEXT;      -- JSON
    ALTER TABLE extraction_units ADD COLUMN ocr_layout TEXT;  -- JSON
    """,
    # v7: regrouping (move, rename, delete) and feedback on rejected suggestions
    """
    ALTER TABLE categories ADD COLUMN deleted_at TEXT;  -- deleted categories stay: earlier placements name them
    CREATE TABLE moves (                                -- a move that has started; startup finishes it
        document_id TEXT PRIMARY KEY REFERENCES documents(id),
        category_id TEXT NOT NULL REFERENCES categories(id),
        started_at TEXT NOT NULL
    );
    CREATE TABLE suggestion_feedback (                  -- the user set the suggested names aside and chose another
        id INTEGER PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id),
        analyzer_version TEXT,
        reason TEXT,                                    -- one of the fixed reasons, or NULL
        category_id TEXT NOT NULL REFERENCES categories(id),
        at TEXT NOT NULL
    );
    """,
]


def default_data_dir():
    if os.environ.get("CLASSIFILE_DATA_DIR"):
        return Path(os.environ["CLASSIFILE_DATA_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Catalog:
    """One connection shared by the GUI and worker threads, serialized with a lock."""

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = Path(path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    @classmethod
    def open_default(cls):
        return cls(default_data_dir() / "catalog.sqlite3")

    def close(self):
        with self.lock:
            self.db.close()

    def _migrate(self):
        with self.lock, self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self.db.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self.db.execute("INSERT INTO schema_version VALUES (0)")
            version = row[0] if row else 0
        if version > len(MIGRATIONS):
            raise RuntimeError("catalog was created by a newer version of the app")
        for v, sql in enumerate(MIGRATIONS[version:], version + 1):
            with self.lock:
                # executescript commits first; wrap the migration and version bump in one transaction.
                self.db.executescript(f"BEGIN;\n{sql}\nUPDATE schema_version SET version = {v};\nCOMMIT;")

    @property
    def schema_version(self):
        return self.one("SELECT version FROM schema_version")[0]

    # -- small query helpers ---------------------------------------------------------------
    def one(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).fetchone()

    def all(self, sql, *args):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def run(self, sql, *args):
        with self.lock, self.db:
            return self.db.execute(sql, args)

    # -- settings ----------------------------------------------------------------------------
    def get_setting(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key = ?", key)
        return row[0] if row else default

    def set_setting(self, key, value):
        self.run("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, value)

    # -- documents ---------------------------------------------------------------------------
    def snapshot_by_hash(self, sha):
        return self.one("SELECT * FROM snapshots WHERE sha256 = ?", sha)

    STATUS_FOR_READ = {"ok": "needs_decision", "failed": "failed", "pending": "pending"}

    def add_document(self, result, source_path, analysis, summary=None):
        """Record a read result (any status) as a new document with one snapshot. Returns the document ID."""
        doc_id, t = str(uuid.uuid4()), now()
        with self.lock, self.db:
            self.db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
                            (doc_id, self.STATUS_FOR_READ[result.status], result.reason, t, t))
            snap = self.db.execute(
                "INSERT INTO snapshots (document_id, sha256, size, source_path, file_name, imported_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, result.sha256, result.size, str(source_path), Path(source_path).name, t),
            ).lastrowid
            self._add_extraction(snap, result, analysis, summary, t)
        return doc_id

    def replace_extraction(self, doc_id, result, analysis, summary=None):
        """A new read of the same snapshot replaces its extraction and the document's read status."""
        t = now()
        with self.lock, self.db:
            snap = self.db.execute("SELECT id FROM snapshots WHERE document_id = ?", (doc_id,)).fetchone()[0]
            self.db.execute("DELETE FROM extraction_units WHERE extraction_id IN"
                            " (SELECT id FROM extractions WHERE snapshot_id = ?)", (snap,))
            self.db.execute("DELETE FROM extractions WHERE snapshot_id = ?", (snap,))
            self._add_extraction(snap, result, analysis, summary, t)
            self.db.execute("UPDATE documents SET status = ?, status_reason = ?, updated_at = ? WHERE id = ?",
                            (self.STATUS_FOR_READ[result.status], result.reason, t, doc_id))

    def _add_extraction(self, snap, result, analysis, summary, t):
        rec = result.record
        row = {"snapshot_id": snap, "status": result.status, "reason": result.reason, "created_at": t}
        if rec:
            row |= {"reader_version": rec.reader_version, "record_version": rec.record_version,
                    "format": rec.format, "unit": rec.unit, "unit_count": rec.unit_count}
            row |= {f"{k}_json": json.dumps(getattr(rec, k)) for k in (
                "metadata", "template_lines", "recurring_lines", "running_lines", "first_page_lines", "ocr")}
        if analysis:
            row |= {"analyzer_version": analysis.analyzer_version, "analysis_json": json.dumps(analysis.to_dict())}
        if summary:
            row |= {"summary_version": summary["summary_version"], "summary_json": json.dumps(summary)}
        ext = self._insert("extractions", row)
        for u in (rec.units if rec else []):
            self._insert("extraction_units", {"extraction_id": ext, "unit_index": u.index} | {
                k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in asdict(u).items() if k != "index"})

    def _insert(self, table, row):
        """Caller holds the lock and transaction. Column names come from code, never from documents."""
        cols = ", ".join(row)
        return self.db.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(row))})",
                               tuple(row.values())).lastrowid

    def update_source_path(self, doc_id, path):
        """The original was found at a new location (same content hash): remember where it is now."""
        self.run("UPDATE snapshots SET source_path = ? WHERE document_id = ?", str(path), doc_id)

    def set_document_status(self, doc_id, status, reason=None):
        self.run("UPDATE documents SET status = ?, status_reason = ?, updated_at = ? WHERE id = ?",
                 status, reason, now(), doc_id)

    def document(self, doc_id):
        return self.one(
            "SELECT d.*, s.sha256, s.size, s.source_path, s.file_name FROM documents d"
            " JOIN snapshots s ON s.document_id = d.id WHERE d.id = ?", doc_id)

    _FILED = ("SELECT d.*, s.sha256, s.file_name, s.imported_at, s.source_path, c.id AS category_id,"
              " c.name AS category, p.path AS copy_path,"
              " p.status AS copy_status, p.updated_at AS filed_at FROM documents d"
              " JOIN snapshots s ON s.document_id = d.id"
              " JOIN memberships m ON m.document_id = d.id AND m.status = 'active'"
              " JOIN categories c ON c.id = m.category_id"
              " LEFT JOIN copies p ON p.id = (SELECT id FROM copies WHERE document_id = d.id AND category_id = c.id"
              " AND status IN ('published', 'edited') ORDER BY id DESC LIMIT 1) ")

    def documents(self, category_id=None):
        """Documents in a category (with category, copy path and filed time), or (category_id=None) every document
        that is not filed: the Inbox."""
        if category_id is None:
            return self.all("SELECT d.*, s.sha256, s.file_name, s.imported_at, s.source_path FROM documents d"
                            " JOIN snapshots s ON s.document_id = d.id WHERE d.status != 'filed'"
                            " ORDER BY s.file_name, d.id")
        return self.all(self._FILED + "WHERE m.category_id = ? AND d.status = 'filed' ORDER BY s.file_name, d.id",
                        category_id)

    def recent_documents(self, since_iso):
        """Documents imported since the given time (ISO, UTC), newest first."""
        return self.all("SELECT d.*, s.sha256, s.file_name, s.imported_at FROM documents d JOIN snapshots s"
                        " ON s.document_id = d.id WHERE s.imported_at >= ? ORDER BY s.imported_at DESC, d.id", since_iso)

    def all_documents(self):
        """Every document: filed ones with their category, copy path and filed time; the rest without."""
        filed = self.all(self._FILED + "WHERE d.status = 'filed' ORDER BY s.file_name, d.id")
        ids = {d["id"] for d in filed}
        rest = [dict(d) | {"category_id": None, "category": None, "copy_path": None, "copy_status": None,
                           "filed_at": None} for d in self.documents(None) if d["id"] not in ids]
        return sorted([dict(d) for d in filed] + rest, key=lambda d: (d["file_name"].casefold(), d["id"]))

    def remove_document(self, doc_id):
        """Delete a waiting document's catalog rows: snapshot, stored text and analysis, any membership.
        Refused when the document has a copy that exists or may exist (the original is never involved)."""
        with self.lock, self.db:
            live = self.db.execute("SELECT 1 FROM copies WHERE document_id = ? AND status != 'failed'",
                                   (doc_id,)).fetchone()
            status = self.db.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if status is None:
                return
            if live or status[0] == "filed":
                raise ValueError("filed documents cannot be removed")
            snaps = [r[0] for r in self.db.execute("SELECT id FROM snapshots WHERE document_id = ?", (doc_id,))]
            for snap in snaps:
                self.db.execute("DELETE FROM extraction_units WHERE extraction_id IN"
                                " (SELECT id FROM extractions WHERE snapshot_id = ?)", (snap,))
                self.db.execute("DELETE FROM extractions WHERE snapshot_id = ?", (snap,))
            self.db.execute("DELETE FROM snapshots WHERE document_id = ?", (doc_id,))
            self.db.execute("DELETE FROM membership_events WHERE membership_id IN"
                            " (SELECT id FROM memberships WHERE document_id = ?)", (doc_id,))
            self.db.execute("DELETE FROM memberships WHERE document_id = ?", (doc_id,))
            self.db.execute("DELETE FROM copies WHERE document_id = ?", (doc_id,))
            self.db.execute("DELETE FROM moves WHERE document_id = ?", (doc_id,))
            self.db.execute("DELETE FROM suggestion_feedback WHERE document_id = ?", (doc_id,))
            self.db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def analysis(self, doc_id):
        row = self.one("SELECT e.analysis_json FROM extractions e JOIN snapshots s ON e.snapshot_id = s.id"
                       " WHERE s.document_id = ?", doc_id)
        return json.loads(row[0]) if row and row[0] else None

    def first_page_lines(self, doc_id):
        row = self.one("SELECT e.first_page_lines_json FROM extractions e JOIN snapshots s ON e.snapshot_id = s.id"
                       " WHERE s.document_id = ?", doc_id)
        return json.loads(row[0]) if row and row[0] else []

    # -- categories --------------------------------------------------------------------------
    def categories(self):
        return self.all("SELECT * FROM categories WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE, id")

    def category_counts(self):
        """{category id: documents in it}."""
        return dict(self.all("SELECT category_id, COUNT(*) FROM memberships WHERE status = 'active'"
                             " GROUP BY category_id"))

    def recent_categories(self, n=5):
        """Ids of the categories used last (a document was filed in or moved to them), latest first."""
        return [r[0] for r in self.all(
            "SELECT m.category_id FROM memberships m JOIN categories c ON c.id = m.category_id"
            " WHERE c.deleted_at IS NULL GROUP BY m.category_id ORDER BY MAX(m.id) DESC LIMIT ?", n)]

    def rename_category(self, cat_id, name, key, folder_name):
        self.run("UPDATE categories SET name = ?, name_key = ?, folder_name = ? WHERE id = ?",
                 name, key, folder_name, cat_id)

    def delete_category(self, cat_id):
        """Only a category without documents. The row stays for the history of earlier placements; its name and
        folder name become free again. Folders are never touched here."""
        with self.lock, self.db:
            if self.db.execute("SELECT 1 FROM memberships WHERE category_id = ? AND status = 'active'",
                               (cat_id,)).fetchone():
                raise ValueError("this category still holds documents")
            self.db.execute("UPDATE categories SET deleted_at = ?, name_key = ?, folder_name = ? WHERE id = ?",
                            (now(), f"deleted:{cat_id}", f"deleted:{cat_id}", cat_id))

    def category(self, cat_id):
        return self.one("SELECT * FROM categories WHERE id = ?", cat_id)

    def category_by_key(self, key):
        return self.one("SELECT * FROM categories WHERE name_key = ?", key)

    def add_category(self, name, key, folder_name, level="user-defined", created_by="user", description=None):
        cat_id = str(uuid.uuid4())
        self.run("INSERT INTO categories (id, name, name_key, folder_name, description, level, created_by, created_at)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", cat_id, name, key, folder_name, description, level, created_by,
                 now())
        return cat_id

    def folder_taken(self, folder_name):
        return self.one("SELECT 1 FROM categories WHERE folder_name = ?", folder_name) is not None

    # -- memberships -------------------------------------------------------------------------
    def active_primary(self, doc_id):
        return self.one("SELECT * FROM memberships WHERE document_id = ? AND role = 'primary' AND status = 'active'",
                        doc_id)

    def add_primary(self, doc_id, cat_id, provenance):
        t = now()
        with self.lock, self.db:
            mid = self.db.execute(
                "INSERT INTO memberships (document_id, category_id, role, provenance, status, created_at, updated_at)"
                " VALUES (?, ?, 'primary', ?, 'active', ?, ?)", (doc_id, cat_id, provenance, t, t)).lastrowid
            self.db.execute("INSERT INTO membership_events (membership_id, event, provenance, at) VALUES (?, ?, ?, ?)",
                            (mid, "created", provenance, t))
        return mid

    def replace_primary(self, doc_id, cat_id, provenance):
        """The user's later choice wins: the active primary placement is superseded (kept as history) and a new
        one is recorded."""
        t = now()
        with self.lock, self.db:
            for (mid,) in self.db.execute("SELECT id FROM memberships WHERE document_id = ? AND role = 'primary'"
                                          " AND status = 'active'", (doc_id,)).fetchall():
                self.db.execute("UPDATE memberships SET status = 'superseded', updated_at = ? WHERE id = ?", (t, mid))
                self.db.execute("INSERT INTO membership_events (membership_id, event, provenance, at)"
                                " VALUES (?, 'superseded', ?, ?)", (mid, provenance, t))
            mid = self.db.execute(
                "INSERT INTO memberships (document_id, category_id, role, provenance, status, created_at, updated_at)"
                " VALUES (?, ?, 'primary', ?, 'active', ?, ?)", (doc_id, cat_id, provenance, t, t)).lastrowid
            self.db.execute("INSERT INTO membership_events (membership_id, event, provenance, at) VALUES (?, ?, ?, ?)",
                            (mid, "created", provenance, t))
        return mid

    def start_move(self, doc_id, cat_id):
        self.run("INSERT INTO moves VALUES (?, ?, ?) ON CONFLICT(document_id) DO UPDATE SET"
                 " category_id = excluded.category_id, started_at = excluded.started_at", doc_id, cat_id, now())

    def end_move(self, doc_id):
        self.run("DELETE FROM moves WHERE document_id = ?", doc_id)

    def pending_moves(self):
        return self.all("SELECT document_id, category_id FROM moves ORDER BY started_at, document_id")

    def add_feedback(self, doc_id, cat_id, reason=None):
        """The suggested names were set aside for this document; the user chose cat_id (reason: a fixed string)."""
        row = self.one("SELECT e.analyzer_version FROM extractions e JOIN snapshots s ON e.snapshot_id = s.id"
                       " WHERE s.document_id = ?", doc_id)
        self.run("INSERT INTO suggestion_feedback (document_id, analyzer_version, reason, category_id, at)"
                 " VALUES (?, ?, ?, ?, ?)", doc_id, row[0] if row else None, reason, cat_id, now())

    def remove_primary(self, doc_id):
        """Undo a placement whose copy never succeeded (the membership and its events)."""
        with self.lock, self.db:
            ids = [r[0] for r in self.db.execute("SELECT id FROM memberships WHERE document_id = ? AND role ="
                                                 " 'primary' AND status = 'active'", (doc_id,))]
            for mid in ids:
                self.db.execute("DELETE FROM membership_events WHERE membership_id = ?", (mid,))
                self.db.execute("DELETE FROM memberships WHERE id = ?", (mid,))

    def discard_unused_category(self, cat_id):
        """Delete a category that has no memberships and no copies except failed attempts. Returns True if deleted.
        Folders are never touched here."""
        with self.lock, self.db:
            used = self.db.execute("SELECT 1 FROM memberships WHERE category_id = ? UNION ALL SELECT 1 FROM copies"
                                   " WHERE category_id = ? AND status != 'failed' UNION ALL SELECT 1 FROM moves"
                                   " WHERE category_id = ? UNION ALL SELECT 1 FROM suggestion_feedback"
                                   " WHERE category_id = ? LIMIT 1", (cat_id,) * 4).fetchone()
            if used:
                return False
            self.db.execute("DELETE FROM copies WHERE category_id = ?", (cat_id,))
            self.db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            return True

    # -- copies ------------------------------------------------------------------------------
    def published_copy(self, sha, cat_id):
        return self.one("SELECT * FROM copies WHERE snapshot_sha256 = ? AND category_id = ? AND status = 'published'",
                        sha, cat_id)

    def plan_copy(self, doc_id, sha, cat_id, temp_path):
        t = now()
        return self.run(
            "INSERT INTO copies (document_id, snapshot_sha256, category_id, temp_path, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'planned', ?, ?)", doc_id, sha, cat_id, str(temp_path), t, t).lastrowid

    def update_copy(self, copy_id, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.run(f"UPDATE copies SET {cols}, updated_at = ? WHERE id = ?", *fields.values(), now(), copy_id)

    def document_copies(self, doc_id, status="published"):
        return self.all("SELECT * FROM copies WHERE document_id = ? AND status = ? ORDER BY id", doc_id, status)

    def copies(self, status=None):
        if status:
            return self.all("SELECT * FROM copies WHERE status = ? ORDER BY id", status)
        return self.all("SELECT * FROM copies ORDER BY id")
