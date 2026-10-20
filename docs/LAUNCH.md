# ClassiFile v1: the finish line

2026-10-14, marked 2026-10-15 · the definition of done for ClassiFile v1. From now on ClassiFile gets only the
launch work below and bug fixes, until v1 is released. New features wait for v1.1.

**[Blocker]** must be done before v1 is released. **[v1.1]** can wait. Everything in sections 1 to 3 is a
blocker unless marked otherwise.

## 0. Before the freeze (found 2026-10-15)

- **[Blocker, done 2026-10-15]** The owner decided the changes to the decision record: written as record 2.8 (the
  update check, the one evaluation, "Check these", E1 not built and E5–E7 on their defaults for v1).
- **[Blocker, done 2026-10-16]** "Update matching" once more, so the frozen version has learned the owner's last
  moves (version 6); the owner answered "Check these" (Keep here).
- **[Blocker, done 2026-10-15]** The CP5 report covers all of Part E: `python -m tools.quality_gate`.
- **[Blocker, done 2026-10-16]** Functional gate: an offline run with networking disabled
  (`python -m tools.offline_check`; the owner ran it in airplane mode).
- **[v1.1]** Balanced with "the nearest document is in the best folder" (on development data it files as many as
  Balanced and wrongly files fewer new subjects, 11 of 118 instead of 15). Only if the owner wants more automatic
  filing than Strict; it would need validation and a record change.
- **[v1.1]** E5–E7 run on their own data (name equivalence, instance identifiers, conflicting self-descriptions).

## 1. CP5: freeze, then the final evaluation once (done 2026-10-16)

**Result** (`tools.final_eval`, run once; record 2.10). Matching version 6, Strict; 28 documents in 22 families,
6 labels, every one an existing category (so the final set says nothing about new subjects or new folders).
Counts on a small held-out set, not a promise of accuracy.

| | Count | 95% range |
|---|---|---|
| The owner's category first | 26 of 28 | 77–98% |
| In the first three | 27 of 28 | 82–99% |
| Filed automatically (Strict), right | 18 | |
| Filed automatically (Strict), wrong | 0 | precision 82–100% |
| Left waiting | 10 of 28 | 21–54% |
| New folders created / mixing / second folder for a known subject | 0 / 0 / 0 | |
| Documents per decision | 1.00 (10 questions) | |

Other levels, right / wrong / waiting: Very strict 9 / 0 / 19; Balanced 21 / 0 / 7; Lenient 25 / 2 / 1.


