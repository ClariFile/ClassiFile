# Installer test on a clean laptop

A step-by-step check of `ClassiFile-<version>-setup.exe` on a Windows 10 or 11 laptop (64-bit) that has never had
Python or ClassiFile. About 30 minutes. Note what you see at each step in the table at the end. Nothing needs to be
installed first.

## Short checklist

Use a spare laptop or a disposable Windows (a virtual machine, or a separate Windows account), never the only
computer someone depends on. Disposable test documents only.

- [ ] Install: SmartScreen "More info → Run anyway"; no administrator prompt; no folder page (it always goes to
      `%LOCALAPPDATA%\Programs\ClassiFile`).
- [ ] First run: tour, an empty output folder; Help and About readable; About shows the version.
- [ ] Offline (airplane mode): add the documents, the scanned one too; none "couldn't be read"; file them; copies
      appear in the category folders; an original's Modified time unchanged; nothing new beside originals.
- [ ] Reopen: same state.
- [ ] Self-test (step 14): PASS.
- [ ] Upgrade (step 19): the newer setup over the older keeps categories and documents.
- [ ] Uninstall: program and shortcuts gone; output folder, `%LOCALAPPDATA%\ClassiFile` and originals stay.

The detailed steps follow.

## Bring

- The setup file on a USB stick (or downloaded from the GitHub release).
- 6–10 test documents in a folder of their own, for example `Desktop\ClassiFile test`: some PDFs, one Word file
  (.docx), one PowerPoint file (.pptx), and one scanned page or a PDF that is mostly pictures of text. Use copies of
  harmless documents. Nothing from `data\final-eval`.

## 1. Install

1. Copy the setup file to the laptop's Downloads folder and double-click it.
2. Windows shows a blue box, **"Windows protected your PC"**. This is expected: the installer is not signed yet.
   Click **More info**, then **Run anyway**.
   - Expected: no administrator prompt (no "Do you want to allow this app to make changes…"). If one appears, note it.
3. The wizard asks about a desktop shortcut. Tick it if you like, then **Install**.
   - Expected: it installs into `C:\Users\<name>\AppData\Local\Programs\ClassiFile` in under a minute.
4. Leave **Start ClassiFile** ticked and click **Finish**.

## 2. First run

5. Expected: the ClassiFile window opens with a short tour (4 steps). Go through it.
6. When asked for the output folder, make a new folder, for example `Documents\ClassiFile`, and choose it.
7. Open Help and About. Expected: text that fills its card across the window, the version (for example 1.0.0-rc.8) on
   About.

## 3. Offline use

8. Switch on **airplane mode** (or turn Wi-Fi off). Keep it on until step 13.
9. Before adding documents, right-click one test document → **Properties** and note its **Modified** date and time.
10. Drag the whole test folder's documents onto the window (or press **Add documents**).
    - Expected: each document is read. The scanned or picture document takes longer (it is read with OCR). None
      shows "couldn't be read".
11. Open **Needs your decision**. Press **Details** on a row: its pages show beside the list. Type a category name
    for the first documents ("Choose category…"), and file the rest in the categories you made.
    - Expected: each filed document has a copy in its category folder inside the output folder (open it in File
      Explorer to see).
12. Check the document from step 9 again: same **Modified** date and time, still in its folder. No new files appear
    beside the originals.
13. Close ClassiFile, open it again from the Start menu. Expected: the same categories and documents. Airplane mode
    can go off now.

## 4. Built-in check (optional, two minutes)

14. Press the Windows key, type `cmd`, press Enter, and paste (change the last part to one of your test documents,
    ideally the scanned one):

    ```
    "%LOCALAPPDATA%\Programs\ClassiFile\ClassiFile.exe" --self-test "%USERPROFILE%\Desktop\classifile-check.txt" "%USERPROFILE%\Desktop\ClassiFile test\scan.pdf"
    ```

15. Open `classifile-check.txt` on the desktop. Expected: "OCR language data: found", "ok" for the file, and **PASS**
    on the last line. It contains counts only, never document text.

## 5. Uninstall

16. Windows **Settings → Apps → Installed apps** → ClassiFile → **⋯ → Uninstall**, and confirm.
    - Expected: no administrator prompt; ClassiFile disappears from the Start menu and the desktop.
17. Check what stays:
    - the output folder (`Documents\ClassiFile`) with its copies;
    - `%LOCALAPPDATA%\ClassiFile` (paste it into File Explorer's address bar) with `catalog.sqlite3`;
    - the original test documents, unchanged.
    - Gone: `%LOCALAPPDATA%\Programs\ClassiFile`.
18. Optional: install again. Expected: the same categories and documents come back.

## 6. Upgrade (when an older setup file is at hand)

19. Install the older version, file two documents, then run the newer setup without uninstalling.
    - Expected: no folder question; About shows the new version; the same categories and documents.

## Results

| Step | Expected | Seen (OK / what happened) |
|---|---|---|
| 2 | SmartScreen: More info → Run anyway; no administrator prompt | |
| 3–4 | Installs per user, window opens | |
| 5–7 | Tour, output folder, Help and About readable | |
| 10 | Every document read, the scanned one too | |
| 11 | Details shows pages; copies in category folders | |
| 12 | Original unchanged, nothing new beside it | |
| 13 | Same state after reopening, offline | |
| 15 | Self-test PASS | |
| 16–17 | Uninstall removes the program, keeps copies, catalog and originals | |
| 19 | Upgrade keeps categories and documents | |

Send the table, the laptop's Windows version (Settings → System → About) and `classifile-check.txt`. Never send the
documents themselves.
