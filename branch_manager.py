#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DakkeManager - مدیریت شعب دکه مارکت
نسخه: 1.0.0
"""

import os
import sys
import json
import toml
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import math

# PyQt5
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QCheckBox, QComboBox, QMessageBox, QDialog,
    QProgressBar, QStatusBar, QFrame, QSplitter, QGroupBox,
    QScrollArea, QTabWidget, QTextEdit, QDialogButtonBox,
    QAbstractItemView, QStyle, QStyleFactory, QSpinBox,
    QSizePolicy, QSpacerItem, QToolButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QFontDatabase

# ============================================
# تنظیمات
# ============================================

APP_VERSION = "1.0.0"
CONFIG_FILE = "branches.toml"
LOG_FILE = "branch_manager.log"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY = 3

# رنگ‌های دکه مارکت
COLORS = {
    "primary": "#15b366",      # سبز دکه مارکت
    "secondary": "#0F8A4F",    # سبز تیره‌تر
    "accent": "#1ADB7A",       # سبز روشن‌تر
    "bg": "#121212",           # پس‌زمینه اصلی
    "surface": "#1e1e1e",      # رنگ کارت‌ها
    "text": "#e0e0e0",
    "danger": "#ff4d4d",
    "warning": "#ffaa00",
    "border": "#333333",
    "row_alt": "#252525",
    "row_hover": "#2a3a2a",
}

# ============================================
# تنظیم لاگ
# ============================================

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
# Enums و Data Classes
# ============================================

class BranchStatus(Enum):
    UNKNOWN = 0
    OFFLINE = 1
    API_DOWN = 2
    AUTH_ERROR = 3
    CONNECTED = 4


@dataclass
class Branch:
    name: str
    ip: str
    database: str
    user: str
    password: str
    port: int = 7480
    status: BranchStatus = BranchStatus.UNKNOWN
    enabled: bool = True
    is_reference: bool = False
    articles: List[Dict] = field(default_factory=list)
    
    @property
    def api_url(self) -> str:
        return f"http://{self.ip}:{self.port}"


# ============================================
# توابع کمکی
# ============================================

def format_price(value) -> str:
    """فرمت قیمت با جداکننده هزارگان"""
    if value is None or value == "" or value == 0:
        return ""
    try:
        num = float(value)
        if num == int(num):
            return "{:,.0f}".format(int(num))
        else:
            return "{:,.2f}".format(num).rstrip('0').rstrip('.')
    except:
        return str(value)


def format_number(value) -> str:
    """فرمت اعداد - حذف صفرهای اضافی"""
    if value is None or value == "":
        return ""
    try:
        num = float(value)
        if num == 0:
            return ""
        if num == int(num):
            return str(int(num))
        return str(num).rstrip('0').rstrip('.')
    except:
        return str(value)


# ============================================
# کلاس API Client
# ============================================

class HolooAPIClient:
    def __init__(self, branch: Branch, api_key: str, timeout: int = DEFAULT_TIMEOUT, retry: int = DEFAULT_RETRY):
        self.branch = branch
        self.api_key = api_key
        self.timeout = timeout
        self.retry = retry
    
    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }
    
    def _db_params(self) -> Dict[str, str]:
        return {
            "server": self.branch.ip,
            "database": self.branch.database,
            "username": self.branch.user,
            "password": self.branch.password
        }
    
    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        url = f"{self.branch.api_url}{endpoint}"
        
        if data is None:
            data = {}
        
        data.update(self._db_params())
        
        last_error = None
        for attempt in range(self.retry):
            try:
                if method.upper() == "GET":
                    response = requests.get(url, timeout=self.timeout)
                else:
                    response = requests.post(
                        url, 
                        json=data, 
                        headers=self._headers(),
                        timeout=self.timeout
                    )
                
                return response.json()
            
            except requests.exceptions.ConnectionError:
                last_error = "عدم دسترسی به سرور"
            except requests.exceptions.Timeout:
                last_error = "تایم‌اوت درخواست"
            except Exception as e:
                last_error = str(e)
            
            if attempt < self.retry - 1:
                time.sleep(1)
        
        return {"success": False, "error": last_error}
    
    def check_health(self) -> BranchStatus:
        try:
            response = requests.get(f"{self.branch.api_url}/ping", timeout=5)
            if response.status_code != 200:
                return BranchStatus.API_DOWN
        except:
            return BranchStatus.OFFLINE
        
        result = self._request("POST", "/check/db")
        
        if not result.get("success"):
            status = result.get("status", "")
            if status in ["DB_AUTH_ERROR", "DB_NOT_FOUND"]:
                return BranchStatus.AUTH_ERROR
            return BranchStatus.API_DOWN
        
        return BranchStatus.CONNECTED
    
    def get_articles(self, search: str = "", limit: int = 50000) -> List[Dict]:
        result = self._request("POST", "/articles", {
            "search": search,
            "limit": limit
        })
        
        if result.get("success"):
            return result.get("data", [])
        return []
    
    def get_groups(self) -> List[Dict]:
        result = self._request("POST", "/groups")
        if result.get("success"):
            return result.get("data", [])
        return []
    
    def update_article(self, code: str, **kwargs) -> Dict:
        return self._request("POST", f"/article/{code}/update", kwargs)
    
    def batch_update(self, items: List[Dict]) -> Dict:
        return self._request("POST", "/batch/update", {"items": items})


# ============================================
# ویجت چراغ وضعیت
# ============================================

class StatusLight(QLabel):
    COLORS = {
        BranchStatus.UNKNOWN: "#808080",
        BranchStatus.OFFLINE: COLORS["danger"],
        BranchStatus.API_DOWN: COLORS["warning"],
        BranchStatus.AUTH_ERROR: COLORS["warning"],
        BranchStatus.CONNECTED: COLORS["primary"],
    }
    
    TOOLTIPS = {
        BranchStatus.UNKNOWN: "نامشخص",
        BranchStatus.OFFLINE: "آفلاین",
        BranchStatus.API_DOWN: "سرویس غیرفعال",
        BranchStatus.AUTH_ERROR: "خطای احراز هویت",
        BranchStatus.CONNECTED: "متصل",
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.set_status(BranchStatus.UNKNOWN)
    
    def set_status(self, status: BranchStatus):
        color = self.COLORS.get(status, "#808080")
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 8px;
                border: 2px solid {COLORS['border']};
            }}
        """)
        self.setToolTip(self.TOOLTIPS.get(status, ""))


