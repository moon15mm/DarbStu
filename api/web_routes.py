# -*- coding: utf-8 -*-
"""
api/web_routes.py — مسارات لوحة التحكم الويب /web/*
"""
import datetime, json, base64, os, io, hashlib, hmac, re, sqlite3, subprocess, zipfile, urllib.request
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response

from constants import (DB_PATH, DATA_DIR, HOST, PORT, TZ_OFFSET,
                       STATIC_DOMAIN, BASE_DIR, BACKUP_DIR,
                       STUDENTS_JSON, TEACHERS_JSON, CONFIG_JSON,
                       now_riyadh_date, CURRENT_USER, ROLES, ROLE_TABS,
                       APP_VERSION)
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
                      update_referral_deputy, close_referral,
                      create_academic_inquiry, get_academic_inquiries,
                      get_academic_inquiry, reply_academic_inquiry,
                      create_circular, get_circulars, mark_circular_as_read,
                      get_unread_circulars_count, delete_circular)
from whatsapp_service import (send_whatsapp_message, send_whatsapp_pdf,
                               check_whatsapp_server_status)
from alerts_service import (log_message_status, run_smart_alerts,
                             build_daily_summary_message, send_daily_report_to_admin,
                             get_students_exceeding_threshold, get_student_full_analysis,
                             get_top_absent_students, get_student_absence_count,
                             get_tardiness_recipients, save_tardiness_recipients,
                             query_permissions, insert_permission,
                             update_permission_status, load_schedule, save_schedule,
                             send_permission_request, build_absent_groups)
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

