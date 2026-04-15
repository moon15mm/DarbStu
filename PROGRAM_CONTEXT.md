# DarbStu — وصف شامل للبرنامج
> **نظام إدارة الغياب والتأخر المدرسي**  
> الإصدار: **2.8.2** | المطوّر: moon15mm | المنصة: Windows  
> المستودع: `https://github.com/moon15mm/DarbStu`

> [!NOTE]
> آخر تحديث لهذا الملف: أبريل 2026 — يشمل إضافة نظام التحويلات ونماذج المعلم وخطابات الاستفسار الأكاديمي

---

## 1. نظرة عامة

**DarbStu (درب)** برنامج سطح مكتب مكتوب بـ Python يُدار في المدارس السعودية لتسجيل الغياب والتأخر وإرسال إشعارات الواتساب للأولياء. يعمل البرنامج كخادم ويب محلي (FastAPI) ويفتح واجهة رسومية (Tkinter) في نفس الوقت. يمكن الوصول للبرنامج عبر الإنترنت من خلال نفق Cloudflare على النطاق `darbte.uk`.

**المكونات الرئيسية الثلاثة:**
- **Tkinter GUI** — واجهة المشرف على سطح المكتب (27 تبويباً)
- **FastAPI Server** — خادم ويب على المنفذ 8000 لاستقبال طلبات المعلمين والأولياء عبر المتصفح
- **Node.js WhatsApp Server** — خادم واتساب محلي في `my-whatsapp-server/` يُشغَّل بـ `npm start`

---

## 2. هيكل الملفات

```
DarbStu/
├── main.py                      ← نقطة الدخول الوحيدة
├── constants.py                 ← الثوابت والمتغيرات العامة المشتركة
├── database.py                  ← كل عمليات SQLite (CRUD + schema)
├── config_manager.py            ← تحميل/حفظ config.json مع Cache
├── whatsapp_service.py          ← إرسال رسائل الواتساب عبر الخادم المحلي
├── cloudflare_tunnel.py         ← إدارة نفق Cloudflare لرابط darbte.uk
├── license_manager.py           ← نظام الترخيص (HMAC + معرف الجهاز)
├── alerts_service.py            ← الإشعارات الذكية + الجدولة + التقارير
├── report_builder.py            ← بناء تقارير HTML/Excel
├── pdf_generator.py             ← توليد PDF (جلسات إرشادية، عقود سلوكية)
├── updater.py                   ← التحديث التلقائي من GitHub
├── grade_analysis.py            ← تحليل الدرجات
├── absences.db                  ← قاعدة البيانات الرئيسية (SQLite)
│
├── api/
│   ├── app.py                   ← تطبيق FastAPI الرئيسي (3 routers)
│   ├── mobile_routes.py         ← روابط الفصول، التأخر، النتائج، الاستئذان
│   ├── web_routes.py            ← بوابة الويب
│   └── misc_routes.py           ← مسارات متنوعة
│
├── gui/
│   ├── app_gui.py               ← الكلاس الرئيسي AppGUI (يرث 23 Mixin)
│   ├── login_window.py          ← نافذة تسجيل الدخول
│   └── tabs/                    ← ملف Python لكل تبويب
│       ├── dashboard_tab.py     ← لوحة المراقبة
│       ├── links_tab.py         ← روابط الفصول
│       ├── absence_tab.py       ← إدارة الغياب
│       ├── tardiness_tab.py     ← التأخر
│       ├── tardiness_msg_tab.py ← رسائل التأخر
│       ├── messages_tab.py      ← إرسال رسائل الغياب
│       ├── excuses_tab.py       ← الأعذار
│       ├── permissions_tab.py   ← الاستئذان
│       ├── reports_tab.py       ← التقارير والطباعة
│       ├── term_report_tab.py   ← تقرير الفصل
│       ├── results_tab.py       ← نشر النتائج
│       ├── grade_analysis_tab.py← تحليل النتائج
│       ├── noor_tab.py          ← تصدير نور
│       ├── alerts_tab.py        ← الإشعارات الذكية
│       ├── monitor_tab.py       ← المراقبة الحية
│       ├── schedule_tab.py      ← جدولة الروابط
│       ├── whatsapp_tab.py      ← إدارة الواتساب
│       ├── students_tab.py      ← إدارة الطلاب
│       ├── add_student_tab.py   ← إضافة طالب
│       ├── phones_tab.py        ← إدارة أرقام الجوالات
│       ├── settings_tab.py      ← إعدادات المدرسة
│       ├── users_tab.py         ← المستخدمون
│       ├── counselor_tab.py     ← الموجّه الطلابي
│       └── ...
│
└── data/
    ├── students.json            ← بيانات الطلاب (فصول + طلاب + جوالات)
    ├── teachers.json            ← بيانات المعلمين
    ├── config.json              ← إعدادات المدرسة
    ├── users.json               ← (غير مستخدم — المستخدمون في SQLite)
    └── backups/                 ← نسخ احتياطية تلقائية
        └── terms/               ← نسخ نهاية الفصول
```

