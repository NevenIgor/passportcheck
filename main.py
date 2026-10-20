import sys
import os
from abc import ABC, abstractmethod
from typing import List, Optional
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QListWidget, QLineEdit, QPushButton,
                             QLabel, QSplitter, QInputDialog, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QFont


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
    def get_objects(self, filter_text: str = "") -> List[str]: pass

    @abstractmethod
    def add_subsection(self, object_name: str, subsection_name: str) -> bool: pass

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

    def close(self) -> None:
        if self.conn:
            self.conn.close()

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

    def get_objects(self, filter_text: str = "") -> List[str]:
        query = "SELECT name FROM objects WHERE name LIKE ? ORDER BY name"
        cursor = self.conn.execute(query, (f"%{filter_text}%",))
        return [row["name"] for row in cursor.fetchall()]

    def add_subsection(self, object_name: str, subsection_name: str) -> bool:
        try:
            with self.conn:
                obj = self.conn.execute("SELECT id FROM objects WHERE name = ?", (object_name,)).fetchone()
                if not obj: return False
                self.conn.execute("INSERT INTO subsections (object_id, name) VALUES (?, ?)",
                                  (obj["id"], subsection_name))
            return True
        except sqlite3.IntegrityError:
            return False

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
"""
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

    def init_tables(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("""
