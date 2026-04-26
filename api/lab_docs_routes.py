# -*- coding: utf-8 -*-
"""
api/lab_docs_routes.py — توثيق شواهد الأداء الوظيفي لمحضر المختبر
يخدم صفحة HTML التفاعلية ويوفر API للحفظ والتحميل من قاعدة البيانات.
"""
import os, json, datetime, base64 as _b64
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from database import get_db
from constants import BASE_DIR, DATA_DIR

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
    try:
        cur.execute("ALTER TABLE lab_doc_submissions ADD COLUMN pdf_path TEXT DEFAULT NULL")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE lab_doc_submissions ADD COLUMN full_name TEXT DEFAULT NULL")
    except Exception:
        pass
    con.commit(); con.close()
    os.makedirs(os.path.join(DATA_DIR, "lab_submissions"), exist_ok=True)

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

  // ── زر إرسال الملف للمدير (PDF) ─────────────────────────────
  window.addEventListener('load', function() {{
    var sendBtn = document.createElement('button');
    sendBtn.textContent = '📤 إرسال للمدير';
    sendBtn.style.cssText = 'position:fixed;bottom:22px;left:22px;z-index:9999;background:#1565C0;color:white;border:none;border-radius:10px;padding:12px 20px;font-size:14px;font-weight:700;font-family:Cairo,sans-serif;cursor:pointer;box-shadow:0 4px 14px rgba(21,101,192,0.45);direction:rtl';

    function _loadScript(src) {{
      return new Promise(function(res, rej) {{
        if (document.querySelector('script[src="' + src + '"]')) {{ res(); return; }}
        var s = document.createElement('script');
        s.src = src; s.onload = res; s.onerror = rej;
        document.head.appendChild(s);
      }});
    }}

    sendBtn.onclick = async function() {{
      if (!confirm('📤 هل تريد إرسال ملف PDF لشواهد أدائك الوظيفي إلى مدير المدرسة الآن؟')) return;
      if (typeof saveAllData === 'function') saveAllData();

      // بناء overlay التحميل
      var overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(10,30,25,0.82);z-index:99999;display:flex;align-items:center;justify-content:center';
      overlay.innerHTML = '<div style="background:#fff;padding:36px 44px;border-radius:18px;text-align:center;font-family:Cairo,sans-serif;min-width:300px"><div id="_dstatus" style="font-size:16px;font-weight:700;color:#0f6e56;margin-bottom:8px">⏳ جارٍ تحضير الملف...</div><div style="color:#888;font-size:13px">يُرجى الانتظار</div></div>';
      document.body.appendChild(overlay);
      sendBtn.disabled = true;

      function setStatus(msg) {{
        var el = document.getElementById('_dstatus');
        if (el) el.textContent = msg;
      }}

      try {{
        setStatus('⏳ جارٍ تحميل مكتبات PDF...');
        await _loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
        await _loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');

        setStatus('⏳ جارٍ تحضير الصفحات...');
        // إظهار جميع الصفحات مؤقتاً
        var tmpStyle = document.createElement('style');
        tmpStyle.id = '_ds_tmp';
        tmpStyle.textContent = '#pagesContainer .page{{display:block!important;max-width:860px!important}}';
        document.head.appendChild(tmpStyle);
        await new Promise(function(r){{ setTimeout(r, 350); }});

        var pages = document.querySelectorAll('#pagesContainer .page');
        var {{ jsPDF }} = window.jspdf;
        var pdf = new jsPDF('p', 'mm', 'a4');
        var first = true;

        for (var i = 0; i < pages.length; i++) {{
          setStatus('⏳ جارٍ التقاط الصفحة ' + (i+1) + ' من ' + pages.length + '...');
          var pg = pages[i];
          try {{
            var cvs = await html2canvas(pg, {{
              scale: 1.8,
              useCORS: true,
              allowTaint: true,
              backgroundColor: '#ffffff',
              logging: false,
            }});
            if (cvs.width === 0 || cvs.height === 0) continue;
            var imgData = cvs.toDataURL('image/jpeg', 0.88);
            var ratio = cvs.width / cvs.height;
            var mW = 190, mH = 277;
            var iW = mW, iH = mW / ratio;
            if (iH > mH) {{ iH = mH; iW = mH * ratio; }}
            if (!first) pdf.addPage();
            pdf.addImage(imgData, 'JPEG', (210 - iW) / 2, (297 - iH) / 2, iW, iH);
            first = false;
          }} catch(e) {{ /* تخطّي الصفحة عند خطأ */ }}
        }}

        // إزالة السيتيل المؤقت
        var ts = document.getElementById('_ds_tmp');
        if (ts) ts.remove();

        setStatus('⏳ جارٍ رفع الملف...');
        var pdfB64 = pdf.output('datauristring').split(',')[1];

        var r = await fetch('/web/api/lab-docs/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ pdf_data: pdfB64 }})
        }});
        var d = await r.json();
        overlay.remove();
        if (d.ok) {{
          alert('✅ تم إرسال الملف بنجاح! سيصل التنبيه للمدير.');
        }} else {{
          alert('❌ فشل الإرسال: ' + (d.msg || 'خطأ غير معروف'));
        }}
      }} catch(e) {{
        var ts2 = document.getElementById('_ds_tmp');
        if (ts2) ts2.remove();
        overlay.remove();
        alert('❌ خطأ أثناء إنشاء PDF: ' + e.message);
      }}
      sendBtn.disabled = false; sendBtn.textContent = '📤 إرسال للمدير';
    }};
    document.body.appendChild(sendBtn);
  }});
}})();
</script>
"""


def _build_lab_docs_html(username: str) -> str:
    user_ctx = f'<script>window.__LAB_USER__={json.dumps({"username": username})};</script>'
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>شواهد الأداء الوظيفي — محضر المختبر</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
{user_ctx}
{_HEAD_INJECT}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Cairo,sans-serif;background:#f0f4f3;direction:rtl}}
.page-topbar{{background:#0f6e56;color:white;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;font-size:15px;font-weight:700;position:sticky;top:0;z-index:100}}
.page-topbar a{{color:#9ee8d4;text-decoration:none;font-size:13px}}
.page-tabs{{display:flex;gap:4px;padding:12px 20px;background:#e8f5f1;border-bottom:2px solid #c1e0d7;flex-wrap:wrap}}
.tab-btn{{padding:8px 18px;border:2px solid #0f6e56;border-radius:8px;background:white;color:#0f6e56;font-family:Cairo,sans-serif;font-size:13px;font-weight:700;cursor:pointer;transition:.2s}}
.tab-btn.active{{background:#0f6e56;color:white}}
#pagesContainer{{padding:20px;max-width:900px;margin:0 auto}}
.page{{display:none;background:white;border-radius:16px;padding:28px;box-shadow:0 2px 16px rgba(15,110,86,.1);margin-bottom:20px}}
.page.active{{display:block}}
.page-title{{font-size:20px;font-weight:900;color:#0f6e56;border-bottom:3px solid #0f6e56;padding-bottom:10px;margin-bottom:20px}}
.section-title{{font-size:15px;font-weight:700;color:#065f46;margin:18px 0 10px;background:#e8f5f1;padding:8px 14px;border-radius:8px;border-right:4px solid #0f6e56}}
.field-row{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
.field-row.full{{grid-template-columns:1fr}}
.field-group label{{display:block;font-size:12px;color:#555;font-weight:600;margin-bottom:4px}}
.field-group input,.field-group textarea,.field-group select{{width:100%;border:1.5px solid #d1d5db;border-radius:8px;padding:9px 12px;font-family:Cairo,sans-serif;font-size:13px;color:#222;transition:.2s;background:#fafafa}}
.field-group input:focus,.field-group textarea:focus,.field-group select:focus{{border-color:#0f6e56;background:white;outline:none}}
.field-group textarea{{resize:vertical;min-height:70px}}
.criteria-table{{width:100%;border-collapse:collapse;margin-bottom:18px}}
.criteria-table th{{background:#0f6e56;color:white;padding:10px 12px;font-size:13px;text-align:center}}
.criteria-table th:first-child{{text-align:right}}
.criteria-table td{{padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;vertical-align:middle}}
.criteria-table tr:hover{{background:#f0fdf9}}
.criteria-table .grade-cell{{text-align:center}}
.criteria-table input[type=radio]{{width:16px;height:16px;accent-color:#0f6e56;cursor:pointer}}
.grade-labels{{display:flex;justify-content:space-around;background:#f9fafb;padding:6px 12px;border-radius:6px;margin-bottom:8px;font-size:11px;color:#666;font-weight:600}}
.action-bar{{display:flex;gap:10px;justify-content:flex-end;padding:16px 0;flex-wrap:wrap}}
.btn{{padding:10px 22px;border:none;border-radius:10px;font-family:Cairo,sans-serif;font-size:14px;font-weight:700;cursor:pointer;transition:.2s}}
.btn-save{{background:#0f6e56;color:white}}
.btn-save:hover{{background:#065f46}}
.btn-clear{{background:#ef4444;color:white}}
.btn-clear:hover{{background:#dc2626}}
.btn-print{{background:#1565C0;color:white}}
.btn-print:hover{{background:#0d47a1}}
.score-summary{{background:linear-gradient(135deg,#0f6e56,#065f46);color:white;border-radius:12px;padding:20px;margin-top:20px;text-align:center}}
.score-big{{font-size:52px;font-weight:900;line-height:1}}
.score-label{{font-size:14px;opacity:.85;margin-top:6px}}
.grade-badge{{display:inline-block;padding:6px 20px;border-radius:20px;font-weight:700;font-size:15px;margin-top:10px}}
.grade-ممتاز{{background:#fbbf24;color:#78350f}}
.grade-جيدجداً{{background:#34d399;color:#064e3b}}
.grade-جيد{{background:#60a5fa;color:#1e3a8a}}
.grade-مقبول{{background:#fb923c;color:#7c2d12}}
.grade-ضعيف{{background:#f87171;color:#7f1d1d}}
@media print{{
  .page-topbar,.page-tabs,.action-bar{{display:none!important}}
  .page{{display:block!important;box-shadow:none;margin-bottom:0;page-break-after:always}}
  body{{background:white}}
}}
</style>
</head>
<body>
<div class="page-topbar">
  <span>📋 شواهد الأداء الوظيفي — محضر المختبر</span>
  <a href="/web/dashboard">← لوحة التحكم</a>
</div>

<div class="page-tabs">
  <button class="tab-btn active" onclick="showPage(0,this)">📝 البيانات الشخصية</button>
  <button class="tab-btn" onclick="showPage(1,this)">🔬 الكفايات المختبرية</button>
  <button class="tab-btn" onclick="showPage(2,this)">🎓 الكفايات التربوية</button>
  <button class="tab-btn" onclick="showPage(3,this)">👔 الكفايات الشخصية</button>
  <button class="tab-btn" onclick="showPage(4,this)">📊 التقييم الختامي</button>
</div>

<div id="pagesContainer">

<!-- ═══ صفحة 1: البيانات الشخصية ═══ -->
<div class="page active" id="page-0">
  <div class="page-title">📝 البيانات الشخصية والوظيفية</div>

  <div class="section-title">بيانات المحضر</div>
  <div class="field-row">
    <div class="field-group"><label>الاسم الكامل</label><input type="text" id="p_name" placeholder="اسم المحضر"></div>
    <div class="field-group"><label>رقم الهوية / السجل المدني</label><input type="text" id="p_id" placeholder="1xxxxxxxxx"></div>
  </div>
  <div class="field-row">
    <div class="field-group"><label>التخصص</label><input type="text" id="p_major" placeholder="مثال: كيمياء / أحياء / فيزياء"></div>
    <div class="field-group"><label>المؤهل العلمي</label>
      <select id="p_edu">
        <option value="">-- اختر --</option>
        <option>بكالوريوس</option><option>دبلوم عالٍ</option><option>ماجستير</option><option>دكتوراه</option><option>دبلوم</option>
      </select>
    </div>
  </div>
  <div class="field-row">
    <div class="field-group"><label>عدد سنوات الخبرة في التعليم</label><input type="number" id="p_exp" min="0" placeholder="0"></div>
    <div class="field-group"><label>عدد سنوات الخبرة في المختبر</label><input type="number" id="p_lab_exp" min="0" placeholder="0"></div>
  </div>

  <div class="section-title">بيانات المدرسة والفترة</div>
  <div class="field-row">
    <div class="field-group"><label>اسم المدرسة</label><input type="text" id="p_school" placeholder="اسم المدرسة"></div>
    <div class="field-group"><label>المرحلة الدراسية</label>
      <select id="p_stage">
        <option value="">-- اختر --</option>
        <option>ابتدائي</option><option>متوسط</option><option>ثانوي</option>
      </select>
    </div>
  </div>
  <div class="field-row">
    <div class="field-group"><label>العام الدراسي</label><input type="text" id="p_year" placeholder="مثال: 1446/1447"></div>
    <div class="field-group"><label>الفصل الدراسي</label>
      <select id="p_semester">
        <option value="">-- اختر --</option>
        <option>الأول</option><option>الثاني</option><option>الثالث</option><option>كامل العام</option>
      </select>
    </div>
  </div>

  <div class="action-bar">
    <button class="btn btn-save" onclick="saveAllData()">💾 حفظ البيانات</button>
    <button class="btn btn-print" onclick="window.print()">🖨️ طباعة</button>
  </div>
</div>

<!-- ═══ صفحة 2: الكفايات المختبرية ═══ -->
<div class="page" id="page-1">
  <div class="page-title">🔬 الكفايات المختبرية والتقنية</div>
  <div class="grade-labels">
    <span>ممتاز (5)</span><span>جيد جداً (4)</span><span>جيد (3)</span><span>مقبول (2)</span><span>ضعيف (1)</span>
  </div>

  <div class="section-title">أولاً: إعداد وتجهيز المختبر</div>
  <table class="criteria-table">
    <thead><tr><th>المعيار</th><th>ممتاز</th><th>جيد جداً</th><th>جيد</th><th>مقبول</th><th>ضعيف</th></tr></thead>
    <tbody id="lab-criteria-1"></tbody>
  </table>

  <div class="section-title">ثانياً: صيانة الأجهزة والمعدات</div>
  <table class="criteria-table">
    <thead><tr><th>المعيار</th><th>ممتاز</th><th>جيد جداً</th><th>جيد</th><th>مقبول</th><th>ضعيف</th></tr></thead>
    <tbody id="lab-criteria-2"></tbody>
  </table>

  <div class="section-title">ثالثاً: السلامة والأمان</div>
  <table class="criteria-table">
    <thead><tr><th>المعيار</th><th>ممتاز</th><th>جيد جداً</th><th>جيد</th><th>مقبول</th><th>ضعيف</th></tr></thead>
    <tbody id="lab-criteria-3"></tbody>
  </table>

  <div class="action-bar">
    <button class="btn btn-save" onclick="saveAllData()">💾 حفظ</button>
  </div>
</div>

<!-- ═══ صفحة 3: الكفايات التربوية ═══ -->
<div class="page" id="page-2">
  <div class="page-title">🎓 الكفايات التربوية والتعليمية</div>
  <div class="grade-labels">
    <span>ممتاز (5)</span><span>جيد جداً (4)</span><span>جيد (3)</span><span>مقبول (2)</span><span>ضعيف (1)</span>
  </div>

  <div class="section-title">أولاً: دعم العملية التعليمية</div>
  <table class="criteria-table">
    <thead><tr><th>المعيار</th><th>ممتاز</th><th>جيد جداً</th><th>جيد</th><th>مقبول</th><th>ضعيف</th></tr></thead>
    <tbody id="edu-criteria-1"></tbody>
  </table>

  <div class="section-title">ثانياً: التوثيق والمتابعة</div>
  <table class="criteria-table">
    <thead><tr><th>المعيار</th><th>ممتاز</th><th>جيد جداً</th><th>جيد</th><th>مقبول</th><th>ضعيف</th></tr></thead>
    <tbody id="edu-criteria-2"></tbody>
  </table>

  <div class="action-bar">
    <button class="btn btn-save" onclick="saveAllData()">💾 حفظ</button>
  </div>
</div>

<!-- ═══ صفحة 4: الكفايات الشخصية ═══ -->
<div class="page" id="page-3">
  <div class="page-title">👔 الكفايات الشخصية والمهنية</div>
  <div class="grade-labels">
    <span>ممتاز (5)</span><span>جيد جداً (4)</span><span>جيد (3)</span><span>مقبول (2)</span><span>ضعيف (1)</span>
  </div>

  <div class="section-title">الكفايات الشخصية</div>
  <table class="criteria-table">
    <thead><tr><th>المعيار</th><th>ممتاز</th><th>جيد جداً</th><th>جيد</th><th>مقبول</th><th>ضعيف</th></tr></thead>
    <tbody id="personal-criteria"></tbody>
  </table>

  <div class="section-title">ملاحظات إضافية</div>
  <div class="field-row full">
    <div class="field-group"><label>الإنجازات والمبادرات خلال الفترة</label>
      <textarea id="p_achievements" placeholder="اذكر أبرز الإنجازات والمبادرات..." rows="4"></textarea>
    </div>
  </div>
  <div class="field-row full">
    <div class="field-group"><label>احتياجات التطوير المهني</label>
      <textarea id="p_development" placeholder="الدورات والتدريبات المطلوبة..." rows="3"></textarea>
    </div>
  </div>

  <div class="action-bar">
    <button class="btn btn-save" onclick="saveAllData()">💾 حفظ</button>
  </div>
</div>

<!-- ═══ صفحة 5: التقييم الختامي ═══ -->
<div class="page" id="page-4">
  <div class="page-title">📊 التقييم الختامي والتوصيات</div>

  <div class="score-summary">
    <div class="score-big" id="final-score">--</div>
    <div class="score-label">الدرجة الكلية من 100</div>
    <div id="final-grade-badge"></div>
  </div>

  <div class="section-title" style="margin-top:20px">ملاحظات المقيّم</div>
  <div class="field-row full">
    <div class="field-group"><label>نقاط القوة</label>
      <textarea id="eval_strengths" placeholder="أبرز نقاط القوة..." rows="3"></textarea>
    </div>
  </div>
  <div class="field-row full">
    <div class="field-group"><label>جوانب تحتاج تحسيناً</label>
      <textarea id="eval_improvements" placeholder="الجوانب التي تحتاج تطوير..." rows="3"></textarea>
    </div>
  </div>
  <div class="field-row full">
    <div class="field-group"><label>التوصيات</label>
      <textarea id="eval_recommendations" placeholder="توصيات للمحضر..." rows="3"></textarea>
    </div>
  </div>

  <div class="field-row">
    <div class="field-group"><label>اسم المقيّم / المدير</label><input type="text" id="eval_name" placeholder="اسم مدير المدرسة"></div>
    <div class="field-group"><label>تاريخ التقييم</label><input type="date" id="eval_date"></div>
  </div>

  <div class="action-bar">
    <button class="btn btn-save" onclick="saveAllData()">💾 حفظ الكل</button>
    <button class="btn btn-print" onclick="window.print()">🖨️ طباعة التقرير</button>
    <button class="btn btn-clear" onclick="clearAllData()">🗑 مسح الكل</button>
  </div>
</div>

</div><!-- /pagesContainer -->

<script>
/* ══════════════════════════════════════════
   بيانات معايير التقييم
══════════════════════════════════════════ */
var CRITERIA = {{
  'lab-criteria-1': [
    'تجهيز المختبر قبل الحصة بالمواد والأدوات اللازمة',
    'ترتيب وتنظيم المختبر وفق معايير السلامة',
    'حفظ وتخزين المواد الكيميائية بطريقة صحيحة وآمنة',
    'توفير مستلزمات التجارب في الوقت المناسب',
    'متابعة مستوى المخزون وطلب المستلزمات عند الحاجة',
  ],
  'lab-criteria-2': [
    'صيانة الأجهزة والمعدات وإبلاغ الجهات المعنية عند العطل',
    'التحقق من سلامة وجاهزية الأجهزة قبل استخدامها',
    'توثيق العمليات الدورية لصيانة المعدات',
    'حفظ سجلات دقيقة لجميع المعدات والأجهزة',
    'التعامل الصحيح مع الأجهزة الدقيقة والحساسة',
  ],
  'lab-criteria-3': [
    'الالتزام بتعليمات السلامة ومتطلبات الوقاية',
    'توفير معدات الحماية الشخصية وضمان استخدامها',
    'التعامل الآمن مع المواد الكيميائية والخطرة',
    'وجود خطة واضحة للتعامل مع حالات الطوارئ',
    'توعية الطلاب بقواعد السلامة داخل المختبر',
  ],
  'edu-criteria-1': [
    'المساعدة في إعداد وتنفيذ التجارب العلمية',
    'توضيح أساليب الاستخدام الصحيح للأدوات للطلاب',
    'التعاون مع المعلمين لإنجاح العملية التعليمية',
    'تقديم الدعم والمساندة للطلاب أثناء التجارب',
    'المساهمة في تطوير بيئة تعليمية محفزة',
  ],
  'edu-criteria-2': [
    'توثيق التجارب والأنشطة المختبرية بدقة',
    'الاحتفاظ بسجلات منتظمة لاستخدام المختبر',
    'إعداد التقارير الدورية عن الوضع العام للمختبر',
    'متابعة الكسر والفقدان وتوثيقه رسمياً',
    'المشاركة في الجرد الدوري للمواد والأجهزة',
  ],
  'personal-criteria': [
    'الالتزام بمواعيد الدوام والحضور المنتظم',
    'الانضباط والتصرف المهني في بيئة العمل',
    'التعاون وروح الفريق مع الزملاء والإدارة',
    'المبادرة وتقديم اقتراحات لتحسين العمل',
    'الاستعداد للتطوير المهني والتدريب المستمر',
    'الأمانة والنزاهة في العمل',
    'حسن التواصل مع الطلاب والمعلمين والإدارة',
  ],
}};

/* ══ بناء جداول التقييم ══ */
Object.keys(CRITERIA).forEach(function(tbodyId) {{
  var tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  CRITERIA[tbodyId].forEach(function(text, i) {{
    var key = tbodyId + '_' + i;
    var tr = document.createElement('tr');
    var grades = ['5','4','3','2','1'];
    var cells = '<td>' + text + '</td>';
    grades.forEach(function(g) {{
      cells += '<td class="grade-cell"><input type="radio" name="' + key + '" value="' + g + '" onchange="updateScore()"></td>';
    }});
    tr.innerHTML = cells;
    tbody.appendChild(tr);
  }});
}});

/* ══ التنقل بين الصفحات ══ */
function showPage(idx, btn) {{
  document.querySelectorAll('.page').forEach(function(p,i){{ p.classList.toggle('active', i===idx); }});
  document.querySelectorAll('.tab-btn').forEach(function(b){{ b.classList.remove('active'); }});
  if (btn) btn.classList.add('active');
  if (idx === 4) updateScore();
}}

/* ══ حساب الدرجة الكلية ══ */
function updateScore() {{
  var total = 0, count = 0;
  document.querySelectorAll('input[type=radio]:checked').forEach(function(r) {{
    total += parseInt(r.value); count++;
  }});
  var maxScore = 0;
  Object.values(CRITERIA).forEach(function(arr){{ maxScore += arr.length * 5; }});
  var pct = maxScore > 0 ? Math.round((total / maxScore) * 100) : 0;
  var el = document.getElementById('final-score');
  var badge = document.getElementById('final-grade-badge');
  if (el) el.textContent = pct;
  if (badge) {{
    var g = pct >= 90 ? 'ممتاز' : pct >= 80 ? 'جيدجداً' : pct >= 70 ? 'جيد' : pct >= 60 ? 'مقبول' : 'ضعيف';
    var gl = pct >= 90 ? 'ممتاز' : pct >= 80 ? 'جيد جداً' : pct >= 70 ? 'جيد' : pct >= 60 ? 'مقبول' : 'ضعيف';
    badge.innerHTML = '<span class="grade-badge grade-' + g + '">' + gl + '</span>';
  }}
}}

/* ══ حفظ واسترجاع البيانات ══ */
var _KEY = 'lab_perf_data_v1';

function saveAllData() {{
  var data = {{}};
  // حقول النص
  ['p_name','p_id','p_major','p_edu','p_exp','p_lab_exp','p_school','p_stage','p_year',
   'p_semester','p_achievements','p_development','eval_name','eval_date',
   'eval_strengths','eval_improvements','eval_recommendations'].forEach(function(id) {{
    var el = document.getElementById(id);
    if (el) data[id] = el.value;
  }});
  // أزرار الراديو
  document.querySelectorAll('input[type=radio]:checked').forEach(function(r) {{
    data['radio_' + r.name] = r.value;
  }});
  localStorage.setItem(_KEY, JSON.stringify(data));
}}

function restoreAllData() {{
  var raw = localStorage.getItem(_KEY);
  if (!raw) return;
  try {{
    var data = JSON.parse(raw);
    Object.keys(data).forEach(function(k) {{
      if (k.startsWith('radio_')) {{
        var name = k.replace('radio_', '');
        var el = document.querySelector('input[type=radio][name="'+name+'"][value="'+data[k]+'"]');
        if (el) el.checked = true;
      }} else {{
        var el = document.getElementById(k);
        if (el) el.value = data[k] || '';
      }}
    }});
  }} catch(e) {{}}
}}

function clearAllData() {{
  if (!confirm('⚠️ هل تريد مسح جميع البيانات؟')) return;
  localStorage.removeItem(_KEY);
  location.reload();
}}

// تحميل البيانات عند فتح الصفحة
window.addEventListener('load', function() {{
  restoreAllData();
  updateScore();
}});
</script>
{_body_inject(username)}
</body>
</html>"""


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
    return HTMLResponse(_build_lab_docs_html(user.get("username", "")))


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
    full_name = user.get("full_name", "") or username
    try:
        body = await request.json()
        pdf_b64 = body.get("pdf_data", "")
        form_data = body.get("form_data", "{}")
        if not isinstance(form_data, str):
            form_data = json.dumps(form_data)
        now = datetime.datetime.now()
        now_str = now.isoformat()

        pdf_path = None
        if pdf_b64:
            subs_dir = os.path.join(DATA_DIR, "lab_submissions")
            os.makedirs(subs_dir, exist_ok=True)
            fname = f"lab_{username}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = os.path.join(subs_dir, fname)
            with open(pdf_path, "wb") as f:
                f.write(_b64.b64decode(pdf_b64))

        con = get_db(); cur = con.cursor()
        cur.execute("""
            INSERT INTO lab_doc_submissions (username, full_name, form_data, submitted_at, is_read, pdf_path)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (username, full_name, form_data, now_str, pdf_path))
        con.commit(); con.close()
        return JSONResponse({"ok": True, "submitted_at": now_str})
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
            SELECT id, username, COALESCE(full_name, username) as display_name, submitted_at, is_read, pdf_path
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
        sub_id, uname, display_name, sub_at, is_read, pdf_path = row
        badge = "" if is_read else '<span style="background:#ef4444;color:white;padding:2px 8px;border-radius:20px;font-size:11px;margin-right:6px">جديد</span>'
        dt = sub_at[:16].replace("T", " ") if sub_at else ""
        has_pdf = pdf_path and os.path.exists(pdf_path)
        view_btn = (
            f'<a href="/web/lab-docs/view/{sub_id}" target="_blank" '
            f'style="background:#1565C0;color:white;padding:6px 12px;border-radius:8px;'
            f'text-decoration:none;font-size:13px;font-weight:700">📄 عرض PDF</a>'
        ) if has_pdf else '<span style="color:#aaa;font-size:12px">لا يوجد PDF</span>'
        del_btn = (
            f'<button onclick="delSub({sub_id},this)" '
            f'style="background:#ef4444;color:white;border:none;padding:6px 12px;border-radius:8px;'
            f'font-size:13px;font-weight:700;cursor:pointer;font-family:Cairo,sans-serif">🗑 حذف</button>'
        )
        rows_html += f"""
        <tr id="row-{sub_id}" style="{'background:#fff' if is_read else 'background:#FFF7ED'}">
          <td style="padding:10px 14px;direction:rtl">{badge}{display_name}</td>
          <td style="padding:10px 14px;color:#666;font-size:13px">{dt}</td>
          <td style="padding:10px 14px;display:flex;gap:8px;align-items:center">{view_btn}{del_btn}</td>
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
  .card{{background:white;border-radius:14px;padding:24px;max-width:900px;margin:0 auto;box-shadow:0 2px 12px rgba(0,0,0,0.08)}}
  h2{{color:#0f6e56;margin-top:0}}
  table{{width:100%;border-collapse:collapse}}
  thead tr{{background:#0f6e56;color:white}}
  th{{padding:10px 14px;font-weight:700;text-align:right}}
  tr:hover{{background:#f0fdf9!important}}
  .back{{display:inline-block;margin-bottom:16px;color:#2da88a;text-decoration:none;font-weight:700}}
</style>
<script>
async function delSub(id, btn) {{
  if (!confirm('⚠️ هل أنت متأكد من حذف هذا الملف نهائياً؟')) return;
  btn.disabled = true; btn.textContent = '⏳';
  try {{
    var r = await fetch('/web/api/lab-docs/submissions/' + id + '/delete', {{method:'DELETE'}});
    var d = await r.json();
    if (d.ok) {{
      var row = document.getElementById('row-' + id);
      if (row) row.remove();
    }} else {{
      alert('❌ فشل الحذف: ' + (d.msg || ''));
      btn.disabled = false; btn.textContent = '🗑 حذف';
    }}
  }} catch(e) {{
    alert('❌ خطأ في الاتصال');
    btn.disabled = false; btn.textContent = '🗑 حذف';
  }}
}}
</script>
</head>
<body>
<div class="card">
  <a class="back" href="/web/dashboard">← العودة للوحة التحكم</a>
  <h2>📋 شواهد الأداء الوظيفي — المُرسَلة للمدير</h2>
  {'<p style="color:#888;text-align:center;padding:30px">لا توجد ملفات مُرسَلة بعد.</p>' if not rows else f'<table><thead><tr><th>المحضر</th><th>تاريخ الإرسال</th><th>الإجراءات</th></tr></thead><tbody>{rows_html}</tbody></table>'}
</div>
</body>
</html>"""
    return HTMLResponse(page)


@router.delete("/web/api/lab-docs/submissions/{sub_id}/delete")
async def lab_docs_delete_submission(sub_id: int, request: Request):
    user = _get_current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"ok": False, "msg": "غير مصرح"}, status_code=403)

    con = get_db(); cur = con.cursor()
    try:
        cur.execute("SELECT pdf_path FROM lab_doc_submissions WHERE id = ?", (sub_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse({"ok": False, "msg": "السجل غير موجود"}, status_code=404)
        pdf_path = row[0]
        cur.execute("DELETE FROM lab_doc_submissions WHERE id = ?", (sub_id,))
        con.commit()
    finally:
        con.close()

    if pdf_path and os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
        except Exception:
            pass

    return JSONResponse({"ok": True})


@router.get("/web/lab-docs/view/{sub_id}")
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
            "SELECT username, pdf_path, submitted_at FROM lab_doc_submissions WHERE id = ?",
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
        sub_username, pdf_path, submitted_at = row
        cur.execute("UPDATE lab_doc_submissions SET is_read = 1 WHERE id = ?", (sub_id,))
        con.commit()
    finally:
        con.close()

    if not pdf_path or not os.path.exists(pdf_path):
        return HTMLResponse(
            "<html dir='rtl'><body style='font-family:Cairo,sans-serif;text-align:center;padding:80px'>"
            f"<h2 style='color:#e24b4a'>⚠️ ملف PDF غير متوفر</h2>"
            f"<p>أُرسل بواسطة: <b>{sub_username}</b></p>"
            "<a href='/web/lab-docs/submissions' style='color:#2da88a'>العودة للقائمة</a></body></html>",
            status_code=404
        )

    dt_safe = (submitted_at or "")[:10]
    fname = f"lab_perf_{sub_username}_{dt_safe}.pdf"
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'}
    )
