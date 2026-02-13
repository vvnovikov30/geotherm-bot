"""
Адаптер для хранения обработанных публикаций в SQLite.
"""

import hashlib
import os
import sqlite3

from ...ports.repository import Repository


class SQLiteSeenRepository(Repository):
    """Реализация Repository для SQLite."""

    def __init__(self, db_path: str):
        """
        Инициализирует репозиторий.

        Args:
            db_path: Путь к файлу базы данных SQLite
        """
        self.db_path = db_path
        self.db_dir = os.path.dirname(db_path)

    def init(self) -> None:
        """Инициализирует базу данных и создает таблицу, если её нет."""
        if self.db_dir and not os.path.exists(self.db_dir):
            os.makedirs(self.db_dir)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                fingerprint TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                published_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        print(f"База данных инициализирована: {self.db_path}")

    def make_fingerprint(self, title: str, url: str) -> str:
        """
        Создает уникальный fingerprint для публикации.

        Args:
            title: Заголовок публикации
            url: URL публикации

        Returns:
            str: Уникальный fingerprint
        """
        combined = f"{title}|{url}".encode("utf-8")
        fingerprint = hashlib.sha256(combined).hexdigest()
        return fingerprint

    def already_seen(self, fingerprint: str) -> bool:
        """
        Проверяет, была ли публикация уже обработана.

        Args:
            fingerprint: Уникальный идентификатор публикации

        Returns:
            bool: True если публикация уже была обработана, False иначе
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM seen_items WHERE fingerprint = ?", (fingerprint,))
        result = cursor.fetchone()

        conn.close()
        return result is not None

    def mark_seen(self, fingerprint: str, url: str, published_at: str) -> None:
        """
        Помечает публикацию как обработанную.

        Args:
            fingerprint: Уникальный идентификатор публикации
            url: URL публикации
            published_at: Дата публикации
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO seen_items (fingerprint, url, published_at)
            VALUES (?, ?, ?)
        """,
            (fingerprint, url, published_at),
        )

        conn.commit()
        conn.close()
