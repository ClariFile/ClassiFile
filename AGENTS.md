Read CLAUDE.md, DECISION_RECORD.md and DOS_AND_DONTS.md (if present) before any work. They are authoritative.

# AGENTS.md — ClassiFile

The rules below repeat the most important ones in short form, in case the linked files are not read. Where this
file and those files differ, those files win.

## Non-negotiable rules

- **Originals:** never modify, move, rename or delete a source file or change its metadata; open sources read-only;
  no side files next to them. Never overwrite any existing file.
- **Held-out data:** never open, read or test against `data\validation`, `data\final-eval` or `data\final-check`
  unless the owner says so.
- **Privacy:** no document text, real file names or personal data (names, user-folder paths, course codes, people,
  institutions, titles from documents) in tracked files, logs, error messages or commit messages.
- **Before every push:** `.venv\Scripts\python -m tools.audit_terms --range origin/main..main`; push only with
  0 hits. Never force-push.
- **Deleting:** ask before deleting any file the owner put in the project (for example under `data\`), even an
  exact duplicate.
- **Asking first:** ask before adding a dependency, and before launching other programs (Word, PowerPoint,
  installers and the like).
- **Never edit DECISION_RECORD.md;** propose changes to the owner instead.
- No network calls at runtime. Never present similarity scores as probabilities.

## Commands

Run from the project folder (Windows; the venv uses Python 3.12).

- Set up: `py -3.12 -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`
- Run the app: `.venv\Scripts\python -m classifile.app`
- Test: `.venv\Scripts\python -m pytest -q` (run the full suite before reporting)
- Interface checks: `.venv\Scripts\python -m tools.check_ui`

Every other command is in CLAUDE.md.

## Skills

Skills in `.agents\skills` are used only when the owner types `$name`; never start one on your own.
