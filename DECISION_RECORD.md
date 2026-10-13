# Decision Record — ClassiFile (Offline Document Organizer)

Version 2.3 · 2026-10-13

**Names**
- **ClariFile:** the suite.
- **ClassiFile:** this project, the categorizer (the "organizer" in this record). Python package `classifile`.
- **SummarEase:** the secondary summarizer (A11), a fully separate project.

**Status:** authoritative. This record was produced after the design debate between the project owner (the user), ChatGPT and Claude. Only the user can change it. Every change goes in the changelog at the end.

**Roles**
- Claude Code implements the project, one checkpoint at a time.
- ChatGPT reviews ideas, bugs, evaluation results and proposed changes.
- Both follow this record. Where it conflicts with older handoff files or `legacy_prototype/`, this record wins.

**Labels**
- **[Requirement]**: confirmed by the user; settled.
- **[Decision]**: agreed design decision.
- **[Default]**: conservative initial default; changes only with evidence and the user's approval.

---

## Glossary

- **Source (original):** a file the user imports. Never modified.
- **App copy:** a byte-identical copy the app places in an output category folder. App-owned.
- **Document:** catalog entity with a stable document ID. Each imported byte snapshot has a SHA-256 hash. The hash identifies bytes, not the document.
- **Category:** catalog entity with a stable category ID. It has a display name, an optional concise scope description, explicitly confirmed aliases, and a level (series, purpose, subject, or user-defined).
- **Membership:** a link between a document and a category. A document has at most one primary membership and any number of secondary ones.
- **Extraction observations:** measured facts per page, slide or block (e.g., native characters, image area). Never described as "completeness".
- **Suspected unread content:** a heuristic flag, recorded together with the rule that raised it.
- **Decision states:** committed, provisional, pending, failed.
- **"Needs your decision" queue:** a persistent list of open questions for the user.
- **Label provenance:** machine-assigned, user-confirmed, or user-corrected.
- **Label status:** active, superseded, or excluded.
- **Document family:** files that are versions or format twins of the same material (e.g., the PDF and PPTX of one lecture).
- **Data splits:** development, validation, final evaluation. Always split by family.
- **Vocabulary coverage:** the share of a document's terms the current vectorizer represents. **OOV rate:** the share it does not.

---

## A. Confirmed requirements

**A0 [Requirement] Goal**
- ClassiFile is an automatic categorizer. Choosing by hand is the fallback, not the main workflow.
- The app decides from the document's content.
- It files automatically when the match is clear, and asks the user only when it is unsure.
- It suggests new names only when no existing category fits.
- How clear is clear enough is the operating point the user chooses (Part E).

**A1 [Requirement] Platform**
- Offline processing.
- No required paid API. Installation and model downloads may use the internet.
- Python 3.11+.
- English documents first. Other languages are flagged where feasible; Burmese comes later.
- Target laptop: MSI GS65 9SE, 16 GB RAM. Other specs are verified in CP0.

**A2 [Requirement] Inputs**
- PDF, PPTX, DOCX and ODT.
- Drag-and-drop and manual file selection. Not CLI-only.

**A3 [Requirement] General organizer**
- The user's course materials are development data only.
- No course-primary default.
- Automatic mode follows one documented general organizing policy and never asks per-file preference questions.

**A4 [Requirement] Automatic mode**
- Each document is analysed independently from its own content and purpose, then compared with existing categories.
- A genuinely equivalent existing category is reused when the match is supported. A new category is created when supported.
- One document can justify creating a category if it clearly supports its own category and passes duplicate and conflict checks.
- An unmatched string alone is insufficient. It must describe this document, not a prerequisite, a reference or an incidental topic.
- Ambiguous cases stay pending.
- No folder per file.
- Existing folders never force a document into an unsuitable placement.
- Useful trained knowledge is used.

**A5 [Requirement] Selected-category mode**
- Destinations are limited to the selected categories.
- Creating a category requires permission.
- Other categories are checked for duplicate prevention only. They never become destinations without authorization.

**A6 [Requirement] Memberships**
- "Belongs to this category" replaces the primary assignment.
- "Also belongs to" adds a secondary membership.
- A confirmation applies to that document only. It never silently becomes an alias, a rule or a universal policy.

**A7 [Requirement] Learning**
- Explicit confirmations and corrections are eligible supervised training examples by default.
- Model updates are deliberate, versioned and validated.

