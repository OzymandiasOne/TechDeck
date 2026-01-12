; TechDeck Installer Script
; Version 0.7.8 - Production Beta Release
; Requires Inno Setup 6.0 or later

#define MyAppName "TechDeck"
#define MyAppVersion "0.7.8"
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
// Custom initialization for plugins directory and admin config
procedure CurStepChanged(CurStep: TSetupStep);
var
  LocalAppData: String;
  AdminConfigPath: String;
  AdminConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Get %LOCALAPPDATA% path
    LocalAppData := ExpandConstant('{localappdata}');
    
    // Create default admin.config if it doesn't exist
    AdminConfigPath := LocalAppData + '\TechDeck\admin.config';
    
    if not FileExists(AdminConfigPath) then
    begin
      AdminConfig := '{' + #13#10 +
        '  "version": "1.0.0",' + #13#10 +
        '  "user_role": "user",' + #13#10 +
        '  "company_api_key": "",' + #13#10 +
        '  "update_url": "https://ozymandiasone.github.io/TechDeck-updates/manifest.json",' + #13#10 +
        '  "plugin_whitelist": [],' + #13#10 +
        '  "plugin_blacklist": [],' + #13#10 +
        '  "mandatory_plugins": [],' + #13#10 +
        '  "allow_plugin_install": true,' + #13#10 +
        '  "allow_custom_profiles": true,' + #13#10 +
        '  "locked": false' + #13#10 +
        '}';
      
      SaveStringToFile(AdminConfigPath, AdminConfig, False);
      Log('Created default admin.config at: ' + AdminConfigPath);
    end
    else
    begin
      Log('Admin config already exists, preserving: ' + AdminConfigPath);
    end;
  end;
end;

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
