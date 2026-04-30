# سجل التعديلات المؤجلة لـ DarbStu_Dist

هذا الملف يتتبع كل التعديلات التي طُبِّقت على `DarbStu` (مدرسة الدرب)
وتحتاج إلى تطبيقها لاحقاً على `DarbStu_Dist` (قالب المدارس الجديدة).

---

## [2026-04-30] إصلاح تغيير كلمة مرور المستخدمين

### المشكلة
- من الموقع: خطأ `name 'update_user_password' is not defined`
- من جهاز العميل (ديسكتوب): يظهر "تم بنجاح" لكن كلمة المرور لا تتغير فعلياً

### التعديلات المطلوبة

#### 1. `api/web_routes.py` — السطر ~44
أضف `update_user_password` لقائمة الاستيرادات من `database`:

```python
# قبل:
                      get_exempted_students, add_exempted_student, remove_exempted_student)

# بعد:
                      get_exempted_students, add_exempted_student, remove_exempted_student,
                      update_user_password)
```

#### 2. `database.py` — دالة `update_user_password` (السطر ~1794)
اجعل الدالة تُرجع خطأ إذا فشل الطلب للسيرفر:

```python
# قبل:
def update_user_password(username, new_password):
    client = get_cloud_client()
    if client.is_active():
        client.post("/web/api/users/update-password", {"username": username, "password": new_password})
        return
    ...

# بعد:
def update_user_password(username, new_password):
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/users/update-password", {"username": username, "password": new_password})
        if not res.get("ok"):
            raise Exception(res.get("msg", "فشل تغيير كلمة المرور على السيرفر"))
        return
    ...
```

#### 3. `gui/tabs/users_tab.py` — دالة `_user_change_pw` (السطر ~489)
أحط استدعاء الدالة بـ try/except:

```python
# قبل:
        update_user_password(username, new_pw)
        messagebox.showinfo("تم","تم تغيير كلمة المرور بنجاح")

# بعد:
        try:
            update_user_password(username, new_pw)
            messagebox.showinfo("تم","تم تغيير كلمة المرور بنجاح")
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل تغيير كلمة المرور:\n{e}")
```

#### 4. `gui/tabs/users_tab.py` — دالة `_user_send_individual_creds` (السطر ~664)
أحط استدعاء الدالة بـ try/except:

```python
# قبل:
        password = str(random.randint(100000, 999999))
        update_user_password(username, password)

# بعد:
        password = str(random.randint(100000, 999999))
        try:
            update_user_password(username, password)
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل تغيير كلمة المرور:\n{e}"); return
```

---

## [2026-04-30] إضافة زر حذف الطالب في تبويب إدارة الطلاب (الموقع)

### المشكلة
لا يوجد خيار حذف طالب من تبويب "إدارة الطلاب" في لوحة الويب.

### التعديلات المطلوبة

#### 1. `api/web_routes.py` — رأس جدول إدارة الطلاب (السطر ~2376)
أضف عمود "حذف":
```html
<!-- قبل: -->
<thead><tr><th>رقم الهوية</th><th>الاسم</th><th>الصف</th><th>الفصل</th><th>الجوال</th><th>تعديل</th></tr></thead>

<!-- بعد: -->
<thead><tr><th>رقم الهوية</th><th>الاسم</th><th>الصف</th><th>الفصل</th><th>الجوال</th><th>تعديل</th><th>حذف</th></tr></thead>
```

