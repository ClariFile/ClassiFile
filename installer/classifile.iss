; Inno Setup script for ClassiFile: a per-user install (no administrator rights), offline after download.
; Built by installer/build.py, which passes AppVersion, Source (the PyInstaller folder) and Licenses.
; Uninstalling removes only the installed program files. The user's documents, ClassiFile's copies and its
; catalog (%LOCALAPPDATA%\ClassiFile) are never touched: nothing here deletes them.

#ifndef AppVersion
  #error Run through installer/build.py
#endif

[Setup]
AppId={{6F1C2B7E-3D4A-4C8E-9A51-2B7D0E9F4C13}
AppName=ClassiFile
AppVersion={#AppVersion}
AppVerName=ClassiFile {#AppVersion}
AppPublisher=ClariFile
AppPublisherURL=https://github.com/ClariFile/ClassiFile
AppSupportURL=https://github.com/ClariFile/ClassiFile/issues
DefaultDirName={localappdata}\Programs\ClassiFile
DefaultGroupName=ClassiFile
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ClassiFile-{#AppVersion}-setup
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\ClassiFile.exe
UninstallDisplayName=ClassiFile
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Licenses}\*"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\ClassiFile"; Filename: "{app}\ClassiFile.exe"
Name: "{userprograms}\ClassiFile licences"; Filename: "{app}\licenses"
Name: "{userdesktop}\ClassiFile"; Filename: "{app}\ClassiFile.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClassiFile.exe"; Description: "Start ClassiFile"; Flags: nowait postinstall skipifsilent
