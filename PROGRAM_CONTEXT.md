# DarbStu — وصف شامل للبرنامج
> **نظام إدارة الغياب والتأخر المدرسي**  
> الإصدار: **3.0.9** | المطوّر: moon15mm | المنصة: Windows  
> المستودع: `https://github.com/moon15mm/DarbStu`

> [!IMPORTANT]
> آخر تحديث لهذا الملف: 22 أبريل 2026 — يشمل إصلاحات أمان الحذف الموحدة، استعادة محرك تحليل الدرجات، تصفير البيانات لنهاية العام، وتحسينات واجهة الويب.

---

## 1. نظرة عامة

**DarbStu (درب)** هو نظام مدرسي متكامل لإدارة الحضور والانصراف، التواصل مع أولياء الأمور، وإدارة العمليات الإدارية (تحويلات، تعاميم، إرشاد). يتميز بالقدرة على العمل في وضعين:
1. **وضع السيرفر (Local Server):** يعمل كقاعدة بيانات رئيسية وخادم ويب.
2. **وضع السحاب (Cloud Mode):** يتصل بقاعدة بيانات عن بُعد عبر API، مما يسمح بتعدد الأجهزة والمزامنة الفورية.

**المكونات الرئيسية:**
- **Tkinter GUI** — واجهة الإدارة على سطح المكتب (تضم أكثر من 28 تبويباً).
- **FastAPI Server** — خادم ويب لاستقبال طلبات المعلمين والأولياء (المنفذ 8000).
- **CloudDBClient** — محرك مزامنة سحابي ذكي مدمج في `database.py`.
- **Node.js WhatsApp Server** — خادم محلي لإدارة إرسال الرسائل عبر مكتبة `whatsapp-web.js`.

---

## 2. هيكل الملفات المحدث

```
DarbStu/
├── main.py                      ← نقطة الدخول (تشمل فحوصات الترقية والمزامنة)
├── constants.py                 ← الثوابت، إصدار البرنامج، وأدوار المستخدمين
├── database.py                  ← محرك البيانات (يدعم Local SQLite + Cloud API)
├── config_manager.py            ← إدارة الإعدادات مع دعم الـ Caching
├── whatsapp_service.py          ← منطق إرسال الرسائل والمرفقات
├── pdf_generator.py             ← توليد نماذج PDF (إرشاد، تحضير، عقود)
│
├── api/
│   ├── app.py                   ← تطبيق FastAPI الرئيسي
│   ├── web_routes.py            ← (الأكبر) يشمل مسارات الإدارة، النتائج، والتعاميم
│   ├── mobile_routes.py         ← واجهة المعلم والأولياء المحمولة
│   └── misc_routes.py           ← مسارات متنوعة واختبارات الصحة
│
├── gui/
│   ├── app_gui.py               ← الكلاس الرئيسي (تجميع كل الـ Mixins والتبويبات)
│   ├── login_window.py          ← نافذة الدخول مع إعدادات الربط السحابي
│   └── tabs/
│       ├── alerts_tab.py        ← الإشعارات الذكية (تدعم Cloud API)
│       ├── circulars_tab.py     ← إدارة التعاميم الرسمية
│       ├── cloud_tab.py         ← إدارة المزامنة والربط مع السيرفر
│       ├── dashboard_tab.py     ← لوحة المراقبة والإحصاءات الحية
│       ├── counselor_tab.py     ← الموجّه الطلابي (إرشاد + استفسارات)
│       ├── links_tab.py         ← روابط الفصول (تستخدم URL السيرفر في Cloud)
│       ├── student_analysis_tab.py ← تحليل الطالب (يجلب GPA من السيرفر في Cloud)
│       ├── tardiness_msg_tab.py ← رسائل التأخر (تحميل في thread خلفي)
│       ├── teacher_forms_tab.py ← نماذج التحضير وتقارير البرامج
│       └── ... (بقية التبويبات الـ 25+)
│
└── data/
    ├── attachments/
    │   └── circulars/           ← تخزين مرفقات التعاميم (PDF/Images)
    └── backups/                 ← نسخ احتياطية دورية
```

---

