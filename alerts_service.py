# -*- coding: utf-8 -*-
"""
alerts_service.py — نظام الإشعارات الذكية والتقارير اليومية
"""
import datetime, threading, os, json, sqlite3
from typing import List, Dict, Any, Optional
from constants import DB_PATH, DATA_DIR, TZ_OFFSET, CONFIG_JSON, now_riyadh_date
from config_manager import load_config, get_terms, render_message
from database import (get_db, query_absences, query_tardiness,
                      _apply_class_name_fix, load_students, get_cloud_client)
from whatsapp_service import send_whatsapp_message, check_whatsapp_server_status
# تأجيل استيراد report_builder لتجنّب الدورة (circular import)
def _get_compute_today_metrics():
    from report_builder import compute_today_metrics
    return compute_today_metrics

def safe_send_absence_alert(student_id: str, student_name: str, class_name: str, date_str: str) -> (bool, str):
    """يرسل تنبيه الغياب مع فحص حالة الخادم أولاً"""
    _cfg = load_config()
    if not _cfg.get("absence_bot_enabled", True):
        return False, "بوت رسائل الغياب موقوف — فعّله من تبويب إدارة الواتساب."

    if not check_whatsapp_server_status():
        return False, "خادم الواتساب غير متاح. الرجاء تشغيله أولاً."
    
    store = load_students()
    phone = next((s.get("phone") for c in store.get("list", []) for s in c.get("students", []) if s.get("id") == student_id), None)
    
    if not phone:
        return False, "لا يوجد رقم جوال مسجل للطالب"
        
    message_body = render_message(student_name, class_name, date_str)
    _student_data = {
        "student_id":   student_id,
        "student_name": student_name,
        "class_name":   class_name,
        "class_id":     class_name,   # fallback
        "date":         date_str,
    }
    return send_whatsapp_message(phone, message_body, student_data=_student_data)

def send_absence_alert(student_id: str, student_name: str, class_name: str, date_str: str) -> (bool, str):
    """يرسل تنبيه الغياب باستخدام القالب المخزن."""
    return safe_send_absence_alert(student_id, student_name, class_name, date_str)

def build_absent_groups(date_str: str) -> Dict[str, Dict[str, Any]]:
    """
    يُرجع هيكل مجمّع: {class_id: {"class_name":..., "students": [ {id,name,phone}, ... ]}}
    يعتمد على سجلات الغياب لليوم + أرقام الجوال من students.json
    """
    rows = _apply_class_name_fix(query_absences(date_filter=date_str))
    store = load_students()
    phone_map = {}
    class_name_map = {}
    for c in store["list"]:
        class_name_map[c["id"]] = c["name"]
        for s in c["students"]:
            phone_map[s["id"]] = s.get("phone", "")

    grouped: Dict[str, Dict[str, Any]] = {}
    seen = set()
    for r in rows:
        sid = r["student_id"]
        if sid in seen:
            continue
        seen.add(sid)
        cid = r["class_id"]
        cname = r.get("class_name") or class_name_map.get(cid, cid)
        if cid not in grouped:
            grouped[cid] = {"class_name": cname, "students": []}
        grouped[cid]["students"].append({
            "id": sid,
            "name": r["student_name"],
            "phone": phone_map.get(sid, "")
        })
    for v in grouped.values():
        v["students"].sort(key=lambda s: s["name"])
    return grouped

