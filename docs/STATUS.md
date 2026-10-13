# ClassiFile status

2026-10-13 · decision record version 2.4

## Done

**CP0 Foundation**
- Environment baseline (docs/ENVIRONMENT.md), project skeleton with the isolated reader, GUI smoke test.
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
- `docs/UI_PROPOSAL.md`: measurements and a phased proposal for the interface; phase 1 is built (below).
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
  `docs/CP4_PROPOSAL.md`).

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
  The strictness trade-off for automatic filing is in `docs/CP4_PROPOSAL.md`. The saved result is
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
  - What would settle the level: the user's own grouping of the development files (decision record G3), which
    does not exist yet. Filing them in the app with the categories the user wants would provide it.
- **From the record's CP4 list, not built:** automatic creation of a category from a single document (the owner
  ruled that the app never creates a folder by itself) and the discovery replay (E10). The record still lists
  both; a change of the record is the owner's.
- **"Also belongs to" cannot be undone in the app yet** (there is no "remove from this category").

## Next

1. The owner tries CP4 and the new interface in the app.
2. Interface phases 4 (motion, Reduce motion) and 5 (retry for unreadable documents, "Find category…", the
   written states) of `docs/UI_PROPOSAL.md`, on the owner's go-ahead.
3. CP5 quality gate and freeze (`data\final-eval` stays untouched until then). SummarEase is a separate
   project.
