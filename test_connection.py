#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
تست اتصال به SQL Server
این فایل برای عیب‌یابی مشکلات اتصال استفاده می‌شود
"""

import pyodbc
import sys

print("=" * 50)
print("  تست اتصال به SQL Server")
print("=" * 50)
print()

# اطلاعات اتصال
SERVER = "192.168.30.30"
DATABASE = "Holoo_TestDB"
USERNAME = "321"
PASSWORD = "123"

# لیست درایورهای موجود
print("[1] درایورهای ODBC نصب شده:")
print("-" * 40)
drivers = pyodbc.drivers()
if drivers:
    for i, driver in enumerate(drivers, 1):
        print(f"    {i}. {driver}")
else:
    print("    هیچ درایوری پیدا نشد!")
print()

# پیدا کردن درایور مناسب
sql_drivers = [d for d in drivers if 'SQL Server' in d]
print(f"[2] درایورهای SQL Server: {sql_drivers}")
print()

if not sql_drivers:
    print("[خطا] هیچ درایور SQL Server پیدا نشد!")
    print("لطفاً ODBC Driver for SQL Server را نصب کنید.")
    input("\nEnter برای خروج...")
    sys.exit(1)

# انتخاب بهترین درایور (جدیدترین)
preferred_drivers = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server"
]

selected_driver = None
for pref in preferred_drivers:
    if pref in drivers:
        selected_driver = pref
        break

if not selected_driver:
    selected_driver = sql_drivers[0]

print(f"[3] درایور انتخاب شده: {selected_driver}")
print()

# تست اتصال
print("[4] تلاش برای اتصال...")
print(f"    Server: {SERVER}")
print(f"    Database: {DATABASE}")
print(f"    User: {USERNAME}")
print()

# برای ODBC Driver 18 باید TrustServerCertificate اضافه بشه
if "18" in selected_driver:
    connection_string = (
        f"DRIVER={{{selected_driver}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=10;"
    )
else:
    connection_string = (
        f"DRIVER={{{selected_driver}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
        f"Connection Timeout=10;"
    )

print(f"    Connection String: {connection_string}")
print()

try:
    print("    در حال اتصال...")
    conn = pyodbc.connect(connection_string, timeout=10)
    print("    [موفق] اتصال برقرار شد!")
    print()
    
    # تست یک کوئری ساده
    print("[5] تست کوئری...")
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    print(f"    SQL Server Version: {row[0][:50]}...")
    print()
    
    # تست دسترسی به جدول ARTICLE
    print("[6] تست دسترسی به جدول ARTICLE...")
    try:
        cursor.execute("SELECT COUNT(*) FROM dbo.ARTICLE")
        count = cursor.fetchone()[0]
        print(f"    [موفق] تعداد کالاها: {count}")
    except Exception as e:
        print(f"    [هشدار] جدول ARTICLE پیدا نشد یا دسترسی ندارید: {e}")
    
    cursor.close()
    conn.close()
    print()
    print("=" * 50)
    print("  تست با موفقیت انجام شد!")
    print("=" * 50)
    
except pyodbc.Error as e:
    print(f"    [خطا] اتصال ناموفق!")
    print(f"    پیام خطا: {e}")
    print()
    
    # راهنمایی
    error_str = str(e)
    if "Login failed" in error_str:
        print("    راهنما: یوزر یا پسورد اشتباه است")
    elif "Cannot open database" in error_str:
        print("    راهنما: دیتابیس پیدا نشد")
    elif "server was not found" in error_str or "TCP Provider" in error_str:
        print("    راهنما: سرور در دسترس نیست یا TCP/IP فعال نیست")
    elif "certificate" in error_str.lower():
        print("    راهنما: مشکل SSL/Certificate - TrustServerCertificate اضافه شود")

except Exception as e:
    print(f"    [خطا] خطای غیرمنتظره: {e}")

print()
input("Enter برای خروج...")