def _create_token(username: str, role: str) -> str:
    import jwt as _jwt, datetime as _dt
    payload = {
        "sub":  username,
        "role": role,
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
        token = _create_token(user["username"], user["role"])
        resp  = JSONResponse({"ok": True, "role": user["role"],
                               "name": user.get("full_name") or user["username"]})
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

        sent = failed = 0
        for stu in students:
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
                "class_name": cname, "date": date_str})
            if ok: sent += 1
            else:  failed += 1

        return JSONResponse({"ok": True, "sent": sent, "failed": failed})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


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

        sent = failed = 0
        for stu in students:
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

            ok, _ = send_whatsapp_message(phone, msg)
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
    store = load_students()
    cls   = next((c for c in store["list"] if c["id"] == class_id), None)
    if not cls: return JSONResponse({"ok": False, "msg": "فصل غير موجود"})
    return JSONResponse({"ok": True, "students": cls["students"], "name": cls["name"]})



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
            data["date"], data["student_id"], data["student_name"],
            data.get("class_id",""), data.get("class_name",""),
            user["sub"], int(data.get("minutes_late", 5)))
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
                   FROM absences GROUP BY month ORDER BY month DESC LIMIT 6""")
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
        users = get_all_users()
        teachers = [{"username": u["username"], "full_name": u.get("full_name") or u["username"]} for u in users if u["role"] == "teacher" and u["active"]]
        return JSONResponse({"ok": True, "teachers": teachers})
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

@router.get("/web/api/circulars/list", response_class=JSONResponse)
async def web_list_circulars(request: Request):
    try:
        user = _get_current_user(request)
        if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
        print(f"[API] 📜 طلب قائمة التعاميم للمستخدم: {user['sub']} ({user['role']})")
        rows = get_circulars(username=user["sub"], role=user["role"])
        print(f"[API] ✅ تم جلب {len(rows)} تعميم بنجاح")
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        import traceback
        print(f"[API-CIRC-ERROR] {e}")
        traceback.print_exc()
        return JSONResponse({"ok": False, "msg": f"خطأ داخلي: {str(e)}"}, status_code=500)

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

    # ── قائمة التبويبات مع مجموعاتها ──────────────────────────
    SIDEBAR_GROUPS = [
        ("الرئيسية", [
            ("لوحة المراقبة",      "dashboard",            "fas fa-chart-line"),
            ("روابط الفصول",        "links",                "fas fa-link"),
            ("المراقبة الحية",      "live_monitor",         "fas fa-satellite-dish"),
        ]),
        ("التسجيل اليومي", [
            ("تسجيل الغياب",        "reg_absence",          "fas fa-user-check"),
            ("تسجيل التأخر",        "reg_tardiness",        "fas fa-stopwatch"),
            ("طلب استئذان",         "new_permission",       "fas fa-bell"),
        ]),
        ("السجلات", [
            ("سجل الغياب",          "absences",             "fas fa-history"),
            ("سجل التأخر",          "tardiness",            "fas fa-clock"),
            ("الأعذار",             "excuses",              "fas fa-file-medical"),
            ("الاستئذان",           "permissions",          "fas fa-door-open"),
            ("السجلات / التصدير",   "logs",                 "fas fa-file-export"),
            ("إدارة الغياب",        "absence_mgmt",         "fas fa-users-cog"),
        ]),
        ("التقارير والتحليل", [
            ("التقارير / الطباعة",  "reports_print",        "fas fa-print"),
            ("تقرير الفصل",         "term_report",          "fas fa-file-alt"),
            ("تحليل النتائج",       "grade_analysis",       "fas fa-chart-bar"),
            ("تقرير الإدارة",       "admin_report",         "fas fa-user-tie"),
            ("تحليل طالب",          "student_analysis",     "fas fa-search"),
            ("أكثر الطلاب غياباً", "top_absent",           "fas fa-award"),
            ("الإشعارات الذكية",    "alerts",               "fas fa-exclamation-triangle"),
        ]),
        ("الرسائل والتواصل", [
            ("إرسال رسائل الغياب",  "send_absence",         "fas fa-envelope-open-text"),
            ("إرسال رسائل التأخر",  "send_tardiness",       "fas fa-paper-plane"),
            ("التعاميم والنشرات",   "circulars",            "fas fa-scroll"),
            ("مستلمو التأخر",       "tardiness_recipients", "fas fa-users"),
            ("جدولة الروابط",       "schedule_links",       "fas fa-calendar-alt"),
        ]),
        ("إدارة البيانات", [
            ("إدارة الطلاب",        "student_mgmt",         "fas fa-graduation-cap"),
            ("إضافة طالب",          "add_student",          "fas fa-user-plus"),
            ("إدارة الفصول",        "class_naming",         "fas fa-school"),
            ("إدارة الجوالات",      "phones",               "fas fa-mobile-alt"),
            ("تصدير نور",           "noor_export",          "fas fa-cloud-upload-alt"),
            ("نشر النتائج",         "results",              "fas fa-medal"),
            ("الموجّه الطلابي",     "counselor",            "fas fa-brain"),
            ("استلام تحويلات",      "referral_deputy",      "fas fa-inbox"),
        ]),
        ("أدوات المعلم", [
            ("تحويل طالب",          "referral_teacher",     "fas fa-clipboard-list"),
            ("نماذج المعلم",        "teacher_forms",        "fas fa-file-contract"),
        ]),
        ("الإعدادات", [
            ("إعدادات المدرسة",     "school_settings",      "fas fa-university"),
            ("المستخدمون",          "users",                "fas fa-user-shield"),
            ("النسخ الاحتياطية",    "backup",               "fas fa-hdd"),
            ("ملاحظات سريعة",       "quick_notes",          "fas fa-sticky-note"),
        ]),
    ]

    # ── بناء شريط التنقل الجانبي ──────────────────────────────
    sidebar_html = ""
    for grp_title, grp_items in SIDEBAR_GROUPS:
        visible = [(n, k, i) for n, k, i in grp_items
                   if allowed_tabs is None or n in allowed_tabs]
        if not visible:
            continue
        sidebar_html += '<div class="sb-group">' + grp_title + '</div>'
        for name, key, icon in visible:
            sidebar_html += (
                '<button class="tab-btn" data-key="' + key + '" onclick="showTab(\'' + key + '\')">'
                '<i class="ti ' + icon + '"></i>' + name + '</button>'
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
    )

    # ── محتوى التبويبات ────────────────────────────────────────
    content_html = '''
<div id="tab-dashboard">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
    <h2 class="pt"><i class="fas fa-chart-line"></i> لوحة المراقبة</h2>
    <input type="date" id="dash-date" onchange="loadDashboard()" style="width:auto">
  </div>
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
      <div class="fg"><label class="fl">الفصل الدراسي</label><select id="tr-sem"><option value="1">الأول</option><option value="2">الثاني</option><option value="3">الثالث</option></select></div>
      <div class="fg"><label class="fl">الصف</label><select id="tr-cls"><option value="">الكل</option></select></div>
    </div>
    <div class="bg-btn">
      <button class="btn bp1" onclick="alert('تقرير الفصل — يحتاج API')">إنشاء</button>
      <button class="btn bp2" onclick="printSec('tr-res')">🖨️ طباعة</button>
    </div>
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
  <div id="ga-res" style="margin-top:14px">
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
  <h2 class="pt"><i class="fas fa-search"></i> تحليل طالب</h2>
  <div class="section">
    <div class="fg2">
      <div class="fg"><label class="fl">الفصل</label><select id="an-class" onchange="loadClsForAn()"><option value="">اختر فصلاً</option></select></div>
      <div class="fg"><label class="fl">الطالب</label><select id="an-student"><option value="">اختر طالباً</option></select></div>
    </div>
    <button class="btn bp1" onclick="analyzeStudent()">تحليل</button>
  </div>
  <div id="an-result" style="margin-top:16px"></div>
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

<div id="tab-circulars">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
    <h2 class="pt" style="margin:0"><i class="fas fa-scroll"></i> التعاميم والنشرات</h2>
    ''' + ('<button class="btn bp1 bsm" onclick="si(\'circulars\',\'circ-add\')">+ إصدار تعميم</button>' if role == 'admin' else '') + '''
    <button class="btn bp2 bsm" onclick="loadCirculars()"><i class="fas fa-sync-alt"></i> تحديث</button>
  </div>
  
  <div id="circ-add" class="ip" style="display:none">
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
      <thead><tr><th>رقم الهوية</th><th>الاسم</th><th>الصف</th><th>الفصل</th><th>الجوال</th><th>تعديل</th></tr></thead>
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
      <div class="fg2"><div class="fg"><label class="fl">المنفذ (Port)</label><input type="number" id="wa-port" value="3000"></div></div>
      <div class="bg-btn">
        <button class="btn bp1" onclick="checkWA()">🔍 فحص</button>
        <button class="btn bp4" onclick="alert('تشغيل الخادم — يعمل محلياً فقط')">▶️ تشغيل</button>
      </div>
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
  </div>
</div>

<div id="tab-users">
  <h2 class="pt"><i class="fas fa-user-shield"></i> إدارة المستخدمين</h2>
  <div class="section">
    <div class="st">إضافة مستخدم جديد</div>
    <div class="fg2">
      <div class="fg"><label class="fl">اسم المستخدم</label><input type="text" id="us-uname"></div>
      <div class="fg"><label class="fl">الاسم الكامل</label><input type="text" id="us-fname"></div>
      <div class="fg"><label class="fl">كلمة المرور</label><input type="text" id="us-pw"></div>
      <div class="fg"><label class="fl">الدور</label><select id="us-role"><option value="admin">مدير</option><option value="deputy">وكيل</option><option value="teacher">معلم</option><option value="guard">حارس</option></select></div>
    </div>
    <button class="btn bp1" onclick="addUser()">+ إضافة</button>
    <div id="us-st" style="margin-top:10px"></div>
  </div>
  <div class="section"><div class="tw"><table>
    <thead><tr><th>اسم المستخدم</th><th>الاسم الكامل</th><th>الدور</th><th>الحالة</th><th>حذف</th></tr></thead>
    <tbody id="us-table"></tbody></table></div></div>
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

<div id="tab-quick_notes">
  <h2 class="pt"><i class="fas fa-sticky-note"></i> ملاحظات سريعة</h2>
  <div class="section">
    <textarea id="qn-text" rows="3" placeholder="اكتب ملاحظتك هنا..." style="width:100%;margin-bottom:8px"></textarea>
    <div class="bg-btn" style="margin-bottom:16px">
      <select id="qn-type"><option value="info">ℹ️ معلومة</option><option value="warning">⚠️ تنبيه</option><option value="task">✅ مهمة</option></select>
      <button class="btn bp1" onclick="addNote()">+ إضافة</button>
    </div>
    <div id="qn-list"></div>
  </div>
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
        <div class="fg"><label class="fl">المرحلة الدراسية</label><select id="tfl-grade"><option>الأول متوسط</option><option>الثاني متوسط</option><option>الثالث متوسط</option><option>الأول ثانوي</option><option>الثاني ثانوي</option><option>الثالث ثانوي</option></select></div>
        <div class="fg"><label class="fl">الفصل</label><input type="text" id="tfl-cls" value="جميع الفصول"></div>
        <div class="fg"><label class="fl">عدد الطلاب</label><input type="number" id="tfl-count" value="30"></div>
        <div class="fg"><label class="fl">المادة</label><input type="text" id="tfl-subj"></div>
        <div class="fg"><label class="fl">التاريخ</label><input type="date" id="tfl-date"></div>
        <div class="fg"><label class="fl">عنوان الدرس</label><input type="text" id="tfl-lesson"></div>
        <div class="fg"><label class="fl">الاستراتيجية</label><select id="tfl-strat">
          <option>التعلم المبني على حل المشكلات</option><option>العصف الذهني</option><option>التعلم التعاوني</option>
          <option>الخرائط الذهنية</option><option>التدريس التبادلي</option><option>التعلم الذاتي</option><option>أخرى</option>
        </select></div>
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
      <div class="bg-btn" style="margin-top:12px">
        <button class="btn bp1" onclick="submitTeacherForm('lesson', false)">تحميل PDF</button>
        <button class="btn bp4" onclick="submitTeacherForm('lesson', true)">📲 إرسال للمدير</button>
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
      <div class="bg-btn" style="margin-top:12px">
        <button class="btn bp1" onclick="submitTeacherForm('program', false)">تحميل PDF</button>
        <button class="btn bp4" onclick="submitTeacherForm('program', true)">📲 إرسال للمدير</button>
      </div><div id="tfp-st"></div>
    </div>
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
'''

    # ── JavaScript الكامل المضغوط ─────────────────────────────
    js = r"""
