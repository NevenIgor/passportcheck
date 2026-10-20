import sys
import os
from abc import ABC, abstractmethod
from typing import List, Optional

from PyQt5.QtCore import Qt, QUrl, QT_VERSION_STR, QCoreApplication
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QLineEdit, QPushButton, QLabel,
    QSplitter, QInputDialog, QMessageBox, QFileDialog, QMenu,
    QToolBar, QAction, QStatusBar, QFrame,
)

# Qt::AA_ShareOpenGLContexts должен быть установлен ДО создания QGuiApplication —
# иначе QtWebEngine печатает предупреждение (а на некоторых сборках работает некорректно).
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover
    sys.exit("Не хватает модуля QtWebEngine. Установите его:\n"
             f"  pip install PyQtWebEngine=={QT_VERSION_STR}.*\n"
             "(версия должна совпадать с установленным PyQt5)")


# ==========================================
# 1. АБСТРАКТНЫЙ ИНТЕРФЕЙС БАЗЫ ДАННЫХ
# ==========================================
class IDatabase(ABC):
    """Независимый интерфейс для работы с БД.
    При переходе на другую СУБД нужно реализовать только эти методы."""

    @abstractmethod
    def connect(self, **kwargs) -> None: pass

    @abstractmethod
    def close(self) -> None: pass

    @abstractmethod
    def init_tables(self) -> None: pass

    @abstractmethod
    def add_object(self, name: str) -> bool: pass

    @abstractmethod
    def rename_object(self, old_name: str, new_name: str) -> bool: pass

    @abstractmethod
    def delete_object(self, name: str) -> bool: pass

    @abstractmethod
    def get_objects(self, filter_text: str = "") -> List[str]: pass

    @abstractmethod
    def add_subsection(self, object_name: str, subsection_name: str) -> bool: pass

    @abstractmethod
    def rename_subsection(self, object_name: str, old_name: str, new_name: str) -> bool: pass

    @abstractmethod
    def delete_subsection(self, object_name: str, subsection_name: str) -> bool: pass

    @abstractmethod
    def get_subsections(self, object_name: str) -> List[str]: pass

    @abstractmethod
    def set_pdf_path(self, object_name: str, subsection_name: str, pdf_path: str) -> bool: pass

    @abstractmethod
    def get_pdf_path(self, object_name: str, subsection_name: str) -> Optional[str]: pass


# ==========================================
# 2. РЕАЛИЗАЦИЯ SQLITE
# ==========================================
import sqlite3


