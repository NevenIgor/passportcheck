import sys
import os
from abc import ABC, abstractmethod
from typing import List, Optional

from PyQt5.QtCore import Qt, QUrl, QT_VERSION_STR, QCoreApplication, QSize, QRect
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QPen, QFontMetrics
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLineEdit, QPushButton, QLabel,
    QSplitter, QInputDialog, QMessageBox, QFileDialog, QMenu,
    QToolBar, QAction, QStatusBar, QFrame,
    QStyledItemDelegate, QStyle,
)

# Qt::AA_ShareOpenGLContexts должен быть установлен ДО создания QGuiApplication —
# иначе QtWebEngine печатает предупреждение (а на некоторых сборках работает некорректно).
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover
    sys.exit("Не хватает модуля QtWebEngine. Установите его:\n"
             "  pip install PyQtWebEngine=={}.*\n"
             "(версия должна совпадать с установленным PyQt5)".format(QT_VERSION_STR))


# ==========================================
# 0. ЛОКАЛЬНЫЕ ИКОНКИ (SVG из папки icons/)
# ==========================================
ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

ICON_COLOR_NORMAL = "#34495e"
ICON_COLOR_SELECTED = "#ffffff"
ICON_LIST_SIZE = 18


def _icon_svg_path(name: str) -> str:
    return os.path.join(ICONS_DIR, "mdi-{}.svg".format(name))


def _paint_fallback_icon(pm: QPixmap):
    """Рисует контурную запасную иконку (квадрат с диагональю), если SVG недоступен."""
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(ICON_COLOR_NORMAL))
    pen.setWidth(2)
    painter.setPen(pen)
    s = pm.width()
    m = max(2, s // 8)
    painter.drawRect(m, m, s - 2 * m - 1, s - 2 * m - 1)
    painter.drawLine(m + 2, m + 2, s - m - 3, s - m - 3)
    painter.end()


def _render_svg(path: str, size: int, color: str) -> Optional[QPixmap]:
    """Рендерит SVG напрямую через QSvgRenderer и подкрашивает его в `color`.

    Возвращает None, если файл не найден или SVG некорректен.
    Такой подход не зависит от плагина imageformats/qsvg, который часто
    отсутствует в сборках PyQt5 (на «голых» ПК без интернета иконок тогда нет).
    """
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    # Подкрасим чёрный fill SVG в нужный цвет интерфейса.
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), QColor(color))
    painter.end()
    return pm


def load_icon(name: str, size: int = ICON_LIST_SIZE) -> QIcon:
    """Загружает SVG-иконку из локальной папки icons/ (без интернета).

    Иконка рендерится программно через QSvgRenderer в двух вариантах:
    обычном (тёмно-сером) и для выделения (белом). Если SVG недоступен,
    рисуется корректная запасная иконка — вместо белого квадрата.
    """
    path = _icon_svg_path(name)
    normal = _render_svg(path, size, ICON_COLOR_NORMAL)
    selected = _render_svg(path, size, ICON_COLOR_SELECTED)
    if normal is not None and not normal.isNull():
        icon = QIcon()
        icon.addPixmap(normal, QIcon.Normal)
        if selected is not None:
            icon.addPixmap(selected, QIcon.Selected)
        return icon
    # Запасной вариант: рисуем простой символ программно.
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    _paint_fallback_icon(pm)
    return QIcon(pm)


def apply_list_item_icons(list_widget, name: str):
    """Ставит одинаковую иконку всем элементам списка."""
    icon = load_icon(name)
    list_widget.setIconSize(QSize(ICON_LIST_SIZE, ICON_LIST_SIZE))
    for i in range(list_widget.count()):
        list_widget.item(i).setIcon(icon)