**A8 [Requirement] Originals**
- Source files are never moved, renamed, deleted, overwritten or edited, and their metadata is never deliberately changed. They are read only.
- Separate, content-identical copies are placed in output categories.
- No source-deletion or Recycle Bin workflow.
- Internal analysis and catalog data stay separate from document contents.
- Summaries, tags or OCR text are never inserted into any document, original or copy.

**A9 [Requirement] Internal summarization**
- Required.
- Hidden: users neither view nor approve it.

**A10 [Requirement] Interface**
- Categories, categorized documents, minimal status, and decision prompts when necessary.
- ClassiFile's scope is suggesting category names and filing documents. It offers no text viewing, copying or exporting; those belong to SummarEase (A11).

**A11 [Requirement] Secondary summarizer: SummarEase (later project)**
- A separate project, usable standalone or called by ClassiFile on demand.
- User-facing; accepts documents or pasted text.
- At least three summary levels.
- Summaries come from the document's content, never from its file name.
- Built after the categorizer.
- A fully separate project, with its own folder, environment and repository.
- ClassiFile detects an installed SummarEase through a registration file in `%LOCALAPPDATA%\ClariFile`, and asks before using it. Each works alone.
- Detection details (the registration file's contents and format) are designed when SummarEase is built.
- Planned for SummarEase (not built now), alongside the summary levels:
  - a readable text view with automatic formatting (layout only, never the words);
  - Copy;
  - Export as a searchable PDF or a Word document.
  - Exports are new files, created only on request and saved where the user chooses. Originals and filed copies are never changed.
- When SummarEase's own repository starts, its entries move to its own decision record.

---

## B. Agreed design decisions

### B1 Decision flow

- **[Decision] Outcomes.** Each document ends as assign, pending (with a reason) or failed (operational). Creating a category is a separate step from assignment.
- **[Decision] Proposer and matcher.**
  - The proposer analyses one document without reference to existing categories (self-description, purpose, subject). It outputs a candidate category with its evidence.
  - The matcher measures fit to existing categories, always against all categories.
  - A selection only filters actions. It never renormalizes scores, so selecting fewer categories cannot manufacture confidence.
- **[Decision] Evidence is weighted, not absolute.**
  - Identity positions (cover, running headers and footers, metadata) and body text can all count, and any of them can mislead.
  - A file name never suggests a category. Suggestions come from the document's content (cover, headings, text, OCR). A file name may count only as weak support for a name the content already gives.
  - Text in prerequisite, reference or "see also" contexts never counts as self-description (A4).
  - Instance identifiers (invoice numbers, dates, lecture or section numbers) are guarded against becoming category names. Complete titles are not banned.
  - A single-member category is not automatically a mistake.
- **[Decision] Names and content.** Names make claims; content tests plausibility. Document fit is not the same as category equivalence. Category relations are kept distinct: equivalent, broader/narrower, related, conflicting.
- **[Decision] Name matching.**
  - Normalized equality is a candidate match, never proof.
  - Normalization covers case and whitespace, plus an explicit equivalence list (e.g., "&" and "and").
  - Punctuation is significant, so C, C++ and C# stay distinct.
  - Abbreviations are expanded only through explicit, context-aware entries.
- **[Default] Different names.** Substantively different names are not reused automatically; the question goes to the queue. Experiment E5 may change this.
- **[Default] Conflicting self-descriptions.**
  - Candidates of comparable strength leave the document pending.
  - Frequency or template repetition alone does not establish dominance.
  - The interpretation of the development sample whose cover title and repeated course line name different identities stays provisional (E7).
- **[Decision] Aliases.** Unconfirmed alternate names are recorded, but never act as aliases or routing authority. Aliases are created only by an explicit, category-level confirmation.
- **[Decision] Category definitions.**
  - A category is defined by its name, a concise scope description when supported, and its confirmed members.
  - A founding document is provisional evidence.
  - Definitions never widen silently as documents arrive. Automatically assigned documents never change a definition; only deliberate, validated updates do.
- **[Decision] Re-evaluation.**
  - Pending documents are re-evaluated when categories change.
  - Re-evaluation is separate from re-notification.
  - Model updates never reopen an explicit user assignment.
- **[Decision] Existing categories at other levels.** The documented policy states how it treats categories at other levels (e.g., created manually or in selected mode), without silently redefining or reorganizing them.

### B2 Queue and effort

- **[Decision]** One persistent "Needs your decision" queue, with no repeated pop-ups. Selected-mode creation approvals go through it.
- **[Decision]** Items are grouped only when the underlying ambiguity is equivalent. A batch answer applies only to the listed documents and never silently authorizes an alias or future rule.
- **[Decision]** New evidence triggers silent recomputation. The user is notified only when a new decision is needed. Unresolved items are not re-asked without meaningful new evidence.
- **[Decision] No one-click category creation once categories exist.**
  - No categories yet: the main action may create the suggested category and file ("Create & file").
  - The top suggestion matches an existing category: the main action files in it ("File in <name>").
  - Otherwise: the main action opens the category picker ("Choose category…"), with existing categories first and the suggested names offered as new categories. Creating a category always takes an explicit choice.
- **[Decision] Cards offer existing categories first** (2.3).
  - When existing categories are a good match for a document's content, its card shows the three best, ranked, each a one-click choice with a plain reason. Filing in an existing category takes one click.
  - Suggested new names are shown only when no existing category is a good match (the abstention baseline, E4).
  - Scores are never shown.
- **[Decision] Automatic filing** (2.3; the operating point the user chose from development and validation results, Part E).
  - Level: Strict. A document is filed without a question when its best category leads the second-best by at least 0.10 (E4). The level is a setting; every change of it is recorded.
  - No automatic filing into a category until it holds at least 3 documents the user confirmed. Until then its documents wait, with the three best categories.
  - Automatically filed documents are machine-assigned and never train the matcher. Only the user's confirmations and moves do (A7).
  - A "Filed automatically" view lists what the app filed by itself, each with its reason and a one-click Move to….
- **[Decision] Grouping new subjects** (2.3; a narrow exception to the clustering deferral in F).
  - Only waiting documents that match no existing category are grouped. Nothing is ever merged into an existing category, and no folder is created by the app itself.
  - A group has at least 2 documents. It is shown as one question: its documents, the shared key words as the reason, and the suggested names. The user names the folder once and can untick documents before confirming.
  - It is tested on development data first (each of the user's categories held out in turn), and the user sees that report before it goes into the app.
- **[Decision]** Effort is reported as four numbers:
  - pending documents;
  - distinct questions;
  - documents resolved per decision;
  - later corrections. These reveal discovered errors only, not every error.

### B3 Extraction

- **[Decision] Isolated reader module.**
  - Imports nothing from organizer or summarizer code.
  - Extracts native text from PDF, PPTX, DOCX and ODT, and uses OCR for image content.
  - Records extraction observations and source locations (page, slide, document block; pasted-text spans later).
- **[Decision] Reading order** must not merge side-by-side columns. Observed: PyMuPDF `sort=True` merged two PHP code panels line by line.
- **[Decision] Terminology.** The app records observations and suspected-unread flags, never "complete". Decisions made while suspected gaps remain, without independent evidence, are provisional.
- **[Default] Selective OCR** (adopted from E8, version 1.5).
  - OCR every non-repeated picture covering at least 5% of its page or slide, regardless of how much native text the unit has.
  - Replaces the first rule (under 300 native characters and at least 30% non-repeated picture area), which missed most text-bearing pictures, including the observed miss type (text-bearing images on text-heavy pages).
  - OCR text is kept apart from native text. Lines that look like junk (photos, decorations) are dropped, and the number of dropped characters is recorded.
- **[Decision] Long documents** are never rejected for length. Documents that may mix topics are judged per section. OCR is the main cost, so the work queue is ordered by expected work.
- **[Decision]** "Reuse compatible extraction when sufficient." Deeper reading from the preserved app copy is allowed later.
- **[Decision] Layout in the extraction record.**
  - For native and OCR text, the reader keeps line breaks, paragraph and block boundaries, positions and text sizes, so SummarEase can build readable formatting later.
  - DOCX and ODT store no positions; for them the reader keeps boundaries and sizes only.
  - The text the categorizer uses is unchanged, and ClassiFile's interface shows none of this layout.

### B4 Models and evaluation

- **[Decision] Scorer comparison.**
  - Start with one word-level TF-IDF representation, fitted inside each training split.
  - Compare nearest centroid, logistic regression and kNN across empty, growing and established catalogs.
  - Select one primary scorer. No ensembles.
- **[Default]** Vocabulary refresh, hashing or embeddings are added only when initial results expose a relevant weakness (E3).
- **[Default]** A global abstention baseline comes first. Category-specific spread is used only with evidence (E4).
- **[Decision]** Vocabulary coverage and OOV rate are diagnostics, not proof of unfamiliarity; OCR errors, identifiers and formulas affect them. Any gate built on them is evaluated before use.
- **[Decision]** Every validated model version bundles its preprocessing, vectorizer, category mapping and decision settings.
- **[Decision]** Classification uses the full extracted content; the internal summary feeds naming and checks. Content-based and digest-based decisions are compared under identical conditions (E9).
- **[Decision]** Candidate-name extraction starts with rules. A trained own-name classifier is deferred and is adopted only if it beats the rules.
  - Name review (development data, 1.8): the user judged the top three suggested names of 34 development files. 21 files had at least one good name in the top three, and the user typed 3 better names; 76 names were marked not good.
  - The acceptable names (good marks plus typed better names) are kept in `data\acceptable_names.csv`, outside the repository, because they contain file names. This record keeps only the counts.
  - These counts describe development data under rules-5. They are not accuracy estimates.
- **[Decision]** Similarity scores and confidences are never presented as probabilities. No accuracy is claimed from the six development PDFs.
- **[Decision] Data splits by document family.** Format twins and revisions always stay together.
  - Development: used to choose policy, features, models and thresholds.
  - Validation: used for operating choices.
  - Final evaluation: untouched, used once per frozen version.
  - Repeatedly inspecting a held-out set turns it into development data.
- **[Decision] Feedback labels.**
  - Labels keep provenance, status and history. The latest resolved explicit label is used.
  - Unresolved conflicts (e.g., family members with conflicting explicit labels, or open queue items) are excluded until resolved.
  - Lack of correction is never confirmation.
  - Feedback on final-evaluation families never trains a model.
- **[Decision]** The learning method is supervised learning from feedback, not active learning or RLHF.

### B5 Storage and copies

- **[Decision] Identity.** A stable catalog document ID, plus a SHA-256 hash per imported snapshot. Changed source bytes become a separate snapshot; version linking is deferred.
- **[Default] Catalog.** SQLite in the app's data folder. No sidecar files in output folders.
- **[Decision] Copy procedure.**
  1. Write to a temporary name inside the destination folder.
  2. Verify the hash.
  3. Publish without any overwrite path.
  4. Record per-copy status.
  - Startup recovery resolves interrupted operations.
  - Name collisions get a suffix.
  - Unrelated files are never overwritten, and recovery never deletes files the app did not create.
- **[Decision] Handling sources.**
  - Opened read-only.
  - No save or timestamp calls on them, including "restoring" access times. OS-level last-access updates are reported, not fought.
  - No side files next to sources; converters run on temporary copies.
  - No alternate data streams or extended attributes.
- **[Decision] Primary replacement.**
  - Create the new copy from a verified app copy, or from the original if its hash still matches. Verify and record it.
  - Only then remove the old primary copy, and only if it is unchanged. A direct move is an optimization, not the safety definition.
  - An existing destination copy is verified before reuse.
  - Edited app copies are never overwritten or removed automatically; they are flagged.
  - Removing a document's final membership leaves a retained, unfiled app copy. It is never a deletion.
  - "Remove membership" is recorded separately from an explicit "incorrect category" judgment.
- **[Decision]** Each membership has its own copy.
- **[Decision] Move to…** (one or several filed documents).
  - Replaces the primary category by the primary-replacement rules above: the new copy is made from a verified copy, the old copy is removed only if it is unchanged, edited copies stay in place and are flagged, nothing is ever overwritten.
  - An interrupted move is finished at the next start.
  - Each move is recorded as user-corrected. The latest explicit choice wins.
- **[Decision] Rename category.**
  - Only ClassiFile's copies move into the renamed folder, by the verified-copy rules.
  - If other files remain in the old folder, it is left in place and the user is told.
  - If the new name already exists, the rename is refused and moving the documents is suggested instead.
- **[Decision] Delete category.**
  - Only a category that holds no documents. Its folder is deleted only if it is empty.
  - When a move leaves categories empty, the user is asked once whether to delete them.
- **[Decision]** No merge command and no aliases for now.
- **[Decision] Remove from ClassiFile** (documents waiting for a decision only).
  - The original file is never touched, and no app copy exists yet for a waiting document.
  - Removing deletes the text, analysis and internal summary ClassiFile stored for that document.
  - Importing the same file again brings it back as a new document.
- **[Default] Folder names.** Category folder names are sanitized for Windows (forbidden characters, reserved names, trailing dots and spaces). A "/" never creates nesting; "+" and "#" are kept.

### B6 Summarization

- **[Decision] Internal summary (hidden).**
  - A structured extractive record: title, self-description candidates, purpose, outline, keyphrases, rule-based entities, a short extractive digest, and OCR and gap flags.
  - Computed once per snapshot, and per section for long documents.
  - No summary method or citation guarantees faithfulness.
- **[Decision] Secondary summarizer (SummarEase): deferred.**
  - Only a boundary note for now: standalone or called on demand; reads extraction records; never writes the organizer's catalog.
  - At least three levels. Exact count, lengths, packaging and invocation are deferred.
  - Source references do not prove that higher levels preserve meaning. Represented meaning and qualifications must be evaluated.
  - Collecting documents, caching extraction, precomputing summaries and training a summarizer are separate decisions.

### B7 Application

- **[Decision]** A lightweight offline desktop app.
- **[Default] GUI: PySide6.** Drag-and-drop yields real file paths, and it supports background workers. CP0 confirms it installs and runs on the laptop. The fallback is Tkinter with tkinterdnd2, only with the user's approval.
- **[Decision]** Heavy work runs off the UI thread. Parser crashes and timeouts are operational failures, never semantic evidence.
- **[Default]** A separate worker process with per-file timeouts arrives with OCR (CP2).
- **[Decision]** No document text in logs. No network calls during normal processing.
- **[Decision] Licensing note.** PyMuPDF is AGPL. That is fine for personal use; review it before any distribution.

---

## C. Remaining experiments

Each experiment lists its alternatives, data, measurements, what decides it, and the default if results are inconclusive.

**E1 Organizing policy (granularity)**
- Alternatives: series → filed-by-type purpose → subject (the candidate), plus policies derived from the user's grouping.
- Data: the user's grouping of 20–30 mixed documents (primary placement only), then a second batch.
- Measure: over-merging and fragmentation separately, plus co-membership precision and recall.
- Decides: the candidate that best balances both, on both batches, becomes the documented policy.
- Default: create categories only from strong self-descriptions; everything else stays pending.
- Result (development data, 2.1): the user regrouped the development files into subject folders. 32 of the 34 files are filed, in 8 categories: 80 pairs of documents the user keeps together. For 28 of the 32 files the category name was typed by the user, not taken from a suggestion.
  - Every name-based stand-in policy (top suggestion; cover or opening line; repeated line; repeated, else cover, else top; file name) put no two documents together: no over-merging, and all 80 pairs fragmented (placed apart or left pending).
  - Upper bound: putting together every pair of documents that shares any suggested name keeps 8 of the 80 pairs and over-merges 4.
  - No name-based policy reproduces the user's grouping, because the folders are subject names that usually are not written in the documents.
  - So CP3 (matching documents to the user's existing categories by their content) comes first, and CP4 needs a plan for naming new subjects. No rule was changed.
  - These counts describe development data and the stored suggestions (rules-7), compared with stand-in policies; the documented policy is not built. They are not accuracy estimates.

**E2 Primary scorer**
- Alternatives: nearest centroid, logistic regression, kNN (word TF-IDF).
- Data: the development split by family, with simulated catalog growth (empty, growing, established), new subjects and varied styles.
- Measure: correct and incorrect assignments, abstentions, false-familiar outcomes, and behaviour with one to three examples per category.
- Decides: the scorer with the best balance. The user picks the operating point (Part E).
- Default: nearest centroid with a higher abstention level.
- Result (development data, 2.3): the 83 filed documents (78 families, 10 categories), each family held out in turn, the vocabulary and every scorer fitted on the rest.
  - The user's category first / in the first three, of the 81 documents whose category has other families: nearest centroid 65 / 77; kNN 69 / 79 (k = 1), 67 / 79 (k = 3), 66 / 79 (k = 5); logistic regression 36 / 64 (C = 1), 56 / 73 (C = 10), 58 / 75 (C = 100).
  - With one to three examples of the category (7 documents): nearest centroid 3 first, kNN (k = 1) 4, logistic regression none.
  - A growing catalog (a quarter, then half, of the other families training): nearest centroid 49 of 71 and 58 of 77 first; kNN (k = 1) 51 and 65; logistic regression (C = 100) 43 and 51.
  - Selected: nearest centroid. kNN puts the right category first for a few more documents, but nearest centroid abstains much better (E4), and it is the default when the comparison is close.
  - Validation, measured once on the 23 validation documents with the model trained on the 83: the user's category first for 21, in the first three for all 23.
  - These counts describe development and validation data. They are not accuracy estimates.

**E3 Representation weaknesses** (run only if E2 exposes them)
- Alternatives: frozen vocabulary, refresh per validated version, hashing, small embeddings.
- Measure: new-subject matching and false-familiar outcomes.
- Default: refresh the vocabulary at each validated version.

**E4 Abstention**
- Alternatives: a global baseline, category-specific spread, document-type-aware comparison.
- Measure: abstention by document type (e.g., labs vs lectures), incorrect assignments, false-familiar outcomes.
- Default: global baseline.
- Result (development data, 2.3): the global baseline is adopted, as one level on how far the best category leads the second-best. Set on the best score alone it was clearly worse.
  - Documents filed right while at most 0 / 1 / 3 are filed wrong, of 83: nearest centroid 32 / 54 / 60 on the lead (18 / 25 / 29 on the best score); kNN (k = 1) 34 / 35 / 48; logistic regression (C = 100) 32 / 39 / 43.
  - New subjects: with each whole category held out, all 83 documents are of a subject never seen. At those levels nearest centroid files 0 / 5 / 16 of them (false familiar).
  - Cards use a lead of 0.02 as "a good match": of the 81 documents whose category exists, 66 show three categories (64 with the user's among them); of the 83 held out as new subjects, 39 show a suggested new name.
  - Automatic filing levels, fixed before validation was read. Strict (lead of 0.10): on development 43 filed right, 1 wrong, 39 waiting, and 3 of the 83 new-subject documents filed; on validation 14 filed, none wrong, 9 waiting. The user chose Strict (B2).
  - These counts describe development and validation data. No validation document is of a new subject. They are not accuracy estimates.

**E5 Semantic name equivalence**
- Data: true synonyms, related-but-distinct categories, broader/narrower pairs, identical names with different meanings, and the networking-course trap (Network Analysis vs Networking Fundamentals).
- Measure: incorrect reuse versus review burden.
- Decides: automatic semantic reuse only if development and validation results support a trade-off the user accepts. The rule is frozen before final evaluation.
- Default: queue.

**E6 Titles and instance identifiers**
- Data: a genuinely new one-document category, a generic title, and invoice and lecture identifiers.
- Measure: whether created categories are appropriate and reusable (human judgement), and how often valid categories are wrongly rejected.
- Decides: keep guards that prevent demonstrated mistakes; refine guards that block valid categories.
- Default: weighting plus targeted identifier guards.

**E7 Dominant self-description vs conflict**
- Data: correct repeated headers, stale repeated templates, accurate covers, misleading filenames, and genuinely conflicting identities.
- Measure: incorrect automatic outcomes and review burden.
- Default: pending when the evidence cannot resolve the conflict.

**E8 Selective OCR**
- Data: page labels on the sample PDFs, plus fixtures of known miss types.
- Measure: meaningful content missed, and OCR time on the laptop.
- Default: the simple rule, with misses disclosed as suspected unread content.
- Result (development data, 1.5): the user labelled 240 units of 34 development files (6 samples, 28 real files; 206 more were labelled "no" automatically because they show no non-repeated picture). 160 had content the native text misses.
  - First rule: caught 42 of 160; 20 flagged units had no such content; 62 units OCR'd.
  - Region rule (picture of at least 5% with little native text inside its box): caught 125 of 160; it did worse than the plain area rule because native text often sits on top of text-bearing pictures.
  - Adopted rule (any non-repeated picture of at least 5%): caught 139 of 160; 55 flagged units had no such content; 212 units OCR'd, about 98 s of reading in total for the 34 files on the laptop.
  - These counts describe development data and a threshold chosen on it; validation confirms or revises them. They are not accuracy estimates.

**E9 Content vs digest classification**
- Measure: a comparison under identical conditions.
- Default: full content.

**E10 Discovery replay (diagnostic)**
- Process the development documents in automatic mode, starting from an empty taxonomy, in several orders.
- Report:
  - categories created;
  - single-member categories (judged case by case, not assumed wrong);
  - duplicates;
  - wrong creations;
  - unsuitable reuse;
  - pending rate;
  - correctness of automatic assignments.
- One held-out-course pass gives a false-familiar diagnostic only.

---

## D. Staged Milestone 1

Partial checkpoints are not the completed v1. Evaluation runs alongside development.

**CP0 Foundation**
- Environment baseline: OS, CPU, RAM, free disk, Python. GPU and driver are recorded if easy; they never block.
- Project skeleton with the isolated reader module.
- GUI smoke test: dropped files arrive as real paths, and a background task runs while the window stays responsive.
- Small utilities are allowed:
  - an inventory tool: hashes, formats, page counts, duplicate hints, plus columns for the user's labels and families;
  - a family-based split tool.

**CP1 First end-to-end slice** (PDF only, user-approved placement)
1. Import by drag-and-drop or file chooser.
2. Extract native PDF text, observations and source locations into an extraction record that carries a version number (bumped whenever the record's format changes).
3. Analyze: rule-based candidate names with their evidence.
4. Show the category decision. The user approves a suggestion, picks an existing category, or creates one.
5. Make a verified copy.
6. Persist to the catalog. Reopening the app shows the same state.

**CP2 Formats and OCR**
- Native extraction for PPTX, DOCX and ODT.
- Selective OCR with observations.
- Worker process with timeouts.
- Hidden internal summary record.
- Extraction checks against the sample page labels (E8).

**CP3 Matching**
- Scorer comparison (E2) and abstention baseline (E4) on development data, producing the initial matcher.
- Cards offer the best-matching existing categories; model updates on request, versioned and checked (B2, B4).
- "Belongs to", primary replacement rules, and edited-copy protection.
  - Brought forward in 2.0: "Belongs to" (as Move to…), with primary replacement and edited-copy protection (B5).
- Moved to CP4 in 2.3: selected-category mode and "Also belongs to".

**CP4 Automatic mode and discovery**
- Automatic filing at the level the user chose, with the "Filed automatically" view (B2).
- Grouping new subjects, after the user has seen the development report (B2).
- Selected-category mode, with permissions through the queue (from CP3).
- "Also belongs to" (from CP3).
- The documented policy (E1) drives the proposer.
- Single-document creation, with duplicate and equivalence checks using the defaults above (E5–E7).
- Re-evaluation of pending documents.
- Discovery replay (E10).

**CP5 Quality gate and freeze**
- From validation results, the user chooses the operating point.
- Choices are frozen.
- The final evaluation runs once, producing the v1 candidate.

---

## E. Gates and acceptance

**Functional gate** (cumulative; applies to the features shipped at each checkpoint)
- Source files preserved: hash, size, modification time, attributes and alternate streams unchanged; no new files beside sources; last-access time reported only.
- Copies verified by hash; unrelated files never overwritten.
- Interrupted operations recover. Crash-injection tests cover the operations shipped so far; merge tests come only once merging ships.
- Selected-mode permissions enforced (from CP3).
- Edited app copies protected (from CP3; for Move to… and Rename category since 2.0).
- Evaluation-family separation maintained.
- An offline run works with networking disabled after installation.
- Decisions and results are reproducible for the same inputs and versions.

**Quality gate** (before unattended automatic sorting)
- Report:
  - incorrect assignments;
  - incorrect creations;
  - duplicate categories;
  - over-merging and fragmentation;
  - pending rate;
  - user decision effort (questions, and documents resolved per decision);
  - later corrections.
- The user chooses an acceptable operating point from development and validation results. Choices are frozen before final evaluation.
- If the evidence is insufficient, automatic behaviour stays limited (more pending) and the limitation is stated.
- Passing the functional gate alone never justifies unattended sorting.
- Zero duplicates in a finite trap suite is a regression result, not a guarantee.
- A held-out-course pass is a diagnostic, not proof of general unknown-category detection.
- No numeric targets until results exist.

---

## F. Deferred

- Secondary summarizer implementation, beyond the boundary note.
- LLMs.
- Clustering, except the grouping of unmatched waiting documents (B2, since 2.3).
- Trained own-name classifier.
- Separate packages.
- Additional representations, unless E2 or E3 justify them.
- Automatic version linking.
- Elaborate category management: merging and aliases. The minimum the workflow needs (rename, delete an empty category) is in B5 since 2.0.
- Installer packaging.
- Burmese and other languages.
- Both GitHub repositories already exist in the ClariFile organization: ClassiFile (this project, `https://github.com/ClariFile/ClassiFile.git`) and SummarEase (empty until its development starts). The reader stays isolated so SummarEase can reuse it.

---

## G. What the user provides

1. Laptop OS and basic resources. Claude Code collects these in CP0; the user confirms.
2. Representative files in each supported format, the known document families (twins and revisions), and primary labels for the inventory.
3. Desired groupings for 20–30 mixed development examples (primary placement only), then a second small batch.
4. Output-location preference.
5. Later: the operating trade-off decision, once validation results exist.

---

## Changelog

- **1.0 (2026-10-07):** consolidated record after the final debate round. All of ChatGPT's final amendments were adopted; none changed a confirmed requirement.
- **1.1 (2026-10-08):** section F: added the two-repository note (organizer and secondary summarizer repositories are created near the finished product; until then one private repository, with the reader kept isolated for reuse by the summarizer). Authorized by the user.
- **1.2 (2026-10-08):** A11: the secondary summarizer is a fully separate project (own folder, environment and repository); the organizer detects an installed summarizer and asks before using it; each works alone; detection details are designed when the summarizer is built. Authorized by the user.
- **1.3 (2026-10-08):** names: ClariFile (suite), ClassiFile (this categorizer; package `classifile`), SummarEase (secondary summarizer). A11: SummarEase is a fully separate project (own folder, environment and repository); ClassiFile detects it through a registration file in `%LOCALAPPDATA%\ClariFile` and asks before using it; each works alone; detection details are designed when SummarEase is built. D/CP1: the extraction record carries a version number. Authorized by the user.
- **1.4 (2026-10-08):** section F: both repositories already exist in the ClariFile organization, ClassiFile (this project) and SummarEase (empty until its development starts); replaces the 1.1 note that they would be created near the finished product. Authorized by the user.
- **1.5 (2026-10-08):** B3 and E8: selective OCR now covers every non-repeated picture of at least 5% of its page or slide, regardless of native text, replacing the first rule; OCR junk from photos and decorations is filtered and counted. E8 development results recorded. Authorized by the user.
- **1.6 (2026-10-08):** A10: ClassiFile's scope is suggesting category names and filing; no text viewing, copying or exporting. A11: SummarEase's planned readable view, Copy and Export (new files only, on request, saved where the user chooses; originals and filed copies never changed); SummarEase entries move to its own record when its repository starts. B5: Remove from ClassiFile for waiting documents. Authorized by the user.
- **1.7 (2026-10-08):** B3: the extraction record keeps layout (line, paragraph and block boundaries, positions and text sizes) for native and OCR text, for SummarEase's later readable view; categorizing text and ClassiFile's interface are unchanged. Authorized by the user.
- **1.8 (2026-10-08):** B4: name review result on development data (21 of 34 files with a good name in the top three; 3 better names typed); the acceptable names are kept in `data\acceptable_names.csv` outside the repository, not in this record. Authorized by the user.
- **1.9 (2026-10-08):** neutral wording before the first push: the sample with conflicting identities (B1) is described instead of named by its course code. No requirement or decision changed. File names, course codes, people, institutions and titles from the user's documents stay out of tracked files; tests refer to development files by neutral IDs through a local map in `data\`. Authorized by the user.
- **2.0 (2026-10-12):** regrouping and naming, after the first filing of the development files gave one category per document. B5: Move to… (primary replacement, recorded as user-corrected), Rename category and Delete category (empty ones only), with the question about emptied categories; no merge and no aliases. D/CP3: "Belongs to" brought forward as Move to…; F: rename and delete of empty categories no longer deferred. B2: no one-click category creation once categories exist. B1: file names never suggest a category and count only as weak support for what the content says. A11: SummarEase summaries come from the content, never the file name. Authorized by the user.
- **2.1 (2026-10-12):** E1: result on development data recorded. No name-based policy reproduces the user's regrouped library (all 80 kept-together pairs fragmented; the shared-name upper bound keeps 8 and over-merges 4), because the folders are subject names that usually are not written in the documents. CP3 (matching to existing categories by content) comes first; CP4 needs a plan for naming new subjects. No rule changed. Authorized by the user.
- **2.2 (2026-10-13):** A0: the goal, stated by the user. ClassiFile is an automatic categorizer and choosing by hand is the fallback; it decides from the document's content, files automatically when the match is clear, asks only when it is unsure, and suggests new names only when no existing category fits. No other entry changed. Authorized by the user.
- **2.3 (2026-10-13):** B2: cards offer the three best-matching existing categories as one-click choices, and suggested new names only when no category is a good match. C: E2 result (nearest centroid selected) and E4 result (one global level on the best category's lead) recorded, with the validation measurement. B2 and Part E: the user chose Strict for automatic filing, with no automatic filing into a category that holds fewer than 3 confirmed documents, a "Filed automatically" view, and the level kept as a setting whose changes are recorded. B2 and F: grouping of waiting documents that match no existing category, approved as a narrow exception to the clustering deferral, shown to the user on development data first. D: selected-category mode and "Also belongs to" move from CP3 to CP4. `data\final-eval` stays untouched until CP5. Authorized by the user.
