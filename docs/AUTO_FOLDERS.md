# More automation: the replay of automatic new folders, and the levels on the 33-file run

2026-10-14 · a report for the owner (decision record 2.6). Counts describe development data and the owner's own
run; they are not accuracy estimates. Categories are named by their size here; the report with their names, the
folder names and the key words is local (`data\auto_folders_replay.txt`). `data\final-eval` was not read.

**Automatic new folders are built and switched off.** They stay off until the owner has read section 1 and turns
them on (Settings, "Create new folders by itself").

## 1. Replay of automatic new folders on development data

`tools.group_eval --folders`: the 116 filed development documents (111 families, 12 categories), each category
held out in turn, as if the app had never seen that subject. The documents then waiting with no good match are the
held-out category's unmatched ones, plus every other document that its own category does not match when its family
is held out. Every group of at least 2 of them at an average similarity of 0.20 becomes a folder, named by the
rule in the record (a name suggested for several of its documents, else the best suggested name).

| Held-out category (documents) | Unmatched | Folders: held-out subject / mixed / a known subject again | The held-out subject comes back as |
|---|---|---|---|
| 51 | 32 | 7 / 0 / 1 | split over 7 folders, 14 left waiting |
| 17 | 7 | 1 / 0 / 1 | one folder, 1 left waiting |
| 11 | 5 | 1 / 0 / 0 | one folder, 3 left waiting |
| 8 | 3 | 1 / 0 / 1 | one folder, 1 left waiting |
| 7 | 4 | 1 / 0 / 1 | one folder, 2 left waiting |
| 6 | 0 | 0 / 0 / 0 | nothing to group |
| 5 | 1 | 0 / 0 / 1 | fewer than 2 unmatched |
| 4 | 0 | 0 / 0 / 1 | nothing to group |
| 3 | 1 | 0 / 0 / 1 | fewer than 2 unmatched |
| 2 | 0 | 0 / 0 / 1 | nothing to group |
| 1 | 1 | 0 / 0 / 1 | fewer than 2 unmatched |
| 1 | 0 | 0 / 0 / 1 | nothing to group |

**What you asked for:**
- **Folders created:** 21 over the 12 rounds.
- **Folders mixing subjects:** 0.
- **Subjects split in two or more:** 1. The 51-document subject, held out whole, comes back as 7 folders, with 14
  documents left waiting. The other 4 subjects with at least 2 unmatched documents come back as one folder each.

**What else the replay found: second folders for subjects the app already has.**
- 10 of the 21 folders hold only documents of a category the app already has.
  - They are 2 distinct pairs, counted once per round they appear in.
  - One pair from the 11-document folder appears in 9 of the 12 rounds. Its 2 documents match no existing folder
    whenever their family is held out, and they resemble each other.
  - One pair from the 4-document folder appears in 1 round.
- Live, such a pair would get a new folder beside the folder it belongs in: a duplicate folder.
- A simple threshold does not prevent this. Their similarity to the best existing folder (0.22 to 0.28) is the
  same as that of the genuine new-subject groups (0.13 to 0.33).
- **One option, not built:** create a folder only for groups of at least 3 documents.
  - On this data that keeps 3 of the 11 new-subject folders (6, 4 and 4 documents) and none of the 10 duplicates.
  - Pairs would stay questions, as groups found only at 0.15 do now.
  - This was chosen after seeing the results, so new files would have to confirm it.

**Names.**
- 14 folders took a name suggested for several of their documents; 7 took the best suggested name. Every group had
  a free name.
- None of the 11 new-subject folders got the owner's own folder name. This matches E1: your folders are subject
  names that the documents rarely contain.
- So expect to use Rename, which is one click in "Filed automatically".

**Fine print.**
- Holding out the 51-document category is an extreme case: in real use a subject arrives a few documents at a time.
- The app weighs the words over the trained documents plus the waiting ones. The replay weighs them over all 116.
  The two differ slightly.

## 2. The levels on your 33-file run (item 3)

Each of the 33 files was asked of a model built the way version 3 is: trained on the other 115 documents, without
near-identical versions of the file. The usual rule applies: no automatic filing into a category with fewer than 3
confirmed documents.

| Level | Filed automatically | Wrong | Left waiting |
|---|---|---|---|
| Very strict (lead 0.15) | 18 | 0 | 15 |
| **Strict (0.10, in use)** | 28 | 0 | 5 |
| Balanced (0.06) | 28 | 0 | 5 |
| Lenient (0.03) | 31 | 0 | 2 |

- Your category came first for 32 of the 33.
- Your actual run with version 2 at Strict was 21 filed (1 wrong) and 12 waiting. Most of the difference is the
  new folder of 5: version 2 had never seen that subject, while here its other 4 documents are in the training.
  That makes these figures kinder than a run on new files would be.
- Balanced adds nothing over Strict here. Lenient files 3 more with none wrong. With only 33 files that is no
  evidence that Lenient is safe: on development data (E4) it filed more documents wrongly.
- **Strict stays in use.** Changing the level is your choice, in Settings.

## 3. What was built (record 2.6, and interface phases 4 and 5)

- **Automatic new folders** (off; section 1).
  - Only in automatic mode: all categories, and a level other than Off. In "Only the ones I tick" mode the app asks
    first.
  - Only for groups of at least 2 unmatched waiting documents at 0.20. Groups found only at 0.15 stay questions,
    and a single document waits.
  - A name equal to an existing category is never reused: the next name is tried, and without one the group stays
    a question.
  - The folder is marked "New (named by ClassiFile)": "New · 3" in the sidebar, and listed in "Filed automatically"
    with its documents, key words and a one-click Rename… Renaming clears the mark.
  - Its documents are machine-assigned. They teach the matcher nothing until you confirm them, and nothing more is
    filed into the folder automatically until it holds 3 documents you confirmed.
- **Learning by itself.**
  - After every 10 confirmations or moves since the last version was trained, matching updates in the background,
    with the same check as before: a version that does worse is recorded and not used.
  - Settings lists the last versions: when, by you or by itself, and what the check found.
  - A note at the top of the window says when it updated, and goes once Settings has been opened or the note is
    dismissed.
- **Key words on cards.** "Similar to 9 documents in X (router, network, traffic)": 2 to 4 words the document
  shares most with that category, leaving out words found in more than a third of the documents. Automatic
  filings carry them too.
- **After each import, one line**, for example "Filed 4 automatically · 1 new folder · 1 needs you", with Review.
- **Phase 4 (motion).**
  - Settings, "Motion": Follow Windows (default), Reduce motion, or Full motion.
  - A filed row folds away in 150 ms, and the other rows keep their places meanwhile.
  - With reduced motion every change is instant. The details panel, the choices and the toast were already
    animated.
- **Phase 5.**
  - "Retry" on documents that couldn't be read: the original is read again.
  - "Find category…" above the sidebar's list from 11 categories, with "No category matches …" when nothing does.
    The open view stays as it is.
  - The nothing-found states of the pages were there already.