## 3. نظام الصلاحيات (RBAC)

| الدور | المفتاح | التبويبات |
|-------|---------|-----------|
| **مدير (admin)** | `admin` | كل شيء (None = بلا قيود) |
| **وكيل (deputy)** | `deputy` | لوحة المراقبة، التأخر، الأعذار، الرسائل، إدارة الواتساب، استلام التحويلات، التعاميم |
| **معلم (teacher)** | `teacher` | لوحة المراقبة، تحليل النتائج، تحويل طالب، نماذج المعلم، خطابات الاستفسار، التعاميم |
| **حارس (guard)** | `guard` | لوحة القيادة، التأخر، المراقبة الحية |

**ملاحظة:** تبويب "إدارة الواتساب" مخصص للوكيل والمدير فقط.

---

## 4. هيكل قاعدة البيانات (الجداول الرئيسية)

| الجدول | الوصف |
|--------|-------|
| `absences` | سجلات الغياب اليومي |
| `tardiness` | سجلات التأخر (date, class_id, class_name, student_id, student_name, teacher_name, period, minutes_late) |
| `excuses` | الأعذار المقدمة |
| `permissions` | الاستئذان |
| `messages_log` | سجل الرسائل المرسلة (WhatsApp) |
| `student_results` | نتائج الطلاب (gpa, class_rank, section_rank, subjects_json) |
| `student_notes` | ملاحظات إدارية مرتبطة بطلاب |
| `counselor_sessions` | جلسات الإرشاد |
| `counselor_referrals` | تحويلات الموجه |
| `student_referrals` | تحويلات المعلمين |
| `counselor_alerts` | إنذارات الموجه |
| `circulars` | التعاميم الرسمية |
| `circular_reads` | تتبع قراءة التعاميم |
| `academic_inquiries` | الاستفسارات الأكاديمية |
| `users` | المستخدمون والصلاحيات |

---

## 5. نمط Cloud Client (مرجع مهم)

في وضع العميل السحابي، جميع دوال البيانات يجب أن تتحقق من `get_cloud_client()` أولاً:

```python
def _worker():
    from database import get_cloud_client
    client = get_cloud_client()
    if client and client.is_active():
        resp = client.get("/web/api/endpoint")
        data = resp.get("data") if resp.get("ok") else local_fallback()
    else:
        data = local_fallback()
    self.root.after(0, lambda d=data: self._update_ui(d))
threading.Thread(target=_worker, daemon=True).start()
```

