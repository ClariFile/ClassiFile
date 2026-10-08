"""Pre-push audit: no tracked file, path or commit to be pushed contains a term from a local term list.

Usage: python -m tools.audit_terms [--terms data/audit_terms.txt] [--range origin/main..main]

The term list stays in data/ (not tracked): one term per line, matched case-insensitively; a line starting with
"re:" is a regular expression; lines starting with "#" are comments. Checked: the content and path of every tracked
file, and for each commit in --range its message, author and committer (name and email) and its added lines.
Prints each hit as where: term, and exits with 1 when there is any.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TERMS = ROOT / "data" / "audit_terms.txt"


def load_terms(path):
    patterns = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        body = line[3:] if line.startswith("re:") else re.escape(line)
        patterns.append((line, re.compile(body, re.I)))
    return patterns


def hits(text, patterns):
    return [label for label, rx in patterns if rx.search(text)]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def audit(patterns, rev_range=None):
    found = []
    for path in git("ls-files", "-z").split("\0"):
        if not path:
            continue
        found += [(f"path {path}", t) for t in hits(path, patterns)]
        data = (ROOT / path).read_bytes() if (ROOT / path).is_file() else b""
        if b"\0" in data[:4096]:
            continue  # binary (icons)
        for no, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            found += [(f"{path}:{no}", t) for t in hits(line, patterns)]
    if rev_range:
        for sha in git("rev-list", rev_range).split():
            meta = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", sha)
            found += [(f"commit {sha[:7]} message/author", t) for t in hits(meta, patterns)]
            for line in git("show", "--format=", "--unified=0", sha).splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    found += [(f"commit {sha[:7]} added line", t) for t in hits(line, patterns)]
                elif line.startswith("+++ b/") or line.startswith("diff --git"):
                    found += [(f"commit {sha[:7]} path", t) for t in hits(line, patterns)]
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--terms", type=Path, default=DEFAULT_TERMS)
    ap.add_argument("--range", dest="rev_range", help="commits to be pushed, e.g. origin/main..main")
    a = ap.parse_args(argv)
    found = audit(load_terms(a.terms), a.rev_range)
    for where, term in found:
        print(f"{where}: {term}")
    print(f"{len(found)} hit(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
