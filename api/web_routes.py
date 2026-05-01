# -*- coding: utf-8 -*-
"""
api/web_routes.py — مسارات لوحة التحكم الويب /web/*
"""
import datetime, json, base64, os, io, hashlib, hmac, re, sqlite3, subprocess, zipfile, urllib.request, threading
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response

from constants import (DB_PATH, DATA_DIR, HOST, PORT, TZ_OFFSET,
                       STATIC_DOMAIN, BASE_DIR, BACKUP_DIR,
                       STUDENTS_JSON, TEACHERS_JSON, CONFIG_JSON,
                       now_riyadh_date, CURRENT_USER, ROLES, ROLE_TABS,
                       APP_VERSION, INBOX_ATTACHMENTS_DIR, SCHOOL_REPORTS_DIR)
from config_manager import (load_config, save_config, get_terms,
                             logo_img_tag_from_config, render_message,
                             invalidate_config_cache)
import hashlib as _hl
_JWT_SECRET = "darb-web-" + _hl.sha256(b"DarbStu2025").hexdigest()[:16]
_JWT_EXPIRE = 8  # ساعات

from database import (get_db, load_students, load_teachers,
                      query_absences, query_tardiness, query_excuses,
                      insert_absences, insert_tardiness, delete_tardiness,
                      insert_excuse, delete_excuse,
                      create_backup, get_backup_list, get_all_users,
                      create_user, delete_user, toggle_user_active,
                      authenticate, hash_password, save_user_allowed_tabs,
                      delete_circular, get_user_allowed_tabs, get_user_info,
                      import_students_from_excel_sheet2_format,
                      import_teachers_from_excel,
                      create_student_referral, get_referrals_for_teacher,
                      get_all_referrals, get_referral_by_id,
                      update_referral_deputy, update_referral_counselor, close_referral,
                      create_academic_inquiry, get_academic_inquiries,
                      get_academic_inquiry, reply_academic_inquiry,
                      create_circular, get_circulars, mark_circular_as_read,
                      get_unread_circulars_count, delete_circular,
                      insert_counselor_session, get_counselor_sessions,
                      delete_counselor_session, insert_counselor_alert,
                      get_counselor_alerts, insert_behavioral_contract,
                      get_behavioral_contracts, delete_behavioral_contract,
                      delete_absence, delete_excuse, save_user_phone,
                      get_exempted_students, add_exempted_student, remove_exempted_student,
                      add_transferred_student,
                      update_user_password,
                      send_inbox_message, get_inbox_messages, get_sent_messages,
                      get_inbox_unread_count, mark_inbox_message_read, delete_inbox_message,
                      upload_backup_telegram)
from whatsapp_service import (send_whatsapp_message, send_whatsapp_pdf,
                               check_whatsapp_server_status)
from alerts_service import (log_message_status, run_smart_alerts,
                             build_daily_summary_message, send_daily_report_to_admin,
                             get_students_exceeding_threshold, get_student_full_analysis,
                             get_top_absent_students, get_student_absence_count,
                             get_tardiness_recipients, save_tardiness_recipients,
                             query_permissions, insert_permission,
                             update_permission_status, load_schedule, save_schedule,
                             send_permission_request, build_absent_groups,
                             delete_permission, query_today_messages,
                             get_week_comparison, get_absence_by_day_of_week)
from report_builder import (generate_daily_report, generate_monthly_report,
                             generate_weekly_report, export_to_noor_excel,
                             build_daily_report_df, get_live_monitor_status,
                             compute_today_metrics, detect_suspicious_patterns,
                             query_absences_in_range)
from pdf_generator import (generate_session_pdf, generate_behavioral_contract_pdf,
                            _render_pdf_page_as_png, save_results_to_db,
                            parse_results_pdf, get_student_result)
from config_manager import get_message_template

try:
    from gui.tabs.teacher_forms_tab import _make_lesson_pdf as generate_lesson_pdf, _make_program_pdf as generate_program_pdf
except ImportError:
    generate_lesson_pdf = lambda d: b""
    generate_program_pdf = lambda d: b""
from grade_analysis import _ga_parse_file, _ga_build_html

router = APIRouter()

def _create_token(username: str, role: str, full_name: str = "") -> str:
    import jwt as _jwt, datetime as _dt
    payload = {
        "sub":  username,
        "role": role,
        "full_name": full_name,
        "exp":  _dt.datetime.utcnow() + _dt.timedelta(hours=_JWT_EXPIRE)
    }
    return _jwt.encode(payload, _JWT_SECRET, algorithm="HS256")

def _verify_token(token: str) -> dict:
    import jwt as _jwt
    try:
        return _jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    except:
        return {}

def _get_current_user(request: Request) -> dict:
    token = request.cookies.get("darb_token","") or request.headers.get("Authorization","").replace("Bearer ","")
    if not token: return {}
    
    # 1. جرب التحقق من الـ Access Token الثابت (المستخدم في الربط السحابي)
    cfg = load_config()
    master_token = cfg.get("cloud_token")
    if master_token and token == master_token:
        return {"sub": "master_sync", "role": "admin", "username": "master_sync"}

    # 2. جرب التحقق من الـ JWT العادي (المستخدم في لوحة الويب)
    data = _verify_token(token)
    if data:
        data["username"] = data.get("sub", "")
    return data


# ─── Login API ───────────────────────────────────────────────

@router.get("/web/dashboard.js")
async def web_dashboard_js(request: Request):
    """يخدم JavaScript الـ dashboard كملف خارجي لتجنب CSP."""
    user = _get_current_user(request)
    # نعطي الـ JS لأي زائر (الحماية في الـ API نفسها)
    js = _get_dashboard_js()
    from starlette.responses import Response
    return Response(
        content=js,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Content-Security-Policy": "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
        }
    )

@router.get("/web", response_class=HTMLResponse)
async def web_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/web/dashboard")

@router.get("/web/login", response_class=HTMLResponse)
async def web_login_page():
    return HTMLResponse(_web_login_html())

@router.post("/web/api/login", response_class=JSONResponse)
async def web_login(req: Request):
    try:
        data = await req.json()
        user = authenticate(data.get("username",""), data.get("password",""))
        if not user:
            return JSONResponse({"ok": False, "msg": "اسم المستخدم أو كلمة المرور غير صحيحة"})
        token        = _create_token(user["username"], user["role"], user.get("full_name", ""))
        allowed_tabs = get_user_allowed_tabs(user["username"])
        resp  = JSONResponse({"ok": True, "role": user["role"],
                               "name": user.get("full_name") or user["username"],
                               "allowed_tabs": allowed_tabs})
        resp.set_cookie("darb_token", token, httponly=True,
                        max_age=_JWT_EXPIRE*3600, samesite="lax")
        return resp
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/logout")
async def web_logout():
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse("/web/login")
    resp.delete_cookie("darb_token")
    return resp

@router.get("/web/dashboard", response_class=HTMLResponse)
async def web_dashboard(request: Request):
    user = _get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/web/login")
    allowed = get_user_allowed_tabs(user["sub"])
    html    = _web_dashboard_html(user["sub"], user["role"], allowed)
    return HTMLResponse(
        content=html,
        headers={
            "Content-Security-Policy":
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline';",
            "X-Content-Security-Policy":
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline';",
        }
    )


# ─── API Endpoints للواجهة الويب ─────────────────────────────
@router.get("/web/api/dashboard-data", response_class=JSONResponse)
async def web_dashboard_data(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        d       = date or now_riyadh_date()
        metrics = compute_today_metrics(d)
        # أضف إحصاء التأخر
        tard = query_tardiness(date_filter=d)
        metrics["totals"]["tardiness"] = len(tard)
        return JSONResponse({"ok": True, "date": d, "metrics": metrics})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/sync-info", response_class=JSONResponse)
async def api_sync_info(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM absences")
        abs_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tardiness")
        tard_count = cur.fetchone()[0]
        con.close()
        return JSONResponse({
            "ok": True,
            "last_sync": now_riyadh_date(),
            "total_records": abs_count + tard_count,
            "absences": abs_count,
            "tardiness": tard_count,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# --- Analytics Endpoints ---

@router.get("/web/api/analytics/dashboard", response_class=JSONResponse)
async def api_analytics_dashboard(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "Unauthenticated"}, status_code=401)
    try:
        d = date or now_riyadh_date()
        metrics = compute_today_metrics(d)
        weekly = get_week_comparison()
        tard = query_tardiness(date_filter=d)
        metrics["totals"]["tardiness"] = len(tard)
        return JSONResponse({
            "ok": True,
            "metrics": metrics,
            "weekly": weekly
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/analytics/weekly-comparison", response_class=JSONResponse)
async def api_weekly_comparison(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        return JSONResponse({"ok": True, "data": get_week_comparison()})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/analytics/top-absent", response_class=JSONResponse)
async def api_top_absent(request: Request, month: str = None, limit: int = 10):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        rows = get_top_absent_students(month=month, limit=limit)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/analytics/absence-by-dow", response_class=JSONResponse)
async def api_absence_by_dow(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = get_absence_by_day_of_week()
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/student-analytics/{student_id}", response_class=JSONResponse)
async def api_student_analytics(request: Request, student_id: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_student_analytics_data
        data = get_student_analytics_data(student_id)
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# ─── ADMIN POINTS MANAGEMENT API ───────────────────────────────────

@router.get("/web/api/admin/points-logs", response_class=JSONResponse)
async def api_admin_points_logs(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_admin_points_logs
        logs = get_admin_points_logs(limit=500)
        return JSONResponse({"ok": True, "logs": logs})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/admin/points-usage", response_class=JSONResponse)
async def api_admin_points_usage(request: Request, month: str):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_teachers_points_usage
        usage = get_teachers_points_usage(month)
        return JSONResponse({"ok": True, "usage": usage})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/admin/points-settings", response_class=JSONResponse)
async def api_admin_points_settings(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await request.json()
        limit = int(data.get("limit", 100))
        from config_manager import load_config, save_config
        cfg = load_config()
        cfg["monthly_points_limit"] = limit
        save_config(cfg)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/admin/points-delete/{record_id}", response_class=JSONResponse)
async def api_admin_points_delete(request: Request, record_id: int):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import delete_points_record
        delete_points_record(record_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/admin/points-adjust", response_class=JSONResponse)
async def api_admin_points_adjust(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await request.json()
        uname = data.get("username")
        pts = int(data.get("points", 0))
        reason = data.get("reason", "")
        month = data.get("month") or datetime.date.today().isoformat()[:7]
        if not uname: return JSONResponse({"ok": False, "msg": "اختر مستخدماً"})
        
        from database import add_teacher_points_adjustment
        add_teacher_points_adjustment(uname, pts, reason, month)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/absences", response_class=JSONResponse)
async def web_absences(request: Request, date: str = None, class_id: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    date    = date or now_riyadh_date()
    filters = {"date_filter": date}
    if class_id: filters["class_id_filter"] = class_id
    rows    = query_absences(**filters)
    return JSONResponse({"ok": True, "rows": rows, "count": len(rows)})

@router.get("/web/api/tardiness", response_class=JSONResponse)
async def web_tardiness(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    rows = query_tardiness(date_filter=date or now_riyadh_date())
    return JSONResponse({"ok": True, "rows": rows})

@router.get("/web/api/excuses", response_class=JSONResponse)
async def web_excuses(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    rows = query_excuses(date_filter=date or now_riyadh_date())
    return JSONResponse({"ok": True, "rows": rows})

@router.post("/web/api/add-excuse", response_class=JSONResponse)
async def web_add_excuse(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        insert_excuse(
            data["date"], data["student_id"], data["student_name"],
            data.get("class_id",""), data.get("class_name",""),
            data["reason"], source="web", approved_by=user["sub"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/send-absence-messages", response_class=JSONResponse)
async def web_send_absence_messages(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data     = await req.json()
        date_str = data.get("date", now_riyadh_date())
        students = data.get("students", [])
        if not students:
            return JSONResponse({"ok": False, "msg": "لا يوجد طلاب"})

        cfg      = load_config()
        school   = cfg.get("school_name", "المدرسة")
        template = get_message_template()
        store    = load_students()

        # ابنِ خريطة الطلاب للحصول على أرقام أولياء الأمور
        phone_map = {}
        for cls in store["list"]:
            for s in cls["students"]:
                phone_map[s["id"]] = s.get("phone", "")

        import random, asyncio
        sent = failed = 0
        for i, stu in enumerate(students):
            # تأخير عشوائي بين الرسائل (إلا الأولى)
            if i > 0:
                await asyncio.sleep(random.uniform(7, 15))
            
            sid   = str(stu.get("student_id", ""))
            sname = stu.get("student_name", "")
            cname = stu.get("class_name", "")
            phone = phone_map.get(sid, "")
            if not phone:
                failed += 1; continue

            msg = template.format(
                school_name=school,
                student_name=sname,
                class_name=cname,
                date=date_str)

            ok, _ = send_whatsapp_message(phone, msg, student_data={
                "student_id": sid, "student_name": sname,
                "class_name": cname, "date": date_str}, humanize=True)
            if ok: sent += 1
            else:  failed += 1

        return JSONResponse({"ok": True, "sent": sent, "failed": failed})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/send-save-number", response_class=JSONResponse)
async def web_send_save_number(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "للمدير والوكيل فقط"}, status_code=403)
    try:
        data     = await req.json()
        class_id = data.get("class_id", "")
        cfg      = load_config()
        school   = cfg.get("school_name", "المدرسة")
        store    = load_students()

        import random, asyncio
        sent = failed = skipped = 0
        seen_phones = set()

        public_url = cfg.get("public_url", cfg.get("cloud_url", "")).rstrip("/")
        vcard_link = f"{public_url}/web/save-contact" if public_url else ""
        vcard_line = f"\n📲 أو اضغط هنا لحفظ الرقم مباشرةً:\n{vcard_link}" if vcard_link else ""

        msg_template = (
            "السلام عليكم ورحمة الله وبركاته\n\n"
            "ولي الأمر الكريم،\n\n"
            "تهديكم إدارة {school} أطيب التحيات وأزكاها.\n\n"
            "يسعدنا إعلامكم بأن هذا الرقم هو الرقم الرسمي للمدرسة المخصص للتواصل مع أولياء الأمور، "
            "وسيُستخدم لإبلاغكم بكل ما يخص أبنائكم من غياب أو تأخر أو أخبار مهمة.\n\n"
            "🔖 نرجو منكم حفظ هذا الرقم باسم:\n"
            "({school})"
            "{vcard_line}\n\n"
            "وذلك لضمان وصول الرسائل إليكم دون انقطاع.\n\n"
            "شاكرين تعاونكم وحرصكم،\n"
            "إدارة {school}"
        )

        for cls in store["list"]:
            if class_id and cls.get("id") != class_id:
                continue
            for s in cls["students"]:
                phone = s.get("phone", "").strip()
                if not phone or phone in seen_phones:
                    skipped += 1; continue
                seen_phones.add(phone)
                if sent > 0:
                    await asyncio.sleep(random.uniform(8, 18))
                msg = msg_template.format(school=school, vcard_line=vcard_line)
                ok, _ = send_whatsapp_message(phone, msg)
                if ok: sent += 1
                else:  failed += 1

        return JSONResponse({"ok": True, "sent": sent, "failed": failed, "skipped": skipped})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/save-contact")
async def web_save_contact():
    cfg    = load_config()
    school = cfg.get("school_name", "المدرسة")
    phone  = cfg.get("wa_phone", "").strip()
    if not phone:
        return Response("رقم المدرسة غير مُعيَّن في الإعدادات", media_type="text/plain; charset=utf-8", status_code=404)
    vcard = (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"FN:{school}\r\n"
        f"ORG:{school}\r\n"
        f"TEL;TYPE=CELL:{phone}\r\n"
        "END:VCARD\r\n"
    )
    return Response(
        content=vcard.encode("utf-8"),
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="school.vcf"'}
    )


@router.get("/web/api/save-number-preview", response_class=JSONResponse)
async def web_save_number_preview(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    cfg        = load_config()
    school     = cfg.get("school_name", "المدرسة")
    public_url = cfg.get("public_url", cfg.get("cloud_url", "")).rstrip("/")
    vcard_line = f"\n📲 أو اضغط هنا لحفظ الرقم مباشرةً:\n{public_url}/web/save-contact" if public_url else ""
    msg = (
        "السلام عليكم ورحمة الله وبركاته\n\n"
        "ولي الأمر الكريم،\n\n"
        f"تهديكم إدارة {school} أطيب التحيات وأزكاها.\n\n"
        "يسعدنا إعلامكم بأن هذا الرقم هو الرقم الرسمي للمدرسة المخصص للتواصل مع أولياء الأمور، "
        "وسيُستخدم لإبلاغكم بكل ما يخص أبنائكم من غياب أو تأخر أو أخبار مهمة.\n\n"
        "🔖 نرجو منكم حفظ هذا الرقم باسم:\n"
        f"({school})"
        f"{vcard_line}\n\n"
        "وذلك لضمان وصول الرسائل إليكم دون انقطاع.\n\n"
        "شاكرين تعاونكم وحرصكم،\n"
        f"إدارة {school}"
    )
    return JSONResponse({"ok": True, "msg": msg})


@router.post("/web/api/send-tardiness-messages", response_class=JSONResponse)
async def web_send_tardiness_messages(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data     = await req.json()
        date_str = data.get("date", now_riyadh_date())
        students = data.get("students", [])
        if not students:
            return JSONResponse({"ok": False, "msg": "لا يوجد طلاب"})

        cfg      = load_config()
        school   = cfg.get("school_name", "المدرسة")
        template = cfg.get("tardiness_message_template",
                           "تنبيه تأخر: {student_name} تأخر {minutes_late} دقيقة بتاريخ {date}")
        store    = load_students()

        phone_map = {}
        for cls in store["list"]:
            for s in cls["students"]:
                phone_map[s["id"]] = s.get("phone", "")

        import random, asyncio
        sent = failed = 0
        for i, stu in enumerate(students):
            if i > 0:
                await asyncio.sleep(random.uniform(7, 15))
                
            sid   = str(stu.get("student_id", ""))
            sname = stu.get("student_name", "")
            cname = stu.get("class_name", "")
            mins  = stu.get("minutes_late", 0)
            phone = phone_map.get(sid, "")
            if not phone:
                failed += 1; continue

            msg = template.format(
                school_name=school,
                student_name=sname,
                class_name=cname,
                date=date_str,
                minutes_late=mins)

            ok, _ = send_whatsapp_message(phone, msg, humanize=True)
            if ok: sent += 1
            else:  failed += 1

        return JSONResponse({"ok": True, "sent": sent, "failed": failed})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/add-permission", response_class=JSONResponse)
async def web_add_permission(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data    = await req.json()
        send_wa = data.get("send_wa", True)
        pid = insert_permission(
            data["date"], data["student_id"], data["student_name"],
            data.get("class_id",""), data.get("class_name",""),
            data.get("parent_phone",""), data.get("reason",""),
            user["sub"])
        msg = "تم تسجيل طلب الاستئذان"
        if send_wa and data.get("parent_phone"):
            ok, status = send_permission_request(pid)
            msg = "✅ تم التسجيل وإرسال واتساب" if ok else "تم التسجيل — فشل إرسال واتساب: "+status
        return JSONResponse({"ok": True, "msg": msg, "id": pid})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/update-permission", response_class=JSONResponse)
async def web_update_permission(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        pid = int(data.get("id", 0))
        update_permission_status(pid, data.get("status", "approved"), user["sub"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/academic-inquiry/{inq_id}", response_class=JSONResponse)
async def web_get_academic_inquiry_detail(inq_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        row = get_academic_inquiry(inq_id)
        return JSONResponse({"ok": True, "row": row})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/daily-report", response_class=JSONResponse)
async def web_daily_report(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        d       = date or now_riyadh_date()
        report  = build_daily_summary_message(d)
        return JSONResponse({"ok": True, "report": report, "date": d})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/send-daily-report", response_class=JSONResponse)
async def web_send_daily_report(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data    = await req.json()
        date_str = data.get("date", now_riyadh_date())
        ok, msg = send_daily_report_to_admin(date_str)
        return JSONResponse({"ok": ok, "msg": msg})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/students", response_class=JSONResponse)
async def web_students(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    store = load_students()
    return JSONResponse({"ok": True, "classes": store["list"]})

@router.post("/web/api/update-students", response_class=JSONResponse)
async def web_update_students(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        classes = data.get("classes")
        if classes is None:
            return JSONResponse({"ok": False, "msg": "بيانات مفقودة"})
        if not classes:
            return JSONResponse({"ok": False, "msg": "لا يمكن حفظ قائمة فصول فارغة"})

        from constants import STUDENTS_JSON, ensure_dirs
        import json, os as _os
        ensure_dirs()
        _tmp = STUDENTS_JSON + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
        _os.replace(_tmp, STUDENTS_JSON)

        # تحديث المتجر في الذاكرة أيضاً للسيرفر
        import constants
        constants.STUDENTS_STORE = {"list": classes, "by_id": {c["id"]: c for c in classes}}

        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/classes", response_class=JSONResponse)
async def web_classes(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    store   = load_students()
    classes = [{"id": c["id"], "name": c["name"],
                "count": len(c["students"])} for c in store["list"]]
    return JSONResponse({"ok": True, "classes": classes})

@router.get("/web/api/class-students/{class_id}", response_class=JSONResponse)
async def web_class_students(class_id: str, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    
    from database import get_exempted_students
    exempted_ids = {str(e["student_id"]) for e in get_exempted_students()}
    
    store = load_students()
    cls   = next((c for c in store["list"] if c["id"] == class_id), None)
    if not cls: return JSONResponse({"ok": False, "msg": "فصل غير موجود"})
    
    filtered_students = [s for s in cls["students"] if str(s["id"]) not in exempted_ids]
    return JSONResponse({"ok": True, "students": filtered_students, "name": cls["name"]})



@router.post("/web/api/add-absence", response_class=JSONResponse)
async def web_add_absence(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        students = data["students"]
        insert_absences(
            data["date"], data["class_id"], data["class_name"],
            students, None, user["sub"], int(data.get("period", 0)))
        return JSONResponse({"ok": True, "count": len(students)})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/add-tardiness", response_class=JSONResponse)
async def web_add_tardiness(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        insert_tardiness(
            data["date"], data.get("class_id",""), data.get("class_name",""),
            data["student_id"], data["student_name"],
            user["sub"], int(data.get("period", 1)), int(data.get("minutes_late", 5)))
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/stats-monthly", response_class=JSONResponse)
async def web_stats_monthly(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    cur.execute("""SELECT substr(date,1,7) as month,
                          COUNT(DISTINCT date) as school_days,
                          COUNT(*) as total_abs,
                          COUNT(DISTINCT student_id) as unique_students
                   FROM absences 
                   WHERE student_id NOT IN (SELECT student_id FROM exempted_students)
                   GROUP BY month ORDER BY month DESC LIMIT 6""")
    rows = [dict(r) for r in cur.fetchall()]; con.close()
    return JSONResponse({"ok": True, "rows": rows})

@router.get("/web/api/alerts-students", response_class=JSONResponse)
async def web_alerts_students(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        cfg = load_config()
        threshold = cfg.get("alert_absence_threshold", 5)
        import datetime as _dt
        month = _dt.datetime.now().strftime("%Y-%m")
        rows  = get_students_exceeding_threshold(threshold, month)
        return JSONResponse({"ok": True, "rows": rows, "threshold": threshold})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/student-analysis/{student_id}", response_class=JSONResponse)
async def web_student_analysis(student_id: str, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = get_student_full_analysis(student_id)
        data.pop("monthly", None); data.pop("dow_count", None)
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/top-absent", response_class=JSONResponse)
async def web_top_absent(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    import datetime as _dt
    month = _dt.datetime.now().strftime("%Y-%m")
    rows  = get_top_absent_students(month=month, limit=20)
    return JSONResponse({"ok": True, "rows": rows})

@router.post("/web/api/students/mark-transferred", response_class=JSONResponse)
async def web_mark_transferred(req: Request):
    user = _get_current_user(req)
    if not user or user.get("role") not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    data = await req.json()
    sid  = str(data.get("student_id", "")).strip()
    name = str(data.get("student_name", "")).strip()
    if not sid:
        return JSONResponse({"ok": False, "msg": "student_id مطلوب"})
    add_transferred_student(sid, name)
    return JSONResponse({"ok": True})

@router.get("/web/api/permissions", response_class=JSONResponse)
async def web_permissions(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    rows = query_permissions(date_filter=date or now_riyadh_date())
    return JSONResponse({"ok": True, "rows": rows})

@router.get("/web/api/me", response_class=JSONResponse)
async def web_me(request: Request):
    try:
        user = _get_current_user(request)
        if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
        cfg    = load_config()
        gender = cfg.get("school_gender", "boys")
        school = cfg.get("school_name", "المدرسة")
        user_info = get_user_info(user["sub"])
        full_name = user_info.get("full_name") if user_info and user_info.get("full_name") else user["sub"]
        
        return JSONResponse({
            "ok":      True,
            "username": user["sub"],
            "name":     full_name,
            "role":     user["role"],
            "school":   school,
            "gender":   gender,
            "is_girls": gender == "girls",
        })
    except Exception as e:
        print(f"[API-ME-ERROR] {e}")
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/teachers", response_class=JSONResponse)
async def web_get_teachers(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        # نعيد بيانات المعلمين من ملف teachers.json وليس فقط المستخدمين
        data = load_teachers()
        return JSONResponse({"ok": True, "teachers": data.get("teachers", [])})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/sync/users", response_class=JSONResponse)
async def web_sync_users(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        users = get_all_users()
        # تحويل كائنات sqlite3.Row إلى dict لضمان إمكانية تحويلها لـ JSON
        users_list = [dict(u) if not isinstance(u, dict) else u for u in users]
        return JSONResponse({"ok": True, "users": users_list})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/create-academic-inquiry", response_class=JSONResponse)
async def web_create_academic_inquiry(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        inq_id = create_academic_inquiry(data)
        return JSONResponse({"ok": True, "id": inq_id})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# ─── New Sync Endpoints (Batch 1: Counselor & Deletions) ───────

@router.delete("/web/api/absences/{rec_id}", response_class=JSONResponse)
async def api_delete_absence(rec_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "Unauthorized"}, status_code=401)
    try:
        delete_absence(rec_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/tardiness/{rec_id}", response_class=JSONResponse)
async def api_delete_tardiness(rec_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "Unauthorized"}, status_code=401)
    try:
        delete_tardiness(rec_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/excuses/{rec_id}", response_class=JSONResponse)
async def api_delete_excuse(rec_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "Unauthorized"}, status_code=401)
    try:
        delete_excuse(rec_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/circulars/{circ_id}", response_class=JSONResponse)
async def api_delete_circular_sync(circ_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False, "msg": "Admin only"}, status_code=401)
    try:
        delete_circular(circ_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/permissions/{perm_id}", response_class=JSONResponse)
async def api_delete_permission_sync(perm_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "Unauthorized"}, status_code=401)
    try:
        delete_permission(perm_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# --- Counselor API ---

@router.post("/web/api/counselor/session/create", response_class=JSONResponse)
async def api_create_session(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        sid = insert_counselor_session(data)
        return JSONResponse({"ok": True, "id": sid})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/counselor/sessions", response_class=JSONResponse)
async def api_get_sessions(request: Request, student_id: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        rows = get_counselor_sessions(student_id)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/counselor/session/{sess_id}", response_class=JSONResponse)
async def api_delete_session(sess_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        delete_counselor_session(sess_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/counselor/alert/create", response_class=JSONResponse)
async def api_create_counselor_alert(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        aid = insert_counselor_alert(data)
        return JSONResponse({"ok": True, "id": aid})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/counselor/alerts", response_class=JSONResponse)
async def api_get_counselor_alerts(request: Request, student_id: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        rows = get_counselor_alerts(student_id)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/counselor/contract/create", response_class=JSONResponse)
async def api_create_contract(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        cid = insert_behavioral_contract(data)
        return JSONResponse({"ok": True, "id": cid})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/counselor/contracts", response_class=JSONResponse)
async def api_get_contracts(request: Request, student_id: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        rows = get_behavioral_contracts(student_id)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# --- Exempted Students API ---

@router.get("/web/api/exempted-students", response_class=JSONResponse)
async def api_get_exempted_students(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        rows = get_exempted_students()
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/exempted-students/add", response_class=JSONResponse)
async def api_add_exempted_student(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "Unauthorized"}, status_code=401)
    try:
        data = await req.json()
        add_exempted_student(
            data["student_id"], data["student_name"],
            data.get("class_id", ""), data.get("class_name", ""),
            data.get("reason", ""), user["sub"]
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/exempted-students/{student_id}", response_class=JSONResponse)
async def api_remove_exempted_student(student_id: str, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "Unauthorized"}, status_code=401)
    try:
        remove_exempted_student(student_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/counselor/contract/{cid}", response_class=JSONResponse)
async def api_delete_contract(cid: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        delete_behavioral_contract(cid)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/academic-inquiries", response_class=JSONResponse)
async def web_get_academic_inquiries(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        is_teacher = user["role"] == "teacher"
        rows = get_academic_inquiries(teacher_username=user["sub"] if is_teacher else None)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/reply-academic-inquiry", response_class=JSONResponse)
async def web_reply_academic_inquiry(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "teacher": 
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        inq_id = int(data.get("id", 0))
        if inq_id <= 0: return JSONResponse({"ok": False, "msg": "معرف الخطاب غير صالح"})
        reply_academic_inquiry(inq_id, data)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/referrals/create", response_class=JSONResponse)
async def web_referral_create(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        ref_id = create_student_referral(data)
        return JSONResponse({"ok": True, "id": ref_id})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/referrals/teacher", response_class=JSONResponse)
async def web_referral_teacher(request: Request, username: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        rows = get_referrals_for_teacher(username)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/referrals/all", response_class=JSONResponse)
async def web_referral_all(request: Request, status: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        rows = get_all_referrals(status_filter=status)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/referrals/detail/{ref_id}", response_class=JSONResponse)
async def web_referral_detail(ref_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        row = get_referral_by_id(ref_id)
        return JSONResponse({"ok": True, "row": row})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/referrals/update-deputy", response_class=JSONResponse)
async def web_referral_update_deputy(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        ref_id = int(data.get("id", 0))
        update_referral_deputy(ref_id, data)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/referrals/update-counselor", response_class=JSONResponse)
async def web_referral_update_counselor_api(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "counselor"):
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        ref_id = int(data.get("id", 0))
        update_referral_counselor(ref_id, data)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/referrals/close", response_class=JSONResponse)
async def web_referral_close(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        close_referral(int(data.get("id", 0)))
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# ─── التعاميم الرسمية (Circulars) ───────────────────────────

@router.post("/web/api/circulars/create", response_class=JSONResponse)
async def web_create_circular(
    request: Request,
    title: str = Form(...),
    content: str = Form(""),
    target_role: str = Form("all"),
    file: UploadFile = File(None)
):
    user = _get_current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"error": "غير مصرح للمدير فقط"}, status_code=401)
    
    try:
        attachment_path = ""
        if file:
            circ_dir = os.path.join(DATA_DIR, "attachments", "circulars")
            os.makedirs(circ_dir, exist_ok=True)
            # توليد اسم فريد للملف
            fext = os.path.splitext(file.filename)[1]
            fname = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(file.filename) % 10000}{fext}"
            fpath = os.path.join(circ_dir, fname)
            with open(fpath, "wb") as f:
                f.write(await file.read())
            attachment_path = os.path.join("attachments", "circulars", fname)
        
        data = {
            "title": title,
            "content": content,
            "target_role": target_role,
            "attachment_path": attachment_path,
            "created_by": user["sub"],
            "date": now_riyadh_date()
        }
        cid = create_circular(data)
        
        # إرسال تنبيهات واتساب اختيارية
        cfg = load_config()
        if cfg.get("whatsapp_circular_alerts", True):
            threading.Thread(target=lambda: _send_circular_wa_alerts(data), daemon=True).start()
            
        return JSONResponse({"ok": True, "id": cid})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

def _send_circular_wa_alerts(circ_data):
    """إرسال تنبيهات واتساب للمعلمين عند صدور تعميم."""
    try:
        from database import get_all_users
        users = get_all_users()
        target = circ_data.get("target_role", "all")
        msg = f"🔔 *تعميم جديد من إدارة المدرسة*\n\n*العنوان:* {circ_data['title']}\n\nيرجى فتح التطبيق للاطلاع على التفاصيل."
        
        for u in users:
            if not u.get("active"): continue
            if target != "all" and u["role"] != target: continue
            if u["role"] == "admin": continue # لا نرسل للمرسل
            
            phone = u.get("phone")
            if phone:
                send_whatsapp_message(phone, msg)
    except Exception as e:
        print("[Circular-WA-Error]", e)


# ─── User Management Sync API ─────────────────────────────

@router.post("/web/api/users/create", response_class=JSONResponse)
async def api_create_user(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False, "msg": "Admin only"}, status_code=401)
    try:
        data = await req.json()
        ok, msg = create_user(data["username"], data["password"], data["role"], data.get("full_name",""))
        return JSONResponse({"ok": ok, "msg": msg})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/users/update-password", response_class=JSONResponse)
async def api_update_password(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        update_user_password(data["username"], data["password"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/users/toggle-active", response_class=JSONResponse)
async def api_toggle_active(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        toggle_user_active(data["user_id"], data["active"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/users/{user_id}", response_class=JSONResponse)
async def api_delete_user(user_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False}, status_code=401)
    try:
        delete_user(user_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/users/phone", response_class=JSONResponse)
async def api_user_phone(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        save_user_phone(data["username"], data["phone"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/users/allowed-tabs", response_class=JSONResponse)
async def api_user_allowed_tabs(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        save_user_allowed_tabs(data["username"], data["tabs"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/users/deputy-phones", response_class=JSONResponse)
async def api_deputy_phones(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_deputy_phones
        phones = get_deputy_phones()
        return JSONResponse({"ok": True, "phones": phones})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# --- Schedule & Logs API ---

@router.post("/web/api/schedule/save", response_class=JSONResponse)
async def api_save_schedule(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        save_schedule(data["day_of_week"], data["schedule"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/schedule", response_class=JSONResponse)
async def api_get_schedule(request: Request, day_of_week: int):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        # load_schedule returns dict{(cid,period): name}, we need rows for JSON
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("SELECT class_id, period, teacher_name FROM schedule WHERE day_of_week = ?", (day_of_week,))
        rows = [dict(r) for r in cur.fetchall()]; con.close()
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# ─── Points & Leaderboard API ────────────────────────────────

@router.get("/web/api/leaderboard", response_class=JSONResponse)
async def api_get_leaderboard(request: Request, limit: int = 20):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_points_leaderboard
        rows = get_points_leaderboard(limit)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/points/add", response_class=JSONResponse)
async def api_add_points(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy", "teacher", "supervisor", "staff", "lab", "guard", "counselor", "activity_leader"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        from database import add_student_points
        author_id = user.get("username") or user.get("sub") or "admin"
        author_name = user.get("full_name")
        
        if not author_name:
            # محاولة جلب الاسم من قاعدة البيانات لضمان الظهور في السجلات
            try:
                from database import get_db
                con = get_db(); cur = con.cursor()
                cur.execute("SELECT full_name FROM users WHERE username = ?", (author_id,))
                row = cur.fetchone()
                if row and row[0]: author_name = row[0]
                con.close()
            except: pass
        
        if not author_name: author_name = author_id

        add_student_points(
            data["student_id"], data["points"], data.get("reason",""),
            author_id=author_id, author_name=author_name
        )
        
        # تحقق من منح شهادة تميز آلياً
        from alerts_service import check_and_award_certificate
        awarded, level = check_and_award_certificate(data["student_id"], data.get("student_name", "الطالب"))
        
        return JSONResponse({"ok": True, "awarded": awarded, "level": level})
    except ValueError as ve:
        return JSONResponse({"ok": False, "msg": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/points-summary", response_class=JSONResponse)
async def api_points_summary(request: Request, date: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_points_awarded_on_date
        total = get_points_awarded_on_date(date)
        return JSONResponse({"ok": True, "total": total})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/student-analysis/{student_id}", response_class=JSONResponse)
async def api_student_analysis(student_id: str, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_student_analytics_data
        data = get_student_analytics_data(student_id)
        # دمج الاسم والفصل من الـ STORE إذا لم يكن موجوداً (لضمان الدقة)
        from database import load_students
        store = load_students()
        for cls in store.get("list", []):
            for s in cls.get("students", []):
                if s["id"] == student_id:
                    data["name"] = s["name"]
                    data["class_name"] = cls["name"]
                    break
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/teacher-balance", response_class=JSONResponse)
async def api_teacher_balance(request: Request, username: str, month: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_teachers_points_usage
        rows = get_teachers_points_usage(month)
        teacher_data = next((r for r in rows if r["username"] == username), None)
        if teacher_data:
            consumed = teacher_data.get("consumed", teacher_data.get("used", 0))
            total_limit = teacher_data.get("total_limit", teacher_data.get("limit", 100))
            extra = teacher_data.get("extra", 0)
            remaining = teacher_data.get("remaining", max(0, total_limit - consumed))
            return JSONResponse({
                "ok": True,
                "balance": consumed,
                "limit": total_limit,
                "remaining": remaining,
                "extra": extra
            })
        
        from config_manager import load_config
        cfg = load_config()
        limit = cfg.get("monthly_points_limit", 100)
        return JSONResponse({"ok": True, "balance": 0, "limit": limit, "remaining": limit, "extra": 0})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/admin/points-logs", response_class=JSONResponse)
async def api_admin_points_logs(request: Request, limit: int = 500):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "صلاحيات غير كافية"}, status_code=403)
    try:
        from database import get_admin_points_logs
        rows = get_admin_points_logs(limit)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/admin/teachers-usage", response_class=JSONResponse)
async def api_admin_teachers_usage(request: Request, month: str = None):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "صلاحيات غير كافية"}, status_code=403)
    try:
        if not month: month = datetime.date.today().isoformat()[:7]
        from database import get_teachers_points_usage
        rows = get_teachers_points_usage(month)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/admin/points-settings", response_class=JSONResponse)
async def api_admin_points_settings(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "صلاحيات غير كافية"}, status_code=403)
    try:
        data = await request.json()
        new_limit = int(data.get("limit", 100))
        from config_manager import load_config, save_config
        cfg = load_config()
        cfg["monthly_points_limit"] = new_limit
        save_config(cfg)
        return JSONResponse({"ok": True, "msg": "تم تحديث الإعدادات"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/admin/points-delete/{record_id}", response_class=JSONResponse)
async def api_admin_points_delete(record_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "صلاحيات غير كافية"}, status_code=403)
    try:
        from database import delete_points_record
        delete_points_record(record_id)
        return JSONResponse({"ok": True, "msg": "تم حذف السجل بنجاح"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/admin/points-adjust", response_class=JSONResponse)
async def api_admin_points_adjust(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "صلاحيات غير كافية"}, status_code=403)
    try:
        data = await request.json()
        target_username = data.get("username")
        points = int(data.get("points", 0))
        reason = data.get("reason", "")
        month = data.get("month") or datetime.date.today().isoformat()[:7]
        
        if not target_username or points <= 0:
            return JSONResponse({"ok": False, "msg": "بيانات غير مكتملة"})
        
        from database import add_teacher_points_adjustment
        add_teacher_points_adjustment(target_username, points, reason, month)
        return JSONResponse({"ok": True, "msg": "تمت زيادة الرصيد بنجاح"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)



@router.post("/web/api/messages-log/create", response_class=JSONResponse)
async def api_create_msg_log(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        log_message_status(
            data["date"], data["student_id"], data["student_name"],
            data["class_id"], data["class_name"], data["phone"],
            data["status"], data["template_used"], data.get("message_type", "absence")
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/messages-log", response_class=JSONResponse)
async def api_get_msg_log(request: Request, date: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        rows = query_today_messages(date)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/student-absence-count", response_class=JSONResponse)
async def api_student_abs_count(request: Request, student_id: str, month: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = get_student_absence_count(student_id, month)
        return JSONResponse({"ok": True, "data": data})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# ─── خدمة المرفقات (Static) ──────────────────────────────────
@router.get("/web/api/circulars/attachment/{filename}")
async def get_circular_attachment(filename: str):
    fpath = os.path.join(DATA_DIR, "attachments", "circulars", filename)
    if not os.path.exists(fpath):
        return Response(status_code=404)
    
    import mimetypes
    mtype, _ = mimetypes.guess_type(fpath)
    with open(fpath, "rb") as f:
        return Response(content=f.read(), media_type=mtype or "application/octet-stream")

# ═══════════════════════════════════════════════════════════════
# HTML صفحات الويب
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# HTML صفحات الويب — واجهة محسّنة بجميع التبويبات
# ═══════════════════════════════════════════════════════════════

def _get_dashboard_js() -> str:
    """JavaScript مدمج — لا يزال مستخدماً لـ /web/dashboard.js."""
    return "// legacy stub"


def _web_login_html() -> str:
    cfg    = load_config()
    school = cfg.get("school_name", "DarbStu")
    return (
        '<!DOCTYPE html><html lang="ar" dir="rtl"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>دخول — ' + school + '</title>'
        '<style>'
        'body{font-family:Tahoma,Arial,sans-serif;direction:rtl;background:linear-gradient(135deg,#1565C0,#0D47A1);'
        'min-height:100vh;display:flex;align-items:center;justify-content:center;margin:0}'
        '.card{background:#fff;border-radius:16px;padding:40px 36px;width:100%;max-width:400px;box-shadow:0 20px 60px rgba(0,0,0,.25)}'
        'h1{color:#1565C0;font-size:24px;text-align:center;margin:0 0 4px}'
        'p{color:#64748B;font-size:13px;text-align:center;margin:0 0 28px}'
        'label{display:block;color:#374151;font-size:13px;font-weight:700;margin-bottom:6px}'
        'input{width:100%;padding:11px 12px;border:2px solid #E0E7FF;border-radius:8px;'
        'font-size:15px;direction:rtl;outline:none;margin-bottom:16px;box-sizing:border-box}'
        'input:focus{border-color:#1565C0;box-shadow:0 0 0 3px rgba(21,101,192,.15)}'
        '.btn{width:100%;padding:13px;background:#1565C0;color:#fff;border:none;border-radius:8px;'
        'font-size:16px;font-weight:700;cursor:pointer;font-family:Tahoma,Arial}'
        '.btn:hover{background:#0D47A1}'
        '.err{background:#FEE2E2;color:#C62828;padding:10px;border-radius:6px;'
        'text-align:center;font-size:13px;margin-top:12px;display:none}'
        '</style></head><body>'
        '<div class="card">'
        '<h1>🏫 ' + school + '</h1>'
        '<p>DarbStu — نظام إدارة الغياب والتأخر</p>'
        '<label>اسم المستخدم</label>'
        '<input id="u" type="text" autofocus placeholder="username">'
        '<label>كلمة المرور</label>'
        '<input id="p" type="password" placeholder="••••••••">'
        '<button class="btn" onclick="login()">تسجيل الدخول</button>'
        '<div class="err" id="err"></div>'
        '</div>'
        '<script>'
        'document.getElementById("u").onkeydown=function(e){if(e.key==="Enter")document.getElementById("p").focus();};'
        'document.getElementById("p").onkeydown=function(e){if(e.key==="Enter")login();};'
        'async function login(){'
        'var u=document.getElementById("u").value.trim();'
        'var p=document.getElementById("p").value;'
        'if(!u||!p){showErr("ادخل الاسم وكلمة المرور");return;}'
        'var r=await fetch("/web/api/login",{method:"POST",headers:{"Content-Type":"application/json"},'
        'body:JSON.stringify({username:u,password:p})});'
        'var d=await r.json();'
        'if(d.ok)window.location.href="/web/dashboard";'
        'else showErr(d.msg||"خطأ في تسجيل الدخول");}'
        'function showErr(m){var e=document.getElementById("err");e.textContent=m;e.style.display="block";}'
        '</script>'
        '</body></html>'
    )


def _build_tabs_content() -> str:
    """stub — لم يعد مستخدماً، الواجهة الجديدة تُولَّد بالكامل في _web_dashboard_html."""
    return ""


def _web_dashboard_html(username: str, role: str, allowed_tabs) -> str:
    """يُنشئ صفحة الـ dashboard الكاملة بجميع التبويبات."""
    cfg    = load_config()
    school = cfg.get("school_name", "DarbStu")
    gender = cfg.get("school_gender", "boys")

    # جلب التنبيهات الذكية
    from database import get_unread_referrals_count, get_unread_circulars_count, get_unread_lab_submissions_count
    unread_referrals = 0
    if role in ("admin", "deputy", "supervisor", "counselor"):
        unread_referrals = get_unread_referrals_count()
    unread_circs = get_unread_circulars_count(username, role)
    unread_lab_submissions = get_unread_lab_submissions_count() if role == "admin" else 0
    unread_inbox = get_inbox_unread_count(username)

    # ── قائمة التبويبات مع مجموعاتها ──────────────────────────
    SIDEBAR_GROUPS = [
        ("الرئيسية", [
            ("لوحة المراقبة",      "dashboard",            "fas fa-chart-line"),
            ("المراقبة الحية",      "live_monitor",         "fas fa-satellite-dish"),
            ("روابط الفصول",        "links",                "fas fa-link"),
        ]),
        ("التسجيل اليومي", [
            ("تسجيل الغياب",        "reg_absence",          "fas fa-user-check"),
            ("تسجيل التأخر",        "reg_tardiness",        "fas fa-stopwatch"),
            ("طلب استئذان",         "new_permission",       "fas fa-bell"),
        ]),
        ("المتابعة الانضباطية", [
            ("سجل الغياب",              "absences",             "fas fa-history"),
            ("سجل التأخر",              "tardiness",            "fas fa-clock"),
            ("الأعذار",                 "excuses",              "fas fa-file-medical"),
            ("الاستئذان",               "permissions",          "fas fa-door-open"),
            ("إدارة الغياب",            "absence_mgmt",         "fas fa-users-cog"),
            ("هروب واستئذان",           "partial_absence",      "fas fa-running"),
            ("الموجّه الطلابي",         "counselor",            "fas fa-brain"),
            ("استلام تحويلات",          "referral_deputy",      "fas fa-inbox"),
            ("زيارات أولياء الأمور",   "parent_visits",        "fas fa-users"),
        ]),
        ("التقارير والإحصائيات", [
            ("التقارير / الطباعة",  "reports_print",        "fas fa-print"),
            ("تقرير الفصل",         "term_report",          "fas fa-file-alt"),
            ("تقرير الإدارة",       "admin_report",         "fas fa-user-tie"),
            ("تحليل طالب",          "student_analysis",     "fas fa-search"),
            ("أكثر الطلاب غياباً", "top_absent",           "fas fa-award"),
            ("الإشعارات الذكية",    "alerts",               "fas fa-exclamation-triangle"),
            ("تقارير المعلمين",     "teacher_reports_admin","fas fa-file-pdf"),
            ("تقارير المدرسة",      "school_reports",       "fas fa-folder-open"),
        ]),
        ("الرسائل والتواصل", [
            ("إرسال رسائل الغياب",  "send_absence",         "fas fa-envelope-open-text"),
            ("إرسال رسائل التأخر",  "send_tardiness",       "fas fa-paper-plane"),
            ("روابط بوابة أولياء الأمور", "portal_links",  "fas fa-user-shield"),
            ("التعاميم والنشرات",   "circulars",            "fas fa-scroll"),
            ("قصص المدرسة",         "school_stories",       "fas fa-camera-retro"),
            ("تعزيز الحضور الأسبوعي", "weekly_reward",      "fas fa-medal"),
            ("لوحة الصدارة (النقاط)", "leaderboard",        "fas fa-trophy"),
            ("إدارة النقاط (إداري)",  "points_control",     "fas fa-tasks"),
        ]),
        ("إدارة البيانات", [
            ("إدارة الطلاب",        "student_mgmt",         "fas fa-graduation-cap"),
            ("إضافة طالب",          "add_student",          "fas fa-user-plus"),
            ("إدارة الفصول",        "class_naming",         "fas fa-school"),
            ("إدارة الجوالات",      "phones",               "fas fa-mobile-alt"),
            ("الطلاب المستثنون",    "exempted_students",    "fas fa-user-slash"),
            ("نشر النتائج",         "results",              "fas fa-medal"),
            ("تصدير نور",           "noor_export",          "fas fa-cloud-upload-alt"),
        ]),
        ("أدوات المعلم", [
            ("تحويل طالب",          "referral_teacher",     "fas fa-clipboard-list"),
            ("نماذج المعلم",        "teacher_forms",        "fas fa-file-contract"),
            ("تحليل النتائج",       "grade_analysis",       "fas fa-chart-bar"),
        ]),
        ("الإعدادات والنظام", [
            ("إعدادات المدرسة",     "school_settings",      "fas fa-university"),
            ("المستخدمون",          "users",                "fas fa-user-shield"),
            ("النسخ الاحتياطية",    "backup",               "fas fa-hdd"),
            ("الرسائل الداخلية",     "quick_notes",          "fas fa-envelope"),
            ("شواهد الأداء",        "lab_submissions",      "fas fa-clipboard-check"),
        ]),
    ]

    # ── بناء شريط التنقل الجانبي ──────────────────────────────
    sidebar_html = ""
    for grp_title, grp_items in SIDEBAR_GROUPS:
        visible = [(n, k, i) for n, k, i in grp_items
                   if allowed_tabs is None or n in allowed_tabs or n == 'الرسائل الداخلية']
        if not visible:
            continue
        sidebar_html += '<div class="sb-group">' + grp_title + '</div>'
        for name, key, icon in visible:
            badge = ''
            if key == 'lab_submissions' and unread_lab_submissions > 0:
                badge = (f'<span style="background:#ef4444;color:white;border-radius:20px;'
                         f'padding:1px 7px;font-size:11px;margin-right:6px">{unread_lab_submissions}</span>')
            if key == 'quick_notes' and unread_inbox > 0:
                badge = (f'<span id="inbox-sidebar-badge" style="background:#ef4444;color:white;border-radius:20px;'
                         f'padding:1px 7px;font-size:11px;margin-right:6px">{unread_inbox}</span>')
            elif key == 'quick_notes':
                badge = '<span id="inbox-sidebar-badge" style="display:none;background:#ef4444;color:white;border-radius:20px;padding:1px 7px;font-size:11px;margin-right:6px"></span>'
            sidebar_html += (
                '<button class="tab-btn" data-key="' + key + '" onclick="showTab(\'' + key + '\')">'
                '<i class="ti ' + icon + '"></i>' + name + badge + '</button>'
            )
        sidebar_html += '<div class="sb-div"></div>'

    # ── رابط ربط واتساب للمدير والوكيل ────────────────────────
    if role in ("admin", "deputy"):
        sidebar_html += '<div class="sb-group">واتساب</div>'
        sidebar_html += (
            '<a class="tab-btn" href="/web/whatsapp-connect" target="_blank" '
            'style="text-decoration:none;color:inherit">'
            '<i class="ti fas fa-qrcode"></i>ربط واتساب</a>'
        )
        sidebar_html += '<div class="sb-div"></div>'

    # ── CSS المضغوط الكامل ────────────────────────────────────
    css = (
        '@import url(\'https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&display=swap\');'
        ':root{--pr:#1565C0;--pr-dk:#0D47A1;--pr-lt:#EFF6FF;--dg:#C62828;--ok:#2E7D32;--wn:#E65100;'
        '--sw:220px;--th:56px;--bg:#F0F4F8;--cd:#fff;--bd:#E2E8F0;--tx:#1E293B;--mu:#64748B;--rd:12px;--sh:0 2px 12px rgba(0,0,0,.07)}'
        '*,*::before,*::after{box-sizing:border-box;-webkit-tap-highlight-color:transparent}'
        'body{font-family:Tajawal,Arial,sans-serif;direction:rtl;background:var(--bg);margin:0;color:var(--tx)}'
        # Topbar
        '.topbar{background:linear-gradient(135deg,var(--pr),var(--pr-dk));color:#fff;height:var(--th);'
        'display:flex;align-items:center;justify-content:space-between;padding:0 18px;'
        'position:fixed;top:0;right:0;left:0;z-index:300;box-shadow:0 2px 16px rgba(21,101,192,.3)}'
        '.tb-l{display:flex;align-items:center;gap:10px}'
        '.tb-r{display:flex;align-items:center;gap:10px}'
        '.topbar h1{font-size:16px;font-weight:900;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'
        '.ub{font-size:12px;background:rgba(255,255,255,.18);border-radius:20px;padding:4px 12px}'
        '.lo{font-size:12px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);'
        'color:#fff;border-radius:20px;padding:4px 12px;cursor:pointer;text-decoration:none;white-space:nowrap}'
        '.lo:hover{background:rgba(255,255,255,.28)}'
        '#mt{display:none;flex-direction:column;gap:5px;cursor:pointer;padding:6px;border:none;background:transparent}'
        '#mt span{display:block;width:22px;height:2px;background:#fff;border-radius:2px;transition:.3s}'
        '#mt.open span:nth-child(1){transform:rotate(45deg) translate(5px,5px)}'
        '#mt.open span:nth-child(2){opacity:0}'
        '#mt.open span:nth-child(3){transform:rotate(-45deg) translate(5px,-5px)}'
        # Sidebar
        '.sidebar{position:fixed;right:0;top:var(--th);bottom:0;width:var(--sw);background:#fff;'
        'border-left:1px solid var(--bd);overflow-y:auto;z-index:200;transition:transform .25s cubic-bezier(.4,0,.2,1);'
        'scrollbar-width:thin;scrollbar-color:#CBD5E1 transparent}'
        '.sidebar::-webkit-scrollbar{width:4px}'
        '.sidebar::-webkit-scrollbar-thumb{background:#CBD5E1;border-radius:4px}'
        '.sb-group{font-size:10px;font-weight:700;color:#94A3B8;letter-spacing:.8px;padding:14px 14px 4px;text-transform:uppercase}'
        '.tab-btn{display:flex;align-items:center;gap:9px;width:100%;text-align:right;padding:9px 14px;border:none;'
        'background:none;cursor:pointer;font-family:Tajawal,Arial;font-size:13px;color:#475569;'
        'border-right:3px solid transparent;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:all .15s}'
        '.tab-btn .ti{font-size:16px;flex-shrink:0;width:24px;text-align:center;color:var(--mu);transition:color .15s}'
        '.tab-btn:hover .ti,.tab-btn.active .ti{color:var(--pr)}'
        '.tab-btn:hover{background:var(--pr-lt);color:var(--pr)}'
        '.tab-btn.active{background:var(--pr-lt);color:var(--pr);font-weight:700;border-right-color:var(--pr)}'
        '.sb-div{height:1px;background:var(--bd);margin:6px 10px}'
        '#ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:190}'
        '#ov.show{display:block}'
        # Content
        '.content{margin-right:var(--sw);padding:20px;margin-top:var(--th);min-height:calc(100vh - var(--th))}'
        '#tc>div{display:none}'
        '#tc>div.active{display:block;animation:fi .18s ease}'
        '@keyframes fi{from{opacity:.3;transform:translateY(4px)}to{opacity:1;transform:none}}'
        # Cards
        '.stat-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;margin-bottom:18px}'
        '.sc{background:var(--cd);border-radius:var(--rd);padding:16px 12px;text-align:center;box-shadow:var(--sh);border:1px solid var(--bd);transition:transform .15s,box-shadow .15s}'
        '.sc:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.1)}'
        '.sc .v{font-size:26px;font-weight:900;line-height:1.1}'
        '.sc .l{font-size:11px;color:var(--mu);margin-top:5px;font-weight:500}'
        # Section
        '.section{background:var(--cd);border-radius:var(--rd);padding:16px;margin-bottom:16px;box-shadow:var(--sh);border:1px solid var(--bd)}'
        '.st{font-size:14px;font-weight:700;color:var(--pr);margin:0 0 14px;padding-right:10px;border-right:3px solid var(--pr);display:flex;align-items:center;gap:8px}'
        '.pt{font-size:17px;font-weight:800;color:var(--pr);margin:0 0 16px;display:flex;align-items:center;gap:8px}'
        # Table
        '.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:8px}'
        'table{width:100%;border-collapse:collapse;font-size:13px;min-width:380px}'
        'thead tr{background:var(--pr-lt)}'
        'th{color:var(--pr);padding:10px 8px;text-align:center;white-space:nowrap;font-weight:700;font-size:12px}'
        'td{padding:9px 8px;border-bottom:1px solid #F1F5F9;text-align:center}'
        'tbody tr:hover{background:#FAFCFF}'
        'tbody tr:last-child td{border-bottom:none}'
        # Badges
        '.badge{padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700;display:inline-block}'
        '.br{background:#FEE2E2;color:#C62828}'
        '.bg{background:#DCFCE7;color:#166534}'
        '.bo{background:#FEF3C7;color:#92400E}'
        '.bb{background:#DBEAFE;color:#1565C0}'
        '@keyframes slideUp{from{opacity:0;transform:translateY(15px)}to{opacity:1;transform:translateY(0)}}'
        '.bp{background:#F3E8FF;color:#7C3AED}'
        # Forms
        '.fg{display:flex;flex-direction:column;gap:5px}'
        '.fl{font-size:12px;font-weight:600;color:var(--mu)}'
        '.fg2{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:14px}'
        'input[type=text],input[type=date],input[type=tel],input[type=number],input[type=time],select,textarea{'
        'padding:9px 11px;border:1.5px solid var(--bd);border-radius:8px;font-family:Tajawal,Arial;'
        'font-size:13px;color:var(--tx);background:#fff;transition:border-color .2s;width:100%}'
        'input:focus,select:focus,textarea:focus{outline:none;border-color:var(--pr);box-shadow:0 0 0 3px rgba(21,101,192,.1)}'
        'textarea{resize:vertical;min-height:80px}'
        # Buttons
        '.bg-btn{display:flex;gap:8px;flex-wrap:wrap}'
        '.btn{padding:9px 18px;border:none;border-radius:8px;cursor:pointer;font-family:Tajawal,Arial;'
        'font-size:13px;font-weight:700;touch-action:manipulation;transition:all .15s;display:inline-flex;align-items:center;gap:6px}'
        '.btn:hover{opacity:.88;transform:translateY(-1px)}'
        '.btn:active{transform:none;opacity:1}'
        '.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}'
        '.bp1{background:var(--pr);color:#fff}'
        '.bp2{background:#E2E8F0;color:#374151}'
        '.bp3{background:var(--dg);color:#fff}'
        '.bp4{background:var(--ok);color:#fff}'
        '.bp5{background:var(--wn);color:#fff}'
        '.bsm{padding:5px 12px;font-size:12px}'
        # Student cards
        '.sg{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;margin-bottom:14px}'
        '.sk{display:flex;align-items:center;gap:10px;padding:10px 12px;background:#F8FAFF;'
        'border:1.5px solid #E0E7FF;border-radius:8px;cursor:pointer;transition:all .15s}'
        '.sk:hover{border-color:var(--pr);background:var(--pr-lt)}'
        '.sk input[type=checkbox]{width:16px;height:16px;accent-color:var(--pr);flex-shrink:0}'
        # Inner tabs
        '.it{display:flex;gap:4px;margin-bottom:16px;border-bottom:2px solid var(--bd)}'
        '.itb{padding:8px 16px;border:none;background:none;cursor:pointer;font-family:Tajawal,Arial;'
        'font-size:13px;font-weight:600;color:var(--mu);border-bottom:2px solid transparent;'
        'margin-bottom:-2px;border-radius:6px 6px 0 0;transition:all .15s}'
        '.itb.active{color:var(--pr);border-bottom-color:var(--pr);background:var(--pr-lt)}'
        '.ip{display:none}'
        '.ip.active{display:block;animation:fi .15s ease}'
        # Status
        '.sm{padding:10px 14px;border-radius:8px;font-size:13px;font-weight:500;margin:8px 0}'
        '.sok{background:#DCFCE7;color:#166534}'
        '.ser{background:#FEE2E2;color:#C62828}'
        '.sin{background:#DBEAFE;color:#1565C0}'
        '.loading{text-align:center;padding:40px;color:#94A3B8;font-size:14px}'
        # Alert boxes
        '.ab{padding:12px 16px;border-radius:8px;margin-bottom:14px;display:flex;align-items:center;gap:10px;font-size:13px}'
        '.aw{background:#FEF3C7;border:1px solid #FDE68A;color:#92400E}'
        '.ai{background:#DBEAFE;border:1px solid #BFDBFE;color:#1565C0}'
        '.ad{background:#FEE2E2;border:1px solid #FECACA;color:#C62828}'
        '.as{background:#DCFCE7;border:1px solid #BBF7D0;color:#166534}'
        # Link cards
        '.lc{background:#F8FAFF;border:1.5px solid #E0E7FF;border-radius:10px;padding:14px;'
        'display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px}'
        '.lu{font-size:12px;color:var(--pr);word-break:break-all;flex:1}'
        # Schedule item
        '.sci{background:#F8FAFF;border:1.5px solid #E0E7FF;border-radius:8px;padding:12px;'
        'display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}'
        # Responsive
        '@media(max-width:768px){'
        '#mt{display:flex}'
        '.sidebar{transform:translateX(100%);width:260px}'
        '.sidebar.open{transform:translateX(0)}'
        '.content{margin-right:0;padding:12px}'
        '.stat-cards{grid-template-columns:repeat(2,1fr);gap:8px}'
        '.sc .v{font-size:22px}'
        'table{font-size:12px}'
        'th,td{padding:7px 5px}'
        '.fg2{grid-template-columns:1fr}'
        '.btn{padding:10px 14px;font-size:14px}'
        'input[type=text],input[type=date],select{font-size:16px}'
        '}'
        '@media(max-width:420px){.topbar h1{font-size:13px}.section{padding:12px}}'
        '@media print{.topbar,.sidebar,#ov{display:none!important}.content{margin:0!important;padding:0!important}}'
        '</style><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head><body data-user="' + username + '">'
    )

    # ── محتوى التبويبات ────────────────────────────────────────
    _circ_add_btn = '<button class="btn bp1 bsm" onclick="si(\'circulars\',\'circ-add\')">+ إصدار تعميم</button>' if role == 'admin' else ''
    _alert_referral_html = ('<div class="ab ai" style="background:#FFF7ED; border:1px solid #FFEDD5; color:#C2410C; padding:15px; border-radius:12px; display:flex; align-items:center; gap:12px; cursor:pointer" onclick="showTab(\'referral_deputy\')"><i class="fas fa-exclamation-circle" style="font-size:20px"></i> <div><b>تنبيه:</b> يوجد عدد <b>' + str(unread_referrals) + '</b> تحويلات جديدة بانتظار مراجعتك.</div></div>') if unread_referrals > 0 else ''
    _alert_circs_html = ('<div class="ab ai" style="background:#F0F9FF; border:1px solid #E0F2FE; color:#0369A1; padding:15px; border-radius:12px; display:flex; align-items:center; gap:12px; cursor:pointer" onclick="showTab(\'circulars\')"><i class="fas fa-scroll" style="font-size:20px"></i> <div><b>تعميم جديد:</b> لديك <b>' + str(unread_circs) + '</b> تعاميم غير مقروءة.</div></div>') if unread_circs > 0 else ''
    _alert_lab_html = ('<div class="ab ai" style="background:#F0FDF4; border:1px solid #BBF7D0; color:#166534; padding:15px; border-radius:12px; display:flex; align-items:center; gap:12px; cursor:pointer" onclick="window.open(\'/web/lab-docs/submissions\',\'_blank\')"><i class="fas fa-clipboard-check" style="font-size:20px"></i> <div><b>شواهد أداء جديدة:</b> وصل <b>' + str(unread_lab_submissions) + '</b> ملف شواهد أداء وظيفي من المحضر.</div></div>') if unread_lab_submissions > 0 else ''
    content_html = f'''
<div id="tab-dashboard">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
    <h2 class="pt"><i class="fas fa-chart-line"></i> لوحة المراقبة</h2>
    <input type="date" id="dash-date" onchange="loadDashboard()" style="width:auto">
  </div>
  <div id="smart-alert-banner" style="margin-bottom:20px; display: {'block' if (unread_referrals > 0 or unread_circs > 0 or unread_lab_submissions > 0) else 'none'}">
    <div style="display:flex; flex-direction:column; gap:10px">
      {_alert_referral_html}
      {_alert_circs_html}
      {_alert_lab_html}
    </div>
  </div>
  {'<div style="margin-bottom:18px"><a href="/web/lab-docs" target="_blank" style="display:flex;align-items:center;gap:14px;background:linear-gradient(135deg,#0f6e56,#2da88a);color:white;padding:16px 22px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px;box-shadow:0 4px 14px rgba(45,168,138,0.35)"><span style="font-size:28px">📋</span><div><div>توثيق شواهد الأداء الوظيفي</div><div style="font-size:12px;font-weight:400;opacity:0.85;margin-top:3px">سجّل وأرشف شواهد أدائك الوظيفي بشكل تفاعلي</div></div><span style="margin-right:auto;opacity:0.7">↗</span></a></div>' if role == "lab" else ''}
  <div class="stat-cards" id="dash-cards"><div class="loading">⏳ جارٍ التحميل...</div></div>
  <div class="section"><div class="st">أكثر الفصول غياباً</div>
    <div class="tw"><table><thead><tr><th>الفصل</th><th>الغائبون</th><th>الحاضرون</th><th>نسبة الغياب</th></tr></thead>
    <tbody id="dash-classes"></tbody></table></div></div>
</div>

<div id="tab-links">
  <h2 class="pt"><i class="fas fa-link"></i> روابط الفصول</h2>
  <div class="ab ai">💡 شارك الرابط مع المعلم ليسجّل الغياب مباشرة من هاتفه</div>
  <div id="links-list" class="loading">⏳ جارٍ التحميل...</div>
</div>

<div id="tab-live_monitor">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
    <h2 class="pt" style="margin:0"><i class="fas fa-satellite-dish"></i> المراقبة الحية</h2>
    <div style="display:flex;gap:8px;align-items:center">
      <input type="date" id="lm-date" style="width:auto">
      <button class="btn bp1" onclick="loadLiveMonitor()"><i class="fas fa-sync-alt"></i> تحديث</button>
    </div>
  </div>
  <div class="stat-cards" id="lm-cards"></div>
  <div class="section"><div class="st">الغائبون الآن</div><div class="tw">
    <table><thead><tr><th>الطالب</th><th>الفصل</th><th>الحصة</th><th>المعلم</th></tr></thead>
    <tbody id="lm-table"></tbody></table></div></div>
</div>

<div id="tab-reg_absence">
  <h2 class="pt"><i class="fas fa-user-check"></i> تسجيل الغياب</h2>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="ra-date"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="ra-class" onchange="loadClassStudentsForAbs()"><option value="">اختر فصلاً</option></select></div>
      <div class="fg"><label class="fl">الحصة</label><select id="ra-period">
        <option value="0">يوم كامل</option><option value="1">الحصة 1</option><option value="2">الحصة 2</option>
        <option value="3">الحصة 3</option><option value="4">الحصة 4</option><option value="5">الحصة 5</option>
        <option value="6">الحصة 6</option><option value="7">الحصة 7</option></select></div>
    </div>
    <div id="ra-students" class="sg"><p style="color:#9CA3AF">اختر فصلاً أولاً</p></div>
    <div class="bg-btn">
      <button class="btn bp3" onclick="submitAbsence()">💾 تسجيل الغياب</button>
      <button class="btn bp2" onclick="selAll('ra-students')">تحديد الكل</button>
      <button class="btn bp2" onclick="clrAll('ra-students')">إلغاء الكل</button>
    </div>
    <div id="ra-status" style="margin-top:10px"></div>
  </div>
</div>

<div id="tab-reg_tardiness">
  <h2 class="pt"><i class="fas fa-stopwatch"></i> تسجيل التأخر</h2>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="rt-date"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="rt-class" onchange="loadClassStudentsForTard()"><option value="">اختر فصلاً</option></select></div>
    </div>
    <div id="rt-students" class="sg"><p style="color:#9CA3AF">اختر فصلاً أولاً</p></div>
    <div id="rt-status" style="margin-top:10px"></div>
  </div>
</div>

<div id="tab-new_permission">
  <h2 class="pt"><i class="fas fa-bell"></i> تسجيل طلب استئذان</h2>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="np-date"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="np-class" onchange="loadClassForPerm()"><option value="">اختر فصلاً</option></select></div>
      <div class="fg"><label class="fl">الطالب</label><select id="np-student"><option value="">اختر طالباً</option></select></div>
      <div class="fg"><label class="fl">السبب</label><select id="np-reason">
        <option>مراجعة طبية</option><option>ظرف طارئ</option><option>موعد رسمي</option>
        <option>إجراءات حكومية</option><option>أخرى</option></select></div>
      <div class="fg"><label class="fl">جوال ولي الأمر</label><input type="tel" id="np-phone" placeholder="05xxxxxxxx"></div>
    </div>
    <div class="bg-btn">
      <button class="btn bp1" onclick="submitPermission(true)">📲 تسجيل وإرسال واتساب</button>
      <button class="btn bp2" onclick="submitPermission(false)">💾 تسجيل بدون إرسال</button>
    </div>
    <div id="np-status" style="margin-top:12px"></div>
  </div>
  <div class="section"><div class="st">استئذانات اليوم</div><div id="np-today-list" class="loading">...</div></div>
</div>

<div id="tab-absences">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-history"></i> سجل الغياب</h2>
    <input type="date" id="abs-date" style="width:auto">
    <select id="abs-class-filter" style="width:auto"><option value="">كل الفصول</option></select>
    <button class="btn bp1 bsm" onclick="loadAbsences()">تحميل</button>
    <button class="btn bp2 bsm" onclick="exportTbl('abs-table','غياب')">⬇️ تصدير</button>
  </div>
  <div class="section"><div class="tw"><table>
    <thead><tr><th>التاريخ</th><th>الفصل</th><th>الطالب</th><th>الحصة</th><th>المعلم</th><th>حذف</th></tr></thead>
    <tbody id="abs-table"></tbody></table></div></div>
</div>

<div id="tab-tardiness">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-clock"></i> سجل التأخر</h2>
    <input type="date" id="tard-date" style="width:auto">
    <button class="btn bp1 bsm" onclick="loadTardiness()">تحميل</button>
    <button class="btn bp2 bsm" onclick="exportTbl('tard-table','تأخر')">⬇️ تصدير</button>
  </div>
  <div class="section"><div class="tw"><table>
    <thead><tr><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>الدقائق</th><th>المعلم</th><th>حذف</th></tr></thead>
    <tbody id="tard-table"></tbody></table></div></div>
</div>

<div id="tab-excuses">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-file-medical"></i> الأعذار</h2>
    <input type="date" id="exc-date" onchange="loadExcuses()" style="width:auto">
    <button class="btn bp1 bsm" onclick="showAddExc()">+ إضافة عذر</button>
  </div>
  <div id="add-exc-form" style="display:none" class="section">
    <div class="st">إضافة عذر جديد</div>
    <div class="fg2">
      <div class="fg"><label class="fl">الفصل</label><select id="exc-cls" onchange="loadClsForExc()"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">الطالب</label><select id="exc-stu"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="exc-date-new"></div>
      <div class="fg"><label class="fl">السبب</label><input type="text" id="exc-reason" placeholder="سبب الغياب"></div>
    </div>
    <div class="bg-btn">
      <button class="btn bp1" onclick="addExcuse()">💾 حفظ</button>
      <button class="btn bp2" onclick="document.getElementById('add-exc-form').style.display='none'">إلغاء</button>
    </div>
    <div id="exc-add-st" style="margin-top:8px"></div>
  </div>
  <div class="section"><div class="tw"><table>
    <thead><tr><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>السبب</th><th>المصدر</th></tr></thead>
    <tbody id="exc-table"></tbody></table></div></div>
</div>

<div id="tab-permissions">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-door-open"></i> الاستئذان</h2>
    <input type="date" id="perm-date" onchange="loadPermissions()" style="width:auto">
  </div>
  <div id="perm-ind" style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap"></div>
  <div class="section"><div class="tw"><table>
    <thead><tr><th>الطالب</th><th>الفصل</th><th>السبب</th><th>الحالة</th><th>موافقة</th></tr></thead>
    <tbody id="perm-table"></tbody></table></div></div>
</div>

<div id="tab-logs">
  <h2 class="pt"><i class="fas fa-file-export"></i> السجلات والتصدير</h2>
  <div class="it">
    <button class="itb active" onclick="si('logs','lg-abs')">الغياب</button>
    <button class="itb" onclick="si('logs','lg-tard')">التأخر</button>
    <button class="itb" onclick="si('logs','lg-msgs')">الرسائل</button>
  </div>
  <div id="lg-abs" class="ip active">
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;align-items:flex-end">
      <div class="fg"><label class="fl">من</label><input type="date" id="lg-from"></div>
      <div class="fg"><label class="fl">إلى</label><input type="date" id="lg-to"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="lg-cls"><option value="">الكل</option></select></div>
      <button class="btn bp1" onclick="loadLogsAbs()" style="align-self:flex-end">تحميل</button>
      <button class="btn bp4" onclick="exportTbl('lg-abs-tbl','سجل_غياب')" style="align-self:flex-end">⬇️ Excel</button>
    </div>
    <div class="section"><div class="tw"><table>
      <thead><tr><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>الحصة</th><th>المعلم</th></tr></thead>
      <tbody id="lg-abs-tbl"></tbody></table></div></div>
  </div>
  <div id="lg-tard" class="ip">
    <div class="section"><div class="tw"><table>
      <thead><tr><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>الدقائق</th></tr></thead>
      <tbody id="lg-tard-tbl"></tbody></table></div></div>
  </div>
  <div id="lg-msgs" class="ip">
    <div class="section"><div class="tw"><table>
      <thead><tr><th>التاريخ</th><th>الطالب</th><th>الجوال</th><th>الحالة</th><th>النوع</th></tr></thead>
      <tbody id="lg-msgs-tbl"></tbody></table></div></div>
  </div>
</div>

<div id="tab-absence_mgmt">
  <h2 class="pt"><i class="fas fa-users-cog"></i> إدارة الغياب</h2>
  <div class="it">
    <button class="itb active" onclick="si('absence_mgmt','am-srch')">بحث وتعديل</button>
    <button class="itb" onclick="si('absence_mgmt','am-bulk')">حذف مجمّع</button>
  </div>
  <div id="am-srch" class="ip active">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">بحث (اسم أو رقم)</label><input type="text" id="am-q" placeholder="..."></div>
        <div class="fg"><label class="fl">التاريخ</label><input type="date" id="am-date"></div>
        <div class="fg"><label class="fl">الفصل</label><select id="am-cls"><option value="">الكل</option></select></div>
      </div>
      <button class="btn bp1" onclick="loadAbsences()">🔍 بحث وعرض</button>
      <div id="am-res" style="margin-top:14px"></div>
    </div>
  </div>
  <div id="am-bulk" class="ip">
    <div class="section">
      <div class="ab ad">⚠️ الحذف المجمّع لا يمكن التراجع عنه</div>
      <div class="fg2">
        <div class="fg"><label class="fl">من تاريخ</label><input type="date" id="am-bf"></div>
        <div class="fg"><label class="fl">إلى تاريخ</label><input type="date" id="am-bt"></div>
        <div class="fg"><label class="fl">الفصل (اختياري)</label><select id="am-bc"><option value="">الكل</option></select></div>
      </div>
      <button class="btn bp3" onclick="alert('حذف مجمّع — يتطلب تأكيداً')">🗑️ حذف</button>
    </div>
  </div>
</div>

<div id="tab-reports_print">
  <h2 class="pt"><i class="fas fa-print"></i> التقارير والطباعة</h2>
  <div class="it">
    <button class="itb active" onclick="si('reports_print','rp-mo')">الشهرية</button>
    <button class="itb" onclick="si('reports_print','rp-cl')">حسب الفصل</button>
    <button class="itb" onclick="si('reports_print','rp-st')">حسب الطالب</button>
  </div>
  <div id="rp-mo" class="ip active">
    <div class="section">
      <button class="btn bp1 bsm" onclick="loadReports()" style="margin-bottom:12px">تحميل</button>
      <div class="tw"><table><thead><tr><th>الشهر</th><th>أيام الدراسة</th><th>إجمالي الغياب</th><th>الطلاب المتأثرون</th></tr></thead>
      <tbody id="rep-table"></tbody></table></div>
    </div>
  </div>
  <div id="rp-cl" class="ip">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">الفصل</label><select id="rp-cls"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">من تاريخ</label><input type="date" id="rp-from"></div>
        <div class="fg"><label class="fl">إلى تاريخ</label><input type="date" id="rp-to"></div>
      </div>
      <button class="btn bp1" onclick="loadClassReport()">إنشاء</button>
      <div id="rp-cls-res" style="margin-top:14px"></div>
    </div>
  </div>
  <div id="rp-st" class="ip">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">الفصل</label><select id="rp-sc" onchange="loadClsForRp()"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">الطالب</label><select id="rp-ss"><option value="">اختر</option></select></div>
      </div>
      <button class="btn bp1" onclick="loadStuReport()">إنشاء تقرير الطالب</button>
      <div id="rp-st-res" style="margin-top:14px"></div>
    </div>
  </div>
</div>

<div id="tab-term_report">
  <h2 class="pt"><i class="fas fa-file-alt"></i> تقرير الفصل الدراسي</h2>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">الفصل الدراسي</label><select id="tr-sem"><option value="1">الأول</option><option value="2">الثاني</option></select></div>
      <div class="fg"><label class="fl">الصف</label><select id="tr-cls"><option value="">الكل</option></select></div>
    </div>
    <div class="bg-btn">
      <button class="btn bp1" onclick="loadClassReport()">إنشاء</button>
      <button class="btn bp2" onclick="printSec('tr-res')">🖨️ طباعة</button>
    </div>
    <div id="tr-st" style="margin-top:8px"></div>
    <div id="tr-res" style="margin-top:16px"></div>
  </div>
</div>

<div id="tab-grade_analysis">
  <h2 class="pt"><i class="fas fa-chart-bar"></i> تحليل نتائج الطلاب</h2>
  <div class="section">
    <div class="ab ai">📌 ارفع ملف نتائج الطلاب (PDF من نور / Excel / CSV) للحصول على تحليل تفصيلي بنفس محرّك التطبيق المكتبي</div>
    <div class="fg2">
      <div class="fg"><label class="fl">ملف النتائج</label><input type="file" id="ga-file" accept=".pdf,.xlsx,.xls,.csv"></div>
      <div class="fg" style="align-self:flex-end">
        <button class="btn bp1" onclick="analyzeGrades()">⚡ تحليل</button>
      </div>
    </div>
    <div id="ga-st" style="margin-top:10px"></div>
  </div>
  <div id="ga-summary" style="margin-top:14px"></div>
  <div id="ga-filter" style="display:none;margin-top:10px">
    <div class="section" style="padding:12px 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <label class="fl" style="margin:0;white-space:nowrap">🔍 فلتر المادة:</label>
      <select id="ga-subject-sel" onchange="gaFilterSubject()" style="min-width:200px;font-size:14px">
        <option value="الكل">📚 جميع المواد</option>
      </select>
      <span id="ga-filter-info" style="font-size:12px;color:#64748B"></span>
      <button class="btn bp4 bsm" style="margin-right:auto" onclick="printGaFrame()">🖨️ طباعة</button>
    </div>
  </div>
  <div id="ga-res" style="margin-top:10px">
    <div class="ab ai">📌 ارفع ملفاً وانقر «تحليل» لعرض التقرير الكامل</div>
  </div>
</div>

<div id="tab-admin_report">
  <h2 class="pt"><i class="fas fa-user-tie"></i> تقرير الإدارة اليومي</h2>
  <div class="section">
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="ar-date" style="width:auto"></div>
      <button class="btn bp1" onclick="generateAdminReport()">إنشاء التقرير</button>
      <button class="btn bp2" onclick="sendAdminReport()">📨 إرسال للإدارة</button>
      <button class="btn bp2" onclick="printSec('ar-content')">🖨️ طباعة</button>
    </div>
    <div id="ar-status" style="margin-bottom:12px"></div>
    <div id="ar-content"></div>
  </div>
</div>

<div id="tab-student_analysis">
  <h2 class="pt"><i class="fas fa-chart-bar"></i> تحليل الطالب الشامل</h2>
  <div class="section">
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
      <div class="fg"><label class="fl">الفصل</label><select id="an-class" onchange="loadClsForAn()" style="min-width:180px"><option value="">اختر فصلاً</option></select></div>
      <div class="fg"><label class="fl">الطالب</label><select id="an-student" style="min-width:250px"><option value="">اختر طالباً</option></select></div>
      <button class="btn bp1" onclick="analyzeStudent()">🔍 بدء التحليل</button>
    </div>
  </div>

  <div id="an-result" style="display:none;margin-top:20px">
    <div class="section" id="an-header-name" style="background:var(--pr-lt); color:var(--pr); font-weight:900; font-size:20px; text-align:center; padding:15px; margin-bottom:20px; border:2px solid var(--pr); border-radius:12px"></div>
    
    <!-- Points & Portal Link Section -->
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-bottom:20px">
      <div class="section" style="background:linear-gradient(135deg, #FFD700, #FFA500); border:none; color:#fff">
        <div style="display:flex; align-items:center; gap:15px">
            <i class="fas fa-star" style="font-size:30px"></i>
            <div>
                <div style="font-size:14px; opacity:0.9">إجمالي نقاط التميز</div>
                <div id="an-total-points" style="font-size:28px; font-weight:900">0</div>
            </div>
        </div>
      </div>
      <div class="section" style="background:#fff; border:2px dashed #E2E8F0; display:flex; align-items:center; justify-content:space-between">
        <div style="display:flex; align-items:center; gap:12px">
            <i class="fas fa-user-shield" style="color:var(--pr); font-size:24px"></i>
            <div>
                <div style="font-size:13px; color:var(--mu)">بوابة ولي الأمر</div>
                <div style="font-size:11px; color:#94A3B8">رابط المتابعة المباشرة لولي الأمر</div>
            </div>
        </div>
        <div id="an-portal-st">
            <button class="btn bsm bp1" onclick="getPortalLink(document.getElementById('an-student').value)">توليد الرابط</button>
        </div>
      </div>
    </div>
    <!-- كروت الإحصائيات -->
    <div id="an-cards" class="stat-cards" style="margin-bottom:20px"></div>

    <!-- الرسوم البيانية -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(400px, 1fr));gap:20px;margin-bottom:20px">
      <div class="section">
        <div class="st">📈 اتجاه غياب الطالب (شهرياً)</div>
        <div style="height:320px; position:relative;">
          <canvas id="an-chart-line"></canvas>
        </div>
      </div>
      <div class="section">
        <div class="st">📊 توزيع السلوك والتأخر</div>
        <div style="height:320px; position:relative;">
          <canvas id="an-chart-pie"></canvas>
        </div>
      </div>
    </div>

    <!-- السجل الزمني -->
    <div class="section">
      <div class="st">📅 السجل الزمني لأحدث الإجراءات</div>
      <div class="tw">
        <table>
          <thead>
            <tr><th>التاريخ</th><th>النوع</th><th>التفاصيل</th><th>الحالة</th></tr>
          </thead>
          <tbody id="an-table-body"></tbody>
        </table>
      </div>
    </div>

    <!-- سجل نقاط التميز -->
    <div class="section" id="an-pts-section" style="display:none">
      <div class="st">⭐ سجل نقاط التميز التفصيلي</div>
      <div class="tw">
        <table>
          <thead>
            <tr><th>التاريخ</th><th>النقاط</th><th>السبب</th><th>بواسطة</th></tr>
          </thead>
          <tbody id="an-pts-table-body"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<div id="tab-top_absent">
  <h2 class="pt"><i class="fas fa-award"></i> أكثر الطلاب غياباً</h2>
  <div class="section"><div class="tw"><table>
    <thead><tr><th>#</th><th>الطالب</th><th>الفصل</th><th>أيام الغياب</th><th>آخر غياب</th></tr></thead>
    <tbody id="top-table"></tbody></table></div></div>
</div>

<div id="tab-alerts">
  <h2 class="pt"><i class="fas fa-exclamation-triangle"></i> الإشعارات الذكية</h2>
  <div class="it">
    <button class="itb active" onclick="si('alerts','al-abs');loadAlerts();">🔴 الغياب</button>
    <button class="itb" onclick="si('alerts','al-tard');loadAlertsTard();">🟠 التأخر</button>
    <button class="itb" onclick="si('alerts','al-escaped');loadAlertsEscaped();">🚨 الهاربون</button>
  </div>
  <div id="al-abs" class="ip active">
    <div id="alerts-info" style="margin:8px 0 12px"></div>
    <div class="bg-btn" style="margin-bottom:10px">
      <button class="btn bp2 bsm" onclick="alSelAll('alerts-table',true)">✓ تحديد الكل</button>
      <button class="btn bp2 bsm" onclick="alSelAll('alerts-table',false)">✗ إلغاء الكل</button>
      <button class="btn bp1" onclick="referToCounselor('غياب')">🧠 تحويل المحدد للموجّه الطلابي</button>
    </div>
    <div id="al-abs-st" style="margin-bottom:8px"></div>
    <div class="section"><div class="tw"><table>
      <thead><tr><th style="width:32px">☐</th><th>#</th><th>الطالب</th><th>الفصل</th><th>أيام الغياب</th><th>آخر غياب</th><th>الجوال</th></tr></thead>
      <tbody id="alerts-table"></tbody></table></div></div>
  </div>
  <div id="al-tard" class="ip">
    <div id="alerts-tard-info" style="margin:8px 0 12px"></div>
    <div class="bg-btn" style="margin-bottom:10px">
      <button class="btn bp2 bsm" onclick="alSelAll('alerts-tard-table',true)">✓ تحديد الكل</button>
      <button class="btn bp2 bsm" onclick="alSelAll('alerts-tard-table',false)">✗ إلغاء الكل</button>
      <button class="btn bp1" onclick="referToCounselor('تأخر')">🧠 تحويل المحدد للموجّه الطلابي</button>
    </div>
    <div id="al-tard-st" style="margin-bottom:8px"></div>
    <div class="section"><div class="tw"><table>
      <thead><tr><th style="width:32px">☐</th><th>#</th><th>الطالب</th><th>الفصل</th><th>مرات التأخر</th><th>آخر تأخر</th></tr></thead>
      <tbody id="alerts-tard-table"></tbody></table></div></div>
  </div>
  <div id="al-escaped" class="ip">
    <div style="margin:8px 0 12px;font-size:13px;color:#64748B">الطلاب الذين سُجِّلوا هاربين — مرتبون من الأحدث للأقدم</div>
    <div id="al-escaped-month" style="display:flex;gap:10px;align-items:center;margin-bottom:12px">
      <label class="fl" style="margin:0">الشهر:</label>
      <input type="month" id="al-esc-month" style="width:auto">
      <button class="btn bp2 bsm" onclick="loadAlertsEscaped()">🔄 تحديث</button>
      <button class="btn bp3 bsm" onclick="printSec('al-esc-tbl')">🖨️ طباعة</button>
    </div>
    <div class="bg-btn" style="margin-bottom:10px">
      <button class="btn bp2 bsm" onclick="alSelAll('al-esc-tbody',true)">✓ تحديد الكل</button>
      <button class="btn bp2 bsm" onclick="alSelAll('al-esc-tbody',false)">✗ إلغاء الكل</button>
      <button class="btn bp1" onclick="referEscapedToCounselor()">🧠 تحويل المحدد للموجّه الطلابي</button>
    </div>
    <div id="al-esc-st" style="margin-bottom:8px"></div>
    <div class="section" id="al-esc-tbl"><div class="tw"><table>
      <thead><tr><th style="width:32px">☐</th><th>#</th><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>الحصص الغائبة</th><th>حالة الإحالة</th></tr></thead>
      <tbody id="al-esc-tbody"></tbody></table></div></div>
  </div>
</div>

<div id="tab-send_absence">
  <h2 class="pt"><i class="fas fa-envelope-open-text"></i> إرسال رسائل الغياب</h2>
  <div class="section">
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="sa-date" style="width:auto"></div>
      <button class="btn bp1" onclick="loadAbsencesForSend()">تحميل الغائبين</button>
    </div>
    <div id="sa-status" style="margin-bottom:12px"></div>
    <div id="sa-list"></div>
    <div id="sa-send-btn" style="margin-top:12px;display:none">
      <div class="bg-btn">
        <button class="btn bp1" onclick="sendAbsenceMessages()" id="sa-btn">📨 إرسال للمحددين</button>
        <button class="btn bp2" onclick="saAll(true)">تحديد الكل</button>
        <button class="btn bp2" onclick="saAll(false)">إلغاء الكل</button>
      </div>
      <span id="sa-progress" style="display:block;margin-top:8px;font-size:13px;color:var(--mu)"></span>
    </div>
  </div>

</div>

<div id="tab-send_tardiness">
  <h2 class="pt"><i class="fas fa-paper-plane"></i> إرسال رسائل التأخر</h2>
  <div class="section">
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:12px">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="st-date" style="width:auto"></div>
      <button class="btn bp1" onclick="loadTardinessForSend()">تحميل المتأخرين</button>
    </div>
    <div id="st-status" style="margin-bottom:12px"></div>
    <div id="st-list"></div>
    <div id="st-send-btn" style="margin-top:12px;display:none">
      <button class="btn bp1" onclick="sendTardinessMessages()">📩 إرسال للمحددين</button>
      <span id="st-progress" style="margin-right:12px;font-size:13px;color:var(--mu)"></span>
    </div>
  </div>
</div>

<div id="tab-portal_links">
  <h2 class="pt"><i class="fas fa-user-shield"></i> روابط بوابة أولياء الأمور</h2>
  <div class="section">
    <p style="color:var(--mu);font-size:13px;margin-bottom:14px">
      اختر فصلاً لتوليد رابط المتابعة لكل طالب وإرساله لولي أمره عبر الواتساب.
    </p>
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px">
      <div class="fg">
        <label class="fl">الفصل</label>
        <select id="pl-class" style="min-width:200px">
          <option value="">-- اختر فصلاً --</option>
        </select>
      </div>
      <button class="btn bp2" onclick="plLoadClass()">📋 تحميل الطلاب</button>
    </div>
    <div id="pl-status" style="margin-bottom:10px"></div>
    <div id="pl-list"></div>
    <div id="pl-actions" style="display:none;margin-top:14px">
      <div class="bg-btn">
        <button class="btn bp1" onclick="plSend()" id="pl-send-btn">📤 إرسال الروابط للمحددين</button>
        <button class="btn bp2" onclick="plAll(true)">تحديد الكل</button>
        <button class="btn bp2" onclick="plAll(false)">إلغاء الكل</button>
      </div>
      <div id="pl-progress" style="margin-top:10px;font-size:13px;color:var(--mu)"></div>
    </div>
  </div>
</div>

<div id="tab-circulars">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-scroll"></i> التعاميم والنشرات</h2>
    ''' + _circ_add_btn + '''
    <button class="btn bp2 bsm" onclick="loadCirculars()"><i class="fas fa-sync-alt"></i> تحديث</button>
  </div>
  
  <div id="circ-add" class="ip">
    <div class="section">
      <div class="st">إصدار تعميم جديد</div>
      <div class="fg2">
        <div class="fg"><label class="fl">العنوان</label><input type="text" id="ci-title" placeholder="..."></div>
        <div class="fg"><label class="fl">موجه إلى</label><select id="ci-target">
          <option value="all">الكل</option><option value="teacher">المعلمين</option>
          <option value="deputy">الوكلاء</option><option value="counselor">الموجهين</option></select></div>
        <div class="fg" style="grid-column:span 2"><label class="fl">نص التعميم / الملاحظات</label><textarea id="ci-content" rows="3" style="width:100%;padding:8px;border:1px solid #E2E8F0;border-radius:6px"></textarea></div>
        <div class="fg"><label class="fl">إرفاق ملف (PDF/صورة)</label><input type="file" id="ci-file"></div>
      </div>
      <div class="bg-btn">
        <button class="btn bp1" onclick="submitCircular()">🚀 إصدار ونشر</button>
        <button class="btn bp3" onclick="si(\'circulars\',\'circ-list\')">إلغاء</button>
      </div>
      <div id="ci-status" style="margin-top:10px"></div>
    </div>
  </div>

  <div id="circ-list" class="ip active">
    <div id="circ-container" class="loading">⏳ جارٍ التحميل...</div>
  </div>
</div>

<!-- ══ تبويب تقارير المعلمين (للمدير/الوكيل) ══ -->
<div id="tab-teacher_reports_admin">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-file-pdf"></i> تقارير المعلمين</h2>
    <span id="tra-badge" class="badge br" style="display:none;font-size:13px"></span>
    <button class="btn bp2 bsm" onclick="loadTeacherReportsAdmin()"><i class="fas fa-sync-alt"></i> تحديث</button>
  </div>
  <div class="section">
    <div class="tw">
      <table id="tra-table">
        <thead>
          <tr>
            <th>النوع</th>
            <th>العنوان</th>
            <th>المعلم</th>
            <th>التاريخ</th>
            <th>الحالة</th>
            <th>إجراء</th>
          </tr>
        </thead>
        <tbody id="tra-tbody">
          <tr><td colspan="6" style="text-align:center;color:var(--mu)">⏳ جارٍ التحميل...</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>



<!-- ══ تبويب تقارير المدرسة ══ -->
<div id="tab-school_reports">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-folder-open"></i> تقارير المدرسة</h2>
    <button class="btn bp1 bsm" id="sr-refresh-btn" onclick="loadSchoolReports()"><i class="fas fa-sync-alt"></i> تحديث</button>
  </div>

  <!-- شبكة المجلدات -->
  <div id="sr-grid" class="section" style="margin-top:12px">
    <div id="sr-folders" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:18px;padding:4px"></div>
  </div>

  <!-- عرض الفئة -->
  <div id="sr-cat-view" style="display:none">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
      <button class="btn bp1 bsm" onclick="srBack()"><i class="fas fa-arrow-right"></i> رجوع</button>
      <h2 class="pt" id="sr-cat-title" style="margin:0;font-size:18px"></h2>
      <span id="sr-cat-badge" style="font-size:12px;padding:3px 12px;border-radius:20px;font-weight:700;color:#fff"></span>
    </div>

    <!-- نموذج رفع تقرير -->
    <div id="sr-upload-section" class="section" style="border:2px dashed #93c5fd;background:#eff6ff;display:none">
      <h4 style="margin:0 0 12px;color:#1d4ed8"><i class="fas fa-cloud-upload-alt"></i> رفع تقرير جديد</h4>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">عنوان التقرير *</label>
          <input id="sr-title" class="inp" type="text" placeholder="مثال: تقرير الغياب الشهري">
        </div>
        <div>
          <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">تاريخ التقرير *</label>
          <input id="sr-rdate" class="inp" type="date">
        </div>
      </div>
      <div style="margin-top:10px">
        <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">وصف التقرير</label>
        <textarea id="sr-desc" class="inp" rows="2" placeholder="وصف مختصر للتقرير..."></textarea>
      </div>
      <div style="margin-top:10px">
        <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">الملف *</label>
        <input id="sr-file" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png">
        <div style="font-size:11px;color:#64748b;margin-top:3px">PDF, Word, Excel, PowerPoint, صور — الحد الأقصى 20MB</div>
      </div>
      <div style="margin-top:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <button class="btn bp2" onclick="srUpload()"><i class="fas fa-upload"></i> رفع التقرير</button>
        <span id="sr-upload-st" style="font-size:13px"></span>
      </div>
    </div>

    <!-- قائمة التقارير -->
    <div class="section" style="margin-top:14px">
      <div id="sr-list"><div style="text-align:center;color:var(--mu);padding:40px">جاري التحميل...</div></div>
    </div>
  </div>
</div>



<div id="tab-tardiness_recipients">
  <h2 class="pt"><i class="fas fa-users"></i> مستلمو رسائل التأخر</h2>
  <div class="section">
    <div id="recipients-list"><div class="loading">⏳</div></div>
    <div style="margin-top:14px" class="fg2">
      <div class="fg"><label class="fl">الاسم</label><input type="text" id="rec-name" placeholder="اسم المستلم"></div>
      <div class="fg"><label class="fl">الجوال</label><input type="tel" id="rec-phone" placeholder="05xxxxxxxx"></div>
      <div class="fg"><label class="fl">الدور</label><select id="rec-role"><option>مدير</option><option>وكيل</option><option>مشرف</option></select></div>
    </div>
    <button class="btn bp1" onclick="addRecipient()">+ إضافة مستلم</button>
    <div id="rec-st" style="margin-top:10px"></div>
  </div>
</div>

<div id="tab-schedule_links">
  <h2 class="pt"><i class="fas fa-calendar-alt"></i> جدولة الروابط التلقائية</h2>
  <div class="ab ai">💡 الروابط تُرسل تلقائياً للمعلمين في بداية كل حصة</div>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">الفصل</label><select id="sch-cls"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">اليوم</label><select id="sch-day"><option value="0">الأحد</option><option value="1">الاثنين</option><option value="2">الثلاثاء</option><option value="3">الأربعاء</option><option value="4">الخميس</option></select></div>
      <div class="fg"><label class="fl">الحصة</label><select id="sch-per"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option><option value="6">6</option><option value="7">7</option></select></div>
      <div class="fg"><label class="fl">المعلم</label><input type="text" id="sch-tch" placeholder="اسم المعلم"></div>
    </div>
    <button class="btn bp1" onclick="addScheduleItem()">+ إضافة</button>
    <div id="sch-st" style="margin-top:10px"></div>
  </div>
  <div class="section"><div class="st">الجدول الحالي</div><div id="sch-tbl"><div class="loading">⏳</div></div></div>
</div>

<div id="tab-student_mgmt">
  <h2 class="pt"><i class="fas fa-graduation-cap"></i> إدارة الطلاب</h2>
  <div class="section">
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:14px">
      <div class="fg" style="flex:1;min-width:200px"><label class="fl">بحث</label><input type="text" id="sm-q" placeholder="اسم أو رقم الطالب..." oninput="filterStudents()"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="sm-cls" onchange="filterStudents()"><option value="">الكل</option></select></div>
    </div>
    <div id="sm-sum" style="margin-bottom:10px"></div>
    <div class="tw"><table>
      <thead><tr><th>رقم الهوية</th><th>الاسم</th><th>الصف</th><th>الفصل</th><th>الجوال</th><th>تعديل</th><th>حذف</th></tr></thead>
      <tbody id="sm-table"></tbody></table></div>
  </div>
</div>

<div id="tab-add_student">
  <h2 class="pt"><i class="fas fa-user-plus"></i> إضافة طالب</h2>
  <div class="it">
    <button class="itb active" onclick="si('add_student','as-man')">يدوي</button>
    <button class="itb" onclick="si('add_student','as-xl')">Excel</button>
    <button class="itb" onclick="si('add_student','as-noor')">نور</button>
  </div>
  <div id="as-man" class="ip active">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">رقم الهوية</label><input type="text" id="as-id" placeholder="10xxxxxxxxx"></div>
        <div class="fg"><label class="fl">الاسم الكامل</label><input type="text" id="as-name"></div>
        <div class="fg"><label class="fl">الصف</label><select id="as-level"><option>أول ثانوي</option><option>ثاني ثانوي</option><option>ثالث ثانوي</option></select></div>
        <div class="fg"><label class="fl">الفصل</label><select id="as-cls"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">جوال ولي الأمر</label><input type="tel" id="as-phone" placeholder="05xxxxxxxx"></div>
      </div>
      <button class="btn bp1" onclick="addStudentManual()">+ إضافة</button>
      <div id="as-st" style="margin-top:10px"></div>
    </div>
  </div>
  <div id="as-xl" class="ip">
    <div class="section">
      <div class="ab ai">📌 Excel بأعمدة: رقم الهوية، الاسم، الصف، الفصل، جوال ولي الأمر</div>
      <input type="file" id="as-xl-file" accept=".xlsx,.xls">
      <button class="btn bp1" style="margin-top:12px" onclick="importExcel()">📥 استيراد</button>
      <div id="as-xl-st" style="margin-top:10px"></div>
    </div>
  </div>
  <div id="as-noor" class="ip">
    <div class="section">
      <div class="ab ai">📌 صدّر ملف الطلاب من نظام نور ثم ارفعه هنا</div>
      <input type="file" id="as-noor-file" accept=".xlsx,.xls">
      <button class="btn bp1" style="margin-top:12px" onclick="importNoor()">📥 استيراد من نور</button>
      <div id="as-noor-st" style="margin-top:10px"></div>
    </div>
  </div>
</div>

<div id="tab-class_naming">
  <h2 class="pt"><i class="fas fa-school"></i> إدارة الفصول</h2>
  <div class="section"><div id="cn-list"><div class="loading">⏳</div></div></div>
</div>

<div id="tab-phones">
  <h2 class="pt"><i class="fas fa-mobile-alt"></i> إدارة أرقام الجوالات</h2>
  <div class="section">
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:14px">
      <div class="fg" style="flex:1"><label class="fl">بحث</label><input type="text" id="ph-q" placeholder="اسم أو جوال..." oninput="filterStudents()"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="ph-cls" onchange="filterStudents()"><option value="">الكل</option></select></div>
    </div>
    <div class="tw"><table>
      <thead><tr><th>الطالب</th><th>الفصل</th><th>رقم الجوال</th><th>تعديل</th></tr></thead>
      <tbody id="ph-table"></tbody></table></div>
  </div>
</div>

<div id="tab-noor_export">
  <h2 class="pt"><i class="fas fa-cloud-upload-alt"></i> تصدير نور</h2>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="noor-date"></div>
      <div class="fg"><label class="fl">الفصل</label><select id="noor-cls"><option value="">كل الفصول</option></select></div>
    </div>
    <div class="bg-btn">
      <button class="btn bp4" onclick="exportNoor()"><i class="fas fa-file-download"></i> تصدير Excel لنور</button>
    </div>
    <div id="noor-st" style="margin-top:10px"></div>
  </div>
  <div class="section">
    <div class="st">التصدير التلقائي</div>
    <div class="fg2">
      <div class="fg"><label class="fl">وقت التصدير</label><input type="time" id="noor-time" value="13:00"></div>
      <div class="fg" style="justify-content:flex-end;align-items:flex-end">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer"><input type="checkbox" id="noor-auto"> تفعيل التصدير التلقائي</label>
      </div>
    </div>
    <button class="btn bp1" onclick="saveNoorCfg()">💾 حفظ</button>
  </div>
</div>

<div id="tab-results">
  <h2 class="pt"><i class="fas fa-medal"></i> نشر نتائج الطلاب</h2>
  <div class="it">
    <button class="itb active" onclick="si('results','res-up')">رفع النتائج</button>
    <button class="itb" onclick="si('results','res-ls');loadResults()">قائمة النتائج</button>
  </div>
  <div id="res-up" class="ip active">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">العام الدراسي</label><input type="text" id="res-year" placeholder="1446"></div>
        <div class="fg"><label class="fl">ملف PDF</label><input type="file" id="res-pdf" accept=".pdf"></div>
      </div>
      <button class="btn bp1" onclick="uploadResults()">📤 رفع</button>
      <div id="res-up-st" style="margin-top:10px"></div>
    </div>
  </div>
  <div id="res-ls" class="ip">
    <div class="section">
      <div class="fg"><label class="fl">بحث</label><input type="text" id="res-q" placeholder="اسم أو رقم هوية..."></div>
      <div class="tw" style="margin-top:14px"><table>
        <thead><tr><th>رقم الهوية</th><th>الطالب</th><th>الصف</th><th>العام</th><th>المعدل</th><th>عرض</th></tr></thead>
        <tbody id="res-table"></tbody></table></div>
    </div>
  </div>
</div>

<div id="tab-partial_absence">
  <h2 class="pt"><i class="fas fa-running"></i> هروب واستئذان</h2>
  <div class="section">
    <p style="font-size:13px;color:#64748B;margin:0 0 14px">
      يعرض الطلاب الذين حضروا الحصص الأولى ثم غابوا في حصص لاحقة — قد يكونون هاربين أو مستأذنين.
    </p>
    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px">
      <div class="fg"><label class="fl">التاريخ</label><input type="date" id="pa-date" style="width:auto"></div>
      <div class="fg">
        <label class="fl">اعتبر غائباً من الحصة</label>
        <select id="pa-min-period" style="width:auto">
          <option value="2">الثالثة فأكثر (حضر 1 و 2)</option>
          <option value="3">الرابعة فأكثر (حضر 1 و 2 و 3)</option>
          <option value="1">الثانية فأكثر (حضر 1 فقط)</option>
        </select>
      </div>
      <button class="btn bp1" onclick="loadPartialAbsences()">🔍 بحث</button>
    </div>
    <div id="pa-st" style="margin-bottom:10px"></div>
    <div id="pa-list"></div>
  </div>

  <div class="section" style="margin-top:16px;border-right:4px solid #dc2626">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div class="st" style="color:#dc2626;margin:0">🏃 تقرير الهاربين — الشهر الحالي</div>
      <button class="btn bp3 bsm" onclick="printSec('pa-escaped-report')">🖨️ طباعة</button>
    </div>
    <div id="pa-escaped-report"><div class="ab ai" style="font-size:13px">⏳ جارٍ التحميل...</div></div>
  </div>
</div>

<div id="tab-counselor">
  <h2 class="pt"><i class="fas fa-brain"></i> الموجّه الطلابي</h2>
  <div class="it">
    <button class="itb active" onclick="si('counselor','co-main');loadCounselorList();">📋 قائمة المحوّلين</button>
    <button class="itb" onclick="si('counselor','co-ses')">📝 تسجيل جلسة</button>
    <button class="itb" onclick="si('counselor','co-add')">➕ إضافة يدوية</button>
    <button class="itb" onclick="si('counselor','co-inq');loadCounselorInquiries()">📬 خطابات الاستفسار</button>
  </div>

  <!-- ── قائمة المحوّلين الموحَّدة (مرآة للتطبيق المكتبي) ── -->
  <div id="co-main" class="ip active">
    <div class="section">
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px">
        <input type="text" id="co-search" placeholder="🔍 ابحث باسم/فصل/رقم..." oninput="filterCounselorList()" style="flex:1;min-width:200px">
        <button class="btn bp1 bsm" onclick="loadCounselorList()"><i class="fas fa-sync-alt"></i> تحديث</button>
        <button class="btn bp4 bsm" onclick="exportTbl('co-main-tbl','الموجّه_الطلابي')"><i class="fas fa-file-download"></i> Excel</button>
      </div>
      <div id="co-main-info" style="margin-bottom:10px"></div>
      <div id="co-main-st" style="margin-bottom:8px"></div>
      <div class="tw"><table>
        <thead><tr>
          <th>الرقم</th><th>اسم الطالب</th><th>الفصل</th>
          <th>الغياب</th><th>التأخر</th><th>آخر إجراء</th><th>إجراءات</th>
        </tr></thead>
        <tbody id="co-main-tbl"></tbody>
      </table></div>
    </div>
  </div>

  <!-- ── تسجيل جلسة إرشادية ── -->
  <div id="co-ses" class="ip">
    <div class="section">
      <div class="st">📝 تسجيل جلسة إرشادية</div>
      <div class="fg2">
        <div class="fg"><label class="fl">التاريخ</label><input type="date" id="co-date"></div>
        <div class="fg"><label class="fl">الفصل</label><select id="co-cls" onchange="loadClsForCo()"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">الطالب</label><select id="co-stu"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">السبب</label><select id="co-reason"><option>غياب</option><option>تأخر</option><option>سلوك</option><option>أكاديمي</option><option>أخرى</option></select></div>
        <div class="fg" style="grid-column:1/-1"><label class="fl">الملاحظات</label><textarea id="co-notes" placeholder="تفاصيل الجلسة..."></textarea></div>
        <div class="fg"><label class="fl">الإجراء المتخذ</label><input type="text" id="co-action"></div>
      </div>
      <button class="btn bp1" onclick="saveCouSession()">💾 حفظ الجلسة</button>
      <div id="co-st" style="margin-top:10px"></div>
    </div>
    <div class="section"><div class="st">آخر الجلسات</div><div class="tw">
      <table><thead><tr><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>السبب</th><th>الإجراء</th></tr></thead>
      <tbody id="co-ses-tbl"></tbody></table></div></div>
  </div>

  <!-- ── إضافة طالب يدوياً للموجّه ── -->
  <div id="co-add" class="ip">
    <div class="section">
      <div class="st">➕ إضافة طالب لقائمة الموجّه يدوياً</div>
      <div class="fg2">
        <div class="fg"><label class="fl">الفصل</label><select id="coa-cls" onchange="loadClsForCoAdd()"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">الطالب</label><select id="coa-stu"><option value="">اختر</option></select></div>
        <div class="fg"><label class="fl">سبب الإضافة</label><select id="coa-reason"><option>غياب</option><option>تأخر</option><option>سلوك</option><option>أكاديمي</option><option>أخرى</option></select></div>
        <div class="fg" style="grid-column:1/-1"><label class="fl">ملاحظات</label><textarea id="coa-notes" placeholder="ملاحظات إضافية..."></textarea></div>
      </div>
      <button class="btn bp1" onclick="addCounselorManual(false)">✅ إضافة للموجّه</button>
      <div id="coa-st" style="margin-top:10px"></div>
    </div>
  </div>
  <!-- ── خطابات الاستفسار الأكاديمي ── -->
  <div id="co-inq" class="ip">
    <div class="section">
      <div class="st">📩 توجيه خطاب استفسار لمعلم</div>
      <div class="fg2">
        <div class="fg"><label class="fl">التاريخ</label><input type="date" id="coinq-date"></div>
        <div class="fg"><label class="fl">المعلم</label><select id="coinq-teacher"><option value="">اختر المعلم</option></select></div>
        <div class="fg"><label class="fl">الفصل</label><input type="text" id="coinq-class" placeholder="مثال: الأول ثانوي - أ"></div>
        <div class="fg"><label class="fl">المادة</label><input type="text" id="coinq-subject"></div>
        <div class="fg"><label class="fl">الطالب (أو "الكل")</label><input type="text" id="coinq-student" value="الكل"></div>
      </div>
      <button class="btn bp1" onclick="sendCounselorInquiry()">📤 إرسال الخطاب</button>
      <div id="coinq-st" style="margin-top:10px"></div>
    </div>
    <div class="section">
      <div class="st">📜 سجل الخطابات والردود</div>
      <div class="tw"><table>
        <thead><tr><th>التاريخ</th><th>المعلم</th><th>الفصل</th><th>المادة</th><th>الحالة</th><th>التفاصيل</th></tr></thead>
        <tbody id="coinq-tbl"></tbody>
      </table></div>
    </div>
  </div>
</div>

<div id="tab-school_settings">
  <h2 class="pt"><i class="fas fa-university"></i> إعدادات المدرسة</h2>
  <div class="it">
    <button class="itb active" onclick="si('school_settings','ss-gen')">عام</button>
    <button class="itb" onclick="si('school_settings','ss-msg')">الرسائل</button>
    <button class="itb" onclick="si('school_settings','ss-wa')">واتساب</button>
    <button class="itb" onclick="si('school_settings','ss-adv')">متقدم</button>
  </div>
  <div id="ss-gen" class="ip active">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">اسم المدرسة</label><input type="text" id="ss-name"></div>
        <div class="fg"><label class="fl">نوع المدرسة</label><select id="ss-gender"><option value="boys">بنين</option><option value="girls">بنات</option></select></div>
        <div class="fg"><label class="fl">عتبة الإشعارات (أيام)</label><input type="number" id="ss-thr" value="5" min="1"></div>
        <div class="fg"><label class="fl">عدد الحصص اليومية</label><input type="number" id="ss-per" value="7" min="1" max="10"></div>
      </div>
      <button class="btn bp1" onclick="saveSchoolSettings()">💾 حفظ</button>
      <div id="ss-st" style="margin-top:10px"></div>
    </div>
  </div>
  <div id="ss-msg" class="ip">
    <div class="section">
      <div class="st">قالب رسالة الغياب</div>
      <textarea id="ss-abs-tpl" rows="4" placeholder="{school_name} {student_name} {date} {guardian} {son}"></textarea>
      <div class="st" style="margin-top:14px">قالب رسالة التأخر</div>
      <textarea id="ss-tard-tpl" rows="4" placeholder="{student_name} {minutes_late} {date}"></textarea>
      <button class="btn bp1" style="margin-top:12px" onclick="saveMsgTemplates()">💾 حفظ القوالب</button>
    </div>
  </div>
  <div id="ss-wa" class="ip">
    <div class="section">
      <div class="st">إعدادات خادم واتساب</div>
      <div id="wa-ind" class="ab ai">🔄 جارٍ الفحص...</div>
      <div class="fg2">
        <div class="fg"><label class="fl">المنفذ (Port)</label><input type="number" id="wa-port" value="3000"></div>
        <div class="fg"><label class="fl">رقم واتساب المدرسة</label><input type="tel" id="ss-wa-phone" placeholder="9665XXXXXXXX" dir="ltr"></div>
      </div>
      <div class="bg-btn">
        <button class="btn bp1" onclick="checkWA()">🔍 فحص</button>
        <button class="btn bp4" onclick="alert('تشغيل الخادم — يعمل محلياً فقط')">▶️ تشغيل</button>
        <button class="btn bp2" onclick="saveWaSettings()">💾 حفظ الرقم</button>
      </div>
      <div id="ss-wa-st" style="margin-top:10px"></div>
    </div>
    <div class="section" style="margin-top:12px">
      <div class="st">رابط حفظ جهة الاتصال (vCard)</div>
      <div style="font-size:13px;color:#64748B;margin-bottom:10px">أرسل هذا الرابط لأولياء الأمور — عند الضغط عليه يفتح الجوال نافذة "حفظ جهة الاتصال" مباشرةً</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="text" id="sn-vcard-link" readonly dir="ltr"
               style="flex:1;min-width:200px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:8px 10px;font-size:13px;color:#334155">
        <button class="btn bp2 bsm" onclick="snCopyVcard()">📋 نسخ</button>
        <a id="sn-vcard-dl" href="#" class="btn bp1 bsm" download>⬇️ تجربة</a>
      </div>
      <div id="sn-vcard-st" style="margin-top:6px;font-size:12px"></div>
    </div>
    <div class="section" style="margin-top:12px;border:2px dashed #3B82F6;background:#EFF6FF">
      <div class="st" style="color:#1D4ED8;margin-bottom:10px"><i class="fas fa-save"></i> طلب حفظ رقم المدرسة</div>
      <div style="font-size:13px;color:#334155;margin-bottom:14px">
        أرسل رسالة مهذبة لأولياء الأمور تطلب منهم حفظ رقم المدرسة — هذا يقلل احتمال تقييد الحساب بشكل كبير.
      </div>
      <div class="fg2" style="margin-bottom:14px">
        <div class="fg"><label class="fl">الفصل</label>
          <select id="sn-cls"><option value="">جميع الفصول</option></select>
        </div>
      </div>
      <div style="background:white;border:1px solid #BFDBFE;border-radius:8px;padding:14px;font-size:13px;color:#1E293B;white-space:pre-wrap;line-height:2;margin-bottom:14px" id="sn-preview">⏳ جارٍ تحميل المعاينة...</div>
      <div class="bg-btn">
        <button class="btn bp1" onclick="sendSaveNumber()" id="sn-btn">📲 إرسال</button>
      </div>
      <div id="sn-progress" style="margin-top:10px;font-size:13px;color:var(--mu)"></div>
      <div id="sn-st" style="margin-top:8px"></div>
    </div>
  </div>
  <div id="ss-adv" class="ip">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">الرابط العام</label><input type="text" id="ss-url" placeholder="https://..."></div>
        <div class="fg"><label class="fl">جوال مستلم التقرير اليومي</label><input type="tel" id="ss-rpt-phone"></div>
        <div class="fg"><label class="fl">وقت إرسال التقرير</label><input type="time" id="ss-rpt-time" value="14:00"></div>
      </div>
      <button class="btn bp1" onclick="saveAdvSettings()">💾 حفظ</button>
    </div>
    <div class="section" style="margin-top:12px">
      <div class="st">🗄️ النسخ الاحتياطي التلقائي — Telegram</div>
      <p style="color:#64748B;font-size:13px;margin:6px 0 14px">
        أنشئ بوتاً عبر <b>@BotFather</b> في Telegram، أضفه لقناة خاصة كـ Admin،
        ثم ضع التوكن ومعرّف القناة هنا — سيُرسَل ملف النسخة الاحتياطية تلقائياً كل 24 ساعة.
      </p>
      <div class="fg2">
        <div class="fg">
          <label class="fl">Bot Token</label>
          <input type="text" id="ss-tg-token" placeholder="123456789:AAF..." dir="ltr" style="font-family:monospace;font-size:12px">
        </div>
        <div class="fg">
          <label class="fl">Chat ID / Channel ID</label>
          <input type="text" id="ss-tg-chat" placeholder="-1001234567890" dir="ltr" style="font-family:monospace;font-size:12px">
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
        <button class="btn bp1" onclick="saveTelegramBackup()">💾 حفظ</button>
        <button class="btn bp2" onclick="testTelegramBackup()">🧪 اختبار الآن</button>
      </div>
      <div id="tg-backup-st" style="margin-top:8px;font-size:13px"></div>
    </div>
    <div class="section" style="border:2px solid #dc2626;border-radius:10px;margin-top:16px">
      <div class="st" style="color:#dc2626">تحديث طارئ فوري</div>
      <p style="color:#555;font-size:13px;margin:8px 0 14px">يُنزِّل آخر إصدار من الخادم ويُعيد تشغيل البرنامج فوراً. استخدمه فقط عند الضرورة.</p>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <button class="btn" style="background:#dc2626;color:#fff;font-size:14px;padding:10px 22px" onclick="triggerEmergencyUpdate()">تحديث فوري الآن</button>
        <span id="eu-status" style="font-size:13px;color:#555"></span>
      </div>
    </div>
  </div>
</div>

<div id="tab-users">
  <h2 class="pt"><i class="fas fa-user-shield"></i> إدارة المستخدمين وصلاحيات التبويبات</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">

    <!-- ══ قائمة المستخدمين ══ -->
    <div class="section" style="padding:14px">
      <div class="st" style="margin-bottom:10px">قائمة المستخدمين</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">
        <button class="btn bp1 bsm" onclick="usOpenAdd()">➕ جديد</button>
        <button class="btn bp2 bsm" onclick="usToggle()">🔄 تفعيل/تعطيل</button>
        <button class="btn bp2 bsm" onclick="usChangePw()">🔑 كلمة المرور</button>
        <button class="btn bp3 bsm" onclick="usDelete()">🗑 حذف</button>
        <button class="btn bsm" style="background:#0f6e56;color:white" onclick="usSendCreds()">📤 إرسال البيانات</button>
      </div>
      <div class="tw">
        <table id="us-tbl" style="width:100%;font-size:12px">
          <thead><tr>
            <th>ID</th><th>اسم المستخدم</th><th>الاسم الكامل</th>
            <th>الدور</th><th>الحالة</th><th>آخر ظهور</th>
          </tr></thead>
          <tbody id="us-tbody"></tbody>
        </table>
      </div>
      <div id="us-st" style="margin-top:8px;font-size:13px"></div>
    </div>

    <!-- ══ صلاحيات التبويبات ══ -->
    <div class="section" style="padding:14px">
      <div class="st" style="margin-bottom:6px">صلاحيات التبويبات</div>
      <div id="us-perm-title" style="font-size:13px;font-weight:700;color:var(--pr);margin-bottom:10px">← اختر مستخدماً من القائمة</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
        <button class="btn bp1 bsm" onclick="usSaveTabs()">💾 حفظ الصلاحيات</button>
        <button class="btn bp2 bsm" onclick="usResetTabs()">↩ افتراضي للدور</button>
        <button class="btn bp2 bsm" onclick="usSelAll(true)">تحديد الكل</button>
        <button class="btn bp2 bsm" onclick="usSelAll(false)">إلغاء الكل</button>
      </div>
      <div id="us-tabs-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:4px;max-height:420px;overflow-y:auto"></div>
    </div>
  </div>

  <!-- مودال إضافة مستخدم -->
  <div id="us-add-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;align-items:center;justify-content:center">
    <div style="background:white;border-radius:14px;padding:28px;width:360px;direction:rtl">
      <div style="font-size:16px;font-weight:700;margin-bottom:16px;color:var(--pr)">➕ إضافة مستخدم جديد</div>
      <div class="fg" style="margin-bottom:10px"><label class="fl">اسم المستخدم</label><input type="text" id="us-new-uname" style="width:100%"></div>
      <div class="fg" style="margin-bottom:10px"><label class="fl">الاسم الكامل</label><input type="text" id="us-new-fname" style="width:100%"></div>
      <div class="fg" style="margin-bottom:10px"><label class="fl">كلمة المرور</label><input type="text" id="us-new-pw" style="width:100%"></div>
      <div class="fg" style="margin-bottom:16px"><label class="fl">الدور</label>
        <select id="us-new-role" style="width:100%">
          <option value="admin">مدير</option>
          <option value="deputy">وكيل</option>
          <option value="staff">إداري</option>
          <option value="counselor">موجه طلابي</option>
          <option value="activity_leader">رائد نشاط</option>
          <option value="teacher" selected>معلم</option>
          <option value="lab">محضر</option>
          <option value="guard">حارس</option>
        </select>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn bp1" onclick="usAddConfirm()">حفظ</button>
        <button class="btn bp2" onclick="document.getElementById('us-add-modal').style.display='none'">إلغاء</button>
      </div>
      <div id="us-add-st" style="margin-top:8px;font-size:13px"></div>
    </div>
  </div>

  <!-- مودال إرسال بيانات الدخول -->
  <div id="us-creds-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;align-items:center;justify-content:center">
    <div style="background:white;border-radius:14px;padding:28px;width:400px;max-width:95vw;direction:rtl">
      <div style="font-size:16px;font-weight:700;margin-bottom:6px;color:#0f6e56">📤 إرسال بيانات الدخول</div>
      <p style="font-size:13px;color:#64748B;margin:0 0 16px">سيتم إنشاء كلمة مرور جديدة وإرسالها للمستخدم عبر واتساب</p>
      <div class="fg" style="margin-bottom:10px">
        <label class="fl">الاسم الكامل</label>
        <input type="text" id="uc-name" readonly style="width:100%;background:#f8fafc;color:#334155">
      </div>
      <div class="fg" style="margin-bottom:10px">
        <label class="fl">اسم المستخدم</label>
        <input type="text" id="uc-uname" readonly style="width:100%;background:#f8fafc;color:#334155;direction:ltr">
      </div>
      <div class="fg" style="margin-bottom:16px">
        <label class="fl">رقم الجوال <span style="color:#dc2626">*</span></label>
        <input type="tel" id="uc-phone" placeholder="9665XXXXXXXX" dir="ltr" style="width:100%">
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn" style="background:#0f6e56;color:white" onclick="usSendCredsConfirm()">📤 إرسال</button>
        <button class="btn bp2" onclick="document.getElementById('us-creds-modal').style.display='none'">إلغاء</button>
      </div>
      <div id="uc-st" style="margin-top:10px;font-size:13px"></div>
    </div>
  </div>
</div>

<div id="tab-backup">
  <h2 class="pt"><i class="fas fa-hdd"></i> النسخ الاحتياطية</h2>
  <div class="section">
    <div class="bg-btn" style="margin-bottom:16px">
      <button class="btn bp1" onclick="createBackup()">💾 إنشاء نسخة الآن</button>
      <button class="btn bp2" onclick="loadBackups()">🔄 تحديث</button>
    </div>
    <div id="bk-st" style="margin-bottom:10px"></div>
    <div class="tw"><table>
      <thead><tr><th>الملف</th><th>الحجم</th><th>التاريخ</th><th>تنزيل</th><th>استعادة</th></tr></thead>
      <tbody id="bk-table"></tbody></table></div>
  </div>
</div>

<div id="bk-restore-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;align-items:center;justify-content:center">
  <div style="background:#fff;border-radius:14px;padding:28px;width:360px;max-width:95vw;box-shadow:0 8px 32px rgba(0,0,0,.25)">
    <h3 style="margin:0 0 6px;font-size:16px;color:#1e293b">↩️ استعادة نسخة احتياطية</h3>
    <p id="bk-restore-fname" style="font-size:12px;color:#64748b;margin:0 0 14px;word-break:break-all;direction:ltr;text-align:right"></p>
    <div class="ab ae" style="margin-bottom:14px;font-size:13px">⚠️ سيتم استبدال جميع البيانات الحالية. سيُنشأ backup تلقائي من وضعك الحالي قبل الاستعادة.</div>
    <div class="fg"><label class="fl">كلمة مرور حسابك</label><input type="password" id="bk-restore-pw" placeholder="أدخل كلمة المرور للتأكيد" onkeydown="if(event.key==='Enter')doRestore()"></div>
    <div id="bk-restore-st" style="margin:10px 0;min-height:22px"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:4px">
      <button class="btn bp2" onclick="closeBkModal()">إلغاء</button>
      <button class="btn bp3" onclick="doRestore()">↩️ استعادة</button>
    </div>
  </div>
</div>

<div id="tab-quick_notes">
  <h2 class="pt"><i class="fas fa-envelope"></i> الرسائل الداخلية</h2>
  <div class="it">
    <button class="itb active" id="inbox-tab-in"  onclick="inboxSwitch('inbox')">📥 الوارد <span id="inbox-unread-badge" style="background:#ef4444;color:white;border-radius:20px;padding:1px 7px;font-size:11px;display:none"></span></button>
    <button class="itb"        id="inbox-tab-out" onclick="inboxSwitch('sent')">📤 المرسل</button>
    <button class="itb"        id="inbox-tab-new" onclick="inboxSwitch('compose')">✉️ رسالة جديدة</button>
  </div>

  <!-- صندوق الوارد -->
  <div id="inbox-pane-inbox" class="ip active">
    <div class="section">
      <div id="inbox-list" style="display:flex;flex-direction:column;gap:8px"><div class="loading">⏳</div></div>
    </div>
  </div>

  <!-- المرسل -->
  <div id="inbox-pane-sent" class="ip">
    <div class="section">
      <div id="inbox-sent-list" style="display:flex;flex-direction:column;gap:8px"><div class="loading">⏳</div></div>
    </div>
  </div>

  <!-- إنشاء رسالة -->
  <div id="inbox-pane-compose" class="ip">
    <div class="section">
      <div class="fg2">
        <div class="fg"><label class="fl">إلى</label><select id="inbox-to" style="width:100%"><option value="">اختر المستلم...</option></select></div>
        <div class="fg"><label class="fl">الموضوع</label><input type="text" id="inbox-subject" placeholder="موضوع الرسالة"></div>
        <div class="fg" style="grid-column:1/-1"><label class="fl">نص الرسالة</label><textarea id="inbox-body" rows="5" placeholder="اكتب رسالتك هنا..."></textarea></div>
      <div class="fg" style="grid-column:1/-1">
        <label class="fl">مرفق (صورة أو ملف — حد أقصى 20 ميغابايت)</label>
        <input type="file" id="inbox-attachment" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.zip"
               onchange="inboxAttachmentChanged(this)">
        <div id="inbox-att-preview" style="margin-top:6px;font-size:12px;color:#64748B"></div>
      </div>
      </div>
      <div class="bg-btn" style="margin-top:10px">
        <button class="btn bp1" onclick="inboxSend()">📤 إرسال</button>
        <button class="btn bp2 bsm" onclick="inboxClearAttachment()">🗑️ إزالة المرفق</button>
      </div>
      <div id="inbox-compose-st" style="margin-top:8px"></div>
    </div>
  </div>

  <!-- عرض رسالة (مخفي افتراضياً) -->
  <div id="inbox-msg-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;align-items:center;justify-content:center">
    <div style="background:white;border-radius:12px;padding:24px;max-width:560px;width:90%;max-height:80vh;overflow-y:auto;position:relative">
      <button onclick="inboxCloseMsg()" style="position:absolute;top:12px;left:12px;background:none;border:none;font-size:20px;cursor:pointer">✕</button>
      <div id="inbox-msg-content"></div>
    </div>
  </div>
</div>

<div id="tab-lab_submissions">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
    <h2 class="pt"><i class="fas fa-clipboard-check"></i> شواهد الأداء الوظيفي</h2>
    <a href="/web/lab-docs/submissions" target="_blank"
       style="background:#1565C0;color:white;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:700">
      ↗ فتح في نافذة جديدة
    </a>
  </div>
  <iframe src="/web/lab-docs/submissions"
          style="width:100%;height:calc(100vh - 160px);border:none;border-radius:12px;background:white"
          id="lab-subs-frame"
          onload="this.style.opacity=1"
          style="opacity:0;transition:opacity .3s">
  </iframe>
</div>

<div id="tab-referral_teacher">
  <h2 class="pt"><i class="fas fa-exchange-alt"></i> تحويل طالب إلى الوكيل</h2>
  <div class="it">
    <button class="itb active" onclick="si('referral_teacher','rt-new');loadRefStudents()">➕ تحويل جديد</button>
    <button class="itb" onclick="si('referral_teacher','rt-hist');loadRefHistory()">📜 سجل تحويلاتي</button>
  </div>
  <div id="rt-new" class="ip active">
    <div class="section">
      <div class="st">بيانات الطالب والمخالفة</div>
      <div class="fg2">
        <div class="fg"><label class="fl">الطالب</label><select id="rt-stu" onchange="rtAutoClass()"><option value="">اختر طالباً</option></select></div>
        <div class="fg"><label class="fl">الفصل</label><input type="text" id="rt-cls" readonly style="background:#f9f9f9"></div>
        <div class="fg"><label class="fl">المادة</label><input type="text" id="rt-subj"></div>
        <div class="fg"><label class="fl">الحصة</label><select id="rt-per"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option><option>6</option><option>7</option><option>8</option></select></div>
        <div class="fg"><label class="fl">الوقت</label><div style="display:flex;gap:4px"><input type="time" id="rt-time" style="width:100%"></div></div>
        <div class="fg"><label class="fl">نوع المخالفة</label><select id="rt-vtype"><option>سلوكية</option><option>تربوية</option><option>أخرى</option></select></div>
        <div class="fg" style="grid-column:1/-1"><label class="fl">وصف المخالفة</label><input type="text" id="rt-violation"></div>
        <div class="fg" style="grid-column:1/-1"><label class="fl">أسباب التحويل</label><textarea id="rt-causes" rows="2"></textarea></div>
        <div class="fg"><label class="fl">تكرار المشكلة</label><select id="rt-repeat"><option>الأول</option><option>الثاني</option><option>الثالث</option><option>الرابع</option></select></div>
      </div>
      <div class="st" style="margin-top:14px">الإجراءات المتخذة</div>
      <div class="fg"><input type="text" id="rt-act1" placeholder="1. "></div>
      <div class="fg"><input type="text" id="rt-act2" placeholder="2. "></div>
      <button class="btn bp1" style="margin-top:12px" onclick="submitTeacherReferral()">📤 إرسال التحويل</button>
      <div id="rt-st" style="margin-top:10px"></div>
    </div>
  </div>
  <div id="rt-hist" class="ip">
    <div class="section"><div class="tw"><table>
      <thead><tr><th>رقم</th><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>الحالة</th><th>التفاصيل</th></tr></thead>
      <tbody id="rt-hist-tbl"></tbody>
    </table></div></div>
  </div>
</div>

<div id="tab-referral_deputy">
  <h2 class="pt"><i class="fas fa-inbox"></i> إدارة تحويلات الطلاب</h2>
  <div class="section">
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <select id="rd-filter" onchange="loadDeputyReferrals()"><option value="all">الكل</option><option value="pending">بانتظار الوكيل</option><option value="with_deputy">مع الوكيل</option><option value="with_counselor">مع الموجه</option><option value="resolved">مغلق</option></select>
      <button class="btn bp1 bsm" onclick="loadDeputyReferrals()">🔄 تحديث</button>
    </div>
    <div class="tw"><table>
      <thead><tr><th>رقم</th><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>المعلم</th><th>الحالة</th><th>إجراء</th></tr></thead>
      <tbody id="rd-tbl"></tbody>
    </table></div>
  </div>
</div>

<div id="tab-parent_visits">
  <h2 class="pt"><i class="fas fa-users"></i> سجل زيارات أولياء الأمور</h2>

  <!-- ── شريط التحكم ── -->
  <div class="section" style="padding:12px 16px">
    <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
      <label class="fl" style="white-space:nowrap">من:</label>
      <input type="date" id="pv-from" style="width:130px">
      <label class="fl" style="white-space:nowrap">إلى:</label>
      <input type="date" id="pv-to" style="width:130px">
      <button class="btn bp1 bsm" onclick="pvLoad()"><i class="fas fa-sync-alt"></i> عرض</button>
      <button class="btn bp4 bsm" onclick="pvOpenAdd()"><i class="fas fa-plus"></i> تسجيل زيارة</button>
      <button class="btn bsm" style="background:#f1f5f9;color:#475569" onclick="exportTbl('pv-tbl','زيارات_أولياء_الأمور')"><i class="fas fa-file-download"></i> Excel</button>
      <button class="btn bsm" style="background:#0d47a1;color:#fff" onclick="pvPrintReport()"><i class="fas fa-print"></i> طباعة التقرير</button>
      <input type="text" id="pv-search" placeholder="🔍 بحث..." oninput="pvFilter()"
             style="width:160px;margin-right:auto">
    </div>
  </div>

  <!-- ── إحصائيات سريعة ── -->
  <div class="stat-cards" id="pv-stats" style="margin-bottom:10px"></div>

  <!-- ── جدول السجلات ── -->
  <div class="section">
    <div class="tw"><table>
      <thead><tr>
        <th>#</th><th>التاريخ</th><th>الوقت</th><th>الطالب</th><th>الفصل</th>
        <th>اسم ولي الأمر</th><th>سبب الزيارة</th><th>الجهة المستقبلة</th>
        <th>نتيجة الزيارة</th><th>ملاحظات</th><th>إجراء</th>
      </tr></thead>
      <tbody id="pv-tbl"></tbody>
    </table></div>
    <div id="pv-empty" style="text-align:center;padding:30px;color:#94a3b8;display:none">
      <i class="fas fa-users fa-2x" style="margin-bottom:8px;display:block"></i>
      لا توجد زيارات في هذه الفترة
    </div>
  </div>

  <!-- ── مودال إضافة زيارة ── -->
  <div id="pv-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:900;align-items:center;justify-content:center">
    <div style="background:#fff;border-radius:14px;padding:28px 32px;width:min(560px,96vw);max-height:90vh;overflow-y:auto;box-shadow:0 8px 40px rgba(0,0,0,.2)">
      <h3 style="margin:0 0 20px;color:#1565C0;font-size:1.1rem">
        <i class="fas fa-user-plus"></i> تسجيل زيارة ولي أمر
      </h3>
      <div class="fg2">
        <div class="fg">
          <label class="fl">التاريخ <span style="color:red">*</span></label>
          <input type="date" id="pv-add-date">
        </div>
        <div class="fg">
          <label class="fl">الوقت <span style="color:red">*</span></label>
          <select id="pv-add-time"></select>
        </div>
        <div class="fg">
          <label class="fl">الفصل <span style="color:red">*</span></label>
          <select id="pv-add-cls" onchange="pvLoadStudents()"><option value="">اختر الفصل</option></select>
        </div>
        <div class="fg">
          <label class="fl">الطالب <span style="color:red">*</span></label>
          <select id="pv-add-stu" onchange="pvFillGuardian()"><option value="">اختر الطالب</option></select>
        </div>
        <div class="fg">
          <label class="fl">اسم ولي الأمر</label>
          <input type="text" id="pv-add-grd" readonly
                 style="background:#f8fafc;color:#475569;cursor:default"
                 placeholder="يملأ تلقائياً">
        </div>
        <div class="fg">
          <label class="fl">سبب الزيارة <span style="color:red">*</span></label>
          <select id="pv-add-reason">
            <option value="">اختر السبب</option>
            <option>غياب الطالب</option>
            <option>التأخر المتكرر</option>
            <option>السلوك والانضباط</option>
            <option>المتابعة الأكاديمية</option>
            <option>طلب إجازة</option>
            <option>استفسار عام</option>
            <option>تسليم وثيقة</option>
            <option>أخرى</option>
          </select>
        </div>
        <div class="fg">
          <label class="fl">الجهة المستقبلة <span style="color:red">*</span></label>
          <select id="pv-add-rcv">
            <option value="">اختر الجهة</option>
            <option>المدير</option>
            <option>الوكيل</option>
            <option>المرشد الطلابي</option>
            <option>الإداري</option>
            <option>المعلم</option>
            <option>أخرى</option>
          </select>
        </div>
        <div class="fg">
          <label class="fl">نتيجة الزيارة <span style="color:red">*</span></label>
          <select id="pv-add-result">
            <option value="">اختر النتيجة</option>
            <option>تم التوجيه والإرشاد</option>
            <option>تم الإشعار والتنبيه</option>
            <option>اتخذ إجراء رسمي</option>
            <option>تم الاستلام وقيد الدراسة</option>
            <option>لم يُتخذ إجراء</option>
            <option>أخرى</option>
          </select>
        </div>
        <div class="fg" style="grid-column:1/-1">
          <label class="fl">ملاحظات</label>
          <textarea id="pv-add-notes" rows="3"
                    placeholder="أي تفاصيل أو ملاحظات إضافية..."></textarea>
        </div>
      </div>
      <div id="pv-add-st" style="margin:10px 0;min-height:20px"></div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:8px">
        <button class="btn bp1" onclick="pvSave()"><i class="fas fa-save"></i> حفظ</button>
        <button class="btn" style="background:#f1f5f9;color:#475569"
                onclick="document.getElementById('pv-modal').style.display='none'">إلغاء</button>
      </div>
    </div>
  </div>
</div>

<div id="tab-teacher_forms">
  <h2 class="pt"><i class="fas fa-file-contract"></i> نماذج المعلم</h2>
  <div class="ab ai">اختر النموذج المراد تعبئته، وسيقوم النظام بتوليد ملف PDF وإرساله للمدير. (يتطلب اتصال واتساب للرسائل)</div>
  <div class="stat-cards">
    <div class="sc" onclick="si('teacher_forms','tf-lesson')" style="cursor:pointer;background:#F0FDF4;border-color:#BBF7D0">
      <div class="v" style="color:#166534"><i class="fas fa-book"></i></div><div class="l">نموذج تحضير الدرس</div>
    </div>
    <div class="sc" onclick="si('teacher_forms','tf-prog')" style="cursor:pointer;background:#EFF6FF;border-color:#BFDBFE">
      <div class="v" style="color:#1D4ED8"><i class="fas fa-chart-line"></i></div><div class="l">تقرير تنفيذ البرنامج</div>
    </div>
    <div class="sc" onclick="si('teacher_forms','tf-inq');loadTeacherInquiries()" style="cursor:pointer;background:#FAF5FF;border-color:#E9D5FF">
      <div class="v" style="color:#7E22CE"><i class="fas fa-envelope-open-text"></i></div><div class="l">استفسارات الموجّه</div>
    </div>
  </div>
  
  <div id="tf-lesson" class="ip" style="margin-top:16px">
    <div class="section"><div class="st">📘 نموذج تحضير الدرس</div>
      <div class="fg2">
        <div class="fg"><label class="fl">المرحلة الدراسية</label><select id="tfl-grade"><option>الأول ثانوي</option><option>الثاني ثانوي</option><option>الثالث ثانوي</option></select></div>
        <div class="fg"><label class="fl">الفصل</label><input type="text" id="tfl-cls" value="جميع الفصول"></div>
        <div class="fg"><label class="fl">عدد الطلاب</label><input type="number" id="tfl-count" value="30"></div>
        <div class="fg"><label class="fl">المادة</label><input type="text" id="tfl-subj"></div>
        <div class="fg"><label class="fl">التاريخ</label><input type="date" id="tfl-date"></div>
        <div class="fg"><label class="fl">عنوان الدرس</label><input type="text" id="tfl-lesson"></div>
        <div class="fg"><label class="fl">الاستراتيجية</label><input type="text" id="tfl-strat" placeholder="اكتب الاستراتيجية..."></div>
      </div>
      <div class="st" style="margin-top:14px">الأدوات والوسائل التعليمية</div>
      <div id="tfl-tools" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px;margin-bottom:10px">
        <label><input type="checkbox" value="سبورة تقليدية" checked> سبورة تقليدية</label>
        <label><input type="checkbox" value="جهاز عرض"> جهاز عرض</label>
        <label><input type="checkbox" value="سبورة ذكية"> سبورة ذكية</label>
        <label><input type="checkbox" value="جهاز الحاسب"> جهاز الحاسب</label>
        <label><input type="checkbox" value="بطاقات تعليمية"> بطاقات تعليمية</label>
        <label><input type="checkbox" value="أوراق عمل"> أوراق عمل</label>
      </div>
      <div class="st" style="margin-top:14px">الأهداف (كل هدف بسطر)</div>
      <textarea id="tfl-goals" rows="4"></textarea>
      <div class="st" style="margin-top:14px">الشواهد (نصي)</div>
      <textarea id="tfl-evidence" rows="3"></textarea>
      <div class="fg" style="margin-top:8px"><label class="fl">صورة شاهد (اختياري)</label><input type="file" id="tfl-ev-img" accept="image/*"></div>
      <div class="section" style="margin-top:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px">
        <div class="st" style="margin-bottom:8px">التواقيع</div>
        <div class="fg2">
          <div class="fg"><label class="fl">اسم المنفذ</label><input type="text" id="tfl-executor" placeholder="يُملأ تلقائياً من حسابك"></div>
          <div class="fg"><label class="fl">مدير المدرسة</label><input type="text" id="tfl-principal" value="حسن محمد عبيري"></div>
        </div>
      </div>
      <div class="bg-btn" style="margin-top:12px">
        <button class="btn bp1" onclick="submitTeacherForm('lesson', false)">تحميل PDF</button>
        <button class="btn bp4" onclick="submitTeacherForm('lesson', true)">📲 واتساب</button>
        <button class="btn" style="background:#7c3aed;color:#fff" onclick="submitTeacherFormPortal('lesson')">📤 إرسال للإدارة</button>
      </div><div id="tfl-st"></div>
    </div>
  </div>
  
  <div id="tf-prog" class="ip" style="margin-top:16px">
    <div class="section"><div class="st">📊 تقرير التنفيذ</div>
      <div class="fg2">
        <div class="fg"><label class="fl">تاريخ التنفيذ</label><input type="date" id="tfp-date"></div>
        <div class="fg"><label class="fl">المنفذ</label><input type="text" id="tfp-exec"></div>
        <div class="fg"><label class="fl">مكان التنفيذ</label><input type="text" id="tfp-place"></div>
        <div class="fg"><label class="fl">المستهدفون</label><input type="text" id="tfp-target"></div>
        <div class="fg"><label class="fl">عدد المستفيدين</label><input type="number" id="tfp-count" value="30"></div>
      </div>
      <div class="st" style="margin-top:14px">الأهداف (كل هدف بسطر)</div>
      <textarea id="tfp-goals" rows="4"></textarea>
      <div class="fg2" style="margin-top:8px">
        <div class="fg"><label class="fl">صورة الشاهد 1 (اختياري)</label><input type="file" id="tfp-img1" accept="image/*"></div>
        <div class="fg"><label class="fl">صورة الشاهد 2 (اختياري)</label><input type="file" id="tfp-img2" accept="image/*"></div>
      </div>
      <div class="section" style="margin-top:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px">
        <div class="st" style="margin-bottom:8px">التواقيع</div>
        <div class="fg2">
          <div class="fg"><label class="fl">اسم المنفذ</label><input type="text" id="tfp-executor" placeholder="يُملأ تلقائياً من حسابك"></div>
          <div class="fg"><label class="fl">مدير المدرسة</label><input type="text" id="tfp-principal" value="حسن محمد عبيري"></div>
        </div>
      </div>
      <div class="bg-btn" style="margin-top:12px">
        <button class="btn bp1" onclick="submitTeacherForm('program', false)">تحميل PDF</button>
        <button class="btn bp4" onclick="submitTeacherForm('program', true)">📲 واتساب</button>
        <button class="btn" style="background:#7c3aed;color:#fff" onclick="submitTeacherFormPortal('program')">📤 إرسال للإدارة</button>
      </div><div id="tfp-st"></div>
    </div>
  </div>
  
  <div id="tf-inq" class="ip" style="margin-top:16px">
    <div class="section"><div class="st">📬 استفسارات الموجّه الطلابي</div>
      <div class="tw"><table>
        <thead><tr><th>التاريخ</th><th>الفصل</th><th>المادة</th><th>الطالب</th><th>الحالة</th><th>إجراء</th></tr></thead>
        <tbody id="tfinq-tbl"></tbody>
      </table></div>
    </div>
    <div id="tfinq-reply-form" class="section" style="display:none;background:#F8FAFC;border:2px solid #E2E8F0">
      <div class="st" id="tfinq-reply-title">رد على استفسار</div>
      <input type="hidden" id="tfinq-id">
      <div class="fg" style="margin-bottom:12px">
        <label class="fl">إفادة المعلم (الأسباب)</label>
        <textarea id="tfinq-reasons" rows="4" placeholder="اكتب أسباب تدني المستوى..."></textarea>
      </div>
      <div class="fg" style="margin-bottom:12px">
        <label class="fl">شواهد المعلم (نص)</label>
        <textarea id="tfinq-evidence" rows="3" placeholder="الشواهد والإشعارات..."></textarea>
      </div>
      <div class="fg" style="margin-bottom:12px">
        <label class="fl">ملف شواهد (اختياري - صورة)</label>
        <input type="file" id="tfinq-file" accept="image/*">
      </div>
      <div class="bg-btn">
        <button class="btn bp1" onclick="submitTeacherInquiryReply()">📤 إرسال الإفادة</button>
        <button class="btn bp2" onclick="document.getElementById('tfinq-reply-form').style.display='none'">❌ إلغاء</button>
      </div>
      <div id="tfinq-st" style="margin-top:10px"></div>
    </div>
  </div>
</div>

<!-- Modal for Deputy Actions -->
<div id="rd-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200;padding:20px;overflow-y:auto">
  <div style="background:#fff;max-width:600px;margin:30px auto;border-radius:12px;padding:20px;position:relative;box-shadow:var(--sh)">
    <button onclick="document.getElementById('rd-modal').style.display='none'" style="position:absolute;left:15px;top:15px;background:none;border:none;font-size:20px;cursor:pointer">✖</button>
    <div class="pt">تفاصيل التحويل <span id="rd-m-id" class="badge bg"></span></div>
    <div id="rd-m-details" style="font-size:13px;line-height:1.6;margin-bottom:16px;background:#f8fafc;padding:12px;border-radius:8px"></div>
    <div class="st">إجراءات الوكيل</div>
    <div class="fg2" style="background:#fff;padding:10px;border:1px solid var(--bd);border-radius:8px">
      <div class="fg"><label class="fl">تاريخ المقابلة</label><input type="date" id="rd-m-date"></div>
      <div class="fg"><label class="fl">عمل رئيسي</label><select id="rd-m-act1"><option>التوجيه والإرشاد</option><option>الاتصال بولي الأمر</option><option>أخرى</option></select></div>
      <div class="fg" style="grid-column:1/-1"><label class="fl">إجراءات أخرى (اختياري)</label><input type="text" id="rd-m-act2"></div>
    </div>
    <div id="rd-m-st"></div>
    <div class="bg-btn" style="margin-top:16px;border-top:1px solid var(--bd);padding-top:14px">
      <button class="btn bp1" onclick="saveDeputyAction(false)">💾 حفظ</button>
      <button class="btn bp4" onclick="saveDeputyAction(true)">🧠 تحويل للموجّه</button>
      <button class="btn bp3" onclick="closeDeputyReferral()">✅ حل وإغلاق</button>
    </div>
  </div>
</div>
<!-- ── تبويب تعزيز الحضور الأسبوعي ────────────────── -->
<div id="tab-weekly_reward">
  <h2 class="pt"><i class="fas fa-medal"></i> تعزيز الحضور الأسبوعي</h2>
  <div class="cards" style="margin-bottom:20px">
    <div class="card g"><div class="v" id="wr-count">0</div><div>طالباً ملتزماً</div></div>
    <div class="card"><div class="v" id="wr-sent">0</div><div>تم الإرسال</div></div>
    <div class="card r"><div class="v" id="wr-failed">0</div><div>فشل الإرسال</div></div>
  </div>

  <div class="section">
    <div class="st">التحقق من طلاب الأسبوع</div>
    <div class="fg2">
      <div class="fg"><label class="fl">من تاريخ</label><input type="date" id="wr-from"></div>
      <div class="fg"><label class="fl">إلى تاريخ</label><input type="date" id="wr-to"></div>
      <button class="btn bp2" onclick="loadPerfectStudents()" style="margin-top:24px">🔎 فحص الطلاب</button>
    </div>
    <div class="ab ai" style="margin-top:10px">هذه الميزة تحصر الطلاب الذين لم يسجلوا أي غياب طوال الفترة المحددة (الأسبوع الدراسي).</div>
    <div class="tw" style="margin-top:14px"><table>
      <thead><tr><th>الطالب</th><th>الفصل</th><th>الجوال</th></tr></thead>
      <tbody id="wr-table"></tbody></table></div>
    <div class="bg-btn" style="margin-top:16px">
      <button class="btn bp4" id="wr-send-btn" onclick="runManualRewards()" style="display:none">🚀 إرسال رسائل التعزيز الآن</button>
    </div>
    <div id="wr-status" style="margin-top:10px"></div>
  </div>

  <div class="section">
    <div class="st">إعدادات الجدولة والرسالة</div>
    <div class="fg2">
      <div class="fg"><label class="fl">تفعيل التعزيز التلقائي</label>
        <select id="wr-cfg-enabled"><option value="1">مفعّل</option><option value="0">معطّل</option></select>
      </div>
      <div class="fg"><label class="fl">يوم التنفيذ</label>
        <select id="wr-cfg-day">
          <option value="0">الأحد</option><option value="1">الاثنين</option><option value="2">الثلاثاء</option>
          <option value="3">الأربعاء</option><option value="4" selected>الخميس</option>
        </select>
      </div>
      <div class="fg"><label class="fl">وقت التنفيذ (ساعة:دقيقة)</label>
        <div style="display:flex;gap:5px">
          <input type="number" id="wr-cfg-hour" min="0" max="23" placeholder="ساعة" style="width:70px">
          <input type="number" id="wr-cfg-min" min="0" max="59" placeholder="دقيقة" style="width:70px">
        </div>
      </div>
    </div>
    <div class="fg" style="margin-top:14px">
      <label class="fl">قالب رسالة التعزيز</label>
      <textarea id="wr-cfg-tpl" rows="5" style="width:100%;font-family:inherit;padding:10px"></textarea>
      <div style="font-size:11px;color:var(--mu);margin-top:4px">الوسوم المتاحة: {student_name}, {school_name}, {guardian}, {son}, {his}</div>
    </div>
    <button class="btn bp1" style="margin-top:14px" onclick="saveRewardSettings()">💾 حفظ الإعدادات</button>
    <div id="wr-cfg-st" style="margin-top:10px"></div>
  </div>
</div>

<!-- ── تبويب لوحة الصدارة (النقاط) ────────────────── -->
<div id="tab-leaderboard">
  <h2 class="pt"><i class="fas fa-trophy" style="color:#D97706"></i> لوحة صدارة فرسان الانضباط</h2>
  <div class="section">
    <div class="st">أعلى الطلاب نقاطاً (تراكمي)</div>
    <div class="tw"><table>
      <thead><tr><th>المركز</th><th>الطالب</th><th>الفصل</th><th>إجمالي النقاط</th><th>إجراء</th></tr></thead>
      <tbody id="lb-table"></tbody></table></div>
  </div>

  <!-- بطاقة رصيد النقاط المتبقي -->
  <div id="lb-balance-card" style="display:none; background:linear-gradient(135deg,#1e40af,#3b82f6); color:#fff; border-radius:14px; padding:16px 20px; margin-bottom:18px; align-items:center; gap:18px; flex-wrap:wrap; box-shadow:0 4px 14px rgba(59,130,246,.35)">
    <i class="fas fa-coins" style="font-size:32px; opacity:.9"></i>
    <div>
      <div style="font-size:12px; opacity:.85; margin-bottom:4px">رصيدك المتبقي من النقاط هذا الشهر</div>
      <div style="display:flex; align-items:baseline; gap:8px">
        <span id="lb-remaining" style="font-size:34px; font-weight:900; line-height:1">—</span>
        <span style="font-size:14px; opacity:.8">/ <span id="lb-limit-val">100</span> نقطة</span>
      </div>
      <div style="margin-top:6px; background:rgba(255,255,255,.25); border-radius:20px; height:8px; overflow:hidden">
        <div id="lb-balance-bar" style="height:100%; background:#fff; border-radius:20px; width:0%; transition:width .6s ease"></div>
      </div>
    </div>
    <div id="lb-balance-note" style="margin-right:auto; font-size:12px; opacity:.85; text-align:left"></div>
  </div>

  <!-- إضافة نقاط يدوية -->
  <div class="section" style="background:#FFFBEB; border: 1px solid #FEF3C7">
    <div class="st">منح نقاط تميز (يدوي)</div>
    <div class="fg2">
      <div class="fg"><label class="fl">الفصل</label><select id="lb-cls" onchange="loadLbStus()"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">الطالب</label><select id="lb-stu"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">عدد النقاط</label><input type="number" id="lb-pts" value="5"></div>
      <div class="fg"><label class="fl">السبب</label><input type="text" id="lb-reason" placeholder="مثال: مشاركة متميزة"></div>
    </div>
    <button class="btn bp1" onclick="addPointsManual()">✨ منح النقاط</button>
    <div id="lb-st" style="margin-top:10px"></div>
  </div>
</div>

<!-- ── تبويب الطلاب المستثنون (جديد) ────────────────── -->
<div id="tab-exempted_students">
  <h2 class="pt"><i class="fas fa-user-slash"></i> الطلاب المستثنون (ظروف خاصة)</h2>
  <div class="section">
    <div class="st">إضافة طالب للاستثناء</div>
    <div class="ab ai">📌 الطالب المستثنى لن يظهر في أي رصد للغياب أو التأخر أو التقارير والرسائل.</div>
    <div class="fg2">
      <div class="fg"><label class="fl">الفصل</label><select id="ex-cls" onchange="loadClsForEx()"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">الطالب</label><select id="ex-stu"><option value="">اختر</option></select></div>
      <div class="fg"><label class="fl">سبب الاستثناء</label><input type="text" id="ex-reason" placeholder="مثال: ظروف صحية خاصة"></div>
    </div>
    <button class="btn bp1" onclick="addExemptedStudent()">+ إضافة للقائمة</button>
    <div id="ex-st" style="margin-top:10px"></div>
  </div>
  <div class="section">
    <div class="st">القائمة الحالية للطلاب المستثنين</div>
    <div class="tw"><table>
      <thead><tr><th>الطالب</th><th>الفصل</th><th>السبب</th><th>تاريخ الإضافة</th><th>حذف</th></tr></thead>
      <tbody id="ex-table"></tbody></table></div>
  </div>
</div>

<!-- ── تبويب قصص المدرسة (جديد) ────────────────── -->
<div id="tab-school_stories">
  <h2 class="pt"><i class="fas fa-camera-retro" style="color:#E91E63"></i> قصص المدرسة (أنشطة الطلاب)</h2>
  <div class="section">
    <div class="st">إضافة قصة جديدة</div>
    <div class="ab ai">💡 الصور المرفوعة هنا ستظهر كـ "سناب" أو "كاروسيل" في بوابة ولي الأمر لتبرز أنشطة المدرسة.</div>
    <div class="fg2">
      <div class="fg"><label class="fl">عنوان النشاط (اختياري)</label><input type="text" id="ss-title" placeholder="مثال: تكريم المتفوقين"></div>
      <div class="fg"><label class="fl">الصورة</label><input type="file" id="ss-file" accept="image/*"></div>
    </div>
    <button class="btn bp1" onclick="uploadStory()" style="margin-top:10px">📤 رفع ونشر القصة</button>
    <div id="ss-upload-st" style="margin-top:10px"></div>
  </div>
  
  <div class="section">
    <div class="st">القصص المنشورة حالياً</div>
    <div id="ss-list" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:15px;margin-top:10px">
      <!-- ستُملأ بالجافا سكريبت -->
    </div>
  </div>
</div>

<!-- ── تبويب إدارة النقاط (إداري) ────────────────── -->
<div id="tab-points_control">
  <div class="top-header" style="margin-bottom:20px">
    <h2 class="pt" style="margin:0"><i class="fas fa-coins" style="color:#f59e0b"></i> إدارة أرصدة وسياسات النقاط</h2>
    <p style="color:var(--mu); font-size:14px">تحكم في أرصدة المعلمين الشهرية وراقب استهلاكهم لنقاط التميز.</p>
  </div>

  <!-- بطاقات التحكم السريع -->
  <div class="fg2" style="margin-bottom:24px">
    <!-- بطاقة الإعدادات -->
    <div class="section" style="flex:1; border-top:4px solid #3b82f6">
      <div class="st"><i class="fas fa-cog"></i> سياسة النقاط الشهرية</div>
      <p style="font-size:13px; color:var(--mu); margin:8px 0">حدد عدد النقاط الافتراضي الذي يحصل عليه كل معلم شهرياً.</p>
      <div class="fg" style="margin-top:15px">
        <label class="fl">الحد الشهري الافتراضي</label>
        <div style="display:flex; gap:8px">
          <input type="number" id="pc-limit-cfg" placeholder="مثال: 100" style="flex:1; font-weight:700; text-align:center; font-size:18px">
          <button class="btn bp1" onclick="savePointsSettings()"><i class="fas fa-save"></i> حفظ</button>
        </div>
      </div>
    </div>
    
    <!-- بطاقة زيادة الرصيد -->
    <div class="section" style="flex:1.5; border-top:4px solid #10b981; background:linear-gradient(to bottom, #f0fdf4, #fff)">
      <div class="st" style="color:#15803d"><i class="fas fa-plus-circle"></i> منح رصيد إضافي (استثنائي)</div>
      <div class="fg2" style="margin-top:12px">
        <div class="fg" style="flex:1.5"><label class="fl">المستخدم (المعلم/الموظف)</label>
          <select id="pc-adj-user" style="font-weight:600"><option value="">جاري التحميل...</option></select></div>
        <div class="fg" style="flex:0.8"><label class="fl">عدد النقاط</label>
          <input type="number" id="pc-adj-pts" value="50" style="font-weight:700; color:#16a34a; text-align:center"></div>
      </div>
      <div class="fg" style="margin-top:10px">
        <label class="fl">السبب (يظهر في سجلات الإدارة)</label>
        <div style="display:flex; gap:8px">
          <input type="text" id="pc-adj-reason" placeholder="مثال: مكافأة لنشاط مدرسي محدد" style="flex:1">
          <button class="btn bp1" style="background:#16a34a" onclick="adjustUserPoints()"><i class="fas fa-check"></i> تنفيذ المنح</button>
        </div>
      </div>
    </div>
  </div>

  <!-- جداول البيانات -->
  <div class="fg2">
    <!-- استهلاك المعلمين -->
    <div class="section" style="flex:1">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px">
        <div class="st"><i class="fas fa-chart-pie"></i> استهلاك المعلمين</div>
        <input type="month" id="pc-month" onchange="loadTeachersUsage()" class="bsm" style="width:auto; padding:4px 8px">
      </div>
      <div class="tw" style="max-height:450px">
        <table>
          <thead>
            <tr><th>المعلم</th><th>المستهلك</th><th>إضافي</th><th>المتبقي</th><th>الحالة</th></tr>
          </thead>
          <tbody id="pc-usage-table-v2"></tbody>
        </table>
      </div>
    </div>

    <!-- السجل العام -->
    <div class="section" style="flex:1.5">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px">
        <div class="st"><i class="fas fa-list-ul"></i> سجل عمليات المنح (الأخيرة)</div>
        <button class="btn bp2 bsm" onclick="loadPointsAdminLogs()"><i class="fas fa-sync"></i> تحديث</button>
      </div>
      <div class="tw" style="max-height:450px">
        <table>
          <thead>
            <tr><th>التاريخ</th><th>بواسطة</th><th>للطالب</th><th>النقاط</th><th>السبب</th><th>إجراء</th></tr>
          </thead>
          <tbody id="pc-logs-table-v2"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>
'''


    # ── JavaScript الكامل المضغوط ─────────────────────────────
    js = r"""
window.onerror = function(msg, url, line, col, error) {
    alert("❌ حصل خطأ في المتصفح:\n" + msg + "\n\nالمكان: " + url + ":" + line);
    return false;
};
var today=new Date().toISOString().split('T')[0];
var _gender='boys', _me=null;

window.onload=function(){
  console.log("🚀 DarbStu Web Dashboard Loaded - Version Update Applied");
  setDates();loadMe();showTab('dashboard');checkUnreadCirculars();setTimeout(checkUnreadTeacherReports,2000);setTimeout(inboxUpdateBadge,3000);
};

function setDates(){
  ['dash-date','abs-date','tard-date','exc-date','perm-date','sa-date','st-date','ar-date',
   'np-date','lm-date','exc-date-new','noor-date','co-date','lg-from','lg-to','wr-from','wr-to'].forEach(function(id){
    var el=document.getElementById(id);if(el)el.value=today;});
  // ضبط تواريخ الأسبوع للتعزيز
  var d = new Date();
  var day = d.getDay(); // 0=Sun, 4=Thu
  var sun = new Date(d); sun.setDate(d.getDate() - day);
  var thu = new Date(sun); thu.setDate(sun.getDate() + 4);
  var f1 = document.getElementById('wr-from'); if(f1) f1.value = sun.toISOString().split('T')[0];
  var f2 = document.getElementById('wr-to'); if(f2) f2.value = thu.toISOString().split('T')[0];
  
  // ضبط حقل شهر إدارة النقاط
  var pcm = document.getElementById('pc-month'); if(pcm) pcm.value = today.slice(0,7);
}

async function api(url,opts){
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), 15000); 
  try{
    // إضافة قيمة عشوائية لمنع التخزين المؤقت (Cache Busting)
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    var finalUrl = url + sep + '_t=' + Date.now();
    
    var r = await fetch(finalUrl,{...opts, signal: controller.signal});
    clearTimeout(id);
    if(r.status===401){location.href='/web/login';return null;}
    return r.json();
  } catch(e){
    console.warn('API Error/Timeout:', url, e);
    return null;
  }
}

async function loadMe(){
  var d=await api('/web/api/me');if(!d)return;
  _me=d;
  if(d.school)document.getElementById('sc-name').textContent=d.school;
  if(d.name)document.getElementById('user-name').textContent='أهلاً بعودتك، ' + d.name;
  else if(d.username)document.getElementById('user-name').textContent='أهلاً بعودتك، ' + d.username;
  if(d.gender)_gender=d.gender;
  if(d.is_girls)document.documentElement.style.setProperty('--pr','#7C3AED');
  
  // تحميل إعدادات النقاط للمدير
  if(d.role === 'admin'){
      api('/web/api/config').then(cfg => {
          if(cfg && cfg.monthly_points_limit){
              var el = document.getElementById('pc-limit-cfg');
              if(el) el.value = cfg.monthly_points_limit;
          }
      });
  }
  loadClasses();
}

/* ── TAB SWITCHING ── */
function showTab(key){
  document.querySelectorAll('#tc>div').forEach(function(d){d.classList.remove('active');});
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
  var tab=document.getElementById('tab-'+key);if(tab)tab.classList.add('active');
  document.querySelectorAll('.tab-btn[data-key="'+key+'"]').forEach(function(b){b.classList.add('active');});
  var L={
    'dashboard':loadDashboard,'links':loadLinks,'live_monitor':loadLiveMonitor,
    'reg_absence':loadClasses,'reg_tardiness':loadClasses,
    'absences':function(){loadAbsences();fillSel('abs-class-filter');},
    'tardiness':loadTardiness,'excuses':loadExcuses,'permissions':loadPermissions,
    'logs':function(){fillSel('lg-cls');},
    'absence_mgmt':function(){fillSel('am-cls');fillSel('am-bc');},
    'partial_absence':function(){document.getElementById('pa-date').value=today;loadEscapedReport();},
    'reports_print':function(){loadReports();fillSel('rp-cls');fillSel('rp-sc');},
    'admin_report':generateAdminReport,
    'student_analysis':function(){fillSel('an-class');},
    'top_absent':loadTopAbsent,'alerts':function(){loadAlerts();},
    'new_permission':function(){loadClasses();loadTodayPerms();},
    'student_mgmt':function(){loadStudents();fillSel('sm-cls');},
    'add_student':function(){fillSel('as-cls');},
    'class_naming':loadClassList,
    'phones':function(){loadStudents();fillSel('ph-cls');},
    'noor_export':function(){fillSel('noor-cls');},
    'results':function(){},
    'counselor':function(){fillSel('co-cls');fillSel('coa-cls');loadCoSessions();loadCounselorList();},
    'circulars': loadCirculars,
    'school_settings':function(){loadSettings();fillSel('sn-cls');snLoadPreview();},
    'users':loadUsers,'backup':loadBackups,
    'quick_notes':function(){inboxSwitch('inbox');},
    'schedule_links':function(){fillSel('sch-cls');loadSchedule();},
    'tardiness_recipients':loadRecipients,
    'grade_analysis':function(){fillSel('ga-cls');},
    'term_report':function(){fillSel('tr-cls');},
    'weekly_reward':loadWeeklyReward,
    'leaderboard':function(){fillSel('lb-cls');loadLeaderboard();loadTeacherBalance();},
    'exempted_students':function(){fillSel('ex-cls');loadExemptedStudents();},
    'points_control': function(){ loadPointsAdminLogs(); loadTeachersUsage(); loadUsersForAdj(); },
    'school_stories':loadStories,
    'referral_teacher':function(){loadRefStudents();loadRefHistory();},
    'referral_deputy':loadDeputyReferrals,
    'teacher_forms':function(){
      var uname = (_me&&_me.name)?_me.name:'';
      var eL=document.getElementById('tfl-executor');var eP=document.getElementById('tfp-executor');
      if(eL&&!eL.value)eL.value=uname;
      if(eP&&!eP.value)eP.value=uname;
    },
    'teacher_reports_admin': loadTeacherReportsAdmin,
    'school_reports': loadSchoolReports,
    'send_absence':function(){},
    'send_tardiness':function(){},
    'parent_visits':pvInit,
  };
  if(L[key])L[key]();
  if(window.innerWidth<=768)closeSidebar();
}

/* ── INNER TABS ── */
function si(tabKey,panelId){
  var par=document.getElementById('tab-'+tabKey);if(!par)return;
  par.querySelectorAll('.ip').forEach(function(p){p.classList.remove('active');});
  par.querySelectorAll('.itb').forEach(function(b){b.classList.remove('active');});
  var p=document.getElementById(panelId);if(p)p.classList.add('active');
  // تفعيل الزر المطابق: إما الحدث الحالي أو بالبحث عن onclick
  var ev=(typeof event!=='undefined')?event:null;
  if(ev&&ev.target&&ev.target.classList&&ev.target.classList.contains('itb')){
    ev.target.classList.add('active');
  } else {
    par.querySelectorAll('.itb').forEach(function(b){
      var oc=b.getAttribute('onclick')||'';
      if(oc.indexOf("'"+panelId+"'")>=0) b.classList.add('active');
    });
  }
}

/* ── SIDEBAR ── */
function toggleSidebar(){var sb=document.getElementById('sb');var ov=document.getElementById('ov');var mt=document.getElementById('mt');
  if(sb.classList.contains('open')){closeSidebar();}
  else{sb.classList.add('open');ov.classList.add('show');mt.classList.add('open');document.body.style.overflow='hidden';}}
function closeSidebar(){document.getElementById('sb').classList.remove('open');document.getElementById('ov').classList.remove('show');
  document.getElementById('mt').classList.remove('open');document.body.style.overflow='';}

/* ── CIRCULARS ── */
async function loadCirculars(){
  try {
    var cont=document.getElementById('circ-list'); if(!cont)return;
    if(!_me || !_me.username) {
       var me_data = await api('/web/api/me');
       if(me_data && me_data.ok) { _me = me_data; }
    }
    console.log('loadCirculars: fetching list...');
    var d = await api('/web/api/circulars/list');
    if(!d || !d.ok){
      console.error('loadCirculars: API failed', d);
      cont.innerHTML='<div class="section" style="color:#b91c1c;text-align:center;padding:30px">❌ فشل تحميل القائمة: '+(d?d.msg:'انقطع الاتصال بالسيرفر')+'</div>';
      return;
    }
    
    var circs = d.rows || [];
    if(circs.length===0){
      cont.innerHTML='<div class="section" style="color:var(--mu);text-align:center;padding:80px 0;background:rgba(255,255,255,0.5)">' + 
                     '<div style="font-size:48px;margin-bottom:15px">📭</div>' +
                     '<div style="font-size:18px;font-weight:bold;color:#64748b">لا توجد تعاميم أو نشرات حالياً</div>' +
                     '<div style="font-size:13px;margin-top:5px">سيظهر هنا ما يتم نشره من قبل الإدارة</div></div>';
      return;
    }
    
    var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:24px;animation:slideUp 0.5s ease-out">';
    for (var i = 0; i < circs.length; i++) {
        var c = circs[i];
        try {
          var myRole = (_me && _me.role) ? _me.role : 'teacher';
          var isAdmin = (myRole === 'admin');
          var isRead = isAdmin ? true : (c.is_read > 0);
          
          var statusBadge = isRead ? 
              '<span style="background:#f1f5f9;color:#64748b;font-size:11px;padding:3px 10px;border-radius:20px;font-weight:600">مقروء</span>' : 
              '<span style="background:#fff7ed;color:#ea580c;border:1px solid #ffedd5;font-size:11px;padding:3px 10px;border-radius:20px;font-weight:700">جديد ✨</span>';
          
          if(isAdmin) statusBadge = '<span style="background:#f0f9ff;color:#0369a1;font-size:11px;padding:3px 10px;border-radius:20px;font-weight:600">📊 '+ (c.read_count||0) +' قراءات</span>';
  
          var attBtn = c.attachment_path ? 
              '<a href="/data/'+c.attachment_path+'" target="_blank" class="btn" style="background:#f8fafc;color:#1e293b;border:1px solid #e2e8f0;margin-top:16px;display:flex;align-items:center;justify-content:center;gap:8px;font-weight:bold;width:100%;transition:0.2s;text-decoration:none"><i class="fas fa-paperclip"></i> فتح المرفق</a>' : '';
          
          var delBtn = isAdmin ? 
              '<button class="btn" style="background:transparent;color:#ef4444;padding:4px;border:none;cursor:pointer;opacity:0.6" onclick="deleteCirc('+c.id+')" title="حذف التعميم"><i class="fas fa-trash-alt"></i></button>' : '';
  
          html += '<div class="section" style="border:none;border-top:5px solid '+(isRead?'#e2e8f0':'#f97316')+';display:flex;flex-direction:column;min-height:220px;transition:transform 0.2s;box-shadow:0 4px 12px rgba(0,0,0,0.05)">'+
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">'+
              '<div><div style="font-size:10px;color:var(--mu);margin-bottom:4px;display:flex;align-items:center;gap:4px"><i class="fas fa-calendar-day"></i> '+ (c.date||'---') +'</div>'+
              '<strong style="font-size:17px;color:#1e293b;line-height:1.4">'+(c.title||'بدون عنوان')+'</strong></div>'+
              '<div style="display:flex;align-items:center;gap:10px">'+delBtn+statusBadge+'</div>'+
            '</div>'+
            '<div style="flex-grow:1;font-size:14px;line-height:1.7;color:#475569;margin-bottom:15px;white-space:pre-wrap">'+ (c.content||'') +'</div>'+
            '<div style="border-top:1px solid #f1f5f9;margin:0 -15px;padding:0 15px">' + attBtn + '</div>' + 
            (!isRead && !isAdmin ? '<button class="btn" style="background:#f97316;color:#fff;margin-top:10px;width:100%;border:none;font-weight:bold" onclick="markCircRead('+c.id+')">تحديد كمقروء ✅</button>' : '')+
            '</div>';
        } catch(err) { console.error('Render error:', err); }
    }
    html += '</div>';
    cont.innerHTML = html;
    console.log('loadCirculars: Render complete');
  } catch(e) {
    console.error('loadCirculars EXCEPTION:', e);
    cont.innerHTML='<div class="section" style="color:#b91c1c">❌ خطأ تقني في معالجة القائمة. يرجى تحديث الصفحة.</div>';
  }
}

async function deleteCirc(id){
  if(!confirm('هل أنت متأكد من حذف هذا التعميم نهائياً؟')) return;
  try {
    var r = await fetch('/web/api/circulars/delete/'+id, {method:'POST'});
    var d = await r.json();
    if(d.ok) { loadCirculars(); } else { alert('❌ فشل الحذف: ' + d.msg); }
  } catch(e) { alert('❌ خطأ في الاتصال بالسيرفر'); }
}

async function submitCircular(){
  var title=document.getElementById('ci-title').value.trim();
  var target=document.getElementById('ci-target').value;
  var content=document.getElementById('ci-content').value.trim();
  var fileInput=document.getElementById('ci-file');
  if(!title){ss('ci-status','أدخل عنوان التعميم أو النشرة','er');return;}
  ss('ci-status','⏳ جارٍ النشر...','in');
  var fd=new FormData();fd.append('title',title);fd.append('target_role',target);fd.append('content',content);
  if(fileInput.files.length)fd.append('file',fileInput.files[0]);
  try{
    var r=await fetch('/web/api/circulars/create',{method:'POST',body:fd});
    var d=await r.json();
    if(d.ok){ss('ci-status','✅ تم النشر بنجاح','ok');loadCirculars();si('circulars','circ-list');}
    else ss('ci-status','❌ '+(d.msg||'فشل'),'er');
  }catch(e){ss('ci-status','❌ خطأ اتصال بالسيرفر','er');}
}

async function markCircRead(id){
  try {
    var r=await fetch('/web/api/circulars/mark-read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var d=await r.json();if(d.ok){loadCirculars(); if(_me) loadMe();}
  } catch(e) { console.error('markCircRead error:', e); }
}

/* ── STATUS ── */
function ss(id,msg,type){var el=document.getElementById(id);if(!el)return;
  el.className='sm s'+(type||'in');el.textContent=msg;el.style.display='block';}

/* ── DASHBOARD ── */
async function loadDashboard(){
  var date=document.getElementById('dash-date').value||today;
  var d=await api('/web/api/dashboard-data?date='+date);
  if(!d||!d.ok){document.getElementById('dash-cards').innerHTML=demoCrd();
    document.getElementById('dash-classes').innerHTML='<tr><td colspan="4" style="color:#9CA3AF">لا يوجد بيانات</td></tr>';return;}
  var t=d.metrics.totals;var pct=t.students>0?(t.absent/t.students*100).toFixed(1):0;
  document.getElementById('dash-cards').innerHTML=
    crd(t.students,'#1565C0','إجمالي الطلاب','<i class="fas fa-graduation-cap"></i>')+crd(t.present,'#2E7D32','الحضور','<i class="fas fa-check-circle"></i>')+
    crd(t.absent,'#C62828','الغياب ('+pct+'%)','<i class="fas fa-user-times"></i>')+crd(t.tardiness||0,'#E65100','التأخر','<i class="fas fa-clock"></i>')+
    crd(t.excused||0,'#0277BD','الأعذار','<i class="fas fa-file-medical"></i>')+crd(t.permissions||0,'#7C3AED','الاستئذان','<i class="fas fa-door-open"></i>');
  var cls=d.metrics.by_class||[];
  document.getElementById('dash-classes').innerHTML=
    cls.sort(function(a,b){return b.absent-a.absent;}).slice(0,10).map(function(c){
      var p=c.total>0?(c.absent/c.total*100).toFixed(1):0;
      return '<tr><td>'+c.class_name+'</td><td><span class="badge br">'+c.absent+'</span></td><td>'+c.present+'</td><td>'+p+'%</td></tr>';
    }).join('')||'<tr><td colspan="4" style="color:#9CA3AF">لا يوجد</td></tr>';
}
function crd(v,c,l,ic){return '<div class="sc"><div class="v" style="color:'+c+'">'+ic+'<br>'+v+'</div><div class="l">'+l+'</div></div>';}
function demoCrd(){return crd(0,'#1565C0','إجمالي الطلاب','<i class="fas fa-graduation-cap"></i>')+crd(0,'#2E7D32','الحضور','<i class="fas fa-check-circle"></i>')+crd(0,'#C62828','الغياب','<i class="fas fa-user-times"></i>')+crd(0,'#E65100','التأخر','<i class="fas fa-clock"></i>');}

/* ── LINKS ── */
async function loadLinks(){
  var d=await api('/web/api/classes');if(!d||!d.ok){document.getElementById('links-list').innerHTML='<p style="color:var(--mu)">لا توجد فصول</p>';return;}
  var base=window.location.origin;
  document.getElementById('links-list').innerHTML=d.classes.map(function(c){
    var url=base+'/c/'+c.id;
    return '<div class="lc"><div><strong>'+c.name+'</strong><br><span class="badge bb" style="margin-top:5px">'+c.count+' طالب</span></div>'+
      '<div class="lu">'+url+'</div>'+
      '<div style="display:flex;gap:6px"><button class="btn bp1 bsm" onclick="copyL(\''+url+'\')">نسخ</button>'+
      '<button class="btn bp2 bsm" onclick="window.open(\''+url+'\',\'_blank\')">فتح</button></div></div>';
  }).join('')||'<p style="color:var(--mu)">لا توجد فصول</p>';
}
function copyL(url){navigator.clipboard&&navigator.clipboard.writeText(url).then(function(){alert('✅ تم نسخ الرابط');});}

/* ── LIVE MONITOR ── */
async function loadLiveMonitor(){
  var date=document.getElementById('lm-date').value||today;
  var d=await api('/web/api/absences?date='+date);if(!d||!d.ok)return;
  document.getElementById('lm-cards').innerHTML=crd(d.rows.length,'#C62828','غياب اليوم','🔴');
  document.getElementById('lm-table').innerHTML=d.rows.map(function(r){
    return '<tr><td>'+r.student_name+'</td><td>'+r.class_name+'</td><td>'+(r.period||'-')+'</td><td>'+(r.teacher_name||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="4" style="color:#9CA3AF">لا يوجد غياب</td></tr>';
}

/* ── CLASSES ── */
var _classes=[];
async function loadClasses(){
  var d=await api('/web/api/classes');if(!d||!d.ok)return;
  _classes=d.classes;
  var opts='<option value="">اختر فصلاً</option>'+d.classes.map(function(c){return '<option value="'+c.id+'" data-name="'+c.name+'">'+c.name+' ('+c.count+')</option>';}).join('');
  ['ra-class','rt-class','np-class','an-class','lb-cls','ex-cls','co-cls'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML=opts;});
}
function fillSel(id){
  var el=document.getElementById(id);if(!el)return;
  var cur=el.value;
  el.innerHTML='<option value="">الكل</option>'+_classes.map(function(c){return '<option value="'+c.id+'">'+c.name+'</option>';}).join('');
  if(cur)el.value=cur;
}

async function loadClassStudentsForAbs(){
  var sel=document.getElementById('ra-class');var cid=sel?sel.value:'';if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('ra-students').innerHTML=d.students.map(function(s){
    return '<label class="sk"><input type="checkbox" value="'+s.id+'" data-name="'+s.name+'"><span style="font-size:13px">'+s.name+'</span></label>';
  }).join('');
}
function selAll(cid){document.querySelectorAll('#'+cid+' input[type=checkbox]').forEach(function(c){c.checked=true;});}
function clrAll(cid){document.querySelectorAll('#'+cid+' input[type=checkbox]').forEach(function(c){c.checked=false;});}
async function submitAbsence(){
  var date=document.getElementById('ra-date').value;
  var sel=document.getElementById('ra-class');var cid=sel?sel.value:'';
  var cname=sel&&sel.options[sel.selectedIndex]?sel.options[sel.selectedIndex].dataset.name||'':'';
  var period=document.getElementById('ra-period').value;
  var checked=Array.from(document.querySelectorAll('#ra-students input:checked'));
  if(!date||!cid||!checked.length){ss('ra-status','اختر التاريخ والفصل والطلاب','er');return;}
  var students=checked.map(function(c){return {id:c.value,name:c.dataset.name};});
  var r=await fetch('/web/api/add-absence',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({date:date,class_id:cid,class_name:cname,students:students,period:parseInt(period)})});
  var d=await r.json();
  ss('ra-status',d.ok?'✅ تم تسجيل غياب '+d.count+' طالب':'❌ '+d.msg,d.ok?'ok':'er');
  if(d.ok)clrAll('ra-students');
}
async function loadAbsences(){
  var date=document.getElementById('abs-date')?document.getElementById('abs-date').value||today:today;
  var d=await api('/web/api/absences?date='+date);if(!d||!d.ok)return;
  var tb=document.getElementById('abs-table');if(!tb)return;
  tb.innerHTML=d.rows.map(function(r){
    return '<tr><td>'+r.date+'</td><td>'+r.class_name+'</td><td>'+r.student_name+'</td><td>'+(r.period||'-')+'</td><td>'+(r.teacher_name||'-')+'</td>'+
           '<td><button class="btn bp3 bsm" onclick="delAbs('+r.id+')">حذف</button></td></tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function delAbs(id){if(!confirm('حذف هذا الغياب؟'))return;
  var r=await fetch('/web/api/delete-absence/'+id,{method:'DELETE'});
  var d=await r.json();if(d.ok)loadAbsences();}

/* ── TARDINESS ── */
async function loadClassStudentsForTard(){
  var sel=document.getElementById('rt-class');var cid=sel?sel.value:'';if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('rt-students').innerHTML=d.students.map(function(s){
    return '<div class="sk" style="justify-content:space-between">'+
      '<span style="font-size:13px">'+s.name+'</span>'+
      '<div style="display:flex;gap:6px;align-items:center">'+
      '<input type="number" min="1" max="60" placeholder="دق" id="td-'+s.id+'" data-name="'+s.name+'" style="width:65px;padding:5px">'+
      '<button onclick="recTard(\''+s.id+'\',\''+encodeURIComponent(s.name)+'\',\''+cid+'\',\''+encodeURIComponent(d.name)+'\')" class="btn bp5 bsm">تسجيل</button>'+
      '</div></div>';
  }).join('');
}
async function recTard(sid,sname,cid,cname){
  sname=decodeURIComponent(sname);cname=decodeURIComponent(cname);
  var date=document.getElementById('rt-date').value;
  var el=document.getElementById('td-'+sid);var mins=el?parseInt(el.value||0):0;
  if(!date||!mins){ss('rt-status','أدخل التاريخ والدقائق','er');return;}
  var r=await fetch('/web/api/add-tardiness',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({date:date,student_id:sid,student_name:sname,class_id:cid,class_name:cname,minutes_late:mins})});
  var d=await r.json();
  ss('rt-status',d.ok?'✅ تم تسجيل تأخر '+sname:'❌ '+d.msg,d.ok?'ok':'er');
}
async function loadTardiness(){
  var date=document.getElementById('tard-date')?document.getElementById('tard-date').value||today:today;
  var d=await api('/web/api/tardiness?date='+date);if(!d||!d.ok)return;
  var tb=document.getElementById('tard-table');if(!tb)return;
  tb.innerHTML=d.rows.map(function(r){
    var cls=r.minutes_late>=15?'br':'bo';
    return '<tr><td>'+r.date+'</td><td>'+r.student_name+'</td><td>'+r.class_name+'</td>'+
           '<td><span class="badge '+cls+'">'+r.minutes_late+' د</span></td><td>'+(r.teacher_name||'-')+'</td>'+
           '<td><button class="btn bp3 bsm" onclick="delTard('+r.id+')">حذف</button></td></tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function delTard(id){if(!confirm('حذف؟'))return;
  var r=await fetch('/web/api/delete-tardiness/'+id,{method:'DELETE'});
  var d=await r.json();if(d.ok)loadTardiness();}

/* ── EXCUSES ── */
function showAddExc(){document.getElementById('add-exc-form').style.display='block';}
async function loadClsForExc(){
  var cid=document.getElementById('exc-cls').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('exc-stu').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'" data-name="'+s.name+'">'+s.name+'</option>';}).join('');
}
async function addExcuse(){
  var clsSel=document.getElementById('exc-cls');var stuSel=document.getElementById('exc-stu');
  var cid=clsSel?clsSel.value:'';var cname=clsSel?clsSel.options[clsSel.selectedIndex].text:'';
  var sid=stuSel?stuSel.value:'';var sname=stuSel?stuSel.options[stuSel.selectedIndex].dataset.name||stuSel.options[stuSel.selectedIndex].text:'';
  var date=document.getElementById('exc-date-new').value;var reason=document.getElementById('exc-reason').value;
  if(!cid||!sid||!date||!reason){ss('exc-add-st','اكمل جميع الحقول','er');return;}
  var r=await fetch('/web/api/add-excuse',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({date:date,student_id:sid,student_name:sname,class_id:cid,class_name:cname,reason:reason})});
  var d=await r.json();ss('exc-add-st',d.ok?'✅ تم حفظ العذر':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  if(d.ok)loadExcuses();
}
async function loadExcuses(){
  var date=document.getElementById('exc-date')?document.getElementById('exc-date').value||today:today;
  var d=await api('/web/api/excuses?date='+date);if(!d||!d.ok)return;
  var tb=document.getElementById('exc-table');if(!tb)return;
  tb.innerHTML=d.rows.map(function(r){
    return '<tr><td>'+r.date+'</td><td>'+r.student_name+'</td><td>'+r.class_name+'</td><td>'+(r.reason||'-')+'</td>'+
           '<td>'+(r.source==='whatsapp'?'واتساب':'إداري')+'</td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا يوجد</td></tr>';
}

/* ── PERMISSIONS ── */
async function loadPermissions(){
  var date=document.getElementById('perm-date')?document.getElementById('perm-date').value||today:today;
  var d=await api('/web/api/permissions?date='+date);if(!d||!d.ok)return;
  var w=d.rows.filter(function(r){return r.status==='انتظار';}).length;
  var a=d.rows.filter(function(r){return r.status==='موافق';}).length;
  document.getElementById('perm-ind').innerHTML=
    (w?'<span class="badge bo">انتظار: '+w+'</span>':'')+
    (a?'<span class="badge bg">وافق وخرج: '+a+'</span>':'');
  var cols={'انتظار':'bo','موافق':'bg','مرفوض':'br'};
  document.getElementById('perm-table').innerHTML=d.rows.map(function(r){
    return '<tr><td>'+r.student_name+'</td><td>'+r.class_name+'</td><td>'+(r.reason||'-')+'</td>'+
           '<td><span class="badge '+(cols[r.status]||'')+'">'+r.status+'</span></td>'+
           '<td><button class="btn bp4 bsm" onclick="approvePerm('+r.id+')">✅ موافقة</button></td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا يوجد</td></tr>';
}

async function loadClsForAn(){
  var cid = document.getElementById('an-class').value; if(!cid) return;
  var d = await api('/web/api/class-students/'+cid); if(!d||!d.ok) return;
  document.getElementById('an-student').innerHTML = '<option value="">اختر طالباً</option>' +
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}

function renderAnCharts(data){
  if(anCharts.line) anCharts.line.destroy();
  if(anCharts.pie) anCharts.pie.destroy();
  var lineCtx = document.getElementById('an-chart-line').getContext('2d');
  var trend = data.absence_trend || {};
  var labels = Object.keys(trend).sort();
  var points = labels.map(function(l){ return trend[l]; });
  anCharts.line = new Chart(lineCtx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'حالات الغياب',
        data: points,
        borderColor: '#1565C0',
        backgroundColor: 'rgba(21, 101, 192, 0.1)',
        tension: 0.3, fill: true
      }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
  var pieCtx = document.getElementById('an-chart-pie').getContext('2d');
  anCharts.pie = new Chart(pieCtx, {
    type: 'doughnut',
    data: {
      labels: ['تأخر', 'مخالفات سلوكية', 'جلسات إرشادية'],
      datasets: [{
        data: [data.total_tardiness, data.behavior_referrals, data.counselor_sessions],
        backgroundColor: ['#f59e0b', '#ef4444', '#10b981']
      }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
}

async function approvePerm(id){
  var r=await fetch('/web/api/approve-permission/'+id,{method:'POST'});
  var d=await r.json();if(d.ok)loadPermissions();}
async function loadClassForPerm(){
  var cid=document.getElementById('np-class').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('np-student').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'" data-phone="'+(s.phone||'')+'">'+s.name+'</option>';}).join('');
  document.getElementById('np-student').onchange=function(){
    var opt=this.options[this.selectedIndex];if(opt)document.getElementById('np-phone').value=opt.dataset.phone||'';};
}
async function loadTodayPerms(){
  var date=document.getElementById('np-date')?document.getElementById('np-date').value||today:today;
  var d=await api('/web/api/permissions?date='+date);if(!d||!d.ok)return;
  var cols={'انتظار':'bo','موافق':'bg','مرفوض':'br'};
  document.getElementById('np-today-list').innerHTML=d.rows.length
    ?'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px">'+
      d.rows.map(function(r){return '<div class="section" style="padding:10px">'+
        '<strong style="font-size:13px">'+r.student_name+'</strong>'+
        '<div style="font-size:11px;color:var(--mu)">'+r.class_name+' — '+(r.reason||'-')+'</div>'+
        '<span class="badge '+(cols[r.status]||'')+'" style="margin-top:6px">'+r.status+'</span></div>';}).join('')+'</div>'
    :'<p style="color:#94A3B8;text-align:center;padding:20px">لا توجد طلبات</p>';
}
async function submitPermission(sendWA){
  var date=document.getElementById('np-date').value;
  var clsSel=document.getElementById('np-class');var stuSel=document.getElementById('np-student');
  var cid=clsSel?clsSel.value:'';
  var cname=clsSel&&clsSel.options[clsSel.selectedIndex]?clsSel.options[clsSel.selectedIndex].text.split(' (')[0]:'';
  var sid=stuSel?stuSel.value:'';var sname=stuSel&&stuSel.options[stuSel.selectedIndex]?stuSel.options[stuSel.selectedIndex].text:'';
  var reason=document.getElementById('np-reason').value;var phone=document.getElementById('np-phone').value.trim();
  if(!date||!cid||!sid){ss('np-status','اختر التاريخ والفصل والطالب','er');return;}
  ss('np-status','جارٍ التسجيل...','in');
  var r=await fetch('/web/api/add-permission',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({date:date,student_id:sid,student_name:sname,class_id:cid,class_name:cname,parent_phone:phone,reason:reason,send_wa:sendWA})});
  var d=await r.json();ss('np-status',d.ok?'✅ '+d.msg:'❌ '+d.msg,d.ok?'ok':'er');
  if(d.ok)loadTodayPerms();
}

/* ── MESSAGES ── */
async function loadAbsencesForSend(){
  var date=document.getElementById('sa-date').value;if(!date){alert('اختر التاريخ');return;}
  ss('sa-status','جارٍ التحميل...','in');
  var d=await api('/web/api/absences?date='+date);if(!d||!d.ok)return;
  if(!d.rows.length){ss('sa-status','لا يوجد غياب','ok');document.getElementById('sa-list').innerHTML='';document.getElementById('sa-send-btn').style.display='none';return;}
  var seen=new Set();var students=d.rows.filter(function(r){if(seen.has(r.student_id))return false;seen.add(r.student_id);return true;});
  document.getElementById('sa-status').innerHTML='<span class="badge br">'+students.length+' طالب غائب</span>';
  document.getElementById('sa-list').innerHTML='<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin-top:8px">'+
    students.map(function(s){return '<label class="sk"><input type="checkbox" value="'+s.student_id+'" data-name="'+s.student_name+'" data-class="'+s.class_name+'" data-classid="'+s.class_id+'" checked>'+
      '<div><div style="font-size:13px;font-weight:600">'+s.student_name+'</div><div style="font-size:11px;color:var(--mu)">'+s.class_name+'</div></div></label>';}).join('')+'</div>';
  document.getElementById('sa-send-btn').style.display='block';
}
function saAll(v){document.querySelectorAll('#sa-list input[type=checkbox]').forEach(function(c){c.checked=v;});}
async function sendAbsenceMessages(){
  var date=document.getElementById('sa-date').value;
  var checked=Array.from(document.querySelectorAll('#sa-list input:checked'));
  if(!checked.length){alert('حدد طالباً');return;}
  var btn=document.getElementById('sa-btn');btn.disabled=true;btn.textContent='جارٍ الإرسال...';
  var students=checked.map(function(c){return {student_id:c.value,student_name:c.dataset.name,class_id:c.dataset.classid,class_name:c.dataset.class};});
  var r=await fetch('/web/api/send-absence-messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:date,students:students})});
  var d=await r.json();
  document.getElementById('sa-progress').textContent=d.ok?'✅ تم إرسال '+d.sent+' رسالة':'❌ '+d.msg;
  btn.disabled=false;btn.textContent='📨 إرسال للمحددين';
}
async function loadTardinessForSend(){
  var date=document.getElementById('st-date').value;if(!date){alert('اختر التاريخ');return;}
  var d=await api('/web/api/tardiness?date='+date);if(!d||!d.ok)return;
  if(!d.rows.length){ss('st-status','لا يوجد تأخر','ok');document.getElementById('st-list').innerHTML='';document.getElementById('st-send-btn').style.display='none';return;}
  document.getElementById('st-status').innerHTML='<span class="badge bo">'+d.rows.length+' حالة تأخر</span>';
  document.getElementById('st-list').innerHTML='<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:6px;margin-top:8px">'+
    d.rows.map(function(s){return '<label class="sk" style="background:#FFF8F0;border-color:#FED7AA"><input type="checkbox" value="'+s.student_id+'" data-name="'+s.student_name+'" data-class="'+s.class_name+'" data-mins="'+s.minutes_late+'" checked>'+
      '<div><div style="font-size:13px;font-weight:600">'+s.student_name+'</div><div style="font-size:11px;color:#92400E">'+s.class_name+' - '+s.minutes_late+' دقيقة</div></div></label>';}).join('')+'</div>';
  document.getElementById('st-send-btn').style.display='block';
}
async function sendTardinessMessages(){
  var date=document.getElementById('st-date').value;
  var checked=Array.from(document.querySelectorAll('#st-list input:checked'));if(!checked.length){alert('حدد طالباً');return;}
  var students=checked.map(function(c){return {student_id:c.value,student_name:c.dataset.name,class_name:c.dataset.class,minutes_late:c.dataset.mins};});
  var r=await fetch('/web/api/send-tardiness-messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:date,students:students})});
  var d=await r.json();document.getElementById('st-progress').textContent=d.ok?'✅ تم إرسال '+d.sent+' رسالة':'❌ '+d.msg;
}

/* ── SAVE NUMBER ── */
async function snLoadPreview(){
  var d=await api('/web/api/save-number-preview');
  var el=document.getElementById('sn-preview');
  if(el)el.textContent=d&&d.msg?d.msg:'تعذر تحميل المعاينة';
}
async function sendSaveNumber(){
  if(!confirm('سيتم إرسال رسالة "حفظ الرقم" لجميع أولياء الأمور في الفصل المحدد.\nهذا قد يستغرق وقتاً بسبب التأخير بين الرسائل.\nهل تريد المتابعة؟'))return;
  var cls=document.getElementById('sn-cls').value;
  var btn=document.getElementById('sn-btn');
  btn.disabled=true;btn.textContent='⏳ جارٍ الإرسال...';
  document.getElementById('sn-progress').textContent='يُرسل الرسائل بشكل تدريجي لتفادي التقييد...';
  document.getElementById('sn-st').innerHTML='';
  var r=await fetch('/web/api/send-save-number',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({class_id:cls})});
  var d=await r.json();
  btn.disabled=false;btn.textContent='📲 إرسال';
  document.getElementById('sn-progress').textContent='';
  if(d.ok)ss('sn-st','✅ تم الإرسال — أُرسل: '+d.sent+' | فشل: '+d.failed+' | مكرر/بدون رقم: '+d.skipped,'ok');
  else ss('sn-st','❌ '+(d.msg||'خطأ'),'er');
}

/* ── PORTAL LINKS ── */
(function(){
  // تحميل قائمة الفصول عند فتح التبويب
  var _plLoaded = false;
  var _origShow = window.showTab;
  window.showTab = function(key){
    if(typeof _origShow==='function') _origShow(key);
    if(key==='portal_links' && !_plLoaded){ _plLoaded=true; plInitClasses(); }
  };
})();

async function plInitClasses(){
  var d = await api('/web/api/students');
  if(!d||!d.ok) return;
  var sel = document.getElementById('pl-class');
  if(!sel) return;
  sel.innerHTML = '<option value="">-- اختر فصلاً --</option>';
  (d.classes||[]).forEach(function(c){
    sel.innerHTML += '<option value="'+c.id+'">'+c.name+'</option>';
  });
}

var _plStudents = [];
async function plLoadClass(){
  var cid = document.getElementById('pl-class').value;
  if(!cid){ alert('اختر فصلاً أولاً'); return; }
  ss('pl-status','⏳ جارٍ التحميل...','in');
  var d = await api('/web/api/class-students/'+cid);
  if(!d||!d.ok){ ss('pl-status','❌ فشل التحميل','er'); return; }
  _plStudents = d.students||[];
  if(!_plStudents.length){ ss('pl-status','لا يوجد طلاب في هذا الفصل','wn'); return; }
  ss('pl-status','','in');
  var html = '<table style="width:100%;border-collapse:collapse">'
    +'<thead><tr style="background:var(--pr-lt)">'
    +'<th style="padding:8px;text-align:right;font-size:13px">تحديد</th>'
    +'<th style="padding:8px;text-align:right;font-size:13px">اسم الطالب</th>'
    +'<th style="padding:8px;text-align:right;font-size:13px">رقم الجوال</th>'
    +'<th style="padding:8px;text-align:right;font-size:13px">الحالة</th>'
    +'</tr></thead><tbody>';
  _plStudents.forEach(function(s,i){
    var hasPhone = s.phone && s.phone.trim();
    html += '<tr id="pl-row-'+i+'" style="border-bottom:1px solid #e5e7eb">'
      +'<td style="padding:8px;text-align:center">'
      +'<input type="checkbox" class="pl-chk" value="'+s.id+'" data-idx="'+i+'" '+(hasPhone?'checked':'disabled')+'>'
      +'</td>'
      +'<td style="padding:8px;font-size:13px">'+s.name+'</td>'
      +'<td style="padding:8px;font-size:13px;direction:ltr;text-align:right">'+(hasPhone?s.phone:'<span style="color:#aaa">لا يوجد</span>')+'</td>'
      +'<td style="padding:8px;font-size:12px" id="pl-st-'+i+'">'+(!hasPhone?'<span style="color:#aaa">لا يوجد جوال</span>':'')+'</td>'
      +'</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('pl-list').innerHTML = html;
  document.getElementById('pl-actions').style.display = '';
}

function plAll(v){
  document.querySelectorAll('.pl-chk:not(:disabled)').forEach(function(c){ c.checked=v; });
}

async function plSend(){
  var checks = Array.from(document.querySelectorAll('.pl-chk:checked'));
  if(!checks.length){ alert('حدد طالباً واحداً على الأقل'); return; }
  var btn = document.getElementById('pl-send-btn');
  btn.disabled = true;
  var prog = document.getElementById('pl-progress');
  var sent=0, failed=0, total=checks.length;
  prog.textContent = 'جارٍ الإرسال... 0 / '+total;
  for(var i=0;i<checks.length;i++){
    var idx = parseInt(checks[i].dataset.idx);
    var stu = _plStudents[idx];
    var stEl = document.getElementById('pl-st-'+idx);
    if(stEl) stEl.innerHTML = '⏳';
    var r = await fetch('/web/api/send-portal-link',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({student_id:stu.id, student_name:stu.name, phone:stu.phone})
    });
    var d = await r.json();
    if(d.ok){ sent++; if(stEl) stEl.innerHTML='<span style="color:green">✅ أُرسل</span>'; }
    else { failed++; if(stEl) stEl.innerHTML='<span style="color:red">❌ '+(d.msg||'فشل')+'</span>'; }
    prog.textContent = 'جارٍ الإرسال... '+(sent+failed)+' / '+total;
  }
  prog.innerHTML = '✅ أُرسل: <b>'+sent+'</b> &nbsp;|&nbsp; ❌ فشل: <b>'+failed+'</b>';
  btn.disabled = false;
}

/* ── ADMIN REPORT ── */
async function generateAdminReport(){
  var date=document.getElementById('ar-date')?document.getElementById('ar-date').value||today:today;
  ss('ar-status','جارٍ الإنشاء...','in');
  var d=await api('/web/api/daily-report?date='+date);
  if(!d||!d.ok){ss('ar-status','❌ خطأ','er');return;}
  ss('ar-status','✅ التقرير جاهز','ok');
  document.getElementById('ar-content').innerHTML='<div class="section"><pre style="font-family:Tajawal,Arial;font-size:13px;direction:rtl;white-space:pre-wrap;line-height:1.7">'+
    (d.report||'').replace(/</g,'&lt;')+'</pre></div>';
}
async function sendAdminReport(){
  var date=document.getElementById('ar-date').value||today;
  var r=await fetch('/web/api/send-daily-report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:date})});
  var d=await r.json();ss('ar-status',d.ok?'✅ تم الإرسال':'❌ '+d.msg,d.ok?'ok':'er');
}

/* ── STUDENT ANALYSIS ── */
var anCharts = {};
async function loadClsForAn(){
  var cid = document.getElementById('an-class').value; if(!cid) return;
  var d = await api('/web/api/class-students/'+cid); if(!d||!d.ok) return;
  document.getElementById('an-student').innerHTML = '<option value="">اختر طالباً</option>' +
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}

async function analyzeStudent(){
  var sid = document.getElementById('an-student').value;
  if(!sid){ alert('يرجى اختيار طالب أولاً'); return; }
  
  document.getElementById('an-cards').innerHTML = '<div class="loading">⏳ جارٍ التحميل...</div>';
  
  // إضافة زر بوابة ولي الأمر
  var actionArea = document.getElementById('an-action-area');
  if(!actionArea) {
      actionArea = document.createElement('div');
      actionArea.id = 'an-action-area';
      actionArea.style.marginBottom = '15px';
      document.getElementById('an-result').insertBefore(actionArea, document.getElementById('an-cards'));
  }
  actionArea.innerHTML = '<button class="btn bp2" onclick="getPortalLink(\''+sid+'\')"><i class="fas fa-share-alt"></i> مشاركة رابط بوابة ولي الأمر</button> <span id="an-portal-st"></span>';
  try {
    var res = await fetch('/web/api/student-analytics/' + sid);
    var d = await res.json();
    if(!d.ok){ alert('❌ فشل جلب البيانات: ' + d.msg); return; }
    
    var data = d.data;
    
    // (1) تحديث الكروت
    var cardsHtml = 
      crd(data.total_absences, (data.total_absences >= 5 ? '#C62828' : '#1565C0'), 'إجمالي الغياب', '<i class="fas fa-user-times"></i>') +
      crd(data.total_tardiness, '#E65100', 'دقائق التأخر', '<i class="fas fa-clock"></i>') +
      crd(data.behavior_referrals, '#C62828', 'المخالفات السلوكية', '<i class="fas fa-user-shield"></i>') +
      crd(data.academic_results, '#2E7D32', 'المعدل / التقدير', '<i class="fas fa-graduation-cap"></i>');
    document.getElementById('an-cards').innerHTML = cardsHtml;
    
    // (2) تحديث الجدول
    var tableHtml = (data.recent_events || []).map(function(ev){
      var color = ev.type==='غياب'?'#ef4444':(ev.type==='تأخر'?'#f59e0b':'#3b82f6');
      return '<tr>' +
        '<td>'+ev.date+'</td>' +
        '<td><span class="badge" style="background:'+color+';color:white">'+ev.type+'</span></td>' +
        '<td>'+(ev.details || '-')+'</td>' +
        '<td><span class="badge bg">'+(ev.status || '-')+'</span></td>' +
      '</tr>';
    }).join('') || '<tr><td colspan="4" style="color:#94A3B8;text-align:center">لا يوجد سجلات حالية</td></tr>';
    document.getElementById('an-table-body').innerHTML = tableHtml;
    
    // (3) الرسوم البيانية
    renderAnCharts(data);
    
  } catch(e) {
    console.error('analyzeStudent Error:', e);
    alert('❌ حدث خطأ أثناء التحليل');
  }
}

function renderAnCharts(data){
  // تدمير الرسوم السابقة إن وجدت
  if(anCharts.line) anCharts.line.destroy();
  if(anCharts.pie) anCharts.pie.destroy();
  
  // -- Line Chart (Absence Trend) --
  var lineCtx = document.getElementById('an-chart-line').getContext('2d');
  var trend = data.absence_trend || {};
  var labels = Object.keys(trend).sort();
  var points = labels.map(function(l){ return trend[l]; });
  
  anCharts.line = new Chart(lineCtx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'حالات الغياب',
        data: points,
        borderColor: '#1565C0',
        backgroundColor: 'rgba(21, 101, 192, 0.1)',
        tension: 0.3,
        fill: true
      }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
  
  // -- Pie Chart (Behavior/Tardiness) --
  var pieCtx = document.getElementById('an-chart-pie').getContext('2d');
  anCharts.pie = new Chart(pieCtx, {
    type: 'doughnut',
    data: {
      labels: ['تأخر', 'مخالفات سلوكية', 'جلسات إرشادية'],
      datasets: [{
        data: [data.total_tardiness, data.behavior_referrals, data.counselor_sessions],
        backgroundColor: ['#f59e0b', '#ef4444', '#10b981']
      }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
}

/* ── REPORTS ── */
async function loadReports(){
  var d=await api('/web/api/stats-monthly');if(!d||!d.ok)return;
  document.getElementById('rep-table').innerHTML=d.rows.map(function(r){
    return '<tr><td>'+r.month+'</td><td>'+r.school_days+'</td><td><span class="badge br">'+r.total_abs+'</span></td><td>'+r.unique_students+'</td></tr>';
  }).join('')||'<tr><td colspan="4" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function loadTopAbsent(){
  var d=await api('/web/api/top-absent');if(!d||!d.ok)return;
  document.getElementById('top-table').innerHTML=d.rows.map(function(r,i){
    return '<tr><td>'+(i+1)+'</td><td>'+(r.student_name||r.name)+'</td><td>'+r.class_name+'</td>'+
           '<td><span class="badge br">'+(r.days||r.count)+'</span></td><td>'+(r.last_date||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function loadAlerts(){
  var d=await api('/web/api/alerts-students');if(!d||!d.ok)return;
  document.getElementById('alerts-info').innerHTML='<span class="badge br">'+d.rows.length+' طالب تجاوزوا '+d.threshold+' أيام غياب هذا الشهر</span>';
  document.getElementById('alerts-table').innerHTML=d.rows.map(function(r,i){
    var sid=String(r.student_id);
    return '<tr data-sid="'+sid+'" data-name="'+r.student_name+'" data-cls="'+r.class_name+'" data-cnt="'+r.absence_count+'">'+
           '<td><input type="checkbox" class="al-chk" value="'+sid+'"></td>'+
           '<td>'+(i+1)+'</td><td>'+r.student_name+'</td><td>'+r.class_name+'</td>'+
           '<td><span class="badge br">'+r.absence_count+' يوم</span></td>'+
           '<td>'+(r.last_date||'-')+'</td><td>'+(r.parent_phone||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="7" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function loadAlertsTard(){
  var d=await api('/web/api/alerts-tardiness');if(!d||!d.ok)return;
  document.getElementById('alerts-tard-info').innerHTML='<span class="badge bo">'+d.rows.length+' طالب تجاوزوا '+d.threshold+' مرات تأخر هذا الشهر</span>';
  document.getElementById('alerts-tard-table').innerHTML=d.rows.map(function(r,i){
    var sid=String(r.student_id);
    var ref=r.already_referred?' style="background:#EDE9FE"':'';
    return '<tr'+ref+' data-sid="'+sid+'" data-name="'+r.student_name+'" data-cls="'+r.class_name+'" data-cnt="'+r.tardiness_count+'">'+
           '<td><input type="checkbox" class="al-chk-tard" value="'+sid+'"'+(r.already_referred?' disabled':'')+'></td>'+
           '<td>'+(i+1)+'</td><td>'+r.student_name+(r.already_referred?' ✅':'')+'</td><td>'+r.class_name+'</td>'+
           '<td><span class="badge bo">'+r.tardiness_count+'</span></td>'+
           '<td>'+(r.last_date||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا يوجد</td></tr>';
}
function alSelAll(tblId,checked){
  document.querySelectorAll('#'+tblId+' input[type=checkbox]:not(:disabled)').forEach(function(c){c.checked=checked;});
}
var _escRows=[];
async function loadAlertsEscaped(){
  var monthEl=document.getElementById('al-esc-month');
  if(!monthEl.value) monthEl.value=today.substring(0,7);
  var month=monthEl.value;
  var d=await api('/web/api/escaped-report?month='+month);
  var tbody=document.getElementById('al-esc-tbody');
  var st=document.getElementById('al-esc-st');
  if(!d||!d.ok){st.textContent='❌ خطأ في التحميل';tbody.innerHTML='';return;}
  _escRows=d.rows||[];
  st.textContent=_escRows.length?_escRows.length+' طالب مسجَّل هارب هذا الشهر':'';
  if(!_escRows.length){tbody.innerHTML='<tr><td colspan="7" style="color:#9CA3AF;text-align:center">لا يوجد هاربون هذا الشهر</td></tr>';return;}
  tbody.innerHTML=_escRows.map(function(r,i){
    var notesShort=(r.notes||'').replace('هروب من المدرسة — الحصص الغائبة: ','');
    var referred=r.status==='مُحال';
    return '<tr style="background:#FEF2F2" data-idx="'+i+'" data-sid="'+r.student_id+'" data-name="'+r.student_name+'" data-cls="'+r.class_name+'">'+
      '<td><input type="checkbox" class="al-esc-chk" value="'+i+'"'+(referred?' disabled':'')+'></td>'+
      '<td style="color:#dc2626;font-weight:700">'+(i+1)+'</td>'+
      '<td>'+r.date+'</td>'+
      '<td style="color:#dc2626;font-weight:700">🏃 '+r.student_name+'</td>'+
      '<td>'+r.class_name+'</td>'+
      '<td style="font-size:12px">'+notesShort+'</td>'+
      '<td><span style="color:'+(referred?'#16a34a':'#dc2626')+';font-weight:700">'+(referred?'✅ مُحال للموجّه':'جديد')+'</span></td>'+
      '</tr>';
  }).join('');
}
async function referEscapedToCounselor(){
  var checked=[...document.querySelectorAll('.al-esc-chk:checked')];
  if(!checked.length){ss('al-esc-st','اختر طالباً على الأقل','er');return;}
  var students=checked.map(function(chk){
    var idx=parseInt(chk.value);
    var r=_escRows[idx];
    return {student_id:r.student_id,student_name:r.student_name,class_name:r.class_name,
            absence_count:0,referral_type:'هروب'};
  });
  ss('al-esc-st','⏳ جارٍ التحويل...','ai');
  var r=await fetch('/web/api/refer-to-counselor',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({students:students,date:today,ref_type:'هروب'})});
  var d=await r.json();
  if(d&&d.ok){
    ss('al-esc-st','✅ تم التحويل: '+d.added+' طالب','ok');
    loadAlertsEscaped();
  } else {
    ss('al-esc-st','❌ '+(d&&d.msg||'خطأ'),'er');
  }
}
async function referToCounselor(type){
  var tblId=type==='غياب'?'alerts-table':'alerts-tard-table';
  var stId=type==='غياب'?'al-abs-st':'al-tard-st';
  var rows=document.querySelectorAll('#'+tblId+' tr');
  var students=[];
  rows.forEach(function(tr){
    var chk=tr.querySelector('input[type=checkbox]');
    if(chk&&chk.checked){
      students.push({
        id:tr.getAttribute('data-sid'),
        name:tr.getAttribute('data-name'),
        class_name:tr.getAttribute('data-cls'),
        count:parseInt(tr.getAttribute('data-cnt'))||0
      });
    }
  });
  if(!students.length){ss(stId,'حدد طلاباً أولاً','er');return;}
  if(!confirm('تحويل '+students.length+' طالب للموجّه الطلابي كـ "'+type+'"؟'))return;
  ss(stId,'⏳ جارٍ التحويل...','ai');
  try{
    var r=await fetch('/web/api/refer-to-counselor',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type:type,students:students})});
    var d=await r.json();
    if(d.ok){
      var msg='✅ تم تحويل '+d.added+' طالب';
      if(d.skipped)msg+=' (تجاهل '+d.skipped+' محوّل مسبقاً)';
      ss(stId,msg,'ok');
      if(type==='غياب')loadAlerts();else loadAlertsTard();
    }else ss(stId,'❌ '+(d.msg||'فشل'),'er');
  }catch(e){ss(stId,'❌ خطأ في الاتصال','er');}
}

/* ── STUDENTS ── */
async function loadStudents(){
  var d=await api('/web/api/students');if(!d||!d.ok)return;
  var all=[];d.classes.forEach(function(c){c.students.forEach(function(s){all.push(Object.assign({},s,{class_name:c.name,class_id:c.id}));});});
  window._students=all;renderStuTbl(all);renderPhoTbl(all);
  var sm=document.getElementById('sm-sum');if(sm)sm.innerHTML='<span class="badge bb">'+all.length+' طالب إجمالاً</span>';
}
function filterStudents(){
  var phTab=document.getElementById('tab-phones');
  var phActive=phTab&&phTab.classList.contains('active');
  var q=(phActive?document.getElementById('ph-q'):document.getElementById('sm-q')||document.getElementById('ph-q'));
  var cls=(phActive?document.getElementById('ph-cls'):document.getElementById('sm-cls')||document.getElementById('ph-cls'));
  var qv=(q&&q.value||'').toLowerCase();
  var clsv=cls&&cls.value||'';
  var f=(window._students||[]).filter(function(s){
    return(!qv||(s.name||'').toLowerCase().includes(qv)||(s.id||'').includes(qv)||(s.phone||'').includes(qv))
        &&(!clsv||s.class_id===clsv);
  });
  renderStuTbl(f);renderPhoTbl(f);
}
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
function renderPhoTbl(arr){
  var tb=document.getElementById('ph-table');if(!tb)return;
  tb.innerHTML=arr.slice(0,200).map(function(s){
    return '<tr><td>'+s.name+'</td><td>'+s.class_name+'</td><td>'+(s.phone||'—')+'</td>'+
           '<td><button class="btn bp2 bsm" onclick="editPhone(\''+s.id+'\')">✏️</button></td></tr>';
  }).join('')||'<tr><td colspan="4" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function editPhone(id){
  var phone=prompt('رقم الجوال الجديد (05xxxxxxxx):');if(!phone)return;
  var r=await fetch('/web/api/update-student-phone',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:id,phone:phone})});
  var d=await r.json();alert(d.ok?'✅ تم التحديث':'❌ '+(d.msg||'خطأ'));if(d.ok)loadStudents();
}

/* ── USERS ── */
var _usSelected = null;
var _usData = [];
var _US_ROLES = {admin:'مدير',deputy:'وكيل',staff:'إداري',counselor:'موجه طلابي',
                 activity_leader:'رائد نشاط',teacher:'معلم',lab:'محضر',guard:'حارس'};
var _US_ALL_TABS = [
  'لوحة المراقبة','المراقبة الحية','روابط الفصول','تسجيل الغياب','تسجيل التأخر',
  'طلب استئذان','سجل الغياب','سجل التأخر','الأعذار','الاستئذان','إدارة الغياب',
  'الموجّه الطلابي','استلام تحويلات','التقارير / الطباعة','تقرير الفصل','تقرير الإدارة',
  'تحليل طالب','أكثر الطلاب غياباً','الإشعارات الذكية','إرسال رسائل الغياب',
  'إرسال رسائل التأخر','روابط بوابة أولياء الأمور','التعاميم والنشرات','قصص المدرسة',
  'تعزيز الحضور الأسبوعي','لوحة الصدارة (النقاط)','إدارة الطلاب','إضافة طالب',
  'إدارة الفصول','إدارة الجوالات','الطلاب المستثنون','نشر النتائج','تصدير نور',
  'زيارات أولياء الأمور','تحويل طالب','نماذج المعلم','تحليل النتائج',
  'إعدادات المدرسة','المستخدمون','النسخ الاحتياطية','شواهد الأداء','الرسائل الداخلية',
  'هروب واستئذان'
];
var _US_ROLE_DEFAULTS = {
  deputy:['لوحة المراقبة','المراقبة الحية','روابط الفصول','تسجيل الغياب','تسجيل التأخر',
          'طلب استئذان','سجل الغياب','سجل التأخر','الأعذار','الاستئذان','إدارة الغياب',
          'الموجّه الطلابي','استلام تحويلات','التقارير / الطباعة','تقرير الفصل','تقرير الإدارة',
          'تحليل طالب','أكثر الطلاب غياباً','الإشعارات الذكية','إرسال رسائل الغياب',
          'إرسال رسائل التأخر','روابط بوابة أولياء الأمور','التعاميم والنشرات','قصص المدرسة',
          'تعزيز الحضور الأسبوعي','لوحة الصدارة (النقاط)','إدارة الطلاب','إضافة طالب',
          'إدارة الفصول','إدارة الجوالات','الطلاب المستثنون','نشر النتائج','تصدير نور',
          'زيارات أولياء الأمور','الرسائل الداخلية','هروب واستئذان'],
  staff:['لوحة المراقبة','المراقبة الحية','روابط الفصول','تسجيل الغياب','تسجيل التأخر',
         'طلب استئذان','سجل الغياب','سجل التأخر','الأعذار','الاستئذان','التعاميم والنشرات',
         'إدارة الطلاب','إضافة طالب','إدارة الجوالات','الطلاب المستثنون','قصص المدرسة',
         'لوحة الصدارة (النقاط)','تحليل طالب','زيارات أولياء الأمور','الرسائل الداخلية','هروب واستئذان'],
  counselor:['لوحة المراقبة','المراقبة الحية','روابط الفصول','سجل الغياب','سجل التأخر',
             'الأعذار','الموجّه الطلابي','تحليل طالب','أكثر الطلاب غياباً','الإشعارات الذكية',
             'التعاميم والنشرات','قصص المدرسة','تعزيز الحضور الأسبوعي','لوحة الصدارة (النقاط)',
             'زيارات أولياء الأمور','الرسائل الداخلية'],
  activity_leader:['لوحة المراقبة','التعاميم والنشرات','قصص المدرسة','لوحة الصدارة (النقاط)','تحليل طالب','نماذج المعلم','الرسائل الداخلية'],
  teacher:['لوحة المراقبة','تحويل طالب','نماذج المعلم','تحليل النتائج','التعاميم والنشرات','لوحة الصدارة (النقاط)','تحليل طالب','الرسائل الداخلية'],
  lab:['لوحة المراقبة','نماذج المعلم','التعاميم والنشرات','لوحة الصدارة (النقاط)','تحليل طالب','شواهد الأداء','الرسائل الداخلية'],
  guard:['لوحة المراقبة','تسجيل التأخر','المراقبة الحية','لوحة الصدارة (النقاط)','تحليل طالب','الرسائل الداخلية']
};

async function loadUsers(){
  var d=await api('/web/api/users');
  if(!d||!d.ok){document.getElementById('us-tbody').innerHTML='';return;}
  _usData=d.users||[];
  _usRenderTable();
  _usBuildTabsGrid();
}
function _usRenderTable(){
  document.getElementById('us-tbody').innerHTML=_usData.map(function(u){
    var isAdm=u.role==='admin';
    var tabsInfo=isAdm?'كل التبويبات':(u.allowed_tabs?(JSON.parse(u.allowed_tabs||'[]').length+' تبويب'):'افتراضي');
    var sel=_usSelected&&_usSelected.id===u.id;
    return '<tr onclick="usSelect('+u.id+')" style="cursor:pointer;'+(sel?'background:var(--pr-lt)':'')+
           (isAdm?';color:#7C3AED;font-weight:700':'')+(!u.active?';color:#9CA3AF':'')+'">'+
           '<td>'+u.id+'</td><td>'+u.username+'</td><td>'+(u.full_name||'-')+'</td>'+
           '<td>'+(_US_ROLES[u.role]||u.role)+'</td>'+
           '<td>'+(u.active?'<span style="color:green">✅ نشط</span>':'<span style="color:#aaa">⛔ معطل</span>')+'</td>'+
           '<td style="font-size:11px;color:#888">'+(u.last_login||'-')+'</td>'+
           '</tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF;text-align:center">لا يوجد مستخدمون</td></tr>';
}
function _usBuildTabsGrid(){
  var grid=document.getElementById('us-tabs-grid');
  grid.innerHTML=_US_ALL_TABS.map(function(t){
    return '<label style="display:flex;align-items:center;gap:6px;font-size:12px;padding:4px 6px;border-radius:6px;cursor:pointer;border:1px solid #e5e7eb">'+
           '<input type="checkbox" class="us-tab-chk" value="'+t+'"> '+t+'</label>';
  }).join('');
}
function usSelect(id){
  _usSelected=_usData.find(function(u){return u.id===id;})||null;
  _usRenderTable();
  if(!_usSelected)return;
  var u=_usSelected;
  document.getElementById('us-perm-title').textContent='تبويبات المستخدم: '+u.full_name+' — '+('' +_US_ROLES[u.role]||u.role);
  if(u.role==='admin'){
    document.querySelectorAll('.us-tab-chk').forEach(function(c){c.checked=true;c.disabled=true;});
    return;
  }
  var allowed=[];
  try{allowed=JSON.parse(u.allowed_tabs||'null')||_US_ROLE_DEFAULTS[u.role]||[];}catch(e){allowed=_US_ROLE_DEFAULTS[u.role]||[];}
  document.querySelectorAll('.us-tab-chk').forEach(function(c){c.disabled=false;c.checked=allowed.indexOf(c.value)>-1;});
}
function usSelAll(v){document.querySelectorAll('.us-tab-chk:not(:disabled)').forEach(function(c){c.checked=v;});}
async function usSaveTabs(){
  if(!_usSelected){ss('us-st','اختر مستخدماً أولاً','er');return;}
  var tabs=Array.from(document.querySelectorAll('.us-tab-chk:checked')).map(function(c){return c.value;});
  var r=await fetch('/web/api/users/allowed-tabs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({username:_usSelected.username,tabs:tabs})});
  var d=await r.json();
  ss('us-st',d.ok?'✅ تم حفظ الصلاحيات':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  if(d.ok){_usSelected.allowed_tabs=JSON.stringify(tabs);_usRenderTable();}
}
function usResetTabs(){
  if(!_usSelected){ss('us-st','اختر مستخدماً أولاً','er');return;}
  var defs=_US_ROLE_DEFAULTS[_usSelected.role]||[];
  document.querySelectorAll('.us-tab-chk').forEach(function(c){c.checked=defs.indexOf(c.value)>-1;});
}
async function usToggle(){
  if(!_usSelected){ss('us-st','اختر مستخدماً أولاً','er');return;}
  var newActive=!_usSelected.active;
  var r=await fetch('/web/api/users/toggle-active',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({user_id:_usSelected.id,active:newActive})});
  var d=await r.json();
  ss('us-st',d.ok?'✅ تم التحديث':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  if(d.ok){_usSelected.active=newActive;_usRenderTable();}
}
async function usChangePw(){
  if(!_usSelected){ss('us-st','اختر مستخدماً أولاً','er');return;}
  var pw=prompt('كلمة المرور الجديدة لـ '+_usSelected.username+':');
  if(!pw)return;
  var r=await fetch('/web/api/users/update-password',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({username:_usSelected.username,password:pw})});
  var d=await r.json();ss('us-st',d.ok?'✅ تم تغيير كلمة المرور':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
}
async function usDelete(){
  if(!_usSelected){ss('us-st','اختر مستخدماً أولاً','er');return;}
  if(!confirm('حذف المستخدم '+_usSelected.username+'؟'))return;
  var r=await fetch('/web/api/users/'+_usSelected.id,{method:'DELETE'});
  var d=await r.json();
  if(d.ok){_usSelected=null;ss('us-st','✅ تم الحذف','ok');loadUsers();}
  else ss('us-st','❌ '+(d.msg||'خطأ'),'er');
}
function usSendCreds(){
  if(!_usSelected){ss('us-st','اختر مستخدماً أولاً','er');return;}
  document.getElementById('uc-name').value  = _usSelected.full_name || _usSelected.username;
  document.getElementById('uc-uname').value = _usSelected.username;
  document.getElementById('uc-phone').value = _usSelected.phone || '';
  document.getElementById('uc-st').textContent = '';
  document.getElementById('us-creds-modal').style.display = 'flex';
}
async function usSendCredsConfirm(){
  var phone = document.getElementById('uc-phone').value.trim();
  var st    = document.getElementById('uc-st');
  if(!phone){st.textContent='❌ أدخل رقم الجوال';st.style.color='#dc2626';return;}
  st.textContent='⏳ جارٍ الإرسال...';st.style.color='#1565C0';
  var r = await fetch('/web/api/users/send-creds',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({user_id:_usSelected.id, phone:phone})});
  var d = await r.json();
  if(d.ok){
    st.textContent='✅ تم الإرسال بنجاح';st.style.color='#16a34a';
    setTimeout(function(){document.getElementById('us-creds-modal').style.display='none';loadUsers();},1500);
  } else {
    st.textContent='❌ '+(d.msg||'فشل الإرسال');st.style.color='#dc2626';
  }
}
function usOpenAdd(){document.getElementById('us-add-modal').style.display='flex';}
async function usAddConfirm(){
  var un=document.getElementById('us-new-uname').value.trim();
  var fn=document.getElementById('us-new-fname').value.trim();
  var pw=document.getElementById('us-new-pw').value;
  var rl=document.getElementById('us-new-role').value;
  if(!un||!pw){document.getElementById('us-add-st').textContent='❌ اكمل الحقول المطلوبة';return;}
  var r=await fetch('/web/api/users/create',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({username:un,full_name:fn,password:pw,role:rl})});
  var d=await r.json();
  document.getElementById('us-add-st').textContent=d.ok?'✅ تم الإضافة':'❌ '+(d.msg||'خطأ');
  if(d.ok){setTimeout(function(){document.getElementById('us-add-modal').style.display='none';loadUsers();},800);}
}
/* دوال قديمة للتوافق */
async function addUser(){usOpenAdd();}
async function delUser(id){_usSelected=_usData.find(function(u){return u.id===id;})||null;usDelete();}

/* ── BACKUP ── */
var _bkRestoreFile='';
async function loadBackups(){
  var d=await api('/web/api/backups');if(!d||!d.ok){document.getElementById('bk-table').innerHTML='';return;}
  document.getElementById('bk-table').innerHTML=(d.backups||[]).map(function(b){
    var fname=b.filename.split('/').pop().split('\\').pop();
    var dt=b.created_at?b.created_at.substring(0,16).replace('T',' '):'—';
    return '<tr><td style="font-size:12px">'+fname+'</td><td>'+(b.size_kb||0)+' KB</td>'+
           '<td style="font-size:12px">'+dt+'</td>'+
           '<td><a href="/web/api/download-backup/'+encodeURIComponent(b.filename)+'" class="btn bp1 bsm">⬇️</a></td>'+
           '<td><button class="btn bp5 bsm" onclick="openBkModal(\''+b.filename.replace(/\\/g,'\\\\').replace(/'/g,"\\'")+'\')" >↩️</button></td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا توجد نسخ</td></tr>';
}
function openBkModal(filename){
  _bkRestoreFile=filename;
  document.getElementById('bk-restore-fname').textContent=filename.split('/').pop().split('\\').pop();
  document.getElementById('bk-restore-pw').value='';
  document.getElementById('bk-restore-st').innerHTML='';
  document.getElementById('bk-restore-modal').style.display='flex';
  setTimeout(function(){document.getElementById('bk-restore-pw').focus();},100);
}
function closeBkModal(){document.getElementById('bk-restore-modal').style.display='none';}
async function doRestore(){
  var pw=document.getElementById('bk-restore-pw').value.trim();
  if(!pw){ss('bk-restore-st','أدخل كلمة المرور','er');return;}
  ss('bk-restore-st','⏳ جارٍ الاستعادة...','in');
  document.querySelector('#bk-restore-modal .btn.bp3').disabled=true;
  var r=await fetch('/web/api/restore-backup',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({filename:_bkRestoreFile,password:pw})});
  var d=await r.json();
  document.querySelector('#bk-restore-modal .btn.bp3').disabled=false;
  if(d.ok){
    ss('bk-restore-st','✅ تمت الاستعادة — أعد تحميل الصفحة لتطبيق التغييرات','ok');
    setTimeout(function(){closeBkModal();location.reload();},2000);
  } else {
    ss('bk-restore-st','❌ '+(d.msg||'فشل'),'er');
  }
}
async function createBackup(){
  ss('bk-st','⏳ جارٍ الإنشاء...','in');
  var r=await fetch('/web/api/create-backup',{method:'POST'});var d=await r.json();
  ss('bk-st',d.ok?'✅ تم إنشاء النسخة':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');if(d.ok)loadBackups();
}

/* ── SETTINGS ── */
async function loadSettings(){
  var d=await api('/web/api/config');if(!d)return;
  if(d.school_name)document.getElementById('ss-name').value=d.school_name;
  if(d.school_gender)document.getElementById('ss-gender').value=d.school_gender;
  if(d.alert_absence_threshold)document.getElementById('ss-thr').value=d.alert_absence_threshold;
  if(d.message_template)document.getElementById('ss-abs-tpl').value=d.message_template;
  if(d.tardiness_message_template)document.getElementById('ss-tard-tpl').value=d.tardiness_message_template;
  if(d.admin_report_phone)document.getElementById('ss-rpt-phone').value=d.admin_report_phone;
  if(d.wa_phone)document.getElementById('ss-wa-phone').value=d.wa_phone;
  if(d.telegram_backup_token)document.getElementById('ss-tg-token').value=d.telegram_backup_token;
  if(d.telegram_backup_chat)document.getElementById('ss-tg-chat').value=d.telegram_backup_chat;
  // تحديث رابط vCard
  var base=window.location.origin;
  var link=base+'/web/save-contact';
  var lnkEl=document.getElementById('sn-vcard-link');
  var dlEl=document.getElementById('sn-vcard-dl');
  if(lnkEl)lnkEl.value=link;
  if(dlEl)dlEl.href=link;
}
async function saveWaSettings(){
  var phone=document.getElementById('ss-wa-phone').value.trim();
  var r=await fetch('/web/api/save-config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({wa_phone:phone})});
  var d=await r.json();
  ss('ss-wa-st',d.ok?'✅ تم حفظ الرقم':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  if(d.ok)snLoadPreview();
}
function snCopyVcard(){
  var el=document.getElementById('sn-vcard-link');
  if(!el||!el.value){ss('sn-vcard-st','لم يتم تعيين الرابط بعد','er');return;}
  navigator.clipboard.writeText(el.value).then(function(){ss('sn-vcard-st','✅ تم نسخ الرابط','ok');}).catch(function(){el.select();document.execCommand('copy');ss('sn-vcard-st','✅ تم نسخ الرابط','ok');});
}
async function saveSchoolSettings(){
  var r=await fetch('/web/api/save-config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({school_name:document.getElementById('ss-name').value,
      school_gender:document.getElementById('ss-gender').value,
      alert_absence_threshold:parseInt(document.getElementById('ss-thr').value)||5})});
  var d=await r.json();ss('ss-st',d.ok?'✅ تم الحفظ':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
}
async function saveMsgTemplates(){
  var r=await fetch('/web/api/save-config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message_template:document.getElementById('ss-abs-tpl').value,
      tardiness_message_template:document.getElementById('ss-tard-tpl').value})});
  var d=await r.json();alert(d.ok?'✅ تم حفظ القوالب':'❌ '+(d.msg||'خطأ'));
}
async function saveAdvSettings(){
  var r=await fetch('/web/api/save-config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({public_url:document.getElementById('ss-url').value,
      admin_report_phone:document.getElementById('ss-rpt-phone').value})});
  var d=await r.json();alert(d.ok?'✅ تم الحفظ':'❌ '+(d.msg||'خطأ'));
}
async function saveTelegramBackup(){
  var token=document.getElementById('ss-tg-token').value.trim();
  var chat=document.getElementById('ss-tg-chat').value.trim();
  var st=document.getElementById('tg-backup-st');
  if(!token||!chat){st.textContent='⚠️ أدخل التوكن ومعرّف القناة';st.style.color='#d97706';return;}
  var r=await fetch('/web/api/save-config',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({telegram_backup_token:token,telegram_backup_chat:chat})});
  var d=await r.json();
  st.textContent=d.ok?'✅ تم الحفظ':'❌ '+(d.msg||'خطأ');
  st.style.color=d.ok?'#16a34a':'#dc2626';
}
async function testTelegramBackup(){
  var st=document.getElementById('tg-backup-st');
  st.textContent='⏳ جارٍ الإرسال...';st.style.color='#1565C0';
  try{
    var r=await fetch('/web/api/backup/send-telegram',{method:'POST'});
    var d=await r.json();
    st.textContent=d.ok?'✅ تم الإرسال بنجاح! تحقق من قناة Telegram':'❌ '+(d.msg||'فشل الإرسال');
    st.style.color=d.ok?'#16a34a':'#dc2626';
  }catch(e){st.textContent='❌ خطأ في الاتصال';st.style.color='#dc2626';}
}
async function triggerEmergencyUpdate(){
  var st=document.getElementById('eu-status');
  if(!confirm('سيتم تحديث البرنامج على السيرفر وإعادة تشغيله فوراً. هل أنت متأكد؟')) return;
  st.textContent='جارٍ التحديث...';st.style.color='#1565C0';
  try{
    var r=await fetch('/web/api/admin/trigger-update',{method:'POST'});
    var d=await r.json();
    if(d.ok){st.textContent='تم التحديث إلى '+d.msg+' — البرنامج يُعاد تشغيله الآن';st.style.color='#16a34a';}
    else{st.textContent=d.msg||'لا يوجد تحديث جديد';st.style.color='#555';}
  }catch(e){st.textContent='انقطع الاتصال — البرنامج يُعاد تشغيله';st.style.color='#d97706';}
}
async function checkWA(){
  var el=document.getElementById('wa-ind');
  el.className='ab ai';el.textContent='🔄 جارٍ الفحص...';
  try{
    var d=await api('/web/api/check-whatsapp');
    if(d&&d.ok){el.className='ab as';el.textContent='✅ خادم واتساب متصل ويعمل';}
    else{el.className='ab ae';el.textContent='❌ خادم واتساب غير متصل — '+(d&&d.msg?d.msg:'');}
  }catch(e){el.className='ab ae';el.textContent='❌ خطأ في الفحص';}
}

/* ── SCHEDULE ── */
async function loadSchedule(){
  var d=await api('/web/api/schedule');if(!d||!d.ok){document.getElementById('sch-tbl').innerHTML='<p style="color:var(--mu)">لا يوجد جدول</p>';return;}
  var days=['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس'];
  document.getElementById('sch-tbl').innerHTML=(d.items||[]).map(function(it){
    return '<div class="sci"><div><strong>'+it.class_name+'</strong><br><span style="font-size:12px;color:var(--mu)">'+(days[it.day_of_week]||'')+' — الحصة '+it.period+'</span></div>'+
           '<div style="font-size:12px">'+(it.teacher_name||'—')+'</div></div>';
  }).join('')||'<p style="color:var(--mu)">لا يوجد</p>';
}
async function addScheduleItem(){
  var cls=document.getElementById('sch-cls').value;if(!cls){ss('sch-st','اختر فصلاً','er');return;}
  var cname=document.getElementById('sch-cls').options[document.getElementById('sch-cls').selectedIndex].text;
  var r=await fetch('/web/api/save-schedule',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({class_id:cls,class_name:cname,day_of_week:parseInt(document.getElementById('sch-day').value),
      period:parseInt(document.getElementById('sch-per').value),teacher_name:document.getElementById('sch-tch').value})});
  var d=await r.json();ss('sch-st',d.ok?'✅ تمت الإضافة':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');if(d.ok)loadSchedule();
}

/* ── RECIPIENTS ── */
async function loadRecipients(){
  var d=await api('/web/api/tardiness-recipients');if(!d||!d.ok){document.getElementById('recipients-list').innerHTML='<p style="color:var(--mu)">لا يوجد مستلمون</p>';return;}
  document.getElementById('recipients-list').innerHTML='<div class="tw"><table><thead><tr><th>الاسم</th><th>الجوال</th><th>الدور</th><th>حذف</th></tr></thead><tbody>'+
    (d.recipients||[]).map(function(r){return '<tr><td>'+r.name+'</td><td>'+r.phone+'</td><td>'+(r.role||'-')+'</td>'+
      '<td><button class="btn bp3 bsm">حذف</button></td></tr>';}).join('')+'</tbody></table></div>';
}
async function addRecipient(){
  var name=document.getElementById('rec-name').value.trim();var phone=document.getElementById('rec-phone').value.trim();
  var role=document.getElementById('rec-role').value;if(!name||!phone){ss('rec-st','اكمل الاسم والجوال','er');return;}
  var r=await fetch('/web/api/add-tardiness-recipient',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,phone:phone,role:role})});
  var d=await r.json();ss('rec-st',d.ok?'✅ تمت الإضافة':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');if(d.ok)loadRecipients();
}

/* ── PARTIAL ABSENCE ── */
var _paRows=[], _paDate='';
async function loadPartialAbsences(){
  var date=document.getElementById('pa-date').value;
  var minP=document.getElementById('pa-min-period').value;
  if(!date){ss('pa-st','اختر تاريخاً','er');return;}
  ss('pa-st','⏳ جارٍ البحث...','ai');
  var d=await api('/web/api/partial-absences?date='+date+'&min_period='+minP);
  if(!d||!d.ok){ss('pa-st','❌ '+(d&&d.msg||'خطأ'),'er');return;}
  _paRows=d.rows||[]; _paDate=date;
  if(!_paRows.length){ss('pa-st','✅ لا يوجد طلاب في هذه الحالة ليوم '+date,'ok');document.getElementById('pa-list').innerHTML='';return;}
  ss('pa-st',_paRows.length+' طالب بحاجة تصنيف','ai');
  var statusColors={'هارب':'#dc2626','مستأذن':'#2563eb','غير محدد':'#94a3b8'};
  var html='<div class="tw"><table><thead><tr><th>#</th><th>الطالب</th><th>الفصل</th><th>حصص الغياب</th><th>الحالة</th><th>تصنيف</th></tr></thead><tbody>';
  _paRows.forEach(function(r,i){
    var sid=String(r.student_id);
    var periods=(r.absent_periods||'').split(',').map(function(p){return 'ح'+p;}).join('، ');
    var sc=statusColors[r.status]||'#94a3b8';
    var classified=r.status!=='غير محدد';
    var rowBg=r.status==='هارب'?'background:#FEF2F2':r.status==='مستأذن'?'background:#EFF6FF':'';
    html+='<tr style="'+rowBg+'">';
    html+='<td>'+(i+1)+'</td><td>'+r.student_name+'</td><td>'+r.class_name+'</td>';
    html+='<td>'+periods+'</td>';
    html+='<td><span style="color:'+sc+';font-weight:700">'+r.status+'</span></td>';
    html+='<td style="white-space:nowrap;display:flex;gap:4px">';
    if(!classified||r.status==='هارب')
      html+='<button class="btn bsm" style="background:#dc2626;color:#fff" onclick="paMarkEscaped(this,'+i+')">🏃 هارب</button>';
    if(!classified||r.status==='مستأذن')
      html+='<button class="btn bsm" style="background:#2563eb;color:#fff" onclick="paMarkPermitted(this,'+i+')">📋 مستأذن</button>';
    if(classified)
      html+='<button class="btn bp2 bsm" onclick="paReset(\''+sid+'\')">↩</button>';
    html+='</td></tr>';
  });
  html+='</tbody></table></div>';
  document.getElementById('pa-list').innerHTML=html;
}
async function paMarkEscaped(btn, idx){
  var row=_paRows[idx]; if(!row)return;
  btn.disabled=true; btn.textContent='⏳';
  var r=await fetch('/web/api/partial-absences/mark-escaped',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:row.student_id,student_name:row.student_name,
      class_name:row.class_name,date:_paDate,absent_periods:row.absent_periods})});
  var d=await r.json();
  if(d&&d.ok){loadPartialAbsences();loadEscapedReport();}
  else{btn.disabled=false;btn.textContent='🏃 هارب';alert('❌ '+(d&&d.msg||'خطأ'));}
}
async function paMarkPermitted(btn, idx){
  var row=_paRows[idx]; if(!row)return;
  btn.disabled=true; btn.textContent='⏳';
  var r=await fetch('/web/api/partial-absences/mark-permitted',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:row.student_id,student_name:row.student_name,
      class_name:row.class_name,date:_paDate,absent_periods:row.absent_periods})});
  var d=await r.json();
  if(d&&d.ok){loadPartialAbsences();}
  else{btn.disabled=false;btn.textContent='📋 مستأذن';alert('❌ '+(d&&d.msg||'خطأ'));}
}
async function paReset(sid){
  var r=await fetch('/web/api/partial-absences/status',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:sid,status:'غير محدد',date:_paDate})});
  var d=await r.json();
  if(d&&d.ok) loadPartialAbsences();
}
async function loadEscapedReport(){
  var month=today.substring(0,7);
  var d=await api('/web/api/escaped-report?month='+month);
  var box=document.getElementById('pa-escaped-report');
  if(!d||!d.ok||!d.rows||!d.rows.length){box.innerHTML='<div class="ab ai" style="font-size:13px">لا يوجد هاربون هذا الشهر</div>';return;}
  var html='<div class="tw"><table><thead><tr><th>التاريخ</th><th>الطالب</th><th>الفصل</th><th>التفاصيل</th><th>الحالة</th></tr></thead><tbody>';
  d.rows.forEach(function(r){
    html+='<tr style="background:#FEF2F2"><td>'+r.date+'</td><td style="color:#dc2626;font-weight:700">'+r.student_name+'</td><td>'+r.class_name+'</td><td style="font-size:12px;color:#64748B">'+r.notes+'</td><td>'+r.status+'</td></tr>';
  });
  html+='</tbody></table></div>';
  box.innerHTML=html;
}

/* ── COUNSELOR ── */
async function loadClsForCo(){
  var cid=document.getElementById('co-cls').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('co-stu').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
async function loadCoSessions(){
  var d=await api('/web/api/counselor-sessions');if(!d||!d.ok)return;
  document.getElementById('co-ses-tbl').innerHTML=(d.sessions||[]).map(function(s){
    return '<tr><td>'+s.date+'</td><td>'+s.student_name+'</td><td>'+s.class_name+'</td><td>'+(s.reason||'-')+'</td><td>'+(s.action_taken||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function saveCouSession(){
  var stuSel=document.getElementById('co-stu');var clsSel=document.getElementById('co-cls');
  var r=await fetch('/web/api/add-counselor-session',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({date:document.getElementById('co-date').value,
      student_id:stuSel.value,student_name:stuSel.options[stuSel.selectedIndex]?stuSel.options[stuSel.selectedIndex].text:'',
      class_name:clsSel.options[clsSel.selectedIndex]?clsSel.options[clsSel.selectedIndex].text:'',
      reason:document.getElementById('co-reason').value,notes:document.getElementById('co-notes').value,
      action_taken:document.getElementById('co-action').value})});
  var d=await r.json();ss('co-st',d.ok?'✅ تم حفظ الجلسة':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');if(d.ok)loadCoSessions();
}

/* ── COUNSELOR — قائمة المحوّلين الموحَّدة (مرآة للتطبيق المكتبي) ── */
var _coRows=[];
async function loadCounselorList(){
  var d=await api('/web/api/counselor-list');
  var tbl=document.getElementById('co-main-tbl');
  if(!d||!d.ok){
    if(tbl)tbl.innerHTML='<tr><td colspan="7" style="color:#9CA3AF">خطأ في التحميل</td></tr>';
    return;
  }
  _coRows=d.rows||[];
  document.getElementById('co-main-info').innerHTML='<span class="badge bb">'+_coRows.length+' طالب محوَّل للموجّه</span>';
  renderCounselorList(_coRows);
}
function renderCounselorList(rows){
  var tbl=document.getElementById('co-main-tbl');
  if(!rows||!rows.length){
    tbl.innerHTML='<tr><td colspan="7" style="color:#9CA3AF">لا يوجد محوّلون</td></tr>';
    return;
  }
  tbl.innerHTML=rows.map(function(r){
    var bg = 'background:#FFF7ED';
    if(r.referral_type === 'غياب') bg = 'background:#FFF0F0';
    else if(r.referral_type === 'تحويل معلم') bg = 'background:#EDE7F6';
    else if(r.referral_type === 'هروب') bg = 'background:#dc2626;color:#fff';
    var sid=String(r.student_id).replace(/'/g,"\\'");
    var sn=String(r.student_name).replace(/'/g,"\\'");
    var cn=String(r.class_name).replace(/'/g,"\\'");
    
    var buttons = '';
    if (r.referral_type === 'تحويل معلم') {
      buttons = `<button class="btn bp4 bsm" onclick="openCounselorReferralForm('${r.ref_id}')">📋 إجراءات التحويل</button>`;
    } else {
      buttons = `<button class="btn bp1 bsm" onclick="viewCounselorHistory('${sid}','${sn}')" title="السجل الإرشادي">📄</button> `+
        `<div style="display:inline-block;position:relative" onmouseleave="this.querySelector('.drp').style.display='none'">`+
          `<button class="btn bp3 bsm" onclick="var d=this.nextElementSibling;d.style.display=d.style.display==='block'?'none':'block'" title="جلسة إرشادية">✏️ جلسة ▾</button>`+
          `<div class="drp" style="display:none;position:absolute;top:100%;right:0;background:#fff;border:1px solid var(--bd);border-radius:6px;z-index:100;min-width:120px;box-shadow:var(--sh);overflow:hidden;text-align:right">`+
            `<div style="padding:8px 12px;cursor:pointer;font-size:12px;border-bottom:1px solid var(--bd)" onclick="openSessionDialog('${sid}','${sn}','${cn}','discipline');this.parentNode.style.display='none'" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='#fff'">انضباط مدرسي</div>`+
            `<div style="padding:8px 12px;cursor:pointer;font-size:12px" onclick="openSessionDialog('${sid}','${sn}','${cn}','behavior');this.parentNode.style.display='none'" onmouseover="this.style.background='var(--bg)'" onmouseout="this.style.background='#fff'">سلوك</div>`+
          `</div>`+
        `</div> `+
        `<button class="btn bp4 bsm" onclick="openContractDialog('${sid}','${sn}','${cn}')" title="عقد سلوكي">📝</button> `+
        `<button class="btn bp2 bsm" onclick="openAlertDialog('${sid}','${sn}')" title="تنبيه/استدعاء">🔔</button> `+
        `<button class="btn bp5 bsm" onclick="delCounselorStudent('${sid}','${sn}')" title="حذف">🗑️</button>`;
    }
    
    var typeBadge = '';
    if(r.referral_type === 'هروب') typeBadge = ' <span style="background:#7f1d1d;color:#fca5a5;font-size:11px;padding:2px 7px;border-radius:10px;font-weight:bold">🏃 هروب</span>';
    else if(r.referral_type === 'غياب') typeBadge = ' <span style="background:#fef2f2;color:#dc2626;font-size:11px;padding:2px 7px;border-radius:10px;border:1px solid #fca5a5">غياب</span>';
    else if(r.referral_type === 'تأخر') typeBadge = ' <span style="background:#fff7ed;color:#ea580c;font-size:11px;padding:2px 7px;border-radius:10px;border:1px solid #fed7aa">تأخر</span>';
    else if(r.referral_type === 'تحويل معلم') typeBadge = ' <span style="background:#ede9fe;color:#7c3aed;font-size:11px;padding:2px 7px;border-radius:10px;border:1px solid #c4b5fd">تحويل معلم</span>';
    else if(r.referral_type) typeBadge = ' <span style="background:#f3f4f6;color:#374151;font-size:11px;padding:2px 7px;border-radius:10px">'+r.referral_type+'</span>';
    return '<tr style="'+bg+'">'+
      '<td>'+r.student_id+'</td>'+
      '<td><strong>'+r.student_name+'</strong>'+typeBadge+'</td>'+
      '<td>'+r.class_name+'</td>'+
      '<td><span class="badge br">'+r.absences+'</span></td>'+
      '<td><span class="badge bo">'+r.tardiness+'</span></td>'+
      '<td style="font-size:11px">'+(r.last_action||'—')+'</td>'+
      '<td style="white-space:nowrap">'+buttons+'</td>'+
    '</tr>';
  }).join('');
}
function filterCounselorList(){
  var q=(document.getElementById('co-search').value||'').toLowerCase().trim();
  if(!q){renderCounselorList(_coRows);return;}
  var filtered=_coRows.filter(function(r){
    return String(r.student_name).toLowerCase().indexOf(q)>=0 ||
           String(r.class_name).toLowerCase().indexOf(q)>=0 ||
           String(r.student_id).toLowerCase().indexOf(q)>=0;
  });
  renderCounselorList(filtered);
}
async function delCounselorStudent(sid,sname){
  if(!confirm('هل أنت متأكد من حذف الطالب «'+sname+'» من قائمة الموجّه؟\n(سيُحذف فقط من قائمة المحوّلين، ولن يُحذف من بيانات المدرسة)'))return;
  try{
    var r=await fetch('/web/api/counselor-delete-student/'+encodeURIComponent(sid),{method:'DELETE'});
    var d=await r.json();
    if(d.ok){ss('co-main-st','✅ تم حذف الطالب من قائمة الموجّه','ok');loadCounselorList();}
    else ss('co-main-st','❌ '+(d.msg||'فشل الحذف'),'er');
  }catch(e){ss('co-main-st','❌ خطأ في الاتصال','er');}
}

/* ── إضافة طالب يدوياً للموجّه ── */
async function loadClsForCoAdd(){
  var cid=document.getElementById('coa-cls').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('coa-stu').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
async function addCounselorManual(force){
  var clsSel=document.getElementById('coa-cls');
  var stuSel=document.getElementById('coa-stu');
  if(!stuSel.value){ss('coa-st','اختر الفصل والطالب','er');return;}
  var payload={
    student_id:stuSel.value,
    student_name:stuSel.options[stuSel.selectedIndex].text,
    class_name:clsSel.options[clsSel.selectedIndex]?clsSel.options[clsSel.selectedIndex].text:'',
    reason:document.getElementById('coa-reason').value,
    notes:document.getElementById('coa-notes').value,
    force:!!force
  };
  try{
    var r=await fetch('/web/api/counselor-add-manual',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)});
    var d=await r.json();
    if(d.ok){
      ss('coa-st','✅ تمت إضافة الطالب لقائمة الموجّه','ok');
      document.getElementById('coa-notes').value='';
      // تحديث القائمة الرئيسية
      loadCounselorList();
    } else if(d.duplicate){
      if(confirm(d.msg+'\n\nهل تريد إضافته مرة أخرى؟')){
        addCounselorManual(true);
      }else ss('coa-st','تم الإلغاء','ai');
    } else ss('coa-st','❌ '+(d.msg||'فشل'),'er');
  }catch(e){ss('coa-st','❌ خطأ في الاتصال','er');}
}

/* ── السجل الإرشادي الكامل (modal) ── */
async function viewCounselorHistory(sid,sname){
  showCoModal('السجل الإرشادي: '+sname,'<div class="loading">⏳ جارٍ التحميل...</div>');
  var d=await api('/web/api/counselor-history/'+encodeURIComponent(sid));
  if(!d||!d.ok){setCoModalBody('<div class="ab ae">❌ فشل التحميل</div>');return;}
  var html='<div class="it">'+
    '<button class="itb active" onclick="coModalTab(\'cm-ses\')">📝 الجلسات ('+(d.sessions||[]).length+')</button>'+
    '<button class="itb" onclick="coModalTab(\'cm-alr\')">🔔 التنبيهات ('+(d.alerts||[]).length+')</button>'+
    '<button class="itb" onclick="coModalTab(\'cm-ct\')">📄 العقود ('+(d.contracts||[]).length+')</button>'+
    '</div>';
  // الجلسات
  html+='<div id="cm-ses" class="ip active"><div class="tw"><table>'+
    '<thead><tr><th>التاريخ</th><th>السبب</th><th>الإجراء</th><th>الملاحظات</th></tr></thead><tbody>';
  if((d.sessions||[]).length){
    d.sessions.forEach(function(s){
      html+='<tr><td>'+s.date+'</td><td>'+(s.reason||'—')+'</td><td>'+(s.action_taken||'—')+'</td><td style="font-size:11px">'+(s.notes||'—')+'</td></tr>';
    });
  }else html+='<tr><td colspan="4" style="color:#9CA3AF">لا توجد جلسات</td></tr>';
  html+='</tbody></table></div></div>';
  // التنبيهات
  html+='<div id="cm-alr" class="ip"><div class="tw"><table>'+
    '<thead><tr><th>التاريخ</th><th>النوع</th><th>الطريقة</th><th>الحالة</th></tr></thead><tbody>';
  if((d.alerts||[]).length){
    d.alerts.forEach(function(a){
      html+='<tr><td>'+a.date+'</td><td>'+(a.type||'—')+'</td><td>'+(a.method||'—')+'</td><td>'+(a.status||'—')+'</td></tr>';
    });
  }else html+='<tr><td colspan="4" style="color:#9CA3AF">لا توجد تنبيهات</td></tr>';
  html+='</tbody></table></div></div>';
  // العقود
  html+='<div id="cm-ct" class="ip"><div class="tw"><table>'+
    '<thead><tr><th>التاريخ</th><th>المادة</th><th>من</th><th>إلى</th><th>الملاحظات</th></tr></thead><tbody>';
  if((d.contracts||[]).length){
    d.contracts.forEach(function(c){
      html+='<tr><td>'+c.date+'</td><td>'+(c.subject||'—')+'</td><td>'+(c.period_from||'—')+'</td><td>'+(c.period_to||'—')+'</td><td style="font-size:11px">'+(c.notes||'—')+'</td></tr>';
    });
  }else html+='<tr><td colspan="5" style="color:#9CA3AF">لا توجد عقود</td></tr>';
  html+='</tbody></table></div></div>';
  setCoModalBody(html);
}
function coModalTab(panelId){
  var modal=document.getElementById('co-modal');if(!modal)return;
  modal.querySelectorAll('.ip').forEach(function(p){p.classList.remove('active');});
  modal.querySelectorAll('.itb').forEach(function(b){b.classList.remove('active');});
  var p=document.getElementById(panelId);if(p)p.classList.add('active');
  if(typeof event!=='undefined'&&event.target&&event.target.classList)event.target.classList.add('active');
}

/* ── إضافة تنبيه/استدعاء ── */
function openAlertDialog(sid,sname){
  var t=prompt('نوع التنبيه (اتصال/استدعاء/رسالة):','اتصال هاتفي');
  if(!t)return;
  var st=prompt('الحالة (تم/في الانتظار/لم يرد):','تم');
  if(!st)return;
  fetch('/web/api/counselor-alert',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:sid,student_name:sname,type:t,method:t,status:st})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){ss('co-main-st','✅ تم تسجيل التنبيه','ok');loadCounselorList();}
      else ss('co-main-st','❌ '+(d.msg||'فشل'),'er');
    });
}

/* ──────────────────────────────────────────────────────────
   جلسة إرشادية كاملة — مرآة لـ _open_session_dialog المكتبية
   ────────────────────────────────────────────────────────── */
async function openSessionDialog(sid,sname,sclass, sessionType){
  sessionType = sessionType || 'discipline';
  // جلب البنود الافتراضية + معلومات المدير/الوكيل من الـ backend
  var defs=await api('/web/api/counselor-session-defaults');
  if(!defs||!defs.ok){alert('فشل جلب البيانات');return;}
  var goals=defs.goals||[],discs=defs.discussions||[],recs=defs.recommendations||[];

  if (sessionType === 'behavior') {
      goals = [
          "التعرف على المشكلة وأسبابها",
          "توضيح دور الطالب ومسؤولياته في المدرسة",
          "الالتزام بقوانين وأنظمة المدرسة",
          "اخد التعهد على الطالب بعدم تكرار المخالفة"
      ];
      discs = [
          "تمت مناقشة الطالب عن السلوك الذي قام به ( الهروب من المدرسـة وعدم حضور الحصص )",
          "تمت مناقشة الطالب عن أسباب هذا السلوك والدافع له"
      ];
      recs = [
          "توضيح سلبيات هذا السلوك ومخالفته للائحة السلوك وأنظمة المدرسة",
          "متابعة الطالب دراسياً ومتابعة حضوره للحصص",
          "تحويل الطالب (          ) للوكيل (          )"
      ];
  }
  var c1=(defs.counselor1_name||'').trim();
  var c2=(defs.counselor2_name||'').trim();
  var activeC=(defs.active_counselor||'1');
  var counselor=defs.counselor_name||'الموجّه الطلابي';
  var school=defs.school_name||'';
  var hasPrincipal=!!defs.principal_phone, hasDeputy=!!defs.deputy_phone;
  var today=new Date().toISOString().split('T')[0].replace(/-/g,'/');

  // بناء قائمة اختيار الموجّه (تظهر فقط إن وُجد موجّهان مسجّلان)
  var counselorPicker='';
  if(c1 && c2){
    counselorPicker='<div class="fg" style="grid-column:1/-1"><label class="fl">الموجّه الطلابي</label>'+
      '<select id="sd-counselor" onchange="var t=this.options[this.selectedIndex].text;document.getElementById(\'sd-counselor-lbl\').innerText=t;var l2=document.getElementById(\'sd-counselor-lbl2\');if(l2)l2.innerText=t;">'+
        '<option value="1"'+(activeC==='1'?' selected':'')+'>'+c1+'</option>'+
        '<option value="2"'+(activeC==='2'?' selected':'')+'>'+c2+'</option>'+
      '</select></div>';
  } else {
    // موجّه واحد فقط — نخزّنه في حقل مخفي
    counselorPicker='<input type="hidden" id="sd-counselor" value="'+(c2&&!c1?'2':'1')+'">';
  }

  // بناء HTML الفورم — مطابق لتصميم النافذة المكتبية
  var html='';
  // بيانات الطالب
  html+='<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:8px;padding:12px;margin-bottom:12px">'+
    '<div style="font-weight:bold;color:#7c3aed;margin-bottom:8px">📋 بيانات الطالب</div>'+
    '<div class="fg2">'+
      '<div class="fg"><label class="fl">اسم الطالب</label><input type="text" value="'+sname+'" disabled></div>'+
      '<div class="fg"><label class="fl">الفصل</label><input type="text" value="'+sclass+'" disabled></div>'+
      '<div class="fg"><label class="fl">عنوان الجلسة</label><input type="text" id="sd-title" value="'+(sessionType==='behavior' ? 'سلوك' : 'الانضباط المدرسي')+'"></div>'+
      '<div class="fg"><label class="fl">التاريخ</label><input type="text" id="sd-date" value="'+today+'"></div>'+
      counselorPicker+
    '</div>'+
    '<div style="margin-top:8px;font-size:11px;color:#7c3aed"><strong>الموجّه الطلابي:</strong> <span id="sd-counselor-lbl">'+counselor+'</span> &nbsp;|&nbsp; <strong>المدرسة:</strong> '+school+'</div>'+
  '</div>';

  // الأهداف
  html+='<div style="background:#fff;border:1px solid #ddd6fe;border-radius:8px;padding:12px;margin-bottom:10px">'+
    '<div style="font-weight:bold;color:#7c3aed;margin-bottom:8px">🎯 الهدف من الجلسة</div>';
  goals.forEach(function(g,i){
    html+='<label style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;cursor:pointer">'+
      '<input type="checkbox" class="sd-goal" value="'+g.replace(/"/g,'&quot;')+'" checked>'+
      '<span style="font-size:13px">'+(i+1)+'. '+g+'</span></label>';
  });
  html+='<div style="margin-top:6px"><input type="text" id="sd-goal-extra" placeholder="هدف إضافي (اختياري)" style="width:100%"></div>'+
  '</div>';

  // المداولات
  html+='<div style="background:#fff;border:1px solid #ddd6fe;border-radius:8px;padding:12px;margin-bottom:10px">'+
    '<div style="font-weight:bold;color:#7c3aed;margin-bottom:8px">🗣️ المداولات</div>';
  discs.forEach(function(d,i){
    html+='<label style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;cursor:pointer">'+
      '<input type="checkbox" class="sd-disc" value="'+d.replace(/"/g,'&quot;')+'" checked>'+
      '<span style="font-size:13px">'+(i+1)+'. '+d+'</span></label>';
  });
  html+='<div style="margin-top:6px"><input type="text" id="sd-disc-extra" placeholder="مداولة إضافية (اختياري)" style="width:100%"></div>'+
  '</div>';

  // التوصيات
  html+='<div style="background:#fff;border:1px solid #ddd6fe;border-radius:8px;padding:12px;margin-bottom:10px">'+
    '<div style="font-weight:bold;color:#7c3aed;margin-bottom:8px">✅ التوصيات</div>';
  recs.forEach(function(r,i){
    html+='<label style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;cursor:pointer">'+
      '<input type="checkbox" class="sd-rec" value="'+r.replace(/"/g,'&quot;')+'" checked>'+
      '<span style="font-size:12px">'+(i+1)+'. '+r+'</span></label>';
  });
  html+='<div style="margin-top:6px"><input type="text" id="sd-rec-extra" placeholder="توصية إضافية (اختياري)" style="width:100%"></div>'+
  '</div>';

  // ملاحظات
  html+='<div style="background:#fff;border:1px solid #ddd6fe;border-radius:8px;padding:12px;margin-bottom:12px">'+
    '<div style="font-weight:bold;color:#7c3aed;margin-bottom:6px">📝 ملاحظات إضافية</div>'+
    '<textarea id="sd-notes" rows="3" style="width:100%" placeholder="ملاحظات الجلسة..."></textarea>'+
  '</div>';

  // التواقيع
  html+='<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;margin-bottom:12px;display:flex;justify-content:space-between;font-size:12px">'+
    '<div><strong>قائد المدرسة</strong></div>'+
    '<div style="color:#7c3aed"><strong>الموجّه الطلابي:</strong> <span id="sd-counselor-lbl2">'+counselor+'</span></div>'+
  '</div>';

  // أزرار الإجراءات
  html+='<div id="sd-st" style="margin-bottom:8px"></div>'+
    '<div class="bg-btn" style="flex-wrap:wrap;gap:6px">'+
    '<button class="btn bp1" onclick="submitSession(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'save\')">💾 حفظ</button>'+
    (hasPrincipal?'<button class="btn bp3" onclick="submitSession(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'send_principal\')">📨 إرسال للمدير</button>':'')+
    (hasDeputy?'<button class="btn bp3" onclick="submitSession(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'send_deputy\')">📨 إرسال للوكيل</button>':'')+
    ((hasPrincipal&&hasDeputy)?'<button class="btn bp4" onclick="submitSession(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'send_both\')">📨📨 إرسال للاثنين</button>':'')+
    '<button class="btn bp2" onclick="printSession(\''+sid+'\',\''+sname+'\',\''+sclass+'\')">🖨️ طباعة PDF</button>'+
    '</div>';

  showCoModal('📝 جلسة إرشاد فردي — '+sname+(sessionType==='behavior'?' (سلوك)':' (انضباط)'),html,'#7c3aed','#5b21b6');
}

function _collectSessionData(sid,sname,sclass){
  var goals=[],discs=[],recs=[];
  document.querySelectorAll('.sd-goal:checked').forEach(function(c){goals.push(c.value);});
  document.querySelectorAll('.sd-disc:checked').forEach(function(c){discs.push(c.value);});
  document.querySelectorAll('.sd-rec:checked' ).forEach(function(c){recs.push(c.value);});
  var ge=(document.getElementById('sd-goal-extra').value||'').trim();if(ge)goals.push(ge);
  var de=(document.getElementById('sd-disc-extra').value||'').trim();if(de)discs.push(de);
  var re=(document.getElementById('sd-rec-extra').value ||'').trim();if(re)recs.push(re);
  var cEl=document.getElementById('sd-counselor');
  var cChoice=cEl?cEl.value:'1';
  var cName='';
  if(cEl && cEl.tagName==='SELECT'){
    cName=cEl.options[cEl.selectedIndex].text;
  }
  return {
    student_id:sid,student_name:sname,class_name:sclass,
    title:document.getElementById('sd-title').value,
    date:document.getElementById('sd-date').value,
    goals:goals,discussions:discs,recommendations:recs,
    notes:document.getElementById('sd-notes').value,
    counselor_choice:cChoice,
    counselor_name:cName
  };
}

async function submitSession(sid,sname,sclass,action){
  var payload=_collectSessionData(sid,sname,sclass);
  payload.action=action;
  ss('sd-st','⏳ جارٍ المعالجة...','ai');
  try{
    var r=await fetch('/web/api/counselor-session-full',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)});
    var d=await r.json();
    if(d.ok){
      var msg='✅ تم الحفظ';
      if(action!=='save') msg+=' وأُرسلت لـ '+d.sent+'/'+d.total;
      ss('sd-st',msg,'ok');
      if(action==='save'){
        setTimeout(function(){document.getElementById('co-modal').remove();},900);
      }
      loadCounselorList();
    } else {
      var errDetail=d.msg||(d.results&&d.results.length?d.results[0].msg:'')||'فشل الإرسال';
      ss('sd-st','❌ '+errDetail,'er');
    }
  }catch(e){ss('sd-st','❌ خطأ في الاتصال: '+(e.message||e),'er');}
}

function printSession(sid,sname,sclass){
  var payload=_collectSessionData(sid,sname,sclass);
  // افتح النافذة فوراً بشكل متزامن لتجاوز حاجب النوافذ المنبثقة
  var w=window.open('','_blank');
  if(w){
    try{
      w.document.write('<!doctype html><html dir="rtl"><head><meta charset="utf-8"><title>جارٍ تحضير PDF...</title></head><body style="font-family:Tahoma,Arial;text-align:center;padding:40px;color:#555">⏳ جارٍ إنشاء ملف PDF...</body></html>');
    }catch(e){}
  }
  fetch('/web/api/counselor-session-pdf',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)})
    .then(function(r){
      if(!r.ok){
        if(w)try{w.close();}catch(e){}
        return r.text().then(function(t){throw new Error(t||'فشل إنشاء PDF');});
      }
      return r.blob();
    })
    .then(function(blob){
      if(!blob)return;
      var url=URL.createObjectURL(blob);
      if(w && !w.closed){
        // وجّه النافذة المفتوحة مسبقاً إلى ملف PDF
        w.location.href=url;
        setTimeout(function(){try{w.focus();w.print();}catch(e){}},900);
      } else {
        // النوافذ المنبثقة محجوبة — نزّل الملف بدلاً من ذلك
        var a=document.createElement('a');
        a.href=url;
        a.download='جلسة_ارشادية_'+(payload.student_name||'طالب')+'.pdf';
        document.body.appendChild(a);a.click();
        setTimeout(function(){document.body.removeChild(a);URL.revokeObjectURL(url);},1500);
      }
    })
    .catch(function(err){
      if(w)try{w.close();}catch(e){}
      alert('خطأ في إنشاء PDF: '+(err&&err.message?err.message:''));
    });
}

/* ──────────────────────────────────────────────────────────
   نموذج إجراءات الموجّه لتحويلات المعلمين
   ────────────────────────────────────────────────────────── */
async function openCounselorReferralForm(refId){
  var d=await api('/web/api/referral/'+refId);
  if(!d||!d.ok||!d.referral){alert('❌ فشل تحميل بيانات التحويل');return;}
  var ref=d.referral;
  var defs=await api('/web/api/counselor-session-defaults');
  var today=new Date().toISOString().split('T')[0];
  var cName=(defs&&defs.counselor_name)||'الموجّه الطلابي';
  var html='<div style="background:#f3e5f5;padding:12px;border-radius:8px;margin-bottom:12px;font-size:13px">'+
    '<div style="margin-bottom:4px"><strong>الطالب:</strong> '+ref.student_name+'</div>'+
    '<div style="margin-bottom:4px"><strong>الفصل:</strong> '+(ref.class_name||'—')+'</div>'+
    '<div style="margin-bottom:4px"><strong>المخالفة:</strong> '+(ref.violation_type||'')+' — '+(ref.violation||'')+'</div>'+
    '<div><strong>المعلم:</strong> '+(ref.teacher_name||'—')+'</div>'+
    '</div>'+
    '<div class="fg2">'+
      '<div class="fg"><label class="fl">تاريخ المقابلة</label><input type="date" id="crf-date" value="'+(ref.counselor_meeting_date||today)+'" class="fc"></div>'+
      '<div class="fg"><label class="fl">الحصة</label><select id="crf-period" class="fc">'+[1,2,3,4,5,6,7,8].map(function(i){return '<option value="'+i+'"'+(ref.counselor_meeting_period==i?' selected':'')+'>'+i+'</option>'}).join('')+'</select></div>'+
    '</div>'+
    '<div class="fg"><label class="fl">الإجراء 1 (التوجيه والإرشاد)</label><input type="text" id="crf-a1" class="fc" value="'+(ref.counselor_action1||'')+'"></div>'+
    '<div class="fg"><label class="fl">الإجراء 2 (التواصل مع ولي الأمر)</label><input type="text" id="crf-a2" class="fc" value="'+(ref.counselor_action2||'')+'"></div>'+
    '<div class="fg"><label class="fl">الإجراء 3 (الإحالة لجهة أخرى)</label><input type="text" id="crf-a3" class="fc" value="'+(ref.counselor_action3||'')+'"></div>'+
    '<div class="fg"><label class="fl">الإجراء 4 (أخرى)</label><input type="text" id="crf-a4" class="fc" value="'+(ref.counselor_action4||'')+'"></div>'+
    '<div class="fg2">'+
      '<div class="fg"><label class="fl">اسم الموجّه</label><input type="text" id="crf-name" class="fc" value="'+(ref.counselor_name||cName)+'"></div>'+
      '<div class="fg"><label class="fl">تاريخ الإعادة للوكيل</label><input type="date" id="crf-back" class="fc" value="'+(ref.counselor_referred_back_date||'')+'"></div>'+
    '</div>'+
    '<div id="crf-st" style="margin-bottom:8px"></div>'+
    '<div class="bg-btn" style="margin-top:8px">'+
      '<button class="btn bp1" onclick="submitCounselorReferralForm('+refId+',false)">💾 حفظ الإجراءات</button>'+
      '<button class="btn bp3" onclick="submitCounselorReferralForm('+refId+',true)">✅ حفظ وإغلاق التحويل</button>'+
    '</div>';
  showCoModal('📋 إجراءات الموجّه الطلابي', html, '#6a1b9a', '#4a148c');
}

async function submitCounselorReferralForm(refId, closeIt){
  var payload={
    counselor_meeting_date:document.getElementById('crf-date').value.trim(),
    counselor_meeting_period:document.getElementById('crf-period').value.trim(),
    counselor_action1:document.getElementById('crf-a1').value.trim(),
    counselor_action2:document.getElementById('crf-a2').value.trim(),
    counselor_action3:document.getElementById('crf-a3').value.trim(),
    counselor_action4:document.getElementById('crf-a4').value.trim(),
    counselor_name:document.getElementById('crf-name').value.trim(),
    counselor_referred_back_date:document.getElementById('crf-back').value.trim(),
    close_it: closeIt
  };
  if(!payload.counselor_name){ss('crf-st','أدخل اسم الموجّه','er');return;}
  ss('crf-st','⏳ جارٍ الحفظ...','ai');
  try{
    var r=await fetch('/web/api/update-counselor-referral/'+refId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    var d=await r.json();
    if(d.ok){
      ss('crf-st','✅ تم الحفظ','ok');
      if(closeIt) setTimeout(function(){var m=document.getElementById('co-modal');if(m)m.remove();},800);
      loadCounselorList();
    }else ss('crf-st','❌ '+(d.msg||'فشل'),'er');
  }catch(e){ss('crf-st','❌ خطأ اتصال','er');}
}

/* ──────────────────────────────────────────────────────────
   عقد سلوكي كامل — مرآة لـ _open_behavioral_contract_dialog
   ────────────────────────────────────────────────────────── */
async function openContractDialog(sid,sname,sclass){
  var defs=await api('/web/api/counselor-session-defaults');
  var counselor=(defs&&defs.counselor_name)||'الموجّه الطلابي';
  var c1=(defs&&defs.counselor1_name||'').trim();
  var c2=(defs&&defs.counselor2_name||'').trim();
  var activeC=(defs&&defs.active_counselor)||'1';
  var school=(defs&&defs.school_name)||'';
  var hasPrincipal=defs&&defs.principal_phone, hasDeputy=defs&&defs.deputy_phone;
  var today=new Date().toISOString().split('T')[0];

  var counselorPicker='';
  if(c1 && c2){
    counselorPicker='<div class="fg" style="grid-column:1/-1"><label class="fl">الموجّه الطلابي</label>'+
      '<select id="cd-counselor" onchange="var t=this.options[this.selectedIndex].text;document.getElementById(\'cd-counselor-lbl\').innerText=t;">'+
        '<option value="1"'+(activeC==='1'?' selected':'')+'>'+c1+'</option>'+
        '<option value="2"'+(activeC==='2'?' selected':'')+'>'+c2+'</option>'+
      '</select></div>';
  } else {
    counselorPicker='<input type="hidden" id="cd-counselor" value="'+(c2&&!c1?'2':'1')+'">';
  }

  var html='';
  // بيانات الطالب
  html+='<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin-bottom:12px">'+
    '<div style="font-weight:bold;color:#92400e;margin-bottom:8px">📋 بيانات الطالب</div>'+
    '<div class="fg2">'+
      '<div class="fg"><label class="fl">اسم الطالب</label><input type="text" value="'+sname+'" disabled></div>'+
      '<div class="fg"><label class="fl">الفصل</label><input type="text" value="'+sclass+'" disabled></div>'+
      '<div class="fg"><label class="fl">موضوع العقد</label><input type="text" id="cd-subject" value="الانضباط السلوكي"></div>'+
      '<div class="fg"><label class="fl">تاريخ العقد</label><input type="date" id="cd-date" value="'+today+'"></div>'+
      counselorPicker+
    '</div>'+
    '<div style="margin-top:8px;font-size:11px;color:#92400e"><strong>المدرسة:</strong> '+school+' &nbsp;|&nbsp; <strong>الموجّه:</strong> <span id="cd-counselor-lbl">'+counselor+'</span></div>'+
  '</div>';

  // الفترة الزمنية
  html+='<div style="background:#fff;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin-bottom:10px">'+
    '<div style="font-weight:bold;color:#92400e;margin-bottom:8px">📅 الفترة الزمنية للعقد (هجري)</div>'+
    '<div class="fg2">'+
      '<div class="fg"><label class="fl">من</label><input type="text" id="cd-from" placeholder="مثال: 01/09/1446"></div>'+
      '<div class="fg"><label class="fl">إلى</label><input type="text" id="cd-to" placeholder="مثال: 30/09/1446"></div>'+
    '</div>'+
  '</div>';

  // ملاحظات
  html+='<div style="background:#fff;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin-bottom:10px">'+
    '<div style="font-weight:bold;color:#92400e;margin-bottom:6px">📝 ملاحظات إضافية</div>'+
    '<textarea id="cd-notes" rows="3" style="width:100%" placeholder="ملاحظات اختيارية..."></textarea>'+
  '</div>';

  // معاينة بنود العقد (نفس البنود الثابتة في التطبيق المكتبي)
  html+='<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin-bottom:12px">'+
    '<div style="font-weight:bold;color:#92400e;margin-bottom:8px">📋 بنود العقد (تُطبع تلقائياً في PDF)</div>'+
    '<div style="font-size:12px;line-height:1.8;color:#451a03">'+
      '<strong>المسؤوليات على الطالب:</strong><br>'+
      '&nbsp;&nbsp;1 - الحضور للمدرسة بانتظام.<br>'+
      '&nbsp;&nbsp;2 - القيام بالواجبات المنزلية المُكلَّف بها.<br>'+
      '&nbsp;&nbsp;3 - عدم الاعتداء على أي طالب بالمدرسة.<br>'+
      '&nbsp;&nbsp;4 - عدم القيام بأي مخالفات داخل المدرسة.<br><br>'+
      '<strong>المزايا والتدعيمات:</strong><br>'+
      '&nbsp;&nbsp;1 - سوف يضاف له درجات في السلوك.<br>'+
      '&nbsp;&nbsp;2 - سوف يذكر اسمه في الإذاعة المدرسية كطالب متميز.<br>'+
      '&nbsp;&nbsp;3 - سوف يسلم شهادة تميز سلوكي.<br>'+
      '&nbsp;&nbsp;4 - يُكرَّم في نهاية العام الدراسي.<br>'+
      '&nbsp;&nbsp;5 - يتم مساعدته في المواد الدراسية من قبل المعلمين.<br><br>'+
      '<strong>مكافآت إضافية:</strong> عند الاستمرار في هذا التميز السلوكي حتى نهاية العام.<br>'+
      '<strong>عقوبات:</strong> في حالة عدم الالتزام تُلغى المزايا ويُتخذ الإجراء المناسب.'+
    '</div>'+
  '</div>';

  // الأزرار
  html+='<div id="cd-st" style="margin-bottom:8px"></div>'+
    '<div class="bg-btn" style="flex-wrap:wrap;gap:6px">'+
    '<button class="btn bp1" onclick="submitContract(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'save\')">💾 حفظ</button>'+
    (hasPrincipal?'<button class="btn bp3" onclick="submitContract(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'send_principal\')">📨 إرسال للمدير</button>':'')+
    (hasDeputy?'<button class="btn bp3" onclick="submitContract(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'send_deputy\')">📨 إرسال للوكيل</button>':'')+
    ((hasPrincipal&&hasDeputy)?'<button class="btn bp4" onclick="submitContract(\''+sid+'\',\''+sname+'\',\''+sclass+'\',\'send_both\')">📨📨 إرسال للاثنين</button>':'')+
    '<button class="btn bp2" onclick="printContract(\''+sid+'\',\''+sname+'\',\''+sclass+'\')">🖨️ طباعة PDF</button>'+
    '</div>';

  showCoModal('📋 عقد سلوكي — '+sname,html,'#d97706','#92400e');
}

function _collectContractData(sid,sname,sclass){
  var cEl=document.getElementById('cd-counselor');
  var cChoice=cEl?cEl.value:'1';
  var cName='';
  if(cEl && cEl.tagName==='SELECT'){
    cName=cEl.options[cEl.selectedIndex].text;
  }
  return {
    student_id:sid,student_name:sname,class_name:sclass,
    subject:document.getElementById('cd-subject').value,
    date:document.getElementById('cd-date').value,
    period_from:document.getElementById('cd-from').value,
    period_to:document.getElementById('cd-to').value,
    notes:document.getElementById('cd-notes').value,
    counselor_choice:cChoice,
    counselor_name:cName
  };
}

async function submitContract(sid,sname,sclass,action){
  var payload=_collectContractData(sid,sname,sclass);
  payload.action=action;
  ss('cd-st','⏳ جارٍ المعالجة...','ai');
  try{
    var r=await fetch('/web/api/counselor-contract-full',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)});
    var d=await r.json();
    if(d.ok){
      var msg='✅ تم الحفظ';
      if(action!=='save') msg+=' وأُرسل لـ '+d.sent+'/'+d.total;
      ss('cd-st',msg,'ok');
      if(action==='save'){
        setTimeout(function(){document.getElementById('co-modal').remove();},900);
      }
    } else {
      ss('cd-st','❌ '+(d.msg||'فشل'),'er');
    }
  }catch(e){ss('cd-st','❌ خطأ في الاتصال','er');}
}

function printContract(sid,sname,sclass){
  var payload=_collectContractData(sid,sname,sclass);
  var w=window.open('','_blank');
  if(w){
    try{
      w.document.write('<!doctype html><html dir="rtl"><head><meta charset="utf-8"><title>جارٍ تحضير PDF...</title></head><body style="font-family:Tahoma,Arial;text-align:center;padding:40px;color:#555">⏳ جارٍ إنشاء ملف PDF...</body></html>');
    }catch(e){}
  }
  fetch('/web/api/counselor-contract-pdf',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)})
    .then(function(r){
      if(!r.ok){
        if(w)try{w.close();}catch(e){}
        return r.text().then(function(t){throw new Error(t||'فشل إنشاء PDF');});
      }
      return r.blob();
    })
    .then(function(blob){
      if(!blob)return;
      var url=URL.createObjectURL(blob);
      if(w && !w.closed){
        w.location.href=url;
        setTimeout(function(){try{w.focus();w.print();}catch(e){}},900);
      } else {
        var a=document.createElement('a');
        a.href=url;
        a.download='عقد_سلوكي_'+(payload.student_name||'طالب')+'.pdf';
        document.body.appendChild(a);a.click();
        setTimeout(function(){document.body.removeChild(a);URL.revokeObjectURL(url);},1500);
      }
    })
    .catch(function(err){
      if(w)try{w.close();}catch(e){}
      alert('خطأ في إنشاء PDF: '+(err&&err.message?err.message:''));
    });
}

/* ── Modal بسيط متعدّد الاستخدام ── */
function showCoModal(title,bodyHtml,hdrColor,hdrColorDark){
  var existing=document.getElementById('co-modal');
  if(existing)existing.remove();
  hdrColor=hdrColor||'#7c3aed';
  hdrColorDark=hdrColorDark||'#5b21b6';
  var modal=document.createElement('div');
  modal.id='co-modal';
  modal.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML='<div style="background:#fff;border-radius:12px;max-width:900px;width:100%;max-height:92vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.3)">'+
    '<div style="background:linear-gradient(135deg,'+hdrColor+','+hdrColorDark+');color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center">'+
      '<strong>'+title+'</strong>'+
      '<button onclick="document.getElementById(\'co-modal\').remove()" style="background:rgba(255,255,255,.2);color:#fff;border:none;border-radius:50%;width:32px;height:32px;cursor:pointer;font-size:18px;font-weight:bold">×</button>'+
    '</div>'+
    '<div id="co-modal-body" style="padding:20px;overflow-y:auto;flex:1">'+bodyHtml+'</div>'+
    '</div>';
  document.body.appendChild(modal);
  modal.addEventListener('click',function(e){if(e.target===modal)modal.remove();});
}
function setCoModalBody(html){
  var body=document.getElementById('co-modal-body');
  if(body)body.innerHTML=html;
}

/* ── TEACHER REFERRALS (تحويل طالب) ── */
async function loadRefStudents(){
  var d=await api('/web/api/students');if(!d||!d.ok)return;
  var all=[];d.classes.forEach(function(c){c.students.forEach(function(s){all.push(Object.assign({},s,{class_name:c.name,class_id:c.id}));});});
  window._refStudents=all;
  document.getElementById('rt-stu').innerHTML='<option value="">اختر طالباً</option>'+
    all.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
function rtAutoClass(){
  var id=document.getElementById('rt-stu').value;
  var s=(window._refStudents||[]).find(function(x){return x.id==id;});
  if(s)document.getElementById('rt-cls').value=s.class_name;
  else document.getElementById('rt-cls').value='';
}
async function submitTeacherReferral(){
  var stuSel=document.getElementById('rt-stu');
  if(!stuSel.value){ss('rt-st','اختر طالباً','er');return;}
  var st = (window._refStudents||[]).find(function(x){return x.id==stuSel.value;});
  var payload={
    student_id:stuSel.value,
    student_name:stuSel.options[stuSel.selectedIndex].text,
    class_id:st?st.class_id:'',
    class_name:document.getElementById('rt-cls').value,
    subject:document.getElementById('rt-subj').value,
    period:document.getElementById('rt-per').value,
    session_time:document.getElementById('rt-time').value||'',
    violation_type:document.getElementById('rt-vtype').value,
    violation:document.getElementById('rt-violation').value,
    problem_causes:document.getElementById('rt-causes').value,
    repeat_count:document.getElementById('rt-repeat').value,
    teacher_action1:document.getElementById('rt-act1').value,
    teacher_action2:document.getElementById('rt-act2').value
  };
  ss('rt-st','⏳ جارٍ الإرسال...','ai');
  var r=await fetch('/web/api/create-referral',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  var d=await r.json();
  if(d.ok){
    ss('rt-st','✅ تم إرسال التحويل لمدير/وكيل شؤون الطلاب','ok');
    document.getElementById('rt-subj').value='';document.getElementById('rt-violation').value='';
    document.getElementById('rt-causes').value='';document.getElementById('rt-act1').value='';
    document.getElementById('rt-act2').value='';
  }else ss('rt-st','❌ '+(d.msg||'خطأ'),'er');
}
async function loadRefHistory(){
  var d=await api('/web/api/referral-history');if(!d||!d.ok)return;
  var stLabel={pending:'⏳ بانتظار الوكيل',with_deputy:'📋 مع الوكيل',with_counselor:'👨‍🏫 مع الموجه',resolved:'✅ تم الحل'};
  document.getElementById('rt-hist-tbl').innerHTML=(d.referrals||[]).map(function(r){
    return `<tr><td>${r.id}</td><td>${r.ref_date}</td><td>${r.student_name}</td><td>${r.class_name}</td><td><span class="badge ${r.status==='resolved'?'bg':'bb'}">${(stLabel[r.status]||r.status)}</span></td><td><button class="btn bp1 bsm" onclick="openTeacherRefDetails(${r.id})">🔍 التفاصيل</button></td></tr>`;
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا يوجد</td></tr>';
}

async function openTeacherRefDetails(id){
  var d=await api('/web/api/referral/'+id);
  if(!d||!d.ok){alert('❌ فشل تحميل تفاصيل التحويل');return;}
  var r=d.referral;
  var html='<div style="line-height:1.8;padding:12px;font-size:13px;color:#333;">';
  html+='<div style="margin-bottom:12px"><strong>نوع المخالفة:</strong> '+r.violation_type+' — '+r.violation+'</div>';
  if(r.problem_causes) html+='<div style="margin-bottom:12px"><strong>الأسباب:</strong> '+r.problem_causes+'</div>';
  
  // Teacher Actions
  if(r.teacher_action1 || r.teacher_action2){
    var ta='<ul style="margin:4px 0;padding-inline-start:20px">';
    if(r.teacher_action1) ta+='<li>'+r.teacher_action1+'</li>';
    if(r.teacher_action2) ta+='<li>'+r.teacher_action2+'</li>';
    ta+='</ul>';
    html+='<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:8px;margin-bottom:10px;color:#1e3a8a"><strong style="display:block;margin-bottom:4px">📝 إجراءات المعلم:</strong>'+ta+'</div>';
  }
  
  // Deputy Actions
  if(r.deputy_action1 || r.deputy_action2){
    var da='<ul style="margin:4px 0;padding-inline-start:20px">';
    if(r.deputy_action1) da+='<li>'+r.deputy_action1+'</li>';
    if(r.deputy_action2) da+='<li>'+r.deputy_action2+'</li>';
    if(r.refer_to_counselor) da+='<li><span style="background:#fef08a;padding:2px 6px;border-radius:4px;color:#a16207;font-size:11px">تم التحويل للموجه</span></li>';
    da+='</ul>';
    var dd=r.deputy_meeting_date?' '+r.deputy_meeting_date:'';
    html+='<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:8px;margin-bottom:10px;color:#92400e"><strong style="display:block;margin-bottom:4px">📋 إجراء الوكيل'+dd+':</strong>'+da+'</div>';
  }
  
  // Counselor Actions
  if(r.counselor_action1 || r.counselor_action2 || r.counselor_action3 || r.counselor_action4){
    var ca='<ul style="margin:4px 0;padding-inline-start:20px">';
    if(r.counselor_action1) ca+='<li>'+r.counselor_action1+'</li>';
    if(r.counselor_action2) ca+='<li>'+r.counselor_action2+'</li>';
    if(r.counselor_action3) ca+='<li>'+r.counselor_action3+'</li>';
    if(r.counselor_action4) ca+='<li>'+r.counselor_action4+'</li>';
    ca+='</ul>';
    var cd=r.counselor_meeting_date?' '+r.counselor_meeting_date:'';
    html+='<div style="background:#f3e5f5;border:1px solid #e1bee7;border-radius:6px;padding:8px;margin-bottom:10px;color:#4a148c"><strong style="display:block;margin-bottom:4px">🧠 إجراء الموجه'+cd+':</strong>'+ca+'</div>';
  }
  html+='</div>';
  showCoModal('تفاصيل التحويل رقم '+id, html, '#1565C0', '#0D47A1');
}

/* ── DEPUTY REFERRALS (استلام تحويلات) ── */
async function loadDeputyReferrals(){
  var sf=document.getElementById('rd-filter').value;
  var url='/web/api/all-referrals'+(sf!=='all'?'?status='+sf:'');
  var d=await api(url);if(!d||!d.ok)return;
  var stLabel={pending:'⏳ بانتظار الوكيل',with_deputy:'📋 مع الوكيل',with_counselor:'👨‍🏫 مع الموجه',resolved:'✅ تم الحل'};
  document.getElementById('rd-tbl').innerHTML=(d.referrals||[]).map(function(r){
    return '<tr><td>'+r.id+'</td><td>'+r.ref_date+'</td><td>'+r.student_name+'</td><td>'+r.class_name+'</td><td>'+r.teacher_name+'</td>'+
      '<td><span class="badge '+(r.status==='resolved'?'bg':'bb')+'">'+(stLabel[r.status]||r.status)+'</span></td>'+
      '<td><button class="btn bp1 bsm" onclick="openDeputyReferralModal('+r.id+')">التفاصيل</button></td></tr>';
  }).join('')||'<tr><td colspan="7" style="color:#9CA3AF">لا يوجد</td></tr>';
}
window._curRef=0;
async function openDeputyReferralModal(id){
  var d=await api('/web/api/referral/'+id);if(!d||!d.ok){alert('خطأ');return;}
  window._curRef=id;var r=d.referral;
  document.getElementById('rd-m-id').innerText='#'+r.id;
  document.getElementById('rd-m-details').innerHTML='<strong>الطالب:</strong> '+r.student_name+' &nbsp;|&nbsp; <strong>المعلم:</strong> '+r.teacher_name+'<br>'+
    '<strong>المخالفة:</strong> '+r.violation_type+' - '+r.violation+'<br><strong>الأسباب:</strong> '+r.problem_causes+'<br><strong>إجراءات المعلم:</strong> '+(r.teacher_action1||'')+' / '+(r.teacher_action2||'');
  document.getElementById('rd-m-date').value=(r.deputy_meeting_date||new Date().toISOString().split('T')[0]);
  document.getElementById('rd-m-act1').value=(r.deputy_action1||'التوجيه والإرشاد');
  document.getElementById('rd-m-act2').value=(r.deputy_action2||'');
  document.getElementById('rd-modal').style.display='block';
}
async function saveDeputyAction(referToCounselor){
  var payload={
    deputy_meeting_date:document.getElementById('rd-m-date').value,
    deputy_action1:document.getElementById('rd-m-act1').value,
    deputy_action2:document.getElementById('rd-m-act2').value,
    refer_to_counselor:referToCounselor
  };
  var r=await fetch('/web/api/update-referral/'+window._curRef,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  var d=await r.json();if(d.ok){ss('rd-m-st','✅ تم الحفظ','ok');loadDeputyReferrals();}else ss('rd-m-st','❌ خطأ','er');
}
async function closeDeputyReferral(){
  if(!confirm('إغلاق هذا التحويل كـ (تم الحل)؟'))return;
  var r=await fetch('/web/api/close-referral/'+window._curRef,{method:'POST'});
  var d=await r.json();if(d.ok){document.getElementById('rd-modal').style.display='none';loadDeputyReferrals();alert('تم إغلاق التحويل');}
}

/* ── PARENT VISITS (زيارات أولياء الأمور) ── */
var _pvRows=[], _pvStudMap={};
var _pvTimes=["07:00","07:15","07:30","07:45","08:00","08:15","08:30","08:45",
  "09:00","09:15","09:30","09:45","10:00","10:15","10:30","10:45",
  "11:00","11:15","11:30","11:45","12:00","12:15","12:30","12:45",
  "13:00","13:15","13:30","13:45","14:00","14:30","15:00"];

function pvInit(){
  var d=new Date(), pad=function(n){return String(n).padStart(2,'0');};
  var today=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
  var m1=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-01';
  document.getElementById('pv-from').value=m1;
  document.getElementById('pv-to').value=today;
  pvLoad();
}

async function pvLoad(){
  var from=document.getElementById('pv-from').value;
  var to=document.getElementById('pv-to').value;
  var d=await api('/web/api/parent-visits?from='+from+'&to='+to);
  if(!d||!d.ok)return;
  _pvRows=d.visits||[];
  pvRender(_pvRows);
  pvStats(_pvRows);
}

function pvStats(rows){
  var wrap=document.getElementById('pv-stats');
  var total=rows.length;
  var reasons={};
  rows.forEach(function(r){reasons[r.visit_reason]=(reasons[r.visit_reason]||0)+1;});
  var topReason=Object.entries(reasons).sort(function(a,b){return b[1]-a[1];});
  var html='<div class="sc" style="background:#EFF6FF;border-color:#BFDBFE">'
    +'<div class="v" style="color:#1d4ed8">'+total+'</div><div class="l">إجمالي الزيارات</div></div>';
  if(topReason.length>0)
    html+='<div class="sc" style="background:#F0FDF4;border-color:#BBF7D0">'
      +'<div class="v" style="color:#166534;font-size:14px">'+topReason[0][0]+'</div>'
      +'<div class="l">أكثر أسباب الزيارة</div></div>';
  var rcvMap={};
  rows.forEach(function(r){rcvMap[r.received_by]=(rcvMap[r.received_by]||0)+1;});
  var topRcv=Object.entries(rcvMap).sort(function(a,b){return b[1]-a[1];});
  if(topRcv.length>0)
    html+='<div class="sc" style="background:#FFF7ED;border-color:#FED7AA">'
      +'<div class="v" style="color:#c2410c;font-size:14px">'+topRcv[0][0]+'</div>'
      +'<div class="l">أكثر الجهات استقبالاً</div></div>';
  wrap.innerHTML=html;
}

function pvFilter(){
  var q=document.getElementById('pv-search').value.toLowerCase().trim();
  var filtered=_pvRows.filter(function(r){
    return !q||Object.values(r).some(function(v){return String(v).toLowerCase().includes(q);});
  });
  pvRender(filtered);
}

function pvRender(rows){
  var tbody=document.getElementById('pv-tbl');
  var empty=document.getElementById('pv-empty');
  if(!rows.length){tbody.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  tbody.innerHTML=rows.map(function(r){
    return '<tr>'
      +'<td>'+r.id+'</td>'
      +'<td>'+r.date+'</td>'
      +'<td>'+r.visit_time+'</td>'
      +'<td>'+r.student_name+'</td>'
      +'<td>'+r.class_name+'</td>'
      +'<td>'+(r.guardian_name||'-')+'</td>'
      +'<td><span class="badge bb">'+r.visit_reason+'</span></td>'
      +'<td>'+r.received_by+'</td>'
      +'<td>'+r.visit_result+'</td>'
      +'<td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+(r.notes||'')+'">'+(r.notes||'-')+'</td>'
      +'<td><button class="btn bsm" style="background:#fee2e2;color:#991b1b" onclick="pvDelete('+r.id+')">'
      +'<i class="fas fa-trash"></i></button></td>'
      +'</tr>';
  }).join('');
}

function pvOpenAdd(){
  var modal=document.getElementById('pv-modal');
  modal.style.display='flex';
  /* التاريخ والوقت */
  var d=new Date(),pad=function(n){return String(n).padStart(2,'0');};
  document.getElementById('pv-add-date').value=
    d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
  var timeEl=document.getElementById('pv-add-time');
  timeEl.innerHTML=_pvTimes.map(function(t){return '<option>'+t+'</option>';}).join('');
  var nowMin=d.getHours()*60+d.getMinutes();
  var closest=_pvTimes.reduce(function(a,b){
    var ta=parseInt(a.split(':')[0])*60+parseInt(a.split(':')[1]);
    var tb=parseInt(b.split(':')[0])*60+parseInt(b.split(':')[1]);
    return Math.abs(tb-nowMin)<Math.abs(ta-nowMin)?b:a;
  });
  timeEl.value=closest;
  /* الفصول من _classes العامة */
  var clsEl=document.getElementById('pv-add-cls');
  clsEl.innerHTML='<option value="">اختر الفصل</option>';
  (_classes||[]).forEach(function(c){
    clsEl.innerHTML+='<option value="'+c.id+'" data-name="'+c.name+'">'+c.name+'</option>';
  });
  document.getElementById('pv-add-stu').innerHTML='<option value="">اختر الطالب</option>';
  document.getElementById('pv-add-grd').value='';
  document.getElementById('pv-add-reason').value='';
  document.getElementById('pv-add-rcv').value='';
  document.getElementById('pv-add-result').value='';
  document.getElementById('pv-add-notes').value='';
  document.getElementById('pv-add-st').innerHTML='';
}

async function pvLoadStudents(){
  var clsEl=document.getElementById('pv-add-cls');
  var cid=clsEl.value;
  var stuEl=document.getElementById('pv-add-stu');
  stuEl.innerHTML='<option value="">اختر الطالب</option>';
  document.getElementById('pv-add-grd').value='';
  _pvStudMap={};
  if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);
  if(!d||!d.ok)return;
  (d.students||[]).forEach(function(s){
    _pvStudMap[s.id]=s.name;
    stuEl.innerHTML+='<option value="'+s.id+'">'+s.name+'</option>';
  });
}

function pvFillGuardian(){
  var stuEl=document.getElementById('pv-add-stu');
  var sid=stuEl.value;
  var sname=stuEl.options[stuEl.selectedIndex]&&stuEl.options[stuEl.selectedIndex].text;
  document.getElementById('pv-add-grd').value=sname?'ولي أمر: '+sname:'';
}

async function pvSave(){
  var date=document.getElementById('pv-add-date').value;
  var time=document.getElementById('pv-add-time').value;
  var stuEl=document.getElementById('pv-add-stu');
  var sid=stuEl.value;
  var sname=stuEl.options[stuEl.selectedIndex]&&stuEl.options[stuEl.selectedIndex].text;
  var clsEl=document.getElementById('pv-add-cls');
  var cls=clsEl.options[clsEl.selectedIndex]&&clsEl.options[clsEl.selectedIndex].dataset.name||clsEl.value;
  var grd=document.getElementById('pv-add-grd').value;
  var reason=document.getElementById('pv-add-reason').value;
  var rcv=document.getElementById('pv-add-rcv').value;
  var result=document.getElementById('pv-add-result').value;
  var notes=document.getElementById('pv-add-notes').value.trim();
  var st=document.getElementById('pv-add-st');
  if(!date||!time||!sid||!cls||!reason||!rcv||!result){
    st.innerHTML='<span style="color:#dc2626">⚠️ يرجى تعبئة جميع الحقول المطلوبة</span>';return;
  }
  st.innerHTML='⏳ جارٍ الحفظ...';
  var payload={date:date,visit_time:time,student_id:sid,student_name:sname,
    class_name:cls,guardian_name:grd,visit_reason:reason,received_by:rcv,
    visit_result:result,notes:notes};
  var r=await fetch('/web/api/parent-visits',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  var d=await r.json();
  if(d.ok){
    document.getElementById('pv-modal').style.display='none';
    pvLoad();
  } else {
    st.innerHTML='<span style="color:#dc2626">❌ '+d.msg+'</span>';
  }
}

async function pvDelete(id){
  if(!confirm('هل تريد حذف هذا السجل؟'))return;
  var r=await fetch('/web/api/parent-visits/'+id,{method:'DELETE'});
  var d=await r.json();
  if(d.ok)pvLoad();else alert('خطأ في الحذف');
}

function pvPrintReport(){
  var from=document.getElementById('pv-from').value;
  var to=document.getElementById('pv-to').value;
  var url='/web/parent-visits/report?from='+from+'&to='+to;
  var q=document.getElementById('pv-search').value.trim();
  if(q){url+='&q='+encodeURIComponent(q);}
  window.open(url,'_blank');
}

/* إغلاق مودال زيارات عند النقر خارجه */
document.addEventListener('click',function(e){
  var m=document.getElementById('pv-modal');
  if(m&&e.target===m)m.style.display='none';
});

/* ── TEACHER FORMS (نماذج المعلم) ── */
async function toBase64(file){
   return new Promise(function(resolve){
       if(!file) return resolve('');
       var reader = new FileReader();
       reader.onload = function(e){ resolve(e.target.result.split(',')[1]); };
       reader.onerror = function(){ resolve(''); };
       reader.readAsDataURL(file);
   });
}
async function submitTeacherForm(formType, sendToPrincipal){
  var payload={form_type:formType,send:sendToPrincipal};
  if(formType==='lesson'){
    payload.strategy=document.getElementById('tfl-strat').value;
    payload.subject=document.getElementById('tfl-subj').value;
    payload.date=document.getElementById('tfl-date').value;
    payload.grade=document.getElementById('tfl-grade').value;
    payload.class_name=document.getElementById('tfl-cls').value;
    payload.student_count=document.getElementById('tfl-count').value;
    payload.lesson=document.getElementById('tfl-lesson').value;
    payload.evidence=document.getElementById('tfl-evidence').value;
    payload.goals=document.getElementById('tfl-goals').value.split('\n').filter(Boolean);
    payload.tools=Array.from(document.querySelectorAll('#tfl-tools input:checked')).map(function(c){return c.value;});
    payload.evidence_img_b64 = await toBase64(document.getElementById('tfl-ev-img').files[0]);
    payload.executor_name = document.getElementById('tfl-executor').value;
    payload.principal_name = document.getElementById('tfl-principal').value;
  } else {
    payload.date=document.getElementById('tfp-date').value || new Date().toISOString().split('T')[0];
    payload.executor=document.getElementById('tfp-exec').value;
    payload.place=document.getElementById('tfp-place').value;
    payload.target=document.getElementById('tfp-target').value;
    payload.count=document.getElementById('tfp-count').value;
    payload.goals=document.getElementById('tfp-goals').value.split('\n').filter(Boolean);
    payload.img1_b64 = await toBase64(document.getElementById('tfp-img1').files[0]);
    payload.img2_b64 = await toBase64(document.getElementById('tfp-img2').files[0]);
    payload.executor_name = document.getElementById('tfp-executor').value;
    payload.principal_name = document.getElementById('tfp-principal').value;
  }
  var stId=formType==='lesson'?'tfl-st':'tfp-st';
  ss(stId,'⏳ جارٍ الإنشاء...','ai');
  try {
      if(!sendToPrincipal){
         var r = await fetch('/web/api/generate-teacher-form',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
         var blob = await r.blob();
         ss(stId,'✅ تم الإنشاء','ok');
         var url=URL.createObjectURL(blob);
         var w=window.open(url,'_blank');
         if(!w){var a=document.createElement('a');a.href=url;a.download=formType+'.pdf';document.body.appendChild(a);a.click();URL.revokeObjectURL(url);}
      } else {
         var r = await fetch('/web/api/send-teacher-form',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
         var d = await r.json();
         if(d.ok) ss(stId,'✅ '+d.msg,'ok'); else ss(stId,'❌ '+d.msg,'er');
      }
  } catch(err) {
      ss(stId,'❌ فشل العملية','er');
  }
}


/* ── CLASS LIST ── */
async function loadClassList(){
  var d=await api('/web/api/classes');if(!d||!d.ok){document.getElementById('cn-list').innerHTML='<p style="color:var(--mu)">لا يوجد فصول</p>';return;}
  document.getElementById('cn-list').innerHTML='<div style="display:flex;flex-wrap:wrap;gap:8px">'+
    d.classes.map(function(c){return '<div class="sci" style="min-width:200px"><strong>'+c.name+'</strong><span class="badge bb" style="margin-right:8px">'+c.count+' طالب</span></div>';}).join('')+'</div>';
}

/* ── LOGS ── */
async function loadLogsAbs(){
  var from=document.getElementById('lg-from').value;var to=document.getElementById('lg-to').value;
  var url='/web/api/absences-range?from='+from+'&to='+to;
  var cls=document.getElementById('lg-cls').value;if(cls)url+='&class_id='+cls;
  var d=await api(url);if(!d||!d.ok)return;
  document.getElementById('lg-abs-tbl').innerHTML=(d.rows||[]).map(function(r){
    return '<tr><td>'+r.date+'</td><td>'+r.student_name+'</td><td>'+r.class_name+'</td><td>'+(r.period||'-')+'</td><td>'+(r.teacher_name||'-')+'</td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا يوجد</td></tr>';
}

/* ── RESULTS ── */
async function loadResults(){
  var d=await api('/web/api/results');if(!d||!d.ok){document.getElementById('res-table').innerHTML='<tr><td colspan="6" style="color:#9CA3AF">لا توجد نتائج</td></tr>';return;}
  document.getElementById('res-table').innerHTML=(d.results||[]).map(function(r){
    return '<tr><td>'+r.identity_no+'</td><td>'+r.student_name+'</td><td>'+(r.section||'-')+'</td>'+
           '<td>'+(r.school_year||'-')+'</td><td>'+(r.gpa||'-')+'</td>'+
           '<td><a href="/results/'+r.identity_no+'" target="_blank" class="btn bp1 bsm">عرض</a></td></tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا توجد نتائج</td></tr>';
}
async function uploadResults(){
  var year=document.getElementById('res-year').value.trim();
  var f=document.getElementById('res-pdf').files[0];
  if(!year||!f){ss('res-up-st','اختر العام الدراسي وملف PDF','er');return;}
  ss('res-up-st','⏳ جارٍ الرفع...','ai');
  var fd=new FormData();fd.append('year',year);fd.append('file',f);
  try{
    var r=await fetch('/web/api/upload-results',{method:'POST',body:fd});
    var d=await r.json();
    ss('res-up-st',d.ok?('✅ تم الرفع — عدد الطلاب: '+(d.count||0)):('❌ '+(d.msg||'فشل')),d.ok?'ok':'er');
    if(d.ok){document.getElementById('res-pdf').value='';loadResults();}
  }catch(e){ss('res-up-st','❌ خطأ في الاتصال','er');}
}

/* ── NOOR ── */
async function exportNoor(){
  var date=document.getElementById('noor-date').value||today;
  var cls=document.getElementById('noor-cls').value;
  var url='/web/api/noor-export?date='+date+(cls?'&class_id='+cls:'');
  var r=await fetch(url);
  if(r.ok){var b=await r.blob();var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='noor_'+date+'.xlsx';a.click();}
  else{ss('noor-st','❌ فشل التصدير','er');}
}
async function saveNoorCfg(){
  var time=document.getElementById('noor-time').value;
  var auto=document.getElementById('noor-auto').checked;
  try{
    var r=await fetch('/web/api/save-noor-config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({auto_export:auto,export_time:time})});
    var d=await r.json();ss('noor-st',d.ok?'✅ تم حفظ إعدادات نور':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  }catch(e){ss('noor-st','❌ خطأ في الاتصال','er');}
}

/* ── GRADE ANALYSIS — يستخدم نفس محرّك التطبيق المكتبي ── */
async function analyzeStudent(forcedSid){
  var sid = forcedSid || document.getElementById('an-student').value;
  if(!sid){alert('اختر طالباً');return;}
  
  if(forcedSid) {
      showTab('student_analysis');
      var sel = document.getElementById('an-student');
      if(sel) {
          // جلب أو إنشاء الخيار
          var existing = Array.from(sel.options).find(o => o.value === sid);
          if(!existing){
              var opt = document.createElement('option');
              opt.value = sid; opt.text = 'تحميل الطالب...'; opt.selected = true;
              sel.appendChild(opt);
          } else {
              existing.selected = true;
          }
      }
  }

  var box=document.getElementById('an-result');
  box.style.display='block';
  document.getElementById('an-header-name').textContent = '⏳ جاري تحميل بيانات الطالب...';
  
  var d=await api('/web/api/student-analysis/'+sid);
  if(!d||!d.ok){
      document.getElementById('an-header-name').textContent = '❌ فشل التحميل';
      return;
  }
  var a=d.data||{};
  
  // تحديث الاسم في الهيدر والدروب داون
  var fullName = a.name || 'طالب';
  var className = a.class_name || '';
  document.getElementById('an-header-name').innerHTML = '<i class="fas fa-user-graduate"></i> ' + fullName + (className ? ' — <span style="font-weight:400; font-size:16px">' + className + '</span>' : '');
  
  // تحديث نص الخيار في الدروب داون إذا كان غير واضح
  var sel = document.getElementById('an-student');
  if(sel && sel.value === sid){
      var opt = sel.options[sel.selectedIndex];
      if(opt.text === 'تحميل الطالب...' || opt.text === 'طالب محدد...') {
          opt.text = fullName;
      }
  }
  
  document.getElementById('an-total-points').textContent = a.total_points || 0;
  document.getElementById('an-portal-st').innerHTML = '<button class="btn bsm bp1" onclick="getPortalLink(\''+sid+'\')">توليد الرابط</button>';
  
  var cardsHtml=crd(a.total_absences||0,'#C62828','أيام الغياب','🔴')+
                crd(a.total_tardiness||0,'#E65100','مرات التأخر','⏰')+
                crd(a.total_excuses||0,'#2E7D32','أعذار مقبولة','✅')+
                crd(a.referrals_count||0,'#7c3aed','تحويلات الموجّه','🧠');
  document.getElementById('an-cards').innerHTML=cardsHtml;
  
  renderStudentCharts(a);
  
  var tblBody=document.getElementById('an-table-body');
  tblBody.innerHTML=(a.timeline||[]).map(function(t){
    var cl=(t.type==='غياب')?'r':(t.type==='تأخر')?'o':'g';
    return '<tr><td>'+t.date+'</td><td><span class="badge '+cl+'">'+t.type+'</span></td><td>'+(t.notes||t.details||'-')+'</td><td>'+(t.status||'مسجل')+'</td></tr>';
  }).join('')||'<tr><td colspan="4" style="color:var(--mu);text-align:center">لا يوجد سجل</td></tr>';

  var ptsBody=document.getElementById('an-pts-table-body');
  var ptsHist = a.points_history || [];
  if(ptsHist.length > 0){
      document.getElementById('an-pts-section').style.display = 'block';
      ptsBody.innerHTML = ptsHist.map(function(p){
          var auth = p.author_name || p.author_id || 'مدير';
          return '<tr><td>'+p.date+'</td><td><span class="badge g">+'+p.points+'</span></td><td>'+(p.reason||'-')+'</td><td>'+auth+'</td></tr>';
      }).join('');
  } else {
      document.getElementById('an-pts-section').style.display = 'none';
  }
}

function renderStudentCharts(data){
    // منطق رسم المخططات (يمكن تفصيله لاحقاً)
}

/* ── LEADERBOARD & POINTS ── */
async function loadLeaderboard(){
  // جلب الرصيد إذا كان المستخدم معلماً
  var uname = document.body.dataset.user;
  var month = new Date().toISOString().slice(0, 7);
  var d_bal = await api('/web/api/teacher-balance?username='+uname+'&month='+month);
  
  if(d_bal && d_bal.ok){
      var limit = d_bal.limit || 100;
      var used = d_bal.balance || 0;
      var rem = limit - used;
      if(rem < 0) rem = 0;
      
      var card = document.getElementById('lb-balance-card');
      var remEl = document.getElementById('lb-remaining');
      var barEl = document.getElementById('lb-balance-bar');
      var noteEl = document.getElementById('lb-balance-note');
      
      if(uname === 'admin') {
          if(card) card.style.display = 'none'; // المدير لا يحتاج لرؤية رصيده الخاص في هذا الكارت
      } else {
          if(card) {
              card.style.display = 'flex';
              if(remEl) remEl.textContent = rem;
              if(barEl) barEl.style.width = Math.max(0, Math.min(100, (rem/limit)*100)) + '%';
              if(noteEl) noteEl.innerHTML = 'الحد المسموح لك: ' + limit + ' نقطة شهرياً<br>تم استهلاك: ' + used;
              
              // تغيير لون البار إذا قارب على الانتهاء
              if(barEl) barEl.style.background = (rem <= limit * 0.2) ? '#f87171' : '#fff';
          }
      }
  }

  var d=await api('/web/api/leaderboard'); if(!d||!d.ok) return;
  document.getElementById('lb-table').innerHTML = d.rows.map(function(r, i){
    var icon = (i===0)?'🥇':(i===1)?'🥈':(i===2)?'🥉':'';
    return '<tr><td>'+(i+1)+' '+icon+'</td><td>'+r.name+'</td><td>'+r.class_name+'</td>'+
           '<td><span class="badge bg" style="font-size:14px">'+r.points+' ⭐</span></td>'+
           '<td><button class="btn bsm bp2" onclick="showAnForLb(\''+r.student_id+'\')">تحليل</button></td></tr>';
  }).join('') || '<tr><td colspan="5" style="color:var(--mu);text-align:center">لا توجد بيانات حالياً</td></tr>';
}
function showAnForLb(sid){
  analyzeStudent(sid);
}
async function loadLbStus(){
  var cid = document.getElementById('lb-cls').value; if(!cid) return;
  var d = await api('/web/api/class-students/'+cid); if(!d||!d.ok) return;
  document.getElementById('lb-stu').innerHTML = '<option value="">اختر</option>' +
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
async function addPointsManual(){
  var sid = document.getElementById('lb-stu').value;
  var pts = document.getElementById('lb-pts').value;
  var reason = document.getElementById('lb-reason').value;
  if(!sid||!pts){ alert('أكمل البيانات'); return; }
  ss('lb-st', '⏳ جارٍ المنح...', 'in');
  try {
      var r=await fetch('/web/api/points/add', {method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({student_id:sid, points:parseInt(pts), reason:reason})});
      var d=await r.json();
      if(d.ok){ 
          ss('lb-st', '✅ تم منح النقاط بنجاح — تم الخصم من رصيدك الشهري', 'ok'); 
          loadLeaderboard(); 
          document.getElementById('lb-pts').value = 5;
          document.getElementById('lb-reason').value = '';
      } else { ss('lb-st', '❌ '+(d.msg||'فشل'), 'er'); }
  } catch(e) { ss('lb-st', '❌ خطأ اتصال', 'er'); }
}

async function loadPointsAdminLogs(){
  var tb=document.getElementById('pc-logs-table-v2'); if(!tb) return;
  tb.innerHTML='<tr><td colspan="6" style="text-align:center;padding:15px">⏳ جارٍ التحميل...</td></tr>';
  var d=await api('/web/api/admin/points-logs-v2');if(!d||!d.ok){
    tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:#ef4444;padding:15px">❌ فشل تحميل البيانات</td></tr>';
    return;
  }
  var logs = d.logs || [];
  if(logs.length===0){
    tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:#64748b;padding:15px">لا توجد عمليات مسجلة حالياً</td></tr>';
    return;
  }
  tb.innerHTML=logs.map(function(r){
    var teacher = r.teacher_full_name || r.author_name || r.author_id || 'مدير';
    return '<tr><td style="font-size:12px">'+r.date+'</td><td style="font-weight:600">'+teacher+'</td><td>'+(r.student_name||'طالب')+' <small style="display:block;color:#94a3b8">'+(r.class_name||'-')+'</small></td>'+
           '<td><span class="badge bg" style="font-size:13px">+'+r.points+'</span></td><td style="font-size:12px;color:#475569">'+(r.reason||'-')+'</td>'+
           '<td><button class="btn bp3 bsm" onclick="deletePointsRecord('+r.id+')"><i class="fas fa-trash-alt"></i></button></td></tr>';
  }).join('');
}

async function loadTeachersUsage(){
  var tb=document.getElementById('pc-usage-table-v2'); if(!tb) return;
  tb.innerHTML='<tr><td colspan="5" style="text-align:center;padding:15px">⏳ جارٍ التحميل...</td></tr>';
  var month = document.getElementById('pc-month') ? document.getElementById('pc-month').value : new Date().toISOString().slice(0,7);
  var d=await api('/web/api/admin/points-usage-v2?month='+month);if(!d||!d.ok){
    tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:#ef4444;padding:15px">❌ فشل تحميل البيانات</td></tr>';
    return;
  }
  var usage = d.usage || [];
  if(usage.length===0){
    tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:#64748b;padding:15px">لا توجد بيانات لهذا الشهر</td></tr>';
    return;
  }
  tb.innerHTML=usage.map(function(r){
    var used = r.used || 0;
    var limit = r.limit || 100;
    var rem = r.remaining || 0;
    var pct = limit > 0 ? Math.min(100, (used/limit)*100) : 0;
    var color = pct > 90 ? '#ef4444' : (pct > 70 ? '#f59e0b' : '#10b981');
    var statusTxt = rem <= 0 ? 'منتهي' : (rem < 20 ? 'منخفض' : 'متوفر');
    var statusBg = rem <= 0 ? '#fee2e2' : (rem < 20 ? '#fef3c7' : '#dcfce7');
    var statusColor = rem <= 0 ? '#991b1b' : (rem < 20 ? '#92400e' : '#166534');
    
    return '<tr>' +
           '<td style="font-weight:700">'+(r.name||r.username)+'<br><small style="font-weight:normal;color:#64748b">'+(r.role==='activity_leader'?'رائد نشاط':'معلم')+'</small></td>' +
           '<td><b>'+used+'</b> / '+limit+'</td>' +
           '<td style="color:#16a34a; font-weight:bold">+' + (r.extra || 0) + '</td>' +
           '<td style="color:'+color+'; font-weight:900; font-size:15px">'+rem+'</td>' +
           '<td><span class="badge" style="background:'+statusBg+'; color:'+statusColor+'; font-size:11px; padding:3px 8px">'+statusTxt+'</span></td>' +
           '</tr>';
  }).join('');
}
async function savePointsSettings(){
  var lim=document.getElementById('pc-limit-cfg').value;if(!lim){alert('أدخل الحد');return;}
  var r=await fetch('/web/api/admin/points-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({limit:parseInt(lim)})});
  var d=await r.json();if(d.ok){alert('✅ تم الحفظ');loadTeachersUsage();}
}
async function deletePointsRecord(id){
  if(!confirm('هل أنت متأكد من حذف هذا السجل؟ سيتم إعادة النقاط لرصيد المعلم.'))return;
  var r=await fetch('/web/api/admin/points-delete/'+id,{method:'DELETE'});
  var d=await r.json();if(d.ok){loadPointsAdminLogs();loadTeachersUsage();}
}
async function loadUsersForAdj(){
  var d=await api('/web/api/users');if(!d||!d.ok)return;
  var sel = document.getElementById('pc-adj-user'); if(!sel) return;
  var users = d.users || [];
  sel.innerHTML='<option value="">اختر مستخدماً</option>'+
    users.filter(u=>u.role!=='admin').map(u=>'<option value="'+u.username+'">'+u.full_name+' ('+u.role+')</option>').join('');
}
async function adjustUserPoints(){
  var u=document.getElementById('pc-adj-user').value;
  var p=document.getElementById('pc-adj-pts').value;
  var r=document.getElementById('pc-adj-reason').value;
  if(!u||!p){alert('أكمل البيانات');return;}
  var res=await fetch('/web/api/admin/points-adjust',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:u,points:parseInt(p),reason:r})});
  var d=await res.json();
  if(d.ok){alert('✅ تم زيادة الرصيد بنجاح');loadTeachersUsage();loadPointsAdminLogs();}else{alert('❌ '+d.msg);}
}


async function getPortalLink(sid){
  var st = document.getElementById('an-portal-st');
  st.textContent = '⏳ جاري التوليد...';
  var d = await api('/web/api/portal-link/'+sid);
  if(d && d.ok){
    st.innerHTML = '<a href="'+d.link+'" target="_blank" style="color:var(--pr);font-weight:700;margin-right:10px">🔗 فتح الرابط</a> ' +
                   '<button class="btn bsm bp1" onclick="navigator.clipboard.writeText(\''+d.link+'\');alert(\'تم نسخ الرابط\')">نسخ</button>';
  } else { st.textContent = '❌ فشل'; }
}

async function loadGradeAnalysis(){
  // عند فتح التبويب: حاول جلب آخر تحليل محفوظ
  var d=await api('/web/api/grade-analysis');
  if(d&&d.ok&&d.has_data&&d.html){
    renderGaHtml(d.html);
    ss('ga-st','📌 يتم عرض آخر تحليل محفوظ — ارفع ملفاً جديداً لتحديثه','ai');
  }
}
async function analyzeGrades(){
  var f=document.getElementById('ga-file').files[0];
  if(!f){ss('ga-st','اختر ملفاً أولاً','er');return;}
  ss('ga-st','⏳ جارٍ تحليل الملف بنفس محرّك التطبيق المكتبي...','ai');
  document.getElementById('ga-res').innerHTML='<div class="loading">⏳ جارٍ التحليل...</div>';
  document.getElementById('ga-summary').innerHTML='';
  document.getElementById('ga-filter').style.display='none';
  var fd=new FormData();fd.append('file',f);
  try{
    var r=await fetch('/web/api/grade-analysis-upload',{method:'POST',body:fd});
    var d=await r.json();
    if(!d.ok){
      ss('ga-st','❌ '+(d.msg||'فشل التحليل'),'er');
      document.getElementById('ga-res').innerHTML='<div class="ab ae">❌ '+(d.msg||'فشل')+'</div>';
      return;
    }
    ss('ga-st','✅ تم تحليل '+d.students+' طالب','ok');
    document.getElementById('ga-summary').innerHTML='<div class="stat-cards">'+
      crd(d.students,'#1565C0','عدد الطلاب','👨‍🎓')+
      crd(d.average+'%','#2471A3','متوسط التحصيل','📊')+
      crd(d.pass_rate+'%',d.pass_rate>=70?'#27AE60':'#E67E22','نسبة النجاح','✅')+
      '</div>';
    // بناء قائمة المواد في الفلتر
    var sel=document.getElementById('ga-subject-sel');
    sel.innerHTML='<option value="الكل">📚 جميع المواد</option>';
    (d.subjects||[]).forEach(function(s){
      sel.innerHTML+='<option value="'+s+'">'+s+'</option>';
    });
    document.getElementById('ga-filter').style.display='';
    document.getElementById('ga-filter-info').textContent=(d.subjects||[]).length+' مادة';
    renderGaHtml(d.html);
  }catch(e){
    ss('ga-st','❌ خطأ في الاتصال','er');
    document.getElementById('ga-res').innerHTML='<div class="ab ae">❌ خطأ في الاتصال</div>';
  }
}
async function gaFilterSubject(){
  var sub=document.getElementById('ga-subject-sel').value;
  var info=document.getElementById('ga-filter-info');
  info.textContent='⏳ جارٍ التحديث...';
  try{
    var r=await fetch('/web/api/grade-analysis-view?subject='+encodeURIComponent(sub));
    var html=await r.text();
    renderGaHtml(html, true);
    info.textContent=sub==='الكل'?'جميع المواد':'مادة: '+sub;
  }catch(e){
    info.textContent='❌ خطأ';
  }
}
function renderGaHtml(html, isFullPage){
  var box=document.getElementById('ga-res');
  box.innerHTML='<iframe id="ga-frame" style="width:100%;height:800px;border:1px solid var(--bd);border-radius:var(--rd);background:#fff" sandbox="allow-same-origin allow-modals allow-scripts allow-forms"></iframe>';
  var iframe=document.getElementById('ga-frame');
  var doc=iframe.contentDocument||iframe.contentWindow.document;
  doc.open();
  if(isFullPage){
    doc.write(html);
  }else{
    doc.write('<!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><style>body{margin:0;font-family:Tahoma,Arial,sans-serif;direction:rtl}</style></head><body>'+html+'</body></html>');
  }
  doc.close();
}
function printGaFrame(){
  var sub=document.getElementById('ga-subject-sel')?document.getElementById('ga-subject-sel').value:'الكل';
  window.open('/web/api/grade-analysis-print?subject='+encodeURIComponent(sub),'_blank');
}

/* ── REPORT HELPERS ── */
async function loadClassReport(){
  var cid=document.getElementById('tr-cls').value;
  var sem=document.getElementById('tr-sem').value;
  var box=document.getElementById('tr-res');
  ss('tr-st','⏳ جارٍ التحميل...','ai');
  if(box)box.innerHTML='<div class="loading">⏳</div>';
  try{
    var url='/web/api/class-report?semester='+encodeURIComponent(sem);
    if(cid) url+='&class_id='+encodeURIComponent(cid);
    var d=await api(url);
    if(!d||!d.ok){ss('tr-st','❌ '+((d&&d.msg)||'فشل'),'er');if(box)box.innerHTML='';return;}
    ss('tr-st','','');
    var title=cid?(d.class_name||cid):'جميع الفصول';
    var html='<div class="section"><div class="st">الفصل الدراسي '+(sem==='1'?'الأول':sem==='2'?'الثاني':'الثالث')+' — '+title+'</div></div>'+
      '<div class="stat-cards">'+
      crd(d.students||0,'#1565C0','عدد الطلاب','👨‍🎓')+
      crd(d.total_absences||0,'#C62828','إجمالي الغياب','🔴')+
      crd(d.total_tardiness||0,'#E65100','إجمالي التأخر','⏰')+
      crd((d.avg_absent_per_student||0).toFixed(1),'#7c3aed','متوسط الغياب/طالب','📊')+
      '</div>';
    html+='<div class="section"><div class="st">الطلاب مرتبون حسب الغياب</div><div class="tw"><table><thead><tr><th>#</th><th>الطالب</th><th>الفصل</th><th>أيام الغياب</th><th>التأخر</th></tr></thead><tbody>';
    (d.rows||[]).forEach(function(r,i){
      html+='<tr><td>'+(i+1)+'</td><td>'+r.name+'</td><td>'+(r.class_name||'')+'</td><td>'+r.absences+'</td><td>'+r.tardiness+'</td></tr>';
    });
    html+='</tbody></table></div></div>';
    if(box)box.innerHTML=html;
  }catch(e){ss('tr-st','❌ خطأ في الاتصال','er');if(box)box.innerHTML='';}
}
async function loadStuReport(){
  var sid=document.getElementById('rp-ss').value;
  if(!sid){alert('اختر طالباً');return;}
  var d=await api('/web/api/student-analysis/'+sid);
  if(!d||!d.ok){alert('❌ فشل التحميل');return;}
  var a=d.data||{};
  var html='<div class="section"><div class="st">تقرير الطالب: '+(a.name||'')+'</div>'+
    '<p><strong>الفصل:</strong> '+(a.class_name||'—')+'</p>'+
    '<p><strong>أيام الغياب:</strong> '+(a.total_absences||0)+'</p>'+
    '<p><strong>مرات التأخر:</strong> '+(a.total_tardiness||0)+'</p></div>';
  var box=document.getElementById('rp-res');if(box)box.innerHTML=html;else alert('✅');
}
async function loadClsForRp(){
  var cid=document.getElementById('rp-sc').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('rp-ss').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
async function addStudentManual(){
  var id=document.getElementById('as-id').value.trim();
  var name=document.getElementById('as-name').value.trim();
  var cls=document.getElementById('as-cls').value;
  var phone=document.getElementById('as-phone').value.trim();
  var level=document.getElementById('as-level').value;
  if(!id||!name||!cls){ss('as-st','أكمل الحقول المطلوبة (الرقم، الاسم، الفصل)','er');return;}
  try{
    var r=await fetch('/web/api/add-student',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({student_id:id,name:name,class_id:cls,phone:phone,level:level})});
    var d=await r.json();
    ss('as-st',d.ok?'✅ تمت الإضافة بنجاح':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
    if(d.ok){
      document.getElementById('as-id').value='';
      document.getElementById('as-name').value='';
      document.getElementById('as-phone').value='';
    }
  }catch(e){ss('as-st','❌ خطأ في الاتصال','er');}
}
async function importExcel(){
  var f=document.getElementById('as-xl-file').files[0];
  if(!f){ss('as-xl-st','اختر ملفاً','er');return;}
  ss('as-xl-st','⏳ جارٍ الاستيراد...','ai');
  var fd=new FormData();fd.append('file',f);fd.append('mode','generic');
  try{
    var r=await fetch('/web/api/import-students',{method:'POST',body:fd});
    var d=await r.json();
    ss('as-xl-st',d.ok?('✅ تم استيراد '+(d.count||0)+' طالباً'):('❌ '+(d.msg||'فشل')),d.ok?'ok':'er');
    if(d.ok)document.getElementById('as-xl-file').value='';
  }catch(e){ss('as-xl-st','❌ خطأ في الاتصال','er');}
}
async function importNoor(){
  var f=document.getElementById('as-noor-file').files[0];
  if(!f){ss('as-noor-st','اختر ملف نور','er');return;}
  ss('as-noor-st','⏳ جارٍ استيراد ملف نور...','ai');
  var fd=new FormData();fd.append('file',f);fd.append('mode','noor');
  try{
    var r=await fetch('/web/api/import-students',{method:'POST',body:fd});
    var d=await r.json();
    ss('as-noor-st',d.ok?('✅ تم استيراد '+(d.count||0)+' طالباً من نور'):('❌ '+(d.msg||'فشل')),d.ok?'ok':'er');
    if(d.ok)document.getElementById('as-noor-file').value='';
  }catch(e){ss('as-noor-st','❌ خطأ في الاتصال','er');}
}

/* ── INBOX ── */
var _inboxMode='inbox';
function inboxSwitch(mode){
  _inboxMode=mode;
  ['inbox','sent','compose'].forEach(function(m){
    document.getElementById('inbox-pane-'+m).classList.toggle('active',m===mode);
    document.getElementById('inbox-tab-'+(m==='inbox'?'in':m==='sent'?'out':'new')).classList.toggle('active',m===mode);
  });
  if(mode==='inbox')loadInbox();
  else if(mode==='sent')loadInboxSent();
  else inboxLoadUsers();
}
async function loadInbox(){
  var box=document.getElementById('inbox-list');box.innerHTML='<div class="loading">⏳</div>';
  var d=await api('/web/api/inbox');
  if(!d||!d.ok){box.innerHTML='<p style="color:#94A3B8;text-align:center;padding:30px">تعذر التحميل</p>';return;}
  var msgs=d.messages||[];
  box.innerHTML=msgs.length?msgs.map(function(m){
    var unread=!m.is_read;
    return '<div onclick="inboxOpenMsg('+m.id+',\'inbox\')" style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:'+(unread?'#EFF6FF':'white')+';border:1px solid #E2E8F0;border-radius:10px;cursor:pointer;transition:.2s" onmouseenter="this.style.background=\'#F1F5F9\'" onmouseleave="this.style.background=\''+(unread?'#EFF6FF':'white')+'\'">'
      +'<div style="flex:1;min-width:0">'
      +'<div style="font-weight:'+(unread?'700':'500')+';font-size:14px">'+escHtml(m.subject||'(بدون موضوع)')+(m.attachment_path?' 📎':'')+'</div>'
      +'<div style="font-size:12px;color:#64748B;margin-top:2px">من: '+escHtml(m.from_user)+'</div></div>'
      +'<div style="text-align:left;flex-shrink:0">'
      +(unread?'<span style="background:#3B82F6;color:white;border-radius:20px;padding:2px 8px;font-size:11px">جديد</span>':'')
      +'<div style="font-size:11px;color:#94A3B8;margin-top:4px">'+fmtInboxDate(m.created_at)+'</div></div>'
      +'<button onclick="event.stopPropagation();inboxDelete('+m.id+',\'inbox\')" style="background:none;border:none;cursor:pointer;color:#CBD5E1;font-size:18px" title="حذف">×</button>'
      +'</div>';
  }).join(''):'<p style="color:#94A3B8;text-align:center;padding:30px">📭 لا توجد رسائل</p>';
  inboxUpdateBadge();
}
async function loadInboxSent(){
  var box=document.getElementById('inbox-sent-list');box.innerHTML='<div class="loading">⏳</div>';
  var d=await api('/web/api/inbox/sent');
  if(!d||!d.ok){box.innerHTML='<p style="color:#94A3B8;text-align:center;padding:30px">تعذر التحميل</p>';return;}
  var msgs=d.messages||[];
  box.innerHTML=msgs.length?msgs.map(function(m){
    return '<div onclick="inboxOpenMsg('+m.id+',\'sent\')" style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:white;border:1px solid #E2E8F0;border-radius:10px;cursor:pointer;transition:.2s" onmouseenter="this.style.background=\'#F1F5F9\'" onmouseleave="this.style.background=\'white\'">'+
      '<div style="flex:1;min-width:0">'+
      '<div style="font-weight:500;font-size:14px">'+escHtml(m.subject||'(بدون موضوع)')+(m.attachment_path?' 📎':'')+'</div>'+
      '<div style="font-size:12px;color:#64748B;margin-top:2px">إلى: '+escHtml(m.to_user)+'</div></div>'+
      '<div style="text-align:left;flex-shrink:0"><div style="font-size:11px;color:#94A3B8">'+fmtInboxDate(m.created_at)+'</div></div>'+
      '<button onclick="event.stopPropagation();inboxDelete('+m.id+',\'sent\')" style="background:none;border:none;cursor:pointer;color:#CBD5E1;font-size:18px" title="حذف">×</button>'+
      '</div>';
  }).join(''):'<p style="color:#94A3B8;text-align:center;padding:30px">📭 لا توجد رسائل مرسلة</p>';
}
async function inboxLoadUsers(){
  var sel=document.getElementById('inbox-to');
  if(sel.options.length>1)return;
  var d=await api('/web/api/inbox/users');
  if(!d||!d.users)return;
  d.users.forEach(function(u){
    var o=document.createElement('option');o.value=u.username;
    o.textContent=(u.full_name||u.username)+' ('+u.username+')';
    sel.appendChild(o);
  });
}
async function inboxOpenMsg(id,box){
  var modal=document.getElementById('inbox-msg-modal');
  var content=document.getElementById('inbox-msg-content');
  content.innerHTML='<div class="loading">⏳</div>';
  modal.style.display='flex';
  var endpoint=box==='inbox'?'/web/api/inbox':'/web/api/inbox/sent';
  var d=await api(endpoint);
  if(!d||!d.messages){content.innerHTML='تعذر التحميل';return;}
  var msg=d.messages.find(function(m){return m.id===id;});
  if(!msg){content.innerHTML='الرسالة غير موجودة';return;}
  if(box==='inbox'&&!msg.is_read){
    await fetch('/web/api/inbox/'+id+'/read',{method:'POST'});
    inboxUpdateBadge();loadInbox();
  }
  var dir=box==='inbox'?'من: '+escHtml(msg.from_user):'إلى: '+escHtml(msg.to_user);
  var attHtml='';
  if(msg.attachment_path){
    var isImg=/\.(jpg|jpeg|png|gif|webp)$/i.test(msg.attachment_name||'');
    var attUrl='/web/api/inbox/attachment/'+encodeURIComponent(msg.attachment_path);
    if(isImg){
      attHtml='<div style="margin-top:14px"><div style="font-size:12px;color:#64748B;margin-bottom:6px">📎 مرفق:</div>'+
        '<img src="'+attUrl+'" style="max-width:100%;border-radius:8px;border:1px solid #E2E8F0" alt="'+escHtml(msg.attachment_name||'')+'"></div>';
    } else {
      var sizeKb=msg.attachment_size?Math.round(msg.attachment_size/1024)+' KB':'';
      attHtml='<div style="margin-top:14px"><a href="'+attUrl+'" download="'+escHtml(msg.attachment_name||'file')+'" '+
        'style="display:inline-flex;align-items:center;gap:8px;padding:10px 14px;background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;text-decoration:none;color:#1E293B;font-size:13px">'+
        '📎 '+escHtml(msg.attachment_name||'مرفق')+(sizeKb?' — '+sizeKb:'')+' ⬇️</a></div>';
    }
  }
  content.innerHTML='<h3 style="margin:0 0 12px;font-size:17px;color:#1E293B">'+escHtml(msg.subject||'(بدون موضوع)')+'</h3>'+
    '<div style="font-size:12px;color:#64748B;margin-bottom:16px">'+dir+' — '+fmtInboxDate(msg.created_at)+'</div>'+
    '<div style="white-space:pre-wrap;font-size:14px;line-height:1.7;color:#334155;padding:14px;background:#F8FAFC;border-radius:8px">'+escHtml(msg.body)+'</div>'+
    attHtml;
}
function inboxCloseMsg(){document.getElementById('inbox-msg-modal').style.display='none';}
async function inboxDelete(id,box){
  if(!confirm('حذف هذه الرسالة؟'))return;
  await fetch('/web/api/inbox/'+id,{method:'DELETE'});
  if(box==='inbox')loadInbox();else loadInboxSent();
}
var _inboxAttachment=null;
function inboxAttachmentChanged(input){
  var f=input.files[0];
  if(!f){_inboxAttachment=null;document.getElementById('inbox-att-preview').textContent='';return;}
  if(f.size>20*1024*1024){ss('inbox-compose-st','❌ الملف أكبر من 20 ميغابايت','er');input.value='';return;}
  _inboxAttachment=f;
  var icon=f.type.startsWith('image/')?'🖼️':'📎';
  document.getElementById('inbox-att-preview').textContent=icon+' '+f.name+' ('+Math.round(f.size/1024)+' KB)';
}
function inboxClearAttachment(){
  _inboxAttachment=null;
  document.getElementById('inbox-attachment').value='';
  document.getElementById('inbox-att-preview').textContent='';
}
async function inboxSend(){
  var to=document.getElementById('inbox-to').value;
  var sub=document.getElementById('inbox-subject').value.trim();
  var body=document.getElementById('inbox-body').value.trim();
  if(!to){ss('inbox-compose-st','اختر المستلم','er');return;}
  if(!body){ss('inbox-compose-st','اكتب نص الرسالة','er');return;}
  var attId='', attName='', attSize=0;
  if(_inboxAttachment){
    ss('inbox-compose-st','⏳ جارٍ رفع المرفق...','ai');
    var fd=new FormData();fd.append('file',_inboxAttachment);
    var ur=await fetch('/web/api/inbox/upload-attachment',{method:'POST',body:fd});
    var ud=await ur.json();
    if(!ud.ok){ss('inbox-compose-st','❌ فشل رفع المرفق: '+(ud.msg||'خطأ'),'er');return;}
    attId=ud.file_id;attName=ud.file_name;attSize=ud.file_size;
  }
  ss('inbox-compose-st','⏳ جارٍ الإرسال...','ai');
  var r=await fetch('/web/api/inbox/send',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({to_user:to,subject:sub,body:body,attachment_id:attId,attachment_name:attName,attachment_size:attSize})});
  var d=await r.json();
  if(d.ok){
    ss('inbox-compose-st','✅ تم الإرسال بنجاح','ok');
    document.getElementById('inbox-subject').value='';
    document.getElementById('inbox-body').value='';
    document.getElementById('inbox-to').value='';
    inboxClearAttachment();
  } else ss('inbox-compose-st','❌ '+(d.msg||'خطأ'),'er');
}
async function inboxUpdateBadge(){
  var d=await api('/web/api/inbox/unread-count');if(!d||!d.ok)return;
  var n=d.count||0;
  var sb=document.getElementById('inbox-sidebar-badge');
  var ub=document.getElementById('inbox-unread-badge');
  if(sb){sb.textContent=n;sb.style.display=n?'':'none';}
  if(ub){ub.textContent=n;ub.style.display=n?'':'none';}
}
function fmtInboxDate(iso){
  if(!iso)return '';
  try{var d=new Date(iso);return d.toLocaleDateString('ar-SA')+' '+d.toLocaleTimeString('ar-SA',{hour:'2-digit',minute:'2-digit'});}
  catch(e){return iso.substring(0,16);}
}
function escHtml(s){var d=document.createElement('div');d.appendChild(document.createTextNode(s||''));return d.innerHTML;}
setInterval(inboxUpdateBadge,60000);

/* ── UTILITIES ── */
function exportTbl(id,name){
  var tb=document.getElementById(id);if(!tb)return;
  var rows=Array.from(tb.querySelectorAll('tr')).map(function(tr){
    return Array.from(tr.querySelectorAll('th,td')).map(function(td){return td.textContent.trim();}).join('\t');}).join('\n');
  var b=new Blob(['\uFEFF'+rows],{type:'text/plain;charset=utf-8'});
  var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name+'_'+today+'.txt';a.click();
}
function printSec(id){
  var c=document.getElementById(id);if(!c)return;
  var w=window.open('','_blank');w.document.write('<html dir="rtl"><head><meta charset="UTF-8"><title>طباعة</title></head><body>'+c.innerHTML+'</body></html>');
  w.print();w.close();
}

/* ── ACADEMIC INQUIRIES ── */
async function loadCounselorInquiries(){
  var d=await api('/web/api/academic-inquiries');
  if(!d||!d.ok)return;
  document.getElementById('coinq-tbl').innerHTML=(d.rows||[]).map(function(r){
    var st = r.status==='جديد'?'<span class="badge bo">جديد - بانتظار المعلم</span>':'<span class="badge bg">تم الرد</span>';
    return '<tr><td>'+r.inquiry_date+'</td><td>'+r.teacher_name+'</td><td>'+r.class_name+'</td><td>'+r.subject+'</td><td>'+st+'</td>'+
    '<td><button class="btn bp1 bsm" onclick="viewInqDetails('+r.id+',true)">الرد</button></td></tr>';
  }).join('')||'<tr><td colspan="6" style="text-align:center;color:var(--mu)">لا توجد خطابات</td></tr>';
  
  // load teachers drop down
  var dt=await api('/web/api/teachers');
  if(dt&&dt.ok){
     document.getElementById('coinq-teacher').innerHTML='<option value="">اختر المعلم</option>'+
       dt.teachers.map(function(t){var n=t["اسم المعلم"]||t.full_name||'';return '<option value="'+n+'">'+n+'</option>';}).join('');
  }
}

async function sendCounselorInquiry(){
  var tSel=document.getElementById('coinq-teacher');
  var teacher_uname = tSel.value;
  var teacher_name = tSel.options[tSel.selectedIndex]?tSel.options[tSel.selectedIndex].text:'';
  var date = document.getElementById('coinq-date').value;
  var class_name = document.getElementById('coinq-class').value;
  var subject = document.getElementById('coinq-subject').value;
  var student_name = document.getElementById('coinq-student').value;
  if(!teacher_uname || !class_name || !subject){
    ss('coinq-st','أكمل البيانات المطلوبة (المعلم، الفصل، المادة)','er'); return;
  }
  var r = await fetch('/web/api/create-academic-inquiry',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      inquiry_date:date, teacher_username:teacher_uname, teacher_name:teacher_name,
      class_name:class_name, subject:subject, student_name:student_name
    })});
  var d=await r.json();
  ss('coinq-st',d.ok?'✅ تم إرسال الخطاب للمعلم':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  if(d.ok){
    document.getElementById('coinq-class').value='';
    document.getElementById('coinq-subject').value='';
    document.getElementById('coinq-student').value='الكل';
    loadCounselorInquiries();
  }
}

async function loadTeacherInquiries(){
  var d=await api('/web/api/academic-inquiries');
  if(!d||!d.ok)return;
  document.getElementById('tfinq-tbl').innerHTML=(d.rows||[]).map(function(r){
    var st = r.status==='جديد'?'<span class="badge bo">جديد</span>':'<span class="badge bg">تم الرد</span>';
    var btn = r.status==='جديد'? '<button class="btn bp1 bsm" onclick="openTeacherInquiryReply('+r.id+')">رد على الاستفسار</button>'
           : '<button class="btn bp4 bsm" onclick="viewInqDetails('+r.id+',false)">التفاصيل</button>';
    return '<tr><td>'+r.inquiry_date+'</td><td>'+r.class_name+'</td><td>'+r.subject+'</td><td>'+r.student_name+'</td><td>'+st+'</td>'+
    '<td>'+btn+'</td></tr>';
  }).join('')||'<tr><td colspan="6" style="text-align:center;color:var(--mu)">لا توجد خطابات مرسلة لك</td></tr>';
}

function openTeacherInquiryReply(id){
  document.getElementById('tfinq-id').value = id;
  document.getElementById('tfinq-reasons').value = '';
  document.getElementById('tfinq-evidence').value = '';
  document.getElementById('tfinq-file').value = '';
  document.getElementById('tfinq-st').innerHTML = '';
  document.getElementById('tfinq-reply-form').style.display = 'block';
  document.getElementById('tfinq-reply-form').scrollIntoView();
}

async function submitTeacherInquiryReply(){
  var id = document.getElementById('tfinq-id').value;
  var reasons = document.getElementById('tfinq-reasons').value;
  var evidence = document.getElementById('tfinq-evidence').value;
  var file_b64 = await toBase64(document.getElementById('tfinq-file').files[0]);
  
  if(!reasons){
      ss('tfinq-st','الرجاء كتابة الأسباب على الأقل','er');return;
  }
  
  var payload = {
      id: id,
      reasons: reasons,
      evidence_text: evidence,
      evidence_img_b64: file_b64,
      reply_date: new Date().toISOString().split('T')[0]
  };
  
  ss('tfinq-st','⏳ جارٍ الإرسال...','ai');
  var r = await fetch('/web/api/reply-academic-inquiry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  var d = await r.json();
  if(d.ok){
      ss('tfinq-st','✅ تم إرسال الرد بنجاح','ok');
      document.getElementById('tfinq-reply-form').style.display = 'none';
      loadTeacherInquiries();
  } else {
      ss('tfinq-st','❌ '+(d.msg||'خطأ'),'er');
  }
}

function viewInqDetails(id, isCounselor){
  if(typeof showCoModal !== 'function'){
     alert('تم تسجيل الرد أو الخطاب. يمكنك مراجعته.');
     return;
  }
  fetch('/web/api/academic-inquiries').then(function(r){return r.json();}).then(function(d){
    if(d.ok){
      var inq = (d.rows||[]).find(function(x){return x.id==id;});
      if(inq){
        var html = '<div style="line-height:1.6;font-size:14px;padding:10px">';
        html += '<p><strong>التاريخ:</strong> '+inq.inquiry_date+'</p>';
        html += '<p><strong>المعلم:</strong> '+inq.teacher_name+'</p>';
        html += '<p><strong>الفصل:</strong> '+inq.class_name+'</p>';
        html += '<p><strong>المادة:</strong> '+inq.subject+'</p>';
        html += '<p><strong>الطالب:</strong> '+inq.student_name+'</p>';
        if(inq.status !== 'جديد'){
            html += '<hr><p><strong>تاريخ الرد:</strong> '+inq.reply_date+'</p>';
            html += '<p><strong>أسباب تدني المستوى:</strong> '+(inq.reasons||'-')+'</p>';
            html += '<p><strong>الشواهد:</strong> '+(inq.evidence_text||'-')+'</p>';
            if(inq.evidence_file) {
                 html += '<p><strong>مرفق:</strong> (تم إرفاق صورة/ملف في النظام)</p>';
            }
        } else {
            html += '<hr><p style="color:red">لم يتم الرد من المعلم بعد.</p>';
        }
        html += '</div>';
        showCoModal('تفاصيل الاستفسار الأكاديمي', html, '#1565C0', '#0D47A1');
      }
    }
  });
}

async function checkUnreadCirculars(){
  try {
    // جلب عدد التعاميم غير المقروءة
    var d = await api('/web/api/circulars/unread-count');
    if(d && d.ok && d.count > 0){
      var html = '<div style="text-align:center;padding:10px">' +
                 '<div style="font-size:50px;margin-bottom:15px">🔔</div>' +
                 '<h3 style="color:#f97316;margin-bottom:10px">لديك تعاميم جديدة غير مقروءة!</h3>' +
                 '<p style="color:#64748b;margin-bottom:20px;font-size:15px">يوجد عدد <b>('+d.count+')</b> تعميم جديد بانتظار مراجعتك في تبويب التعاميم والنشرات.</p>' +
                 '<button class="btn bp1" style="width:100%;justify-content:center;padding:12px;font-size:16px" onclick="showTab(\'circulars\');document.getElementById(\'co-modal\').remove();">' +
                 '<i class="fas fa-scroll" style="margin-left:8px"></i> الانتقال للتعاميم الآن</button>' +
                 '</div>';
      showCoModal('تنبيه هام', html, '#f97316', '#ea580c');
    }
  } catch(e) { console.error('checkUnreadCirculars Error:', e); }
}

/* ── TEACHER REPORTS (Admin) ── */
async function checkUnreadTeacherReports(){
  try {
    if(!_me || !['admin','deputy'].includes(_me.role)) return;
    var d = await api('/web/api/teacher-reports/unread-count');
    if(d && d.ok && d.count > 0){
      var html = '<div style="text-align:center;padding:10px">' +
                 '<div style="font-size:50px;margin-bottom:15px">📄</div>' +
                 '<h3 style="color:#7c3aed;margin-bottom:10px">تقارير معلمين جديدة!</h3>' +
                 '<p style="color:#64748b;margin-bottom:20px;font-size:15px">يوجد <b>('+d.count+')</b> تقرير جديد من المعلمين بانتظار مراجعتك.</p>' +
                 '<button class="btn" style="background:#7c3aed;color:#fff;width:100%;justify-content:center;padding:12px;font-size:16px" ' +
                 'onclick="showTab(\'teacher_reports_admin\');document.getElementById(\'co-modal\').remove();">' +
                 '<i class="fas fa-file-pdf" style="margin-left:8px"></i> عرض التقارير</button>' +
                 '</div>';
      showCoModal('تقارير معلمين جديدة', html, '#7c3aed', '#6d28d9');
    }
  } catch(e) {}
}

async function loadTeacherReportsAdmin(){
  var tb = document.getElementById('tra-tbody');
  if(!tb) return;
  tb.innerHTML = '<tr><td colspan="6" style="text-align:center">⏳ جارٍ التحميل...</td></tr>';
  var d = await api('/web/api/teacher-reports');
  if(!d || !d.ok){ tb.innerHTML='<tr><td colspan="6" style="color:red;text-align:center">❌ فشل التحميل</td></tr>'; return; }
  var rows = d.reports || [];
  var badge = document.getElementById('tra-badge');
  var unread = rows.filter(function(r){return !r.is_read;}).length;
  if(badge){ if(unread>0){badge.textContent=unread+' جديد';badge.style.display='inline-block';}else{badge.style.display='none';} }
  if(!rows.length){ tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--mu)">لا توجد تقارير</td></tr>'; return; }
  tb.innerHTML = rows.map(function(r){
    var typeLabel = r.form_type==='lesson'?'📘 تحضير درس':'📊 تقرير تنفيذ';
    var statusBadge = r.is_read
      ? '<span class="badge bg" style="font-size:11px">مقروء</span>'
      : '<span class="badge bo" style="font-size:11px">جديد</span>';
    var date = r.submitted_at ? r.submitted_at.substring(0,16).replace('T',' ') : '-';
    return '<tr style="'+(r.is_read?'':'background:#f5f3ff')+'">' +
      '<td>'+typeLabel+'</td>' +
      '<td style="font-weight:600">'+r.title+'</td>' +
      '<td>'+r.submitted_name+'</td>' +
      '<td style="font-size:12px;color:#64748b">'+date+'</td>' +
      '<td>'+statusBadge+'</td>' +
      '<td style="display:flex;gap:6px">' +
        '<button class="btn bp1 bsm" onclick="viewTeacherReport('+r.id+')"><i class="fas fa-eye"></i> عرض</button>' +
        '<button class="btn bp3 bsm" onclick="deleteTeacherReport('+r.id+')"><i class="fas fa-trash"></i></button>' +
      '</td></tr>';
  }).join('');
}

async function viewTeacherReport(id){
  await fetch('/web/api/teacher-reports/'+id+'/read', {method:'POST'});
  window.open('/web/api/teacher-reports/'+id+'/pdf','_blank');
  setTimeout(loadTeacherReportsAdmin, 800);
}

async function deleteTeacherReport(id){
  if(!confirm('هل تريد حذف هذا التقرير نهائياً؟')) return;
  var r = await fetch('/web/api/teacher-reports/'+id, {method:'DELETE'});
  var d = await r.json();
  if(d.ok) loadTeacherReportsAdmin(); else alert('فشل الحذف');
}

async function submitTeacherFormPortal(formType){
  var stId = formType==='lesson'?'tfl-st':'tfp-st';
  ss(stId,'⏳ جارٍ الإرسال...','ai');
  try {
    var payload = {form_type: formType};
    if(formType==='lesson'){
      payload.strategy = document.getElementById('tfl-strat').value;
      payload.subject  = document.getElementById('tfl-subj').value;
      payload.date     = document.getElementById('tfl-date').value;
      payload.grade    = document.getElementById('tfl-grade').value;
      payload.class_name    = document.getElementById('tfl-cls').value;
      payload.student_count = document.getElementById('tfl-count').value;
      payload.lesson   = document.getElementById('tfl-lesson').value;
      payload.evidence = document.getElementById('tfl-evidence').value;
      payload.goals    = document.getElementById('tfl-goals').value.split('\n').filter(Boolean);
      payload.tools    = Array.from(document.querySelectorAll('#tfl-tools input:checked')).map(function(c){return c.value;});
      payload.evidence_img_b64 = await toBase64(document.getElementById('tfl-ev-img').files[0]);
      payload.executor_name  = document.getElementById('tfl-executor').value;
      payload.principal_name = document.getElementById('tfl-principal').value;
    } else {
      payload.date     = document.getElementById('tfp-date').value || new Date().toISOString().split('T')[0];
      payload.executor = document.getElementById('tfp-exec').value;
      payload.place    = document.getElementById('tfp-place').value;
      payload.target   = document.getElementById('tfp-target').value;
      payload.count    = document.getElementById('tfp-count').value;
      payload.goals    = document.getElementById('tfp-goals').value.split('\n').filter(Boolean);
      payload.img1_b64 = await toBase64(document.getElementById('tfp-img1').files[0]);
      payload.img2_b64 = await toBase64(document.getElementById('tfp-img2').files[0]);
      payload.executor_name  = document.getElementById('tfp-executor').value;
      payload.principal_name = document.getElementById('tfp-principal').value;
    }
    var r = await fetch('/web/api/teacher-reports/submit', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
    var d = await r.json();
    if(d.ok) ss(stId,'✅ تم الإرسال للإدارة بنجاح','ok');
    else ss(stId,'❌ '+(d.msg||'فشل الإرسال'),'er');
  } catch(err){ ss(stId,'❌ خطأ في الإرسال','er'); }
}

/* ── SCHOOL REPORTS ── */
var _srCat='', _srCatCanUpload=false;
var _SR_CATS=[
  {key:'admin',         label:'تقارير الإدارة',           icon:'👑', color:'#7c3aed', bg:'#f5f3ff', roles:['admin']},
  {key:'educational',   label:'تقارير الشؤون التعليمية',   icon:'📚', color:'#1d4ed8', bg:'#eff6ff', roles:['admin','deputy']},
  {key:'school_affairs',label:'تقارير الشؤون المدرسية',    icon:'🏫', color:'#059669', bg:'#f0fdf4', roles:['admin','deputy']},
  {key:'guidance',      label:'تقارير التوجيه الطلابي',    icon:'💡', color:'#d97706', bg:'#fffbeb', roles:['admin','counselor']},
  {key:'activity',      label:'تقارير النشاط الطلابي',     icon:'⚽', color:'#dc2626', bg:'#fef2f2', roles:['admin','activity_leader']},
  {key:'achievement',   label:'تقارير التحصيل الدراسي',    icon:'🏆', color:'#b45309', bg:'#fefce8', roles:['admin','deputy','teacher']},
];
async function loadSchoolReports(){
  document.getElementById('sr-grid').style.display='';
  document.getElementById('sr-cat-view').style.display='none';
  _srCat='';
  var d=await api('/web/api/school-reports/counts');
  var counts=(d&&d.ok)?d.counts:{};
  var role=(_me&&_me.role)?_me.role:'';
  document.getElementById('sr-folders').innerHTML=_SR_CATS.map(function(c){
    var cnt=counts[c.key]||0;
    return '<div onclick="srOpenCategory(\''+c.key+'\')" style="cursor:pointer;background:'+c.bg+';border:2px solid '+c.color+'40;border-radius:16px;padding:28px 16px 20px;text-align:center;transition:transform .18s,box-shadow .18s;box-shadow:0 2px 8px rgba(0,0,0,.07)" onmouseover="this.style.transform=\'translateY(-5px)\';this.style.boxShadow=\'0 10px 24px rgba(0,0,0,.13)\'" onmouseout="this.style.transform=\'\';this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.07)\'">'
      +'<div style="font-size:50px;margin-bottom:10px;line-height:1">'+c.icon+'</div>'
      +'<div style="font-size:13px;font-weight:700;color:'+c.color+';margin-bottom:10px;line-height:1.3">'+c.label+'</div>'
      +'<div style="background:'+c.color+';color:#fff;border-radius:20px;padding:3px 14px;font-size:12px;display:inline-block;font-weight:600">'+cnt+' '+(cnt===1?'تقرير':'تقارير')+'</div>'
      +'</div>';
  }).join('');
}
async function srOpenCategory(cat){
  _srCat=cat;
  var c=_SR_CATS.find(function(x){return x.key===cat;})||{label:cat,color:'#333',bg:'#fff',roles:[]};
  var role=(_me&&_me.role)?_me.role:'';
  _srCatCanUpload=c.roles.indexOf(role)>=0;
  document.getElementById('sr-cat-title').textContent=c.label;
  var badge=document.getElementById('sr-cat-badge');
  badge.style.background=c.color; badge.textContent=c.label;
  document.getElementById('sr-upload-section').style.display=_srCatCanUpload?'':'none';
  document.getElementById('sr-grid').style.display='none';
  document.getElementById('sr-cat-view').style.display='';
  var rd=document.getElementById('sr-rdate'); if(rd&&!rd.value)rd.value=today;
  await srLoadList();
}
function srBack(){
  _srCat='';
  document.getElementById('sr-cat-view').style.display='none';
  document.getElementById('sr-grid').style.display='';
  loadSchoolReports();
}
async function srLoadList(){
  var el=document.getElementById('sr-list');
  if(!el)return;
  el.innerHTML='<div style="text-align:center;color:var(--mu);padding:30px">⏳ جاري التحميل...</div>';
  var d=await api('/web/api/school-reports?category='+encodeURIComponent(_srCat));
  if(!d||!d.ok){el.innerHTML='<div style="color:#ef4444;padding:16px">❌ خطأ في التحميل</div>';return;}
  if(!d.rows||!d.rows.length){
    el.innerHTML='<div style="text-align:center;color:var(--mu);padding:48px"><div style="font-size:48px;opacity:.25;margin-bottom:12px"><i class="fas fa-folder-open"></i></div>لا توجد تقارير مرفوعة بعد</div>';
    return;
  }
  el.innerHTML=d.rows.map(function(r){
    var extIcon='📄';
    var fn=(r.file_name||'').toLowerCase();
    if(fn.endsWith('.pdf'))extIcon='📕';
    else if(fn.match(/\.(doc|docx)$/))extIcon='📘';
    else if(fn.match(/\.(xls|xlsx)$/))extIcon='📗';
    else if(fn.match(/\.(ppt|pptx)$/))extIcon='📙';
    else if(fn.match(/\.(jpg|jpeg|png)$/))extIcon='🖼️';
    var sz=r.file_size?'('+Math.round(r.file_size/1024)+' KB)':'';
    return '<div style="border:1px solid var(--bd);border-radius:12px;padding:16px;margin-bottom:12px;background:var(--card)">'
      +'<div style="display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap">'
      +'<div style="font-size:32px;line-height:1;padding-top:2px">'+extIcon+'</div>'
      +'<div style="flex:1;min-width:180px">'
      +'<div style="font-size:15px;font-weight:700;margin-bottom:4px">'+r.title+'</div>'
      +(r.description?'<div style="color:var(--mu);font-size:13px;margin-bottom:6px">'+r.description+'</div>':'')
      +'<div style="font-size:12px;color:var(--mu)">📅 '+r.report_date+' &nbsp;·&nbsp; 👤 '+r.uploaded_by+' &nbsp;·&nbsp; 📎 '+(r.file_name||'')+' '+sz+'</div>'
      +'</div>'
      +'<div style="display:flex;gap:8px;align-items:center;flex-shrink:0">'
      +'<a href="/web/api/school-reports/file/'+r.id+'" target="_blank" class="btn bp2 bsm"><i class="fas fa-download"></i> تحميل</a>'
      +(_srCatCanUpload?'<button class="btn bp5 bsm" onclick="srDelete('+r.id+',\''+String(r.title).replace(/'/g,"\\'")+'\')" title="حذف"><i class="fas fa-trash"></i></button>':'')
      +'</div>'
      +'</div>'
      +'</div>';
  }).join('');
}
async function srUpload(){
  var title=(document.getElementById('sr-title').value||'').trim();
  var rdate=document.getElementById('sr-rdate').value||'';
  var desc=(document.getElementById('sr-desc').value||'').trim();
  var fileEl=document.getElementById('sr-file');
  var st=document.getElementById('sr-upload-st');
  if(!title){st.textContent='❌ أدخل عنوان التقرير';st.style.color='#ef4444';return;}
  if(!rdate){st.textContent='❌ أدخل تاريخ التقرير';st.style.color='#ef4444';return;}
  if(!fileEl.files||!fileEl.files[0]){st.textContent='❌ اختر ملفاً';st.style.color='#ef4444';return;}
  st.textContent='⏳ جاري الرفع...';st.style.color='#f59e0b';
  var fd=new FormData();
  fd.append('file',fileEl.files[0]);
  fd.append('category',_srCat);
  fd.append('title',title);
  fd.append('report_date',rdate);
  fd.append('description',desc);
  try{
    var r=await fetch('/web/api/school-reports/upload',{method:'POST',body:fd});
    var d=await r.json();
    if(d.ok){
      st.textContent='✅ تم رفع التقرير بنجاح';st.style.color='#22c55e';
      document.getElementById('sr-title').value='';
      document.getElementById('sr-desc').value='';
      fileEl.value='';
      await srLoadList();
      loadSchoolReports();
    }else{st.textContent='❌ '+(d.msg||'خطأ');st.style.color='#ef4444';}
  }catch(e){st.textContent='❌ خطأ في الاتصال';st.style.color='#ef4444';}
}
async function srDelete(id,title){
  if(!confirm('هل أنت متأكد من حذف التقرير:\n«'+title+'»؟'))return;
  var d=await api('/web/api/school-reports/'+id,{method:'DELETE'});
  if(d&&d.ok){await srLoadList();loadSchoolReports();}
  else alert('❌ '+(d&&d.msg||'خطأ'));
}

/* ── WEEKLY REWARDS ── */
async function loadWeeklyReward(){
  var d=await api('/web/api/rewards/settings');
  if(d && d.ok){
    document.getElementById('wr-cfg-enabled').value = d.enabled ? "1" : "0";
    document.getElementById('wr-cfg-day').value = d.day;
    document.getElementById('wr-cfg-hour').value = d.hour;
    document.getElementById('wr-cfg-min').value = d.minute;
    document.getElementById('wr-cfg-tpl').value = d.template;
  }
}
async function loadPerfectStudents(){
  var f=document.getElementById('wr-from').value;
  var t=document.getElementById('wr-to').value;
  if(!f || !t) return;
  ss('wr-status', '🔎 جاري الفحص...', 'in');
  var d=await api('/web/api/rewards/perfect-attendance?start='+f+'&end='+t);
  if(!d || !d.ok){ ss('wr-status', '❌ فشل الفحص', 'er'); return; }
  document.getElementById('wr-count').textContent = d.students.length;
  document.getElementById('wr-table').innerHTML = d.students.map(function(s){
    return '<tr><td>'+s.name+'</td><td>'+s.class_name+'</td><td>'+(s.phone||'-')+'</td></tr>';
  }).join('') || '<tr><td colspan="3" style="color:var(--mu);text-align:center">لا يوجد طلاب ملتزمون في هذه الفترة</td></tr>';
  document.getElementById('wr-send-btn').style.display = d.students.length > 0 ? 'inline-block' : 'none';
  ss('wr-status', '✅ تم العثور على ' + d.students.length + ' طالب ملتزم', 'ok');
}
async function runManualRewards(){
  if(!confirm('هل أنت متأكد من إرسال رسائل التعزيز لجميع هؤلاء الطلاب الآن؟')) return;
  ss('wr-status', '🚀 جاري بدء عملية الإرسال...', 'in');
  var r=await fetch('/web/api/rewards/send', {method:'POST'});
  var d=await r.json();
  if(d.ok){
    document.getElementById('wr-sent').textContent = d.results.sent;
    document.getElementById('wr-failed').textContent = d.results.failed;
    ss('wr-status', '✅ اكتمل الإرسال: تم إرسال ' + d.results.sent + ' بنجاح، وفشل ' + d.results.failed, 'ok');
  } else {
    ss('wr-status', '❌ فشل التشغيل: ' + d.msg, 'er');
  }
}
async function saveRewardSettings(){
  var data = {
    enabled: document.getElementById('wr-cfg-enabled').value === "1",
    day: parseInt(document.getElementById('wr-cfg-day').value),
    hour: parseInt(document.getElementById('wr-cfg-hour').value),
    minute: parseInt(document.getElementById('wr-cfg-min').value),
    template: document.getElementById('wr-cfg-tpl').value
  };
  ss('wr-cfg-st', '⏳ جاري الحفظ...', 'in');
  var r=await fetch('/web/api/rewards/save-settings', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
  });
  var d=await r.json();
  ss('wr-cfg-st', d.ok ? '✅ تم حفظ الإعدادات بنجاح' : '❌ فشل الحفظ', d.ok ? 'ok' : 'er');
}

/* ── LEADERBOARD & POINTS ── */
async function loadTeacherBalance(){
  if(!_me || !_me.username) return;
  var card = document.getElementById('lb-balance-card');
  var remEl = document.getElementById('lb-remaining');
  var barEl = document.getElementById('lb-balance-bar');
  var noteEl = document.getElementById('lb-balance-note');
  if(!card || !remEl) return;

  if(_me.role === 'admin') {
      card.style.display = 'flex';
      card.style.background = 'linear-gradient(135deg, #475569, #1e293b)';
      remEl.textContent = '∞';
      if(noteEl) noteEl.innerHTML = 'مدير النظام — رصيد غير محدود';
      return;
  }

  var month = new Date().toISOString().slice(0,7);
  var d = await api('/web/api/teacher-balance?username='+encodeURIComponent(_me.username)+'&month='+month);
  if(!d || !d.ok){ card.style.display='none'; return; }

  var limit = d.limit || 100;
  var used = d.balance || 0;
  var remaining = d.remaining != null ? d.remaining : Math.max(0, limit - used);
  card.style.display = 'flex';
  remEl.textContent = remaining;
  var limitEl = document.getElementById('lb-limit-val');
  if(limitEl) limitEl.textContent = limit;
  if(barEl) barEl.style.width = Math.max(0, Math.min(100, (remaining/limit)*100)) + '%';
  if(noteEl) noteEl.innerHTML = 'الحد المسموح: ' + limit + ' نقطة شهرياً<br>تم استهلاك: ' + used;
  if(barEl) barEl.style.background = (remaining <= limit*0.2) ? '#f87171' : '#fff';
  if(remaining === 0) card.style.background = 'linear-gradient(135deg, #dc2626, #b91c1c)';
  else if(remaining <= 20) card.style.background = 'linear-gradient(135deg, #d97706, #b45309)';
  else card.style.background = 'linear-gradient(135deg, #1e40af, #3b82f6)';
}
async function loadLeaderboard(){
  var d=await api('/web/api/leaderboard'); if(!d||!d.ok) return;
  document.getElementById('lb-table').innerHTML = d.rows.map(function(r, i){
    var icon = (i===0)?'\ud83e\udd47':(i===1)?'\ud83e\udd48':(i===2)?'\ud83e\udd49':'';
    return '<tr><td>'+(i+1)+' '+icon+'</td><td>'+r.name+'</td><td>'+r.class_name+'</td>'+
           '<td><span class="badge bg" style="font-size:14px">'+r.points+' \u2b50</span></td>'+
           '<td><button class="btn bsm bp2" onclick="showAnForLb(\''+r.student_id+'\')">تحليل</button></td></tr>';
  }).join('') || '<tr><td colspan="5" style="color:var(--mu);text-align:center">لا توجد بيانات حالياً</td></tr>';
  loadTeacherBalance();
}
function showAnForLb(sid){
  analyzeStudent(sid);
}
async function loadLbStus(){
  var cid = document.getElementById('lb-cls').value; if(!cid) return;
  var d = await api('/web/api/class-students/'+cid); if(!d||!d.ok) return;
  document.getElementById('lb-stu').innerHTML = '<option value="">اختر</option>' +
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
async function addPointsManual(){
  var sid = document.getElementById('lb-stu').value;
  var pts = document.getElementById('lb-pts').value;
  var reason = document.getElementById('lb-reason').value;
  if(!sid||!pts){ alert('أكمل البيانات'); return; }
  ss('lb-st', '⏳ جارٍ المنح...', 'in');
  var r=await fetch('/web/api/points/add', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:sid, points:parseInt(pts), reason:reason})});
  var d=await r.json();
  if(d.ok){ ss('lb-st', '✅ تم منح النقاط بنجاح', 'ok'); loadLeaderboard(); }
  else ss('lb-st', '❌ فشل: '+d.msg, 'er');
}
async function getPortalLink(sid){
  var st = document.getElementById('an-portal-st');
  st.textContent = '⏳ جاري التوليد...';
  var d = await api('/web/api/portal-link/'+sid);
  if(d && d.ok){
    st.innerHTML = '<a href="'+d.link+'" target="_blank" style="color:var(--pr);font-weight:700;margin-right:10px">🔗 فتح الرابط</a> ' +
                   '<button class="btn bsm bp1" onclick="navigator.clipboard.writeText(\''+d.link+'\');alert(\'تم نسخ الرابط\')">نسخ</button>';
  } else { st.textContent = '❌ فشل'; }
}

/* ── EXEMPTED STUDENTS ── */
async function loadExemptedStudents(){
  var d=await api('/web/api/exempted-students');if(!d||!d.ok)return;
  document.getElementById('ex-table').innerHTML=(d.rows||[]).map(function(r){
    return '<tr><td>'+r.student_name+'</td><td>'+r.class_name+'</td><td>'+(r.reason||'-')+'</td><td>'+(r.exempted_at?r.exempted_at.split('T')[0]:'-')+'</td>'+
      '<td><button class="btn bp3 bsm" onclick="removeExemptedStudent(\''+r.student_id+'\')"><i class="fas fa-trash"></i></button></td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF;text-align:center">لا يوجد طلاب مستثنون</td></tr>';
}
async function addExemptedStudent(){
  var cls=document.getElementById('ex-cls').value;
  var stu=document.getElementById('ex-stu').value;
  var reason=document.getElementById('ex-reason').value.trim();
  if(!stu){alert('اختر طالباً');return;}
  var sName = document.getElementById('ex-stu').options[document.getElementById('ex-stu').selectedIndex].text;
  var cName = document.getElementById('ex-cls').options[document.getElementById('ex-cls').selectedIndex].text;
  ss('ex-st','⏳ جارٍ الحفظ...','ai');
  var r=await fetch('/web/api/exempted-students/add',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:stu,student_name:sName,class_id:cls,class_name:cName,reason:reason})});
  var d=await r.json();
  if(d.ok){ss('ex-st','✅ تم الإضافة للقائمة','ok');loadExemptedStudents();document.getElementById('ex-reason').value='';}
  else ss('ex-st','❌ خطأ: '+d.msg,'er');
}
async function removeExemptedStudent(id){
  if(!confirm('هل تريد حذف الطالب من قائمة الاستثناء؟'))return;
  var r=await fetch('/web/api/exempted-students/'+id,{method:'DELETE'});
  var d=await r.json();if(d.ok)loadExemptedStudents();
}
async function loadClsForEx(){
  var cid=document.getElementById('ex-cls').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('ex-stu').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}

async function loadStories(){
  var d=await api('/web/api/stories');
  if(!d || !d.ok) return;
  var html = (d.stories||[]).map(function(s){
    var fname = s.image_path.split(/[\\/]/).pop();
    return '<div class="card" style="padding:10px;text-align:center">' +
           '<img src="/data/school_stories/'+fname+'" style="width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:8px">' +
           '<div style="font-size:12px;font-weight:700;margin-bottom:5px">'+(s.title||'بدون عنوان')+'</div>' +
           '<button class="btn bsm bp3" onclick="deleteStory('+s.id+')">حذف</button></div>';
  }).join('');
  document.getElementById('ss-list').innerHTML = html || '<div style="grid-column:1/-1;text-align:center;color:var(--mu)">لا يوجد قصص منشورة</div>';
}
async function uploadStory(){
  var title = document.getElementById('ss-title').value;
  var fileInput = document.getElementById('ss-file');
  var file = fileInput.files[0];
  if(!file){ alert('يرجى اختيار صورة أولاً'); return; }
  ss('ss-upload-st', '⏳ جاري الرفع...', 'in');
  var fd = new FormData(); fd.append('title', title); fd.append('file', file);
  try {
    var r = await fetch('/web/api/stories/add', {method:'POST', body:fd});
    var d = await r.json();
    if(d.ok){
      ss('ss-upload-st', '✅ تم النشر بنجاح', 'ok');
      document.getElementById('ss-title').value = ''; fileInput.value = '';
      loadStories();
    } else ss('ss-upload-st', '❌ فشل الرفع: ' + (d.msg||'خطأ'), 'er');
  } catch(e){ ss('ss-upload-st', '❌ خطأ اتصال', 'er'); }
}
async function deleteStory(id){
  if(!confirm('حذف القصة؟')) return;
  try {
    var r = await fetch('/web/api/stories/delete/'+id, {method:'DELETE'});
    var d = await r.json(); if(d.ok) loadStories();
  } catch(e){ alert('❌ خطأ اتصال'); }
}
async function toBase64(file){
  if(!file) return null;
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = error => reject(error);
  });
}
"""

    h = '<!DOCTYPE html><html lang="ar" dir="rtl"><head>'
    h += '<meta charset="UTF-8">'
    h += '<meta name="viewport" content="width=device-width,initial-scale=1">'
    h += '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">'
    h += '<title>' + str(school) + ' — لوحة التحكم</title>'
    h += '<style>' + str(css) + '</style>'
    h += '</head><body>'
    h += '<div class="topbar">'
    h += '<div class="tb-l"><button id="mt" onclick="toggleSidebar()"><span></span><span></span><span></span></button>'
    h += '<h1><i class="fas fa-university" style="margin-left:8px;font-size:18px"></i> <span id="sc-name">' + str(school) + '</span></h1></div>'
    h += '<div class="tb-r"><div class="ub"><i class="fas fa-user-circle"></i> <span id="user-name">أهلاً بك...</span></div>'
    h += '<a href="/web/logout" class="lo">خروج</a></div></div>'
    h += '<div id="ov" onclick="closeSidebar()"></div>'
    h += '<div class="sidebar" id="sb">' + str(sidebar_html) + '</div>'
    h += '<div class="content"><div id="tc">' + str(content_html) + '</div></div>'
    h += '<script>' + str(js) + '</script>'
    h += '</body></html>'
    return h




# ═══════════════════════════════════════════════════════════════
# APIs إضافية للواجهة الجديدة
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# APIs إضافية للواجهة الجديدة
# ═══════════════════════════════════════════════════════════════

@router.get("/web/api/config", response_class=JSONResponse)
async def web_get_config(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        cfg = load_config()
        return JSONResponse(cfg)
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/save-config", response_class=JSONResponse)
async def web_save_config(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    if user.get("role") not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        data = await req.json()
        cfg  = load_config()
        cfg.update(data)
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        global _CONFIG_CACHE, _CONFIG_MTIME
        _CONFIG_CACHE = cfg
        try: _CONFIG_MTIME = os.path.getmtime(CONFIG_JSON)
        except: pass
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/users", response_class=JSONResponse)
async def web_get_users(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    if user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "المدير فقط"}, status_code=403)
    try:
        users = get_all_users()
        # إذا كان حقل الجوال فارغاً، نحاول سحبه من teachers.json (مطابقة رقم الهوية = username)
        try:
            if os.path.exists(TEACHERS_JSON):
                with open(TEACHERS_JSON, "r", encoding="utf-8") as _tf:
                    _teachers = json.load(_tf)
                _phone_map = {
                    str(t.get("رقم الهوية", "")).strip(): str(t.get("رقم الجوال", "")).strip()
                    for t in _teachers if t.get("رقم الهوية") and t.get("رقم الجوال")
                }
                for u in users:
                    if not u.get("phone"):
                        u["phone"] = _phone_map.get(str(u.get("username", "")).strip(), "")
        except Exception:
            pass
        return JSONResponse({"ok": True, "users": users})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/add-user", response_class=JSONResponse)
async def web_add_user(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    if user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "المدير فقط"}, status_code=403)
    try:
        data = await req.json()
        ok, msg = create_user(
            data["username"], data["password"],
            data.get("role", "teacher"), data.get("full_name", ""))
        return JSONResponse({"ok": ok, "msg": msg})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/users/send-creds", response_class=JSONResponse)
async def web_send_user_creds(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    if user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "المدير فقط"}, status_code=403)
    try:
        import random
        from whatsapp_service import send_whatsapp_message
        data    = await req.json()
        user_id = data.get("user_id")
        phone   = str(data.get("phone", "")).strip()
        if not user_id or not phone:
            return JSONResponse({"ok": False, "msg": "بيانات ناقصة"})

        users    = get_all_users()
        target   = next((u for u in users if str(u["id"]) == str(user_id)), None)
        if not target:
            return JSONResponse({"ok": False, "msg": "المستخدم غير موجود"})

        username = target["username"]
        name     = target.get("full_name") or username

        # حفظ الرقم إن لم يكن محفوظاً
        if not target.get("phone"):
            save_user_phone(username, phone)

        cfg        = load_config()
        public_url = cfg.get("cloud_url_internal", "") or cfg.get("cloud_url", "") or cfg.get("public_url", "")
        if not public_url:
            return JSONResponse({"ok": False, "msg": "لم يُعثر على الرابط العام — أضفه في الإعدادات"})

        password = str(random.randint(100000, 999999))
        update_user_password(username, password)

        msg = (f"مرحباً {name}\n\n"
               f"بيانات دخولك للنظام:\n\n"
               f"🔗 الرابط: {public_url}/web/login\n"
               f"👤 اسم المستخدم: {username}\n"
               f"🔑 كلمة المرور: {password}\n\n"
               f"مع تحيات إدارة المدرسة")

        ok = send_whatsapp_message(phone, msg)
        if ok:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "msg": "فشل إرسال الرسالة — تأكد من اتصال الواتساب"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/delete-user/{user_id}", response_class=JSONResponse)
async def web_delete_user(user_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    if user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "المدير فقط"}, status_code=403)
    try:
        delete_user(user_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/backups", response_class=JSONResponse)
async def web_get_backups(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        backups = get_backup_list()
        return JSONResponse({"ok": True, "backups": backups})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/create-backup", response_class=JSONResponse)
async def web_create_backup(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        ok, path, size = create_backup()
        if ok:
            return JSONResponse({"ok": True, "filename": path, "size_kb": size})
        return JSONResponse({"ok": False, "msg": path})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/backup/send-telegram", response_class=JSONResponse)
async def web_send_backup_telegram(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        ok, path, size = create_backup()
        if not ok:
            return JSONResponse({"ok": False, "msg": f"فشل إنشاء النسخة: {path}"})
        sent = upload_backup_telegram(path)
        if sent:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "msg": "تأكد من صحة التوكن ومعرّف القناة في الإعدادات"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/download-backup/{filename:path}", response_class=JSONResponse)
async def web_download_backup(filename: str, request: Request):
    user = _get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/web/login")
    try:
        from fastapi.responses import FileResponse
        # أبحث عن الملف بالاسم أو المسار الكامل
        if os.path.isabs(filename) and os.path.exists(filename):
            path = filename
        else:
            path = os.path.join(BACKUP_DIR, os.path.basename(filename))
        if not os.path.exists(path):
            return JSONResponse({"error": "الملف غير موجود"}, status_code=404)
        return FileResponse(path, filename=os.path.basename(path),
                            media_type="application/zip")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/web/api/restore-backup", response_class=JSONResponse)
async def web_restore_backup(req: Request):
    user = _get_current_user(req)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False, "msg": "هذا الإجراء للمدير فقط"}, status_code=403)
    try:
        data = await req.json()
        filename = str(data.get("filename", "")).strip()
        password = str(data.get("password", "")).strip()
        if not filename or not password:
            return JSONResponse({"ok": False, "msg": "بيانات مفقودة"})

        if authenticate(user["username"], password) is None:
            return JSONResponse({"ok": False, "msg": "كلمة المرور غير صحيحة"})

        fpath = filename if (os.path.isabs(filename) and os.path.exists(filename)) \
                else os.path.join(BACKUP_DIR, os.path.basename(filename))
        if not os.path.exists(fpath):
            return JSONResponse({"ok": False, "msg": "ملف النسخة غير موجود"})

        # نسخة من الوضع الحالي قبل الاستعادة
        create_backup()

        import zipfile as _zf
        with _zf.ZipFile(fpath, "r") as zf:
            names = zf.namelist()
            if "absences.db" in names:
                zf.extract("absences.db", os.path.dirname(DB_PATH))
            for jname in ["students.json", "teachers.json", "config.json"]:
                if jname in names:
                    zf.extract(jname, DATA_DIR)

        import constants as _c
        _c.STUDENTS_STORE = None
        from config_manager import invalidate_config_cache
        invalidate_config_cache()
        load_students(force_reload=True)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/delete-absence/{record_id}", response_class=JSONResponse)
async def web_delete_absence(record_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("DELETE FROM absences WHERE id=?", (record_id,))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/delete-tardiness/{record_id}", response_class=JSONResponse)
async def web_delete_tardiness_rec(record_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("DELETE FROM tardiness WHERE id=?", (record_id,))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/approve-permission/{perm_id}", response_class=JSONResponse)
async def web_approve_permission(perm_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); cur = con.cursor()
        cur.execute(
            "UPDATE permissions SET status='موافق', approved_by=?, approved_at=? WHERE id=?",
            (user["sub"], datetime.datetime.utcnow().isoformat(), perm_id))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/update-student-phone", response_class=JSONResponse)
async def web_update_student_phone(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        student_id = str(data["student_id"])
        phone      = str(data["phone"]).strip()
        store = load_students(force_reload=True)
        updated = False
        for cls in store["list"]:
            for s in cls["students"]:
                if str(s["id"]) == student_id:
                    s["phone"] = phone
                    updated = True
        if updated:
            import os as _os
            create_backup()
            _tmp = STUDENTS_JSON + ".tmp"
            with open(_tmp, "w", encoding="utf-8") as f:
                json.dump({"classes": store["list"]}, f, ensure_ascii=False, indent=2)
            _os.replace(_tmp, STUDENTS_JSON)
            load_students(force_reload=True)
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "msg": "الطالب غير موجود"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/students/{student_id}", response_class=JSONResponse)
async def web_delete_student(student_id: str, req: Request):
    user = _get_current_user(req)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح — للمدير والوكيل فقط"}, status_code=403)
    try:
        store = load_students(force_reload=True)
        found = False
        deleted_name = ""
        for cls in store["list"]:
            for i, s in enumerate(cls["students"]):
                if str(s["id"]) == str(student_id):
                    deleted_name = s.get("name", "")
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
        add_transferred_student(student_id, deleted_name)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/inbox/users", response_class=JSONResponse)
async def web_inbox_users(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    users = get_all_users()
    result = [{"username": u["username"], "full_name": u.get("full_name") or u["username"]}
              for u in users if u["username"] != user["username"]]
    return JSONResponse({"ok": True, "users": result})


@router.get("/web/api/inbox", response_class=JSONResponse)
async def web_inbox_get(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    msgs = get_inbox_messages(user["username"])
    return JSONResponse({"ok": True, "messages": msgs})

@router.get("/web/api/inbox/sent", response_class=JSONResponse)
async def web_inbox_sent(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    msgs = get_sent_messages(user["username"])
    return JSONResponse({"ok": True, "messages": msgs})

@router.get("/web/api/inbox/unread-count", response_class=JSONResponse)
async def web_inbox_unread_count(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    count = get_inbox_unread_count(user["username"])
    return JSONResponse({"ok": True, "count": count})

@router.post("/web/api/inbox/send", response_class=JSONResponse)
async def web_inbox_send(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await req.json()
        to_user  = data.get("to_user", "").strip()
        subject  = data.get("subject", "").strip()
        body     = data.get("body", "").strip()
        if not to_user or not body:
            return JSONResponse({"ok": False, "msg": "المستلم والرسالة مطلوبان"})
        if to_user == user["username"]:
            return JSONResponse({"ok": False, "msg": "لا يمكن إرسال رسالة لنفسك"})
        att_id   = data.get("attachment_id", "")
        att_name = data.get("attachment_name", "")
        att_size = data.get("attachment_size", 0)
        msg_id = send_inbox_message(user["username"], to_user, subject, body,
                                    att_id or None, att_name or None, att_size or None)
        return JSONResponse({"ok": True, "id": msg_id})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/inbox/{msg_id}/read", response_class=JSONResponse)
async def web_inbox_mark_read(msg_id: int, req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    mark_inbox_message_read(msg_id, user["username"])
    return JSONResponse({"ok": True})

@router.delete("/web/api/inbox/{msg_id}", response_class=JSONResponse)
async def web_inbox_delete(msg_id: int, req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    delete_inbox_message(msg_id, user["username"])
    return JSONResponse({"ok": True})


@router.post("/web/api/inbox/upload-attachment", response_class=JSONResponse)
async def web_inbox_upload_attachment(req: Request, file: UploadFile = File(...)):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        import uuid, os as _os
        _os.makedirs(INBOX_ATTACHMENTS_DIR, exist_ok=True)
        ext  = _os.path.splitext(file.filename or "file")[1][:10]
        fname = uuid.uuid4().hex + ext
        fpath = _os.path.join(INBOX_ATTACHMENTS_DIR, fname)
        content = await file.read()
        if len(content) > 20 * 1024 * 1024:
            return JSONResponse({"ok": False, "msg": "الحد الأقصى لحجم المرفق 20 ميغابايت"})
        with open(fpath, "wb") as f:
            f.write(content)
        return JSONResponse({"ok": True, "file_id": fname,
                             "file_name": file.filename, "file_size": len(content)})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/inbox/attachment/{file_id}")
async def web_inbox_get_attachment(file_id: str, req: Request):
    user = _get_current_user(req)
    if not user: return Response("غير مصرح", status_code=401)
    import os as _os, re
    if not re.match(r'^[a-f0-9]{32}\.[a-zA-Z0-9]{0,10}$', file_id):
        return Response("معرف غير صالح", status_code=400)
    fpath = _os.path.join(INBOX_ATTACHMENTS_DIR, file_id)
    if not _os.path.exists(fpath):
        return Response("الملف غير موجود", status_code=404)
    from fastapi.responses import FileResponse
    return FileResponse(fpath)


@router.get("/web/api/absences-range", response_class=JSONResponse)
async def web_absences_range(request: Request, from_date: str = None,
                              to_date: str = None, class_id: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        start = from_date or now_riyadh_date()
        end   = to_date   or now_riyadh_date()
        rows  = query_absences_in_range(start, end, class_id or None)
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/schedule", response_class=JSONResponse)
async def web_get_schedule(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("SELECT s.*, c.name as class_name FROM schedule s LEFT JOIN (SELECT id, name FROM students_classes) c ON s.class_id=c.id ORDER BY day_of_week, period")
        rows = [dict(r) for r in cur.fetchall()]; con.close()
        # Fallback: إذا لم يوجد join
        if not rows:
            con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
            cur.execute("SELECT * FROM schedule ORDER BY day_of_week, period")
            rows = [dict(r) for r in cur.fetchall()]; con.close()
            # أضف اسم الفصل من store
            store = load_students()
            cls_map = {c["id"]: c["name"] for c in store["list"]}
            for r in rows:
                r["class_name"] = cls_map.get(r.get("class_id", ""), r.get("class_id", ""))
        return JSONResponse({"ok": True, "items": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e), "items": []})


@router.post("/web/api/save-schedule", response_class=JSONResponse)
async def web_save_schedule_item(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        con  = get_db(); cur = con.cursor()
        cur.execute("""INSERT OR REPLACE INTO schedule
            (day_of_week, class_id, period, teacher_name)
            VALUES (?, ?, ?, ?)""",
            (int(data["day_of_week"]), data["class_id"],
             int(data["period"]), data.get("teacher_name", "")))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/tardiness-recipients", response_class=JSONResponse)
async def web_get_recipients(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        cfg  = load_config()
        recs = cfg.get("tardiness_recipients", [])
        return JSONResponse({"ok": True, "recipients": recs})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/add-tardiness-recipient", response_class=JSONResponse)
async def web_add_recipient(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        cfg  = load_config()
        recs = cfg.get("tardiness_recipients", [])
        recs.append({"name": data["name"], "phone": data["phone"],
                     "role": data.get("role", "")})
        cfg["tardiness_recipients"] = recs
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/counselor-sessions", response_class=JSONResponse)
async def web_counselor_sessions(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("SELECT * FROM counselor_sessions ORDER BY date DESC LIMIT 100")
        rows = [dict(r) for r in cur.fetchall()]; con.close()
        return JSONResponse({"ok": True, "sessions": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/add-counselor-session", response_class=JSONResponse)
async def web_add_counselor_session(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        con  = get_db(); cur = con.cursor()
        cur.execute("""INSERT INTO counselor_sessions
            (date, student_id, student_name, class_name, reason, notes, action_taken, created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (data.get("date"), data.get("student_id"), data.get("student_name"),
             data.get("class_name"), data.get("reason"), data.get("notes"),
             data.get("action_taken"), datetime.datetime.utcnow().isoformat()))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── زيارات أولياء الأمور ─────────────────────────────────────

@router.get("/web/api/parent-visits", response_class=JSONResponse)
async def web_get_parent_visits(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        date_from = request.query_params.get("from")
        date_to   = request.query_params.get("to")
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        q = "SELECT * FROM parent_visits WHERE 1=1"
        params = []
        if date_from:
            q += " AND date>=?"; params.append(date_from)
        if date_to:
            q += " AND date<=?"; params.append(date_to)
        q += " ORDER BY date DESC, visit_time DESC LIMIT 500"
        cur.execute(q, params)
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return JSONResponse({"ok": True, "visits": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/parent-visits", response_class=JSONResponse)
async def web_add_parent_visit(req: Request):
    user = _get_current_user(req)
    if not user:
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        required = ["date", "visit_time", "student_id", "student_name",
                    "class_name", "visit_reason", "received_by", "visit_result"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return JSONResponse({"ok": False, "msg": "حقول مطلوبة: " + ", ".join(missing)})
        data["created_by"] = user.get("sub", "")
        from database import insert_parent_visit
        new_id = insert_parent_visit(data)
        return JSONResponse({"ok": True, "id": new_id})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/parent-visits/{vid}", response_class=JSONResponse)
async def web_delete_parent_visit(vid: int, request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        from database import delete_parent_visit
        delete_parent_visit(vid)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/parent-visits/report", response_class=HTMLResponse)
async def web_parent_visits_report(request: Request):
    """تقرير زيارات أولياء الأمور — صفحة HTML جاهزة للطباعة."""
    user = _get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/web/login")

    date_from   = request.query_params.get("from", "")
    date_to     = request.query_params.get("to",   "")
    filter_cls  = request.query_params.get("cls",  "")
    filter_rsn  = request.query_params.get("reason", "")
    filter_rcv  = request.query_params.get("rcv",  "")

    cfg         = load_config()
    school_name = cfg.get("school_name", "المدرسة")
    logo_tag    = logo_img_tag_from_config(cfg)

    # ── جلب البيانات ──────────────────────────────────────────
    con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
    q = "SELECT * FROM parent_visits WHERE 1=1"
    params = []
    if date_from: q += " AND date>=?"; params.append(date_from)
    if date_to:   q += " AND date<=?"; params.append(date_to)
    if filter_cls: q += " AND class_name=?"; params.append(filter_cls)
    if filter_rsn: q += " AND visit_reason=?"; params.append(filter_rsn)
    if filter_rcv: q += " AND received_by=?"; params.append(filter_rcv)
    q += " ORDER BY date ASC, visit_time ASC"
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    con.close()

    # ── إحصائيات ──────────────────────────────────────────────
    total = len(rows)
    reason_counts   = {}
    rcv_counts      = {}
    result_counts   = {}
    class_counts    = {}
    for r in rows:
        reason_counts[r["visit_reason"]]  = reason_counts.get(r["visit_reason"], 0) + 1
        rcv_counts[r["received_by"]]      = rcv_counts.get(r["received_by"], 0) + 1
        result_counts[r["visit_result"]]  = result_counts.get(r["visit_result"], 0) + 1
        class_counts[r["class_name"]]     = class_counts.get(r["class_name"], 0) + 1

    def _stat_rows(d):
        return "".join(
            f'<tr><td>{k}</td><td style="text-align:center;font-weight:700">{v}</td></tr>'
            for k, v in sorted(d.items(), key=lambda x: -x[1])
        )

    # ── صفوف الجدول التفصيلي ──────────────────────────────────
    detail_rows = ""
    for i, r in enumerate(rows, 1):
        detail_rows += (
            f'<tr>'
            f'<td style="text-align:center">{i}</td>'
            f'<td style="text-align:center">{r["date"]}</td>'
            f'<td style="text-align:center">{r["visit_time"]}</td>'
            f'<td>{r["student_name"]}</td>'
            f'<td style="text-align:center">{r["class_name"]}</td>'
            f'<td>{r.get("guardian_name","")}</td>'
            f'<td>{r["visit_reason"]}</td>'
            f'<td style="text-align:center">{r["received_by"]}</td>'
            f'<td>{r["visit_result"]}</td>'
            f'<td style="font-size:11px;color:#555">{r.get("notes","")}</td>'
            f'</tr>'
        )
    if not detail_rows:
        detail_rows = '<tr><td colspan="10" style="text-align:center;color:#999;padding:20px">لا توجد زيارات في هذه الفترة</td></tr>'

    period_label = ""
    if date_from and date_to:
        period_label = f"من {date_from} إلى {date_to}"
    elif date_from:
        period_label = f"من {date_from}"
    elif date_to:
        period_label = f"حتى {date_to}"
    else:
        period_label = "كامل السجل"

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<title>تقرير زيارات أولياء الأمور — {school_name}</title>
<style>
  @page {{ size: A4; margin: 18mm 14mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; direction: rtl;
         color: #1e293b; font-size: 12px; background: #fff; }}

  /* ── رأس التقرير ── */
  .header {{ display: flex; align-items: center; justify-content: space-between;
             border-bottom: 3px solid #1565C0; padding-bottom: 10px; margin-bottom: 16px; }}
  .header-center {{ text-align: center; flex: 1; }}
  .header-center h1 {{ font-size: 18px; color: #1565C0; font-weight: 700; margin-bottom: 4px; }}
  .header-center h2 {{ font-size: 13px; color: #475569; font-weight: 400; }}
  .header-side {{ min-width: 70px; text-align: center; }}
  .meta-bar {{ display: flex; gap: 24px; background: #EFF6FF; border: 1px solid #BFDBFE;
               border-radius: 8px; padding: 8px 14px; margin-bottom: 16px;
               font-size: 11.5px; flex-wrap: wrap; }}
  .meta-bar span {{ color: #1e40af; }}
  .meta-bar strong {{ color: #1e3a5f; margin-left: 4px; }}

  /* ── بطاقات الإحصاء ── */
  .stats-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-bottom: 16px; }}
  .stat-card {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 8px;
                text-align: center; background: #f8fafc; }}
  .stat-card .val {{ font-size: 22px; font-weight: 700; color: #1565C0; line-height: 1.1; }}
  .stat-card .lbl {{ font-size: 10px; color: #64748b; margin-top: 3px; }}

  /* ── جداول الملخص ── */
  .summary-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 18px; }}
  .sum-box h3 {{ font-size: 11px; font-weight: 700; color: #1565C0;
                 padding: 5px 8px; background: #EFF6FF; border-radius: 6px 6px 0 0;
                 border: 1px solid #BFDBFE; border-bottom: none; }}
  .sum-box table {{ width: 100%; border-collapse: collapse;
                    border: 1px solid #e2e8f0; border-radius: 0 0 6px 6px; overflow: hidden; }}
  .sum-box td {{ padding: 5px 8px; border-bottom: 1px solid #f1f5f9; font-size: 11px; }}
  .sum-box tr:last-child td {{ border-bottom: none; }}
  .sum-box tr:nth-child(even) {{ background: #f8fafc; }}

  /* ── الجدول التفصيلي ── */
  .section-title {{ font-size: 13px; font-weight: 700; color: #1565C0;
                    border-right: 4px solid #1565C0; padding-right: 8px;
                    margin-bottom: 10px; }}
  table.main {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  table.main th {{ background: #1565C0; color: #fff; padding: 7px 5px;
                   text-align: center; font-weight: 600; border: 1px solid #1043a0; }}
  table.main td {{ padding: 6px 5px; border: 1px solid #e2e8f0; vertical-align: top; }}
  table.main tr:nth-child(even) {{ background: #f8fafc; }}
  table.main tr:hover {{ background: #EFF6FF; }}

  /* ── تذييل ── */
  .footer {{ margin-top: 18px; border-top: 1px solid #e2e8f0; padding-top: 8px;
             display: flex; justify-content: space-between; color: #94a3b8; font-size: 10px; }}

  /* ── طباعة ── */
  @media print {{
    body {{ font-size: 11px; }}
    .no-print {{ display: none !important; }}
    table.main {{ page-break-inside: auto; }}
    table.main tr {{ page-break-inside: avoid; }}
  }}

  /* ── شريط الطباعة (يختفي عند الطباعة) ── */
  .print-bar {{ position: fixed; top: 0; left: 0; right: 0; background: #1565C0;
               color: #fff; padding: 8px 20px; display: flex; gap: 10px;
               align-items: center; z-index: 999; box-shadow: 0 2px 8px rgba(0,0,0,.2); }}
  .print-bar button {{ padding: 6px 18px; border: none; border-radius: 6px; cursor: pointer;
                       font-size: 13px; font-family: Tahoma; font-weight: 700; }}
  .btn-print {{ background: #fff; color: #1565C0; }}
  .btn-close {{ background: rgba(255,255,255,.2); color: #fff; }}
  @media screen {{ body {{ padding-top: 48px; }} }}
</style>
</head>
<body>

<!-- شريط الطباعة -->
<div class="print-bar no-print">
  <button class="btn-print" onclick="window.print()">🖨️ طباعة / حفظ PDF</button>
  <button class="btn-close" onclick="window.close()">✕ إغلاق</button>
  <span style="margin-right:auto;font-size:12px;opacity:.8">
    يمكنك حفظ كـ PDF من خيارات الطباعة
  </span>
</div>

<!-- رأس التقرير -->
<div class="header">
  <div class="header-side"><div style="max-width:70px;max-height:70px;overflow:hidden">{logo_tag}</div></div>
  <div class="header-center">
    <h1>تقرير زيارات أولياء الأمور</h1>
    <h2>{school_name}</h2>
  </div>
  <div class="header-side" style="text-align:left;font-size:10px;color:#64748b">
    {now_riyadh_date()}
  </div>
</div>

<!-- شريط المعلومات -->
<div class="meta-bar">
  <div><strong>الفترة:</strong> <span>{period_label}</span></div>
  <div><strong>إجمالي الزيارات:</strong> <span>{total}</span></div>
  {'<div><strong>الفصل:</strong> <span>' + filter_cls + '</span></div>' if filter_cls else ''}
  {'<div><strong>سبب الزيارة:</strong> <span>' + filter_rsn + '</span></div>' if filter_rsn else ''}
  {'<div><strong>الجهة المستقبلة:</strong> <span>' + filter_rcv + '</span></div>' if filter_rcv else ''}
</div>

<!-- بطاقات الإحصاء -->
<div class="stats-grid">
  <div class="stat-card">
    <div class="val">{total}</div>
    <div class="lbl">إجمالي الزيارات</div>
  </div>
  <div class="stat-card">
    <div class="val">{len(reason_counts)}</div>
    <div class="lbl">أنواع الأسباب</div>
  </div>
  <div class="stat-card">
    <div class="val">{len(class_counts)}</div>
    <div class="lbl">فصل مشارك</div>
  </div>
  <div class="stat-card">
    <div class="val">{len(rcv_counts)}</div>
    <div class="lbl">جهة استقبال</div>
  </div>
</div>

<!-- جداول الملخص -->
<div class="summary-grid">
  <div class="sum-box">
    <h3>📋 توزيع أسباب الزيارات</h3>
    <table>{_stat_rows(reason_counts) or '<tr><td>—</td></tr>'}</table>
  </div>
  <div class="sum-box">
    <h3>🏢 الجهات المستقبلة</h3>
    <table>{_stat_rows(rcv_counts) or '<tr><td>—</td></tr>'}</table>
  </div>
  <div class="sum-box">
    <h3>✅ نتائج الزيارات</h3>
    <table>{_stat_rows(result_counts) or '<tr><td>—</td></tr>'}</table>
  </div>
</div>

<!-- الجدول التفصيلي -->
<div class="section-title">📄 سجل الزيارات التفصيلي</div>
<table class="main">
  <thead>
    <tr>
      <th style="width:30px">#</th>
      <th style="width:80px">التاريخ</th>
      <th style="width:50px">الوقت</th>
      <th style="width:110px">اسم الطالب</th>
      <th style="width:80px">الفصل</th>
      <th style="width:100px">ولي الأمر</th>
      <th style="width:100px">سبب الزيارة</th>
      <th style="width:80px">الجهة</th>
      <th style="width:110px">النتيجة</th>
      <th>ملاحظات</th>
    </tr>
  </thead>
  <tbody>{detail_rows}</tbody>
</table>

<!-- التذييل -->
<div class="footer">
  <span>نظام درب — DarbStu</span>
  <span>تاريخ الطباعة: {now_riyadh_date()}</span>
  <span>إجمالي السجلات: {total}</span>
</div>

</body>
</html>"""
    return HTMLResponse(content=html, headers={
        "Content-Security-Policy": "default-src 'self' 'unsafe-inline'; img-src * data:;"
    })


# ─── تحويلات الموجّه الطلابي ─────────────────────────────────
@router.get("/web/api/counselor-referrals", response_class=JSONResponse)
async def web_counselor_referrals(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("""SELECT * FROM counselor_referrals
                       ORDER BY created_at DESC LIMIT 500""")
        rows = [dict(r) for r in cur.fetchall()]; con.close()
        return JSONResponse({"ok": True, "referrals": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/counselor-referrals/{ref_id}", response_class=JSONResponse)
async def web_delete_referral(ref_id: int, request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("DELETE FROM counselor_referrals WHERE id=?", (ref_id,))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/refer-to-counselor", response_class=JSONResponse)
async def web_refer_to_counselor(request: Request):
    """يحوّل الطلاب المحددين للموجّه الطلابي — مرآة لـ _refer_to_counselor المكتبية."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        ref_type = (data.get("type") or data.get("ref_type") or "غياب").strip()
        students = data.get("students") or []
        if ref_type not in ("غياب", "تأخر", "هروب"):
            return JSONResponse({"ok": False, "msg": "نوع التحويل غير صحيح"})
        if not students:
            return JSONResponse({"ok": False, "msg": "لا يوجد طلاب محددون"})

        now_str  = datetime.datetime.now().isoformat()
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        month    = date_str[:7] + "%"

        con = get_db(); cur = con.cursor()
        count_new = 0; skipped = 0
        for s in students:
            sid   = str(s.get("id") or s.get("student_id") or "").strip()
            sname = (s.get("name") or s.get("student_name") or "").strip()
            sclass = (s.get("class_name") or s.get("class") or "").strip()
            cnt    = int(s.get("count") or s.get("absence_count") or 0)
            if not sid or not sname:
                continue

            if ref_type == "هروب":
                # الهارب موجود مسبقاً — نحدّث حالته إلى "مُحال"
                cur.execute("""UPDATE counselor_referrals SET status='مُحال'
                               WHERE student_id=? AND referral_type='هروب'""", (sid,))
                if cur.rowcount:
                    count_new += 1
                else:
                    skipped += 1
                continue

            # تجنّب التكرار: نفس الطالب + نفس النوع + نفس الشهر
            cur.execute("""SELECT id FROM counselor_referrals
                           WHERE student_id=? AND referral_type=? AND date LIKE ?""",
                        (sid, ref_type, month))
            if cur.fetchone():
                skipped += 1
                continue

            abs_c = cnt if ref_type == "غياب" else 0
            tard_c = cnt if ref_type == "تأخر" else 0
            cur.execute("""
                INSERT INTO counselor_referrals
                    (date, student_id, student_name, class_name, referral_type,
                     absence_count, tardiness_count, notes, referred_by, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (date_str, sid, sname, sclass, ref_type,
                  abs_c, tard_c, "", user.get("sub","الويب"), "جديد", now_str))
            count_new += 1

        con.commit(); con.close()
        return JSONResponse({"ok": True, "added": count_new, "skipped": skipped})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/counselor-profile/{student_id}", response_class=JSONResponse)
async def web_counselor_profile(student_id: str, request: Request):
    """ملف الطالب الإرشادي المجمّع: تحليل + جلسات + تحويلات."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        analysis = get_student_full_analysis(student_id)
        # تنظيف الحقول الثقيلة غير المطلوبة في الملف الإرشادي
        analysis.pop("monthly", None)
        analysis.pop("dow_count", None)

        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()

        # الجلسات الإرشادية
        cur.execute("""SELECT * FROM counselor_sessions
                       WHERE student_id=? ORDER BY date DESC""", (student_id,))
        sessions = [dict(r) for r in cur.fetchall()]

        # التحويلات
        cur.execute("""SELECT * FROM counselor_referrals
                       WHERE student_id=? ORDER BY created_at DESC""", (student_id,))
        referrals = [dict(r) for r in cur.fetchall()]

        # العقود السلوكية إن وُجدت
        contracts = []
        try:
            cur.execute("""SELECT * FROM behavioral_contracts
                           WHERE student_id=? ORDER BY date DESC""", (student_id,))
            contracts = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

        con.close()

        return JSONResponse({
            "ok": True,
            "analysis": analysis,
            "sessions": sessions,
            "referrals": referrals,
            "contracts": contracts
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── تنبيهات التأخر (مرآة لتنبيهات الغياب) ───────────────────
@router.get("/web/api/alerts-tardiness", response_class=JSONResponse)
async def web_alerts_tardiness(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        cfg = load_config()
        threshold = cfg.get("alert_tardiness_threshold", 3)
        import datetime as _dt
        month = _dt.datetime.now().strftime("%Y-%m")

        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("""
            SELECT student_id,
                   MAX(student_name) as student_name,
                   MAX(class_name)   as class_name,
                   COUNT(*)          as tardiness_count,
                   MAX(date)         as last_date
            FROM tardiness
            WHERE date LIKE ?
            GROUP BY student_id
            HAVING tardiness_count >= ?
            ORDER BY tardiness_count DESC
        """, (month + "%", threshold))
        rows = [dict(r) for r in cur.fetchall()]; con.close()

        # التحقق من المحوّلين مسبقاً هذا الشهر
        con2 = get_db(); cur2 = con2.cursor()
        cur2.execute("""SELECT student_id FROM counselor_referrals
                        WHERE referral_type='تأخر' AND date LIKE ?""",
                     (month + "%",))
        already_ref = {r[0] for r in cur2.fetchall()}
        con2.close()

        for r in rows:
            r["already_referred"] = r["student_id"] in already_ref

        return JSONResponse({"ok": True, "rows": rows, "threshold": threshold})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/results", response_class=JSONResponse)
async def web_get_results(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("SELECT * FROM student_results ORDER BY uploaded_at DESC LIMIT 500")
        rows = [dict(r) for r in cur.fetchall()]; con.close()
        return JSONResponse({"ok": True, "results": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/results", response_class=JSONResponse)
async def web_clear_results(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        clear_student_results()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/noor-export", response_class=JSONResponse)
async def web_noor_export(request: Request, date: str = None):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        import tempfile
        from fastapi.responses import FileResponse
        date_str = date or now_riyadh_date()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx",
                                          prefix="noor_web_")
        tmp.close()
        export_to_noor_excel(date_str, tmp.name)
        return FileResponse(
            tmp.name,
            filename=f"noor_{date_str}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ── تحديث /web/api/me لإرسال الاسم الكامل ────────────────────
# (نُعيد تعريفه بدون @app لأن الأصلي موجود — نستخدم middleware بدلاً)
# تُضاف name للـ me endpoint عبر الكود الأصلي — لا داعي لإعادة التعريف


# ═════════════════════════════════════════════════════════════
# APIs إضافية لدعم تبويبات الويب الكاملة
# ═════════════════════════════════════════════════════════════

@router.get("/web/api/check-whatsapp", response_class=JSONResponse)
async def web_check_whatsapp(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        ok = check_whatsapp_server_status()
        return JSONResponse({"ok": bool(ok), "msg": "متصل" if ok else "غير متصل"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})


@router.post("/web/api/add-student", response_class=JSONResponse)
async def web_add_student(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        sid   = (data.get("student_id") or "").strip()
        name  = (data.get("name") or "").strip()
        cid   = (data.get("class_id") or "").strip()
        phone = (data.get("phone") or "").strip()
        if not sid or not name or not cid:
            return JSONResponse({"ok": False, "msg": "الرقم والاسم والفصل مطلوبة"})

        store = load_students(force_reload=True)
        classes = store.get("list", [])

        # التحقق من عدم التكرار
        for c in classes:
            for s in c.get("students", []):
                if str(s.get("id")) == sid:
                    return JSONResponse({"ok": False, "msg": f"الرقم {sid} مستخدم مسبقاً"})

        # البحث عن الفصل (قد يكون class_id أو اسم الفصل)
        target = None
        for c in classes:
            if c.get("id") == cid or c.get("name") == cid:
                target = c
                break
        if not target:
            return JSONResponse({"ok": False, "msg": "الفصل غير موجود"})

        target.setdefault("students", []).append({
            "id": sid, "name": name, "phone": phone
        })

        import json as _j, os as _os
        _tmp = STUDENTS_JSON + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            _j.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
        _os.replace(_tmp, STUDENTS_JSON)

        global STUDENTS_STORE
        STUDENTS_STORE = None
        load_students(force_reload=True)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/import-students", response_class=JSONResponse)
async def web_import_students(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from fastapi import UploadFile
        import tempfile
        form = await request.form()
        upload = form.get("file")
        mode = (form.get("mode") or "generic").strip()
        if not upload:
            return JSONResponse({"ok": False, "msg": "لم يتم رفع ملف"})

        suffix = ".xlsx"
        fn = getattr(upload, "filename", "") or ""
        if fn.lower().endswith(".xls"):
            suffix = ".xls"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="stu_import_")
        content = await upload.read()
        tmp.write(content); tmp.close()

        if mode == "noor":
            result = import_students_from_excel_sheet2_format(tmp.name)
        else:
            # وضع عام — نحاول نفس دالة نور أولاً ثم نسجل الأعداد
            result = import_students_from_excel_sheet2_format(tmp.name)

        try: os.unlink(tmp.name)
        except Exception: pass

        if isinstance(result, dict) and result.get("ok"):
            global STUDENTS_STORE
            STUDENTS_STORE = None
            load_students(force_reload=True)
            return JSONResponse({
                "ok": True,
                "count": result.get("students_count") or result.get("count") or 0,
                "classes": result.get("classes_count") or 0
            })
        else:
            msg = (result or {}).get("msg", "فشل الاستيراد")
            return JSONResponse({"ok": False, "msg": msg})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/upload-results", response_class=JSONResponse)
async def web_upload_results(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        form = await request.form()
        upload = form.get("file")
        year = (form.get("year") or "").strip()
        if not upload or not year:
            return JSONResponse({"ok": False, "msg": "العام الدراسي وملف PDF مطلوبان"})

        # حفظ في موقع ثابت مشترك بين التطبيق والويب
        results_dir = os.path.join(DATA_DIR, "results")
        os.makedirs(results_dir, exist_ok=True)
        safe_name = f"results_{year}.pdf"
        dest = os.path.join(results_dir, safe_name)
        content = await upload.read()
        with open(dest, "wb") as f:
            f.write(content)

        # فهرسة الـ PDF وحفظ النتائج في DB (نفس دوال التطبيق المكتبي)
        try:
            students = parse_results_pdf(dest)
            inserted, _ = save_results_to_db(students, year)
            return JSONResponse({
                "ok": True,
                "count": len(students),
                "inserted": inserted,
                "year": year,
                "path": safe_name
            })
        except ImportError as ie:
            return JSONResponse({"ok": False, "msg": f"يلزم تثبيت pdfplumber: {ie}"})
        except Exception as pe:
            return JSONResponse({"ok": False, "msg": f"فشل تحليل PDF: {pe}"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/save-noor-config", response_class=JSONResponse)
async def web_save_noor_config(request: Request):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        import json as _j
        cfg = load_config()
        cfg["noor_auto_export"] = bool(data.get("auto_export", False))
        cfg["noor_export_time"] = str(data.get("export_time", "13:00"))
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            _j.dump(cfg, f, ensure_ascii=False, indent=2)
        invalidate_config_cache()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/class-report", response_class=JSONResponse)
async def web_class_report(request: Request, class_id: str = "", semester: str = ""):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        import datetime as _dt
        # نطاق تاريخ الفصل الدراسي
        today = _dt.date.today()
        yr = today.year
        # السنة الدراسية: إذا الشهر >= 9 → العام الحالي، وإلا العام السابق
        acad_yr = yr if today.month >= 9 else yr - 1
        sem_ranges = {
            "1": (f"{acad_yr}-09-01",    f"{acad_yr+1}-01-31"),
            "2": (f"{acad_yr+1}-02-01",  f"{acad_yr+1}-06-30"),
            "3": (f"{acad_yr+1}-05-01",  f"{acad_yr+1}-08-31"),
        }
        date_from, date_to = sem_ranges.get(semester, ("1900-01-01", "2999-12-31"))

        store = load_students(force_reload=False)
        all_classes = store.get("list", [])

        # فلترة الفصل إذا طُلب
        if class_id:
            target_classes = [c for c in all_classes if c.get("id") == class_id or c.get("name") == class_id]
            if not target_classes:
                return JSONResponse({"ok": False, "msg": "الفصل غير موجود"})
        else:
            target_classes = all_classes

        # حساب الغياب والتأخر لكل طالب من قاعدة البيانات
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        abs_rows = cur.execute(
            "SELECT student_id, COUNT(DISTINCT date) as cnt FROM absences WHERE date BETWEEN ? AND ? AND student_id NOT IN (SELECT student_id FROM transferred_students) GROUP BY student_id",
            (date_from, date_to)
        ).fetchall()
        tard_rows = cur.execute(
            "SELECT student_id, COUNT(*) as cnt FROM tardiness WHERE date BETWEEN ? AND ? AND student_id NOT IN (SELECT student_id FROM transferred_students) GROUP BY student_id",
            (date_from, date_to)
        ).fetchall()
        con.close()
        abs_map  = {str(r["student_id"]): r["cnt"] for r in abs_rows}
        tard_map = {str(r["student_id"]): r["cnt"] for r in tard_rows}

        rows = []
        total_abs = 0; total_tard = 0; total_stu = 0
        for cls in target_classes:
            cls_name = cls.get("name", "")
            for s in cls.get("students", []):
                sid = str(s.get("id"))
                a = abs_map.get(sid, 0)
                t = tard_map.get(sid, 0)
                total_abs += a; total_tard += t; total_stu += 1
                rows.append({"id": sid, "name": s.get("name",""), "class_name": cls_name, "absences": a, "tardiness": t})
        rows.sort(key=lambda r: -r["absences"])

        n = max(total_stu, 1)
        return JSONResponse({
            "ok": True,
            "class_name": target_classes[0].get("name","") if len(target_classes) == 1 else "جميع الفصول",
            "students": total_stu,
            "total_absences": total_abs,
            "total_tardiness": total_tard,
            "avg_absent_per_student": round(total_abs / n, 2),
            "rows": rows
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/grade-analysis", response_class=JSONResponse)
async def web_grade_analysis(request: Request, class_id: str = ""):
    """يُرجع آخر تحليل محفوظ — يستخدم لعرض الكاش بعد الرفع."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        cache_dir = os.path.join(DATA_DIR, "grade_analysis")
        cache_file = os.path.join(cache_dir, "last_analysis.html")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                html = f.read()
            return JSONResponse({"ok": True, "html": html, "has_data": True})
        return JSONResponse({"ok": True, "html": "", "has_data": False})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/grade-analysis-upload", response_class=JSONResponse)
async def web_grade_analysis_upload(request: Request):
    """يستقبل ملف نتائج (PDF/Excel/CSV) ويحلّله بنفس محرّك التطبيق المكتبي."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        import tempfile
        form = await request.form()
        upload = form.get("file")
        if not upload:
            return JSONResponse({"ok": False, "msg": "لم يتم رفع ملف"})

        fn = getattr(upload, "filename", "") or "results.pdf"
        ext = os.path.splitext(fn)[1].lower() or ".pdf"
        if ext not in (".pdf", ".xlsx", ".xls", ".csv"):
            return JSONResponse({"ok": False, "msg": f"صيغة غير مدعومة: {ext}"})

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="ga_")
        content = await upload.read()
        tmp.write(content); tmp.close()

        try:
            # التحليل بنفس محرّك التطبيق المكتبي
            students = _ga_parse_file(tmp.name)
            if not students:
                return JSONResponse({"ok": False, "msg": "لم يُعثر على بيانات طلاب في الملف"})

            # بناء HTML التفاعلي من النسخة المتقدمة
            html = _ga_build_html(students)

            # ملخص سريع للإحصائيات للكروت العلوية
            total_students = len(students)
            all_pcts = []
            for s in students:
                for sub in s.get("subjects", []):
                    if sub.get("max_score", 0) > 0:
                        all_pcts.append(sub["score"] / sub["max_score"] * 100)
            avg = round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0
            pass_rate = round(sum(1 for p in all_pcts if p >= 50) / len(all_pcts) * 100, 1) if all_pcts else 0

            # حفظ كاش HTML والبيانات الخام للطباعة
            cache_dir = os.path.join(DATA_DIR, "grade_analysis")
            os.makedirs(cache_dir, exist_ok=True)
            with open(os.path.join(cache_dir, "last_analysis.html"), "w", encoding="utf-8") as f:
                f.write(html)
            
            # حفظ البيانات الخام (JSON) لتمكين إعادة توليد التقارير أو الطباعة
            with open(os.path.join(cache_dir, "last_analysis.json"), "w", encoding="utf-8") as f:
                json.dump(students, f, ensure_ascii=False, indent=2)

            subjects = sorted(set(
                sub.get("subject", sub.get("name", ""))
                for s in students
                for sub in s.get("subjects", [])
                if sub.get("subject", sub.get("name", ""))
            ))

            return JSONResponse({
                "ok": True,
                "html": html,
                "students": total_students,
                "average": avg,
                "pass_rate": pass_rate,
                "subjects": subjects
            })
        except Exception as e:
            import traceback
            return JSONResponse({"ok": False, "msg": str(e), "trace": traceback.format_exc()[:500]}, status_code=500)
        finally:
            try: os.unlink(tmp.name)
            except Exception: pass
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "msg": str(e), "trace": traceback.format_exc()[:500]}, status_code=500)


@router.get("/web/api/grade-analysis-view")
async def web_grade_analysis_view(request: Request, subject: str = "الكل"):
    """يعيد توليد HTML التفاعلي مفلتراً حسب المادة من الكاش."""
    user = _get_current_user(request)
    if not user:
        return HTMLResponse("<html><body><h3>غير مصرح</h3></body></html>", status_code=401)
    try:
        cache_file = os.path.join(DATA_DIR, "grade_analysis", "last_analysis.json")
        if not os.path.exists(cache_file):
            return HTMLResponse("<html><body><h3>لم يتم إجراء أي تحليل بعد</h3></body></html>")
        with open(cache_file, "r", encoding="utf-8") as f:
            students = json.load(f)
        html = _ga_build_html(students, sel_subject=subject)
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<html><body><h3>خطأ: {str(e)}</h3></body></html>")


@router.get("/web/api/grade-analysis-print")
async def web_grade_analysis_print(request: Request, subject: str = "الكل"):
    """يولد نسخة HTML مهيئة للطباعة (A4) لآخر تحليل نتائج."""
    try:
        cache_file = os.path.join(DATA_DIR, "grade_analysis", "last_analysis.json")
        if not os.path.exists(cache_file):
            return HTMLResponse("<html><body><h3>لم يتم إجراء أي تحليل بعد</h3></body></html>")
        
        with open(cache_file, "r", encoding="utf-8") as f:
            students = json.load(f)
        
        from grade_analysis import _ga_build_print_html
        html = _ga_build_print_html(students, sel_subject=subject)
        
        # إضافة سكريبت للطباعة التلقائية
        if "</body>" in html:
            html = html.replace("</body>", "<script>window.onload = function(){ window.print(); }</script></body>")
            
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<html><body><h3>خطأ في تجهيز الطباعة: {str(e)}</h3></body></html>")


# ─── الموجّه الطلابي: نسخة مطابقة للتطبيق المكتبي ──────────
@router.get("/web/api/counselor-list", response_class=JSONResponse)
async def web_counselor_list(request: Request):
    """قائمة المحوّلين بنفس منطق _load_counselor_data المكتبية:
    - إزالة التكرار (نُبقي الأحدث لكل طالب)
    - حساب الغياب والتأخر الفعليَّين من جداول الأحداث
    - آخر إجراء من counselor_alerts
    """
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("""
            SELECT student_id, student_name, class_name,
                   referral_type, absence_count, tardiness_count,
                   date, status, notes
            FROM counselor_referrals
            ORDER BY date DESC
        """)
        referrals = [dict(r) for r in cur.fetchall()]

        seen = set(); unique = []
        for ref in referrals:
            if ref["student_id"] not in seen:
                seen.add(ref["student_id"])
                unique.append(ref)

        rows = []
        for ref in unique:
            sid = ref["student_id"]
            cur.execute("SELECT COUNT(DISTINCT date) as c FROM absences WHERE student_id=?", (sid,))
            r = cur.fetchone(); abs_c = r["c"] if r else (ref.get("absence_count") or 0)
            cur.execute("SELECT COUNT(*) as c FROM tardiness WHERE student_id=?", (sid,))
            r = cur.fetchone(); tard_c = r["c"] if r else (ref.get("tardiness_count") or 0)
            try:
                cur.execute("""SELECT type, date FROM counselor_alerts
                               WHERE student_id=? ORDER BY date DESC LIMIT 1""", (sid,))
                last = cur.fetchone()
                last_action = f"{last['type']} ({last['date']})" if last else "لا يوجد"
            except Exception:
                last_action = "لا يوجد"

            rows.append({
                "student_id":   sid,
                "student_name": ref["student_name"],
                "class_name":   ref["class_name"],
                "absences":     abs_c,
                "tardiness":    tard_c,
                "last_action":  last_action,
                "referral_type": ref["referral_type"],
                "date":         ref["date"],
                "status":       ref.get("status") or "جديد",
            })
            
        # ── إضافة تحويلات المعلمين (student_referrals) غير المغلقة ──
        cur.execute("SELECT * FROM student_referrals WHERE status != 'resolved' ORDER BY created_at DESC")
        stu_refs = [dict(r) for r in cur.fetchall()]
        status_lbl = {
            "pending": "بانتظار الوكيل",
            "with_deputy": "مع الوكيل",
            "with_counselor": "للموجّه",
        }
        for sr in stu_refs:
            st = sr["status"]
            lbl = status_lbl.get(st, st)
            action = f"{lbl} | {sr.get('teacher_name', '')}"
            rows.append({
                "student_id":   sr["student_id"],
                "student_name": sr["student_name"],
                "class_name":   sr["class_name"],
                "absences":     0,
                "tardiness":    0,
                "last_action":  action,
                "referral_type": "تحويل معلم",  # لتمييزها في القائمة
                "date":         (sr.get("ref_date") or sr.get("created_at") or "")[:10],
                "status":       st,
                "ref_id":       sr["id"],
            })
            
        con.close()
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/counselor-add-manual", response_class=JSONResponse)
async def web_counselor_add_manual(request: Request):
    """إضافة طالب يدوياً للموجّه — مرآة لـ _open_add_student_dialog المكتبية."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        sid    = (data.get("student_id") or "").strip()
        sname  = (data.get("student_name") or "").strip()
        sclass = (data.get("class_name") or "").strip()
        reason = (data.get("reason") or "غياب").strip()
        notes  = (data.get("notes") or "").strip()
        force  = bool(data.get("force", False))

        if not sid or not sname:
            return JSONResponse({"ok": False, "msg": "الطالب مطلوب"})

        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()

        # حساب الغياب/التأخر الفعلي
        cur.execute("SELECT COUNT(DISTINCT date) as c FROM absences WHERE student_id=?", (sid,))
        r = cur.fetchone(); abs_c = r["c"] if r else 0
        cur.execute("SELECT COUNT(*) as c FROM tardiness WHERE student_id=?", (sid,))
        r = cur.fetchone(); tard_c = r["c"] if r else 0

        # التحقق من التكرار هذا الشهر
        now_str  = datetime.datetime.now().isoformat()
        date_str = now_str[:10]
        month_prefix = date_str[:7]
        cur.execute("""SELECT id FROM counselor_referrals
                       WHERE student_id=? AND date LIKE ?""", (sid, month_prefix + "%"))
        existing = cur.fetchone()
        if existing and not force:
            con.close()
            return JSONResponse({"ok": False, "duplicate": True,
                                  "msg": f"الطالب {sname} موجود بالفعل في قائمة الموجّه هذا الشهر"})

        cur.execute("""
            INSERT INTO counselor_referrals
                (date, student_id, student_name, class_name, referral_type,
                 absence_count, tardiness_count, notes, referred_by, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (date_str, sid, sname, sclass, reason,
              abs_c, tard_c, notes, "إضافة يدوية - ويب", "جديد", now_str))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.delete("/web/api/counselor-delete-student/{student_id}", response_class=JSONResponse)
async def web_counselor_delete_student(student_id: str, request: Request):
    """حذف الطالب من قائمة الموجّه (كل سجلاته في counselor_referrals)."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); cur = con.cursor()
        cur.execute("DELETE FROM counselor_referrals WHERE student_id=?", (student_id,))
        affected = cur.rowcount
        con.commit(); con.close()
        return JSONResponse({"ok": True, "deleted": affected})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/counselor-history/{student_id}", response_class=JSONResponse)
async def web_counselor_history(student_id: str, request: Request):
    """السجل الإرشادي الكامل لطالب: جلسات + تنبيهات + عقود."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        cur.execute("SELECT * FROM counselor_sessions WHERE student_id=? ORDER BY date DESC",
                    (student_id,))
        sessions = [dict(r) for r in cur.fetchall()]
        try:
            cur.execute("SELECT * FROM counselor_alerts WHERE student_id=? ORDER BY date DESC",
                        (student_id,))
            alerts = [dict(r) for r in cur.fetchall()]
        except Exception:
            alerts = []
        try:
            cur.execute("SELECT * FROM behavioral_contracts WHERE student_id=? ORDER BY date DESC",
                        (student_id,))
            contracts = [dict(r) for r in cur.fetchall()]
        except Exception:
            contracts = []
        con.close()
        return JSONResponse({
            "ok": True,
            "sessions": sessions,
            "alerts": alerts,
            "contracts": contracts
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/counselor-alert", response_class=JSONResponse)
async def web_counselor_add_alert(request: Request):
    """إضافة تنبيه/استدعاء جديد للطالب — مرآة لزر التنبيهات المكتبي."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        sid    = (data.get("student_id") or "").strip()
        sname  = (data.get("student_name") or "").strip()
        atype  = (data.get("type") or "تنبيه").strip()
        method = (data.get("method") or "اتصال هاتفي").strip()
        status = (data.get("status") or "تم").strip()
        if not sid:
            return JSONResponse({"ok": False, "msg": "الطالب مطلوب"})

        now_str = datetime.datetime.now().isoformat()
        date_str = now_str[:10]
        con = get_db(); cur = con.cursor()
        cur.execute("""INSERT INTO counselor_alerts
            (date, student_id, student_name, type, method, status, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (date_str, sid, sname, atype, method, status, now_str))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/counselor-contract", response_class=JSONResponse)
async def web_counselor_add_contract(request: Request):
    """إضافة عقد سلوكي للطالب."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        sid    = (data.get("student_id") or "").strip()
        sname  = (data.get("student_name") or "").strip()
        sclass = (data.get("class_name") or "").strip()
        subject     = (data.get("subject") or "").strip()
        period_from = (data.get("period_from") or "").strip()
        period_to   = (data.get("period_to") or "").strip()
        notes       = (data.get("notes") or "").strip()
        if not sid:
            return JSONResponse({"ok": False, "msg": "الطالب مطلوب"})

        now_str = datetime.datetime.now().isoformat()
        date_str = now_str[:10]
        con = get_db(); cur = con.cursor()
        cur.execute("""INSERT INTO behavioral_contracts
            (date, student_id, student_name, class_name, subject, period_from, period_to, notes, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (date_str, sid, sname, sclass, subject, period_from, period_to, notes, now_str))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── البنود الافتراضية للجلسة الإرشادية (مطابقة للتطبيق المكتبي) ──
_SESSION_DEFAULT_GOALS = [
    "الحد من غياب الطالب المتكرر بلا عذر",
    "أن يدرك الطالب أضرار الغياب على تحصيله الدراسي",
    "أن ينظم الطالب وقته ويجتهد في دراسته",
]
_SESSION_DEFAULT_DISCUSSIONS = [
    "حوار ونقاش وعصف ذهني مع الطالب حول أضرار الغياب",
    "معرفة أسباب الغياب ومساعدة الطالب للتغلب عليها",
    "استخدام أسلوب الضبط الذاتي وشرحه للطالب للحد من الغياب بلا عذر",
]
_SESSION_DEFAULT_RECS = [
    "التزام الطالب بالحضور للمدرسة وعدم غيابه إلا بعذر مقبول",
    "التزام الطالب بتنظيم الوقت والضبط الذاتي",
    "التأكيد على إدارة المدرسة بعدم التساهل في تطبيق لائحة المواظبة في جميع المراحل، وتكثيف التوعية الإعلامية لنشر ثقافة الانتباط، واحترام أوقات الدراسة، وجعل المدرسة بيئة جاذبة للطالب",
]


@router.get("/web/api/counselor-session-defaults", response_class=JSONResponse)
async def web_counselor_session_defaults(request: Request):
    """يُرجع البنود الافتراضية للجلسة + أرقام جوال المدير والوكيل."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    cfg = load_config()
    c1 = (cfg.get("counselor1_name", "") or "").strip()
    c2 = (cfg.get("counselor2_name", "") or "").strip()
    active = (cfg.get("active_counselor", "1") or "1").strip()
    # الاسم الافتراضي بناءً على الموجّه النشط
    if active == "2" and c2:
        default_name = c2
    else:
        default_name = c1 or c2 or "الموجّه الطلابي"
    return JSONResponse({
        "ok": True,
        "goals": _SESSION_DEFAULT_GOALS,
        "discussions": _SESSION_DEFAULT_DISCUSSIONS,
        "recommendations": _SESSION_DEFAULT_RECS,
        "counselor_name": default_name,
        "counselor1_name": c1,
        "counselor2_name": c2,
        "active_counselor": active,
        "school_name": cfg.get("school_name", "المدرسة"),
        "principal_phone": bool(cfg.get("principal_phone", "").strip()),
        "deputy_phone": bool(cfg.get("alert_admin_phone", "").strip()),
    })


def _persist_session(sid, sname, sclass, title, goals, discs, recs, notes_extra):
    """يحفظ الجلسة في DB — مرآة لـ _save_to_db المكتبية."""
    notes_db = ("الأهداف: " + "; ".join(goals) +
                "\nالمداولات: " + "; ".join(discs) +
                "\nالتوصيات: " + "; ".join(recs))
    if notes_extra:
        notes_db += "\nملاحظات: " + notes_extra
    action = "; ".join(recs) if recs else "تنبيه الطالب"
    date_db = datetime.datetime.now().strftime("%Y-%m-%d")
    con = get_db(); cur = con.cursor()
    cur.execute("""INSERT INTO counselor_sessions
        (date, student_id, student_name, class_name, reason, notes, action_taken, created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (date_db, sid, sname, sclass, title, notes_db, action,
         datetime.datetime.now().isoformat()))
    con.commit(); con.close()


@router.post("/web/api/counselor-session-full", response_class=JSONResponse)
async def web_counselor_session_full(request: Request):
    """يحفظ جلسة إرشادية كاملة + اختياري إرسال للمدير/الوكيل عبر واتساب.
    action: 'save' | 'send_principal' | 'send_deputy' | 'send_both'
    """
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        action = (data.get("action") or "save").strip()
        sid    = (data.get("student_id") or "").strip()
        sname  = (data.get("student_name") or "").strip()
        sclass = (data.get("class_name") or "").strip()
        title  = (data.get("title") or "الانضباط المدرسي").strip()
        goals  = [g for g in (data.get("goals") or []) if g and g.strip()]
        discs  = [d for d in (data.get("discussions") or []) if d and d.strip()]
        recs   = [r for r in (data.get("recommendations") or []) if r and r.strip()]
        notes_extra = (data.get("notes") or "").strip()
        date_str = (data.get("date") or "").strip() or datetime.datetime.now().strftime("%Y/%m/%d")

        if not sid or not sname:
            return JSONResponse({"ok": False, "msg": "بيانات الطالب مطلوبة"})

        cfg = load_config()
        # السماح للواجهة باختيار الموجّه (1 أو 2) أو إرسال الاسم مباشرة
        counselor_choice = (data.get("counselor_choice") or "").strip()
        counselor_name_in = (data.get("counselor_name") or "").strip()
        c1 = (cfg.get("counselor1_name", "") or "").strip()
        c2 = (cfg.get("counselor2_name", "") or "").strip()
        if counselor_name_in:
            counselor_name = counselor_name_in
        elif counselor_choice == "2":
            counselor_name = c2 or c1 or "الموجّه الطلابي"
        elif counselor_choice == "1":
            counselor_name = c1 or c2 or "الموجّه الطلابي"
        else:
            counselor_name = c1 or c2 or "الموجّه الطلابي"
        principal_phone = cfg.get("principal_phone", "").strip()
        deputy_phone    = cfg.get("alert_admin_phone", "").strip()

        # حفظ في DB
        _persist_session(sid, sname, sclass, title, goals, discs, recs, notes_extra)

        if action == "save":
            return JSONResponse({"ok": True, "saved": True})

        # بناء بيانات الجلسة لـ PDF
        session_data = {
            "student_name":    sname,
            "class_name":      sclass,
            "date":            date_str,
            "title":           title,
            "goals":           goals,
            "discussions":     discs,
            "recommendations": recs,
            "notes":           notes_extra,
            "counselor_name":  counselor_name,
        }

        try:
            pdf_bytes = generate_session_pdf(session_data)
        except Exception as pe:
            return JSONResponse({"ok": False, "msg": f"تعذّر إنشاء PDF: {pe}"})

        fname = f"جلسة_ارشادية_{sname}_{date_str.replace('/','-')}.pdf"

        targets = []
        if action in ("send_principal", "send_both"):
            if not principal_phone:
                return JSONResponse({"ok": False, "msg": "لم يُسجَّل جوال مدير المدرسة في الإعدادات"})
            targets.append((principal_phone, "مدير المدرسة"))
        if action in ("send_deputy", "send_both"):
            if not deputy_phone:
                return JSONResponse({"ok": False, "msg": "لم يُسجَّل جوال وكيل المدرسة في الإعدادات"})
            targets.append((deputy_phone, "وكيل المدرسة"))

        results = []
        sent_ok = 0
        for phone, role in targets:
            caption = f"📋 جلسة إرشادية — {sname} — {sclass} | {role}"
            ok, res = send_whatsapp_pdf(phone, pdf_bytes, fname, caption)
            results.append({"role": role, "ok": bool(ok), "msg": str(res)[:200]})
            if ok: sent_ok += 1

        all_ok = sent_ok > 0 or not targets
        fail_msgs = [r["msg"] for r in results if not r["ok"]]
        return JSONResponse({
            "ok": all_ok,
            "saved": True,
            "sent": sent_ok,
            "total": len(targets),
            "results": results,
            "msg": "" if all_ok else (fail_msgs[0] if fail_msgs else "فشل الإرسال")
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/counselor-session-pdf")
async def web_counselor_session_pdf(request: Request):
    """يُرجع PDF للجلسة الإرشادية للتحميل/الطباعة."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from fastapi.responses import Response
        data = await request.json()
        cfg = load_config()
        counselor_choice = (data.get("counselor_choice") or "").strip()
        counselor_name_in = (data.get("counselor_name") or "").strip()
        c1 = (cfg.get("counselor1_name", "") or "").strip()
        c2 = (cfg.get("counselor2_name", "") or "").strip()
        if counselor_name_in:
            counselor_name = counselor_name_in
        elif counselor_choice == "2":
            counselor_name = c2 or c1 or "الموجّه الطلابي"
        elif counselor_choice == "1":
            counselor_name = c1 or c2 or "الموجّه الطلابي"
        else:
            counselor_name = c1 or c2 or "الموجّه الطلابي"

        session_data = {
            "student_name":    (data.get("student_name") or "").strip(),
            "class_name":      (data.get("class_name") or "").strip(),
            "date":             (data.get("date") or datetime.datetime.now().strftime("%Y/%m/%d")),
            "title":            (data.get("title") or "الانضباط المدرسي").strip(),
            "goals":            [g for g in (data.get("goals") or []) if g and g.strip()],
            "discussions":      [d for d in (data.get("discussions") or []) if d and d.strip()],
            "recommendations":  [r for r in (data.get("recommendations") or []) if r and r.strip()],
            "notes":            (data.get("notes") or "").strip(),
            "counselor_name":   counselor_name,
        }
        pdf_bytes = generate_session_pdf(session_data)
        sname = session_data["student_name"] or "طالب"
        fname = f"جلسة_ارشادية_{sname}.pdf"
        # رؤوس HTTP لا تقبل إلا latin-1، فنستخدم RFC 5987 للأسماء العربية
        from urllib.parse import quote
        fname_ascii = "session.pdf"
        fname_enc = quote(fname, safe="")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=\"{fname_ascii}\"; filename*=UTF-8''{fname_enc}"}
        )
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/counselor-contract-full", response_class=JSONResponse)
async def web_counselor_contract_full(request: Request):
    """يحفظ عقداً سلوكياً كاملاً + اختياري إرسال للمدير/الوكيل عبر واتساب.
    action: 'save' | 'send_principal' | 'send_deputy' | 'send_both'
    """
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        action = (data.get("action") or "save").strip()
        sid    = (data.get("student_id") or "").strip()
        sname  = (data.get("student_name") or "").strip()
        sclass = (data.get("class_name") or "").strip()
        subject     = (data.get("subject") or "الانضباط السلوكي").strip()
        period_from = (data.get("period_from") or "").strip()
        period_to   = (data.get("period_to") or "").strip()
        notes       = (data.get("notes") or "").strip()
        date_str    = (data.get("date") or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d")

        if not sid or not sname:
            return JSONResponse({"ok": False, "msg": "بيانات الطالب مطلوبة"})

        cfg = load_config()
        school = cfg.get("school_name", "المدرسة")
        counselor_choice = (data.get("counselor_choice") or "").strip()
        counselor_name_in = (data.get("counselor_name") or "").strip()
        c1 = (cfg.get("counselor1_name", "") or "").strip()
        c2 = (cfg.get("counselor2_name", "") or "").strip()
        if counselor_name_in:
            counselor_name = counselor_name_in
        elif counselor_choice == "2":
            counselor_name = c2 or c1 or "الموجّه الطلابي"
        elif counselor_choice == "1":
            counselor_name = c1 or c2 or "الموجّه الطلابي"
        else:
            counselor_name = c1 or c2 or "الموجّه الطلابي"
        principal_phone = cfg.get("principal_phone", "").strip()
        deputy_phone    = cfg.get("alert_admin_phone", "").strip()

        # حفظ في DB
        con = get_db(); cur = con.cursor()
        cur.execute("""INSERT INTO behavioral_contracts
            (date, student_id, student_name, class_name, subject, period_from, period_to, notes, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (date_str, sid, sname, sclass, subject, period_from, period_to, notes,
             datetime.datetime.now().isoformat()))
        con.commit(); con.close()

        if action == "save":
            return JSONResponse({"ok": True, "saved": True})

        contract_data = {
            "date":           date_str,
            "student_id":     sid,
            "student_name":   sname,
            "class_name":     sclass,
            "subject":        subject,
            "period_from":    period_from,
            "period_to":      period_to,
            "notes":          notes,
            "school_name":    school,
            "counselor_name": counselor_name,
        }
        try:
            pdf_bytes = generate_behavioral_contract_pdf(contract_data)
        except Exception as pe:
            return JSONResponse({"ok": False, "msg": f"تعذّر إنشاء PDF: {pe}"})

        fname = f"عقد_سلوكي_{sname}_{date_str}.pdf"

        targets = []
        if action in ("send_principal", "send_both"):
            if not principal_phone:
                return JSONResponse({"ok": False, "msg": "لم يُسجَّل جوال مدير المدرسة في الإعدادات"})
            targets.append((principal_phone, "مدير المدرسة"))
        if action in ("send_deputy", "send_both"):
            if not deputy_phone:
                return JSONResponse({"ok": False, "msg": "لم يُسجَّل جوال وكيل المدرسة في الإعدادات"})
            targets.append((deputy_phone, "وكيل المدرسة"))

        results = []
        sent_ok = 0
        for phone, role in targets:
            caption = f"📋 عقد سلوكي — {sname} — {sclass} | {role}"
            ok, res = send_whatsapp_pdf(phone, pdf_bytes, fname, caption)
            results.append({"role": role, "ok": bool(ok), "msg": str(res)[:200]})
            if ok: sent_ok += 1

        return JSONResponse({
            "ok": sent_ok > 0 or not targets,
            "saved": True,
            "sent": sent_ok,
            "total": len(targets),
            "results": results
        })
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/counselor-contract-pdf")
async def web_counselor_contract_pdf(request: Request):
    """يُرجع PDF للعقد السلوكي للتحميل/الطباعة."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from fastapi.responses import Response
        data = await request.json()
        cfg = load_config()
        counselor_choice = (data.get("counselor_choice") or "").strip()
        counselor_name_in = (data.get("counselor_name") or "").strip()
        c1 = (cfg.get("counselor1_name", "") or "").strip()
        c2 = (cfg.get("counselor2_name", "") or "").strip()
        if counselor_name_in:
            counselor_name_final = counselor_name_in
        elif counselor_choice == "2":
            counselor_name_final = c2 or c1 or "الموجّه الطلابي"
        elif counselor_choice == "1":
            counselor_name_final = c1 or c2 or "الموجّه الطلابي"
        else:
            counselor_name_final = c1 or c2 or "الموجّه الطلابي"
        contract_data = {
            "date":          (data.get("date") or datetime.datetime.now().strftime("%Y-%m-%d")),
            "student_id":    (data.get("student_id") or "").strip(),
            "student_name":  (data.get("student_name") or "").strip(),
            "class_name":    (data.get("class_name") or "").strip(),
            "subject":       (data.get("subject") or "الانضباط السلوكي").strip(),
            "period_from":   (data.get("period_from") or "").strip(),
            "period_to":     (data.get("period_to") or "").strip(),
            "notes":         (data.get("notes") or "").strip(),
            "school_name":   cfg.get("school_name", "المدرسة"),
            "counselor_name": counselor_name_final,
        }
        pdf_bytes = generate_behavioral_contract_pdf(contract_data)
        sname = contract_data["student_name"] or "طالب"
        fname = f"عقد_سلوكي_{sname}.pdf"
        from urllib.parse import quote
        fname_ascii = "contract.pdf"
        fname_enc = quote(fname, safe="")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=\"{fname_ascii}\"; filename*=UTF-8''{fname_enc}"}
        )
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ==================== المسارات الجديدة (التحويلات ونماذج المعلم) ====================

@router.post("/web/api/create-referral", response_class=JSONResponse)
async def web_create_referral(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        data["teacher_name"] = user.get("full_name", user.get("username", ""))
        data["teacher_username"] = user.get("username", "")
        data["ref_date"] = now_riyadh_date()
        
        # التوافقية مع الـ Desktop app
        if "action1" in data and "teacher_action1" not in data:
            data["teacher_action1"] = data.pop("action1")
        if "action2" in data and "teacher_action2" not in data:
            data["teacher_action2"] = data.pop("action2")
            
        ref_id = create_student_referral(data)
        
        # Notify Deputy
        try:
            from database import get_deputy_phones
            phones = get_deputy_phones()
            cfg = load_config()
            if not phones and cfg.get("principal_phone"):
                phones = [cfg.get("principal_phone")]
            
            msg = (
                f"🔔 *تنبيه: تحويل طالب جديد*\n\n"
                f"الطالب: {data.get('student_name', '')}\n"
                f"الفصل: {data.get('class_name', '')}\n"
                f"المعلم: {data['teacher_name']}\n"
                f"التاريخ: {now_riyadh_date()}\n"
                f"رقم التحويل: {ref_id}\n\n"
                f"يرجى مراجعة نظام درب لاتخاذ الإجراء المناسب."
            )
            for ph in phones:
                try: send_whatsapp_message(ph, msg)
                except: pass
        except Exception:
            pass
            
        return JSONResponse({"ok": True, "ref_id": ref_id})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/referral-history", response_class=JSONResponse)
async def web_referral_history(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        rows = get_referrals_for_teacher(user.get("username", ""))
        return JSONResponse({"ok": True, "referrals": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/all-referrals", response_class=JSONResponse)
async def web_all_referrals(request: Request, status: str = None):
    user = _get_current_user(request)
    if not user or user.get("role") not in ["admin", "deputy", "supervisor", "counselor"]:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        rows = get_all_referrals(status)
        return JSONResponse({"ok": True, "referrals": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/referral/{ref_id}", response_class=JSONResponse)
async def web_get_referral(request: Request, ref_id: int):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        row = get_referral_by_id(ref_id)
        return JSONResponse({"ok": True, "referral": row})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/update-referral/{ref_id}", response_class=JSONResponse)
async def web_update_referral(request: Request, ref_id: int):
    user = _get_current_user(request)
    if not user or user.get("role") not in ["admin", "deputy", "supervisor"]:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        data["deputy_name"] = user.get("full_name", user.get("username", ""))
        data["deputy_date"] = now_riyadh_date()
        if data.get("refer_to_counselor"):
            data["status"] = "with_counselor"
            data["deputy_referred_date"] = now_riyadh_date()
            # Notify counselor
            try:
                from database import get_counselor_phones
                c_phones = get_counselor_phones()
                msg = f"🧠 *تحويل جديد للموجّه*\n\nالتحويل رقم: {ref_id}\nيرجى مراجعة نظام درب."
                for p in c_phones:
                    try: send_whatsapp_message(p, msg)
                    except: pass
            except: pass
        else:
            data["status"] = "with_deputy"
        update_referral_deputy(ref_id, data)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/close-referral/{ref_id}", response_class=JSONResponse)
async def web_close_referral(request: Request, ref_id: int):
    user = _get_current_user(request)
    if not user or user.get("role") not in ["admin", "deputy", "supervisor"]:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        close_referral(ref_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/update-counselor-referral/{ref_id}", response_class=JSONResponse)
async def web_update_counselor_referral(request: Request, ref_id: int):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        close_it = bool(data.get("close_it", False))
        
        # We enforce "resolved" or "with_counselor"
        data["status"] = "resolved" if close_it else "with_counselor"
        
        from database import update_referral_counselor, close_referral
        update_referral_counselor(ref_id, data)
        if close_it:
            close_referral(ref_id)
            
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/generate-teacher-form")
async def web_generate_teacher_form(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from fastapi.responses import Response
        data = await request.json()
        user_full_name = user.get("full_name") or user.get("username", "معلم")
        if not data.get("executor_name"):
            data["executor_name"] = user_full_name
        data["teacher_name"] = data["executor_name"]
        if not data.get("principal_name"):
            data["principal_name"] = "حسن محمد عبيري"

        # معالجة الشواهد كـ Base64
        import base64, tempfile
        temp_files = []
        for key_b64, key_path in [("evidence_img_b64", "evidence_img"), ("img1_b64", "img1"), ("img2_b64", "img2")]:
            if data.get(key_b64):
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tmp.write(base64.b64decode(data[key_b64]))
                    tmp.close()
                    data[key_path] = tmp.name
                    temp_files.append(tmp.name)
                except Exception: pass

        if data.get("form_type") == "lesson":
            pdf_bytes = generate_lesson_pdf(data)
        else:
            pdf_bytes = generate_program_pdf(data)
            
        for tf in temp_files:
            try: os.unlink(tf)
            except Exception: pass
            
        fname = f"نموذج_معلم_({data.get('form_type')}).pdf"
        from urllib.parse import quote
        fname_enc = quote(fname, safe="")
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename*=UTF-8''{fname_enc}"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── CIRCULARS API ───────────────────────────────────────────────

@router.get("/web/api/circulars/list", response_class=JSONResponse)
async def web_list_circulars(request: Request):
    try:
        user = _get_current_user(request)
        if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
        rows = get_circulars(username=user["sub"], role=user["role"])
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/circulars/mark-read", response_class=JSONResponse)
async def web_mark_read(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    try:
        data = await req.json()
        mark_circular_as_read(int(data["id"]), user["sub"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/circulars/unread-count", response_class=JSONResponse)
async def web_unread_count(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"error": "غير مصرح"}, status_code=401)
    count = get_unread_circulars_count(user["sub"], user["role"])
    return JSONResponse({"ok": True, "count": count})

# ─── تقارير المعلمين ──────────────────────────────────────────────

@router.post("/web/api/teacher-reports/submit", response_class=JSONResponse)
async def web_submit_teacher_report(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from database import save_teacher_report
        import base64, tempfile
        data = await request.json()
        user_full_name = user.get("full_name") or user.get("username", "معلم")
        if not data.get("executor_name"):
            data["executor_name"] = user_full_name
        data["teacher_name"] = data["executor_name"]
        if not data.get("principal_name"):
            data["principal_name"] = "حسن محمد عبيري"

        temp_files = []
        for key_b64, key_path in [("evidence_img_b64","evidence_img"),("img1_b64","img1"),("img2_b64","img2")]:
            if data.get(key_b64):
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tmp.write(base64.b64decode(data[key_b64])); tmp.close()
                    data[key_path] = tmp.name; temp_files.append(tmp.name)
                except Exception: pass

        if data.get("form_type") == "lesson":
            pdf_bytes = generate_lesson_pdf(data)
            title = f"تحضير درس — {data.get('subject','')} — {data.get('date','')}"
        else:
            pdf_bytes = generate_program_pdf(data)
            title = f"تقرير تنفيذ — {data.get('executor','المنفذ')} — {data.get('date','')}"

        for tf in temp_files:
            try: os.unlink(tf)
            except Exception: pass

        save_teacher_report(
            form_type      = data.get("form_type","lesson"),
            title          = title,
            submitted_by   = user["sub"],
            submitted_name = user_full_name,
            pdf_data       = pdf_bytes
        )
        return JSONResponse({"ok": True, "msg": "تم إرسال التقرير للإدارة"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/teacher-reports", response_class=JSONResponse)
async def web_get_teacher_reports(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin","deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from database import get_teacher_reports
        return JSONResponse({"ok": True, "reports": get_teacher_reports()})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/teacher-reports/unread-count", response_class=JSONResponse)
async def web_teacher_reports_unread(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "count": 0})
    if user["role"] not in ("admin","deputy"): return JSONResponse({"ok": True, "count": 0})
    try:
        from database import get_unread_teacher_reports_count
        return JSONResponse({"ok": True, "count": get_unread_teacher_reports_count()})
    except Exception:
        return JSONResponse({"ok": True, "count": 0})

@router.get("/web/api/teacher-reports/{report_id}/pdf")
async def web_teacher_report_pdf(report_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin","deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from database import get_teacher_report_pdf
        from fastapi.responses import Response
        pdf = get_teacher_report_pdf(report_id)
        if not pdf: return JSONResponse({"ok": False, "msg": "لم يُعثر على التقرير"}, status_code=404)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=report_{report_id}.pdf"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/teacher-reports/{report_id}/read", response_class=JSONResponse)
async def web_mark_teacher_report(report_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin","deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from database import mark_teacher_report_read
        mark_teacher_report_read(report_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/teacher-reports/{report_id}", response_class=JSONResponse)
async def web_delete_teacher_report(report_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin","deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from database import delete_teacher_report
        delete_teacher_report(report_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/circulars/create", response_class=JSONResponse)
async def web_create_circular(request: Request, title: str = Form(...), content: str = Form(""), target_role: str = Form("all"), file: UploadFile = File(None)):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        fpath = None
        if file and file.filename:
            os.makedirs(os.path.join(DATA_DIR, "attachments", "circulars"), exist_ok=True)
            fpath = os.path.join("attachments", "circulars", f"{int(datetime.datetime.now().timestamp())}_{file.filename}")
            with open(os.path.join(DATA_DIR, fpath), "wb") as b:
                import shutil
                shutil.copyfileobj(file.file, b)
        
        from database import create_circular
        create_circular(title, content, target_role, fpath)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/circulars/delete/{id}", response_class=JSONResponse)
async def web_delete_circular(id: int, request: Request):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        from database import delete_circular
        delete_circular(id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/send-teacher-form", response_class=JSONResponse)
async def web_send_teacher_form(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        user_full_name = user.get("full_name") or user.get("username", "معلم")
        if not data.get("executor_name"):
            data["executor_name"] = user_full_name
        data["teacher_name"] = data["executor_name"]
        if not data.get("principal_name"):
            data["principal_name"] = "حسن محمد عبيري"

        # معالجة الشواهد كـ Base64
        import base64, tempfile
        temp_files = []
        for key_b64, key_path in [("evidence_img_b64", "evidence_img"), ("img1_b64", "img1"), ("img2_b64", "img2")]:
            if data.get(key_b64):
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tmp.write(base64.b64decode(data[key_b64]))
                    tmp.close()
                    data[key_path] = tmp.name
                    temp_files.append(tmp.name)
                except Exception: pass

        if data.get("form_type") == "lesson":
            pdf_bytes = generate_lesson_pdf(data)
            caption = f"📘 نموذج تحضير درس\nالمنفذ: {data['executor_name']}\nالمادة: {data.get('subject','')}\nالتاريخ: {data.get('date','')}"
        else:
            pdf_bytes = generate_program_pdf(data)
            caption = f"📊 تقرير تنفيذ برنامج\nالمنفذ: {data['executor_name']}\nالتاريخ: {data.get('date','')}"
            
        for tf in temp_files:
            try: os.unlink(tf)
            except Exception: pass
            
        cfg = load_config()
        principal_phone = cfg.get("principal_phone", "").strip()
        if not principal_phone:
            return JSONResponse({"ok": False, "msg": "لم يُسجّل جوال مدير المدرسة في الإعدادات"})
            
        fname = f"form_{data.get('form_type')}.pdf"
        ok, res = send_whatsapp_pdf(principal_phone, pdf_bytes, fname, caption)
        if ok:
            return JSONResponse({"ok": True, "msg": "تم الإرسال لمدير المدرسة بنجاح"})
        else:
            return JSONResponse({"ok": False, "msg": "فشل إرسال رسالة الواتساب"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

# ─── REWARDS API ────────────────────────────────────────────────

@router.get("/web/api/rewards/perfect-attendance", response_class=JSONResponse)
async def api_perfect_attendance(request: Request, start: str, end: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from alerts_service import get_perfect_attendance_students
        students = get_perfect_attendance_students(start, end)
        return JSONResponse({"ok": True, "students": students})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/rewards/send", response_class=JSONResponse)
async def api_run_rewards(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False, "msg": "غير مصرح للمدير فقط"}, status_code=401)
    try:
        from alerts_service import run_weekly_rewards
        # تشغيل في خلفية (أو بشكل متزامن للويب لسهولة المتابعة)
        res = run_weekly_rewards()
        return JSONResponse({"ok": True, "results": res})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/rewards/settings", response_class=JSONResponse)
async def api_get_reward_settings(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    cfg = load_config()
    return JSONResponse({
        "ok": True,
        "enabled": cfg.get("weekly_reward_enabled", False),
        "day":     cfg.get("weekly_reward_day", 4),
        "hour":    cfg.get("weekly_reward_hour", 14),
        "minute":  cfg.get("weekly_reward_minute", 0),
        "template": cfg.get("weekly_reward_template", "")
    })

@router.post("/web/api/rewards/save-settings", response_class=JSONResponse)
async def api_save_reward_settings(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        cfg = load_config()
        cfg["weekly_reward_enabled"] = bool(data.get("enabled"))
        cfg["weekly_reward_day"]     = int(data.get("day", 4))
        cfg["weekly_reward_hour"]    = int(data.get("hour", 14))
        cfg["weekly_reward_minute"]  = int(data.get("minute", 0))
        cfg["weekly_reward_template"] = data.get("template", "").strip()
        
        from config_manager import save_config
        save_config(cfg)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── POINTS & LEADERBOARD API ────────────────────────────────────

@router.get("/web/api/leaderboard", response_class=JSONResponse)
async def api_get_leaderboard(request: Request, limit: int = 20):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    from database import get_points_leaderboard
    rows = get_points_leaderboard(limit)
    return JSONResponse({"ok": True, "rows": rows})


@router.get("/web/api/teacher-balance", response_class=JSONResponse)
async def api_get_teacher_balance(request: Request, username: str, month: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        from database import get_teacher_points_balance
        used = get_teacher_points_balance(username, month)
        return JSONResponse({"ok": True, "balance": used})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})





@router.get("/web/api/portal-link/{student_id}", response_class=JSONResponse)
async def api_get_portal_link(request: Request, student_id: str):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    from database import get_or_create_portal_token
    token = get_or_create_portal_token(student_id)
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse({"ok": True, "link": f"{base_url}/p/{token}"})


@router.post("/web/api/send-portal-link", response_class=JSONResponse)
async def api_send_portal_link(request: Request):
    """يولّد رابط بوابة ولي الأمر لطالب واحد ويرسله عبر الواتساب."""
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        body = await request.json()
        student_id   = str(body.get("student_id", "")).strip()
        student_name = str(body.get("student_name", "")).strip()
        phone        = str(body.get("phone", "")).strip()

        if not phone:
            return JSONResponse({"ok": False, "msg": "لا يوجد رقم جوال"})

        from database import get_or_create_portal_token
        from whatsapp_service import send_whatsapp_message
        from constants import CLOUDFLARE_DOMAIN

        token    = get_or_create_portal_token(student_id)
        base_url = f"https://{CLOUDFLARE_DOMAIN}"
        link     = f"{base_url}/p/{token}"

        msg = (
            f"ولي أمر الطالب: {student_name}\n\n"
            f"يسعدنا إطلاعكم على رابط بوابة المتابعة المدرسية الخاص بنجلكم،\n"
            f"يمكنكم من خلاله الاطلاع على الغياب والتأخر والإجراءات المتخذة.\n\n"
            f"🔗 رابط المتابعة:\n{link}\n\n"
            f"الرابط خاص بنجلكم ولا يُشارَك مع أحد."
        )
        ok, status = send_whatsapp_message(phone, msg)
        return JSONResponse({"ok": ok, "msg": status})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── PARENT PORTAL (SNAP-VIEW) ───────────────────────────────────

@router.get("/p/{token}", response_class=HTMLResponse)
async def web_parent_portal(token: str):
    from database import (get_student_id_by_portal_token, get_student_total_points,
                          get_active_stories)
    from alerts_service import get_student_full_analysis
    student_id = get_student_id_by_portal_token(token)
    if not student_id:
        return HTMLResponse("<h1>404 - الرابط غير صالح</h1><p>عذراً، هذا الرابط غير موجود أو تم إبطاله.</p>", status_code=404)
    
    analysis = get_student_full_analysis(student_id)
    points = get_student_total_points(student_id)
    stories = get_active_stories()
    cfg = load_config()
    school = cfg.get("school_name", "مدرسة درب")
    
    # بناء قسم قصص المدرسة (Carousel)
    stories_html = ""
    if stories:
        slides = ""
        for i, s in enumerate(stories):
            active = "active" if i == 0 else ""
            slides += f"""
            <div class="slide {active}" style="background-image: url('/data/school_stories/{os.path.basename(s['image_path'])}')">
                <div class="slide-caption">{s['title'] or ''}</div>
            </div>"""
        
        stories_html = f"""
        <div class="section-title"><i class="fas fa-camera-retro" style="color: #E91E63"></i> قصص المدرسة</div>
        <div class="card" style="padding: 0; overflow: hidden; height: 250px; position: relative;">
            <div class="carousel">
                {slides}
            </div>
            <div class="carousel-dots">
                {"".join([f'<div class="dot {"active" if i==0 else ""}" onclick="showSlide({i})"></div>' for i in range(len(stories))])}
            </div>
        </div>
        """

    # تحويل البيانات لعرضها بشكل جذاب
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>بوابة ولي الأمر - {analysis.get('name', 'طالب')}</title>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{ --pr: #1565C0; --bg: #F8FAFC; --txt: #1E293B; --sh: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        body {{ font-family: 'Cairo', sans-serif; background: var(--bg); color: var(--txt); margin: 0; padding: 20px; }}
        .container {{ max-width: 500px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .card {{ background: #fff; border-radius: 20px; padding: 20px; box-shadow: var(--sh); margin-bottom: 20px; border: 1px solid #E2E8F0; }}
        .profile-header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }}
        .avatar {{ width: 60px; height: 60px; background: #E0F2FE; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; color: var(--pr); }}
        .student-name {{ font-weight: 900; font-size: 20px; margin: 0; }}
        .class-name {{ color: #64748B; font-size: 14px; margin: 0; }}
        .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
        .stat-item {{ padding: 15px; border-radius: 15px; text-align: center; color: #fff; }}
        .stat-blue {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); }}
        .stat-orange {{ background: linear-gradient(135deg, #F97316, #C2410C); }}
        .stat-red {{ background: linear-gradient(135deg, #EF4444, #B91C1C); }}
        .stat-green {{ background: linear-gradient(135deg, #10B981, #047857); }}
        .stat-value {{ font-size: 28px; font-weight: 900; margin-bottom: 5px; }}
        .stat-label {{ font-size: 12px; opacity: 0.9; }}
        .section-title {{ font-weight: 700; font-size: 16px; margin: 20px 0 10px; display: flex; align-items: center; gap: 8px; }}
        .absence-item {{ display: flex; justify-content: space-between; padding: 12px; border-bottom: 1px solid #F1F5F9; font-size: 14px; }}
        .absence-item:last-child {{ border-bottom: none; }}
        .points-badge {{ background: #FEF3C7; color: #92400E; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 14px; }}
        
        /* Carousel Styles */
        .carousel {{ height: 100%; width: 100%; position: relative; }}
        .slide {{ position: absolute; inset: 0; background-size: cover; background-position: center; opacity: 0; transition: opacity 0.5s ease; }}
        .slide.active {{ opacity: 1; }}
        .slide-caption {{ position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.5); color: #fff; padding: 10px; font-size: 13px; text-align: center; backdrop-filter: blur(4px); }}
        .carousel-dots {{ position: absolute; bottom: 40px; left: 0; right: 0; display: flex; justify-content: center; gap: 8px; }}
        .dot {{ width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.5); cursor: pointer; }}
        .dot.active {{ background: #fff; width: 20px; border-radius: 10px; }}
        
        .footer {{ text-align: center; color: #94A3B8; font-size: 12px; margin-top: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="font-size: 24px; margin-bottom: 5px; color: var(--pr);">{school}</h1>
            <p style="margin:0; opacity:0.7">بوابة ولي الأمر الذكية</p>
        </div>

        <div class="card">
            <div class="profile-header">
                <div class="avatar"><i class="fas fa-user-graduate"></i></div>
                <div>
                    <h2 class="student-name">{analysis.get('name', 'طالب')}</h2>
                    <p class="class-name">{analysis.get('class_name', 'فصل')} — <span class="points-badge">{points} نقطة تميز ⭐</span></p>
                </div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-item stat-blue">
                <div class="stat-value">{analysis.get('total_absences', 0)}</div>
                <div class="stat-label">أيام غياب كلي</div>
            </div>
            <div class="stat-item stat-orange">
                <div class="stat-value">{analysis.get('total_tardiness', 0)}</div>
                <div class="stat-label">حالات تأخر</div>
            </div>
            <div class="stat-item stat-green">
                <div class="stat-value">{analysis.get('attendance_rate', '100')}%</div>
                <div class="stat-label">نسبة الانضباط</div>
            </div>
            <div class="stat-item stat-red">
                <div class="stat-value">{analysis.get('unexcused_days', 0)}</div>
                <div class="stat-label">غياب غير مبرر</div>
            </div>
        </div>

        {stories_html}

        <div class="section-title"><i class="fas fa-history" style="color: var(--pr)"></i> آخر المسجلات</div>
        <div class="card" style="padding: 10px;">
            {"".join([f'<div class="absence-item"><span>📅 {r["date"]}</span> <span style="color:#C62828">غياب</span></div>' for r in (analysis.get('absence_rows', [])[:5])])}
            {f'<p style="text-align:center; opacity:0.5; font-size:13px; padding:10px">لا يوجد غياب مسجل مؤخراً</p>' if not analysis.get('absence_rows') else ''}
        </div>

        <div class="section-title"><i class="fas fa-medal" style="color: #D97706"></i> سجل التميز</div>
        <div class="card" style="padding: 10px;">
             {"".join([f'<div class="absence-item"><span>🌟 {r["points"]} نقطة</span> <span style="font-size:12px; color:#64748B">{r["reason"]}</span></div>' for r in (analysis.get('points_history', [])[:3])])}
             {f'<p style="text-align:center; opacity:0.5; font-size:13px; padding:10px">ابدأ في جمع النقاط لتظهر هنا!</p>' if not analysis.get('points_history') else ''}
        </div>

        <div class="footer">
            <p>جميع الحقوق محفوظة © {datetime.datetime.now().year} DarbStu</p>
        </div>
    </div>
    
    <script>
        let currentSlide = 0;
        const slides = document.querySelectorAll('.slide');
        const dots = document.querySelectorAll('.dot');
        
        function showSlide(n) {{
            if (slides.length === 0) return;
            slides[currentSlide].classList.remove('active');
            dots[currentSlide].classList.remove('active');
            currentSlide = (n + slides.length) % slides.length;
            slides[currentSlide].classList.add('active');
            dots[currentSlide].classList.add('active');
        }}
        
        if (slides.length > 1) {{
            setInterval(() => showSlide(currentSlide + 1), 5000);
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(html)

# ─── ADMIN POINTS MANAGEMENT ───

@router.get("/web/api/admin/points-logs", response_class=JSONResponse)
async def api_admin_points_logs(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    from database import get_admin_points_logs
    return JSONResponse({"ok": True, "logs": get_admin_points_logs()})

@router.get("/web/api/admin/points-usage", response_class=JSONResponse)
async def api_admin_points_usage(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    month = request.query_params.get("month", datetime.date.today().isoformat()[:7])
    from database import get_teachers_points_usage
    return JSONResponse({"ok": True, "usage": get_teachers_points_usage(month)})

@router.delete("/web/api/admin/points-delete/{record_id}", response_class=JSONResponse)
async def api_admin_points_delete(request: Request, record_id: int):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    from database import delete_points_record
    delete_points_record(record_id)
    return JSONResponse({"ok": True})

@router.post("/web/api/admin/points-settings", response_class=JSONResponse)
async def api_admin_save_points_settings(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    data = await request.json()
    limit = data.get("limit", 100)
    from config_manager import load_config, save_config
    cfg = load_config()
    cfg["monthly_points_limit"] = int(limit)
    save_config(cfg)
    return JSONResponse({"ok": True})

@router.post("/web/api/admin/points-adjust", response_class=JSONResponse)
async def api_admin_points_adjust(request: Request):
    user = _get_current_user(request)
    if not user or user["role"] != "admin": return JSONResponse({"ok": False}, status_code=401)
    data = await request.json()
    username = data.get("username")
    points = data.get("points", 0)
    reason = data.get("reason", "")
    from database import adjust_teacher_balance
    adjust_teacher_balance(username, points, reason)
    return JSONResponse({"ok": True})

# ─── SCHOOL STORIES API ──────────────────────────────────────────

@router.get("/web/api/stories", response_class=JSONResponse)
async def api_get_stories(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    from database import get_active_stories
    return JSONResponse({"ok": True, "stories": get_active_stories()})

@router.post("/web/api/stories/add", response_class=JSONResponse)
async def api_add_story(request: Request, title: str = Form(None), file: UploadFile = File(...)):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy", "activity_leader"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    
    try:
        from constants import DATA_DIR
        import shutil
        
        stories_dir = os.path.join(DATA_DIR, "school_stories")
        os.makedirs(stories_dir, exist_ok=True)
        
        # حفظ الملف
        ext = os.path.splitext(file.filename)[1]
        fname = f"story_{int(datetime.datetime.now().timestamp())}{ext}"
        fpath = os.path.join(stories_dir, fname)
        
        with open(fpath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        from database import add_school_story
        add_school_story(title, fpath)
        
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.delete("/web/api/stories/delete/{story_id}", response_class=JSONResponse)
async def api_delete_story(request: Request, story_id: int):
    user = _get_current_user(request)
    if not user or user["role"] not in ("admin", "deputy", "activity_leader"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    
    try:
        from database import get_db
        con = get_db(); cur = con.cursor()
        cur.execute("SELECT image_path FROM school_stories WHERE id = ?", (story_id,))
        row = cur.fetchone()
        con.close()
        
        if row:
            fpath = row[0]
            if fpath and os.path.exists(fpath):
                try: os.remove(fpath)
                except: pass

        from database import delete_school_story
        delete_school_story(story_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)



# ─── WhatsApp Browser Connect ────────────────────────────────────────────────

@router.get("/web/api/wa/qr")
async def wa_qr_proxy(request: Request):
    """بروكسي لـ QR من خادم Node.js — متاح فقط للمدير والوكيل."""
    user = _get_current_user(request)
    if not user or user.get("role") not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        import urllib.request as _ur, json as _j
        r = _ur.urlopen("http://localhost:3000/qr", timeout=3)
        data = _j.loads(r.read())
        return JSONResponse({"ok": True, **data})
    except Exception as e:
        return JSONResponse({"ok": False, "ready": False, "qr": None, "msg": str(e)})


@router.get("/web/api/wa/status")
async def wa_status_proxy(request: Request):
    """بروكسي لحالة خادم واتساب."""
    user = _get_current_user(request)
    if not user or user.get("role") not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        import urllib.request as _ur, json as _j
        r = _ur.urlopen("http://localhost:3000/status", timeout=3)
        data = _j.loads(r.read())
        return JSONResponse({"ok": True, **data})
    except Exception as e:
        return JSONResponse({"ok": False, "ready": False, "msg": str(e)})


@router.post("/web/api/wa/start", response_class=JSONResponse)
async def wa_start_server(request: Request):
    """تشغيل خادم واتساب — للمدير والوكيل فقط."""
    user = _get_current_user(request)
    if not user or user.get("role") not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        from whatsapp_service import start_whatsapp_server
        start_whatsapp_server()
        return JSONResponse({"ok": True, "msg": "جارٍ التشغيل..."})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})


@router.post("/web/api/wa/reset", response_class=JSONResponse)
async def wa_reset_session(request: Request):
    """حذف جلسة واتساب المحفوظة لإجبار QR جديد."""
    user = _get_current_user(request)
    if not user or user.get("role") not in ("admin", "deputy"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        import shutil
        from constants import BASE_DIR
        auth_path = os.path.join(BASE_DIR, "my-whatsapp-server", ".wwebjs_auth")
        if os.path.exists(auth_path):
            shutil.rmtree(auth_path, ignore_errors=True)
        return JSONResponse({"ok": True, "msg": "تم حذف الجلسة — يرجى تشغيل الخادم من جديد"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})


@router.get("/web/whatsapp-connect", response_class=HTMLResponse)
async def wa_connect_page(request: Request):
    """صفحة ربط واتساب — للمدير والوكيل فقط."""
    user = _get_current_user(request)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/web/login")
    if user.get("role") not in ("admin", "deputy"):
        return HTMLResponse(
            "<h2 style='text-align:center;margin-top:60px;font-family:Tahoma'>"
            "غير مصرح لك بالوصول لهذه الصفحة</h2>", status_code=403)

    html = """<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ربط واتساب — درب</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Tahoma,Arial,sans-serif;background:#f0f4f8;min-height:100vh;
       display:flex;flex-direction:column;align-items:center;justify-content:center}
  .card{background:#fff;border-radius:16px;padding:32px 36px;
        box-shadow:0 4px 28px rgba(0,0,0,.11);max-width:460px;width:95%;text-align:center}
  h1{font-size:1.25rem;color:#1e3a5f;margin-bottom:4px}
  .sub{color:#64748b;font-size:.88rem;margin-bottom:22px}

  /* شارة الحالة */
  #badge{display:inline-flex;align-items:center;gap:8px;padding:8px 20px;
         border-radius:999px;font-size:.92rem;font-weight:700;margin-bottom:18px;
         transition:all .3s}
  .b-init    {background:#f1f5f9;color:#475569}
  .b-starting{background:#fef3c7;color:#92400e}
  .b-waiting {background:#fef3c7;color:#92400e}
  .b-scanning{background:#dbeafe;color:#1e40af}
  .b-ok      {background:#d1fae5;color:#065f46}
  .b-error   {background:#fee2e2;color:#991b1b}

  .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
  .d-grey  {background:#9ca3af}
  .d-yellow{background:#f59e0b;animation:blink 1s infinite}
  .d-blue  {background:#3b82f6;animation:blink .8s infinite}
  .d-green {background:#22c55e;animation:pulse 1.2s infinite}
  .d-red   {background:#ef4444}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

  /* منطقة QR */
  #qr-area{min-height:230px;display:flex;flex-direction:column;align-items:center;
           justify-content:center;background:#f8fafc;border-radius:12px;
           border:2px dashed #cbd5e1;margin-bottom:16px;padding:16px;gap:10px}
  #qr-area canvas,#qr-area img{max-width:210px;max-height:210px}
  #qr-area .qr-icon{font-size:2.8rem}
  #qr-area .qr-msg{font-size:.85rem;color:#64748b}

  /* رسالة */
  #msg{color:#475569;font-size:.87rem;line-height:1.7;margin-bottom:14px}

  /* أزرار */
  .btns{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:16px}
  .btn{padding:8px 18px;border:none;border-radius:8px;cursor:pointer;
       font-family:Tahoma;font-size:.88rem;font-weight:700;transition:opacity .2s}
  .btn:hover{opacity:.85}
  .btn:disabled{opacity:.4;cursor:default}
  .btn-primary{background:#1565C0;color:#fff}
  .btn-warn   {background:#f59e0b;color:#fff}
  .btn-danger {background:#dc2626;color:#fff}
  .btn-ghost  {background:#f1f5f9;color:#475569}

  /* خطوات */
  .steps{text-align:right;background:#f8fafc;border-radius:10px;
         padding:12px 16px;color:#374151;font-size:.85rem;line-height:2.1;
         border:1px solid #e2e8f0;margin-bottom:18px}
  .steps strong{color:#1565C0}

  .back{display:inline-block;padding:8px 20px;background:#1565C0;color:#fff;
        border-radius:8px;text-decoration:none;font-size:.88rem}
  #spinner{display:none;width:28px;height:28px;border:3px solid #e2e8f0;
           border-top-color:#1565C0;border-radius:50%;animation:spin .7s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="card">
  <div style="font-size:2rem;margin-bottom:6px">📱</div>
  <h1>ربط واتساب المدرسة</h1>
  <p class="sub">امسح رمز QR بتطبيق واتساب لربط الحساب</p>

  <div id="badge" class="b-init">
    <div class="dot d-grey" id="dot"></div>
    <span id="badge-txt">جارٍ التحقق...</span>
  </div>

  <div id="qr-area">
    <div id="spinner"></div>
    <div id="qr-div"></div>
    <div class="qr-icon" id="qr-icon" style="display:none"></div>
    <div class="qr-msg" id="qr-sub"></div>
  </div>

  <p id="msg"></p>

  <div class="btns" id="btns">
    <button class="btn btn-primary" id="btn-start" onclick="waStart()">▶ تشغيل الخادم</button>
    <button class="btn btn-warn"    id="btn-reset" onclick="waReset()" style="display:none">🔄 فرض QR جديد</button>
    <button class="btn btn-ghost"   id="btn-refresh" onclick="poll()">↻ تحديث</button>
  </div>

  <div class="steps">
    <strong>خطوات الربط:</strong><br>
    ١- اضغط "تشغيل الخادم" إذا كان الخادم غير متصل<br>
    ٢- انتظر ظهور رمز QR (قد يستغرق دقيقة)<br>
    ٣- افتح واتساب ← الأجهزة المرتبطة ← ربط جهاز<br>
    ٤- امسح رمز QR الظاهر أعلاه
  </div>

  <a class="back" href="/web/dashboard">← العودة للوحة التحكم</a>
</div>

<script>
var _connected=false, _lastQR='', _qrInst=null, _pollTimer=null;

function setBadge(cls,dotCls,txt){
  var b=document.getElementById('badge');
  b.className=cls;
  document.getElementById('dot').className='dot '+dotCls;
  document.getElementById('badge-txt').textContent=txt;
}
function setMsg(txt){ document.getElementById('msg').textContent=txt; }
function showSpinner(v){
  document.getElementById('spinner').style.display=v?'block':'none';
}
function showIcon(icon,sub){
  document.getElementById('qr-icon').style.display=icon?'block':'none';
  document.getElementById('qr-icon').textContent=icon||'';
  document.getElementById('qr-sub').textContent=sub||'';
}
function showQRDiv(v){
  document.getElementById('qr-div').style.display=v?'block':'none';
}

function renderQR(txt){
  if(txt===_lastQR)return;
  _lastQR=txt;
  showSpinner(false);
  showIcon('','');
  showQRDiv(true);
  var wrap=document.getElementById('qr-div');
  wrap.innerHTML='';
  _qrInst=new QRCode(wrap,{text:txt,width:210,height:210,
    colorDark:'#000',colorLight:'#fff',correctLevel:QRCode.CorrectLevel.M});
}

function schedulePoll(ms){
  clearTimeout(_pollTimer);
  _pollTimer=setTimeout(poll,ms);
}

async function poll(){
  if(_connected)return;
  try{
    var r=await fetch('/web/api/wa/qr');
    var d=await r.json();

    // ── الخادم لا يعمل (ok=false أو خطأ في الاتصال بـ Node.js) ──
    if(!d.ok){
      setBadge('b-error','d-red','الخادم غير متصل');
      showSpinner(false);
      showIcon('🔴','خادم واتساب لا يعمل');
      showQRDiv(false);
      setMsg('خادم واتساب لا يعمل. اضغط "تشغيل الخادم" ثم انتظر.');
      document.getElementById('btn-start').style.display='';
      document.getElementById('btn-reset').style.display='none';
      schedulePoll(5000);
      return;
    }

    // ── متصل ✅ ──
    if(d.ready){
      _connected=true;
      clearTimeout(_pollTimer);
      setBadge('b-ok','d-green','متصل ✅');
      showSpinner(false);
      showIcon('✅','واتساب متصل وجاهز');
      showQRDiv(false);
      setMsg('تم الربط بنجاح! يمكنك الآن إرسال رسائل واتساب من النظام.');
      document.getElementById('btn-start').style.display='none';
      document.getElementById('btn-reset').style.display='';
      return;
    }

    // ── الخادم يعمل وفيه QR ──
    if(d.qr){
      setBadge('b-scanning','d-blue','بانتظار المسح...');
      renderQR(d.qr);
      setMsg('امسح رمز QR بتطبيق واتساب. ينتهي صلاحيته بعد دقيقة.');
      document.getElementById('btn-start').style.display='none';
      document.getElementById('btn-reset').style.display='';
      schedulePoll(3000);
      return;
    }

    // ── الخادم يعمل لكن لا يوجد QR بعد (جلسة محفوظة تُحمَّل) ──
    setBadge('b-starting','d-yellow','الخادم يبدأ...');
    showSpinner(true);
    showIcon('','');
    showQRDiv(false);
    setMsg('الخادم يعمل ويحاول الاتصال. قد تكون هناك جلسة محفوظة، انتظر أو اضغط "فرض QR جديد".');
    document.getElementById('btn-start').style.display='none';
    document.getElementById('btn-reset').style.display='';
    schedulePoll(3000);

  }catch(e){
    setBadge('b-error','d-red','خطأ في الاتصال');
    showSpinner(false);
    showIcon('⚠️','');
    showQRDiv(false);
    setMsg('تعذّر الوصول للخادم: '+e.message);
    schedulePoll(5000);
  }
}

async function waStart(){
  var btn=document.getElementById('btn-start');
  btn.disabled=true; btn.textContent='⏳ جارٍ التشغيل...';
  setBadge('b-starting','d-yellow','جارٍ التشغيل...');
  showSpinner(true); showQRDiv(false);
  setMsg('جارٍ تشغيل خادم واتساب، يرجى الانتظار...');
  try{
    await fetch('/web/api/wa/start',{method:'POST'});
  }catch(e){}
  setTimeout(function(){ btn.disabled=false; btn.textContent='▶ تشغيل الخادم'; poll(); }, 4000);
}

async function waReset(){
  if(!confirm('سيتم حذف الجلسة المحفوظة وستحتاج لمسح QR جديد. هل تريد المتابعة؟'))return;
  var btn=document.getElementById('btn-reset');
  btn.disabled=true; btn.textContent='⏳...';
  try{
    var r=await fetch('/web/api/wa/reset',{method:'POST'});
    var d=await r.json();
    if(d.ok){ setMsg('تم حذف الجلسة. اضغط "تشغيل الخادم".'); }
    else     { setMsg('خطأ: '+d.msg); }
  }catch(e){ setMsg('خطأ: '+e.message); }
  _lastQR=''; _connected=false;
  btn.disabled=false; btn.textContent='🔄 فرض QR جديد';
  document.getElementById('btn-start').style.display='';
  schedulePoll(1000);
}

// ابدأ فور تحميل الصفحة
showSpinner(true); showQRDiv(false);
poll();
</script>
</body>
</html>"""
    return HTMLResponse(content=html, headers={
        "Content-Security-Policy":
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;"
    })


# ── Partial Absence ──────────────────────────────────────────────────────────

@router.get("/web/api/partial-absences", response_class=JSONResponse)
async def web_partial_absences(request: Request, date: str = "", min_period: int = 2):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    if user.get("role") not in ("admin", "deputy", "staff", "counselor"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    if not date:
        date = now_riyadh_date()
    try:
        from database import get_partial_absences
        rows = get_partial_absences(date, min_period)
        return JSONResponse({"ok": True, "rows": rows, "date": date})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/partial-absences/status", response_class=JSONResponse)
async def web_set_partial_absence_status(req: Request):
    user = _get_current_user(req)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    if user.get("role") not in ("admin", "deputy", "staff", "counselor"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        data       = await req.json()
        student_id = str(data.get("student_id", "")).strip()
        status     = str(data.get("status", "غير محدد")).strip()
        date       = str(data.get("date", "")).strip()
        notes      = str(data.get("notes", "")).strip()
        if not student_id or not date:
            return JSONResponse({"ok": False, "msg": "student_id و date مطلوبان"})
        from database import set_partial_absence_status
        set_partial_absence_status(date, student_id, status, notes)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/partial-absences/mark-permitted", response_class=JSONResponse)
async def web_mark_permitted(req: Request):
    """تسجيل الطالب كمستأذن في جدول الاستئذان."""
    user = _get_current_user(req)
    if not user or user.get("role") not in ("admin", "deputy", "staff"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        data        = await req.json()
        student_id  = str(data.get("student_id", "")).strip()
        student_name= str(data.get("student_name", "")).strip()
        class_name  = str(data.get("class_name", "")).strip()
        date        = str(data.get("date", "")).strip()
        periods     = str(data.get("absent_periods", "")).strip()
        if not student_id or not date:
            return JSONResponse({"ok": False, "msg": "بيانات ناقصة"})

        # جلب class_id و parent_phone من قاعدة البيانات
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        row = cur.execute(
            "SELECT class_id FROM absences WHERE student_id=? AND date=? LIMIT 1",
            (student_id, date)
        ).fetchone()
        class_id = row["class_id"] if row else ""

        # جلب جوال ولي الأمر من students.json إن وُجد
        parent_phone = ""
        try:
            store = load_students(force_reload=False)
            for cls in store.get("list", []):
                for s in cls.get("students", []):
                    if str(s.get("id")) == student_id:
                        parent_phone = s.get("phone", "") or s.get("parent_phone", "")
                        break
        except Exception:
            pass

        # التحقق من عدم وجود استئذان مسبق لنفس الطالب في نفس اليوم
        existing = cur.execute(
            "SELECT id FROM permissions WHERE student_id=? AND date=?",
            (student_id, date)
        ).fetchone()
        con.close()
        if existing:
            # تحديث الحالة في partial_absence_status فقط
            from database import set_partial_absence_status
            set_partial_absence_status(date, student_id, "مستأذن")
            return JSONResponse({"ok": True, "msg": "مسجَّل مسبقاً في الاستئذان"})

        reason = f"غياب جزئي — الحصص: {periods}"
        from alerts_service import insert_permission
        insert_permission(date, student_id, student_name, class_id, class_name,
                          parent_phone, reason=reason, approved_by=user.get("sub", "الويب"))
        from database import set_partial_absence_status
        set_partial_absence_status(date, student_id, "مستأذن")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/web/api/partial-absences/mark-escaped", response_class=JSONResponse)
async def web_mark_escaped(req: Request):
    """تسجيل الطالب كهارب في الإشعارات الذكية (counselor_referrals)."""
    user = _get_current_user(req)
    if not user or user.get("role") not in ("admin", "deputy", "staff"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        data         = await req.json()
        student_id   = str(data.get("student_id", "")).strip()
        student_name = str(data.get("student_name", "")).strip()
        class_name   = str(data.get("class_name", "")).strip()
        date         = str(data.get("date", "")).strip()
        periods      = str(data.get("absent_periods", "")).strip()
        if not student_id or not date:
            return JSONResponse({"ok": False, "msg": "بيانات ناقصة"})

        now_str = datetime.datetime.utcnow().isoformat()
        con = get_db(); cur = con.cursor()
        # تجنب التكرار
        existing = cur.execute(
            "SELECT id FROM counselor_referrals WHERE student_id=? AND date=? AND referral_type='هروب'",
            (student_id, date)
        ).fetchone()
        if not existing:
            cur.execute("""
                INSERT INTO counselor_referrals
                    (date, student_id, student_name, class_name, referral_type,
                     absence_count, notes, referred_by, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (date, student_id, student_name, class_name, "هروب",
                  0, f"هروب من المدرسة — الحصص الغائبة: {periods}",
                  user.get("sub", "الويب"), "جديد", now_str))
            con.commit()
        con.close()
        from database import set_partial_absence_status
        set_partial_absence_status(date, student_id, "هارب")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.get("/web/api/escaped-report", response_class=JSONResponse)
async def web_escaped_report(request: Request, month: str = ""):
    """تقرير الطلاب الهاربين من الحصول على الكاش."""
    user = _get_current_user(request)
    if not user or user.get("role") not in ("admin", "deputy", "staff", "counselor"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
    try:
        import datetime as _dt
        if not month:
            month = _dt.datetime.now().strftime("%Y-%m")
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        rows = cur.execute("""
            SELECT date, student_id, student_name, class_name, notes, status, created_at
            FROM counselor_referrals
            WHERE referral_type = 'هروب' AND date LIKE ?
            ORDER BY date DESC, class_name, student_name
        """, (month + "%",)).fetchall()
        con.close()
        return JSONResponse({"ok": True, "rows": [dict(r) for r in rows], "month": month})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ─── تقارير المدرسة ──────────────────────────────────────────────────

_SR_CAT_ROLES = {
    "admin":         ["admin"],
    "educational":   ["admin", "deputy"],
    "school_affairs":["admin", "deputy"],
    "guidance":      ["admin", "counselor"],
    "activity":      ["admin", "activity_leader"],
    "achievement":   ["admin", "deputy", "teacher"],
}

@router.get("/web/api/school-reports/counts", response_class=JSONResponse)
async def web_sr_counts(req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        rows = cur.execute("SELECT category, COUNT(*) as cnt FROM school_reports GROUP BY category").fetchall()
        con.close()
        return JSONResponse({"ok": True, "counts": {r["category"]: r["cnt"] for r in rows}})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/school-reports", response_class=JSONResponse)
async def web_sr_list(req: Request, category: str = ""):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        rows = cur.execute(
            "SELECT * FROM school_reports WHERE category=? ORDER BY uploaded_at DESC", (category,)
        ).fetchall()
        con.close()
        return JSONResponse({"ok": True, "rows": [dict(r) for r in rows]})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/school-reports/upload", response_class=JSONResponse)
async def web_sr_upload(req: Request,
                         file: UploadFile = File(...),
                         category: str    = Form(...),
                         title: str       = Form(...),
                         report_date: str = Form(""),
                         description: str = Form("")):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    allowed_roles = _SR_CAT_ROLES.get(category, ["admin"])
    if user.get("role") not in allowed_roles:
        return JSONResponse({"ok": False, "msg": "غير مصرح لرفع تقارير في هذا القسم"}, status_code=403)
    try:
        import uuid, os as _os
        _os.makedirs(SCHOOL_REPORTS_DIR, exist_ok=True)
        ext   = _os.path.splitext(file.filename or "file")[1][:10]
        fname = uuid.uuid4().hex + ext
        fpath = _os.path.join(SCHOOL_REPORTS_DIR, fname)
        content = await file.read()
        if len(content) > 20 * 1024 * 1024:
            return JSONResponse({"ok": False, "msg": "الحد الأقصى لحجم الملف 20 ميغابايت"})
        with open(fpath, "wb") as f:
            f.write(content)
        import datetime as _dt
        con = get_db(); cur = con.cursor()
        cur.execute("""INSERT INTO school_reports
                       (category,title,description,report_date,file_path,file_name,file_size,uploaded_by,uploaded_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (category, title, description, report_date, fname,
                     file.filename, len(content),
                     user.get("username", ""), _dt.datetime.now().isoformat()))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/school-reports/file/{report_id}")
async def web_sr_file(report_id: int, req: Request):
    user = _get_current_user(req)
    if not user: return Response("غير مصرح", status_code=401)
    import os as _os
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        row = cur.execute("SELECT * FROM school_reports WHERE id=?", (report_id,)).fetchone()
        con.close()
        if not row: return Response("التقرير غير موجود", status_code=404)
        fpath = _os.path.join(SCHOOL_REPORTS_DIR, row["file_path"])
        if not _os.path.exists(fpath): return Response("الملف غير موجود على الخادم", status_code=404)
        from fastapi.responses import FileResponse
        return FileResponse(fpath, filename=row["file_name"])
    except Exception as e:
        return Response(str(e), status_code=500)

@router.delete("/web/api/school-reports/{report_id}", response_class=JSONResponse)
async def web_sr_delete(report_id: int, req: Request):
    user = _get_current_user(req)
    if not user: return JSONResponse({"ok": False}, status_code=401)
    import os as _os
    try:
        con = get_db(); con.row_factory = sqlite3.Row; cur = con.cursor()
        row = cur.execute("SELECT * FROM school_reports WHERE id=?", (report_id,)).fetchone()
        if not row:
            con.close()
            return JSONResponse({"ok": False, "msg": "التقرير غير موجود"})
        allowed_roles = _SR_CAT_ROLES.get(row["category"], ["admin"])
        if user.get("role") not in allowed_roles:
            con.close()
            return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)
        fpath = _os.path.join(SCHOOL_REPORTS_DIR, row["file_path"])
        cur.execute("DELETE FROM school_reports WHERE id=?", (report_id,))
        con.commit(); con.close()
        try: _os.remove(fpath)
        except: pass
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


# ===================== main =====================

if __name__ == "__main__":
    pass