def log_message_status(date_str: str, student_id: str, student_name: str, class_id: str, class_name: str, phone: str, status: str, template_used: str):
    con = get_db(); cur = con.cursor()
    cur.execute("""
        INSERT INTO messages_log(date, student_id, student_name, class_id, class_name, phone, status, template_used, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_str, student_id, student_name, class_id, class_name, phone, status,
        template_used, datetime.datetime.utcnow().isoformat()
    ))
    con.commit(); con.close()

def query_today_messages(date_str: str) -> List[Dict[str, Any]]:
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM messages_log WHERE date = ? ORDER BY class_id, student_name", (date_str,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

def save_schedule(day_of_week: int, schedule_data: List[Dict[str, Any]]):
    """Saves the class schedule for a specific day of the week."""
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM schedule WHERE day_of_week = ?", (day_of_week,))
    
    for item in schedule_data:
        if item.get("teacher_name"):
            cur.execute(
                "INSERT INTO schedule (day_of_week, class_id, period, teacher_name) VALUES (?, ?, ?, ?)",
                (day_of_week, item["class_id"], item["period"], item["teacher_name"])
            )
    con.commit()
    con.close()


def load_schedule(day_of_week: int) -> Dict[tuple, str]:
    """Reads the class schedule for a specific day of the week."""
    try:
        con = get_db()
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT class_id, period, teacher_name FROM schedule WHERE day_of_week = ?", (day_of_week,))
        rows = cur.fetchall()
        con.close()
        return {(row['class_id'], row['period']): row['teacher_name'] for row in rows}
    except sqlite3.OperationalError:
        return {}




# ===================== الواجهة الرسومية =====================


# ═══════════════════════════════════════════════════════════════
# تحليلات لوحة المدير
# ═══════════════════════════════════════════════════════════════

def get_week_comparison() -> Dict:
    """يقارن غياب هذا الأسبوع بالأسبوع الماضي."""
    today   = datetime.date.today()
    monday  = today - datetime.timedelta(days=today.weekday())
    # بداية هذا الأسبوع (الأحد)
    this_sun  = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    last_sun  = this_sun - datetime.timedelta(days=7)
    this_sat  = this_sun + datetime.timedelta(days=6)
    last_sat  = last_sun + datetime.timedelta(days=6)

    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/analytics/weekly-comparison")
        return res.get("data", {}) if res.get("ok") else {}

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()

    def count_week(start, end):
        cur.execute("""SELECT COUNT(DISTINCT date||student_id) as cnt
                       FROM absences WHERE date BETWEEN ? AND ?""",
                    (start.isoformat(), end.isoformat()))
        return (cur.fetchone() or {"cnt": 0})["cnt"]

    def daily_counts(start, end):
        cur.execute("""SELECT date, COUNT(DISTINCT student_id) as cnt
                       FROM absences WHERE date BETWEEN ? AND ?
                       GROUP BY date ORDER BY date""",
                    (start.isoformat(), end.isoformat()))
        return {r["date"]: r["cnt"] for r in cur.fetchall()}

    this_total = count_week(this_sun, this_sat)
    last_total = count_week(last_sun, last_sat)
    this_daily = daily_counts(this_sun, this_sat)
    last_daily = daily_counts(last_sun, last_sat)
    con.close()

    change = this_total - last_total
    pct    = round(change / max(last_total, 1) * 100, 1)
    return {
        "this_total": this_total,
        "last_total": last_total,
        "change":     change,
        "pct":        pct,
        "this_daily": this_daily,
        "last_daily": last_daily,
        "this_week_start": this_sun.isoformat(),
        "last_week_start": last_sun.isoformat(),
    }


def get_top_absent_students(month: str = None, limit: int = 10) -> List[Dict]:
    """أكثر الطلاب غياباً هذا الشهر."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/analytics/top-absent", params={"month": month, "limit": limit})
        return res.get("rows", []) if res.get("ok") else []

    if not month:
        month = datetime.datetime.now().strftime("%Y-%m")
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""
        SELECT student_id, MAX(student_name) as name,
               MAX(class_name) as class_name,
               COUNT(DISTINCT date) as days,
               MAX(date) as last_date
        FROM absences WHERE date LIKE ?
        GROUP BY student_id
        ORDER BY days DESC LIMIT ?
    """, (month + "%", limit))
    rows = [dict(r) for r in cur.fetchall()]; con.close()
    return rows


def get_absence_by_day_of_week(months_back: int = 2) -> Dict:
    """يحسب متوسط الغياب لكل يوم من أيام الأسبوع."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/analytics/absence-by-dow")
        return res.get("data", {}) if res.get("ok") else {}

    since = (datetime.date.today() - datetime.timedelta(days=months_back*30)).isoformat()
    con   = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""
        SELECT date, COUNT(DISTINCT student_id) as cnt
        FROM absences WHERE date >= ?
        GROUP BY date
    """, (since,))
    rows = cur.fetchall(); con.close()

    day_names = ["الأحد","الاثنين","الثلاثاء","الأربعاء","الخميس"]
    totals = {d: [] for d in day_names}
    for r in rows:
        try:
            dt  = datetime.date.fromisoformat(r["date"])
            dow = (dt.weekday() + 1) % 7  # 0=Sunday
            if dow < 5:
                totals[day_names[dow]].append(r["cnt"])
        except Exception:
            pass
    return {d: (sum(v)/len(v) if v else 0) for d, v in totals.items()}

# ═══════════════════════════════════════════════════════════════
# نظام الإشعارات الذكية — تنبيه عند تجاوز عتبة الغياب
# ═══════════════════════════════════════════════════════════════

def get_student_absence_count(student_id: str, month: str = None) -> Dict[str, Any]:
    """
    يُرجع عدد أيام غياب الطالب + آخر يوم غياب + الفصل + الاسم.
    month: بصيغة "YYYY-MM" — إذا None يحسب كل السجلات.
    """
    client = get_cloud_client()
    if client.is_active():
        # This can be handled by the general query_absences or a specific endpoint
        # For now, let's use the local logic since it relies on query_absences which is already cloud-aware
        pass

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    if month:
        cur.execute("""SELECT COUNT(DISTINCT date) as cnt, MAX(date) as last_date,
                              MAX(student_name) as name, MAX(class_name) as class_name
                       FROM absences WHERE student_id=? AND date LIKE ?""",
                    (student_id, month + "%"))
    else:
        cur.execute("""SELECT COUNT(DISTINCT date) as cnt, MAX(date) as last_date,
                              MAX(student_name) as name, MAX(class_name) as class_name
                       FROM absences WHERE student_id=?""",
                    (student_id,))
    row = cur.fetchone(); con.close()
    if not row or not row["cnt"]:
        return {"count": 0, "last_date": "", "name": "", "class_name": ""}
    return {"count": row["cnt"], "last_date": row["last_date"] or "",
            "name": row["name"] or "", "class_name": row["class_name"] or ""}


def get_students_exceeding_threshold(threshold: int = None,
                                      month: str = None) -> List[Dict]:
    """
    يُرجع قائمة الطلاب الذين تجاوزوا عتبة الغياب.
    يُرتَّب تنازلياً حسب عدد الغيابات.
    """
    cfg = load_config()
    if threshold is None:
        threshold = cfg.get("alert_absence_threshold", 5)
    if month is None:
        month = datetime.datetime.now().strftime("%Y-%m")

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""
        SELECT student_id,
               MAX(student_name)  as student_name,
               MAX(class_name)    as class_name,
               COUNT(DISTINCT date) as absence_count,
               MAX(date)          as last_date
        FROM absences
        WHERE date LIKE ?
        GROUP BY student_id
        HAVING absence_count >= ?
        ORDER BY absence_count DESC
    """, (month + "%", threshold))
    rows = [dict(r) for r in cur.fetchall()]; con.close()

    # أضف رقم جوال ولي الأمر من students.json
    store = load_students()
    phone_map = {}
    for cls in store["list"]:
        for s in cls["students"]:
            phone_map[s["id"]] = s.get("phone", "")

    for r in rows:
        r["parent_phone"] = phone_map.get(r["student_id"], "")

    return rows