---

## 3. نقطة الدخول — main.py

**التسلسل الكامل عند تشغيل البرنامج:**
1. `ensure_dirs()` — إنشاء مجلد `data/` إن لم يكن موجوداً
2. `init_db()` — تهيئة SQLite وترحيل الجداول
3. `uvicorn.run(app)` في خيط خلفي — تشغيل FastAPI على المنفذ 8000
4. `start_cloudflare_tunnel()` — تشغيل نفق Cloudflare → يعيد `public_url`
5. `ThemedTk(theme="arc")` — إنشاء نافذة Tkinter
6. `check_license()` → إن فشل → `LicenseWindow` / إن نجح → `LoginWindow`
7. `LoginWindow` → `AppGUI(root, public_url)` — بناء الواجهة الكاملة
8. جدولة المهام الخلفية:
   - `schedule_auto_backup(root)` — نسخ احتياطي كل 24 ساعة
   - `_schedule_tardiness_sender(root)` — إرسال رابط التأخر عند بدء الدوام
   - `schedule_daily_report(root)` — تقرير يومي في الساعة المحددة
   - `schedule_daily_alerts(root, run_hour=14)` — تنبيهات الغياب المتكرر الساعة 14
9. `root.mainloop()` — حلقة الأحداث الرئيسية

---

## 4. الواجهة الرسومية — AppGUI

### هيكل الكلاس

```python
class AppGUI(
    DashboardTabMixin, LinksTabMixin, AbsenceTabMixin, ReportsTabMixin,
    PhonesTabMixin, MessagesTabMixin, StudentsTabMixin, TardinessTabMixin,
    WhatsappTabMixin, ExcusesTabMixin, UsersTabMixin, SettingsTabMixin,
    TardinessMessagesTabMixin, AlertsTabMixin, NoorTabMixin, CounselorTabMixin,
    PermissionsTabMixin, TermReportTabMixin, ResultsTabMixin, MonitorTabMixin,
    ScheduleTabMixin, AddStudentTabMixin, GradeAnalysisTabMixin,
    TeacherReferralTabMixin,   # ★ جديد
    DeputyReferralTabMixin,    # ★ جديد
    TeacherFormsTabMixin,      # ★ جديد
):
```

> **تنبيه مهم:** كل Mixin يعرّف دوال التبويب الخاصة به (`_build_X_tab`).  
> لكن **بعض هذه الدوال معرَّفة مجدداً داخل `app_gui.py` مباشرةً** وتلك الأخيرة هي الفعلية (Python MRO تعطي الأولوية للكلاس الأخير في سلسلة الوراثة، لكن الدوال المعرَّفة **مباشرة في جسم `app_gui.py`** تتجاوز كل Mixin).

### بناء الشريط الجانبي

الشريط الجانبي يُبنى في `__init__` بـ **سبع مجموعات** (أضيفت مجموعتان جديدتان):

| المجموعة | التبويبات |
|----------|-----------|
| **يومي** | لوحة المراقبة، روابط الفصول، التأخر، الأعذار، الاستئذان، المراقبة الحية، الموجّه الطلابي |
| **السجلات** | السجلات/التصدير، إدارة الغياب، التقارير/الطباعة، تقرير الفصل، نشر النتائج، تحليل النتائج، تصدير نور، الإشعارات الذكية |
| **الرسائل** | إرسال رسائل الغياب، رسائل التأخر، مستلمو التأخر، جدولة الروابط، إدارة الواتساب |
| **البيانات** | إدارة الطلاب، إضافة طالب، إدارة الفصول، إدارة أرقام الجوالات |
| **الإعدادات** | إعدادات المدرسة، المستخدمون، النسخ الاحتياطية، معلومات الترخيص |
| **التحويلات** ★ جديد | تحويل طالب، استلام تحويلات |
| **نماذج المعلم** ★ جديد | نماذج المعلم |

**التبويبات تُبنى lazily** — كل تبويب يُنشأ أول مرة يضغط عليه المستخدم.

---

## 5. التبويبات التفصيلية

