# ClassiFile status

2026-10-19 · decision record version 2.11

## Done

**CP0 Foundation**
- Environment baseline (docs/dev/ENVIRONMENT.md), project skeleton with the isolated reader, GUI smoke test.
- Tools: inventory, family-based splits.

**CP1 First end-to-end slice**
- Import by drag-and-drop or file chooser.
- PDF extraction with observations and source locations, in a versioned extraction record.
- Rule-based candidate names with evidence (rules-8: file names no longer suggest names).
- Two-step filing: the user picks or types a category; filing happens only on the button or Enter.
- Verified copies: temporary name, hash check, publish without overwriting, catalog record.
- SQLite catalog; reopening the app shows the same state. Startup repairs half-done filings.

**CP2 Formats and OCR**
- Native extraction for PPTX, DOCX and ODT, with the Python standard library.
- Selective OCR (any non-repeated picture of at least 5% of its page or slide), with a junk filter and counts.
- Worker processes with per-file timeouts.
- Hidden internal summary record.
- Layout (lines, blocks, positions, sizes) kept in the extraction record for SummarEase later.
- E8 page-label check on development data.

**Since CP2**
- Remove from ClassiFile for waiting documents; Locate file… for originals that moved, checked by hash.
- Changing the output folder moves copies safely; edited copies stay and are flagged.
- Interface redesign: sidebar views, document list, a "Needs your decision" page with one primary action per
  question, group items, a details panel on request, notices and toasts, Settings, responsive breakpoints.
- Spacing pass: one shared spacing system; checked at 1024, 1100, 1280 and 1536 px wide, and at 125% and 150%
  scaling.
