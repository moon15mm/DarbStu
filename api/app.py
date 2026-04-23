# -*- coding: utf-8 -*-
"""
api/app.py — إنشاء تطبيق FastAPI وإضافة الـ Middleware والـ Routers
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    print(f"[API-ERROR] {request.url}: {exc}")
    return JSONResponse({"detail": str(exc)}, status_code=500)

class RemoveCSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;"
        )
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

app.add_middleware(RemoveCSPMiddleware)

# ── تسجيل الـ Routers مباشرة عند استيراد هذا الملف ──
from api.mobile_routes import router as _mobile_router
from api.misc_routes   import router as _misc_router
from api.web_routes    import router as _web_router
from api.points_api   import router as _points_router
app.include_router(_mobile_router)
app.include_router(_misc_router)
app.include_router(_web_router)
app.include_router(_points_router)

# ── خدمة الملفات الثابتة (المرفقات وغيرها) ──
from constants import DATA_DIR
import os
os.makedirs(DATA_DIR, exist_ok=True)
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

def register_routers():
    """متوافق مع الاستدعاء القديم — الـ Routers مُسجَّلة مسبقاً."""
    pass