#### 2. `api/web_routes.py` — دالة `renderStuTbl` في JavaScript (السطر ~4137)
أضف زر الحذف في كل صف ودالة `deleteStudent`:
```javascript
// قبل:
function renderStuTbl(arr){
  var tb=document.getElementById('sm-table');if(!tb)return;
  tb.innerHTML=arr.slice(0,200).map(function(s){
    return '<tr><td>'+s.id+'</td><td>'+s.name+'</td><td>'+(s.level||'-')+'</td><td>'+s.class_name+'</td>'+
           '<td>'+(s.phone||'—')+'</td><td><button class="btn bp2 bsm" onclick="editPhone(\''+s.id+'\')">✏️ تعديل</button></td></tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا يوجد</td></tr>';
}

// بعد:
function renderStuTbl(arr){
  var tb=document.getElementById('sm-table');if(!tb)return;
  tb.innerHTML=arr.slice(0,200).map(function(s){
    return '<tr><td>'+s.id+'</td><td>'+s.name+'</td><td>'+(s.level||'-')+'</td><td>'+s.class_name+'</td>'+
           '<td>'+(s.phone||'—')+'</td>'+
           '<td><button class="btn bp2 bsm" onclick="editPhone(\''+s.id+'\')">✏️ تعديل</button></td>'+
           '<td><button class="btn bp3 bsm" onclick="deleteStudent(\''+s.id+'\',\''+s.name.replace(/'/g,"\\'")+'\')" style="background:#ef4444">🗑️ حذف</button></td></tr>';
  }).join('')||'<tr><td colspan="7" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function deleteStudent(id,name){
  if(!confirm('هل أنت متأكد من حذف الطالب:\n'+name+'؟\n\nسيتم حذف جميع بياناته نهائياً.'))return;
  var r=await fetch('/web/api/students/'+encodeURIComponent(id),{method:'DELETE'});
  var d=await r.json();
  if(d.ok){alert('✅ تم حذف الطالب بنجاح');loadStudents();}
  else alert('❌ '+(d.msg||'خطأ'));
}
```

#### 3. `api/web_routes.py` — endpoint جديد بعد `web_update_student_phone` (السطر ~6641)
أضف endpoint الحذف (للمدير والوكيل فقط):
```python
@router.delete("/web/api/students/{student_id}", response_class=JSONResponse)
async def web_delete_student(student_id: str, req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح — للمدير والوكيل فقط"}, status_code=403)
    try:
        store = load_students(force_reload=True)
        found = False
        for cls in store["list"]:
            for i, s in enumerate(cls["students"]):
                if str(s["id"]) == str(student_id):
                    del cls["students"][i]
                    found = True
                    break
            if found:
                break
        if not found:
            return JSONResponse({"ok": False, "msg": "الطالب غير موجود"})
        create_backup()
        import os as _os
        _tmp = STUDENTS_JSON + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump({"classes": store["list"]}, f, ensure_ascii=False, indent=2)
        _os.replace(_tmp, STUDENTS_JSON)
        load_students(force_reload=True)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)
```

---

---

## [2026-04-30] تحويل تبويب الملاحظات إلى نظام مراسلات داخلية

### المشكلة
تبويب "ملاحظات سريعة" كان مجرد ملاحظات محلية. يُستبدل بنظام مراسلات خاصة بين المستخدمين مع تنبيه بالرسائل الجديدة.

### التعديلات المطلوبة

#### 1. `database.py` — دالة `init_db` (بعد جدول `parent_portal_tokens`)
أضف جدول الرسائل:
```python
cur.execute("""CREATE TABLE IF NOT EXISTS inbox_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user   TEXT NOT NULL,
    to_user     TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0,
    read_at     TEXT,
    deleted_by_sender   INTEGER NOT NULL DEFAULT 0,
    deleted_by_receiver INTEGER NOT NULL DEFAULT 0
)""")
```

#### 2. `database.py` — أضف الدوال بعد `get_exempted_students`
```python
# --- Inbox Messages ---
def send_inbox_message(from_user, to_user, subject, body):
    # INSERT INTO inbox_messages ...
def get_inbox_messages(username):
    # SELECT ... WHERE to_user=? AND deleted_by_receiver=0
def get_sent_messages(username):
    # SELECT ... WHERE from_user=? AND deleted_by_sender=0
def get_inbox_unread_count(username):
    # SELECT COUNT(*) WHERE to_user=? AND is_read=0
def mark_inbox_message_read(msg_id, username):
    # UPDATE SET is_read=1
def delete_inbox_message(msg_id, username):
    # UPDATE deleted_by_sender/receiver
```
*(انسخ الدوال الكاملة من `DarbStu/database.py` السطر ~735)*