window.onerror = function(msg, url, line, col, error) {
    alert("❌ حصل خطأ في المتصفح:\n" + msg + "\n\nالمكان: " + url + ":" + line);
    return false;
};
var today=new Date().toISOString().split('T')[0];
var _gender='boys', _me=null, _notes=[];
try{_notes=JSON.parse(localStorage.getItem('darb_notes')||'[]');}catch(e){}

window.onload=function(){setDates();loadMe();showTab('dashboard');};

function setDates(){
  ['dash-date','abs-date','tard-date','exc-date','perm-date','sa-date','st-date','ar-date',
   'np-date','lm-date','exc-date-new','noor-date','co-date','lg-from','lg-to'].forEach(function(id){
    var el=document.getElementById(id);if(el)el.value=today;});
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
    'reports_print':function(){loadReports();fillSel('rp-cls');fillSel('rp-sc');},
    'admin_report':generateAdminReport,
    'student_analysis':function(){fillSel('an-class');},
    'top_absent':loadTopAbsent,'alerts':loadAlerts,
    'new_permission':function(){loadClasses();loadTodayPerms();},
    'student_mgmt':function(){loadStudents();fillSel('sm-cls');},
    'add_student':function(){fillSel('as-cls');},
    'class_naming':loadClassList,
    'phones':function(){loadStudents();fillSel('ph-cls');},
    'noor_export':function(){fillSel('noor-cls');},
    'results':function(){},
    'counselor':function(){fillSel('co-cls');fillSel('coa-cls');loadCoSessions();loadCounselorList();},
    'circulars': loadCirculars,
    'school_settings':loadSettings,
    'users':loadUsers,'backup':loadBackups,
    'quick_notes':renderNotes,
    'schedule_links':function(){fillSel('sch-cls');loadSchedule();},
    'tardiness_recipients':loadRecipients,
    'grade_analysis':function(){fillSel('ga-cls');},
    'term_report':function(){fillSel('tr-cls');},
    'referral_teacher':function(){loadRefStudents();loadRefHistory();},
    'referral_deputy':loadDeputyReferrals,
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
  ['ra-class','rt-class','np-class','an-class'].forEach(function(id){var el=document.getElementById(id);if(el)el.innerHTML=opts;});
}
function fillSel(id){
  var el=document.getElementById(id);if(!el)return;
  var cur=el.value;
  el.innerHTML='<option value="">الكل</option>'+_classes.map(function(c){return '<option value="'+c.id+'">'+c.name+'</option>';}).join('');
  if(cur)el.value=cur;
}