### 5.1 أمن عمليات الحذف (تحديث 22 أبريل)
تم إلغاء نظام منع الحذف من أجهزة العميل واستبداله بنظام **تأكيد كلمة المرور** الموحد.
- **القاعدة:** أي مستخدم (مدير أو وكيل) يمكنه الحذف من أي جهاز (سيرفر أو عميل) بشرط إدخال كلمة مرور حسابه الشخصي بنجاح.
- **التنفيذ:** يتم استدعاء `database.authenticate(username, password)` قبل تنفيذ أي عملية حذف في الواجهة.
- **الهدف:** توفير مرونة في الوصول مع ضمان أمان البيانات من خلال التحقق من الشخص وليس الجهاز.
```

**التبويبات التي تدعم Cloud حالياً:**
- `student_analysis_tab.py` ← `/web/api/student-analytics/{student_id}`
- `alerts_tab.py` ← `/web/api/alerts-students` و `/web/api/alerts-tardiness`
- `links_tab.py` ← يستخدم `client.url` كـ base URL للروابط

---

## 6. Endpoints السيرفر المهمة (web_routes.py)

| الـ Endpoint | الوصف |
|-------------|-------|
| `GET /web/api/sync-info` | معلومات المزامنة (عدد السجلات، آخر تحديث) |
| `GET /web/api/config` | إعدادات المدرسة (قوالب الرسائل، الحدود، إلخ) |
| `GET /web/api/alerts-students` | الطلاب المتجاوزين لحد الغياب |
| `GET /web/api/alerts-tardiness` | الطلاب المتجاوزين لحد التأخر |
| `GET /web/api/analytics/dashboard` | بيانات لوحة المراقبة |
| `GET /web/api/analytics/weekly-comparison` | مقارنة أسبوعية للغياب |
| `GET /web/api/analytics/absence-by-dow` | توزيع الغياب على أيام الأسبوع |
| `GET /web/api/student-analytics/{id}` | تحليل طالب محدد (GPA + الغياب) |
| `POST /web/api/add-tardiness` | إضافة تأخر (date, class_id, class_name, student_id, student_name, period, minutes_late) |
| `POST /web/api/circulars/create` | إنشاء تعميم جديد |

---

## 7. مزامنة الإعدادات في Cloud Mode

عند تسجيل الدخول في وضع العميل، تُستدعى `force_sync_cloud_data()` في `database.py` التي تقوم بـ:
1. مزامنة الطلاب (`load_students(force_reload=True)`)
2. مزامنة المعلمين (`load_teachers()`)
3. مزامنة الإعدادات من السيرفر (`_sync_config_from_server()`)

**المفاتيح التي تُزامَن من السيرفر:**
- `school_name`, `school_gender`
- `tardiness_message_template`, `message_template`
- `alert_absence_threshold`, `alert_tardiness_threshold`
- `period_times`, `school_start_time`

---

## 8. نظام الترخيص

| الحالة | السلوك |
|--------|--------|
| **جهاز عميل** (cloud_mode=True) | يتجاوز فحص الترخيص مباشرة |
| **مُفعَّل** (license activated) | يعمل بلا قيود |
| **فترة تجربة** (≤7 أيام) | يعمل مع إشعار بالأيام المتبقية |
| **انتهت التجربة** | يفتح نافذة التفعيل قبل الدخول |

- ملف التجربة: `.darb_trial` في `BASE_DIR`
- ملف الترخيص: `.darb_license` في `BASE_DIR`
- زر التفعيل يظهر في الإعدادات للمدير فقط في وضع السيرفر وأثناء فترة التجربة.

---

## 9. نظام التحديث (updater.py)

- يُنزّل ZIP من `https://github.com/moon15mm/DarbStu/archive/refs/heads/main.zip`
- يُحدّث ملفات `.py, .txt, .json, .iss, .bat, .spec, .ico`
- يحمي مجلد `data/` وملفات الإعدادات من الكتابة فوقها
- **مهم:** في وضع EXE المجمّد، تحديث `.py` لا يؤثر — يجب بناء EXE جديد
- يقرأ الإصدار المثبّت من `version.json` (لا من `APP_VERSION` المجمّد) لتجنب حلقة التحديث

---

## 10. WhatsApp

- يعمل محلياً بالكامل على كل جهاز عبر Node.js (`whatsapp-web.js`)
- كل جهاز مستقل بواتسابه — لا مشاركة بين السيرفر والعميل
- يدعم Round-Robin بين عدة خوادم واتساب عبر `wa_servers` في الإعدادات
- المنفذ الافتراضي: `3000`، نقطة الإرسال: `http://127.0.0.1:{port}/send-message`

---

## 11. النمط الصحيح لـ Canvas القابل للتمرير (مرجع دائم)

```python
# 1. الـ scrollbar يُعبأ أولاً دائماً
sb.pack(side="right", fill="y")
canvas.pack(side="left", fill="both", expand=True)

# 2. inner frame → scrollregion فقط
inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

# 3. canvas → itemconfig(width) فقط مع guard لتجنب حلقة لا نهائية
_last_w = [0]
def _on_canvas_conf(e):
    w = canvas.winfo_width()
    if w == _last_w[0]: return
    _last_w[0] = w
    canvas.itemconfig(win_id, width=w)
canvas.bind("<Configure>", _on_canvas_conf)
```

---

## 12. إصلاحات جلسة 18 أبريل 2026

### أ. خطأ threading في إرسال التعاميم (`api/web_routes.py`)
- `threading` كان مستخدماً لإرسال تنبيهات واتساب عند نشر تعميم لكنه غير مستورد
- **الإصلاح:** إضافة `threading` لسطر الـ imports

