; TechDeck Installer Script
; Inno Setup 6.x required

#define MyAppName "TechDeck"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Your Company Name"
#define MyAppURL "https://yourcompany.com"
#define MyAppExeName "TechDeck.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application. Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{A7B9C3D4-E5F6-7G8H-9I0J-K1L2M3N4O5P6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE.txt
; Uncomment the following line to run in non administrative install mode (install for current user only.)
;PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=TechDeck-Setup-{#MyAppVersion}
SetupIconFile=assets\techdeck.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\TechDeck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "plugins\*"; DestDir: "{commonappdata}\TechDeck\plugins"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Dirs]
Name: "{commonappdata}\TechDeck"; Permissions: users-full
Name: "{commonappdata}\TechDeck\plugins"; Permissions: users-full

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Code]
procedure InitializeWizard();
var
  AdminConfigPath: String;
  AdminConfig: String;
begin
  // Create default admin.config during installation
  AdminConfigPath := ExpandConstant('{commonappdata}\TechDeck\admin.config');
  
  // Only create if it doesn't exist (preserve existing configs)
  if not FileExists(AdminConfigPath) then
  begin
    AdminConfig := '{' + #13#10 +
      '  "version": "1.0.0",' + #13#10 +
      '  "user_role": "user",' + #13#10 +
      '  "company_api_key": "",' + #13#10 +
      '  "update_url": "",' + #13#10 +
      '  "plugin_whitelist": [],' + #13#10 +
      '  "plugin_blacklist": [],' + #13#10 +
      '  "mandatory_plugins": [],' + #13#10 +
      '  "allow_plugin_install": true,' + #13#10 +
      '  "allow_custom_profiles": true,' + #13#10 +
      '  "locked": false' + #13#10 +
      '}';
    
    SaveStringToFile(AdminConfigPath, AdminConfig, False);
  end;
end;