def send_alert_for_student(student: Dict, cfg: Dict = None) -> Dict:
    """
    يُرسل تنبيه غياب متكرر لولي الأمر و/أو الإدارة.
    يُرجع {"parent": bool, "admin": bool, "errors": []}
    """
    if cfg is None:
        cfg = load_config()

    school     = cfg.get("school_name", "المدرسة")
    sid        = student["student_id"]
    sname      = student["student_name"]
    cls        = student["class_name"]
    count      = student["absence_count"]
    last_date  = student["last_date"]
    phone      = student.get("parent_phone", "")
    result     = {"parent": False, "admin": False, "errors": []}

    # ─ رسالة ولي الأمر
    if cfg.get("alert_notify_parent") and phone:
        tpl = cfg.get("alert_template_parent", "")
        try:
            msg = tpl.format(
                school_name=school, student_name=sname,
                class_name=cls, absence_count=count,
                last_date=last_date, parent_phone=phone, guardian=get_terms()["guardian"], son=get_terms()["son"], absent_v=get_terms()["absent_v"])
            ok, status = send_whatsapp_message(phone, msg)
            result["parent"] = ok
            if not ok:
                result["errors"].append("ولي أمر {}: {}".format(sname, status))
        except Exception as e:
            result["errors"].append("خطأ رسالة ولي الأمر: {}".format(e))

    # ─ رسالة الإدارة
    if cfg.get("alert_notify_admin"):
        admin_phone = cfg.get("alert_admin_phone", "").strip()
        if admin_phone:
            tpl = cfg.get("alert_template_admin", "")
            try:
                msg = tpl.format(
                    school_name=school, student_name=sname,
                    class_name=cls, absence_count=count,
                    last_date=last_date, parent_phone=phone or "غير مسجّل")
                ok, status = send_whatsapp_message(admin_phone, msg)
                result["admin"] = ok
                if not ok:
                    result["errors"].append("الإدارة: {}".format(status))
            except Exception as e:
                result["errors"].append("خطأ رسالة الإدارة: {}".format(e))

    return result


