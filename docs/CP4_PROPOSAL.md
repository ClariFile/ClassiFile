# CP4 proposal: automatic filing

2026-10-13 · a proposal for the owner; nothing here is built. It follows decision record 2.2 (A0, A4, A5, B1, B2,
Part E) and the CP3 results in `docs/STATUS.md`.

## 1. What CP4 would do

- **File automatically when the match is clear.** A document is filed without a question when its best category
  leads the second-best by at least the level the owner picks (section 2). Everything else waits on "Needs your
  decision", as now: three matching categories to choose from, or a suggested new name when nothing matches.
- **Say what the app did.** An automatically filed document is recorded as machine-assigned and shown as
  "Filed automatically" (not "Approved"), with the same reason as on the cards. It can be moved with Move to…;
  a move is the owner's correction and is recorded as one.
- **Learn only from the owner.** Machine-assigned placements never train the matcher (A7: lack of correction is
  never confirmation). "Update matching" keeps learning from confirmed and corrected placements only.
- **Never create a category without the owner.** In the first step of CP4 the app files into existing
  categories only. A document of a new subject waits with a suggested name, as now (B2).
- **Selected-category mode.** The same rules, within the categories the owner selects: the matcher still
  compares against every category (B1: a selection never manufactures confidence), and a document is filed
  automatically only when its best category overall is one of the selected ones and clears the level.
  Creating a category in this mode asks first, through the queue (A5).

## 2. The trade-off: how strict?

The level is one number: how far the best category must be ahead of the second-best (nearest centroid on word
TF-IDF; a similarity difference, not a probability). Five levels were fixed on development data before the
validation files were read. Validation was then measured once (`tools.match_validation`); the model was trained
on the 83 filed development documents.

**Validation: 23 documents (6 labels, 22 families)**

| Level | Filed automatically | Of those, wrong | Waiting for the owner |
|---|---|---|---|
| Very strict (lead ≥ 0.15) | 8 | 0 | 15 |
| Strict (lead ≥ 0.10) | 14 | 0 | 9 |
| Balanced (lead ≥ 0.06) | 17 | 1 | 6 |
| Lenient (lead ≥ 0.03) | 23 | 2 | 0 |
| File everything | 23 | 2 | 0 |

**Development: 83 documents, each family held out in turn (so no document is asked about its own versions)**

| Level | Filed right | Filed wrong | Waiting | New subjects filed, of 83 |
|---|---|---|---|---|
| Very strict | 24 | 0 | 59 | 0 |
| Strict | 43 | 1 | 39 | 3 |
| Balanced | 55 | 3 | 25 | 7 |
| Lenient | 60 | 6 | 17 | 28 |
| File everything | 65 | 18 | 0 | 83 |

The last column is the weak spot. It holds each whole category out, so every one of its documents is a subject
the app has never seen; any of them that gets filed is filed wrongly ("false familiar"). The validation files
cannot show this: every one of them belongs to a category that already exists.

**What the numbers can and cannot say.** 23 validation documents are few: one document is more than four
points of any share, so these are counts to choose by, not accuracy estimates. All the documents are course
material of one field, so different subjects share many words; a library with more distinct subjects would
separate better. `data\final-eval` has not been read.

**Recommendation: Strict.** No wrong filing on validation, one on development, more than half of the documents
filed without a question, and few new subjects mistaken for known ones (3 of 83). Balanced files a few more
and makes a few more mistakes. The owner picks; the choice is frozen in CP5.

## 3. What CP4 still has to solve

- **Naming new subjects.** E1 showed that the owner's category names are usually not written in the documents,
  so a single document rarely suggests the right name. Proposal: when several waiting documents match no
  category but resemble one another, show them as one question ("these 4 look like one new subject") with the
  suggested names, and let the owner name it once. Finding such groups is a form of clustering, which the
  record defers (F): it needs the owner's approval before it is built.
- **Small categories.** With one to three examples a category is found less often (development: first for 3 of
  7 such documents). Automatic filing into a category could wait until it holds a few confirmed documents.
- **The record's CP4 items** stay as written: re-evaluation of waiting documents when categories change (the
  matcher already recomputes after "Update matching"), and discovery replay (E10) as a diagnostic.

## 4. Decisions needed from the owner

1. The strictness level (section 2).
2. Whether grouping similar unmatched documents may be built for naming new subjects (section 3).
3. The record's CP3 list also has selected-category mode and "Also belongs to", which this round did not build.
   Proposal: move both to CP4 in the record (D).
4. Whether the E2 and E4 results and the rule for cards (three existing categories as one-click choices; new
   names only when no category is a good match) go into the record (B2, C).