class ListItemIconDelegate(QStyledItemDelegate):
    """Делегат, который рисует иконку элементов списков вручную.

    Нужен потому, что стандартный отрисовщик Fusion при наличии QSS
    игнорирует DecorationRole у элементов QListWidget (иконки «слетают»).
    В обычном состоянии иконка рисуется тёмно-серой, на выделении — белой.
    """

    def __init__(self, size: int = ICON_LIST_SIZE, parent=None):
        super().__init__(parent)
        self._size = size
        self._cache = {}

    def _icon_pixmap(self, item, selected: bool) -> Optional[QPixmap]:
        variant = "sel" if selected else "norm"
        cached = self._cache.get((item, variant))
        if cached is not None:
            return cached
        icon = item.icon()
        pm = None
        if not icon.isNull():
            pm = icon.pixmap(self._size, self._size,
                             QIcon.Selected if selected else QIcon.Normal)
            if pm.isNull():
                pm = icon.pixmap(self._size, self._size)
        if pm is None or pm.isNull():
            pm = QPixmap(self._size, self._size)
            pm.fill(Qt.transparent)
            _paint_fallback_icon(pm)
        self._cache[(item, variant)] = pm
        return pm

    def paint(self, painter, option, index):
        # В QListWidget сам объект QListWidgetItem доступен через UserRole+100
        item = index.data(Qt.UserRole + 100)
        if not isinstance(item, QListWidgetItem):
            item = None
        text = index.data(Qt.DisplayRole) or ""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(0, 1, 0, -1)

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        if selected:
            bg_color, fg_color = QColor("#3b82f6"), QColor("#ffffff")
        elif hovered:
            bg_color, fg_color = QColor("#eaf2fe"), QColor("#34495e")
        else:
            bg_color, fg_color = None, QColor("#34495e")
        if bg_color is not None:
            painter.fillRect(rect, bg_color)

        pad = 10
        gap = 8
        x = rect.left() + pad
        y_mid = rect.center().y()
        if item is not None and isinstance(item, QListWidgetItem):
            pm = self._icon_pixmap(item, selected)
            target_h = min(pm.height(), rect.height() - 4)
            if target_h != pm.height():
                pm = pm.scaled(target_h, target_h, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
            painter.drawPixmap(x, y_mid - pm.height() // 2, pm)
            x += pm.width() + gap

        painter.setPen(fg_color)
        font = painter.font()
        font.setBold(selected)
        painter.setFont(font)
        text_rect = QRect(x, rect.top(), rect.right() - x - pad, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         fm_elide(font, text, text_rect.width()))
        painter.restore()


def fm_elide(font, text: str, width: int) -> str:
    """Обрезает длинное название многоточием по ширине колонки."""
    fm = QFontMetrics(font)
    return fm.elidedText(text, Qt.ElideRight, max(0, width))


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
        cursor = self.conn.execute(query, ("%{}%".format(filter_text),))
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
                        ("%{}%".format(filter_text),))
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

/* --- Фильтр по названию --- */
QLineEdit#FilterField {
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

        # Минимальная ширина панелей выбора объектов и разделов. Колонкам
        # принудительно задаётся minimumWidth, поэтому изначально они занимают
        # ровно этот минимум, а вся остальная ширина достаётся просмотрщику.
        panel_min_w = 220

        self._create_actions()
        self._create_menu_and_toolbar()

        # В тулбаре показываем и иконку, и текст кнопки (текст под иконкой).
        for tb in self.findChildren(QToolBar):
            tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

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
        # Изначальные размеры колонок: первая и вторая — минимальные,
        # третья (просмотр документа) — занимает всё оставшееся место.
        for i in (0, 1):
            splitter.widget(i).setMinimumWidth(panel_min_w)
        splitter.setSizes([panel_min_w, panel_min_w,
                           max(400, self.width() - 2 * panel_min_w)])
        root.addWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Готово")

    def _create_actions(self):
        self.act_add_obj = QAction(load_icon("plus"), "Новый объект", self, shortcut="Ctrl+N",
                                   triggered=self._add_object)
        self.act_rename_obj = QAction(load_icon("pencil-outline"), "Переименовать объект", self,
                                      triggered=self._rename_object)
        self.act_delete_obj = QAction(load_icon("trash-can"), "Удалить объект", self,
                                      triggered=self._delete_object)
        self.act_add_sub = QAction(load_icon("plus"), "Новый раздел", self, shortcut="Ctrl+M",
                                   triggered=self._add_subsection)
        self.act_rename_sub = QAction(load_icon("pencil-outline"), "Переименовать раздел", self,
                                      triggered=self._rename_subsection)
        self.act_delete_sub = QAction(load_icon("trash-can"), "Удалить раздел", self,
                                      triggered=self._delete_subsection)
        self.act_load_pdf = QAction(load_icon("file-pdf-box"), "Привязать PDF…", self, shortcut="Ctrl+O",
                                    triggered=self._load_pdf_file)
        self.act_clear_pdf = QAction(load_icon("close-circle-outline"), "Убрать привязку PDF", self,
                                     triggered=self._clear_pdf)
        self.act_open_ext = QAction(load_icon("web"), "Открыть во внешнем просмотрщике", self,
                                    triggered=self._open_in_external_viewer)
        self.act_refresh = QAction(load_icon("refresh"), "Обновить списки", self, shortcut="F5",
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

        self.filter_field = QLineEdit(objectName="FilterField",
                                      placeholderText="Фильтр по названию…")
        self.filter_field.setToolTip(
            "Фильтр списка объектов по названию (без учёта регистра).\n"
            "Пустое поле — отображаются все объекты.")
        self.filter_field.setClearButtonEnabled(True)
        # Своя иконка лупы из локальной папки (по умолчанию Qt берёт стандартную,
        # которая на некоторых сборках без дополнительных плагинов не отображается).
        search_icon = load_icon("magnify")
        if not search_icon.isNull():
            self.filter_field.addAction(search_icon, QLineEdit.LeadingPosition)
        self.filter_field.textChanged.connect(self._filter_objects)
        lay.addWidget(self.filter_field)

        self.objects_list = QListWidget()
        self.objects_list.setItemDelegate(ListItemIconDelegate(parent=self.objects_list))
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

        btn_add = QPushButton(load_icon("plus"), "Добавить объект", objectName="AddButton")
        btn_add.setIconSize(QSize(16, 16))
        btn_add.clicked.connect(self._add_object)
        lay.addWidget(btn_add)
        return panel

    def _make_subsections_panel(self):
        panel, lay = self._panel_frame("Разделы")

        self.sub_label_ctx = QLabel("Выберите объект слева", objectName="HintLabel")
        lay.addWidget(self.sub_label_ctx)

        self.subsections_list = QListWidget()
        self.subsections_list.setItemDelegate(ListItemIconDelegate(parent=self.subsections_list))
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
        btn_add = QPushButton(load_icon("plus"), "Раздел", objectName="AddButton")
        btn_add.setIconSize(QSize(16, 16))
        btn_add.clicked.connect(self._add_subsection)
        btn_del = QPushButton(load_icon("trash-can"), "Удалить", objectName="GrayButton")
        btn_del.setIconSize(QSize(16, 16))
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
        self.load_pdf_btn = QPushButton(load_icon("file-pdf-box"), "Привязать PDF", objectName="DangerButton")
        self.load_pdf_btn.setIconSize(QSize(16, 16))
        self.load_pdf_btn.clicked.connect(self._load_pdf_file)
        self.clear_pdf_btn = QPushButton(load_icon("close-circle-outline"), "Убрать привязку", objectName="GrayButton")
        self.clear_pdf_btn.setIconSize(QSize(16, 16))
        self.clear_pdf_btn.clicked.connect(self._clear_pdf)
        self.open_ext_btn = QPushButton(load_icon("web"), "Внешний просмотрщик", objectName="GrayButton")
        self.open_ext_btn.setIconSize(QSize(16, 16))
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
            show_warning("Пустое имя", "Название не может быть пустым.", self)
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
                self.pdf_info_label.setText("📎 Файл: {}   ({:,.0f} КБ)".format(path, size_kb))
            elif path:
                self.pdf_info_label.setText("⚠️ Файл не найден по сохранённому пути: {}".format(path))
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
        names = self.db.get_objects(self.filter_field.text().strip())
        for n in names:
            self.objects_list.addItem(n)
        apply_list_item_icons(self.objects_list, "folder-text")
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
            self.status.showMessage("Создан объект «{}»".format(name), 5000)
        else:
            show_warning("Ошибка", "Объект «{}» уже существует.".format(name), self)

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
            self.sub_label_ctx.setText("Объект: {}".format(new))
            self.status.showMessage("Объект «{}» переименован в «{}»".format(old, new), 5000)
        else:
            show_warning("Ошибка", "Объект «{}» уже существует.".format(new), self)

    def _delete_object(self):
        item = self._selected_object_item()
        if not item:
            return
        name = item.text()
        subs = self.db.get_subsections(name)
        msg = "Удалить объект «{}»?".format(name)
        if subs:
            msg += "\n\nВместе с ним будут удалены разделы ({}):\n".format(len(subs)) + \
                   "\n".join("  • {}".format(s) for s in subs[:10])
            if len(subs) > 10:
                msg += "\n  … и ещё {}".format(len(subs) - 10)
        if not self._confirm("Подтверждение удаления", msg):
            return
        if self.db.delete_object(name):
            self.current_object = None
            self.current_subsection = None
            self._refresh_objects_list(keep_selection=False)
            self._on_object_selected(cleared=True)
            self.status.showMessage("Объект «{}» удалён".format(name), 5000)
        else:
            show_critical("Ошибка", "Не удалось удалить объект.", self)

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
        self.sub_label_ctx.setText("Объект: {}".format(self.current_object))
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
        apply_list_item_icons(self.subsections_list, "file-pdf-box")
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
                              "Название раздела для объекта «{}»:".format(self.current_object))
        if not name:
            return
        if self.db.add_subsection(self.current_object, name):
            self._refresh_subsections(select=name)
            self.status.showMessage("Раздел «{}» создан".format(name), 5000)
        else:
            show_warning("Ошибка", "Раздел «{}» уже существует.".format(name), self)

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
            self.status.showMessage("Раздел «{}» переименован в «{}»".format(old, new), 5000)
        else:
            show_warning("Ошибка", "Раздел «{}» уже существует.".format(new), self)

    def _delete_subsection(self):
        item = self._selected_sub_item()
        if not item or not self.current_object:
            return
        name = item.text()
        if not self._confirm("Подтверждение удаления",
                             "Удалить раздел «{}»?\n"
                             "Привязанный PDF-файл с диска удалён не будет.".format(name)):
            return
        if self.db.delete_subsection(self.current_object, name):
            self.current_subsection = None
            self._refresh_subsections()
            self.title_label.setText("Документ не выбран")
            self.pdf_viewer.setUrl(QUrl("about:blank"))
            self._set_pdf_info()
            self._update_actions_state()
            self.status.showMessage("Раздел «{}» удалён".format(name), 5000)
        else:
            show_critical("Ошибка", "Не удалось удалить раздел.", self)

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
                "К разделу «{}» привязан файл".format(self.current_subsection), 5000)
        else:
            show_critical("Ошибка", "Не удалось сохранить путь в БД.", self)

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
                os.system('open "{}"'.format(path))
            else:
                os.system('xdg-open "{}"'.format(path))
        except Exception as e:
            show_critical("Ошибка", "Не удалось открыть файл: {}".format(e), self)

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