| اسم التبويب | الميثود الباني | الوظيفة | الملف |
|---|---|---|---|
| لوحة المراقبة | `_build_dashboard_tab` | إحصاءات يومية، مخططات الغياب، أعلى الفصول غياباً | dashboard_tab.py |
| روابط الفصول | `_build_links_tab` | إنشاء روابط مخصصة لكل فصل لتسجيل الحضور عبر المتصفح | links_tab.py |
| التأخر | `_build_tardiness_tab` | تسجيل وحذف التأخر، احتساب الدقائق، عرض التأخرات اليومية | tardiness_tab.py |
| الأعذار | `_build_excuses_tab` | إدارة أعذار الغياب (طبي، رسمي، شخصي) | excuses_tab.py |
| الاستئذان | `_build_permissions_tab` | طلبات خروج الطلاب أثناء الدوام، موافقة/رفض، إشعار الولي | permissions_tab.py |
| المراقبة الحية | `_build_live_monitor_tab` | جدول حي لحضور/غياب كل فصل في كل حصة | monitor_tab.py |
| السجلات / التصدير | `_build_logs_tab` | عرض سجلات الغياب وتصديرها CSV/Excel | logs_tab... (في app_gui.py) |
| إدارة الغياب | `_build_absence_management_tab` | تسجيل غياب بالجملة حسب الفصل والحصة | absence_tab.py |
| التقارير / الطباعة | `_build_reports_tab` | تقارير يومية/أسبوعية/شهرية/نهاية الفصل بصيغة HTML للطباعة | reports_tab.py |
| تقرير الفصل | `_build_term_report_tab` | ملخص الفصل الدراسي كاملاً | term_report_tab.py |
| نشر النتائج | `_build_results_tab` | رفع ملفات PDF النتائج، ربطها بالطلاب، إتاحتها عبر بوابة | results_tab.py |
| تحليل النتائج | `_build_grade_analysis_tab` | رسوم بيانية للدرجات والمعدلات | grade_analysis_tab.py |
| تصدير نور | `_build_noor_export_tab` | تصدير الغياب والتأخر بتنسيق Excel متوافق مع نظام نور | noor_tab.py |
| الإشعارات الذكية | `_build_alerts_tab` | تنبيهات عند تجاوز حد الغياب، إعداد العتبة والرسالة | alerts_tab.py |
| إرسال رسائل الغياب | `_build_messages_tab` | إرسال رسائل واتساب جماعية لأولياء الغائبين | messages_tab.py |
| رسائل التأخر | `_build_tardiness_messages_tab` | إرسال رسائل التأخر لأولياء المتأخرين | tardiness_msg_tab.py |
| مستلمو التأخر | `_build_tardiness_recipients_tab` | إدارة قائمة الأشخاص الذين يستلمون رابط التأخر تلقائياً | app_gui.py |
| جدولة الروابط | `_build_schedule_tab` | الجدول الدراسي الأسبوعي، إرسال روابط الحصص تلقائياً | schedule_tab.py |
| إدارة الواتساب | `_build_whatsapp_manager_tab` | تشغيل خادم الواتساب، مسح QR، فحص الاتصال، بوت الأعذار | whatsapp_tab.py + app_gui.py |
| إدارة الطلاب | `_build_student_management_tab` | حذف طلاب/فصول، عرض قائمة الطلاب | students_tab.py |
| إضافة طالب | `_build_add_student_tab` | إضافة طالب يدوياً أو استيراد من Excel | add_student_tab.py |
| إدارة الفصول | `_build_class_naming_tab` | تعديل أسماء ومعرّفات الفصول | app_gui.py |
| إدارة أرقام الجوالات | `_build_phones_tab` | تحديث أرقام جوالات الطلاب وأولياء الأمور | phones_tab.py |
| إعدادات المدرسة | `_build_school_settings_tab` | بيانات المدرسة، نوع المدرسة (بنين/بنات)، الجوالات، خوادم الواتساب، إدارة الفصل الدراسي | app_gui.py |
| المستخدمون | `_build_users_tab` | إدارة حسابات المستخدمين وصلاحياتهم | users_tab.py |
| النسخ الاحتياطية | `_build_backup_tab` | إنشاء/استعادة/تنزيل نسخ احتياطية | app_gui.py |
| الموجّه الطلابي | `_build_counselor_tab` | جلسات إرشادية، إحالات، عقود سلوكية، PDF | counselor_tab.py |
| تحويل طالب ★ | `_build_teacher_referral_tab` | نموذج تحويل الطالب من المعلم للوكيل، سجل التحويلات، طباعة، إشعار الوكيل | referral_teacher_tab.py |
| استلام تحويلات ★ | `_build_deputy_referral_tab` | عرض جميع التحويلات للوكيل، تسجيل الإجراءات، تحويل للموجه أو إغلاق | referral_deputy_tab.py |
| نماذج المعلم ★ | `_build_teacher_forms_tab` | نموذج تحضير الدرس + تقرير تنفيذ البرنامج، توليد PDF وإرساله للمدير | teacher_forms_tab.py |

---

## 6. نظام الصلاحيات (RBAC)

أربعة أدوار مُعرَّفة في `constants.py`:

| الدور | المعرف | اللون | الصلاحيات |
|-------|--------|-------|-----------|
| مدير | `admin` | `#7c3aed` بنفسجي | **كل التبويبات** بلا قيود |
| وكيل | `deputy` | `#1d4ed8` أزرق | الغياب، التأخر، الرسائل، الطلاب، الواتساب + **استلام تحويلات** ★ |
| معلم | `teacher` | `#065f46` أخضر | لوحة المراقبة، تحليل النتائج + **تحويل طالب** + **نماذج المعلم** + **خطابات الاستفسار** ★ |
| حارس | `guard` | `#92400e` بني | 3 تبويبات (لوحة المراقبة، التأخر، المراقبة الحية) |

