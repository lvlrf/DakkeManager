#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Holoo API - Middle API Service
سرویس واسط برای اتصال به دیتابیس هلو
نسخه: 1.0.0
پورت پیش‌فرض: 7480
"""

import os
import sys
import json
import socket
import logging
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any, List

# Flask برای وب سرور
from flask import Flask, request, jsonify, Response

# pyodbc برای اتصال به SQL Server
import pyodbc

# ============================================
# تنظیمات
# ============================================

DEFAULT_PORT = 7480
API_KEY = "holoo_api_secret_key_2024"  # کلید API - قابل تغییر
REQUEST_TIMEOUT = 30  # ثانیه
MAX_RETRIES = 3
LOG_FILE = "holoo_api.log"

# ============================================
# تنظیم لاگ
# ============================================

# مسیر فایل لاگ کنار فایل اجرایی
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_FILE)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# Flask App
# ============================================

app = Flask(__name__)

# ============================================
# توابع کمکی
# ============================================

def verify_api_key(f):
    """دکوراتور برای بررسی API Key"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != API_KEY:
            logger.warning(f"درخواست با API Key نامعتبر: {request.remote_addr}")
            return jsonify({
                "success": False,
                "error": "API Key نامعتبر است",
                "error_code": "INVALID_API_KEY"
            }), 401
        return f(*args, **kwargs)
    return decorated


def get_db_connection(server: str, database: str, username: str, password: str) -> pyodbc.Connection:
    """ایجاد اتصال به دیتابیس SQL Server"""
    
    # لیست درایورها به ترتیب اولویت
    preferred_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server"
    ]
    
    # پیدا کردن درایورهای نصب شده
    installed_drivers = pyodbc.drivers()
    
    # انتخاب اولین درایور موجود
    selected_driver = None
    for driver in preferred_drivers:
        if driver in installed_drivers:
            selected_driver = driver
            break
    
    if not selected_driver:
        # اگر هیچکدام نبود، اولین درایور SQL Server را انتخاب کن
        sql_drivers = [d for d in installed_drivers if 'SQL Server' in d]
        if sql_drivers:
            selected_driver = sql_drivers[0]
        else:
            raise pyodbc.Error("HY000", "هیچ درایور SQL Server نصب نشده است")
    
    # ساخت Connection String
    # برای ODBC Driver 18 باید TrustServerCertificate اضافه بشه
    if "18" in selected_driver:
        connection_string = (
            f"DRIVER={{{selected_driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={REQUEST_TIMEOUT};"
        )
    else:
        connection_string = (
            f"DRIVER={{{selected_driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"Connection Timeout={REQUEST_TIMEOUT};"
        )
    
    try:
        conn = pyodbc.connect(connection_string, timeout=REQUEST_TIMEOUT)
        logger.info(f"اتصال با درایور {selected_driver} برقرار شد")
        return conn
    except pyodbc.Error as e:
        logger.error(f"خطای اتصال با درایور {selected_driver}: {e}")
        raise e


def execute_with_retry(func, max_retries: int = MAX_RETRIES):
    """اجرای تابع با تلاش مجدد در صورت خطا"""
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            logger.warning(f"تلاش {attempt + 1} از {max_retries} ناموفق: {str(e)}")
            if attempt < max_retries - 1:
                continue
    raise last_error


def parse_db_params(request) -> Dict[str, str]:
    """استخراج پارامترهای دیتابیس از درخواست"""
    # اول از JSON body بخون
    if request.is_json:
        data = request.get_json()
        return {
            "server": data.get("server", "localhost"),
            "database": data.get("database", ""),
            "username": data.get("username", ""),
            "password": data.get("password", "")
        }
    
    # بعد از query string
    return {
        "server": request.args.get("server", "localhost"),
        "database": request.args.get("database", ""),
        "username": request.args.get("username", ""),
        "password": request.args.get("password", "")
    }


