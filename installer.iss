; ─── DarbStu Installer — Inno Setup Script ────────────────────────────────────
; نسخة التنصيب لنظام Windows

#define AppName      "DarbStu"
#define AppNameAr    "درب الطلاب"
#define AppVersion   "3.3.9"
#define AppPublisher "DarbStu"
#define AppURL       "https://github.com/moon15mm/DarbStu"
#define AppExeName   "DarbStu.exe"

[Setup]
; معلومات التطبيق
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; مسار التنصيب الافتراضي (لا يحتاج Admin)
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; الإخراج
OutputDir=Output
OutputBaseFilename=DarbStu_Setup_v{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExeName}

; ضغط عالي
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; لا يحتاج صلاحيات مدير
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; دعم Windows 10 فصاعداً
MinVersion=10.0

; واجهة التنصيب
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
DisableReadyPage=no

; لغة
ShowLanguageDialog=no

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات إضافية:"
Name: "startupicon"; Description: "التشغيل عند بدء Windows"; GroupDescription: "اختصارات إضافية:"; Flags: unchecked

[Files]
; ── الملف الرئيسي والتبعيات (مجلد PyInstaller كاملاً) ────────────────────────
Source: "dist\DarbStu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; اختصار قائمة ابدأ
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"

; اختصار سطح المكتب
Name: "{userdesktop}\{#AppNameAr}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

; إلغاء التنصيب
Name: "{group}\إلغاء تنصيب {#AppName}"; Filename: "{uninstallexe}"

[Registry]
; التشغيل عند بدء Windows (اختياري)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; تشغيل البرنامج بعد التنصيب
Filename: "{app}\{#AppExeName}"; Description: "تشغيل {#AppName} الآن"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

[UninstallDelete]
; حذف ملفات البيانات عند إلغاء التنصيب (اختياري — سيسأل المستخدم)
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// ─── التحقق من الذاكرة المطلوبة ───────────────────────────────────────────────
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// ─── صفحة الترحيب المخصصة ─────────────────────────────────────────────────────
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'سيقوم هذا المثبّت بتثبيت برنامج DarbStu (درب الطلاب) على جهازك.' + #13#10 + #13#10 +
    'البرنامج يعمل على:' + #13#10 +
    '  • تسجيل غياب وتأخر الطلاب' + #13#10 +
    '  • إرسال إشعارات واتساب تلقائية' + #13#10 +
    '  • توليد تقارير الغياب' + #13#10 + #13#10 +
    'الإصدار: {#AppVersion}';
end;