class SQLiteDB(IDatabase):
    def __init__(self, db_path: str = "app_data.sqlite"):
        self.db_path = db_path
        self.conn = None

    def connect(self, **kwargs) -> None:
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        # В SQLite внешние ключи по умолчанию отключены — включаем их,
        # иначе ON DELETE CASCADE не будет работать.
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Встроенная функция LOWER() в SQLite работает только для ASCII.
        # Регистрируем Python-версию, чтобы регистронезависимый поиск
        # корректно работал и с кириллицей.
        self.conn.create_function("LOWER", 1, lambda s: s.lower() if isinstance(s, str) else s)

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_tables(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS subsections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    pdf_path TEXT DEFAULT NULL,
                    FOREIGN KEY(object_id) REFERENCES objects(id) ON DELETE CASCADE,
                    UNIQUE(object_id, name)
                )
            """)

    def add_object(self, name: str) -> bool:
        try:
            with self.conn:
                self.conn.execute("INSERT INTO objects (name) VALUES (?)", (name,))
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_object(self, old_name: str, new_name: str) -> bool:
        try:
            with self.conn:
                cur = self.conn.execute("UPDATE objects SET name = ? WHERE name = ?",
                                        (new_name, old_name))
                return cur.rowcount == 1
        except sqlite3.IntegrityError:
            return False

    def delete_object(self, name: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM objects WHERE name = ?", (name,))
            return cur.rowcount == 1

    def get_objects(self, filter_text: str = "") -> List[str]:
        # LOWER(...) — регистронезависимый поиск, в т.ч. для кириллицы
        query = "SELECT name FROM objects WHERE LOWER(name) LIKE LOWER(?) ORDER BY name"
        cursor = self.conn.execute(query, (f"%{filter_text}%",))
        return [row["name"] for row in cursor.fetchall()]

    def add_subsection(self, object_name: str, subsection_name: str) -> bool:
        try:
            with self.conn:
                obj = self.conn.execute("SELECT id FROM objects WHERE name = ?",
                                        (object_name,)).fetchone()
                if not obj:
                    return False
                self.conn.execute("INSERT INTO subsections (object_id, name) VALUES (?, ?)",
                                  (obj["id"], subsection_name))
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_subsection(self, object_name: str, old_name: str, new_name: str) -> bool:
        try:
            with self.conn:
                obj = self.conn.execute("SELECT id FROM objects WHERE name = ?",
                                        (object_name,)).fetchone()
                if not obj:
                    return False
                cur = self.conn.execute(
                    "UPDATE subsections SET name = ? WHERE object_id = ? AND name = ?",
                    (new_name, obj["id"], old_name))
                return cur.rowcount == 1
        except sqlite3.IntegrityError:
            return False

    def delete_subsection(self, object_name: str, subsection_name: str) -> bool:
        with self.conn:
            cur = self.conn.execute("""
                DELETE FROM subsections
                WHERE object_id = (SELECT id FROM objects WHERE name = ?) AND name = ?
            """, (object_name, subsection_name))
            return cur.rowcount == 1

    def get_subsections(self, object_name: str) -> List[str]:
        cursor = self.conn.execute("""
            SELECT s.name FROM subsections s
            JOIN objects o ON s.object_id = o.id
            WHERE o.name = ? ORDER BY s.name
        """, (object_name,))
        return [row["name"] for row in cursor.fetchall()]

    def set_pdf_path(self, object_name: str, subsection_name: str, pdf_path: str) -> bool:
        try:
            with self.conn:
                self.conn.execute("""
                    UPDATE subsections SET pdf_path = ?
                    WHERE object_id = (SELECT id FROM objects WHERE name = ?)
                    AND name = ?
                """, (pdf_path, object_name, subsection_name))
            return True
        except Exception:
            return False

    def get_pdf_path(self, object_name: str, subsection_name: str) -> Optional[str]:
        cursor = self.conn.execute("""
            SELECT s.pdf_path FROM subsections s
            JOIN objects o ON s.object_id = o.id
            WHERE o.name = ? AND s.name = ?
        """, (object_name, subsection_name))
        row = cursor.fetchone()
        return row["pdf_path"] if row else None


# ==========================================
# 3. РЕАЛИЗАЦИЯ POSTGRESQL (пример)
# ==========================================
# pip install psycopg2-binary
'''
import psycopg2
from psycopg2.extras import RealDictCursor

class PostgreSQLDB(IDatabase):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn = None

    def connect(self, **kwargs) -> None:
        self.conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_tables(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS objects (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subsections (
                    id SERIAL PRIMARY KEY,
                    object_id INTEGER REFERENCES objects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    pdf_path TEXT,
                    UNIQUE(object_id, name)
                )
            """)
        self.conn.commit()

    def add_object(self, name: str) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO objects (name) VALUES (%s)", (name,))
            self.conn.commit()
            return True
        except psycopg2.IntegrityError:
            self.conn.rollback()
            return False

    def rename_object(self, old_name: str, new_name: str) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE objects SET name = %s WHERE name = %s", (new_name, old_name))
                ok = cur.rowcount == 1
            self.conn.commit()
            return ok
        except psycopg2.IntegrityError:
            self.conn.rollback()
            return False

    def delete_object(self, name: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM objects WHERE name = %s", (name,))
            ok = cur.rowcount == 1
        self.conn.commit()
        return ok

    def get_objects(self, filter_text: str = "") -> List[str]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT name FROM objects WHERE name ILIKE %s ORDER BY name",
                        (f"%{filter_text}%",))
            return [row["name"] for row in cur.fetchall()]

    def add_subsection(self, object_name: str, subsection_name: str) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT id FROM objects WHERE name = %s", (object_name,))
                obj = cur.fetchone()
                if not obj:
                    return False
                cur.execute("INSERT INTO subsections (object_id, name) VALUES (%s, %s)",
                            (obj["id"], subsection_name))
            self.conn.commit()
            return True
        except psycopg2.IntegrityError:
            self.conn.rollback()
            return False

    def rename_subsection(self, object_name: str, old_name: str, new_name: str) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT id FROM objects WHERE name = %s", (object_name,))
                obj = cur.fetchone()
                if not obj:
                    return False
                cur.execute("UPDATE subsections SET name = %s WHERE object_id = %s AND name = %s",
                            (new_name, obj["id"], old_name))
                ok = cur.rowcount == 1
            self.conn.commit()
            return ok
        except psycopg2.IntegrityError:
            self.conn.rollback()
            return False

    def delete_subsection(self, object_name: str, subsection_name: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("""
                DELETE FROM subsections
                WHERE object_id = (SELECT id FROM objects WHERE name = %s) AND name = %s
            """, (object_name, subsection_name))
            ok = cur.rowcount == 1
        self.conn.commit()
        return ok

    def get_subsections(self, object_name: str) -> List[str]:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT s.name FROM subsections s
                JOIN objects o ON s.object_id = o.id
                WHERE o.name = %s ORDER BY s.name
            """, (object_name,))
            return [row["name"] for row in cur.fetchall()]

    def set_pdf_path(self, object_name: str, subsection_name: str, pdf_path: str) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE subsections SET pdf_path = %s
                    WHERE object_id = (SELECT id FROM objects WHERE name = %s)
                    AND name = %s
                """, (pdf_path, object_name, subsection_name))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def get_pdf_path(self, object_name: str, subsection_name: str) -> Optional[str]:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT s.pdf_path FROM subsections s
                JOIN objects o ON s.object_id = o.id
                WHERE o.name = %s AND s.name = %s
            """, (object_name, subsection_name))
            row = cur.fetchone()
            return row["pdf_path"] if row else None
'''


# ==========================================
# 4. СТИЛИ (QSS) — современный светлый интерфейс
# ==========================================
APP_STYLESHEET = """
* { font-family: "Segoe UI", "Noto Sans", Arial, sans-serif; font-size: 13px; }
QMainWindow, QWidget#CentralRoot { background-color: #eef1f6; }