# ============================================
# Endpoints
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    """
    بررسی سلامت سرویس (بدون نیاز به API Key)
    حالت‌ها:
    1. سرویس فعال است
    """
    return jsonify({
        "success": True,
        "status": "running",
        "message": "سرویس API در حال اجراست",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })


@app.route('/ping', methods=['GET'])
def ping():
    """تست ساده برای بررسی دسترسی"""
    return jsonify({
        "success": True,
        "message": "pong",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/check/db', methods=['POST'])
@verify_api_key
def check_database():
    """
    بررسی اتصال به دیتابیس
    حالت‌های خروجی:
    - DB_CONNECTED: اتصال برقرار است
    - DB_AUTH_ERROR: خطای احراز هویت
    - DB_NOT_FOUND: دیتابیس پیدا نشد
    - DB_CONNECTION_ERROR: خطای اتصال
    """
    params = parse_db_params(request)
    
    if not params["database"]:
        return jsonify({
            "success": False,
            "status": "DB_PARAM_MISSING",
            "message": "پارامترهای دیتابیس ارسال نشده"
        }), 400
    
    try:
        conn = get_db_connection(
            params["server"],
            params["database"],
            params["username"],
            params["password"]
        )
        
        # تست یک کوئری ساده
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        
        logger.info(f"اتصال به دیتابیس {params['database']} برقرار شد")
        
        return jsonify({
            "success": True,
            "status": "DB_CONNECTED",
            "message": "اتصال به دیتابیس برقرار است",
            "database": params["database"]
        })
        
    except pyodbc.Error as e:
        error_msg = str(e)
        
        if "Login failed" in error_msg or "28000" in error_msg:
            status = "DB_AUTH_ERROR"
            message = "خطای احراز هویت - یوزر یا پسورد اشتباه است"
        elif "Cannot open database" in error_msg or "4060" in error_msg:
            status = "DB_NOT_FOUND"
            message = "دیتابیس پیدا نشد"
        else:
            status = "DB_CONNECTION_ERROR"
            message = f"خطای اتصال: {error_msg}"
        
        logger.error(f"خطای اتصال به دیتابیس: {message}")
        
        return jsonify({
            "success": False,
            "status": status,
            "message": message
        }), 500


@app.route('/articles', methods=['POST'])
@verify_api_key
def get_articles():
    """
    دریافت لیست کالاها
    پارامترهای اختیاری در body:
    - search: جستجو در نام یا کد کالا
    - limit: تعداد نتایج (پیش‌فرض: 1000)
    - offset: شروع از (برای صفحه‌بندی)
    """
    params = parse_db_params(request)
    data = request.get_json() or {}
    
    search = data.get("search", "")
    limit = data.get("limit", 1000)
    offset = data.get("offset", 0)
    
    try:
        def fetch_articles():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            # کوئری سازگار با SQL Server 2008 R2 (بدون OFFSET/FETCH)
            where_clause = ""
            query_params = []
            
            if search:
                where_clause = "WHERE (a.A_Code LIKE ? OR a.A_Name LIKE ?)"
                query_params.extend([f"%{search}%", f"%{search}%"])
            
            # استفاده از ROW_NUMBER برای صفحه‌بندی (سازگار با 2008 R2)
            if offset > 0:
                query = f"""
                    SELECT * FROM (
                        SELECT 
                            a.A_Code AS code,
                            a.A_Name AS name,
                            a.Sel_Price AS price,
                            a.Exist AS stock1,
                            a.Exist2 AS stock2,
                            a.M_Code AS group_code,
                            mg.M_groupname AS group_name,
                            a.A_Code_C AS barcode,
                            a.A_Country AS country,
                            a.Model AS model,
                            ROW_NUMBER() OVER (ORDER BY a.A_Code) AS RowNum
                        FROM dbo.ARTICLE a
                        LEFT JOIN dbo.M_GROUP mg ON mg.M_groupcode = a.M_Code
                        {where_clause}
                    ) AS t
                    WHERE RowNum > {offset} AND RowNum <= {offset + limit}
                """
            else:
                # بدون صفحه‌بندی - فقط TOP
                query = f"""
                    SELECT TOP {limit}
                        a.A_Code AS code,
                        a.A_Name AS name,
                        a.Sel_Price AS price,
                        a.Exist AS stock1,
                        a.Exist2 AS stock2,
                        a.M_Code AS group_code,
                        mg.M_groupname AS group_name,
                        a.A_Code_C AS barcode,
                        a.A_Country AS country,
                        a.Model AS model
                    FROM dbo.ARTICLE a
                    LEFT JOIN dbo.M_GROUP mg ON mg.M_groupcode = a.M_Code
                    {where_clause}
                    ORDER BY a.A_Code
                """
            
            cursor.execute(query, query_params)
            
            columns = [column[0] for column in cursor.description]
            results = []
            
            for row in cursor.fetchall():
                item = dict(zip(columns, row))
                # تبدیل مقادیر None به رشته خالی یا صفر
                for key, value in item.items():
                    if value is None:
                        if key in ['price', 'stock1', 'stock2']:
                            item[key] = 0
                        else:
                            item[key] = ""
                results.append(item)
            
            # شمارش کل
            count_query = "SELECT COUNT(*) FROM dbo.ARTICLE"
            if search:
                count_query += " WHERE A_Code LIKE ? OR A_Name LIKE ?"
                cursor.execute(count_query, [f"%{search}%", f"%{search}%"])
            else:
                cursor.execute(count_query)
            
            total_count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return results, total_count
        
        articles, total = execute_with_retry(fetch_articles)
        
        logger.info(f"دریافت {len(articles)} کالا از {total} کالا")
        
        return jsonify({
            "success": True,
            "data": articles,
            "total": total,
            "count": len(articles),
            "offset": offset,
            "limit": limit
        })
        
    except Exception as e:
        logger.error(f"خطا در دریافت کالاها: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "FETCH_ERROR"
        }), 500


@app.route('/article/<code>', methods=['POST'])
@verify_api_key
def get_article(code: str):
    """دریافت اطلاعات یک کالا با کد"""
    params = parse_db_params(request)
    
    try:
        def fetch_article():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    a.A_Code AS code,
                    a.A_Name AS name,
                    a.Sel_Price AS price,
                    a.Exist AS stock1,
                    a.Exist2 AS stock2,
                    a.M_Code AS group_code,
                    mg.M_groupname AS group_name,
                    a.A_Code_C AS barcode,
                    a.A_Country AS country,
                    a.Model AS model
                FROM dbo.ARTICLE a
                LEFT JOIN dbo.M_GROUP mg ON mg.M_groupcode = a.M_Code
                WHERE a.A_Code = ?
            """
            
            cursor.execute(query, [code])
            row = cursor.fetchone()
            
            if not row:
                return None
            
            columns = [column[0] for column in cursor.description]
            item = dict(zip(columns, row))
            
            cursor.close()
            conn.close()
            
            return item
        
        article = execute_with_retry(fetch_article)
        
        if not article:
            return jsonify({
                "success": False,
                "error": "کالا پیدا نشد",
                "error_code": "NOT_FOUND"
            }), 404
        
        return jsonify({
            "success": True,
            "data": article
        })
        
    except Exception as e:
        logger.error(f"خطا در دریافت کالا {code}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "FETCH_ERROR"
        }), 500


@app.route('/article/<code>/update', methods=['POST'])
@verify_api_key
def update_article(code: str):
    """
    ویرایش کالا
    پارامترهای قابل ویرایش در body:
    - name: نام کالا
    - price: قیمت فروش
    - group_code: کد گروه
    """
    params = parse_db_params(request)
    data = request.get_json() or {}
    
    # فیلدهای قابل ویرایش
    allowed_fields = {
        "name": "A_Name",
        "price": "Sel_Price",
        "group_code": "M_Code"
    }
    
    # ساخت لیست فیلدهای تغییر یافته
    updates = {}
    for key, db_field in allowed_fields.items():
        if key in data:
            updates[db_field] = data[key]
    
    if not updates:
        return jsonify({
            "success": False,
            "error": "هیچ فیلدی برای ویرایش ارسال نشده",
            "error_code": "NO_FIELDS"
        }), 400
    
    try:
        def do_update():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            # ابتدا بررسی وجود کالا
            cursor.execute("SELECT A_Code FROM dbo.ARTICLE WHERE A_Code = ?", [code])
            if not cursor.fetchone():
                cursor.close()
                conn.close()
                return False, "کالا پیدا نشد"
            
            # ساخت کوئری آپدیت
            set_clause = ", ".join([f"{field} = ?" for field in updates.keys()])
            query = f"UPDATE dbo.ARTICLE SET {set_clause} WHERE A_Code = ?"
            
            values = list(updates.values()) + [code]
            cursor.execute(query, values)
            conn.commit()
            
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            
            return True, affected
        
        success, result = execute_with_retry(do_update)
        
        if not success:
            return jsonify({
                "success": False,
                "error": result,
                "error_code": "NOT_FOUND"
            }), 404
        
        logger.info(f"کالا {code} ویرایش شد: {updates}")
        
        return jsonify({
            "success": True,
            "message": "کالا با موفقیت ویرایش شد",
            "code": code,
            "updated_fields": list(updates.keys()),
            "affected_rows": result
        })
        
    except Exception as e:
        logger.error(f"خطا در ویرایش کالا {code}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "UPDATE_ERROR"
        }), 500


@app.route('/groups', methods=['POST'])
@verify_api_key
def get_groups():
    """دریافت لیست گروه‌های کالا"""
    params = parse_db_params(request)
    
    try:
        def fetch_groups():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    M_groupcode AS code,
                    M_groupname AS name
                FROM dbo.M_GROUP
                ORDER BY M_groupcode
            """
            
            cursor.execute(query)
            
            columns = [column[0] for column in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return results
        
        groups = execute_with_retry(fetch_groups)
        
        return jsonify({
            "success": True,
            "data": groups,
            "count": len(groups)
        })
        
    except Exception as e:
        logger.error(f"خطا در دریافت گروه‌ها: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "FETCH_ERROR"
        }), 500


@app.route('/subgroups', methods=['POST'])
@verify_api_key
def get_subgroups():
    """
    دریافت لیست زیرگروه‌ها
    پارامتر اختیاری:
    - group_code: کد گروه اصلی (برای فیلتر)
    """
    params = parse_db_params(request)
    data = request.get_json() or {}
    group_code = data.get("group_code", "")
    
    try:
        def fetch_subgroups():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    sg.M_groupcode AS group_code,
                    mg.M_groupname AS group_name,
                    sg.S_groupcode AS subgroup_code,
                    sg.S_groupname AS subgroup_name
                FROM dbo.S_GROUP sg
                LEFT JOIN dbo.M_GROUP mg ON mg.M_groupcode = sg.M_groupcode
            """
            
            if group_code:
                query += " WHERE sg.M_groupcode = ?"
                cursor.execute(query + " ORDER BY sg.M_groupcode, sg.S_groupcode", [group_code])
            else:
                cursor.execute(query + " ORDER BY sg.M_groupcode, sg.S_groupcode")
            
            columns = [column[0] for column in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return results
        
        subgroups = execute_with_retry(fetch_subgroups)
        
        return jsonify({
            "success": True,
            "data": subgroups,
            "count": len(subgroups)
        })
        
    except Exception as e:
        logger.error(f"خطا در دریافت زیرگروه‌ها: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "FETCH_ERROR"
        }), 500


@app.route('/group/add', methods=['POST'])
@verify_api_key
def add_group():
    """
    افزودن گروه جدید
    پارامترها:
    - name: نام گروه (اجباری)
    - code: کد گروه (اختیاری - اگر نباشد، خودکار تولید میشه)
    """
    params = parse_db_params(request)
    data = request.get_json() or {}
    
    name = data.get("name", "").strip()
    code = data.get("code", "").strip()
    
    if not name:
        return jsonify({
            "success": False,
            "error": "نام گروه الزامی است",
            "error_code": "NAME_REQUIRED"
        }), 400
    
    try:
        def do_add():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            # اگر کد داده نشده، کد جدید تولید کن
            if not code:
                cursor.execute("""
                    SELECT MAX(CAST(M_groupcode AS int)) 
                    FROM dbo.M_GROUP 
                    WHERE ISNUMERIC(M_groupcode) = 1
                """)
                max_code = cursor.fetchone()[0] or 0
                new_code = str(max_code + 1).zfill(2)
            else:
                new_code = code
            
            # بررسی تکراری نبودن کد
            cursor.execute("SELECT M_groupcode FROM dbo.M_GROUP WHERE M_groupcode = ?", [new_code])
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return False, "این کد گروه قبلاً وجود دارد", None
            
            # درج گروه جدید
            cursor.execute(
                "INSERT INTO dbo.M_GROUP (M_groupcode, M_groupname) VALUES (?, ?)",
                [new_code, name]
            )
            conn.commit()
            
            cursor.close()
            conn.close()
            
            return True, "گروه با موفقیت اضافه شد", new_code
        
        success, message, new_code = execute_with_retry(do_add)
        
        if not success:
            return jsonify({
                "success": False,
                "error": message,
                "error_code": "ADD_ERROR"
            }), 400
        
        logger.info(f"گروه جدید اضافه شد: {new_code} - {name}")
        
        return jsonify({
            "success": True,
            "message": message,
            "code": new_code,
            "name": name
        })
        
    except Exception as e:
        logger.error(f"خطا در افزودن گروه: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "ADD_ERROR"
        }), 500


@app.route('/group/<code>/update', methods=['POST'])
@verify_api_key
def update_group(code: str):
    """
    ویرایش گروه
    پارامتر:
    - name: نام جدید گروه
    """
    params = parse_db_params(request)
    data = request.get_json() or {}
    
    name = data.get("name", "").strip()
    
    if not name:
        return jsonify({
            "success": False,
            "error": "نام گروه الزامی است",
            "error_code": "NAME_REQUIRED"
        }), 400
    
    try:
        def do_update():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE dbo.M_GROUP SET M_groupname = ? WHERE M_groupcode = ?",
                [name, code]
            )
            conn.commit()
            
            affected = cursor.rowcount
            cursor.close()
            conn.close()
            
            return affected
        
        affected = execute_with_retry(do_update)
        
        if affected == 0:
            return jsonify({
                "success": False,
                "error": "گروه پیدا نشد",
                "error_code": "NOT_FOUND"
            }), 404
        
        logger.info(f"گروه {code} ویرایش شد به: {name}")
        
        return jsonify({
            "success": True,
            "message": "گروه با موفقیت ویرایش شد",
            "code": code,
            "name": name
        })
        
    except Exception as e:
        logger.error(f"خطا در ویرایش گروه {code}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "UPDATE_ERROR"
        }), 500


@app.route('/stats', methods=['POST'])
@verify_api_key
def get_stats():
    """دریافت آمار کلی دیتابیس"""
    params = parse_db_params(request)
    
    try:
        def fetch_stats():
            conn = get_db_connection(
                params["server"],
                params["database"],
                params["username"],
                params["password"]
            )
            cursor = conn.cursor()
            
            stats = {}
            
            # تعداد کالاها
            cursor.execute("SELECT COUNT(*) FROM dbo.ARTICLE")
            stats["total_articles"] = cursor.fetchone()[0]
            
            # تعداد کالاهای با قیمت
            cursor.execute("SELECT COUNT(*) FROM dbo.ARTICLE WHERE Sel_Price > 0")
            stats["articles_with_price"] = cursor.fetchone()[0]
            
            # تعداد کالاهای با موجودی
            cursor.execute("SELECT COUNT(*) FROM dbo.ARTICLE WHERE Exist > 0")
            stats["articles_with_stock"] = cursor.fetchone()[0]
            
            # تعداد کالاهای با گروه
            cursor.execute("SELECT COUNT(*) FROM dbo.ARTICLE WHERE M_Code IS NOT NULL AND M_Code != ''")
            stats["articles_with_group"] = cursor.fetchone()[0]
            
            # تعداد گروه‌ها
            cursor.execute("SELECT COUNT(*) FROM dbo.M_GROUP")
            stats["total_groups"] = cursor.fetchone()[0]
            
            # تعداد زیرگروه‌ها
            cursor.execute("SELECT COUNT(*) FROM dbo.S_GROUP")
            stats["total_subgroups"] = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return stats
        
        stats = execute_with_retry(fetch_stats)
        
        return jsonify({
            "success": True,
            "data": stats
        })
        
    except Exception as e:
        logger.error(f"خطا در دریافت آمار: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "FETCH_ERROR"
        }), 500


@app.route('/batch/update', methods=['POST'])
@verify_api_key
def batch_update():
    """
    ویرایش دسته‌ای کالاها
    پارامتر items: لیستی از آبجکت‌ها با فیلدهای:
    - code: کد کالا
    - name: نام جدید (اختیاری)
    - price: قیمت جدید (اختیاری)
    - group_code: کد گروه جدید (اختیاری)
    """
    params = parse_db_params(request)
    data = request.get_json() or {}
    
    items = data.get("items", [])
    
    if not items:
        return jsonify({
            "success": False,
            "error": "لیست کالاها خالی است",
            "error_code": "EMPTY_LIST"
        }), 400
    
    results = {
        "success": [],
        "failed": []
    }
    
    try:
        conn = get_db_connection(
            params["server"],
            params["database"],
            params["username"],
            params["password"]
        )
        cursor = conn.cursor()
        
        for item in items:
            code = item.get("code", "")
            if not code:
                results["failed"].append({
                    "code": "",
                    "error": "کد کالا ارسال نشده"
                })
                continue
            
            # ساخت کوئری آپدیت
            updates = {}
            if "name" in item:
                updates["A_Name"] = item["name"]
            if "price" in item:
                updates["Sel_Price"] = item["price"]
            if "group_code" in item:
                updates["M_Code"] = item["group_code"]
            
            if not updates:
                results["failed"].append({
                    "code": code,
                    "error": "هیچ فیلدی برای ویرایش نیست"
                })
                continue
            
            try:
                set_clause = ", ".join([f"{field} = ?" for field in updates.keys()])
                query = f"UPDATE dbo.ARTICLE SET {set_clause} WHERE A_Code = ?"
                values = list(updates.values()) + [code]
                
                cursor.execute(query, values)
                
                if cursor.rowcount > 0:
                    results["success"].append({
                        "code": code,
                        "updated": list(updates.keys())
                    })
                else:
                    results["failed"].append({
                        "code": code,
                        "error": "کالا پیدا نشد"
                    })
            except Exception as e:
                results["failed"].append({
                    "code": code,
                    "error": str(e)
                })
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"ویرایش دسته‌ای: {len(results['success'])} موفق، {len(results['failed'])} ناموفق")
        
        return jsonify({
            "success": True,
            "results": results,
            "summary": {
                "total": len(items),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"])
            }
        })
        
    except Exception as e:
        logger.error(f"خطا در ویرایش دسته‌ای: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "error_code": "BATCH_ERROR"
        }), 500


# ============================================
# Error Handlers
# ============================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "success": False,
        "error": "مسیر پیدا نشد",
        "error_code": "NOT_FOUND"
    }), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "success": False,
        "error": "خطای داخلی سرور",
        "error_code": "SERVER_ERROR"
    }), 500


# ============================================
# Main
# ============================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Holoo API Service')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='پورت سرویس')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='آدرس هاست')
    parser.add_argument('--debug', action='store_true', help='حالت دیباگ')
    
    args = parser.parse_args()
    
    logger.info(f"شروع سرویس Holoo API روی پورت {args.port}")
    
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=True
    )
