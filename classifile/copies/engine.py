"""Verified copies: planned record -> exclusive temp write -> hash check -> publish without overwrite -> published.

Sources are opened read-only. Existing files are never overwritten. Recovery deletes only temp files
that the catalog recorded and that carry the app's temp prefix.
"""
import hashlib
import os
import re
import sys
import uuid
from pathlib import Path

TEMP_PREFIX = ".classifile-"
TEMP_SUFFIX = ".tmp"
MAX_FOLDER_CHARS = 100
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in "123456789¹²³"), *(f"LPT{i}" for i in "123456789¹²³")}


class CopyError(Exception):
    """Plain reason strings: what went wrong and what to do, with paths only; never document content."""


def _plain(error, source, dest_dir):
    if isinstance(error, FileNotFoundError) and not Path(source).exists():
        return f"The original file is no longer at {source}. Import it again from its new location."
    if isinstance(error, FileNotFoundError):
        return f"The folder {dest_dir} disappeared while copying. Try again."
    if isinstance(error, PermissionError):
        return f"ClassiFile wasn't allowed to write into {dest_dir}. Check the folder's permissions, then try again."
    if getattr(error, "errno", None) == 28:  # ENOSPC
        return f"There isn't enough free space for the copy in {dest_dir}. Free some space, then try again."
    return f"The copy into {dest_dir} failed ({type(error).__name__}). Try again."


def sanitize_folder_name(name):
    """Windows-safe single folder name. '/' never nests; '+' and '#' are kept (C, C++ and C# stay distinct)."""
    s = _FORBIDDEN.sub("_", " ".join(name.split()))[:MAX_FOLDER_CHARS].rstrip(" .")
    if not s:
        return "_"
    if s.split(".")[0].upper().rstrip(" ") in _RESERVED:
        s += "_"
    return s


def is_temp_name(path):
    name = Path(path).name
    return name.startswith(TEMP_PREFIX) and name.endswith(TEMP_SUFFIX)


def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _candidates(dest_dir, file_name):
    stem, suffix = Path(file_name).stem, Path(file_name).suffix
    yield dest_dir / file_name
    n = 2
    while True:
        yield dest_dir / f"{stem} ({n}){suffix}"
        n += 1


def _publish(temp, final):
    """Make temp appear at final without any overwrite path. Raises FileExistsError if final exists."""
    if sys.platform == "win32":
        os.rename(temp, final)  # on Windows, rename never replaces an existing file
    else:
        os.link(temp, final)    # atomic no-overwrite; then drop the temp name
        os.unlink(temp)