1. **Freeze** (the record's CP5 and Part E). Write the frozen choices into the decision record:
   - the matcher: the matching version in use, with its preprocessing, vocabulary, category mapping and settings
     (updated once more first, so it has learned the owner's last moves);
   - the level for automatic filing (Strict) and the 3 confirmed documents it needs per category;
   - the folder rules: new folders at a similarity of 0.20, at least 3 documents each; questions for groups found
     at 0.15; a single document waits.
   - the update check (no more wrong automatic filings, no fewer right first, on the full evaluation) and
     "Check these" (another category ahead by at least 0.10);
   - From then on, matching does not update by itself during the evaluation.
2. **Run `data\final-eval` once**, with the frozen version, on a copy of the catalog.
   - The tool reads the folder, measures, and saves its result to a new file. It refuses a second run. It
     counts the same way as `tools.evaluate` (the same summary, levels and ranges).
   - Nothing is tuned afterwards. If a bug is found, it is fixed and reported, and the number stays as measured.
3. **Report**:
   - right first, and in the first three;
   - filed automatically, right and wrong;
   - left waiting;
   - new folders created, any that mix subjects, and any second folder for a subject that already has one;
   - documents per decision.
   These are counts on a small held-out set, not a promise of accuracy.

## 2. A Windows installer

- One installer, built with PyInstaller (or a similar tool) and an installer script (for example Inno Setup).
- It bundles:
  - Python and the dependencies (PyMuPDF, PySide6);
  - Tesseract and its English data, so OCR works without a separate install;
  - the ClassiFile icons;
  - the licence notices: ClassiFile's AGPL-3.0 (with a link to the source), Tesseract's Apache-2.0, and the
    notices of PySide6 (LGPL) and PyMuPDF (AGPL).
- It installs per user and needs no internet connection after download. Uninstalling leaves the user's
  documents, copies and catalog in place.
- Checked on a clean Windows 11 machine: install, first run, import, OCR, filing, uninstall.
- No other new features.

**Built 2026-10-17** (`python -m installer.build`; `installer/`): PyInstaller 6.22.3 makes the app folder, Inno Setup
6.7.3 the setup file (about 52 MB). OCR runs inside PyMuPDF (MuPDF's built-in Tesseract), so only Tesseract's
English data (`eng.traineddata`) is bundled, not the Tesseract program. Per user (`%LOCALAPPDATA%\Programs\ClassiFile`,
no administrator rights), Start-menu shortcuts for the app and its licences, an optional desktop shortcut. The
licences folder holds ClassiFile's AGPL-3.0, NOTICE.txt with the source links, Python's licence, PyMuPDF's AGPL,
LGPL-3.0 with GPL-3.0 for Qt and PySide6, and Tesseract's Apache-2.0.
- Checked on the build laptop: `ClassiFile.exe --self-test` reads the six samples in a worker process with OCR from
  the bundled data (PASS, the same counts as from source); the window starts with a fresh catalog; a silent
  install into a temporary folder, the self-test from there, and the uninstall left no program files, shortcuts or
  uninstall entry, and the catalog byte-for-byte unchanged.
- **Left:** the clean-machine test on a laptop that never had Python: `docs/INSTALLER_TEST.md`. Deferred by the owner
  (2026-10-19) until a spare laptop or a disposable Windows is at hand; never on the owner's only computer. Until
  then every build stays a release candidate (rc.4 to rc.6: checked without installing, `docs/STATUS.md`).

## 3. A user README (written 2026-10-15: `README.md`, and the guide in `docs/guide/`, English and Burmese)

- Install and first run: choosing the output folder, adding documents.
- How filing works:
  - matching with your folders;
  - Strict automatic filing and the 3 confirmed documents it needs;
  - "Filed automatically" and "Looks right";
  - new folders of 3 or more documents, and Rename;
  - learning from your confirmations.
- How to correct it: Move to…, Rename, Delete category, Also belongs to…, Remove from ClassiFile, Retry.
- What never happens: originals are never changed, moved or deleted; nothing is sent over the internet.
- Known limitations:
  - OCR misses text in tables, bordered boxes and on dark or gradient backgrounds;
  - English only;
  - folder names are usually typed by you: subject names are rarely written in the documents;
  - small folders (one or two documents) are rarely matched until they hold about five.

## 4. Not in v1 [v1.1 or later]

- Summaries for the user (SummarEase is a separate project).
- Languages other than English.
- Merging categories, aliases, and undoing an "Also belongs to".
- LLMs, embeddings, or any online service.
- Linking versions of the same document.
- macOS and Linux installers.
- A cloud or multi-device catalog.

## 5. For people other than the owner (gap list, 2026-10-15; decided by the owner the same day)

Decided: the first matching model, "Learn from my existing folders", a first-run tour and Help page, the README
and the guide are in v1 and built (record 2.9). The installer stays a v1 blocker (section 2). Key words per folder
are not built. Photos, household documents and Burmese are v1.1 (section 6).

Effort: S under a day, M a few days, L a week or more. Measurements are in `docs/STATUS.md` ("Toward friends and
family"); they describe development data.

| Gap | Effort | Risk | Proposed |
|---|---|---|---|
| **The first matching model.** A new user gets cards with existing folders, and automatic filing, only after pressing "Update matching" in Settings; the update after every 10 confirmations (A7) never starts while no version exists. | S | low | **v1** (makes the code do what A7 says): the first version after 10 confirmations in at least two folders, by itself. |
| **"Learn from my existing folders."** The user picks an organized folder; each subfolder becomes a category, its files examples, read only, nothing moved or copied. Simulated: with 3 documents per folder, nothing filed wrongly in four arrival orders and about half the decisions. | M | medium: long reads for big folders (OCR); nested subfolders; a record entry for documents that are examples without an app copy | **v1**, before the freeze, if the owner approves the record entry; otherwise v1.1. |
| **Key words per folder as starting examples.** Simulated: the folder name as key words does not help, and filing on them before 3 confirmed documents files many wrongly. | S | high | **Not built.** |
| **Phone photos and scans (JPG, PNG).** The reader refuses a picture today; turned into a one-page PDF in memory it reads through the existing OCR (a clean page image: 290–295 of 302 words). | S (reader) + M (checking) | medium: phone photos (angle, shadow, blur) are unmeasured; HEIC (iPhone) is not readable; photo rotation; the junk filter was tuned on slides; the reader is shared with SummarEase (a new tag) | **v1.1, first item**, after a check on about 20 real phone photos. v1 only if the owner supplies them before the freeze. |
| **Burmese.** Tesseract's Burmese data is installed. Matching reads Latin letters only, so Burmese text gives no words; it needs syllable splitting, Zawgyi and Unicode told apart (the same text in two encodings), name rules, the junk filter, a translated interface and Burmese development documents. | L | high | **v1.1 or later** (record F defers it). |
| **Everyday documents** (bills, receipts, IDs, letters). No development data, so nothing can be claimed. Receipts are very short (little text: they wait or go wrong); monthly bills from one sender look like versions of one document; IDs are mostly photos (the row above). | M (collecting and labelling 30–50 of the owner's own) | medium | **v1:** say so in the README's limitations. **v1.1:** measure on a household set. |
| **Installer and first-run guide** (sections 2 and 3). The first run should say: originals are never changed; choose the output folder; file about 10 documents (or learn from existing folders) before the app files by itself. Unsigned installers show a SmartScreen warning. | M–L | medium: bundling Tesseract and Qt; clean-machine test | **v1** (already a blocker). |

## 6. v1.1 (decided 2026-10-15; not built)

- **Phone photos and scans (JPG, PNG).** After the owner has collected about 20 real phone photos and scans: the
  reader turns a picture into a one-page PDF in memory and reads it with the existing OCR; checked on those photos
  (angle, shadow, blur, rotation), with HEIC (iPhone) said to be unreadable. The reader is shared with SummarEase,
  so a new reader tag follows.
- **A household test set.** 30–50 of the owner's own bills, receipts, IDs and letters, labelled, measured with
  `tools.evaluate` before anything is claimed about everyday documents.
- **Burmese.** The interface translated, and Burmese documents read and matched: syllable splitting, Zawgyi and
  Unicode told apart, Burmese OCR (Tesseract's data is installed), name rules and the junk filter, with Burmese
  development documents.

## Done when

- [x] Section 0 blockers done: record changes decided, matching updated, Check these answered, the full
      CP5 report command, the offline check.
- [x] Choices frozen in the record (2.10); final evaluation run once and reported (2026-10-16).
- [ ] Installer built and checked on a clean machine; licence notices included.
- [x] User README written (2026-10-15).
- [ ] All tests pass, `tools.check_ui` passes, the privacy audit has 0 hits, and v1 is tagged.
