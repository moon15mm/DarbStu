# -*- coding: utf-8 -*-
"""
api/misc_routes.py — مسارات متنوعة: النتائج، ولي الأمر، البوت، الرسائل الجماعية
"""
import datetime, json, base64, os, io
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from constants import (DB_PATH, DATA_DIR, HOST, PORT, now_riyadh_date,
                       STATIC_DOMAIN, CURRENT_USER)
from config_manager import load_config, get_terms, render_message
from database import (get_db, load_students,
                      insert_excuse, query_excuses, student_has_excuse)
from whatsapp_service import send_whatsapp_message
from pdf_generator import (_render_pdf_page_as_png, _render_page_pillow,
                            get_student_result, save_results_to_db, parse_results_pdf,
                            results_portal_html, student_result_html)
from report_builder import parent_portal_html
from alerts_service import (log_message_status, query_permissions,
                             insert_permission, update_permission_status,
                             save_schedule, load_schedule)

router = APIRouter()

# مسارات إضافية ستُضاف هنا
