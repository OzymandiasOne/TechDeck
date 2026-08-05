; TechDeck Installer Script
; Version 0.8.6.12 - 922 Setup card-creation webhook fix (restored buckets key); FormingFinder plate-vs-rod on dual-material parts; LST organizers match revision letters both ways; Batch Repeater audits repeat shop prints
; Requires Inno Setup 6.0 or later

#define MyAppName "TechDeck"
#define MyAppVersion "0.8.6.12"
#define MyAppPublisher "Anthony Siebenmorgen"
#define MyAppURL "https://github.com/OzymandiasOne/TechDeck"
#define MyAppExeName "TechDeck.exe"
#define MyAppDescription "Automation Dashboard for Manufacturing Workflows"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{8F2A3C4D-9B1E-4F7A-A5C3-2D8E6F9B4A1C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Comment out LicenseFile if you don't have a LICENSE.txt file
; LicenseFile=LICENSE.txt
; Use the TechDeck icon for installer
SetupIconFile=assets\techdeck.ico
; Output configuration
OutputDir=installer_output
OutputBaseFilename=TechDeck-{#MyAppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
; Windows version requirements (Windows 10 1809+)
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; UI Configuration
WizardStyle=modern
DisableProgramGroupPage=yes
DisableWelcomePage=no
; Privileges - NO ADMIN REQUIRED
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "launchonstartup"; Description: "Launch {#MyAppName} on Windows startup"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
; Main application files from dist\TechDeck\
Source: "dist\TechDeck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundled plugins (these will be copied to %LOCALAPPDATA% on first run by the app)
Source: "plugins\*"; DestDir: "{app}\plugins"; Flags: ignoreversion recursesubdirs createallsubdirs
; Assets (icons, etc.)
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentation (optional - comment out if not present)
; Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[InstallDelete]
; Remove plugin folders that were renamed (old IDs). Processed before [Files],
; so the new folders install cleanly and upgrades don't leave duplicate tiles.
; The app migrates settings.json (profile tiles, plugin settings, run stats)
; from the old IDs to the new ones on first launch.
Type: filesandordirs; Name: "{app}\plugins\lst_organizer"
Type: filesandordirs; Name: "{app}\plugins\part_sketch_extractor"
Type: filesandordirs; Name: "{app}\plugins\po_packet_extractor"
Type: filesandordirs; Name: "{app}\plugins\run_time_estimator"
Type: filesandordirs; Name: "{app}\plugins\911_linear_inch_calc"
; 2026-07 naming convention (id = family-prefixed snake_case of the Library name)
Type: filesandordirs; Name: "{app}\plugins\pricing_backup_splitter"
Type: filesandordirs; Name: "{app}\plugins\911_pricing_backup_splitter"
Type: filesandordirs; Name: "{app}\plugins\batch_repeater"
Type: filesandordirs; Name: "{app}\plugins\922_form_seeker"
Type: filesandordirs; Name: "{app}\plugins\qa_rework"
Type: filesandordirs; Name: "{app}\plugins\steeltube_game"
; 2026-07-13: 911_runtime_estimator renamed to 911_sspo_award_review
Type: filesandordirs; Name: "{app}\plugins\911_runtime_estimator"
; 2026-07-29: customer_dxf_quoting renamed to customer_dxf_analysis (absorbed
; the DXF Offset Tool; dxf_offset_tool never shipped in a release but purge
; any dev/zip drop of it too)
Type: filesandordirs; Name: "{app}\plugins\customer_dxf_quoting"
Type: filesandordirs; Name: "{app}\plugins\dxf_offset_tool"
; 2026-07-09: 911_linear_inch_cuttime retired (absorbed into 911_runtime_estimator).
; Removed - so also purge the running copy under %LOCALAPPDATA%.
Type: filesandordirs; Name: "{app}\plugins\911_linear_inch_cuttime"
Type: filesandordirs; Name: "{localappdata}\TechDeck\plugins\911_linear_inch_cuttime"

[Dirs]
; Create %LOCALAPPDATA%\TechDeck directory structure with full user permissions
Name: "{localappdata}\TechDeck"; Permissions: users-full
Name: "{localappdata}\TechDeck\plugins"; Permissions: users-full
Name: "{localappdata}\TechDeck\profiles"; Permissions: users-full
Name: "{localappdata}\TechDeck\logs"; Permissions: users-full

[Icons]
; Start Menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\techdeck.ico"; Comment: "{#MyAppDescription}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\techdeck.ico"; Tasks: desktopicon; Comment: "{#MyAppDescription}"
; Startup shortcut (optional)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\techdeck.ico"; Tasks: launchonstartup

[Registry]
; Store installation info in registry (CURRENT USER - no admin needed)
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "DataPath"; ValueData: "{localappdata}\TechDeck"

[Run]
; Option to launch TechDeck after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// NOTE: the installer used to write a default admin.config to
// %LOCALAPPDATA%\TechDeck, but AdminConfigManager reads it from %PROGRAMDATA%
// (system-wide, admin-only — that mismatch meant the file was never read), and
// the default it wrote was identical to the code defaults anyway. Removed so
// there is no misleading dead file. Admin policy, if ever needed, is a
// deliberately-placed ProgramData\TechDeck\admin.config.

// Uninstall: Ask about keeping user data
function InitializeUninstall(): Boolean;
var
  Response: Integer;
  LocalAppData: String;
  TechDeckData: String;
begin
  LocalAppData := ExpandConstant('{localappdata}');
  TechDeckData := LocalAppData + '\TechDeck';
  
  Response := MsgBox('Do you want to keep your TechDeck plugins, profiles, and settings?' + #13#10 + 
                     '(Located in %LOCALAPPDATA%\TechDeck)' + #13#10#13#10 +
                     'Yes = Keep all data (recommended)' + #13#10 +
                     'No = Remove everything', 
                     mbConfirmation, MB_YESNO);
  
  if Response = IDNO then
  begin
    // User wants to remove everything
    if DirExists(TechDeckData) then
    begin
      DelTree(TechDeckData, True, True, True);
      Log('Removed user data directory: ' + TechDeckData);
      MsgBox('All TechDeck data has been removed.', mbInformation, MB_OK);
    end;
  end
  else
  begin
    Log('User chose to keep data directory: ' + TechDeckData);
    MsgBox('Your TechDeck data has been preserved.' + #13#10 +
           'You can reinstall TechDeck without losing your plugins and settings.', 
           mbInformation, MB_OK);
  end;
  
  Result := True;
end;

[UninstallDelete]
; Clean up any temporary files created by the application
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\temp"
Type: filesandordirs; Name: "{app}\cache"
