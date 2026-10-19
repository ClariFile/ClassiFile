@echo off
rem ClassiFile portable test copy: the catalog goes to test-data beside this file, not to AppData\Local\ClassiFile.
rem Choose the test-output folder beside this file as the output folder when the app asks.
set "CLASSIFILE_DATA_DIR=%~dp0test-data"
if not exist "%~dp0test-output" mkdir "%~dp0test-output"
start "" "%~dp0ClassiFile\ClassiFile.exe"