/* --- Панели --- */
QFrame#Panel {
    background-color: #ffffff;
    border: 1px solid #d9dee7;
    border-radius: 10px;
}
QLabel#PanelTitle { color: #2c3e50; font-size: 14px; font-weight: bold; padding: 2px; }
QLabel#HintLabel { color: #8a94a6; }

/* --- Поиск --- */
QLineEdit {
    border: 1px solid #d0d7e2;
    border-radius: 6px;
    padding: 6px 10px;
    background-color: #f8fafd;
    selection-background-color: #3b82f6;
}
QLineEdit:focus { border: 1px solid #3b82f6; background-color: #ffffff; }

/* --- Списки --- */
QListWidget { border: none; background-color: transparent; outline: 0; }
QListWidget::item {
    padding: 8px 10px;
    margin: 2px 4px;
    border-radius: 6px;
    color: #34495e;
    border: 1px solid transparent;
}
QListWidget::item:hover { background-color: #eaf2fe; }
QListWidget::item:selected { background-color: #3b82f6; color: #ffffff; font-weight: bold; }

/* --- Кнопки --- */
QPushButton {
    border: none; border-radius: 6px; padding: 8px 14px;
    font-weight: bold; color: white; background-color: #64748b;
}
QPushButton:hover { background-color: #475569; }
QPushButton:pressed { background-color: #334155; }
QPushButton:disabled { background-color: #cbd5e1; color: #8a94a6; }
QPushButton#AddButton   { background-color: #16a34a; }
QPushButton#AddButton:hover   { background-color: #15803d; }
QPushButton#AddButton:pressed { background-color: #166534; }
QPushButton#DangerButton { background-color: #dc2626; }
QPushButton#DangerButton:hover   { background-color: #b91c1c; }
QPushButton#DangerButton:pressed { background-color: #991b1b; }
QPushButton#GrayButton { background-color: #94a3b8; }
QPushButton#GrayButton:hover { background-color: #64748b; }

/* --- Заголовок документа --- */
QLabel#DocTitle {
    background-color: #2c3e50; color: #ffffff;
    border-radius: 8px; padding: 10px 14px; font-size: 15px; font-weight: bold;
}

/* --- Просмотр PDF --- */
QFrame#ViewerFrame { background-color: #ffffff; border: 1px solid #d9dee7; border-radius: 10px; }

/* --- Меню, тулбар, статус --- */
QMenuBar { background-color: #2c3e50; color: #ecf0f1; }
QMenuBar::item { background: transparent; padding: 6px 12px; }
QMenuBar::item:selected { background-color: #3b82f6; }
QMenu { background-color: #ffffff; border: 1px solid #d0d7e2; border-radius: 6px; padding: 4px; }
QMenu::item { padding: 6px 24px; border-radius: 4px; color: #34495e; }
QMenu::item:selected { background-color: #eaf2fe; color: #1d4ed8; }
QMenu::item:disabled { color: #b0b8c4; }
QMenu::separator { height: 1px; background: #e2e8f0; margin: 4px 8px; }
QToolBar { background-color: #ffffff; border-bottom: 1px solid #d9dee7; spacing: 6px; padding: 4px; }
QToolButton {
    background-color: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 5px 10px; color: #34495e; font-weight: bold;
}
QToolButton:hover { background-color: #eaf2fe; border-color: #bfd6fb; }
QToolButton:pressed { background-color: #dbeafe; }
QToolButton:disabled { color: #b0b8c4; background: transparent; border: none; }
QStatusBar { background-color: #2c3e50; color: #bdc3c7; }
QStatusBar::item { border: none; }
QSplitter::handle { background-color: transparent; }
"""


# ==========================================
# 5. ГЛАВНОЕ ПРИЛОЖЕНИЕ (НЕ ЗАВИСИТ ОТ БД)
# ==========================================
class PDFViewerApp(QMainWindow):
    def __init__(self, db: IDatabase):
        super().__init__()
        self.db = db
        self.current_object = None
        self.current_subsection = None

        # Инициализация БД
        self.db.connect()
        self.db.init_tables()

        self.initUI()
        self._refresh_objects_list()
        self._update_actions_state()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def initUI(self):
        self.setWindowTitle("Просмотр PDF-документов")
        self.resize(1280, 820)
        self.setStyleSheet(APP_STYLESHEET)

        self._create_actions()
        self._create_menu_and_toolbar()

        central = QWidget(objectName="CentralRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        splitter.addWidget(self._make_objects_panel())
        splitter.addWidget(self._make_subsections_panel())
        splitter.addWidget(self._make_viewer_panel())
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([280, 300, 660])
        root.addWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Готово")

    def _create_actions(self):
        self.act_add_obj = QAction("➕  Новый объект", self, shortcut="Ctrl+N",
                                   triggered=self._add_object)
        self.act_rename_obj = QAction("✏️  Переименовать объект", self,
                                      triggered=self._rename_object)
        self.act_delete_obj = QAction("🗑️  Удалить объект", self,
                                      triggered=self._delete_object)
        self.act_add_sub = QAction("➕  Новый раздел", self, shortcut="Ctrl+M",
                                   triggered=self._add_subsection)
        self.act_rename_sub = QAction("✏️  Переименовать раздел", self,
                                      triggered=self._rename_subsection)
        self.act_delete_sub = QAction("🗑️  Удалить раздел", self,
                                      triggered=self._delete_subsection)
        self.act_load_pdf = QAction("📄  Привязать PDF…", self, shortcut="Ctrl+O",
                                    triggered=self._load_pdf_file)
        self.act_clear_pdf = QAction("❌  Убрать привязку PDF", self,
                                     triggered=self._clear_pdf)
        self.act_open_ext = QAction("🌐  Открыть во внешнем просмотрщике", self,
                                    triggered=self._open_in_external_viewer)
        self.act_refresh = QAction("🔄  Обновить списки", self, shortcut="F5",
                                   triggered=self._refresh_all)
        self.act_quit = QAction("Выход", self, shortcut="Ctrl+Q",
                                triggered=self.close)

    def _create_menu_and_toolbar(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&Файл")
        m_file.addActions([self.act_add_obj, self.act_add_sub])
        m_file.addSeparator()
        m_file.addActions([self.act_load_pdf, self.act_open_ext])
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_edit = mb.addMenu("&Правка")
        m_edit.addActions([self.act_rename_obj, self.act_delete_obj])
        m_edit.addSeparator()
        m_edit.addActions([self.act_rename_sub, self.act_delete_sub, self.act_clear_pdf])
        m_edit.addSeparator()
        m_edit.addAction(self.act_refresh)

        tb = QToolBar("Основная")
        tb.setMovable(False)
        self.addToolBar(tb)
        for a in (self.act_add_obj, self.act_rename_obj, self.act_delete_obj, None,
                  self.act_add_sub, self.act_rename_sub, self.act_delete_sub, None,
                  self.act_load_pdf, self.act_clear_pdf, self.act_open_ext):
            if a is None:
                tb.addSeparator()
            else:
                tb.addAction(a)

    def _panel_frame(self, title: str):
        """Возвращает (QFrame с панелью, QVBoxLayout для содержимого)."""
        frame = QFrame(objectName="Panel")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lbl = QLabel(title, objectName="PanelTitle")
        lay.addWidget(lbl)
        return frame, lay

    def _make_objects_panel(self):
        panel, lay = self._panel_frame("Объекты")

        self.search_field = QLineEdit(placeholderText="🔍  Поиск объекта…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._filter_objects)
        lay.addWidget(self.search_field)

        self.objects_list = QListWidget()
        self.objects_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.objects_list.customContextMenuRequested.connect(self._objects_menu)
        self.objects_list.itemSelectionChanged.connect(self._on_object_selected)
        self.objects_list.itemDoubleClicked.connect(lambda *_: self._rename_object())
        lay.addWidget(self.objects_list, 1)

        self.empty_obj_hint = QLabel("Список пуст.\nСоздайте первый объект\n(Ctrl+N).",
                                     objectName="HintLabel")
        self.empty_obj_hint.setAlignment(Qt.AlignCenter)
        self.empty_obj_hint.hide()
        lay.addWidget(self.empty_obj_hint)

        btn_add = QPushButton("➕  Добавить объект", objectName="AddButton")
        btn_add.clicked.connect(self._add_object)
        lay.addWidget(btn_add)
        return panel

    def _make_subsections_panel(self):
        panel, lay = self._panel_frame("Разделы")

        self.sub_label_ctx = QLabel("Выберите объект слева", objectName="HintLabel")
        lay.addWidget(self.sub_label_ctx)

        self.subsections_list = QListWidget()
        self.subsections_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.subsections_list.customContextMenuRequested.connect(self._subsections_menu)
        self.subsections_list.itemSelectionChanged.connect(self._on_subsection_selected)
        self.subsections_list.itemDoubleClicked.connect(lambda *_: self._rename_subsection())
        lay.addWidget(self.subsections_list, 1)

        self.empty_sub_hint = QLabel("Разделов пока нет.\nДобавьте первый раздел\n(Ctrl+M).",
                                     objectName="HintLabel")
        self.empty_sub_hint.setAlignment(Qt.AlignCenter)
        self.empty_sub_hint.hide()
        lay.addWidget(self.empty_sub_hint)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕  Раздел", objectName="AddButton")
        btn_add.clicked.connect(self._add_subsection)
        btn_del = QPushButton("🗑️  Удалить", objectName="GrayButton")
        btn_del.clicked.connect(self._delete_subsection)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        lay.addLayout(btn_row)
        return panel

    def _make_viewer_panel(self):
        panel, lay = self._panel_frame("Документ")

        self.title_label = QLabel("Документ не выбран", objectName="DocTitle")
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.title_label)

        self.pdf_viewer = QWebEngineView()
        self.pdf_viewer.setUrl(QUrl("about:blank"))
        frame = QFrame(objectName="ViewerFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self.pdf_viewer)
        lay.addWidget(frame, 1)

        self.pdf_info_label = QLabel("", objectName="HintLabel")
        self.pdf_info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.pdf_info_label.setWordWrap(True)
        lay.addWidget(self.pdf_info_label)

        btn_row = QHBoxLayout()
        self.load_pdf_btn = QPushButton("📄  Привязать PDF", objectName="DangerButton")
        self.load_pdf_btn.clicked.connect(self._load_pdf_file)
        self.clear_pdf_btn = QPushButton("Убрать привязку", objectName="GrayButton")
        self.clear_pdf_btn.clicked.connect(self._clear_pdf)
        self.open_ext_btn = QPushButton("🌐  Внешний просмотрщик", objectName="GrayButton")
        self.open_ext_btn.clicked.connect(self._open_in_external_viewer)
        for b in (self.load_pdf_btn, self.clear_pdf_btn, self.open_ext_btn):
            btn_row.addWidget(b)
        lay.addLayout(btn_row)
        return panel

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------
    def _ask_name(self, title: str, label: str, initial: str = "") -> Optional[str]:
        text, ok = QInputDialog.getText(self, title, label, text=initial)
        if not ok:
            return None
        text = text.strip()
        if not text:
            QMessageBox.warning(self, "Пустое имя", "Название не может быть пустым.")
            return None
        return text

    def _confirm(self, title: str, message: str) -> bool:
        res = QMessageBox.question(
            self, title, message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return res == QMessageBox.Yes

    def _selected_object_item(self):
        items = self.objects_list.selectedItems()
        return items[0] if items else None

    def _selected_sub_item(self):
        items = self.subsections_list.selectedItems()
        return items[0] if items else None

    def _update_actions_state(self):
        has_obj = self.current_object is not None
        has_sub = self.current_subsection is not None
        self.act_rename_obj.setEnabled(has_obj)
        self.act_delete_obj.setEnabled(has_obj)
        self.act_add_sub.setEnabled(has_obj)
        self.act_rename_sub.setEnabled(has_sub)
        self.act_delete_sub.setEnabled(has_sub)
        self.act_load_pdf.setEnabled(has_sub)
        self.act_clear_pdf.setEnabled(has_sub)
        path = (self.db.get_pdf_path(self.current_object, self.current_subsection)
                if has_obj and has_sub else None)
        self.act_open_ext.setEnabled(bool(path) and os.path.exists(path or ""))

    def _set_pdf_info(self):
        if self.current_object and self.current_subsection:
            path = self.db.get_pdf_path(self.current_object, self.current_subsection)
            if path and os.path.exists(path):
                size_kb = os.path.getsize(path) / 1024
                self.pdf_info_label.setText(f"📎 Файл: {path}   ({size_kb:,.0f} КБ)")
            elif path:
                self.pdf_info_label.setText(f"⚠️ Файл не найден по сохранённому пути: {path}")
            else:
                self.pdf_info_label.setText("PDF не привязан к этому разделу.")
        else:
            self.pdf_info_label.setText("")

    # ------------------------------------------------------------------
    # Объекты
    # ------------------------------------------------------------------
    def _refresh_objects_list(self, keep_selection: bool = True,
                              select: Optional[str] = None):
        prev = self.current_object if keep_selection else None
        self.objects_list.blockSignals(True)
        self.objects_list.clear()
        names = self.db.get_objects(self.search_field.text().strip())
        for n in names:
            self.objects_list.addItem(n)
        self.objects_list.blockSignals(False)
        self.empty_obj_hint.setVisible(not names)

        target = select or prev
        if target:
            items = self.objects_list.findItems(target, Qt.MatchExactly)
            if items:
                self.objects_list.setCurrentItem(items[0])
                return
        # если целевого элемента нет (например, после удаления) — сбрасываем состояние
        if prev and not select:
            self._on_object_selected(cleared=True)

    def _filter_objects(self):
        self._refresh_objects_list()

    def _add_object(self):
        name = self._ask_name("Новый объект", "Введите название объекта:")
        if not name:
            return
        if self.db.add_object(name):
            self._refresh_objects_list(select=name)
            self.status.showMessage(f"Создан объект «{name}»", 5000)
        else:
            QMessageBox.warning(self, "Ошибка", f"Объект «{name}» уже существует.")

    def _rename_object(self):
        item = self._selected_object_item()
        if not item:
            return
        old = item.text()
        new = self._ask_name("Переименовать объект", "Новое название объекта:", initial=old)
        if not new or new == old:
            return
        if self.db.rename_object(old, new):
            self.current_object = new
            self._refresh_objects_list(keep_selection=False, select=new)
            self.sub_label_ctx.setText(f"Объект: {new}")
            self.status.showMessage(f"Объект «{old}» переименован в «{new}»", 5000)
        else:
            QMessageBox.warning(self, "Ошибка", f"Объект «{new}» уже существует.")

    def _delete_object(self):
        item = self._selected_object_item()
        if not item:
            return
        name = item.text()
        subs = self.db.get_subsections(name)
        msg = f"Удалить объект «{name}»?"
        if subs:
            msg += f"\n\nВместе с ним будут удалены разделы ({len(subs)}):\n" + \
                   "\n".join(f"  • {s}" for s in subs[:10])
            if len(subs) > 10:
                msg += f"\n  … и ещё {len(subs) - 10}"
        if not self._confirm("Подтверждение удаления", msg):
            return
        if self.db.delete_object(name):
            self.current_object = None
            self.current_subsection = None
            self._refresh_objects_list(keep_selection=False)
            self._on_object_selected(cleared=True)
            self.status.showMessage(f"Объект «{name}» удалён", 5000)
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось удалить объект.")

    def _on_object_selected(self, cleared: bool = False):
        if cleared:
            self.current_object = None
            self.subsections_list.blockSignals(True)
            self.subsections_list.clear()
            self.subsections_list.blockSignals(False)
            self.empty_sub_hint.hide()
            self.sub_label_ctx.setText("Выберите объект слева")
            self._on_subsection_selected(cleared=True)
            self._update_actions_state()
            return

        item = self._selected_object_item()
        if not item or item.text() == self.current_object:
            return
        self.current_object = item.text()
        self.current_subsection = None
        self.sub_label_ctx.setText(f"Объект: {self.current_object}")
        self._refresh_subsections()
        self.title_label.setText("Документ не выбран")
        self.pdf_viewer.setUrl(QUrl("about:blank"))
        self._set_pdf_info()
        self._update_actions_state()

    def _objects_menu(self, pos):
        item = self.objects_list.itemAt(pos)
        menu = QMenu(self)
        menu.addAction(self.act_add_obj)
        if item:
            self.objects_list.setCurrentItem(item)
            menu.addSeparator()
            menu.addAction(self.act_rename_obj)
            menu.addAction(self.act_delete_obj)
        menu.exec_(self.objects_list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Разделы
    # ------------------------------------------------------------------
    def _refresh_subsections(self, select: Optional[str] = None):
        self.subsections_list.blockSignals(True)
        self.subsections_list.clear()
        names = self.db.get_subsections(self.current_object) if self.current_object else []
        for n in names:
            self.subsections_list.addItem(n)
        self.subsections_list.blockSignals(False)
        self.empty_sub_hint.setVisible(not names)
        if select:
            items = self.subsections_list.findItems(select, Qt.MatchExactly)
            if items:
                self.subsections_list.setCurrentItem(items[0])

    def _add_subsection(self):
        if not self.current_object:
            return
        name = self._ask_name("Новый раздел",
                              f"Название раздела для объекта «{self.current_object}»:")
        if not name:
            return
        if self.db.add_subsection(self.current_object, name):
            self._refresh_subsections(select=name)
            self.status.showMessage(f"Раздел «{name}» создан", 5000)
        else:
            QMessageBox.warning(self, "Ошибка", f"Раздел «{name}» уже существует.")

    def _rename_subsection(self):
        item = self._selected_sub_item()
        if not item or not self.current_object:
            return
        old = item.text()
        new = self._ask_name("Переименовать раздел", "Новое название раздела:", initial=old)
        if not new or new == old:
            return
        if self.db.rename_subsection(self.current_object, old, new):
            self.current_subsection = new
            self._refresh_subsections(select=new)
            self.title_label.setText(new)
            self._set_pdf_info()
            self._update_actions_state()
            self.status.showMessage(f"Раздел «{old}» переименован в «{new}»", 5000)
        else:
            QMessageBox.warning(self, "Ошибка", f"Раздел «{new}» уже существует.")

    def _delete_subsection(self):
        item = self._selected_sub_item()
        if not item or not self.current_object:
            return
        name = item.text()
        if not self._confirm("Подтверждение удаления",
                             f"Удалить раздел «{name}»?\n"
                             "Привязанный PDF-файл с диска удалён не будет."):
            return
        if self.db.delete_subsection(self.current_object, name):
            self.current_subsection = None
            self._refresh_subsections()
            self.title_label.setText("Документ не выбран")
            self.pdf_viewer.setUrl(QUrl("about:blank"))
            self._set_pdf_info()
            self._update_actions_state()
            self.status.showMessage(f"Раздел «{name}» удалён", 5000)
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось удалить раздел.")

    def _on_subsection_selected(self, cleared: bool = False):
        if cleared:
            self.current_subsection = None
            self.title_label.setText("Документ не выбран")
            self.pdf_viewer.setUrl(QUrl("about:blank"))
            self._set_pdf_info()
            self._update_actions_state()
            return

        item = self._selected_sub_item()
        if not item:
            return
        self.current_subsection = item.text()
        self.title_label.setText(self.current_subsection)
        self._set_pdf_info()

        path = self.db.get_pdf_path(self.current_object, self.current_subsection)
        if path and os.path.exists(path):
            self.pdf_viewer.setUrl(QUrl.fromLocalFile(path))
        else:
            self.pdf_viewer.setUrl(QUrl("about:blank"))
        self._update_actions_state()

    def _subsections_menu(self, pos):
        item = self.subsections_list.itemAt(pos)
        menu = QMenu(self)
        if self.current_object:
            menu.addAction(self.act_add_sub)
        if item:
            self.subsections_list.setCurrentItem(item)
            menu.addSeparator()
            menu.addAction(self.act_rename_sub)
            menu.addAction(self.act_delete_sub)
            menu.addAction(self.act_clear_pdf)
            menu.addSeparator()
            menu.addAction(self.act_load_pdf)
        if menu.actions():
            menu.exec_(self.subsections_list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    def _load_pdf_file(self):
        if not self.current_object or not self.current_subsection:
            return
        start_dir = os.path.dirname(self.db.get_pdf_path(
            self.current_object, self.current_subsection) or "")
        path, _ = QFileDialog.getOpenFileName(self, "Выберите PDF-файл",
                                              start_dir, "Документы PDF (*.pdf)")
        if not path:
            return
        if self.db.set_pdf_path(self.current_object, self.current_subsection, path):
            self.pdf_viewer.setUrl(QUrl.fromLocalFile(path))
            self._set_pdf_info()
            self._update_actions_state()
            self.status.showMessage(
                f"К разделу «{self.current_subsection}» привязан файл", 5000)
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить путь в БД.")

    def _clear_pdf(self):
        if not self.current_object or not self.current_subsection:
            return
        if self.db.set_pdf_path(self.current_object, self.current_subsection, ""):
            self.pdf_viewer.setUrl(QUrl("about:blank"))
            self._set_pdf_info()
            self._update_actions_state()
            self.status.showMessage("Привязка PDF убрана (файл остался на диске)", 5000)

    def _open_in_external_viewer(self):
        if not self.current_object or not self.current_subsection:
            return
        path = self.db.get_pdf_path(self.current_object, self.current_subsection)
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Файл не найден",
                                    "Для этого раздела PDF не привязан или файл отсутствует.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл: {e}")

    # ------------------------------------------------------------------
    def _refresh_all(self):
        self._refresh_objects_list()
        if self.current_object:
            self._refresh_subsections(select=self.current_subsection)
        self.status.showMessage("Списки обновлены", 3000)

    def closeEvent(self, event):
        self.db.close()
        event.accept()


# ==========================================
# 6. ТОЧКА ВХОДА
# ==========================================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("PDF Viewer")

    # >>> ЗДЕСЬ МЕНЯЕТСЯ ТИП БАЗЫ ДАННЫХ <<<
    # Вариант 1: SQLite (по умолчанию)
    database = SQLiteDB("my_app.db")

    # Вариант 2: PostgreSQL (раскомментируйте и настройте DSN)
    # database = PostgreSQLDB("dbname=mydb user=postgres password=secret host=localhost")

    window = PDFViewerApp(database)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