def run_smart_alerts(month: str = None, log_cb=None) -> Dict:
    """
    يفحص كل الطلاب ويُرسل تنبيهات لمن تجاوز العتبة.
    يُرجع ملخص العملية.
    """
    cfg = load_config()
    if not cfg.get("alert_enabled", True):
        return {"skipped": True, "reason": "الإشعارات معطّلة"}

    if month is None:
        month = datetime.datetime.now().strftime("%Y-%m")

    threshold = cfg.get("alert_absence_threshold", 5)
    students  = get_students_exceeding_threshold(threshold, month)

    if log_cb:
        log_cb("فحص الإشعارات — {} طالب تجاوز {} أيام غياب".format(
            len(students), threshold))

    sent_p, sent_a, failed = 0, 0, 0
    details = []

    _delay = max(1, cfg.get("tard_msg_delay_sec", 8))
    for s in students:
        res = send_alert_for_student(s, cfg)
        if res["parent"]: sent_p += 1
        if res["admin"]:  sent_a += 1
        if res["errors"]: failed += 1
        details.append({
            "student": s["student_name"],
            "class":   s["class_name"],
            "count":   s["absence_count"],
            "parent":  res["parent"],
            "admin":   res["admin"],
            "errors":  res["errors"],
        })
        if log_cb:
            status = "✅" if (res["parent"] or res["admin"]) else "❌"
            log_cb("{} {} — {} يوم غياب".format(
                status, s["student_name"], s["absence_count"]))
        time.sleep(_delay)  # تأخير بين الرسائل لتجنب حظر الواتساب

    return {
        "month": month, "threshold": threshold,
        "total_students": len(students),
        "sent_parent": sent_p, "sent_admin": sent_a,
        "failed": failed, "details": details,
    }


def schedule_daily_alerts(root_widget, run_hour: int = 14):
    """
    يجدول تشغيل الإشعارات الذكية يومياً في ساعة محددة (افتراضي 14:00).
    """
    def check_and_run():
        now = datetime.datetime.now()
        if now.weekday() in {4, 5}:  # الجمعة والسبت إجازة
            root_widget.after(3_600_000, check_and_run)
            return
        if now.hour == run_hour and now.minute < 5:
            print("[ALERTS] تشغيل الإشعارات الذكية اليومية...")
            threading.Thread(
                target=lambda: run_smart_alerts(
                    log_cb=lambda m: print("[ALERTS]", m)),
                daemon=True).start()
            # انتظر ساعة قبل الفحص التالي لتجنب التكرار
            root_widget.after(3_600_000, check_and_run)
        else:
            root_widget.after(300_000, check_and_run)  # فحص كل 5 دقائق

    root_widget.after(60_000, check_and_run)

# ═══════════════════════════════════════════════════════════════
# نافذة تسجيل الدخول
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# تحليل الطالب الفردي
# ═══════════════════════════════════════════════════════════════