def make_copy(catalog, doc_id, sha, source_path, cat_id, output_root, _crash_at=None, reuse=True):
    """Copy a snapshot into a category folder. Returns ("already filed" | "published", path).
    reuse=False always makes a new copy (moving copies to a new output folder)."""
    existing = catalog.published_copy(sha, cat_id) if reuse else None
    if existing:
        return "already filed", Path(existing["path"])

    dest_dir = Path(output_root) / catalog.category(cat_id)["folder_name"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    temp = dest_dir / f"{TEMP_PREFIX}{uuid.uuid4().hex}{TEMP_SUFFIX}"
    copy_id = catalog.plan_copy(doc_id, sha, cat_id, temp)

    try:
        h = hashlib.sha256()
        with open(source_path, "rb") as src, open(temp, "xb") as out:
            for i, chunk in enumerate(iter(lambda: src.read(1 << 20), b"")):
                h.update(chunk)
                out.write(chunk)
                if _crash_at == "mid-write" and i == 0:
                    raise _Crash
            out.flush()
            os.fsync(out.fileno())
        if h.hexdigest() != sha:
            raise CopyError(f"The original file at {source_path} has changed since it was imported. "
                            "Import it again to file the new version.")
        if _hash(temp) != sha:
            raise CopyError("The copy didn't match the original, so it was discarded. Try again.")
        if _crash_at == "before-publish":
            raise _Crash

        file_name = Path(catalog.document(doc_id)["file_name"]).name
        for final in _candidates(dest_dir, file_name):
            if final.exists():
                continue
            catalog.update_copy(copy_id, path=str(final))  # record intent before the file appears
            try:
                _publish(temp, final)
                break
            except FileExistsError:  # appeared between the check and the publish; try the next name
                continue
        if _crash_at == "after-publish":
            raise _Crash
    except _Crash:
        raise
    except (OSError, CopyError) as e:
        _discard_temp(temp)
        catalog.update_copy(copy_id, status="failed")
        if isinstance(e, CopyError):
            raise
        raise CopyError(_plain(e, source_path, dest_dir)) from None

    catalog.update_copy(copy_id, status="published", hash_at_creation=sha, temp_path=None)
    return "published", final


class _Crash(BaseException):
    """Test hook: simulates the process dying at a given point (no cleanup runs)."""


def _discard_temp(temp):
    if temp and is_temp_name(temp):
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def _inside(path, root):
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except OSError:
        return False


def _retire_old_copy(catalog, c):
    """The copy now has a verified twin in the new output folder: remove the old file only if it is unchanged.
    Edited copies stay where they are and are flagged. Returns the outcome."""
    old = Path(c["path"])
    if not old.exists():
        catalog.update_copy(c["id"], status="moved")
        return "moved"
    if _hash(old) != c["hash_at_creation"]:
        catalog.update_copy(c["id"], status="edited")
        return "edited"
    os.unlink(old)
    catalog.update_copy(c["id"], status="moved")
    return "moved"


def move_copies(catalog, new_root):
    """Move every published copy outside new_root into it by the verified-copy rules: a new verified copy is
    published (never overwriting; name clashes get a suffix), then the old file is removed only if unchanged.
    Edited copies are left in place and flagged; missing ones are flagged. Returns [(copy_id, outcome)]."""
    report = []
    for c in catalog.copies("published"):
        if _inside(c["path"], new_root):
            continue
        old = Path(c["path"])
        if not old.exists():
            catalog.update_copy(c["id"], status="missing")
            report.append((c["id"], "missing"))
            continue
        if _hash(old) != c["hash_at_creation"]:
            catalog.update_copy(c["id"], status="edited")
            report.append((c["id"], "edited"))
            continue
        try:
            make_copy(catalog, c["document_id"], c["snapshot_sha256"], old, c["category_id"], new_root, reuse=False)
        except CopyError:
            report.append((c["id"], "failed"))  # the old copy stays where it is, still published
            continue
        report.append((c["id"], _retire_old_copy(catalog, c)))
    return report


def finish_moves(catalog, output_root):
    """After an interrupted move: a published copy outside the output folder whose twin (same snapshot and
    category) is published inside it is retired by the same rules."""
    report = []
    inside = {(c["snapshot_sha256"], c["category_id"]) for c in catalog.copies("published")
              if _inside(c["path"], output_root)}
    for c in catalog.copies("published"):
        if not _inside(c["path"], output_root) and (c["snapshot_sha256"], c["category_id"]) in inside:
            report.append((c["id"], _retire_old_copy(catalog, c)))
    return report


def recover(catalog, output_root=None):
    """Resolve copies left 'planned' by an interrupted run, finish interrupted moves, and flag published copies
    that went missing. Returns a list of (copy_id, outcome)."""
    report = []
    for c in catalog.copies("planned"):
        temp = Path(c["temp_path"]) if c["temp_path"] else None
        final = Path(c["path"]) if c["path"] else None
        temp_exists = bool(temp and temp.exists())
        if temp_exists and final and final.exists() and os.path.samefile(temp, final):
            _discard_temp(temp)  # POSIX link published but the temp name remained
            outcome = "published"
        elif temp_exists:
            _discard_temp(temp)  # never published; final (if any) is not ours
            outcome = "failed"
        elif final and final.exists() and _hash(final) == c["snapshot_sha256"]:
            outcome = "published"
        else:
            outcome = "failed"
        if outcome == "published":
            catalog.update_copy(c["id"], status="published", hash_at_creation=c["snapshot_sha256"], temp_path=None)
        else:
            catalog.update_copy(c["id"], status="failed")
        report.append((c["id"], outcome))
    if output_root:
        report += finish_moves(catalog, output_root)
    for c in catalog.copies("published"):
        if not Path(c["path"]).exists():
            catalog.update_copy(c["id"], status="missing")
            report.append((c["id"], "missing"))
    return report