#### 3. `api/web_routes.py` — الاستيرادات (السطر ~44)
أضف:
```python
send_inbox_message, get_inbox_messages, get_sent_messages,
get_inbox_unread_count, mark_inbox_message_read, delete_inbox_message
```

#### 4. `api/web_routes.py` — sidebar: تغيير اسم التبويب
```python
# قبل:
("ملاحظات سريعة", "quick_notes", "fas fa-sticky-note"),
# بعد:
("الرسائل الداخلية", "quick_notes", "fas fa-envelope"),
```

#### 5. `api/web_routes.py` — حساب unread_inbox عند بناء الصفحة
```python
unread_inbox = get_inbox_unread_count(username)
```
وأضف badge في حلقة بناء الشريط الجانبي:
```python
if key == 'quick_notes' and unread_inbox > 0:
    badge = f'<span id="inbox-sidebar-badge" ...>{unread_inbox}</span>'
elif key == 'quick_notes':
    badge = '<span id="inbox-sidebar-badge" style="display:none" ...></span>'
```

#### 6. `api/web_routes.py` — HTML التبويب
استبدل محتوى `<div id="tab-quick_notes">` بواجهة المراسلات الكاملة (وارد/مرسل/إنشاء + مودال عرض الرسالة).
*(انسخ من `DarbStu/api/web_routes.py` السطر ~2737)*

#### 7. `api/web_routes.py` — API endpoints جديدة
أضف قبل `/web/api/absences-range`:
- `GET  /web/api/inbox/users` — قائمة المستخدمين للمرسل إليه
- `GET  /web/api/inbox` — الوارد
- `GET  /web/api/inbox/sent` — المرسل
- `GET  /web/api/inbox/unread-count` — عدد غير المقروء
- `POST /web/api/inbox/send` — إرسال
- `POST /web/api/inbox/{id}/read` — تعليم مقروء
- `DELETE /web/api/inbox/{id}` — حذف
*(انسخ من `DarbStu/api/web_routes.py` السطر ~6684)*

#### 8. `api/web_routes.py` — JavaScript
- احذف دوال `renderNotes`, `addNote`, `delNote` واستبدلها بـ `loadInbox`, `loadInboxSent`, `inboxSend`, `inboxDelete`, `inboxOpenMsg`, `inboxUpdateBadge`, إلخ
- احذف `var _notes=[]` من التهيئة
- غيّر `'quick_notes':renderNotes` إلى `'quick_notes':function(){inboxSwitch('inbox');}`
- أضف في `window.onload`: `setTimeout(inboxUpdateBadge,3000)`
- أضف `setInterval(inboxUpdateBadge,60000)` للتحديث كل دقيقة
*(انسخ الكود من `DarbStu/api/web_routes.py`)*

---

## [2026-04-30] إضافة ميزة "طلب حفظ رقم المدرسة" في تبويب إرسال رسائل الغياب

### المشكلة
إرسال الرسائل لأرقام لم تحفظ الرقم يسبب تقييد حساب الواتساب. الحل: إرسال رسالة مهذبة للأولياء مرة واحدة لطلب حفظ الرقم.

### التعديلات المطلوبة

#### 1. `api/web_routes.py` — HTML داخل `tab-send_absence` (بعد قسم الإرسال)
أضف قسماً جديداً بإطار أزرق منقط يحتوي على: معاينة الرسالة + فلتر الفصل + زر الإرسال.
*(انسخ من `DarbStu/api/web_routes.py` — ابحث عن `طلب حفظ رقم المدرسة`)*

#### 2. `api/web_routes.py` — endpoint المعاينة (قبل `send-tardiness-messages`)
```python
@router.get("/web/api/save-number-preview", ...)
# يُرجع نص الرسالة المهذبة مع اسم المدرسة
```

#### 3. `api/web_routes.py` — endpoint الإرسال (قبل `send-tardiness-messages`)
```python
@router.post("/web/api/send-save-number", ...)
# للمدير والوكيل فقط
# يرسل لجميع الأولياء مع تأخير عشوائي 8-18 ثانية بين كل رسالة
# يتجنب التكرار عبر seen_phones
```

