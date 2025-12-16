# مدیریت شعب هلو
## Holoo Branch Manager

نسخه: 1.0.0

---

## معرفی

این پروژه شامل دو برنامه است:

1. **holoo_api.py** - سرویس API واسط که روی هر سرور شعبه اجرا می‌شود
2. **branch_manager.py** - برنامه دسکتاپ مدیریت شعب

---

## پیش‌نیازها

### روی سرورهای شعبه (برای API):
- Python 3.8+
- SQL Server 2008 R2+
- ODBC Driver for SQL Server
- NSSM (برای تبدیل به سرویس ویندوز)

### روی سیستم مدیر (برای برنامه دسکتاپ):
- Python 3.8+
- فونت Dana (اختیاری)

---

## نصب

### قدم 1: نصب Python
از [python.org](https://www.python.org/downloads/) دانلود و نصب کنید.
حتماً گزینه "Add Python to PATH" را تیک بزنید.

### قدم 2: نصب وابستگی‌ها
```cmd
pip install -r requirements.txt
```

### قدم 3: نصب ODBC Driver (روی سرورها)
از لینک زیر دانلود و نصب کنید:
https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

---

## تنظیمات

### فایل branches.toml
این فایل را کنار برنامه‌ها قرار دهید و تنظیمات شعب را وارد کنید:

```toml
[settings]
api_key = "holoo_api_secret_key_2024"
timeout = 30
retry_count = 3

[[branches]]
name = "شعبه مرکزی"
ip = "192.168.1.10"
database = "Holoo_Main"
user = "sa"
password = "your_password"
port = 7480
```

### کلید API
کلید API در دو جا باید یکسان باشد:
1. در فایل `holoo_api.py` (متغیر `API_KEY`)
2. در فایل `branches.toml` (بخش `settings.api_key`)

---

## اجرا

### روش 1: اجرای مستقیم

**API روی سرور:**
```cmd
python holoo_api.py --port 7480
```

**برنامه مدیریت شعب:**
```cmd
python branch_manager.py
```

### روش 2: تبدیل به سرویس ویندوز با NSSM

1. NSSM را از [nssm.cc](https://nssm.cc/download) دانلود کنید
2. فایل `nssm.exe` را در مسیر قرار دهید
3. دستور زیر را اجرا کنید:

```cmd
nssm install HolooAPI "C:\Python39\python.exe" "C:\path\to\holoo_api.py --port 7480"
nssm set HolooAPI DisplayName "Holoo API Service"
nssm set HolooAPI Description "سرویس API هلو برای مدیریت شعب"
nssm start HolooAPI
```

---

## Endpoints API

### بدون نیاز به API Key:

| مسیر | متد | توضیح |
|------|-----|-------|
| `/health` | GET | بررسی سلامت سرویس |
| `/ping` | GET | تست اتصال |

### نیاز به API Key (در Header با نام X-API-Key):

| مسیر | متد | توضیح |
|------|-----|-------|
| `/check/db` | POST | بررسی اتصال به دیتابیس |
| `/articles` | POST | لیست کالاها |
| `/article/<code>` | POST | اطلاعات یک کالا |
| `/article/<code>/update` | POST | ویرایش کالا |
| `/groups` | POST | لیست گروه‌ها |
| `/subgroups` | POST | لیست زیرگروه‌ها |
| `/group/add` | POST | افزودن گروه |
| `/group/<code>/update` | POST | ویرایش گروه |
| `/stats` | POST | آمار کلی |
| `/batch/update` | POST | ویرایش دسته‌ای |

### پارامترهای اتصال به دیتابیس (در Body همه درخواست‌ها):

```json
{
    "server": "192.168.1.10",
    "database": "Holoo_Main",
    "username": "sa",
    "password": "your_password"
}
```

---

## نمونه درخواست‌ها

### بررسی اتصال:
```bash
curl -X POST http://192.168.1.10:7480/check/db \
  -H "Content-Type: application/json" \
  -H "X-API-Key: holoo_api_secret_key_2024" \
  -d '{"server":"localhost","database":"HolooDb","username":"sa","password":"123"}'
```

### لیست کالاها:
```bash
curl -X POST http://192.168.1.10:7480/articles \
  -H "Content-Type: application/json" \
  -H "X-API-Key: holoo_api_secret_key_2024" \
  -d '{"server":"localhost","database":"HolooDb","username":"sa","password":"123","limit":100}'
```

### ویرایش قیمت:
```bash
curl -X POST http://192.168.1.10:7480/article/0101182/update \
  -H "Content-Type: application/json" \
  -H "X-API-Key: holoo_api_secret_key_2024" \
  -d '{"server":"localhost","database":"HolooDb","username":"sa","password":"123","price":150000}'
```

---

## وضعیت‌های اتصال

| رنگ چراغ | وضعیت | توضیح |
|----------|--------|-------|
| 🔴 قرمز | OFFLINE | سرور در دسترس نیست |
| 🟠 نارنجی | API_DOWN | سرویس API فعال نیست |
| 🟠 نارنجی | AUTH_ERROR | خطای احراز هویت |
| 🟢 سبز | CONNECTED | متصل و آماده |

---

## لاگ‌ها

- **holoo_api.log** - لاگ سرویس API
- **branch_manager.log** - لاگ برنامه مدیریت

---

## عیب‌یابی

### خطای اتصال به دیتابیس:
1. بررسی کنید SQL Server در حال اجراست
2. بررسی کنید TCP/IP فعال است
3. بررسی کنید یوزر و پسورد درست است
4. بررسی کنید فایروال پورت 1433 را باز کرده

### خطای ODBC:
درایور ODBC را نصب کنید:
https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

### فونت Dana نمایش داده نمی‌شود:
فونت Dana را نصب کنید یا برنامه از فونت Tahoma استفاده می‌کند.

---

## توسعه آینده

- [ ] افزودن کالای جدید
- [ ] مدیریت زیرگروه‌ها
- [ ] گزارش فاکتورها
- [ ] Backup قبل از تغییرات
- [ ] همگام‌سازی خودکار

---

## لایسنس

این پروژه برای استفاده داخلی طراحی شده است.

---

## تماس

در صورت بروز مشکل، لاگ‌ها را بررسی کنید.