**آلية التحقق:**
1. المستخدم يُسجّل الدخول → `authenticate(username, password)` في `database.py`
2. الدور يُحفظ في `CURRENT_USER` (dict عالمي في `constants.py`)
3. `get_user_allowed_tabs(username)` → `None` للمدير = كل شيء، أو قائمة للبقية
4. `AppGUI.__init__` يبني الشريط الجانبي بناءً على القائمة المسموح بها فقط

**إمكانية تخصيص التبويبات لكل مستخدم** — المدير يستطيع منح/سحب تبويبات بعينها لأي مستخدم من تبويب "المستخدمون".

> ⚠️ **تنبيه تعارض:** `constants.py → ROLE_TABS` يستخدم الاسم القديم **"لوحة القيادة"** لتبويب الداشبورد، بينما `app_gui.py` يستخدم **"لوحة المراقبة"**. الفلترة الفعلية تعتمد على `get_user_allowed_tabs()` من DB وليس ROLE_TABS، لذا لا يؤثر هذا التعارض على الصلاحيات المخصصة يدوياً.

---

## 7. قاعدة البيانات — absences.db (SQLite)

**إعدادات الأداء:** WAL mode, `synchronous=NORMAL`, `temp_store=MEMORY`

### الجداول (14 جدول)

#### absences — الغياب الرئيسي
```sql
id, date TEXT, class_id TEXT, class_name TEXT,
student_id TEXT, student_name TEXT,
teacher_id TEXT, teacher_name TEXT,
period INTEGER,         -- رقم الحصة (1-8)
created_at TEXT
UNIQUE(date, class_id, student_id)
```

#### tardiness — التأخر
```sql
id, date TEXT, class_id TEXT, class_name TEXT,
student_id TEXT, student_name TEXT,
teacher_name TEXT, period INTEGER,
minutes_late INTEGER,   -- عدد الدقائق
created_at TEXT
UNIQUE(date, student_id)
```

#### excuses — الأعذار
```sql
id, date TEXT, student_id TEXT, student_name TEXT,
class_id TEXT, class_name TEXT,
reason TEXT,            -- من EXCUSE_REASONS
source TEXT,            -- doctor / official / personal
approved_by TEXT, created_at TEXT
```

#### permissions — الاستئذان
```sql
id, date TEXT, student_id TEXT, student_name TEXT,
class_id TEXT, class_name TEXT,
parent_phone TEXT, reason TEXT,
approved_by TEXT, status TEXT,  -- waiting / approved / rejected
msg_sent_at TEXT, approved_at TEXT, created_at TEXT
```

#### users — المستخدمون
```sql
id, username TEXT UNIQUE, password TEXT,  -- SHA-256 hash
role TEXT,              -- admin / deputy / teacher / guard
full_name TEXT, active INTEGER,
allowed_tabs TEXT,      -- JSON list أو NULL للمدير
phone TEXT, created_at TEXT
```

#### messages_log — سجل الرسائل
```sql
id, date TEXT, student_id TEXT, student_name TEXT,
class_id TEXT, class_name TEXT,
phone TEXT, status TEXT,        -- sent / failed
template_used TEXT, message_type TEXT, created_at TEXT
```

#### student_results — نتائج الطلاب
```sql
id, identity_no TEXT,           -- رقم الهوية
student_name TEXT, section TEXT, school_year TEXT,
page_no INTEGER, pdf_path TEXT,
gpa REAL, class_rank INTEGER, section_rank INTEGER,
excused_abs INTEGER, unexcused_abs INTEGER,
subjects_json TEXT,             -- JSON مواد الدرجات
uploaded_at TEXT
```

#### result_tokens — رموز الوصول للنتائج
```sql
id, token TEXT UNIQUE, created_at TEXT, note TEXT
```

#### schedule — الجدول الدراسي
```sql
day_of_week INTEGER,    -- 0=الأحد ... 4=الخميس
class_id TEXT, period INTEGER,
teacher_name TEXT,
PRIMARY KEY(day_of_week, class_id, period)
```

#### counselor_sessions — الجلسات الإرشادية
```sql
id, date TEXT, student_id TEXT, student_name TEXT,
class_name TEXT, reason TEXT, notes TEXT,
action_taken TEXT, created_at TEXT
```

#### counselor_referrals — إحالات الإرشاد (من الوكيل للموجّه)
```sql
id, date TEXT, student_id TEXT, student_name TEXT,
class_name TEXT, referral_type TEXT,
absence_count INTEGER, tardiness_count INTEGER,
notes TEXT, referred_by TEXT, status TEXT, created_at TEXT
```