/* ── ABSENCES ── */
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
async function loadClsForAn(){
  var cid=document.getElementById('an-class').value;if(!cid)return;
  var d=await api('/web/api/class-students/'+cid);if(!d||!d.ok)return;
  document.getElementById('an-student').innerHTML='<option value="">اختر طالباً</option>'+
    d.students.map(function(s){return '<option value="'+s.id+'">'+s.name+'</option>';}).join('');
}
async function analyzeStudent(){
  var sid=document.getElementById('an-student').value;if(!sid){alert('اختر طالباً');return;}
  document.getElementById('an-result').innerHTML='<div class="loading">⏳ جارٍ التحليل...</div>';
  var d=await api('/web/api/student-analysis/'+sid);if(!d||!d.ok){document.getElementById('an-result').innerHTML='<div class="section">❌ خطأ</div>';return;}
  var data=d.data;var ac=data.total_absences>=5?'#C62828':'#1565C0';
  document.getElementById('an-result').innerHTML='<div class="stat-cards">'+
    '<div class="sc" style="border-bottom:3px solid '+ac+'"><div class="v" style="color:'+ac+'">'+data.total_absences+'</div><div class="l">إجمالي الغياب</div></div>'+
    '<div class="sc"><div class="v" style="color:#2E7D32">'+data.excused_days+'</div><div class="l">مبرر</div></div>'+
    '<div class="sc"><div class="v" style="color:#C62828">'+data.unexcused_days+'</div><div class="l">غير مبرر</div></div>'+
    '<div class="sc"><div class="v" style="color:#E65100">'+data.total_tardiness+'</div><div class="l">تأخر</div></div>'+
    '<div class="sc"><div class="v" style="color:#0277BD">'+(data.total_permissions||0)+'</div><div class="l">استئذانات</div></div>'+
    '</div><div class="section"><div class="st">آخر الغيابات</div><div class="tw"><table><thead><tr><th>التاريخ</th><th>الفصل</th><th>الحصة</th></tr></thead><tbody>'+
    (data.absence_rows||[]).slice(0,10).map(function(r){return '<tr><td>'+r.date+'</td><td>'+r.class_name+'</td><td>'+(r.period||'-')+'</td></tr>';}).join('')+
    '</tbody></table></div></div>';
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
  window._students=all;renderStuTbl(all);
  var sm=document.getElementById('sm-sum');if(sm)sm.innerHTML='<span class="badge bb">'+all.length+' طالب إجمالاً</span>';
}
function filterStudents(){
  var q=(document.getElementById('sm-q')||document.getElementById('ph-q')||{value:''}).value.toLowerCase();
  var cls=(document.getElementById('sm-cls')||document.getElementById('ph-cls')||{value:''}).value;
  var f=(window._students||[]).filter(function(s){return(!q||(s.name||'').toLowerCase().includes(q)||(s.id||'').includes(q))&&(!cls||s.class_id===cls);});
  renderStuTbl(f);renderPhoTbl(f);
}
function renderStuTbl(arr){
  var tb=document.getElementById('sm-table');if(!tb)return;
  tb.innerHTML=arr.slice(0,200).map(function(s){
    return '<tr><td>'+s.id+'</td><td>'+s.name+'</td><td>'+(s.level||'-')+'</td><td>'+s.class_name+'</td>'+
           '<td>'+(s.phone||'—')+'</td><td><button class="btn bp2 bsm" onclick="editPhone(\''+s.id+'\')">✏️ تعديل</button></td></tr>';
  }).join('')||'<tr><td colspan="6" style="color:#9CA3AF">لا يوجد</td></tr>';
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
async function loadUsers(){
  var d=await api('/web/api/users');if(!d||!d.ok){document.getElementById('us-table').innerHTML='';return;}
  var rl={admin:'مدير',deputy:'وكيل',teacher:'معلم',guard:'حارس'};
  document.getElementById('us-table').innerHTML=(d.users||[]).map(function(u){
    return '<tr><td>'+u.username+'</td><td>'+(u.full_name||'-')+'</td>'+
           '<td><span class="badge bb">'+(rl[u.role]||u.role)+'</span></td>'+
           '<td>'+(u.active?'<span class="badge bg">نشط</span>':'<span class="badge br">معطل</span>')+'</td>'+
           '<td><button class="btn bp3 bsm" onclick="delUser('+u.id+')">حذف</button></td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا يوجد</td></tr>';
}
async function addUser(){
  var un=document.getElementById('us-uname').value.trim();var fn=document.getElementById('us-fname').value.trim();
  var pw=document.getElementById('us-pw').value;var rl=document.getElementById('us-role').value;
  if(!un||!pw){ss('us-st','اكمل الحقول المطلوبة','er');return;}
  var r=await fetch('/web/api/add-user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:un,full_name:fn,password:pw,role:rl})});
  var d=await r.json();ss('us-st',d.ok?'✅ تم الإضافة':'❌ '+(d.msg||'خطأ'),d.ok?'ok':'er');
  if(d.ok)loadUsers();
}
async function delUser(id){if(!confirm('حذف هذا المستخدم؟'))return;
  var r=await fetch('/web/api/delete-user/'+id,{method:'DELETE'});var d=await r.json();if(d.ok)loadUsers();}

/* ── BACKUP ── */
async function loadBackups(){
  var d=await api('/web/api/backups');if(!d||!d.ok){document.getElementById('bk-table').innerHTML='';return;}
  document.getElementById('bk-table').innerHTML=(d.backups||[]).map(function(b){
    return '<tr><td style="font-size:12px">'+b.filename.split('/').pop().split('\\').pop()+'</td><td>'+(b.size_kb||0)+' KB</td>'+
           '<td style="font-size:12px">'+b.created_at+'</td>'+
           '<td><a href="/web/api/download-backup/'+encodeURIComponent(b.filename)+'" class="btn bp1 bsm">⬇️</a></td>'+
           '<td><button class="btn bp5 bsm" onclick="alert(\'استعادة: '+b.filename.split('/').pop()+'\')">استعادة</button></td></tr>';
  }).join('')||'<tr><td colspan="5" style="color:#9CA3AF">لا توجد نسخ</td></tr>';
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
    
    return '<tr style="'+bg+'">'+
      '<td>'+r.student_id+'</td>'+
      '<td><strong>'+r.student_name+'</strong></td>'+
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
  } else {
    payload.date=document.getElementById('tfp-date').value || new Date().toISOString().split('T')[0];
    payload.executor=document.getElementById('tfp-exec').value;
    payload.place=document.getElementById('tfp-place').value;
    payload.target=document.getElementById('tfp-target').value;
    payload.count=document.getElementById('tfp-count').value;
    payload.goals=document.getElementById('tfp-goals').value.split('\n').filter(Boolean);
    payload.img1_b64 = await toBase64(document.getElementById('tfp-img1').files[0]);
    payload.img2_b64 = await toBase64(document.getElementById('tfp-img2').files[0]);
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
    renderGaHtml(d.html);
  }catch(e){
    ss('ga-st','❌ خطأ في الاتصال','er');
    document.getElementById('ga-res').innerHTML='<div class="ab ae">❌ خطأ في الاتصال</div>';
  }
}
function renderGaHtml(html){
  // عرض HTML في iframe لعزل الأنماط ومنع تعارضها مع الصفحة
  var box=document.getElementById('ga-res');
  box.innerHTML='<iframe id="ga-frame" style="width:100%;height:800px;border:1px solid var(--bd);border-radius:var(--rd);background:#fff" sandbox="allow-same-origin"></iframe>'+
    '<div style="margin-top:8px;text-align:left"><button class="btn bp4 bsm" onclick="printGaFrame()">🖨️ طباعة التقرير</button></div>';
  var iframe=document.getElementById('ga-frame');
  var doc=iframe.contentDocument||iframe.contentWindow.document;
  doc.open();
  doc.write('<!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><style>body{margin:0;font-family:Tahoma,Arial,sans-serif;direction:rtl}</style></head><body>'+html+'</body></html>');
  doc.close();
}
function printGaFrame(){
  var iframe=document.getElementById('ga-frame');
  if(iframe&&iframe.contentWindow){iframe.contentWindow.focus();iframe.contentWindow.print();}
}

/* ── REPORT HELPERS ── */
async function loadClassReport(){
  var cid=document.getElementById('tr-cls').value;
  if(!cid){ss('tr-st','اختر فصلاً','er');return;}
  var box=document.getElementById('tr-res');
  if(box)box.innerHTML='<div class="loading">⏳</div>';
  try{
    var d=await api('/web/api/class-report?class_id='+encodeURIComponent(cid));
    if(!d||!d.ok){if(box)box.innerHTML='<div class="ab ae">❌ '+((d&&d.msg)||'فشل')+'</div>';return;}
    var html='<div class="stat-cards">'+
      crd(d.students||0,'#1565C0','عدد الطلاب','👨‍🎓')+
      crd(d.total_absences||0,'#C62828','إجمالي الغياب','🔴')+
      crd(d.total_tardiness||0,'#E65100','إجمالي التأخر','⏰')+
      crd((d.avg_absent_per_student||0).toFixed(1),'#7c3aed','متوسط الغياب/طالب','📊')+
      '</div>';
    html+='<div class="section"><div class="st">الطلاب مرتبون حسب الغياب</div><div class="tw"><table><thead><tr><th>#</th><th>الطالب</th><th>أيام الغياب</th><th>التأخر</th></tr></thead><tbody>';
    (d.rows||[]).forEach(function(r,i){
      html+='<tr><td>'+(i+1)+'</td><td>'+r.name+'</td><td>'+r.absences+'</td><td>'+r.tardiness+'</td></tr>';
    });
    html+='</tbody></table></div></div>';
    if(box)box.innerHTML=html;else alert('✅ تم التحميل');
  }catch(e){if(box)box.innerHTML='<div class="ab ae">❌ خطأ</div>';}
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

/* ── NOTES ── */
function renderNotes(){
  var cols={info:'#DBEAFE',warning:'#FEF3C7',task:'#DCFCE7'};var ics={info:'ℹ️',warning:'⚠️',task:'✅'};
  document.getElementById('qn-list').innerHTML=_notes.length
    ?_notes.map(function(n,i){return '<div style="display:flex;align-items:start;gap:10px;padding:12px;background:'+(cols[n.type]||'#F8FAFF')+';border-radius:8px;margin-bottom:8px">'+
        '<span style="font-size:18px">'+(ics[n.type]||'📝')+'</span>'+
        '<div style="flex:1"><div style="font-size:13px">'+n.text+'</div>'+
        '<div style="font-size:11px;color:var(--mu);margin-top:4px">'+n.date+'</div></div>'+
        '<button onclick="delNote('+i+')" style="background:none;border:none;cursor:pointer;color:#94A3B8;font-size:18px">×</button></div>';}).join('')
    :'<p style="color:#94A3B8;text-align:center;padding:30px">لا توجد ملاحظات</p>';
}
function addNote(){
  var text=document.getElementById('qn-text').value.trim();var type=document.getElementById('qn-type').value;
  if(!text)return;_notes.unshift({text:text,type:type,date:new Date().toLocaleString('ar-SA')});
  try{localStorage.setItem('darb_notes',JSON.stringify(_notes));}catch(e){}
  document.getElementById('qn-text').value='';renderNotes();
}
function delNote(i){_notes.splice(i,1);try{localStorage.setItem('darb_notes',JSON.stringify(_notes));}catch(e){}renderNotes();}

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
       dt.teachers.map(function(t){return '<option value="'+t.username+'">'+t.full_name+'</option>';}).join('');
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

"""

    return (
        '<!DOCTYPE html><html lang="ar" dir="rtl"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">'
        '<title>' + school + ' — لوحة التحكم</title>'
        '<style>' + css + '</style>'
        '</head><body>'
        '<div class="topbar">'
        '<div class="tb-l">'
        '<button id="mt" onclick="toggleSidebar()" aria-label="القائمة">'
        '<span></span><span></span><span></span></button>'
        '<h1><i class="fas fa-university" style="margin-left:8px;font-size:18px"></i> <span id="sc-name">' + school + '</span></h1>'
        '</div>'
        '<div class="tb-r">'
        '<div class="ub"><i class="fas fa-user-circle" style="margin-left:6px"></i> <span id="user-name">أهلاً بك...</span></div>'
        '<a href="/web/logout" class="lo">خروج</a>'
        '</div></div>'
        '<div id="ov" onclick="closeSidebar()"></div>'
        '<div class="sidebar" id="sb">' + sidebar_html + '</div>'
        '<div class="content">'
        '<div id="tc">'
        + content_html +
        '</div></div>'
        '<script>' + js + '</script>'
        '</body></html>'
    )




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
            with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
            load_students(force_reload=True)
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "msg": "الطالب غير موجود"})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


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
        ref_type = (data.get("type") or "غياب").strip()
        students = data.get("students") or []
        if ref_type not in ("غياب", "تأخر"):
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

        import json as _j
        with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
            _j.dump({"classes": classes}, f, ensure_ascii=False, indent=2)

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
async def web_class_report(request: Request, class_id: str = ""):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        if not class_id:
            return JSONResponse({"ok": False, "msg": "class_id مطلوب"})

        store = load_students(force_reload=False)
        target = None
        for c in store.get("list", []):
            if c.get("id") == class_id or c.get("name") == class_id:
                target = c; break
        if not target:
            return JSONResponse({"ok": False, "msg": "الفصل غير موجود"})

        students = target.get("students", [])
        cid_actual = target.get("id") or class_id

        # حساب الغياب والتأخر لكل طالب
        con = get_db(); cur = con.cursor()
        abs_rows = cur.execute(
            "SELECT student_id, COUNT(DISTINCT date) as cnt FROM absences WHERE class_id=? GROUP BY student_id",
            (cid_actual,)
        ).fetchall()
        tard_rows = cur.execute(
            "SELECT student_id, COUNT(*) as cnt FROM tardiness WHERE class_id=? GROUP BY student_id",
            (cid_actual,)
        ).fetchall()
        abs_map  = {str(r["student_id"]): r["cnt"] for r in abs_rows}
        tard_map = {str(r["student_id"]): r["cnt"] for r in tard_rows}

        rows = []
        total_abs = 0; total_tard = 0
        for s in students:
            sid = str(s.get("id"))
            a = abs_map.get(sid, 0)
            t = tard_map.get(sid, 0)
            total_abs += a; total_tard += t
            rows.append({"id": sid, "name": s.get("name",""), "absences": a, "tardiness": t})
        rows.sort(key=lambda r: -r["absences"])

        n = max(len(students), 1)
        return JSONResponse({
            "ok": True,
            "class_name": target.get("name",""),
            "students": len(students),
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
        # محاولة جلب آخر HTML محفوظ
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

        # حفظ مؤقت للملف
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix="ga_")
        content = await upload.read()
        tmp.write(content); tmp.close()

        try:
            # التحليل بنفس محرّك التطبيق المكتبي
            students = _ga_parse_file(tmp.name)
            if not students:
                return JSONResponse({"ok": False, "msg": "لم يُعثر على بيانات طلاب في الملف"})

            # بناء HTML بنفس دالة التطبيق المكتبي
            html = _ga_build_html(students)

            # حفظ كاش لاستعادتها لاحقاً
            cache_dir = os.path.join(DATA_DIR, "grade_analysis")
            os.makedirs(cache_dir, exist_ok=True)
            with open(os.path.join(cache_dir, "last_analysis.html"), "w", encoding="utf-8") as f:
                f.write(html)

            # ملخص سريع للإحصائيات
            total_students = len(students)
            all_pcts = []
            for s in students:
                for sub in s.get("subjects", []):
                    if sub.get("max_score", 0) > 0:
                        all_pcts.append(sub["score"] / sub["max_score"] * 100)
            avg = round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0
            pass_rate = round(sum(1 for p in all_pcts if p >= 50) / len(all_pcts) * 100, 1) if all_pcts else 0

            return JSONResponse({
                "ok": True,
                "html": html,
                "students": total_students,
                "average": avg,
                "pass_rate": pass_rate
            })
        finally:
            try: os.unlink(tmp.name)
            except Exception: pass
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "msg": str(e), "trace": traceback.format_exc()[:500]}, status_code=500)


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
        data["teacher_name"] = user.get("full_name", user.get("username", "معلم"))
        
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
        return JSONResponse({"ok": False, "msg": "غير مصرح - للمدير فقط"}, status_code=401)
    
    try:
        att_path = ""
        if file and file.filename:
            # Ensure data/attachments/circulars exists
            rel_dir = os.path.join("attachments", "circulars")
            abs_dir = os.path.join(DATA_DIR, rel_dir)
            os.makedirs(abs_dir, exist_ok=True)
            
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r'[^\w\.-]', '_', file.filename)
            att_name = f"{ts}_{safe_name}"
            att_path = os.path.join(rel_dir, att_name)
            
            with open(os.path.join(abs_dir, att_name), "wb") as buffer:
                buffer.write(await file.read())
        
        c_id = create_circular({
            "title": title,
            "target_role": target_role.lower(), # توحيد الحالة
            "content": content,
            "attachment_path": att_path,
            "created_by": user.get("name") or user["sub"]
        })
        return JSONResponse({"ok": True, "id": c_id})
    except Exception as e:
        print(f"[ERROR] web_create_circular: {e}")
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/circulars/list", response_class=JSONResponse)
async def web_list_circulars(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        # جلب التعاميم مع حالة القراءة الصحيحة
        rows = get_circulars(user["sub"], user["role"])
        return JSONResponse({"ok": True, "rows": rows})
    except Exception as e:
        print(f"[ERROR] web_list_circulars: {e}")
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/circulars/mark-read", response_class=JSONResponse)
async def web_mark_read_circular(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        mark_circular_as_read(int(data["id"]), user["sub"])
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/circulars/delete/{cid}", response_class=JSONResponse)
async def web_delete_circular(request: Request, cid: int):
    user = _get_current_user(request)
    if not user or user["role"] != "admin":
        return JSONResponse({"ok": False, "msg": "غير مصرح للمدير فقط"}, status_code=401)
    try:
        delete_circular(cid)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.get("/web/api/circulars/unread-count", response_class=JSONResponse)
async def web_unread_circulars_count(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        # حساب التنبيهات بناءً على التعاميم غير المقروءة
        circs = get_circulars(user["sub"], user["role"])
        unread = sum(1 for c in circs if not c.get("is_read") and user["role"] != "admin")
        return JSONResponse({"ok": True, "count": unread})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)

@router.post("/web/api/send-teacher-form", response_class=JSONResponse)
async def web_send_teacher_form(request: Request):
    user = _get_current_user(request)
    if not user: return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=401)
    try:
        data = await request.json()
        teacher_name = user.get("full_name", user.get("username", "معلم"))
        data["teacher_name"] = teacher_name
        
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
            caption = f"📘 نموذج تحضير درس\nالمعلم: {teacher_name}\nالمادة: {data.get('subject','')}\nالتاريخ: {data.get('date','')}"
        else:
            pdf_bytes = generate_program_pdf(data)
            caption = f"📊 تقرير تنفيذ تقوية\nالمنفذ: {data.get('executor','')}\nالتاريخ: {data.get('date','')}"
            
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

# ===================== main =====================

if __name__ == "__main__":
    pass