# ============================================
# ویجت شعبه
# ============================================

class BranchWidget(QFrame):
    reference_changed = pyqtSignal(object)
    
    def __init__(self, branch: Branch, parent=None):
        super().__init__(parent)
        self.branch = branch
        self.setup_ui()
    
    def setup_ui(self):
        self.setStyleSheet(f"""
            BranchWidget {{
                background-color: {COLORS['surface']};
                border-radius: 8px;
                border: 1px solid {COLORS['border']};
                padding: 4px;
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        
        # چک‌باکس فعال/غیرفعال
        self.enabled_check = QCheckBox()
        self.enabled_check.setChecked(self.branch.enabled)
        self.enabled_check.setToolTip("فعال/غیرفعال کردن شعبه")
        self.enabled_check.toggled.connect(self.on_enabled_changed)
        self.enabled_check.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS['primary']};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.enabled_check)
        
        # چراغ وضعیت
        self.status_light = StatusLight()
        layout.addWidget(self.status_light)
        
        # نام شعبه
        self.name_label = QLabel(self.branch.name)
        self.name_label.setStyleSheet(f"color: {COLORS['text']}; font-weight: bold;")
        layout.addWidget(self.name_label)
        
        # دکمه ستاره (شعبه مرجع)
        self.star_btn = QToolButton()
        self.star_btn.setText("★")
        self.star_btn.setCheckable(True)
        self.star_btn.setChecked(self.branch.is_reference)
        self.star_btn.setToolTip("تعیین به عنوان شعبه مرجع")
        self.star_btn.clicked.connect(self.on_star_clicked)
        self.update_star_style()
        layout.addWidget(self.star_btn)
    
    def on_enabled_changed(self, checked):
        self.branch.enabled = checked
    
    def on_star_clicked(self):
        self.branch.is_reference = self.star_btn.isChecked()
        self.update_star_style()
        self.reference_changed.emit(self.branch)
    
    def update_star_style(self):
        if self.star_btn.isChecked():
            self.star_btn.setStyleSheet(f"""
                QToolButton {{
                    color: {COLORS['warning']};
                    font-size: 16px;
                    border: none;
                    background: transparent;
                }}
            """)
        else:
            self.star_btn.setStyleSheet(f"""
                QToolButton {{
                    color: {COLORS['border']};
                    font-size: 16px;
                    border: none;
                    background: transparent;
                }}
                QToolButton:hover {{
                    color: {COLORS['warning']};
                }}
            """)
    
    def set_as_reference(self, is_ref: bool):
        self.star_btn.setChecked(is_ref)
        self.branch.is_reference = is_ref
        self.update_star_style()
    
    def update_status(self, status: BranchStatus):
        self.branch.status = status
        self.status_light.set_status(status)


# ============================================
# دیالوگ تایید تغییرات
# ============================================

class ConfirmDialog(QDialog):
    def __init__(self, changes: List[Dict], parent=None):
        super().__init__(parent)
        self.changes = changes
        self.confirmed = False
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("تایید تغییرات")
        self.setMinimumSize(600, 400)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['bg']};
                color: {COLORS['text']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        title = QLabel("📋 لیست تغییرات برای اعمال:")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['text']};")
        layout.addWidget(title)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["کد کالا", "شعبه", "فیلد", "مقدار فعلی", "مقدار جدید"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setRowCount(len(self.changes))
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['surface']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
            }}
        """)
        
        for i, change in enumerate(self.changes):
            self.table.setItem(i, 0, QTableWidgetItem(change.get("code", "")))
            self.table.setItem(i, 1, QTableWidgetItem(change.get("branch", "")))
            self.table.setItem(i, 2, QTableWidgetItem(change.get("field", "")))
            self.table.setItem(i, 3, QTableWidgetItem(str(change.get("old_value", ""))))
            self.table.setItem(i, 4, QTableWidgetItem(str(change.get("new_value", ""))))
        
        layout.addWidget(self.table)
        
        self.confirm_check = QCheckBox("✓ تایید می‌کنم که تغییرات بالا اعمال شود")
        self.confirm_check.setStyleSheet(f"color: {COLORS['text']};")
        layout.addWidget(self.confirm_check)
        
        btn_layout = QHBoxLayout()
        
        self.apply_btn = QPushButton("✓ اعمال تغییرات")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:disabled {{
                background-color: {COLORS['border']};
            }}
        """)
        
        self.cancel_btn = QPushButton("✗ انصراف")
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['danger']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
            }}
        """)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)
        
        self.confirm_check.toggled.connect(self.apply_btn.setEnabled)
        self.apply_btn.clicked.connect(self.show_final_warning)
        self.cancel_btn.clicked.connect(self.reject)
    
    def show_final_warning(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("⚠️ هشدار نهایی")
        msg.setText("این تغییرات غیرقابل بازگشت است!")
        msg.setInformativeText("آیا مطمئن هستید؟")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        
        if msg.exec_() == QMessageBox.Yes:
            self.confirmed = True
            self.accept()


# ============================================
# پنجره اصلی
# ============================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.branches: List[Branch] = []
        self.api_key = ""
        self.timeout = DEFAULT_TIMEOUT
        self.retry = DEFAULT_RETRY
        self.pending_changes: List[Dict] = []
        self.all_articles: Dict[str, Dict] = {}
        
        # صفحه‌بندی
        self.current_page = 1
        self.items_per_page = 0  # 0 = همه
        self.total_items = 0
        
        self.load_config()
        self.setup_ui()
        self.setup_style()
        
        QTimer.singleShot(500, self.check_all_branches)
    
    def load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE)
        
        if not os.path.exists(config_path):
            logger.error(f"فایل تنظیمات پیدا نشد: {config_path}")
            QMessageBox.critical(self, "خطا", f"فایل تنظیمات پیدا نشد:\n{config_path}")
            sys.exit(1)
        
        try:
            config = toml.load(config_path)
            
            settings = config.get("settings", {})
            self.api_key = settings.get("api_key", "")
            self.timeout = settings.get("timeout", DEFAULT_TIMEOUT)
            self.retry = settings.get("retry_count", DEFAULT_RETRY)
            
            for i, branch_data in enumerate(config.get("branches", [])):
                branch = Branch(
                    name=branch_data.get("name", ""),
                    ip=branch_data.get("ip", ""),
                    database=branch_data.get("database", ""),
                    user=branch_data.get("user", ""),
                    password=branch_data.get("password", ""),
                    port=branch_data.get("port", 7480),
                    is_reference=(i == 0)  # اولین شعبه مرجع پیش‌فرض
                )
                self.branches.append(branch)
            
            logger.info(f"تنظیمات بارگذاری شد: {len(self.branches)} شعبه")
            
        except Exception as e:
            logger.error(f"خطا در خواندن تنظیمات: {e}")
            QMessageBox.critical(self, "خطا", f"خطا در خواندن تنظیمات:\n{e}")
            sys.exit(1)
    
    def setup_style(self):
        # تنظیم فونت
        font_families = ["Dana", "B Nazanin", "Tahoma", "Segoe UI"]
        available_fonts = QFontDatabase().families()
        
        selected_font = "Tahoma"
        for font_name in font_families:
            matching = [f for f in available_fonts if font_name.lower() in f.lower()]
            if matching:
                selected_font = matching[0]
                break
        
        font = QFont(selected_font, 10)
        self.setFont(font)
        QApplication.instance().setFont(font)
        
        # استایل کلی
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['bg']};
            }}
            QWidget {{
                background-color: {COLORS['bg']};
                color: {COLORS['text']};
                font-family: Dana, "B Nazanin", Tahoma;
            }}
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['secondary']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['border']};
                color: #666;
            }}
            QLineEdit {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px;
                color: {COLORS['text']};
            }}
            QLineEdit:focus {{
                border-color: {COLORS['primary']};
            }}
            QTableWidget {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                gridline-color: {COLORS['border']};
                color: {COLORS['text']};
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QTableWidget::item:selected {{
                background-color: {COLORS['secondary']};
            }}
            QTableWidget::item:alternate {{
                background-color: {COLORS['row_alt']};
            }}
            QHeaderView::section {{
                background-color: {COLORS['secondary']};
                color: white;
                padding: 10px;
                border: none;
                border-bottom: 2px solid {COLORS['primary']};
                font-weight: bold;
            }}
            QCheckBox {{
                spacing: 8px;
                color: {COLORS['text']};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid {COLORS['border']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS['primary']};
                border-color: {COLORS['primary']};
            }}
            QComboBox {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px;
                color: {COLORS['text']};
                min-width: 80px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['surface']};
                color: {COLORS['text']};
                selection-background-color: {COLORS['primary']};
            }}
            QSpinBox {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px;
                color: {COLORS['text']};
            }}
            QStatusBar {{
                background-color: {COLORS['surface']};
                border-top: 1px solid {COLORS['border']};
                color: {COLORS['text']};
            }}
            QScrollBar:vertical {{
                background-color: {COLORS['surface']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLORS['border']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLORS['primary']};
            }}
            QScrollBar:horizontal {{
                background-color: {COLORS['surface']};
                height: 12px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {COLORS['border']};
                border-radius: 6px;
            }}
        """)
    
    def setup_ui(self):
        self.setWindowTitle(f"DakkeManager - مدیریت شعب دکه مارکت - نسخه {APP_VERSION}")
        self.setMinimumSize(1300, 800)
        self.setLayoutDirection(Qt.RightToLeft)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # === ردیف اول: دکمه‌ها و شعب ===
        top_layout = QHBoxLayout()
        
        # دکمه اعمال تغییرات (سمت چپ)
        self.apply_btn = QPushButton("✓ اعمال تغییرات")
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                font-size: 12px;
                padding: 10px 20px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['border']};
            }}
        """)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_changes)
        top_layout.addWidget(self.apply_btn)
        
        # دکمه افزودن کالا (غیرفعال)
        self.add_article_btn = QPushButton("+ افزودن کالا")
        self.add_article_btn.setEnabled(False)
        self.add_article_btn.setToolTip("به زودی...")
        self.add_article_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['border']};
                padding: 10px 15px;
            }}
        """)
        top_layout.addWidget(self.add_article_btn)
        
        top_layout.addStretch()
        
        # شعب
        self.branch_widgets: List[BranchWidget] = []
        for branch in self.branches:
            widget = BranchWidget(branch)
            widget.reference_changed.connect(self.on_reference_changed)
            self.branch_widgets.append(widget)
            top_layout.addWidget(widget)
        
        top_layout.addStretch()
        
        # دکمه وضعیت ارتباط
        self.check_btn = QPushButton("🔄 وضعیت ارتباط")
        self.check_btn.clicked.connect(self.check_all_branches)
        top_layout.addWidget(self.check_btn)
        
        main_layout.addLayout(top_layout)
        
        # === ردیف دوم: کنترل‌ها ===
        control_layout = QHBoxLayout()
        
        # دکمه دریافت اطلاعات
        self.fetch_btn = QPushButton("📥 دریافت اطلاعات از شعب")
        self.fetch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                font-size: 12px;
                padding: 10px 20px;
            }}
        """)
        self.fetch_btn.clicked.connect(self.fetch_all_data)
        control_layout.addWidget(self.fetch_btn)
        
        control_layout.addSpacing(15)
        
        # نوع مقایسه
        control_layout.addWidget(QLabel("نوع مقایسه:"))
        self.compare_combo = QComboBox()
        self.compare_combo.addItems(["نام", "قیمت", "گروه", "موجودی"])
        self.compare_combo.currentIndexChanged.connect(self.update_table)
        control_layout.addWidget(self.compare_combo)
        
        control_layout.addSpacing(15)
        
        # فقط مغایرت‌ها
        self.diff_only_check = QCheckBox("فقط مغایرت‌ها")
        self.diff_only_check.toggled.connect(self.update_table)
        control_layout.addWidget(self.diff_only_check)
        
        control_layout.addSpacing(15)
        
        # جستجو
        control_layout.addWidget(QLabel("🔍 جستجو:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("جستجو در کد یا نام کالا...")
        self.search_edit.setMinimumWidth(200)
        self.search_edit.textChanged.connect(self.filter_table)
        control_layout.addWidget(self.search_edit)
        
        control_layout.addStretch()
        
        # تعداد آیتم در صفحه
        control_layout.addWidget(QLabel("تعداد:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["همه", "50", "100", "200", "500"])
        self.page_size_combo.currentIndexChanged.connect(self.on_page_size_changed)
        control_layout.addWidget(self.page_size_combo)
        
        # سایز فونت
        control_layout.addSpacing(10)
        control_layout.addWidget(QLabel("سایز:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 16)
        self.font_size_spin.setValue(10)
        self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
        control_layout.addWidget(self.font_size_spin)
        
        main_layout.addLayout(control_layout)
        
        # === جدول اصلی ===
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        
        main_layout.addWidget(self.table)
        
        # === صفحه‌بندی ===
        paging_layout = QHBoxLayout()
        
        self.first_page_btn = QPushButton("« اول")
        self.first_page_btn.clicked.connect(self.go_first_page)
        paging_layout.addWidget(self.first_page_btn)
        
        self.prev_page_btn = QPushButton("‹ قبلی")
        self.prev_page_btn.clicked.connect(self.go_prev_page)
        paging_layout.addWidget(self.prev_page_btn)
        
        paging_layout.addStretch()
        
        self.page_label = QLabel("صفحه:")
        paging_layout.addWidget(self.page_label)
        
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self.on_page_changed)
        paging_layout.addWidget(self.page_spin)
        
        self.total_pages_label = QLabel("از 1")
        paging_layout.addWidget(self.total_pages_label)
        
        paging_layout.addStretch()
        
        self.next_page_btn = QPushButton("بعدی ›")
        self.next_page_btn.clicked.connect(self.go_next_page)
        paging_layout.addWidget(self.next_page_btn)
        
        self.last_page_btn = QPushButton("آخر »")
        self.last_page_btn.clicked.connect(self.go_last_page)
        paging_layout.addWidget(self.last_page_btn)
        
        main_layout.addLayout(paging_layout)
        
        # === نوار وضعیت ===
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("آماده")
        
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(200)
        self.statusBar.addPermanentWidget(self.progress)
    
    def on_reference_changed(self, branch: Branch):
        """وقتی شعبه مرجع تغییر میکنه"""
        if branch.is_reference:
            for widget in self.branch_widgets:
                if widget.branch != branch:
                    widget.set_as_reference(False)
    
    def on_page_size_changed(self, index):
        """تغییر تعداد آیتم در صفحه"""
        sizes = [0, 50, 100, 200, 500]
        self.items_per_page = sizes[index]
        self.current_page = 1
        self.update_table()
    
    def on_font_size_changed(self, size):
        """تغییر سایز فونت"""
        font = self.font()
        font.setPointSize(size)
        self.table.setFont(font)
        self.table.verticalHeader().setDefaultSectionSize(size * 3)
    
    def on_page_changed(self, page):
        """تغییر صفحه از SpinBox"""
        if page != self.current_page:
            self.current_page = page
            self.update_table()
    
    def go_first_page(self):
        self.current_page = 1
        self.page_spin.setValue(1)
    
    def go_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.page_spin.setValue(self.current_page)
    
    def go_next_page(self):
        total = self.get_total_pages()
        if self.current_page < total:
            self.current_page += 1
            self.page_spin.setValue(self.current_page)
    
    def go_last_page(self):
        total = self.get_total_pages()
        self.current_page = total
        self.page_spin.setValue(total)
    
    def get_total_pages(self) -> int:
        if self.items_per_page == 0:
            return 1
        return max(1, math.ceil(self.total_items / self.items_per_page))
    
    def update_paging_controls(self):
        """به‌روزرسانی کنترل‌های صفحه‌بندی"""
        total = self.get_total_pages()
        self.page_spin.setMaximum(total)
        self.total_pages_label.setText(f"از {total}")
        
        self.first_page_btn.setEnabled(self.current_page > 1)
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < total)
        self.last_page_btn.setEnabled(self.current_page < total)
    
    def check_all_branches(self):
        self.statusBar.showMessage("در حال بررسی وضعیت شعب...")
        self.check_btn.setEnabled(False)
        
        for i, branch in enumerate(self.branches):
            if branch.enabled:
                client = HolooAPIClient(branch, self.api_key, self.timeout, self.retry)
                status = client.check_health()
                branch.status = status
                self.branch_widgets[i].update_status(status)
                logger.info(f"وضعیت {branch.name}: {status.name}")
            else:
                self.branch_widgets[i].update_status(BranchStatus.UNKNOWN)
        
        self.check_btn.setEnabled(True)
        connected = sum(1 for b in self.branches if b.status == BranchStatus.CONNECTED and b.enabled)
        enabled = sum(1 for b in self.branches if b.enabled)
        self.statusBar.showMessage(f"بررسی انجام شد: {connected} از {enabled} شعبه متصل")
    
    def fetch_all_data(self):
        enabled_branches = [b for b in self.branches if b.enabled and b.status == BranchStatus.CONNECTED]
        
        if not enabled_branches:
            QMessageBox.warning(self, "هشدار", "هیچ شعبه فعال و متصلی وجود ندارد!")
            return
        
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.fetch_btn.setEnabled(False)
        self.statusBar.showMessage("در حال دریافت اطلاعات...")
        
        total = len(enabled_branches)
        
        for i, branch in enumerate(enabled_branches):
            self.statusBar.showMessage(f"دریافت از {branch.name}...")
            
            client = HolooAPIClient(branch, self.api_key, self.timeout, self.retry)
            articles = client.get_articles()
            branch.articles = articles
            
            self.progress.setValue(int((i + 1) / total * 100))
            QApplication.processEvents()
            
            logger.info(f"دریافت {len(articles)} کالا از {branch.name}")
        
        self.progress.setVisible(False)
        self.fetch_btn.setEnabled(True)
        self.current_page = 1
        self.update_table()
        
        total_articles = sum(len(b.articles) for b in self.branches if b.enabled)
        self.statusBar.showMessage(f"دریافت انجام شد: {total_articles} کالا از {len(enabled_branches)} شعبه")
    
    def update_table(self):
        compare_type = self.compare_combo.currentText()
        diff_only = self.diff_only_check.isChecked()
        
        # شعب فعال
        enabled_branches = [b for b in self.branches if b.enabled]
        
        # جمع‌آوری کالاها
        self.all_articles = {}
        
        for branch in enabled_branches:
            for article in branch.articles:
                code = article.get("code", "")
                if code not in self.all_articles:
                    self.all_articles[code] = {
                        "code": code,
                        "branches": {}
                    }
                
                self.all_articles[code]["branches"][branch.name] = {
                    "name": article.get("name", ""),
                    "price": article.get("price", 0),
                    "group_code": article.get("group_code", ""),
                    "group_name": article.get("group_name", ""),
                    "stock1": article.get("stock1", 0),
                    "stock2": article.get("stock2", 0),
                }
        
        # ستون‌ها بر اساس نوع مقایسه
        columns = ["کد کالا", "غیرفعال", "تغییر"]
        
        # نام از شعبه مرجع
        ref_branch = next((b for b in self.branches if b.is_reference and b.enabled), None)
        if ref_branch:
            columns.append(f"نام ({ref_branch.name})")
        else:
            columns.append("نام کالا")
        
        # ستون‌های شعب
        for branch in enabled_branches:
            if compare_type == "نام":
                columns.append(f"{branch.name}")
            elif compare_type == "قیمت":
                columns.append(f"قیمت {branch.name}")
            elif compare_type == "گروه":
                columns.append(f"گروه {branch.name}")
            elif compare_type == "موجودی":
                columns.append(f"موجودی {branch.name}")
        
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        
        # فیلتر و آماده‌سازی داده
        rows_data = []
        
        for code, data in self.all_articles.items():
            values = []
            has_diff = False
            first_value = None
            ref_name = ""
            
            # نام از شعبه مرجع
            if ref_branch and ref_branch.name in data["branches"]:
                ref_name = data["branches"][ref_branch.name].get("name", "")
            elif data["branches"]:
                ref_name = list(data["branches"].values())[0].get("name", "")
            
            for branch in enabled_branches:
                branch_data = data["branches"].get(branch.name, {})
                
                if compare_type == "نام":
                    value = branch_data.get("name", "")
                elif compare_type == "قیمت":
                    value = branch_data.get("price", 0)
                elif compare_type == "گروه":
                    value = branch_data.get("group_name", "") or branch_data.get("group_code", "")
                elif compare_type == "موجودی":
                    value = branch_data.get("stock1", 0)
                else:
                    value = ""
                
                values.append(value)
                
                if first_value is None and value:
                    first_value = value
                elif first_value is not None and value and str(value) != str(first_value):
                    has_diff = True
            
            if diff_only and not has_diff:
                continue
            
            rows_data.append({
                "code": code,
                "ref_name": ref_name,
                "values": values,
                "has_diff": has_diff
            })
        
        self.total_items = len(rows_data)
        
        # صفحه‌بندی
        if self.items_per_page > 0:
            start = (self.current_page - 1) * self.items_per_page
            end = start + self.items_per_page
            display_data = rows_data[start:end]
        else:
            display_data = rows_data
        
        self.update_paging_controls()
        
        # پر کردن جدول
        self.table.setRowCount(len(display_data))
        
        for row_idx, row_data in enumerate(display_data):
            col = 0
            
            # کد کالا
            item = QTableWidgetItem(row_data["code"])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, col, item)
            col += 1
            
            # دکمه غیرفعال (placeholder)
            disable_item = QTableWidgetItem("☐")
            disable_item.setFlags(disable_item.flags() & ~Qt.ItemIsEditable)
            disable_item.setTextAlignment(Qt.AlignCenter)
            disable_item.setForeground(QColor(COLORS['border']))
            self.table.setItem(row_idx, col, disable_item)
            col += 1
            
            # ستون تغییر (قابل ویرایش)
            change_item = QTableWidgetItem("")
            change_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, col, change_item)
            col += 1
            
            # نام از شعبه مرجع
            name_item = QTableWidgetItem(row_data["ref_name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, col, name_item)
            col += 1
            
            # مقادیر شعب
            for value in row_data["values"]:
                if compare_type == "قیمت":
                    display_value = format_price(value)
                elif compare_type == "موجودی":
                    display_value = format_number(value)
                else:
                    display_value = str(value) if value else ""
                
                item = QTableWidgetItem(display_value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignCenter)
                
                if row_data["has_diff"]:
                    item.setBackground(QColor("#3d2a1a"))
                
                self.table.setItem(row_idx, col, item)
                col += 1
        
        self.filter_table()
        self.table.resizeColumnsToContents()
        
        # حداقل عرض ستون‌ها
        for i in range(self.table.columnCount()):
            if self.table.columnWidth(i) < 80:
                self.table.setColumnWidth(i, 80)
    
    def filter_table(self):
        search_text = self.search_edit.text().strip().lower()
        
        for row in range(self.table.rowCount()):
            show = True
            
            if search_text:
                code = self.table.item(row, 0).text().lower() if self.table.item(row, 0) else ""
                name = self.table.item(row, 3).text().lower() if self.table.item(row, 3) else ""
                
                if search_text not in code and search_text not in name:
                    show = False
            
            self.table.setRowHidden(row, not show)
    
    def apply_changes(self):
        if not self.pending_changes:
            QMessageBox.information(self, "اطلاع", "هیچ تغییری برای اعمال وجود ندارد.")
            return
        
        dialog = ConfirmDialog(self.pending_changes, self)
        
        if dialog.exec_() == QDialog.Accepted and dialog.confirmed:
            self.do_apply_changes()
    
    def do_apply_changes(self):
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.apply_btn.setEnabled(False)
        
        success_count = 0
        fail_count = 0
        
        changes_by_branch: Dict[str, List[Dict]] = {}
        
        for change in self.pending_changes:
            branch_name = change.get("branch")
            if branch_name not in changes_by_branch:
                changes_by_branch[branch_name] = []
            changes_by_branch[branch_name].append(change)
        
        total = len(changes_by_branch)
        
        for i, (branch_name, changes) in enumerate(changes_by_branch.items()):
            branch = next((b for b in self.branches if b.name == branch_name), None)
            if not branch or branch.status != BranchStatus.CONNECTED:
                fail_count += len(changes)
                continue
            
            client = HolooAPIClient(branch, self.api_key, self.timeout, self.retry)
            
            items = []
            for change in changes:
                item = {"code": change["code"]}
                field = change["field"]
                
                if field == "قیمت":
                    item["price"] = change["new_value"]
                elif field == "نام":
                    item["name"] = change["new_value"]
                elif field == "گروه":
                    item["group_code"] = change["new_value"]
                
                items.append(item)
            
            result = client.batch_update(items)
            
            if result.get("success"):
                summary = result.get("summary", {})
                success_count += summary.get("success_count", 0)
                fail_count += summary.get("failed_count", 0)
            else:
                fail_count += len(items)
            
            self.progress.setValue(int((i + 1) / total * 100))
            QApplication.processEvents()
        
        self.progress.setVisible(False)
        self.pending_changes = []
        self.apply_btn.setEnabled(False)
        
        logger.info(f"تغییرات اعمال شد: {success_count} موفق، {fail_count} ناموفق")
        
        QMessageBox.information(
            self,
            "نتیجه",
            f"تغییرات اعمال شد\n\n✓ موفق: {success_count}\n✗ ناموفق: {fail_count}"
        )
        
        self.fetch_all_data()
    
    def closeEvent(self, event):
        if self.pending_changes:
            reply = QMessageBox.question(
                self,
                "تایید خروج",
                "تغییرات اعمال نشده‌ای وجود دارد. آیا مطمئن هستید؟",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                event.ignore()
                return
        
        event.accept()


# ============================================
# Main
# ============================================

def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