#### behavioral_contracts — العقود السلوكية
```sql
id, date TEXT, student_id TEXT, student_name TEXT,
class_name TEXT, subject TEXT,
period_from TEXT, period_to TEXT,
notes TEXT, created_at TEXT
```

#### student_referrals — تحويلات الطلاب من المعلم ★ جديد
```sql
-- بيانات المعلم (طرف المُحوِّل)
id, ref_date TEXT, student_id TEXT, student_name TEXT,
class_id TEXT, class_name TEXT,
subject TEXT, period TEXT, session_time TEXT, session_ampm TEXT,
violation_type TEXT,  -- تربوية / سلوكية / أخرى
violation TEXT, problem_causes TEXT,
repeat_count TEXT,    -- الأول / الثاني / الثالث / الرابع
teacher_action1..5 TEXT,
teacher_name TEXT, teacher_username TEXT, teacher_date TEXT,
status TEXT,          -- pending / with_deputy / with_counselor / resolved
-- بيانات الوكيل
deputy_meeting_date TEXT, deputy_meeting_period TEXT,
deputy_action1..4 TEXT,
deputy_name TEXT, deputy_date TEXT, deputy_referred_date TEXT,
-- بيانات الموجّه
counselor_meeting_date TEXT, counselor_meeting_period TEXT,
counselor_action1..4 TEXT,
counselor_name TEXT, counselor_date TEXT, counselor_referred_back_date TEXT,
created_at TEXT
```

#### academic_inquiries — خطابات الاستفسار الأكاديمي ★ جديد
```sql
-- الموجّه يُرسل خطاباً للمعلم يسأله عن أسباب ضعف طالب
id, date TEXT, counselor_name TEXT,
teacher_username TEXT, teacher_name TEXT,
class_name TEXT, subject TEXT, student_name TEXT,
teacher_reply_date TEXT,     -- رد المعلم
teacher_reply_reasons TEXT,  -- أسباب الضعف
teacher_reply_evidence TEXT, -- الشواهد
status TEXT,                 -- جديد / تم الرد
created_at TEXT
```

#### backup_log — سجل النسخ الاحتياطية
```sql
id, filename TEXT, size_kb INTEGER, created_at TEXT
```

---

## 8. ملفات البيانات JSON

### data/students.json
```json
{
  "classes": [
    {
      "id": "1-أ",
      "name": "أول ثانوي (السنة المشتركة) / أ",
      "students": [
        {"id": "1145182562", "name": "أبراهيم محمد علي", "phone": "0501234567"}
      ]
    }
  ]
}
```
> معرّف الفصل `class_id` له تنسيقات تاريخية متعددة: `"1-أ"`, `"1-A-XXXX"`, `"1-1"` — الدالة `normalize_legacy_class_id()` تُوحّدها.

### data/teachers.json
```json
{
  "teachers": [
    {"اسم المعلم": "أحمد علي", "رقم الجوال": "0536119860"}
  ]
}
```

### data/config.json (المفاتيح الكاملة)
```json
{
  "school_name": "اسم المدرسة",
  "assistant_title": "وكيل شؤون الطلاب",
  "assistant_name": "اسم الوكيل",
  "principal_title": "مدير",
  "principal_name": "اسم المدير",
  "counselor1_name": "اسم الموجّه الأول",
  "counselor1_phone": "966XXXXXXXXX",
  "counselor2_name": "اسم الموجّه الثاني",
  "counselor2_phone": "966XXXXXXXXX",
  "active_counselor": "1",
  "principal_phone": "966XXXXXXXXX",
  "alert_admin_phone": "966XXXXXXXXX",
  "school_gender": "boys",
  "message_template": "نص رسالة الغياب الافتراضية مع {{variables}}",
  "tardiness_message_template": "نص رسالة التأخر",
  "period_times": ["07:16", "08:06", "08:56", "09:50", "10:40", "11:30", "12:20", "13:10"],
  "school_start_time": "06:45",
  "tardiness_auto_send_enabled": true,
  "tardiness_auto_send_time": "06:45",
  "tardiness_recipients": [
    {"name": "الاسم", "phone": "0XXXXXXXXX", "role": "اداري"}
  ],
  "alert_enabled": true,
  "alert_absence_threshold": 5,
  "daily_report_enabled": true,
  "daily_report_hour": 8,
  "daily_report_minute": 0,
  "wa_servers": [
    {"port": 3001, "note": "رقم 2"}
  ],
  "noor_auto_export_enabled": false,
  "noor_export_hour": 14
}
```

---

## 9. خدمة الواتساب

### البنية
- **خادم Node.js** في `my-whatsapp-server/` يعمل على المنفذ 3000 (وأحياناً 3001+)
- يُشغَّل بالأمر: `npm start` (وليس `node server.js`)
- المسار الكامل: `os.path.join(BASE_DIR, 'my-whatsapp-server')` ← المتغير `WHATS_PATH`

