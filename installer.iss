; AIMP Wallpaper 安装包脚本（Inno Setup 6）
; 编译：iscc installer.iss  → dist/aimp-wallpaper-v0.1.0-setup.exe
; 前置：先跑 PyInstaller 输出到 dist-setup\aimp-wallpaper\
; 注意：config.json / portable.flag 不打进安装包（用户状态与便携标记由运行时生成）

#define MyAppName "AIMP Wallpaper"
#define MyAppVersion "1.0.1"
#define MyAppExeName "aimp-wallpaper.exe"
#define MyAppMutex "AIMP_Wallpaper_Single"

[Setup]
AppId={{F4054C13-F6FF-4974-B06A-00916371A6FB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=qiuyitao
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
AppMutex={#MyAppMutex}
SetupIconFile=assets\icon.ico
OutputDir=dist
OutputBaseFilename=aimp-wallpaper-v{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
UsedUserAreasWarning=no
ChangesEnvironment=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; 自启任务只在首次安装时询问：升级完全不碰启动项，开关由设置 GUI 全权管理
; （否则每次升级安装都会把用户在设置里关掉的自启又勾回来）
Name: "autostart"; Description: "开机自动启动（仅首次安装询问；之后在设置里开关）"; \
    GroupDescription: "其他任务:"; Check: NotIsUpgrade()
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Code]
function NotIsUpgrade(): Boolean;
begin
  { [Code] 的 Pascal 字符串里 { 不需要 {{ 转义（那套转义只用于 Setup 段的常量值） }
  Result := not RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{F4054C13-F6FF-4974-B06A-00916371A6FB}_is1');
end;

[Files]
Source: "dist-setup\aimp-wallpaper\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "config.json,portable.flag"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\恢复原壁纸"; Filename: "{app}\{#MyAppExeName}"; Parameters: "restore"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时把首次运行记录的原壁纸设回去（restore 子命令不碰单实例锁，静默快速退出）
Filename: "{app}\{#MyAppExeName}"; Parameters: "restore"; WorkingDir: "{app}"; \
    Flags: skipifdoesntexist runhidden; RunOnceId: "RestoreWallpaper"

[UninstallDelete]
; 用户配置/渲染产物在 %LOCALAPPDATA%\aimp-wallpaper，卸载时保留
