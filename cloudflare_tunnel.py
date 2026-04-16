# -*- coding: utf-8 -*-
"""
cloudflare_tunnel.py — إدارة نفق Cloudflare
"""
import os, re, subprocess, shutil, threading, time
from constants import CLOUDFLARE_DOMAIN

_cf_process = None  # مرجع لعملية cloudflared

def _has_named_tunnel_config() -> bool:
    """يتحقق إذا كان هناك إعداد Named Tunnel (config.yml أو credentials)."""
    cf_dir = os.path.join(os.path.expanduser("~"), ".cloudflared")
    config_yml = os.path.join(cf_dir, "config.yml")
    # ابحث عن credentials file للنفق المُسمّى
    if os.path.exists(config_yml):
        try:
            with open(config_yml, "r") as f:
                content = f.read()
            if "tunnel:" in content and "credentials-file:" in content:
                return True
        except Exception:
            pass
    # ابحث عن أي ملف credentials JSON
    if os.path.exists(cf_dir):
        for fname in os.listdir(cf_dir):
            if fname.endswith(".json") and fname != "cert.pem":
                try:
                    with open(os.path.join(cf_dir, fname), "r") as f:
                        data = json.load(f)
                    if "TunnelID" in data or "AccountTag" in data:
                        return True
                except Exception:
                    pass
    return False


def find_cloudflared_executable():
    """يبحث عن مسار ملف cloudflared.exe في المسارات المحتملة."""
    import sys as _sys
    import shutil
    from typing import Optional
    
    _app_dir = (os.path.dirname(_sys.executable)
                if getattr(_sys, 'frozen', False)
                else os.path.dirname(os.path.abspath(__file__)))

    _candidates = [
        os.path.join(_app_dir, "cloudflared.exe"),
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
        r"C:\Windows\System32\cloudflared.exe",
    ]
    for _p in _candidates:
        if os.path.isfile(_p):
            return _p
    
    return shutil.which("cloudflared.exe") or shutil.which("cloudflared")

def start_cloudflare_tunnel(port: int, domain: str):
    """
    يُشغّل cloudflared tunnel ويعيد الرابط العام.
    - إذا وُجد Named Tunnel مُعدّ (credentials JSON) → يستخدمه مع دومين darbte.uk
    - إذا لم يوجد → يستخدم Quick Tunnel ويلتقط الرابط العشوائي تلقائياً
    """
    global _cf_process
    cloudflared = find_cloudflared_executable()
    if not cloudflared:
        print("[CLOUDFLARE] ⚠️ cloudflared غير مثبّت — يعمل محلياً فقط")
        return None

    print(f"[CLOUDFLARE] مسار cloudflared: {cloudflared}")
    has_named = _has_named_tunnel_config()

    try:
        if has_named:
            print(f"[CLOUDFLARE] 🔑 Named Tunnel مكتشف — سيتصل بـ {domain}")
            cmd = [cloudflared, "tunnel", "--no-autoupdate", "run"]
        else:
            print("[CLOUDFLARE] ⚡ Quick Tunnel (بدون حساب) — سيُنشئ رابطاً مؤقتاً")
            cmd = [
                cloudflared, "tunnel",
                "--url", f"http://localhost:{port}",
                "--hostname", domain,
                "--no-autoupdate"
            ]

        _cf_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        # ─── خيط يقرأ باقي السجلات بعد الالتقاط ─────────────────
        def _drain_logs():
            try:
                for ln in _cf_process.stdout:
                    print(f"[CLOUDFLARE] {ln.rstrip()}")
            except Exception:
                pass

        # ─── قراءة المخرجات والتقاط الرابط ──────────────────────
        detected_url = None
        timeout = 40
        start_t = time.time()

        while time.time() - start_t < timeout:
            if _cf_process.poll() is not None:
                print("[CLOUDFLARE] ❌ انتهت العملية مبكراً")
                break
            line = _cf_process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            print(f"[CLOUDFLARE] {line.rstrip()}")

            # ① التقط رابط trycloudflare العشوائي
            if not detected_url and "trycloudflare.com" in line:
                m = re.search(r'https://[\w\-]+\.trycloudflare\.com', line)
                if m:
                    detected_url = m.group(0)
                    print(f"[CLOUDFLARE] ✅ الرابط المؤقت: {detected_url}")
                    threading.Thread(target=_drain_logs, daemon=True).start()
                    break

            # ② تأكيد اتصال النفق (Named أو مع hostname) — "Registered tunnel connection"
            if not detected_url and "Registered tunnel connection" in line:
                detected_url = f"https://{domain}"
                print(f"[CLOUDFLARE] ✅ متصل بالنطاق: {detected_url}")
                threading.Thread(target=_drain_logs, daemon=True).start()
                break

            # ③ أي سطر يذكر hostname بشكل صريح
            if not detected_url and domain in line and ("http" in line.lower() or "tunnel" in line.lower()):
                detected_url = f"https://{domain}"
                print(f"[CLOUDFLARE] ✅ تم اكتشاف النطاق: {detected_url}")
                threading.Thread(target=_drain_logs, daemon=True).start()
                break

        # ④ إذا انتهت المهلة لكن العملية لا تزال تعمل → افترض النجاح
        if not detected_url and _cf_process and _cf_process.poll() is None:
            detected_url = f"https://{domain}"
            print(f"[CLOUDFLARE] ✅ النفق يعمل (تم افتراض الرابط): {detected_url}")
            threading.Thread(target=_drain_logs, daemon=True).start()

        if not detected_url:
            print("[CLOUDFLARE] ⚠️ لم يُكتشف رابط في المهلة المحددة")

        return detected_url

    except Exception as e:
        print(f"[CLOUDFLARE] ❌ تعذّر تشغيل النفق: {e}")
        return None

def stop_cloudflare_tunnel():
    """يوقف عملية cloudflared."""
    global _cf_process
    if _cf_process:
        try:
            _cf_process.terminate()
            _cf_process = None
            print("[CLOUDFLARE] 🛑 تم إيقاف النفق")
        except Exception as e:
            print(f"[CLOUDFLARE] خطأ عند الإيقاف: {e}")