### نقاط النهاية (Endpoints)
| Method | Path | الوظيفة |
|--------|------|---------|
| GET | `/status` | التحقق من الاتصال → `{"ready": true/false}` |
| POST | `/send-message` | إرسال رسالة نصية |
| POST | `/send-document` | إرسال ملف PDF |
| POST | `/bot-toggle` | تشغيل/إيقاف بوت الأعذار |

### صيغة الإرسال
```python
# إرسال رسالة
send_whatsapp_message(phone, message, student_data=None)
# phone: "0501234567" أو "966501234567" → يُحوَّل تلقائياً لـ "966501234567"

# إرسال PDF
send_whatsapp_pdf(phone, pdf_bytes, filename, caption)
```

### خوادم متعددة (Round Robin)
```python
# config["wa_servers"] = [{"port": 3001}, {"port": 3002}]
# + المنفذ 3000 يُضاف دائماً تلقائياً
get_next_wa_server()  # يعيد المنفذ التالي بالتناوب
```

---

## 10. خادم FastAPI (api/)

**المنفذ:** 8000 | **المسار المحلي:** `http://127.0.0.1:8000`  
**المسار العام:** `https://darbte.uk` (عبر Cloudflare)

### المسارات الرئيسية في mobile_routes.py

| Method | المسار | الوظيفة |
|--------|--------|---------|
| GET | `/` | إعادة توجيه لـ `/mobile` |
| GET | `/mobile` | البوابة الرئيسية (HTML) |
| GET | `/class-links` | روابط تسجيل الغياب لكل فصل |
| GET | `/live-monitor` | لوحة المراقبة الحية (HTML) |
| POST | `/submit-tardiness` | تسجيل التأخر من المتصفح |
| POST | `/submit-absence` | تسجيل الغياب من رابط الفصل |
| GET | `/results-portal` | بوابة نتائج الطلاب العامة |
| POST | `/query-permissions` | عرض طلبات الاستئذان |
| POST | `/submit-permission` | تقديم طلب استئذان |
| GET | `/manage-students` | صفحة إدارة الطلاب (HTML) |
| POST | `/delete-student` | حذف طالب |
| POST | `/delete-class` | حذف فصل |

---

## 11. خدمة الإشعارات (alerts_service.py)

**المهام التلقائية المجدوَلة:**

| المهمة | التوقيت | الوظيفة |
|--------|---------|---------|
| إرسال رابط التأخر | `school_start_time` يومياً | يرسل رابط التأخر لكل المستلمين في `tardiness_recipients` |
| التقرير اليومي | `daily_report_hour:daily_report_minute` | يرسل تلخيص الغياب لجوال الوكيل |
| الإشعارات الذكية | 14:00 يومياً | يفحص الطلاب الذين تجاوزوا عتبة الغياب (`alert_absence_threshold`) |
| النسخ الاحتياطية | كل 24 ساعة | ينشئ نسخة من `absences.db` و JSON files |

**عتبة الإشعارات الذكية:**
- `config["alert_absence_threshold"]` (افتراضي: 5 أيام)
- عند التجاوز: يرسل رسالة واتساب للولي + إشعار للوكيل/المدير

---

## 12. نظام التحديث التلقائي

**ملف:** `updater.py`  
**رابط الفحص:** `https://raw.githubusercontent.com/moon15mm/DarbStu/main/version.json`  
**رابط التنزيل:** `https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip`

**المسارات المحمية (لا تُحذف ولا تُستبدل):**
- `data/` — كل ملفات البيانات
- `my-whatsapp-server/` — خادم الواتساب
- `__pycache__/`, `.git/`

---

## 13. نظام الترخيص

**ملف:** `license_manager.py`  
**خادم الترخيص:** `https://darbstu-license.up.railway.app`

**آلية التحقق:**
1. `_get_machine_id()` = SHA256(عنوان MAC + اسم الجهاز)
2. ملف الترخيص `license.dat` = Base64( JSON + توقيع HMAC )
3. التحقق من: التوقيع + معرّف الجهاز + تاريخ الانتهاء
4. التجديد التلقائي إذا بقي أقل من 7 أيام

---

## 14. الثوابت الرئيسية (constants.py)

```python
APP_VERSION         = "2.8.2"
APP_TITLE           = "تسجيل غياب الطلاب"
PORT                = 8000              # قابل للتغيير بـ ABSENTEE_PORT env var
HOST                = "127.0.0.1"
TZ_OFFSET           = +3 hours          # توقيت الرياض
STATIC_DOMAIN       = "https://darbte.uk"
CLOUDFLARE_DOMAIN   = "darbte.uk"

DB_PATH             = "absences.db"
DATA_DIR            = "data"
BACKUP_DIR          = "data/backups"
STUDENTS_JSON       = "data/students.json"
TEACHERS_JSON       = "data/teachers.json"
CONFIG_JSON         = "data/config.json"
WHATS_PATH          = os.path.join(BASE_DIR, 'my-whatsapp-server')

UPDATE_URL          = "https://raw.githubusercontent.com/moon15mm/DarbStu/main/version.json"
UPDATE_DOWNLOAD_URL = "https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip"

# المستخدم الحالي (dict عالمي يُحدَّث عند تسجيل الدخول)
CURRENT_USER = {"username": "", "role": "admin", "label": "مدير"}
```