#### 4. `api/web_routes.py` — JavaScript (قبل `/* ── PORTAL LINKS ── */`)
```javascript
async function snLoadPreview(){...}
async function sendSaveNumber(){...}
```

#### 5. `api/web_routes.py` — ربط التبويب
```python
# قبل:
'send_absence':function(){},
# بعد:
'send_absence':function(){snLoadPreview();fillSel('sn-cls');},
```

---

## [2026-04-30] إضافة رابط vCard لحفظ رقم المدرسة مباشرةً

### المشكلة
ولي الأمر يحتاج خطوات لحفظ الرقم. الرابط `/web/save-contact` يفتح نافذة "حفظ جهة الاتصال" مباشرةً عند الضغط عليه.

### التعديلات المطلوبة

#### 1. `api/web_routes.py` — إعدادات واتساب (قسم `ss-wa`)
أضف حقل "رقم واتساب المدرسة" وقسم "رابط vCard" مع زر نسخ وزر تجربة.
*(انسخ من `DarbStu/api/web_routes.py` — ابحث عن `ss-wa-phone`)*

#### 2. `api/web_routes.py` — endpoint vCard (قبل `save-number-preview`)
```python
@router.get("/web/save-contact")
async def web_save_contact():
    # يقرأ school_name + wa_phone من config
    # يُرجع ملف .vcf بـ Content-Type: text/vcard
```

#### 3. `api/web_routes.py` — تحديث endpoint الإرسال والمعاينة
أضف رابط `/web/save-contact` داخل نص الرسالة إذا كان `public_url` معيناً.

#### 4. `api/web_routes.py` — JavaScript
- في `loadSettings`: حمّل `wa_phone` واعرض رابط vCard
- أضف `saveWaSettings()` لحفظ الرقم عبر `/web/api/save-config`
- أضف `snCopyVcard()` لنسخ الرابط

---

## [2026-04-30] إصلاح ظهور الرسائل الداخلية + إضافة دعم المرفقات

### التعديلات المطلوبة

#### 1. `constants.py` — أضف مسار مجلد المرفقات
```python
INBOX_ATTACHMENTS_DIR = os.path.join(DATA_DIR, 'inbox_attachments')
```

#### 2. `database.py` — جدول inbox_messages: أضف أعمدة المرفقات
```sql
attachment_path  TEXT,
attachment_name  TEXT,
attachment_size  INTEGER
```
وأضف ترقية ALTER TABLE للمستخدمين الحاليين.

#### 3. `database.py` — دالة `send_inbox_message`: أضف parameters المرفق

#### 4. `api/web_routes.py` — استيراد INBOX_ATTACHMENTS_DIR

#### 5. `api/web_routes.py` — الصلاحيات: أضف "الرسائل الداخلية" لـ:
- `_US_ALL_TABS`
- جميع `_US_ROLE_DEFAULTS` (deputy, staff, counselor, activity_leader, teacher, lab, guard)

#### 6. `api/web_routes.py` — الشريط الجانبي: اجعل التبويب دائم الظهور
```python
visible = [(n, k, i) for n, k, i in grp_items
           if allowed_tabs is None or n in allowed_tabs or n == 'الرسائل الداخلية']
```

#### 7. `api/web_routes.py` — endpoints جديدة
- `POST /web/api/inbox/upload-attachment` — رفع ملف، يُرجع file_id
- `GET  /web/api/inbox/attachment/{file_id}` — تحميل الملف

#### 8. `api/web_routes.py` — HTML: أضف حقل المرفق في نموذج الإنشاء

#### 9. `api/web_routes.py` — JavaScript
- `inboxAttachmentChanged`, `inboxClearAttachment`: إدارة المرفق
- `inboxSend`: رفع المرفق أولاً ثم إرسال الرسالة مع بيانات المرفق
- `inboxOpenMsg`: عرض الصورة مباشرة أو زر تحميل للملفات الأخرى
- `loadInbox`/`loadInboxSent`: أضف أيقونة 📎 للرسائل التي تحتوي مرفقاً

---

## [2026-04-30] إصلاح إرفاق الصور في سجل شواهد الأداء

