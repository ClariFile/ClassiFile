# ClassiFile status

2026-10-12 · decision record version 2.0

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
  the category picker, saved into the CSV after every answer).
- `docs/UI_PROPOSAL.md`: measurements and a phased proposal for the next interface pass (nothing built yet).
- `tools.apply_split`: moves a split's files into `data\development`, `data\validation` and `data\final-eval`,
  all or nothing, never over an existing file.
- 235 automated tests.

## Development results so far

These counts describe development data only. They are not accuracy estimates.

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
- **The regrouped library against grouping policies (E1, 2026-10-12):** 32 of the 34 development files are filed
  (2 still wait) in 8 categories of 8, 7, 6, 6, 2, 1, 1 and 1 documents: 80 pairs of documents the owner keeps
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
- **CP3** has not started.

## Next

1. Discuss the E1 result with the owner before any rule change.
2. Interface: Phase 1 of `docs/UI_PROPOSAL.md` (responsiveness and search), on the owner's go-ahead. The five
   decisions are made and recorded there.
3. CP3 (after the user's go-ahead): scorer comparison (E2) and abstention baseline (E4) on development data,
   selected-category mode with permissions through the queue, "Belongs to" / "Also belongs to", primary
   replacement and edited-copy protection.
4. Later: CP4 automatic mode and discovery, CP5 quality gate and freeze. SummarEase is a separate project.