CREATE
TABLE
IF
NOT
EXISTS
objects(
    id
SERIAL
PRIMARY
KEY,
name
TEXT
UNIQUE
NOT
NULL
)
""")
cur.execute("""
CREATE
TABLE
IF
NOT
EXISTS
subsections(
    id
SERIAL
PRIMARY
KEY,
object_id
INTEGER
REFERENCES
objects(id)
ON
DELETE
CASCADE,
name
TEXT
NOT
NULL,
pdf_path
TEXT,
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

def get_objects(self, filter_text: str = "") -> List[str]:
with self.conn.cursor() as cur:
cur.execute("SELECT name FROM objects WHERE name ILIKE %s ORDER BY name", (f"%{filter_text}%",))
return [row["name"] for row in cur.fetchall()]

def add_subsection(self, object_name: str, subsection_name: str) -> bool:
try:
with self.conn.cursor() as cur:
    cur.execute("SELECT id FROM objects WHERE name = %s", (object_name,))
    obj = cur.fetchone()
    if not obj: return False
    cur.execute("INSERT INTO subsections (object_id, name) VALUES (%s, %s)", (obj["id"], subsection_name))
self.conn.commit()
return True
except psycopg2.IntegrityError:
self.conn.rollback()
return False

def get_subsections(self, object_name: str) -> List[str]:
with self.conn.cursor() as cur:
cur.execute("""
SELECT
s.name
FROM
subsections
s
JOIN
objects
o
ON
s.object_id = o.id
WHERE
o.name = %s
ORDER
BY
s.name
""", (object_name,))
return [row["name"] for row in cur.fetchall()]

def set_pdf_path(self, object_name: str, subsection_name: str, pdf_path: str) -> bool:
try:
with self.conn.cursor() as cur:
    cur.execute("""
UPDATE
subsections
SET
pdf_path = %s
WHERE
object_id = (SELECT id FROM objects WHERE name = %s)
AND
name = %s
""", (pdf_path, object_name, subsection_name))
self.conn.commit()
return True
except Exception:
self.conn.rollback()
return False

def get_pdf_path(self, object_name: str, subsection_name: str) -> Optional[str]:
with self.conn.cursor() as cur:
cur.execute("""
SELECT
s.pdf_path
FROM
subsections
s
JOIN
objects
o
ON
s.object_id = o.id
WHERE
o.name = %s
AND
s.name = %s
""", (object_name, subsection_name))
row = cur.fetchone()
return row["pdf_path"] if row else None
"""


# ==========================================
# 4. ГЛАВНОЕ ПРИЛОЖЕНИЕ (НЕ ЗАВИСИТ ОТ БД)
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

    def initUI(self):
        self.setWindowTitle('PDF Viewer (DB Independent)')
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        splitter_main = QSplitter(Qt.Horizontal)

        left_panel = self._create_left_panel()
        splitter_main.addWidget(left_panel)

        right_container = QWidget()
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        middle_panel = self._create_middle_panel()
        right_layout.addWidget(middle_panel, 1)

        right_panel = self._create_right_panel()
        right_layout.addWidget(right_panel, 2)

        splitter_main.addWidget(right_container)
        splitter_main.setSizes([300, 300, 600])

        main_layout.addWidget(splitter_main)

        # Первичная загрузка
        self._refresh_objects_list()

    def _create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Поиск")
        self.search_field.textChanged.connect(self._filter_objects)
        layout.addWidget(self.search_field)

        self.objects_list = QListWidget()
        self.objects_list.itemClicked.connect(self._on_object_selected)
        layout.addWidget(self.objects_list)

        self.add_obj_btn = QPushButton("Добавить")
        self.add_obj_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.add_obj_btn.clicked.connect(self._add_object)
        layout.addWidget(self.add_obj_btn)
        return panel

    def _create_middle_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.subsections_list = QListWidget()
        self.subsections_list.itemClicked.connect(self._on_subsection_selected)
        layout.addWidget(self.subsections_list)

        self.add_sub_btn = QPushButton("Добавить раздел")
        self.add_sub_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.add_sub_btn.clicked.connect(self._add_subsection)
        self.add_sub_btn.setEnabled(False)
        layout.addWidget(self.add_sub_btn)
        return panel

    def _create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("НАЗВАНИЕ")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.title_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5; padding: 5px;")
        layout.addWidget(self.title_label)

        self.pdf_viewer = QWebEngineView()
        self.pdf_viewer.setUrl(QUrl("about:blank"))
        layout.addWidget(self.pdf_viewer)

        self.load_pdf_btn = QPushButton("Загрузить PDF файл")
        self.load_pdf_btn.clicked.connect(self._load_pdf_file)
        self.load_pdf_btn.setEnabled(False)
        layout.addWidget(self.load_pdf_btn)
        return panel

    def _refresh_objects_list(self):
        self.objects_list.clear()
        for obj in self.db.get_objects():
            self.objects_list.addItem(obj)

    def _filter_objects(self):
        query = self.search_field.text().lower()
        self.objects_list.clear()
        for obj in self.db.get_objects(query):
            self.objects_list.addItem(obj)

    def _add_object(self):
        text, ok = QInputDialog.getText(self, 'Добавить объект', 'Введите название объекта:')
        if ok and text.strip():
            if self.db.add_object(text.strip()):
                self._refresh_objects_list()
            else:
                QMessageBox.warning(self, 'Ошибка', 'Объект уже существует')

    def _on_object_selected(self, item):
        self.current_object = item.text()
        self.current_subsection = None

        self.subsections_list.clear()
        for sub in self.db.get_subsections(self.current_object):
            self.subsections_list.addItem(sub)

        self.add_sub_btn.setEnabled(True)
        self.title_label.setText("НАЗВАНИЕ")
        self.pdf_viewer.setUrl(QUrl("about:blank"))
        self.load_pdf_btn.setEnabled(False)

    def _add_subsection(self):
        if not self.current_object: return
        text, ok = QInputDialog.getText(self, 'Добавить раздел', 'Введите название раздела:')
        if ok and text.strip():
            if self.db.add_subsection(self.current_object, text.strip()):
                self.subsections_list.addItem(text.strip())
            else:
                QMessageBox.warning(self, 'Ошибка', 'Раздел уже существует')

    def _on_subsection_selected(self, item):
        self.current_subsection = item.text()
        self.title_label.setText(self.current_subsection.upper())
        self.load_pdf_btn.setEnabled(True)

        path = self.db.get_pdf_path(self.current_object, self.current_subsection)
        if path and os.path.exists(path):
            self.pdf_viewer.setUrl(QUrl.fromLocalFile(path))
        else:
            self.pdf_viewer.setUrl(QUrl("about:blank"))

    def _load_pdf_file(self):
        if not self.current_object or not self.current_subsection: return
        path, _ = QFileDialog.getOpenFileName(self, "Выберите PDF", "", "PDF (*.pdf)")
        if path:
            if self.db.set_pdf_path(self.current_object, self.current_subsection, path):
                self.pdf_viewer.setUrl(QUrl.fromLocalFile(path))
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось сохранить путь в БД")

    def closeEvent(self, event):
        self.db.close()
        event.accept()


# ==========================================
# 5. ТОЧКА ВХОДА
# ==========================================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

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