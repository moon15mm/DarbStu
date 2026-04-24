# -*- coding: utf-8 -*-
"""
api/lab_docs_routes.py — توثيق شواهد الأداء الوظيفي لمحضر المختبر
يخدم صفحة HTML التفاعلية ويوفر API للحفظ والتحميل من قاعدة البيانات.
"""
import os, json, datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from database import get_db
from constants import BASE_DIR

router = APIRouter()


def _get_current_user(request: Request) -> dict:
    from api.web_routes import _get_current_user as _web_get_user
    return _web_get_user(request)


def _ensure_table():
    con = get_db(); cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lab_docs (
            username   TEXT PRIMARY KEY,
            form_data  TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lab_doc_submissions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT NOT NULL,
            form_data    TEXT NOT NULL DEFAULT '{}',
            submitted_at TEXT NOT NULL,
            is_read      INTEGER NOT NULL DEFAULT 0
        )
    """)
    con.commit(); con.close()

_ensure_table()


# ── سكريبت يُحقن في <head> — يجعل localStorage مرتبطاً بالمستخدم ──────────
_HEAD_INJECT = """
<script>
/* === DarbStu: localStorage per-user isolation === */
(function(){
  var u = (window.__LAB_USER__ && window.__LAB_USER__.username) ? window.__LAB_USER__.username : 'anon';
  var origKey = 'lab_perf_data_v1';
  var userKey = 'lab_perf_data_v1_' + u;
  var gi = Storage.prototype.getItem;
  var si = Storage.prototype.setItem;
  var ri = Storage.prototype.removeItem;
  Storage.prototype.getItem    = function(k){ return gi.call(this, k===origKey ? userKey : k); };
  Storage.prototype.setItem    = function(k,v){ return si.call(this, k===origKey ? userKey : k, v); };
  Storage.prototype.removeItem = function(k){ return ri.call(this, k===origKey ? userKey : k); };
})();
</script>
"""


def _body_inject(username: str) -> str:
    """سكريبت يُحقن قبل </body> — يخفي Google Drive ويضيف مزامنة الخادم."""
    return f"""