def get_student_full_analysis(student_id: str) -> Dict:
    """يجمع كل بيانات الطالب: غياب + تأخر + أعذار + إحصائيات."""
    client = get_cloud_client()
    if client.is_active():
        res = client.get(f"/web/api/student-analysis/{student_id}")
        return res.get("data", {}) if res.get("ok") else {}

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()

    # اسم الطالب وفصله
    cur.execute("""SELECT student_name, class_name, class_id
                   FROM absences WHERE student_id=?
                   ORDER BY date DESC LIMIT 1""", (student_id,))
    row = cur.fetchone()
    name       = row["student_name"] if row else student_id
    class_name = row["class_name"]   if row else ""
    class_id   = row["class_id"]     if row else ""

    # رقم الجوال
    store = load_students()
    phone = next((s.get("phone","")
                  for cls in store["list"]
                  for s in cls["students"]
                  if s["id"] == student_id), "")

    # غياب
    cur.execute("""SELECT date, period, teacher_name
                   FROM absences WHERE student_id=?
                   ORDER BY date DESC""", (student_id,))
    absence_rows = [dict(r) for r in cur.fetchall()]

    # غياب شهري
    cur.execute("""SELECT substr(date,1,7) as month, COUNT(DISTINCT date) as days
                   FROM absences WHERE student_id=?
                   GROUP BY month ORDER BY month DESC""", (student_id,))
    monthly = [dict(r) for r in cur.fetchall()]

    # توزيع أيام الأسبوع
    dow = {"الأحد":0,"الاثنين":0,"الثلاثاء":0,"الأربعاء":0,"الخميس":0}
    for r in absence_rows:
        try:
            dt = datetime.date.fromisoformat(r["date"])
            d  = (dt.weekday()+1) % 7
            if d < 5: dow[list(dow)[d]] += 1
        except: pass

    # تأخر
    cur.execute("""SELECT date, minutes_late FROM tardiness
                   WHERE student_id=? ORDER BY date DESC""", (student_id,))
    tard_rows = [dict(r) for r in cur.fetchall()]

    # أعذار
    cur.execute("""SELECT date, reason, source, approved_by
                   FROM excuses WHERE student_id=? ORDER BY date DESC""",
                (student_id,))
    excuse_rows = [dict(r) for r in cur.fetchall()]

    # استئذانات
    try:
        cur.execute("""SELECT date, reason, status, approved_by, msg_sent_at
                       FROM permissions WHERE student_id=? ORDER BY date DESC""",
                    (student_id,))
        perm_rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        perm_rows = []

    # متوسط الفصل
    cur.execute("""SELECT COUNT(DISTINCT date||student_id) as t,
                          COUNT(DISTINCT student_id) as n
                   FROM absences WHERE class_id=?""", (class_id,))
    cr = cur.fetchone()
    class_avg = round(cr["t"]/max(cr["n"],1), 1) if cr else 0
    con.close()

    unique_days  = len(set(r["date"] for r in absence_rows))
    excused_set  = set(r["date"] for r in excuse_rows)

    return {
        "student_id": student_id, "name": name,
        "class_name": class_name, "class_id": class_id, "phone": phone,
        "total_absences": unique_days,
        "excused_days": len(excused_set),
        "unexcused_days": unique_days - len(excused_set),
        "total_tardiness": len(tard_rows),
        "total_permissions": len(perm_rows),
        "class_avg": class_avg,
        "absence_rows": absence_rows, "monthly": monthly,
        "dow_count": dow, "tardiness_rows": tard_rows,
        "excuse_rows": excuse_rows, "perm_rows": perm_rows,
    }


# ═══════════════════════════════════════════════════════════════
# التقرير اليومي للإدارة — إرسال يدوي فقط
# ═══════════════════════════════════════════════════════════════