---

## 15. قواعد البرمجة الداخلية المهمة

> هذه القواعد ضرورية لأي مطوّر يعمل على الكود:

### 1. Thread Safety
```python
# أي طلب HTTP أو عملية بطيئة → في خيط خلفي
def _do():
    result = some_blocking_call()
    self.root.after(0, lambda: update_ui(result))

threading.Thread(target=_do, daemon=True).start()
```

### 2. Canvas Scroll Pattern (لتجنب Loop لا نهائي)
```python
# canvas.bind("<Configure>") → يُحدّث عرض النافذة الداخلية فقط
_lw = [0]
def _on_cv_conf(e):
    w = _cv.winfo_width()
    if w == _lw[0]: return   # منع Loop
    _lw[0] = w
    _cv.itemconfig(_win, width=w)

_cv.bind("<Configure>", _on_cv_conf)
# inner_frame.bind("<Configure>") → يُحدّث scrollregion فقط
scroll.bind("<Configure>", lambda e: _cv.configure(scrollregion=_cv.bbox("all")))
# عجلة الماوس
_cv.bind_all("<MouseWheel>", lambda e: _cv.yview_scroll(int(-1*(e.delta/120)), "units"))
```

### 3. Widget Consistency
```python
# استخدم دائماً tk.* مع bg="white" صريح (وليس ttk.*) داخل الـ Canvas البيضاء
# ttk.* تأخذ خلفية النظام (رمادي على Windows) وتُسبّب تعارضاً بصرياً
tk.LabelFrame(parent, bg="white", ...)   # ✓
ttk.LabelFrame(parent, ...)              # ✗ في الـ Canvas البيضاء
```

### 4. MRO Override
```python
# إذا عرّفت دالة في app_gui.py مباشرة، فهي تتجاوز نسختها في أي Mixin
# للتأكد من أي نسخة تعمل → ابحث في app_gui.py أولاً
grep "_build_whatsapp_manager_tab" gui/app_gui.py  # إن وُجدت → هي الفعلية
```

### 5. WhatsApp Server Command
```python
# الأمر الصحيح دائماً
subprocess.Popen(rf'cmd.exe /k "cd /d {WHATS_PATH} && npm start"',
                 creationflags=subprocess.CREATE_NEW_CONSOLE)
# الخطأ الشائع: node server.js بدلاً من npm start
```

### 6. إعادة بناء التبويبات
```python
# عند الحاجة لإعادة بناء تبويب (مثلاً بعد تغيير بيانات)
# احذف الـ frame القديم وأنشئ جديداً، أو استخدم update_all_tabs_after_data_change()
self.update_all_tabs_after_data_change()
```

---

## 16. المتطلبات والتبعيات

**Python Packages:**
```
fastapi, uvicorn, python-multipart   ← خادم الويب
tkinter (built-in), ttkthemes        ← الواجهة الرسومية
tkcalendar                           ← منتقي التاريخ
matplotlib                           ← الرسوم البيانية
arabic_reshaper, python-bidi         ← دعم العربية في matplotlib
reportlab                            ← توليد PDF
openpyxl                             ← Excel (نور)
Pillow, qrcode                       ← الصور وQR Code
tkinterweb                           ← عرض HTML داخل Tkinter
requests                             ← طلبات HTTP
```

**Node.js (للواتساب):**
```
my-whatsapp-server/package.json     ← npm install ثم npm start
```

**نظام التشغيل:** Windows (مطلوب لـ `subprocess.CREATE_NEW_CONSOLE` و `os.startfile`)

---

## 17. المسار المنطقي لأهم العمليات

### تسجيل غياب طالب (من المعلم عبر الهاتف)
1. المعلم يفتح رابط فصله: `https://darbte.uk/class/1-أ?token=XXX`
2. FastAPI `mobile_routes.py` يعرض صفحة HTML بقائمة الطلاب
3. المعلم يضغط على اسم الطالب الغائب
4. POST `/submit-absence` → `insert_absences()` في `database.py`
5. الواجهة تُحدَّث تلقائياً بعد 30 ثانية (polling)

### إرسال رسائل الغياب
1. المستخدم يفتح "إرسال رسائل الغياب"
2. يختار التاريخ → يُحمَّل قائمة الغائبين من DB
3. يضغط "إرسال الكل" → لكل طالب:
   - `render_message()` → يملأ القالب بالبيانات
   - `send_whatsapp_message(phone, msg)` → POST لخادم الواتساب
   - `log_message_status()` → يسجّل في `messages_log`
