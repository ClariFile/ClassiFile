ClassiFile portable test copy
=============================

A release candidate for optional testing. Nothing is installed: no Start-menu entry, no uninstall entry, no
registry key written by ClassiFile.

1. Unzip this folder anywhere you can write, for example Desktop\ClassiFile-portable.
2. Double-click ClassiFile-test.cmd (not ClassiFile\ClassiFile.exe: started directly, the app uses the normal
   catalog in AppData\Local\ClassiFile).
3. When asked for the output folder, choose the test-output folder beside ClassiFile-test.cmd.
4. Use copies of harmless documents only.

What it writes
- test-data\ beside ClassiFile-test.cmd: the catalog (catalog.sqlite3).
- test-output\ (or the output folder you chose): the filed copies.
- Nothing else by ClassiFile itself. Windows may record, as it does for any program: recently used folders in
  the file dialog, its usual launch records (Prefetch), and a SmartScreen check of the unzipped files.
- Your original documents are only read, never changed.

Removing it
- Close ClassiFile and delete the whole unzipped folder. That removes the program, its catalog and the test copies
  inside test-output. Documents you added from elsewhere stay where they were.