def build_daily_summary_message(date_str: str = None) -> str:
    if not date_str:
        date_str = now_riyadh_date()
    cfg       = load_config()
    school    = cfg.get("school_name", "المدرسة")
    threshold = cfg.get("alert_absence_threshold", 5)
    metrics   = _get_compute_today_metrics()(date_str)
    t         = metrics["totals"]

    top_classes = sorted(metrics["by_class"],
                         key=lambda x: x["absent"], reverse=True)[:5]
    top_txt = ""
    for c in top_classes:
        if c["absent"] > 0:
            top_txt += "  - {} : {} غائب\n".format(c["class_name"], c["absent"])

    tard_cnt = len(query_tardiness(date_filter=date_str))

    lines = [
        "ملخص يوم {} - {}".format(date_str, school),
        "-" * 30,
        "اجمالي الطلاب: {}".format(t["students"]),
        "الحضور: {}".format(t["present"]),
        "الغياب: {} ({}%)".format(
            t["absent"],
            round(t["absent"] / max(t["students"], 1) * 100, 1)),
        "التاخر: {}".format(tard_cnt),
        "-" * 30,
        "اكثر الفصول غياباً:",
        top_txt.strip() or "لا يوجد غياب",
        "-" * 30,
        "ادارة {}".format(school),
    ]
    return "\n".join(lines)


def send_daily_report_to_admin(date_str: str = None) -> tuple:
    cfg         = load_config()
    admin_phone = cfg.get("alert_admin_phone", "").strip()
    if not admin_phone:
        return False, "لم يُحدَّد رقم الإدارة في إعدادات الإشعارات"
    msg = build_daily_summary_message(date_str)
    return send_whatsapp_message(admin_phone, msg)


def schedule_daily_report(root_widget):
    """
    يجدول التقرير اليومي بـ after() واحدة تحسب الوقت المتبقي بدقة.
    لا يعمل في الخلفية — يُجدَّد مرة واحدة فقط عند الاستدعاء.
    """
    cfg = load_config()
    if not cfg.get("daily_report_enabled", False):
        return  # معطّل — لا تجدول

    now   = datetime.datetime.now()
    h     = cfg.get("daily_report_hour",   13)
    m     = cfg.get("daily_report_minute", 30)
    today = now.replace(hour=h, minute=m, second=0, microsecond=0)

    # إذا فات الوقت اليوم → جدول لغداً
    if now >= today:
        today += datetime.timedelta(days=1)

    # تخطَّ الجمعة والسبت
    while today.weekday() in (4, 5):   # Fri=4, Sat=5
        today += datetime.timedelta(days=1)

    ms = int((today - now).total_seconds() * 1000)

    def _fire():
        cfg2 = load_config()
        if cfg2.get("daily_report_enabled", False):
            import threading as _th
            _th.Thread(
                target=lambda: send_daily_report_to_admin(),
                daemon=True).start()
        # جدول مرة ثانية لليوم التالي
        schedule_daily_report(root_widget)

    root_widget.after(ms, _fire)
    print("[DAILY-REPORT] سيُرسَل في {} (بعد {:.0f} دقيقة)".format(
        today.strftime("%Y-%m-%d %H:%M"),
        (today - now).total_seconds() / 60))


# ═══════════════════════════════════════════════════════════════
# نظام الاستئذان
# ═══════════════════════════════════════════════════════════════

PERMISSION_REASONS = ["مراجعة طبية","ظرف طارئ","موعد رسمي",
                       "إجراءات حكومية","أخرى"]
PERM_WAITING  = "انتظار"
PERM_APPROVED = "موافق"
PERM_REJECTED = "مرفوض"