- Labelling windows for the E8 page labels, the OCR quality check and the name review.
- Dropdowns and disclosure arrows share the control style; the layout was checked at 1920×1080.
- Tests refer to development files by neutral IDs through a local map in `data\` and skip when it is absent.
- Details open beside the "Needs your decision" page (a Details link on each item; the panel slides in from
  the right and the page stays), so a document's pages and its filing buttons are in view together. The
  details panel no longer bounces when a section is opened.
- Decision page: the list stays where it is after filing (it used to scroll to the bottom); the "filed" message
  slides up into the bottom-right corner; the "more" button is first in every item; buttons share one outlined
  style and size, and focus changes only the border colour; "Choose another…" opens one panel whose list is as
  tall as its names (the second, small preview is gone: Details shows the pages).
- `tools.grouping`: the owner's grouping of development files, read from the catalog (read-only).
- Regrouping (record 2.0, B5): Move to… for filed documents (right-click menu and the bar for several
  documents), Rename category… and Delete category (right-click a category). Moves follow primary replacement:
  a verified new copy first, the old copy goes only if unchanged, edited copies stay and are flagged, nothing is
  overwritten, an interrupted move or rename finishes at the next start, each move is recorded as
  user-corrected. After a move the app asks once about the categories it left empty. Deleted categories stay in
  the catalog as history; their names are free again.
- One category picker everywhere a category is chosen: search anywhere in the name, document counts, recently
  used first, then alphabetical; "Create category 'X'" only as a separate last row; Up/Down, Enter, Esc.
- No one-click category creation once categories exist (B2): "Create & file" only for the very first category,
  "File in <name>" when the top suggestion is an existing category, otherwise "Choose category…".
- "None of these fit — type my own" with optional reasons; the rejection, the reason and the chosen category
  are recorded in the catalog. "Only one suggestion found" is said when that is the case.
- File names never suggest a category (B1): they only support a name the content already gives.
- `tools.inventory --families [--known <folder>...]` pre-fills family IDs as suggestions.
- AGPL-3.0 licence file (PyMuPDF is AGPL and the repository is public).
- The sidebar keeps its scroll position when it is rebuilt; Details, once switched on, stays on across the list
  pages and says what to do when nothing is selected.
- `tools.label_inventory`: a window to fill in the labels of an inventory one file at a time (pages shown,
  the category picker, saved into the CSV after every answer). After a split, `--splits` shows each file from
  its split's folder and `--only <label>` just the files recorded under one label, to give them other labels.
- `docs/archive/UI_PROPOSAL.md`: measurements and a phased proposal for the interface; phase 1 is built (below).
- **Interface phase 1 (responsiveness and search):** the window is updated in place instead of rebuilt.
  Decision cards are kept while their question is unchanged; the document list and the sidebar are models
  (`classifile/app/models.py`) with the view, the search and the sort as a filter; one refresh per document
  read, five queries each. The sidebar shows category names with counts only. Search matches file name and
  category on every page (Ctrl+F, Esc, "3 of 7", a nothing-found state, cleared on view change).
  Measurements and the acceptance results are in section 9 of the proposal.
- Status column: a filed document shows "Approved" with a green check (it used to be blank). Every filed
  document was filed by the owner's choice so far; automatic filing (CP4) will need its own word.
- Decision page: each item uses the page's full width, with its buttons at the right and its number in the
  list before its name. While details are open beside the page (or the item is too narrow for both) the buttons
  sit under the suggestion. An item's Details button closes the details it opened, and stays pressed meanwhile.
  Opening an item's choices scrolls the page so they are in view (they used to open below the window).
- `tools.measure_ui` (timings on a made-up catalog) and `tools.check_ui` (the acceptance checks at four window
  sizes and three scalings).
- `tools.apply_split`: moves a split's files into `data\development`, `data\validation` and `data\final-eval`,
  all or nothing, never over an existing file; `--previous` applies a split made again.

**CP3 Matching to existing categories (2026-10-13; the owner's order: before interface phases 2 and 3)**
- The goal is in the record (A0, version 2.2): an automatic categorizer; choosing by hand is the fallback.
- `classifile/matching.py`: one word-level TF-IDF representation fitted on the training documents only, and the
  primary scorer chosen in E2, nearest centroid. Standard library only: no new dependency.
- A model is a versioned bundle in the catalog (preprocessing, vectorizer, category mapping, decision
  settings). It learns only from placements the owner chose or corrected, never from the app's own.
- **Update matching** (Settings): retrains on the filed documents, off the interface thread. The new version
  is checked against the one in use on the documents filed or moved since (the new one is never trained on a
  document it is asked about, or on a near-identical version of it); if it does worse, the previous version
  stays in use and the new one is recorded as rejected.
- **Decision cards:** when existing categories are a good match, a card shows the three best, ranked, each a
  one-click "File in …" with a plain reason ("Similar to 9 documents in …"). When none is a good match (the
  abstention baseline, E4) it says so and shows the suggested new name instead. No score is ever shown. The
  suggested new names stay under "Choose another…". Creating a category still takes an explicit choice (B2).
- Tools: `tools.match_eval` (E2 and E4 on development data), `tools.match_validation` (validation, measured
  once; it refuses a second run), `tools.file_labels` (files waiting development documents from the owner's
  labels, as normal verified copies).
- The owner's 15 waiting development documents were filed from their labels: 83 documents filed in 10 categories.
- Tests: the smoke test no longer depends on a time limit or a fixed delay, and the worker test's healthy read
  has a generous limit (both could fail on a busy machine).
- Not built from the record's CP3 list: selected-category mode and "Also belongs to" (proposed for CP4, see
  `docs/archive/CP4_PROPOSAL.md`).

**CP4 Automatic mode (2026-10-13; the owner's decisions are in the record, versions 2.3 and 2.4)**
- **Automatic filing, built.** A document that is read is filed without a question when its best category
  leads the second by the level in use (Strict, the owner's choice) and that category already holds 3 documents
  the owner confirmed. Otherwise it waits with the three best categories, as before. The copy is the normal
  verified copy; the placement is recorded as machine-assigned with what it rested on, and never trains the
  matcher. Waiting documents are looked at again after "Update matching", after a change of level or of the
  selected categories, and whenever the owner files, moves or confirms a document (a category may then hold the
  3 confirmed documents it takes).
- **Filed automatically** (sidebar view): what the app filed by itself, each with its reason, "Looks right" and
  Move to…. "Looks right", for one document or for all the ticked ones, records the owner's confirmation: the
  documents become training examples. A move is the correction. In the document list such a document's status
  reads "Filed automatically" until it is confirmed or moved, then "Approved".
- **Settings:** the level (Off, Very strict, Strict, Balanced, Lenient) and where to file ("All categories" or
  "Only the ones I tick", with a tick per category); every change is recorded in the catalog. The mode in use
  is always shown at the top of the window, with a link to Settings. The Settings page uses its full reading
  width.
- **Selected-category mode:** a document is filed automatically only when its best category among all
  categories is a ticked one; a selection never raises a document's confidence (B1). Creating a category always
  takes the owner's explicit choice.
- **Grouping new subjects:** waiting documents that match no existing category and resemble one another
  (average similarity of at least 0.15, the owner's choice after the development report) are one question:
  the shared key words first, each document's file name with a tick and a Details link, an empty name field,
  and the suggested names as optional choices. Nothing is created or filed until the owner types the name;
  unticked documents keep waiting. `tools.group_eval` is the development test; its result is below.
- **Also belongs to…** (right-click a filed document): a second verified copy in another category. The
  document's own category, and what the matcher learns from, do not change; it is listed and counted in both.
  Moving the document leaves the second copy where it is. An "also belongs to" that stopped before its copy was
  made is undone at the next start.
- Not built: removing an "also belongs to" again; single-document automatic creation and the discovery replay
  (E10) from the record's CP4 list.

**Interface phases 2 and 3 (2026-10-13, after CP4, in the owner's order)**
- Settings uses the whole page, like the other pages: text at the left, controls at the right.
- **Phase 2, the page preview:** while the panel is resized the picture already drawn is scaled; the page is
  drawn once when the resizing stops, and the last 8 drawn pages are kept, so paging back draws nothing. A
  20-step resize draws the page once (tested).
- **Phase 3, tokens:** `classifile/app/tokens.py` names every colour, text size, radius, spacing, layout width
  and duration once; the style sheet and the widgets use those names. A test fails when a colour, a pixel size,
  an inline style or a duration appears in another interface module. Text sizes are 12, 13, 14, 16 and 22
  (15, 20 and 32 are gone); radii are 4, 6, 8 and 10 (12 is gone). The coordinates inside the two small
  drawn icons stay with their drawing code.
- **Phase 3, appearance:** Settings, "Light or dark": Follow Windows (default), Light, Dark. Colours come from
  the palette, so nothing else changes. Switching was checked on the real display; off-screen checks set a
  light and a dark palette by hand.
- **Phase 3, accessibility:** every button without words (☰, +, ⋯, ✕, ‹, ›) and every unlabelled tick, field
  and dropdown has a name a screen reader can say; the acceptance checks fail on a button that has none. A
  focused list shows the same teal border as a focused button or field.
- **Decision 3 (card actions):** "Leave pending" is in the ⋯ menu with "Remove from ClassiFile". A card keeps
  its main action (or the three matching categories), "Choose another…" and "Details".
- **Decision 4 (narrow windows):** details stay beside the cards and the cards put their buttons under the
  text. The sideways scrolling at 1024×640 with details open is gone.
- Found on the way: the empty "Filed automatically" message was one unwrapped line that set the least width of
  every page and squeezed the details panel; it wraps now.
- `tools.check_ui`: all checks pass at 100%, 125% and 150%, including the two palettes and the button names.
- 260 automated tests.

**Redesign of "Needs your decision" and "Filed automatically" (2026-10-14, the owner's request)**
- Both pages: title and count, the search, a list capped at a readable width, and one Details panel. A click on a
  row inspects it (teal tint and bar; hover is grey); it never files or confirms. Up/Down walk the rows and
  details follow; Esc closes details and returns to the row. Details sit beside the list while it keeps 520 px,
  otherwise over it with "Back to list" (replaces decision 4: beside the cards even when narrow).
- Decision rows: name, "Suggested category: **X**", one line of reason, one main action, then quiet "Choose
  another…", "Details" and ⋯ at the end. The second and third matching categories stay one click away as quiet
  "Or file in:" links (record B2); in the picker they come first. Buttons stack under the text, then on two
  lines, when room is short.
- Auto-filed rows: tick, name, Filed in, status (Not reviewed / Confirmed / Moved by you), "Looks right"
  (outlined) and a quiet "Move to…". A reviewed row stays in its place until the page is left. The bulk bar shows
  the count and "Looks right (N)" only when something is ticked. The "need your decision" notice is a quiet line.
- Details: file name (and the filed name only when it differs), "Suggested category" or "Filed in", status with
  review state, preview, why, and the paths folded under "File locations".
- Motion: details slide in and out, a row's choices unfold; all instant when Windows' Animation effects is off.
  Ticks use the ClassiFile teal.
- `tools.check_ui` covers the auto-filed page and reduced motion; all pass at 100%, 125% and 150%.

**Accuracy round (2026-10-13; a report, nothing changed in the app)**
- `tools.accuracy_round` measures changes to the representation with the E2 test, one at a time: extra weight
  for titles, headings and the first page; character n-grams; word pairs; less weight for OCR text and template
  lines; very common words left out. None clearly beats the matcher in use. One combination is a little better
  on development data and met the rule set for validation by one document. The numbers that move most are the
  documents per folder. Report: `docs/archive/ACCURACY_ROUND.md`. The owner decides whether to adopt anything.
- The record (2.5) now says that ClassiFile never creates a folder by itself; the discovery replay is not needed.
- 261 automated tests.

**Matcher checked on new files and retrained (2026-10-14)**
- The owner's run on 33 new files at Strict: 21 filed automatically (20 kept, 1 moved: a file of a new subject),
  12 waited (the owner filed them). The matcher put the owner's category first for all 28 files whose category
  existed.
- The accuracy-round combination was measured on the same 33 and on all 116 documents: no gain on the new files,
  more wrong at Strict on the 116. Not adopted (`docs/archive/ACCURACY_ROUND.md`, section 9). No code changed.
- Matching version 3 (116 documents, 12 categories) is in use; on the 33 it puts the owner's category first for 32,
  version 2 for 28. A copy of the catalog from before is kept beside it.

**More automation, interface phases 4 and 5 (2026-10-14; record 2.6, the owner's correction and decisions)**
- The record (2.6): in automatic mode the app may create a folder for a group of at least 2 unmatched waiting
  documents at 0.20 (A4, B2); matching also updates by itself after every 10 confirmations or moves (A7).
- **Automatic new folders, built and off** until the owner has read the replay and turns them on.
  - The replay (`tools.group_eval --folders`) found 21 folders over 12 rounds: 0 mixing subjects, and 1 subject
    split (into 7).
  - It also found 10 second folders for subjects the app already has: 2 distinct pairs.
  - Report: `docs/archive/AUTO_FOLDERS.md`.
- The levels on the owner's 33-file run, each file asked of a model trained without it: Strict 28 filed, 0 wrong,
  5 waiting; Balanced the same; Lenient 31, 0, 2. Strict stays.
- **Learning by itself**, with the usual check; the versions are logged in Settings, and a note shows each update.
- **Cards** give 2 to 4 shared key words as the reason.
- **After each import**, one summary line.
- **Phase 4:** Settings, "Motion"; a filed row folds away (instant with reduced motion).
- **Phase 5:** Retry for unreadable documents; "Find category…" from 11 categories.
- `tools.check_ui` checks "Find category…" and Reduce motion now; all pass at 100%, 125% and 150%.
- Catalog schema 10 (a mark for folders the app named; who started each matching update).
- 268 automated tests.

**The owner's decisions, and a colour redesign (2026-10-14; record 2.7)**
- Automatic new folders are on for groups of at least 3 documents; pairs stay a question. Strict stays.
  - Replay with the minimum: 3 folders, 0 mixed, 0 second folders for known subjects, 1 subject in 2 folders.
- **Two complete themes** in `classifile/app/tokens.py`: every surface, text, line, accent and status colour, for
  light and for dark.
  - The cause of the white text in light mode: the style sheet mixed fixed colours with the system palette and grey
    mixes, so text took Windows' colours when they disagreed with the chosen appearance.
  - Now the style sheet and the Qt palette (the Fusion lists, native controls and dialogs included) are built from
    the theme in use, and rebuilt, with every icon and row, whenever the appearance or Windows' setting changes.
  - Hard-coded white is left only on the light theme's primary buttons and the dark overlays.
- Each category has a dot in one of 8 colours, readable in both themes and the same for that category always
  (from its id).
- `tests/test_theme.py` computes the contrast of every pair in both themes: text at least 4.5:1; icons, control
  borders and the selection and focus bars at least 3:1. Dividers are decorative and not held to 3:1.
- Values changed from the owner's starting point where a check failed:
  - light amber #AA4F09 and green #14793A (for tinted rows);
  - dark selection #0D3532 (for the dots and the red text);
  - control borders #7D8796 (light) and #5F7E85 (dark), since #D9DEE5 and #2A3D42 are under 3:1 and stay as
    dividers;
  - the format glyphs and dots, slightly brighter or darker so both themes pass.
- Found by eye in the screenshots, and fixed:
  - Settings cut its text on short windows; it scrolls now.
  - The details panel showed the page colour behind its body in dark mode.
- `tools.render_window --theme light|dark|both` renders with the app's themes (the hand-made dark palette is
  gone); `tools.check_ui` checks both themes through the setting.
- Screenshots of the main pages in both themes: `data\render-light-*.png` and `data\render-dark-*.png` (local).

**Calmer colours (2026-10-14, the owner's request)**
- **Dark theme is neutral charcoal**, with no teal in the backgrounds: #1C1E21 page, #18191C sidebar, #212428
  lists, #272A2F panels, #33373D lines, #E6E8EB and #A0A6AD text.
- **Primary buttons** are #0F766E with white text in both themes. #2DD4BF is gone.
- **Selection** is a faint teal tint (#223234 in dark) with a 2 px bar (#2B9C8E in dark).
- **Status colours** are muted: amber #D29922, green #57AB5A, red #EA756F. #E5534B was under 4.5:1 on panels and
  the selection.
- **Rules for both themes, now tested in `tests/test_theme.py`:**
  - Teal only on the primary button, the selection bar, the focus outline and links.
  - Large surfaces and lines are neutral grey; hover is a grey change.
  - Ticked boxes, toggles, accent buttons, tags, menus and the drop overlay are neutral.
- **Category dots:** 8 muted colours, 8 px.
- **Values changed where a check failed:**
  - outlines #82868C (light) and #777A7F (dark), since #7D8796 and #737A83 had a blue tint;
  - the light toast #26292E;
  - the overlays #16181B, since #111827 was navy;
  - links in dark #38A899, to reach 4.5:1 on panels.
- A primary button is told by its white label; its fill against the page is no longer held to 3:1.
- Screenshots of both themes: `data\theme-calm\` (local).

**One evaluation, and an update check on everything (2026-10-15, the owner's instruction before the CP5 freeze)**
- **One evaluation for every number from now on:** `classifile/evaluation.py`, printed by
  `python -m tools.evaluate` (add `--rules` for the safer filing rules, `--json FILE` to save the rows). Numbers
  in this file from before 2026-10-15 came from earlier tools (`tools.match_eval`, `tools.accuracy_round`,
  `tools.group_eval`) and are kept as history; they are not comparable one to one.
  - Each family held out in turn; the word weights fitted inside each fold; no random step, so the same catalog
    gives the same report (a seed is not needed because nothing is drawn at random).
  - Families: the owner's family ids (recorded once in the catalog with `tools.evaluate --set-families
    data\splits_incoming_2.csv`: 50 of the 118 files), the same bytes, the same file name apart from the
    extension and copy marks, or nearly the same text. The owner's ids matter: three lectures in parts are one
    family only by them, and without them the report counted 4 more documents "right first".
  - It prints what was counted and left out, the model and every threshold, right first and in the first three
    overall and per category, automatic filing at each level, new subjects wrongly filed, the "Check these" list,
    and a 95% range (Wilson) beside each share.
- **Why 116 and not 118:** 2 documents are the only family of their category (two single-document folders). Held
  out, their category has no example left, so they cannot come first; they are left out of "first" and "in the
  first three" and still counted in automatic filing, where filing them anywhere is wrong.
- **The evaluation on 2026-10-15** (118 documents filed by the owner, 113 families, 12 categories; model version 4
  in use, trained before the owner's last moves; the evaluation retrains the same method in each fold). These
  counts describe the owner's development documents; they are not accuracy estimates.

  | | Count | 95% range |
  |---|---|---|
  | The owner's category first | 100 of 116 | 79–91% |
  | In the first three | 112 of 116 | 91–99% |

  | Level (lead) | Filed right | Filed wrong | Waiting | New subjects wrongly filed, of 118 |
  |---|---|---|---|---|
  | Very strict (0.15) | 46 | 0 | 72 | 0 |
  | **Strict (0.10), in use** | 74 | 1 | 43 | 2 |
  | Balanced (0.06) | 85 | 2 | 31 | 15 |
  | Lenient (0.03) | 94 | 6 | 18 | 39 |

- **The update check now looks at everything** (record A7): a new matching version and the one in use are both
  measured on that full evaluation (the old one replayed on its own training, so both answer the same
  questions). The new one replaces the old only if wrong automatic filings at the level in use do not increase
  and "right first" does not drop. Both results are kept with the version and shown in Settings. It used to
  ask only about the documents filed or moved since the last version.
- **Safer filing rules, tried on development data only (item 3; nothing adopted):** each rule added to the lead.

  | At Strict (0.10, in use) | Filed right | Wrong | Waiting | New subjects wrongly filed |
  |---|---|---|---|---|
  | Lead only (in use) | 74 | 1 | 43 | 2 |
  | a. best similarity ≥ 0.20 / 0.25 / 0.30 | 74 / 72 / 70 | 1 | 43 / 45 / 47 | 2 |
  | a. best similarity ≥ 0.35 | 50 | 0 | 68 | 1 |
  | b. nearest 1 of 1, 1 of 3, 2 of 3, 3 of 5 in the best folder | 74 | 1 | 43 | 2 |

  | At Balanced (0.06, for comparison) | Filed right | Wrong | Waiting | New subjects wrongly filed |
  |---|---|---|---|---|
  | Lead only | 85 | 2 | 31 | 15 |
  | a. best similarity ≥ 0.30 / 0.35 | 77 / 52 | 2 / 1 | 39 / 65 | 12 / 3 |
  | b. the nearest document in the best folder | 85 | 2 | 31 | 11 |
  | b. 2 of the 3 nearest / 3 of the 5 nearest | 83 / 82 | 2 | 33 / 34 | 13 / 12 |

  At Strict no rule lowers new subjects wrongly filed without filing clearly fewer documents (the only one that
  lowers it, similarity ≥ 0.35, files 24 fewer), so by the owner's rule none is kept. At Balanced, "the nearest
  document is in the best folder" lowers it from 15 to 11 and files as many: worth considering only if the owner
  moves to Balanced.

**Check these, and the owner's settings (2026-10-15)**
- **Check these** (item 4): filed documents whose content, held out, matches another category ahead of their own
  by at least the Strict lead (0.10). Listed at the top of "Needs your decision" with Move to… and Keep here;
  Keep here is recorded and not asked again while the document stays there. Nothing moves by itself. The list
  comes from the last update check, so it appears after the next "Update matching". On 2026-10-15 the
  evaluation lists 2 documents.
- **Settings in the owner's catalog, as the record says (2.7):** automatic new folders **on** (they had been
  switched off again on 2026-10-14 at 15:09, after several on/off changes within seconds; the change log keeps
  them all), at least 3 documents per folder at an average similarity of 0.20, automatic filing at Strict, all
  categories. A copy of the catalog from before is kept (`catalog.before-evaluation.sqlite3`).
- Catalog schema 11. Matching version 4 is in use; it was trained before the owner's last three moves, so the
  next update (by hand, or by itself after 10 confirmations or moves) learns them.

**Interface defects on the two review pages (2026-10-15, item 6; fixes only, no redesign)**
- Rendered with made-up documents (long names, automatic filings, an app-named folder, Check these, waiting
  cards), both themes, 1280×720 and 1024×640, with and without Details. List and screenshots:
  `data\ui-defects\DEFECTS.md` (local).
- Fixed: Check these rows put their buttons under the text when room is short, as the cards do; Details shows
  "Why this category" above the page preview; documents filed in the same second are listed in a stable order;
  the notice counts what the sidebar counts (waiting documents and filed documents to check).
- `tools.check_ui` passes at 100%, 125% and 150%.

**Toward friends and family (2026-10-15, the owner's instruction; measurements are report only)**
- **Record 2.8** written as the owner approved it (update check, one evaluation, Check these, E1 and E5–E7 not
  built for v1).
- **Part E report, one command:** `python -m tools.quality_gate [--out FILE]`: the one evaluation with outcomes and
  real use, the replay of automatic new folders (the owner's family ids from the catalog), and every Part E item
  at the level in use. On 2026-10-15 (matching version 6, Strict): 0 of 75 automatic filings wrong; 1 of 118 new
  subjects forced into an existing folder; 4 folders created in the replay, none mixing subjects, no second
  folder for a known subject; 1 of 12 held-out subjects split over two folders; 43 of 118 waiting (36%, range
  28–45%); 40 distinct questions, 1.07 documents per decision; later corrections 1 of 21 automatic placements.
- **Offline check:** `python -m tools.offline_check [FOLDER]` (default: the six samples) runs the window offscreen
  with a fresh catalog, imports through the reader worker processes with OCR, files, learns, files by itself,
  checks every copy's hash and reopens the catalog, while every Python process refuses and records network access
  (a temporary sitecustomize). The six samples: PASS, 0 attempts. Its own test caught a first version whose guard
  let everything through; fixed before any result was used. Still to do: the owner runs it with the laptop's
  networking switched off.
- **True and false positives** (`python -m tools.evaluate --outcomes`, development data, each family held out):

  | Level | Right (TP) | Wrong (FP) | New subjects forced, of 118 | Missed automation | Correct waits | Precision | Coverage |
  |---|---|---|---|---|---|---|---|
  | Very strict | 47 | 0 | 0 | 54 | 17 | 47 of 47 | 40% |
  | **Strict (in use)** | 75 | 0 | 1 | 26 | 17 | 75 of 75 (range 95–100%) | 64% (55–72%) |
  | Balanced | 85 | 2 | 15 | 16 | 15 | 85 of 87 | 72% |
  | Lenient | 95 | 4 | 38 | 6 | 13 | 95 of 99 | 81% |

  - Per category at Strict: the largest folder (50 documents) 90% coverage; the 17-document folder 88%; the 11-
    and 6-document folders 0% (their documents wait: the two share cover-page wording); folders of 3 or fewer
    documents 0%.
  - Causes of the 42 distinct false positives over all levels (a document may have several): shared vocabulary
    with the folder it went to 42 (so it does not tell them apart), a broad folder (the largest, about 45% of the
    training documents) 27, template text 4, OCR text 2, very little text 1. OCR and template text are named only
    when taking them away sends the document elsewhere.
- **Real use** (`--real-use`): 21 automatic placements, all by matching version 2: 20 "Looks right", 1 moved (to a
  folder created after it was placed), none left untouched.
- **A new user's first days** (`python -m tools.cold_start [--shuffle SEED]`, development data, empty start,
  Strict; matching trained once two folders exist, then after every 10 decisions; placements not reviewed):

  | Variant (arrival order; shuffled orders 1–3 in brackets) | Decisions | Filed by itself right / wrong | Decisions before the first automatic filing |
  |---|---|---|---|
  | The app as it is | 75 (54–64) | 37 / 6 (51–53 / 3–11) | 10 (5–12) |
  | a. Existing folders hold 3 per folder (87 arrive) | 43 (30–35) | 44 / 0 (52–57 / 0) | 1 (2–11) |
  | a. Existing folders hold half of each (63 arrive) | 30 (26–28) | 31 / 2 (34–36 / 1–2) | 1 (1–2) |
  | b. Folder name as key words, 3-document rule kept | 68 (49–65) | 47 / 3 (50–52 / 1–17) | 11 (10–16) |
  | b. Folder name as key words, rule relaxed | 68 (41–57) | 37 / 13 (43–49 / 17–34) | 0 (0–2) |
  | b. 5 best words (an upper bound), rule relaxed | 58 (50–56) | 51 / 9 (60–62 / 2–7) | 1 (0) |

  - In a cold start the app files wrongly where the steady state does not (6 in arrival order; 3 of them because
    their folder did not exist yet): early models know few documents.
  - "Learn from my existing folders" with 3 documents per folder filed nothing wrongly in all four orders and
    roughly halved the decisions. Key words from the folder name do not help, and filing on them before 3
    confirmed documents files many wrongly.
  - Today a new user's first matching model comes only from pressing "Update matching" in Settings: the update
    after every 10 confirmations (record A7, 2.6) never starts while no version exists. The simulation assumes
    the first model is trained as soon as two folders exist.
- **Pictures (JPG, PNG):** the reader refuses a picture opened as a document (an error while reading pages); the
  same picture turned into a one-page PDF in memory reads through the existing OCR: a dense sample page rendered
  at 100–200 dpi gave back 290–295 of its 302 words. A clean rendering, not a phone photo.

**v1 for friends and family (2026-10-15, record 2.9)**
- **The first matching version is learned by itself** once 10 confirmations or moves exist in at least two
  categories (it used to wait for "Update matching").
- **Learn from my existing folders** (Settings, the start page, the tour, Help): the user picks an organized
  folder; its subfolders are proposed as categories with document counts, to untick or rename; the files are read
  in the worker processes and kept as examples (catalog schema 12: table `examples`, document status `example`).
  They train matching and count toward the 3 documents automatic filing needs; they are never listed, copied or
  moved. Settings lists the folders with Forget. Adding one of those files later makes it a normal waiting document.
- **Help, About and a first-run tour** (four steps; it offers to learn from folders at the end). About: what
  ClassiFile is, how it works, privacy, ClariFile and SummarEase, version 1.0.0-rc.1, licences and credits, the
  source link.
- **Interface:** every page uses the full window width (Needs your decision and Filed automatically stopped at
  1120 px), with sentences kept to a readable 720 px; the Details button is on every page that lists documents;
  Settings keeps matching versions, the log and version numbers in a collapsed Advanced section. Before and after:
  `data\ui-width\` (local, made-up documents). `tools.check_ui` passes at 100%, 125% and 150%.
- **README** for the public with screenshots of a made-up library (`docs/images`, from `tools.screenshots`), and
  the user guide in `docs/guide/` (English; Burmese marked for the owner's review).

**CP5: freeze and the final evaluation (2026-10-16, record 2.10)**
- Frozen: matching version 6, Strict with 3 confirmed documents, the folder rules, the update check and Check these.
- `tools.final_eval` read `data\final-eval` once (28 documents, 22 families) with version 6 on a catalog copy; the
  result is `data\final_evaluation.json` (local) and a second run is refused. The owner's category first for 26 of
  28 and in the first three for 27; at Strict 18 filed right, 0 wrong, 10 waiting; no new folder (every final
  label is an existing category). Table in docs/LAUNCH.md section 1. Counts on a small held-out set, not a
  promise of accuracy.
- Needs your decision: each row has its own Details (Check these rows too; a group lists its documents); the
  page-level Details switch is gone from that page.
- Help and About: captioned sections, each a padded card of topics.

**The Windows installer (2026-10-17, docs/LAUNCH.md section 2)**
- `installer/`: PyInstaller spec, Inno Setup script, the licence texts and notice, and `installer.build`. The setup
  file installs per user, offline; uninstalling keeps documents, copies and the catalog (checked on the build laptop).
- `ClassiFile.exe --self-test REPORT FILE...` checks an installed app: reads in a worker process with OCR, counts only.
- Help, About and Settings: cards span the full width again; long text was cut off where a wrapped label had a
  maximum width straight in a column (Settings' new-folders sentence too). `readable()` in widgets.py, and a test.
- Next: the clean-laptop test (`docs/INSTALLER_TEST.md`).

**Pilot features (2026-10-17)**
- Help, "Copy problem report…": a dialog shows the whole report (versions, Windows, counts, settings and their
  changes, the matching log, the last ten problems), and Copy puts it on the clipboard; no file, no network. Documents
  are "document N"; problem reasons that may name a file or folder are given only by their kind. A test checks
  that no file name, path, category name or document line gets in.
- Help, "Check for updates": opens the releases page in the browser, only on a click.
- README and the guide (sections 12 and 13): the SmartScreen warning, updates, uninstalling, and the problem
  report. The new Burmese sections are marked for the owner's review.
- `docs/guide/pilot.md`: one page, English and Burmese, for the first week of the pilot.

**1.0.0-rc.2 for the pilot (2026-10-17)**
- Smooth scrolling: a mouse wheel turn glides every list and page (160 ms, eased; quick turns add up). Instant
  with reduced motion; touchpads, Ctrl+wheel and sideways scrolling are left to Qt. Item lists scroll by pixel.
- Built with `installer.build` (`dist\ClassiFile-1.0.0-rc.2-setup.exe`, about 52 MB); the built app's self-test
  on the six samples: PASS. The clean-laptop test (`docs/INSTALLER_TEST.md`) is still open.

**1.0.0-rc.3 for the pilot (2026-10-19)**
- Text fills its card on every page (no readable-line-length cap), so Help, About and Settings no longer leave an
  empty band at the right.
- Built with `installer.build` (`dist\ClassiFile-1.0.0-rc.3-setup.exe`, about 52 MB); the built app's self-test
  on the six samples: PASS. The clean-laptop test (`docs/INSTALLER_TEST.md`) is still open.

## Development results so far

These counts describe development data only. They are not accuracy estimates.

- **Scorer comparison (E2, 2026-10-13):** the 83 filed documents (78 families, 10 categories of 32, 11, 10, 8,
  7, 6, 4, 3, 1 and 1 documents), each family held out in turn, the vocabulary and every scorer fitted on the
  rest. 81 documents have a category with other families; the other 2 are a new subject when held out.
  - The owner's category first / in the first three, of 81: nearest centroid 65 / 77; kNN 69 / 79 (k = 1),
    67 / 79 (k = 3), 66 / 79 (k = 5); logistic regression 36 / 64 (C = 1), 56 / 73 (C = 10), 58 / 75 (C = 100).
  - With one to three examples of the category (7 documents): nearest centroid 3 first, kNN (k = 1) 4,
    logistic regression none.
  - A growing catalog (a quarter, then half, of the other families training): nearest centroid 49 of 71 and
    58 of 77 first; kNN (k = 1) 51 and 65; logistic regression (C = 100) 43 and 51.
  - Per category, nearest centroid, first / in the first three / documents: 30/32/32, 8/11/11, 9/10/10, 6/8/8,
    6/6/7, 3/6/6, 2/3/4, 1/1/3, and the two single-document categories 0/0/1 each (nothing to learn from).
  - Chosen: **nearest centroid**. kNN puts the right category first for a few more documents, but nearest
    centroid knows much better when not to file (next point), which automatic filing depends on; it is also
    the record's default when the comparison is close. Logistic regression is behind on every count.
- **Abstention (E4, global baseline):** one level for all categories, set on how far the best category leads
  the second (set on the best score alone it was clearly worse). Documents filed right while at most 0 / 1 / 3
  are filed wrong: nearest centroid 32 / 54 / 60; kNN (k = 1) 34 / 35 / 48, (k = 3) 14 / 44 / 57, (k = 5)
  27 / 34 / 60; logistic regression (C = 100) 32 / 39 / 43.
  - New subjects: with each whole category held out, all 83 documents are of a subject never seen, and filing
    any is wrong. At those same levels nearest centroid files 0 / 5 / 16 of them; kNN (k = 1) 7 / 8 / 12.
  - Cards use a lenient level (lead of 0.02). Of the 81 documents whose category exists, 66 would show three
    categories (64 with the owner's among them, 61 with it first) and 15 a suggested new name; of the 83 held
    out as new subjects, 39 would show a new name and 44 existing categories.
- **Grouping new subjects (2026-10-13):** each of the 11 categories held out in turn (83 documents). 43 of the
  documents then match no existing category; the other 40 are taken for an existing one and are never grouped.
  - At an average similarity of 0.15: 30 of the 43 land in a group, with 2 documents of another category mixed
    in. Of the 7 categories with at least two unmatched documents, 2 come back as one group, 4 are split into
    several groups or leave documents alone, and 1 is mixed.
  - At 0.20: 20 of the 43 land in a group and none is mixed; 1 category comes back as one group, 6 are split.
  - The key words shared by a group read as its subject; the suggested names are lesson titles, so the owner
    would usually type the folder name. The reports with the groups are local (`data\grouping_report_*.txt`).
- **Validation, measured once (2026-10-13):** model version 1 (the 83 development documents) on the 23
  validation documents. The owner's category first for 21 and in the first three for all 23. Per label, first /
  in the first three / documents: 10/10/10, 2/4/4, 3/3/3, 3/3/3, 2/2/2 and 1/1/1. One label names no category;
  its 2 documents are counted under the category the owner filed that label's development files in. Every
  validation document belongs to an existing category, so validation says nothing about new subjects.
  The strictness trade-off for automatic filing is in `docs/archive/CP4_PROPOSAL.md`. The saved result is
  `data\validation_matching.json` (local).

- **Selective OCR (E8):** the adopted rule caught 139 of 160 units with content the native text misses.
- **Name review:** 21 of 34 development files had at least one good name in the top three; 76 suggested names
  were marked not good. The most common problems were subtopics (sections of a document rather than the
  whole), course or series names, fragments and generic or template words. The acceptable names are kept outside
  the repository.
- **OCR quality:** 40 OCR outputs were judged twice. First round: 4 good, 9 partly good, 27 bad. Second round,
  with PDFs showing only the regions OCR read: 5 good, 8 partly good, 27 bad (PDF 5, 8 and 16; slides 7 bad;
  text documents 4 bad). 25 of the 40 answers were the same in both rounds.
- **OCR comparison:** blind, one pass against extra passes on the same 40 items: 4 extra, 3 current, 33 same.
- **Second name review:** 34 files, 80 names marked not good, 7 skipped, none good, 3 category names typed.
- **The owner's grouping (G3), rules-7 suggestions:** 32 of the 34 development files filed, 2 still waiting.
  32 categories, one document in each. The category was a suggestion as shown for 29 documents (23 the first
  name, 4 the second, 1 the third, 1 under "More"), part of a suggestion for 1, and typed for 2.
  No two documents share a category, so the comparison of grouping policies (E1) has no pair to measure:
  over-merging and fragmentation are 0 for every policy tried, and no policy put two documents together
  either. This grouping cannot rank policies; a grouping with shared categories would.
- **The owner's ruling on it (2026-10-12):** one category per document is not wanted; the names were mostly
  accepted as offered. The owner regroups the 34 files into broader folders, roughly one per course or
  subject. The regrouped library is then the reference grouping (G3) for E1. The first filing and both name
  reviews are history only: not labels, not training data.
- **The regrouped library against grouping policies (E1, 2026-10-12; in the record since 2.1):** 32 of the 34
  development files are filed (the other 2 are not in the catalog) in 8 categories of 8, 7, 6, 6, 2, 1, 1 and 1 documents: 80 pairs of documents the owner keeps
  together. 28 categories were typed, 2 are a suggestion as shown and 2 part of one. Every stand-in policy (top
  suggestion; cover line; repeated line; repeated, else cover, else top; file name) put no two documents
  together: over-merging 0, and all 80 pairs fragmented (placed apart or left pending). Even putting together
  every pair that shares any suggested name keeps only 8 of the 80 pairs and over-merges 4. The suggested names
  are lesson-level; the owner's folders are subject-level and mostly not written in the documents. Names found
  in a document cannot produce this grouping; matching against the owner's existing categories (CP3) has to.
  The suggestions compared are the stored ones (rules-7). No rule was changed.
- **Incoming files, split (2026-10-12):** the owner labelled all 104 (6 labels, all spelled as the catalog's
  categories; one label holds 86 files). 3 files were byte-for-byte copies of development files and were
  deleted from `data\incoming` with the owner's leave. The other 101 files (89 families) were split by family
  50/25/25 (seed 20261007): development 52 files (45 families) in `data\development`, validation 26 (22) in
  `data\validation`, final evaluation 23 (22) in `data\final-eval`. No family is in two splits; no two
  families share page text. The 9 families with several files are lectures sharing a cover page, kept together.
  The small labels fell unevenly (two labels have no development file). Record: `data\splits_incoming.csv`.
- **Incoming files, split again (2026-10-12):** the owner gave 39 of the files under the one broad label three
  new labels (9 labels now; no typos, no family with two labels; three of the labels are not catalog
  categories). Split again by family 50/25/25 with the same seed, before anything was built on the first one:
  development 50 files (45 families), validation 23 (22), final evaluation 28 (22). 62 files changed folder;
  the rest were not touched. The split balances families, not files, so the file shares are 50/23/28 of 101.
  Three small labels still have no development file or no held-out file. Record: `data\splits_incoming_2.csv`
  (the first record is kept).
- **Incoming files, inventory:** 104 PDFs in `data\incoming` (one flat folder), inventoried in
  `data\inventory_incoming.csv`. Suggested families: 92, of which 9 hold several files (21 files) because
  their first page reads the same; no two files have the same bytes; 3 files look like versions of development
  files and are marked to join development. Labels are empty (no subfolders). Suggestions for the owner to
  review; nothing was read beyond hashes, page counts and a digest of each first page's text.

## Validation: every use so far

`data\validation` (23 files) is kept apart for operating choices (record B4). Every time it has been used:

1. **2026-10-12, split and labels.** `tools.apply_split` moved the split files into `data\validation`; the owner
   saw their pages to label them (`tools.label_inventory --splits`). Nothing was measured.
2. **2026-10-13, the matcher measured once** (`tools.match_validation`, model version 1, 83 documents in 10
   categories): the owner's category first for 21 of 23, in the first three for 23; at the five levels fixed
   beforehand, Strict filed 14 with 0 wrong and 9 waiting. The owner chose Strict from this and the development
   numbers (`docs/archive/CP4_PROPOSAL.md`, record 2.3). Saved: `data\validation_matching.json` (local).
3. **2026-10-13, one representation variant measured once** (`tools.accuracy_round --validation`, 11
   categories): in use 19 first, the variant 20; both 14 filed, 0 wrong. The rule set beforehand was met by one
   document; the variant was withdrawn on 2026-10-14 after new development files (`docs/archive/ACCURACY_ROUND.md`,
   sections 4 and 9). Saved: `data\validation_accuracy_round.json` (local).
4. **2026-10-15:** `tools.evaluate --set-families` read the family ids of the split CSV and recorded only those
   of files in the catalog; no validation file is in the catalog, so none was recorded and no validation file
   was read.

Validation has informed one operating choice (Strict) and one rejected variant. It has not been used to tune a
threshold since. `data\final-eval` has never been read.

## Open

- **OCR quality.** Investigated on the same 40 items (57 pictures). The counts below are a proxy (distinct
  plausible words kept after the junk filter), on development data; they are not accuracy estimates.
  - The judging window misled in two ways, both corrected: PDFs showed the whole page instead of the regions
    OCR read (before the second round), and slides showed repeated logos that OCR never reads (after it).
  - The junk filter dropped some real lines, although none were marked in the judging: lines with a stray bar
    or dots, and slash-joined words. Fixed: 550 words kept (547 before).
  - Tried and not adopted: regrouping OCR words into rows. It kept no more words and, on a synthetic picture,
    attached junk to a real line so the line was dropped.
  - Resolution is not the cause: rendering at half or a third of the size reads about the same number of words.
  - What OCR really misses is text inside bordered boxes and table cells, light text on dark boxes, and text on
    gradient backgrounds. Formulas and label-free drawings stay poor whatever the setting.
  - PyMuPDF's OCR call has no layout setting. The installed Tesseract program has: in sparse-text mode it reads
    the boxed and table text the current pass misses, but reads some other pictures worse. No single setting
    wins (current 547 words, sparse 537, sparse with adaptive thresholding 589).
  - Extra passes through the Tesseract program (sparse-text layout, best result per picture) were built and
    judged blind by the user on the 40 items: 4 better with them, 3 better without, 33 no difference. Not
    adopted and removed; they also cost about one more second per picture.
  - Speed, same words kept: the OCR result is no longer compressed before it is read back, the photo check
    samples fewer pixels, and a picture shown again in a document is read once. Reading the 18 sampled files:
    about 98 s before, 80 s now. The app reads four documents at once (was two).
  - Not taken: OCR at 200 dpi instead of 300 would bring those files to about 59 s and keep about 1% fewer
    words. The user keeps 300 dpi (2026-10-12): recognition quality is the bigger problem.
- **Category names.** The user's ruling (2026-10-12): ClassiFile never decides, creates or changes a document's
  own title or name; it only suggests category names and files documents.
  - rules-6, from the first review: lines whose only evidence is repeating on some pages go under "More" (score
    unchanged, so no self-description is declared dominant); DOCX/ODT take only their first qualifying opening
    line; generic words, bare codes, IP addresses, quoted data and academic ranks alone are rejected.
  - Second review (rules-6 names, asked as category names): all 34 files reviewed, no suggested name marked
    good, three category names typed. The first review had marked 21 of largely the same names good, so the
    marks cannot say which level a category should have.
  - rules-7, from the typed names: a numbered list on the cover is the document's contents, not its name; a
    title that exists only inside a picture on the cover is suggested (cleaned OCR text, less weight). Of the
    four files with a typed category, two now show it or its near form in the top three (none before).
  - Against the first review, as a regression check only: 32 top-three names marked not good (76 under rules-5),
    20 of 34 files with a name once marked good (21), 17 names never judged. Development data; not accuracy.
  - The owner's grouping (G3) now exists and was measured (E1, record 2.1): names found in documents cannot
    reproduce it, which is why matching by content (CP3) comes first.
- **In the record, not built or not run (2026-10-15):**
  - D/CP4 "The documented policy (E1) drives the proposer": no written policy; suggested names still come from
    the rules (rules-8), and E1 showed names cannot reproduce the owner's folders.
  - E5 (semantic name equivalence), E6 (titles and instance identifiers), E7 (dominant self-description) were not
    run; their defaults are in use (names are compared after normalization only; identifier guards; pending on
    conflict). E3 and E9 were not needed so far.
  - Part E's quality-gate report: built (`tools.quality_gate`, 2026-10-15). For the final evaluation it still has
    to count the held-out set the same way (docs/LAUNCH.md, section 1).
  - Functional gate: `tools.offline_check` passes with Python's network access refused; the run with the laptop's
    networking switched off is the owner's.
- **"Also belongs to" cannot be undone in the app yet** (there is no "remove from this category").

## Next

1. The owner reviews the Burmese guide, answers the last "Check these" document, and runs `tools.offline_check`
   once with networking switched off.
2. CP5: one final "Update matching", the freeze, and the final evaluation once (`data\final-eval` stays untouched
   until then). Then the installer (docs/LAUNCH.md, section 2). SummarEase is a separate project.

## Changes to the decision record, approved by the owner (record 2.8, 2026-10-15)

The owner approved this wording as proposed; it is in the record as version 2.8.


1. **A7, the check:** "A new version replaces the one in use only if, on the full evaluation (each family held out
   in turn, both versions answering the same questions), it files no more documents wrongly at the level in use
   and puts the user's category first no less often. Both results are logged in Settings." (Today A7 says only
   "the previous version stays in use if the new one does worse".)
2. **B4, one evaluation:** "Every number about matching comes from one evaluation (`tools.evaluate`): family-held
   out, preprocessing fitted inside each fold, deterministic, with simple ranges. The owner's family ids are kept
   in the catalog so the app's check and the report hold out the same families."
3. **B2 or B5, Check these:** "Filed documents whose content, held out, matches another category ahead of their own
   by at least the Strict lead are listed with Keep here and Move to…. Keep here is recorded and not asked again
   while the document stays there. Nothing is moved by itself."
4. **D/CP4:** mark "The documented policy (E1) drives the proposer" as not built (or drop it), and E5–E7 as
   running on their defaults for v1.