### ب. الإشعارات الذكية لا تتحدث في العميل (`gui/tabs/alerts_tab.py`)
- `_load_alert_students()` و `_load_tardiness_alert_students()` كانتا تستعلمان من قاعدة البيانات المحلية
- **الإصلاح:** تشغيل في thread خلفي، في Cloud Mode تجلبان من `/web/api/alerts-students` و `/web/api/alerts-tardiness`

### ج. رسائل التأخر مختصرة في العميل (`database.py`)
- `force_sync_cloud_data()` لم تكن تزامن `config.json` (قوالب الرسائل)
- **الإصلاح:** إضافة `_sync_config_from_server()` تجلب الإعدادات المهمة من السيرفر عند الدخول

### د. خطأ `get_week_comparison` و `get_absence_by_day_of_week` (`api/web_routes.py`)
- الدالتان موجودتان في `alerts_service.py` لكنهما غير مستوردتان في `web_routes.py`
- **الإصلاح:** إضافتهما لسطر الـ import

### هـ. endpoint `/web/api/sync-info` مفقود (`api/web_routes.py`)
- لوحة المراقبة في العميل تستعلم عنه كل دقيقتين → 404 متكرر
- **الإصلاح:** إضافة الـ endpoint يُرجع عدد سجلات الغياب والتأخر

### و. خلط بين الحصة ودقائق التأخر (`api/web_routes.py` + `database.py`)
- في `web_routes.py`: ترتيب arguments في استدعاء `insert_tardiness` مقلوب (`student_id` ↔ `class_id`، و`minutes_late` يدخل خانة `period`)
- في `database.py`: العميل لم يُرسل `period` في payload
- **الإصلاح:** تصحيح الترتيب وإضافة `period` للـ payload

### ز. روابط الفصول تعرض IP محلي في العميل (`gui/tabs/links_tab.py`)
- `self.public_url` يكون `None` في العميل → يتراجع للـ IP المحلي
- **الإصلاح:** في Cloud Mode يستخدم `client.url` (رابط السيرفر الفعلي)

### ح. تجميد تبويب رسائل التأخر (`gui/tabs/tardiness_msg_tab.py`)
- `_tard_msg_load()` كانت تستعلم من DB مباشرة على الـ main thread
- **الإصلاح:** تشغيل الاستعلام في thread خلفي مع عرض "جارٍ التحميل..." فوراً

---

## 13. إصلاحات وتطويرات 22 أبريل 2026

### أ. أمن الحذف الموحد (Unified Deletion Security)
- **المشكلة:** منع الحذف من أجهزة العميل كان يقيد العمل الإداري.
- **الإصلاح:** إزالة `is_client_mode` من دوال المنع وإضافة طلب كلمة المرور عبر `simpledialog.askstring` لجميع عمليات الحذف (طلاب، فصول، غياب، تأخر، مستخدمين، إلخ).

### ب. استعادة واستقرار محرك تحليل الدرجات (`grade_analysis.py`)
- **المشكلة:** انهيارات في واجهة تحليل الدرجات بسبب استهلاك الذاكرة ومشاكل الرندر الداخلي.
- **الإصلاح:** إعادة بناء الواجهة لتعمل بشكل مستقر، وتوفير خيار "الفتح في المتصفح" كبديل آمن للرندر الداخلي.

### ج. تصفير البيانات لنهاية الفصل/العام (`database.py`)
- **الإضافة:** تطوير دالة `clear_yearly_data` لتدعم نوعين من المسح:
    - `term`: مسح الغياب، التأخر، الرسائل، التحويلات (نهاية فصل).
    - `year`: مسح النتائج، جلسات الإرشاد، التعاميم (نهاية سنة).

### د. تحسينات واجهة الويب (Web UI Enhancements)
- **التحديث:** دمج مكتبة **Font Awesome 6** وتصحيح مسارات الأيقونات.
- **التخصيص:** إضافة ترحيب شخصي في القائمة العلوية يظهر فيه اسم المستخدم المسجل بدلاً من "Welcome".
- **الاستقرار:** إصلاح أخطاء JavaScript في التعامل مع الأيقونات والتبويبات.

---

*آخر تحديث: 22 أبريل 2026*
*الحالة: مستقر مع أمان حذف متطور*