def insert_permission(date_str, student_id, student_name,
                      class_id, class_name, parent_phone,
                      reason="", approved_by="") -> int:
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/add-permission", {
            "date": date_str, "student_id": student_id, "student_name": student_name,
            "class_id": class_id, "class_name": class_name, "parent_phone": parent_phone,
            "reason": reason
        })
        return res.get("id", 0) if res.get("ok") else 0

    created = datetime.datetime.utcnow().isoformat()
    con = get_db(); cur = con.cursor()
    cur.execute("""INSERT INTO permissions
        (date,student_id,student_name,class_id,class_name,parent_phone,
         reason,approved_by,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (date_str,student_id,student_name,class_id,class_name,parent_phone,
         reason,approved_by,PERM_WAITING,created))
    rid = cur.lastrowid; con.commit(); con.close()
    return rid

def update_permission_status(pid, status, exit_time=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.post("/web/api/update-permission", {
            "id": pid, "status": status
        })
        return res.get("ok", False)

    approved = datetime.datetime.utcnow().isoformat()
    con = get_db(); cur = con.cursor()
    if exit_time:
        cur.execute("UPDATE permissions SET status=?,approved_at=?,msg_sent_at=? WHERE id=?",
                    (status,approved,exit_time,pid))
    else:
        cur.execute("UPDATE permissions SET status=?,approved_at=? WHERE id=?",
                    (status,approved,pid))
    con.commit(); con.close()

def query_permissions(date_filter=None, status=None):
    client = get_cloud_client()
    if client.is_active():
        res = client.get("/web/api/permissions", params={"date": date_filter, "status": status})
        return res.get("rows", []) if res.get("ok") else []

    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q,p = "SELECT * FROM permissions WHERE 1=1", []
    if date_filter: q += " AND date=?";   p.append(date_filter)
    if status:      q += " AND status=?"; p.append(status)
    cur.execute(q+" ORDER BY created_at DESC", p)
    rows = [dict(r) for r in cur.fetchall()]; con.close()
    return rows

def delete_permission(pid):
    con = get_db(); cur = con.cursor()
    cur.execute("DELETE FROM permissions WHERE id=?", (pid,))
    con.commit(); con.close()

def send_permission_request(pid: int) -> tuple:
    """يرسل رسالة واتساب لولي الأمر يطلب موافقته — بدون جدولة."""
    _cfg = load_config()
    if not _cfg.get("permission_bot_enabled", True):
        return False, "بوت رسائل الاستئذان موقوف — فعّله من تبويب إدارة الواتساب."
    if not check_whatsapp_server_status():
        return False, "خادم واتساب غير متصل — شغّله أولاً"
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("SELECT * FROM permissions WHERE id=?", (pid,))
    row = dict(cur.fetchone() or {}); con.close()
    if not row: return False, "السجل غير موجود"
    phone = row.get("parent_phone","")
    if not phone: return False, "لا يوجد رقم جوال لولي الأمر"
    cfg    = load_config()
    school = cfg.get("school_name","المدرسة")
    msg = (
        "مدرسة {school}\n"
        "ولي أمر الطالب/ {name}\n\n"
        "يطلب ابنكم الاستئذان اليوم {date}\n"
        "السبب: {reason}\n\n"
        "للموافقة رد: موافق\n"
        "للرفض رد: رفض\n\n"
        "ادارة {school}"
    ).format(school=school, name=row["student_name"],
             date=row["date"], reason=row.get("reason","غير محدد"))
    student_data = {
        "permission_id": pid,
        "student_id":    row["student_id"],
        "student_name":  row["student_name"],
        "class_name":    row["class_name"],
        "type":          "permission",
    }
    ok, status = send_whatsapp_message(phone, msg, student_data=student_data)
    if ok:
        # حدّث وقت الإرسال + سجّل في pending
        con2 = get_db(); cur2 = con2.cursor()
        cur2.execute("UPDATE permissions SET msg_sent_at=? WHERE id=?",
                     (datetime.datetime.utcnow().isoformat(), pid))
        con2.commit(); con2.close()
        _save_pending_permission(phone, student_data)
    return ok, status

def _save_pending_permission(phone: str, data: dict):
    """يحفظ الطلب في pending_excuses.json للبوت."""
    import json as _j
    pf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "my-whatsapp-server","pending_excuses.json")
    try:
        pending = {}
        if os.path.exists(pf):
            with open(pf,encoding="utf-8") as f: pending = _j.load(f)
        digits = phone.replace("+","").replace(" ","")
        if digits.startswith("05") and len(digits)==10:
            digits = "966"+digits[1:]
        pending[digits] = {**data, "sent_at": datetime.datetime.utcnow().isoformat()}
        with open(pf,"w",encoding="utf-8") as f: _j.dump(pending,f,ensure_ascii=False,indent=2)
    except Exception as e:
        print("[PERM]", e)


# ═══════════════════════════════════════════════════════════════
# إعدادات المستلمين للتأخر
# ═══════════════════════════════════════════════════════════════

def get_tardiness_recipients():
    """يُرجع قائمة مستلمي رابط التأخر من الإعدادات."""
    cfg = load_config()
    return cfg.get("tardiness_recipients", [])

def save_tardiness_recipients(recipients):
    """يحفظ قائمة المستلمين في الإعدادات."""
    cfg = load_config()
    cfg["tardiness_recipients"] = recipients
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