4. النتيجة تظهر في الواجهة (نجاح/فشل)

### جلسة إرشادية
1. الموجّه يفتح "الموجّه الطلابي"
2. يختار الطالب → يرى تاريخ غيابه وتأخره
3. يُسجّل ملاحظات الجلسة → `counselor_sessions` في DB
4. يمكن إنشاء عقد سلوكي أو إحالة → PDF يُرسَل للولي عبر الواتساب

---

## 18. نظام التحويلات ثلاثي المراحل ★ جديد

### المفهوم
نظام تحويل الطالب يمر بثلاث مراحل متسلسلة:

```
المعلم  →  يُنشئ تحويل  →  [pending]
   ↓
 الوكيل  →  يُسجّل إجراءاته  →  [with_deputy]
   ↓ (اختياري)
الموجّه  →  يُكمل الإجراءات  →  [with_counselor]
   ↓
   ✅  [resolved]
```

### حالات التحويل (status)
| الحالة | المعنى |
|--------|--------|
| `pending` | بانتظار الوكيل |
| `with_deputy` | الوكيل يعمل عليه |
| `with_counselor` | أُحيل للموجّه الطلابي |
| `resolved` | تم الحل وأُغلق |

### الإشعارات التلقائية
- عند إرسال تحويل جديد → واتساب للوكيل (`get_deputy_phones()`)
- عند إحالة للموجّه → واتساب للموجّه (`get_counselor_phones()`)
- عند أي مرحلة → يمكن إرسال ملخص للمدير

### طباعة النموذج
- `_build_referral_html(ref)` → تُولّد HTML يشبه النموذج الورقي الرسمي
- يُفتح في المتصفح للطباعة
- يحتوي أقسام: بيانات الطالب / إجراءات المعلم / إجراءات الوكيل / إجراءات الموجّه

### CRUD Functions (database.py)
```python
create_student_referral(data)        → int (id)
get_referrals_for_teacher(username)  → list
get_all_referrals(status_filter)     → list
get_referral_by_id(ref_id)           → dict
update_referral_deputy(ref_id, data) → None
update_referral_counselor(ref_id, data) → None
close_referral(ref_id)               → None
get_deputy_phones()                  → list[str]  # من جدول users
get_counselor_phones()               → list[str]  # من config.json
```

---

## 19. نماذج المعلم ★ جديد

**الملف:** `gui/tabs/teacher_forms_tab.py` — `TeacherFormsTabMixin`

يتيح للمعلمين تعبئة نموذجين رسميين وإرسالهما PDF للمدير:

### 1. نموذج تحضير الدرس
| الحقل | التفاصيل |
|-------|----------|
| الاستراتيجية | Combobox: (التعلم بحل المشكلات، التعاوني، المدمج...) |
| المادة / التاريخ / المرحلة / الفصل / عدد الطلاب / الدرس | حقول نصية |
| الأدوات والوسائل | أزرار toggle: سبورة، جهاز عرض، سبورة ذكية... |
| الأهداف | 5 حقول نصية |
| الشواهد | نص + صورة مرفقة اختيارية |
| التواقيع | المعلم + مدير المدرسة |

### 2. تقرير تنفيذ البرنامج
| الحقل | التفاصيل |
|-------|----------|
| المنفذ / مكان التنفيذ / المستهدفون / عدد المستفيدين / التاريخ | حقول نصية |
| الأهداف | 5 حقول |
| الشواهد بالصور | حتى صورتين مرفقتان |

### توليد PDF وإرساله
```python
_make_lesson_pdf(data)   → bytes   # ReportLab
_make_program_pdf(data)  → bytes
send_whatsapp_pdf(principal_phone, pdf_bytes, fname, caption)
```

---

## 20. خطابات الاستفسار الأكاديمي ★ جديد

**الغرض:** الموجّه يُرسل خطاباً رسمياً للمعلم يستفسر عن أسباب تراجع مستوى طالب.

### دورة العمل
1. الموجّه يفتح تبويب "الموجّه الطلابي" → قسم الاستفسارات
2. يختار المعلم والطالب والمادة
3. ينشئ خطاب استفسار → يُحفظ في `academic_inquiries` بحالة `"جديد"`
4. يُرسل إشعار واتساب للمعلم
5. المعلم يفتح تبويب "خطابات الاستفسار" → يُسجّل رده
6. الحالة تتغير إلى `"تم الرد"`

### CRUD Functions (database.py)
```python
create_academic_inquiry(data)          → int (id)
get_academic_inquiries(teacher_username) → list
get_academic_inquiry(inq_id)           → dict
reply_academic_inquiry(inq_id, data)   → None
```

---

*آخر تحديث: أبريل 2026 — الإصدار 2.8.2*