<script>
/* === DarbStu: Lab Docs Server Sync === */
(function(){{
  // ── إخفاء شريط Google Drive ────────────────────────────────
  var gdb = document.getElementById('gdrive-bar');
  if (gdb) {{ gdb.style.display = 'none'; document.body.style.paddingBottom = '0'; }}

  // ── إضافة بانر التعريف بالمستخدم ───────────────────────────
  var topbar = document.querySelector('.page-topbar');
  if (topbar) {{
    var banner = document.createElement('div');
    banner.style.cssText = 'background:#0f6e56;color:#9ee8d4;padding:5px 20px;font-size:12px;font-weight:700;text-align:right;font-family:Cairo,sans-serif;direction:rtl;display:flex;align-items:center;gap:8px;';
    banner.innerHTML = '📋 بيانات هذه الصفحة خاصة بـ <strong style="color:#f4c542">{username}</strong> — لا تنتقل لأي مستخدم آخر &nbsp;|&nbsp; <span id="srv-status" style="color:#7ee8c8;font-weight:400"></span>';
    topbar.insertAdjacentElement('afterend', banner);
  }}

  function showStatus(msg, color) {{
    var el = document.getElementById('srv-status');
    if (el) {{ el.textContent = msg; el.style.color = color || '#7ee8c8'; }}
  }}

  // ── تحميل البيانات من الخادم ────────────────────────────────
  async function loadFromServer() {{
    try {{
      var r = await fetch('/web/api/lab-docs/load');
      if (!r.ok) return;
      var d = await r.json();
      if (d.ok && d.form_data) {{
        localStorage.setItem('lab_perf_data_v1', d.form_data);
        if (typeof restoreAllData === 'function') restoreAllData();
        var ts = d.updated_at ? ' (آخر حفظ: ' + d.updated_at.substring(0,16).replace('T',' ') + ')' : '';
        showStatus('✅ تم التحميل من الخادم' + ts, '#7ee8c8');
        setTimeout(function(){{ showStatus(''); }}, 4000);
      }} else {{
        showStatus('📭 لا توجد بيانات محفوظة بعد', '#f4c542');
        setTimeout(function(){{ showStatus(''); }}, 3000);
      }}
    }} catch(e) {{
      showStatus('⚠️ تعذّر الاتصال بالخادم', '#ff9090');
    }}
  }}

  // ── حفظ البيانات على الخادم ─────────────────────────────────
  var _saveTimer = null;
  async function saveToServer() {{
    try {{
      var raw = localStorage.getItem('lab_perf_data_v1');
      if (!raw) return;
      showStatus('⏳ جارٍ الحفظ...', '#f4c542');
      var r = await fetch('/web/api/lab-docs/save', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ form_data: raw }})
      }});
      var d = await r.json();
      if (d.ok) {{
        showStatus('✅ محفوظ', '#7ee8c8');
        setTimeout(function(){{ showStatus(''); }}, 2000);
      }} else {{
        showStatus('❌ فشل الحفظ: ' + (d.msg || ''), '#ff9090');
      }}
    }} catch(e) {{
      showStatus('❌ خطأ في الحفظ', '#ff9090');
    }}
  }}

  // ── تغليف saveAllData لإضافة الحفظ على الخادم ───────────────
  window.addEventListener('load', function() {{
    var _orig = window.saveAllData;
    if (typeof _orig === 'function') {{
      window.saveAllData = function() {{
        _orig.apply(this, arguments);
        clearTimeout(_saveTimer);
        _saveTimer = setTimeout(saveToServer, 2000);
      }};
    }}
    // تحميل البيانات من الخادم عند بدء التشغيل
    loadFromServer();
  }});

  // ── تغليف clearAllData للتأكيد الإضافي ─────────────────────
  window.addEventListener('load', function() {{
    var _origClear = window.clearAllData;
    if (typeof _origClear === 'function') {{
      window.clearAllData = function() {{
        if (!confirm('⚠️ سيتم حذف جميع بياناتك من الخادم أيضاً. هل أنت متأكد؟')) return;
        localStorage.removeItem('lab_perf_data_v1');
        fetch('/web/api/lab-docs/clear', {{ method: 'POST' }});
        location.reload();
      }};
    }}
  }});

  // ── زر إرسال الملف للمدير ────────────────────────────────────
  window.addEventListener('load', function() {{
    var topbar = document.querySelector('.page-topbar');
    if (!topbar) return;
    var sendBtn = document.createElement('button');
    sendBtn.textContent = '📤 إرسال للمدير';
    sendBtn.style.cssText = 'position:fixed;bottom:22px;left:22px;z-index:9999;background:#1565C0;color:white;border:none;border-radius:10px;padding:12px 20px;font-size:14px;font-weight:700;font-family:Cairo,sans-serif;cursor:pointer;box-shadow:0 4px 14px rgba(21,101,192,0.45);direction:rtl';
    sendBtn.onclick = async function() {{
      if (!confirm('📤 هل تريد إرسال نسخة من شواهد أدائك الوظيفي إلى مدير المدرسة الآن؟')) return;
      var raw = localStorage.getItem('lab_perf_data_v1');
      if (!raw) {{ alert('⚠️ لا توجد بيانات محفوظة بعد — احفظ أولاً ثم أرسل.'); return; }}
      sendBtn.disabled = true; sendBtn.textContent = '⏳ جارٍ الإرسال...';
      try {{
        var r = await fetch('/web/api/lab-docs/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ form_data: raw }})
        }});
        var d = await r.json();
        if (d.ok) {{
          alert('✅ تم الإرسال بنجاح! سيصل التنبيه للمدير.');
        }} else {{
          alert('❌ فشل الإرسال: ' + (d.msg || 'خطأ غير معروف'));
        }}
      }} catch(e) {{
        alert('❌ تعذّر الاتصال بالخادم');
      }}
      sendBtn.disabled = false; sendBtn.textContent = '📤 إرسال للمدير';
    }};
    document.body.appendChild(sendBtn);
  }});
}})();
</script>
"""


@router.get("/web/lab-docs", response_class=HTMLResponse)
async def lab_docs_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/web/login")
    if user.get("role") not in ("lab", "admin"):
        return HTMLResponse(
            "<html dir='rtl'><body style='font-family:Cairo,sans-serif;"
            "text-align:center;padding:80px;background:#f0f4f3'>"
            "<h2 style='color:#e24b4a'>⛔ غير مصرح — هذه الصفحة للمحضر فقط</h2>"
            "<a href='/web/dashboard' style='color:#2da88a'>العودة للوحة التحكم</a>"
            "</body></html>",
            status_code=403
        )

    username = user.get("username", "")
    html_path = os.path.join(BASE_DIR, "lab_docs.html")

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return HTMLResponse(
            "<html dir='rtl'><body style='font-family:Cairo,sans-serif;"
            "text-align:center;padding:80px;background:#f0f4f3'>"
            f"<h2 style='color:#e24b4a'>⚠️ ملف lab_docs.html غير موجود</h2>"
            f"<p style='color:#555'>يرجى وضع الملف في: <code>{html_path}</code></p>"
            "<a href='/web/dashboard' style='color:#2da88a'>العودة للوحة التحكم</a>"
            "</body></html>",
            status_code=500
        )

    # حقن السياق قبل </head>
    user_ctx = f'<script>window.__LAB_USER__={json.dumps({"username": username})};</script>'
    html = html.replace('</head>', user_ctx + _HEAD_INJECT + '</head>', 1)

    # حقن المزامنة قبل </body>
    html = html.replace('</body>', _body_inject(username) + '</body>', 1)

    return HTMLResponse(html)


@router.get("/web/api/lab-docs/load")
async def lab_docs_load(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") not in ("lab", "admin"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)

    username = user.get("username", "")
    con = get_db(); cur = con.cursor()
    try:
        cur.execute(
            "SELECT form_data, updated_at FROM lab_docs WHERE username = ?",
            (username,)
        )
        row = cur.fetchone()
        if row:
            return JSONResponse({"ok": True, "form_data": row[0], "updated_at": row[1]})
        return JSONResponse({"ok": True, "form_data": None, "updated_at": None})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})
    finally:
        con.close()


@router.post("/web/api/lab-docs/save")
async def lab_docs_save(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") not in ("lab", "admin"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)

    username = user.get("username", "")
    try:
        body = await request.json()
        form_data = body.get("form_data", "{}")
        if not isinstance(form_data, str):
            form_data = json.dumps(form_data)
        now = datetime.datetime.now().isoformat()

        con = get_db(); cur = con.cursor()
        cur.execute("""
            INSERT INTO lab_docs (username, form_data, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                form_data  = excluded.form_data,
                updated_at = excluded.updated_at
        """, (username, form_data, now))
        con.commit(); con.close()
        return JSONResponse({"ok": True, "updated_at": now})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})


@router.post("/web/api/lab-docs/clear")
async def lab_docs_clear(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") not in ("lab", "admin"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)

    username = user.get("username", "")
    con = get_db(); cur = con.cursor()
    try:
        cur.execute("DELETE FROM lab_docs WHERE username = ?", (username,))
        con.commit(); con.close()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})


@router.post("/web/api/lab-docs/submit")
async def lab_docs_submit(request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") not in ("lab", "admin"):
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)

    username = user.get("username", "")
    try:
        body = await request.json()
        form_data = body.get("form_data", "{}")
        if not isinstance(form_data, str):
            form_data = json.dumps(form_data)
        now = datetime.datetime.now().isoformat()

        con = get_db(); cur = con.cursor()
        cur.execute("""
            INSERT INTO lab_doc_submissions (username, form_data, submitted_at, is_read)
            VALUES (?, ?, ?, 0)
        """, (username, form_data, now))
        con.commit(); con.close()
        return JSONResponse({"ok": True, "submitted_at": now})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)})


@router.get("/web/lab-docs/submissions", response_class=HTMLResponse)
async def lab_docs_submissions(request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/web/login")
    if user.get("role") != "admin":
        return HTMLResponse(
            "<html dir='rtl'><body style='font-family:Cairo,sans-serif;text-align:center;padding:80px'>"
            "<h2 style='color:#e24b4a'>⛔ غير مصرح — هذه الصفحة للمدير فقط</h2>"
            "<a href='/web/dashboard' style='color:#2da88a'>العودة</a></body></html>",
            status_code=403
        )

    con = get_db(); cur = con.cursor()
    try:
        cur.execute("""
            SELECT id, username, submitted_at, is_read
            FROM lab_doc_submissions
            ORDER BY submitted_at DESC
        """)
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        con.close()

    rows_html = ""
    for row in rows:
        sub_id, uname, sub_at, is_read = row
        badge = "" if is_read else '<span style="background:#ef4444;color:white;padding:2px 8px;border-radius:20px;font-size:11px;margin-right:6px">جديد</span>'
        dt = sub_at[:16].replace("T", " ") if sub_at else ""
        rows_html += f"""
        <tr style="{'background:#fff' if is_read else 'background:#FFF7ED'}">
          <td style="padding:10px 14px;direction:rtl">{badge}{uname}</td>
          <td style="padding:10px 14px;color:#666;font-size:13px">{dt}</td>
          <td style="padding:10px 14px">
            <a href="/web/lab-docs/view/{sub_id}" target="_blank"
               style="background:#1565C0;color:white;padding:6px 14px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:700">
              عرض الملف
            </a>
          </td>
        </tr>"""

    page = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>شواهد الأداء — المُرسَلة للمدير</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
<style>
  body{{font-family:Cairo,sans-serif;background:#f0f4f3;margin:0;padding:20px}}
  .card{{background:white;border-radius:14px;padding:24px;max-width:860px;margin:0 auto;box-shadow:0 2px 12px rgba(0,0,0,0.08)}}
  h2{{color:#0f6e56;margin-top:0}}
  table{{width:100%;border-collapse:collapse}}
  thead tr{{background:#0f6e56;color:white}}
  th{{padding:10px 14px;font-weight:700;text-align:right}}
  tr:hover{{background:#f0fdf9!important}}
  .back{{display:inline-block;margin-bottom:16px;color:#2da88a;text-decoration:none;font-weight:700}}
</style>
</head>
<body>
<div class="card">
  <a class="back" href="/web/dashboard">← العودة للوحة التحكم</a>
  <h2>📋 شواهد الأداء الوظيفي — المُرسَلة للمدير</h2>
  {'<p style="color:#888;text-align:center;padding:30px">لا توجد ملفات مُرسَلة بعد.</p>' if not rows else f'<table><thead><tr><th>المحضر</th><th>تاريخ الإرسال</th><th>الإجراء</th></tr></thead><tbody>{rows_html}</tbody></table>'}
</div>
</body>
</html>"""
    return HTMLResponse(page)


@router.get("/web/lab-docs/view/{sub_id}", response_class=HTMLResponse)
async def lab_docs_view(sub_id: int, request: Request):
    user = _get_current_user(request)
    if not user:
        return RedirectResponse("/web/login")
    if user.get("role") != "admin":
        return HTMLResponse(
            "<html dir='rtl'><body style='font-family:Cairo,sans-serif;text-align:center;padding:80px'>"
            "<h2 style='color:#e24b4a'>⛔ غير مصرح</h2>"
            "<a href='/web/dashboard' style='color:#2da88a'>العودة</a></body></html>",
            status_code=403
        )

    con = get_db(); cur = con.cursor()
    try:
        cur.execute(
            "SELECT username, form_data, submitted_at FROM lab_doc_submissions WHERE id = ?",
            (sub_id,)
        )
        row = cur.fetchone()
        if not row:
            con.close()
            return HTMLResponse(
                "<html dir='rtl'><body style='font-family:Cairo,sans-serif;text-align:center;padding:80px'>"
                "<h2 style='color:#e24b4a'>⚠️ الملف غير موجود</h2>"
                "<a href='/web/lab-docs/submissions' style='color:#2da88a'>العودة للقائمة</a></body></html>",
                status_code=404
            )
        sub_username, form_data, submitted_at = row
        # تحديد is_read = 1
        cur.execute("UPDATE lab_doc_submissions SET is_read = 1 WHERE id = ?", (sub_id,))
        con.commit()
    finally:
        con.close()

    html_path = os.path.join(BASE_DIR, "lab_docs.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return HTMLResponse(
            "<html dir='rtl'><body style='text-align:center;padding:80px'>"
            "<h2>⚠️ ملف lab_docs.html غير موجود</h2></body></html>",
            status_code=500
        )

    dt_str = submitted_at[:16].replace("T", " ") if submitted_at else ""

    # حقن السياق — وضع بيانات النموذج مباشرةً في localStorage ثم تحميلها
    preload_script = f"""<script>
window.__LAB_READONLY__ = true;
window.__LAB_USER__ = {{ username: {json.dumps(sub_username)} }};
/* تحميل البيانات مسبقاً في localStorage بمفتاح خاص بهذه الجلسة */
(function(){{
  var tempKey = 'lab_perf_data_v1___admin_preview_{sub_id}';
  var origKey = 'lab_perf_data_v1';
  var data = {json.dumps(form_data)};
  localStorage.setItem(tempKey, data);
  var gi = Storage.prototype.getItem;
  var si = Storage.prototype.setItem;
  Storage.prototype.getItem = function(k){{ return gi.call(this, k===origKey ? tempKey : k); }};
  Storage.prototype.setItem = function(k,v){{ /* قراءة فقط — لا حفظ */ }};
  Storage.prototype.removeItem = function(k){{ /* قراءة فقط — لا حذف */ }};
}})();
</script>"""

    readonly_banner = f"""<script>
window.addEventListener('load', function() {{
  // إخفاء Google Drive
  var gdb = document.getElementById('gdrive-bar');
  if (gdb) {{ gdb.style.display = 'none'; document.body.style.paddingBottom = '0'; }}

  // بانر القراءة فقط
  var topbar = document.querySelector('.page-topbar');
  if (topbar) {{
    var banner = document.createElement('div');
    banner.style.cssText = 'background:#1565C0;color:white;padding:8px 20px;font-size:13px;font-weight:700;text-align:right;font-family:Cairo,sans-serif;direction:rtl;display:flex;align-items:center;justify-content:space-between;gap:12px;';
    banner.innerHTML = '<span>👁️ عرض شواهد الأداء — <strong>{sub_username}</strong> | أُرسل: {dt_str}</span>' +
      '<a href="/web/lab-docs/submissions" style="color:#9ee8d4;font-weight:400;font-size:12px">← العودة للقائمة</a>';
    topbar.insertAdjacentElement('afterend', banner);
  }}

  // تحميل البيانات من localStorage مباشرةً
  if (typeof restoreAllData === 'function') restoreAllData();

  // تعطيل أزرار الحفظ والمسح
  document.querySelectorAll('button').forEach(function(b) {{
    var t = b.textContent.trim();
    if (t.includes('حفظ') || t.includes('مسح') || t.includes('حذف') || t.includes('Drive')) {{
      b.disabled = true;
      b.style.opacity = '0.4';
      b.title = 'غير متاح في وضع العرض';
    }}
  }});
}});
</script>"""

    html = html.replace('</head>', preload_script + '</head>', 1)
    html = html.replace('</body>', readonly_banner + '</body>', 1)

    return HTMLResponse(html)