### المشكلة
- في صفحة `/web/lab-docs`، الضغط على منطقة رفع الصور أو سحبها لا يعمل
- كذلك تحديد درجات التقييم (`selScore`) لا يعمل

### السبب
في `lab_docs.html` (الملف خارج DarbStu_Dist عادةً)، كانت الدوال الأربع التالية تُعاد تعريفها باستخدام `function` declarations في نفس كتلة `<script>`:
- `toggleChk`, `selScore`, `addPhotos`, `deletePhoto`

بسبب JavaScript hoisting، الإصدار الأخير من التعريف يُرفع، فيصبح `_origFoo = newFoo` بدلاً من الأصلي → recursion لانهائي يتسبب في stack overflow عند أي استدعاء.

### التعديل المطلوب في `lab_docs.html`

```javascript
// قبل (خطأ — function declarations مرفوعة):
const _origSelScore = selScore;
function selScore(row, score) {
  _origSelScore(row, score);
  debounce(saveAllData, 300)();
}
const _origAddPhotos = addPhotos;
function addPhotos(uid, files) {
  _origAddPhotos(uid, files);
  setTimeout(saveAllData, 800);
}
const _origDeletePhoto = deletePhoto;
function deletePhoto(uid, idx) {
  _origDeletePhoto(uid, idx);
  saveAllData();
}

// بعد (صحيح — plain assignment لا يُرفع):
const _origSelScore = selScore;
selScore = function(row, score) {
  _origSelScore(row, score);
  debounce(saveAllData, 300)();
};
const _origAddPhotos = addPhotos;
addPhotos = function(uid, files) {
  _origAddPhotos(uid, files);
  setTimeout(saveAllData, 800);
};
const _origDeletePhoto = deletePhoto;
deletePhoto = function(uid, idx) {
  _origDeletePhoto(uid, idx);
  saveAllData();
};
```

> ملاحظة: هذا الملف (`lab_docs.html`) مشترك بين كل المدارس في حال توزيعه معهم. طبّق نفس الإصلاح.

---

## [2026-04-30] النسخ الاحتياطي التلقائي إلى Telegram

### التعديلات

#### 1. `database.py` — دالة جديدة بعد `get_backup_list`
```python
def upload_backup_telegram(zip_path: str) -> bool:
    # يقرأ telegram_backup_token و telegram_backup_chat من config.json
    # يرفع ملف ZIP عبر Telegram Bot API
    # يُشغَّل في خيط منفصل من schedule_auto_backup
```

#### 2. `database.py` — تعديل `schedule_auto_backup`
بعد نجاح `create_backup()` أضف:
```python
import threading
threading.Thread(target=upload_backup_telegram, args=(path,), daemon=True, name="backup-upload").start()
```

#### 3. `api/web_routes.py` — imports
```python
from database import (..., upload_backup_telegram)
```

#### 4. `api/web_routes.py` — HTML في قسم `ss-adv`
أضف section جديد بعد section الإعدادات الأساسية:
- حقل `ss-tg-token` لـ Bot Token
- حقل `ss-tg-chat` لـ Chat ID
- زر "حفظ" يستدعي `saveTelegramBackup()`
- زر "اختبار الآن" يستدعي `testTelegramBackup()`

#### 5. `api/web_routes.py` — JavaScript
```javascript
async function saveTelegramBackup() { /* يحفظ في config عبر /web/api/save-config */ }
async function testTelegramBackup() { /* يستدعي POST /web/api/backup/send-telegram */ }
// في loadSettings() أضف:
if(d.telegram_backup_token) document.getElementById('ss-tg-token').value = d.telegram_backup_token;
if(d.telegram_backup_chat)  document.getElementById('ss-tg-chat').value  = d.telegram_backup_chat;
```

#### 6. `api/web_routes.py` — endpoint جديد
```python
@router.post("/web/api/backup/send-telegram")
# ينشئ نسخة احتياطية فورية ثم يرفعها إلى Telegram
# للمدير فقط
```

<!-- أضف تعديلات جديدة هنا بنفس الصيغة -->
