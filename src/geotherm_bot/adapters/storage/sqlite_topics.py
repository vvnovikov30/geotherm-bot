"""
Адаптер для хранения информации о топиках в SQLite.
"""
import os
import sqlite3
from datetime import datetime, timezone

from ...ports.topic_registry import Topic, TopicRegistry


class SQLiteTopicRegistry(TopicRegistry):
    """Реализация TopicRegistry для SQLite."""
    
    def __init__(self, db_path: str):
        """
        Инициализирует реестр топиков.
        
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
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_thread_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                region_key TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'backfill_ru',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_post_at TEXT NULL,
                UNIQUE(chat_id, message_thread_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def upsert_topic(self, chat_id: int, message_thread_id: int, name: str | None) -> Topic:
        """
        Создает или обновляет топик.
        
        Args:
            chat_id: ID чата
            message_thread_id: ID топика
            name: Название топика (может быть None)
        
        Returns:
            Topic: Созданный или обновленный топик
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Проверяем, существует ли топик
        cursor.execute("""
            SELECT id, name FROM topics
            WHERE chat_id = ? AND message_thread_id = ?
        """, (chat_id, message_thread_id))
        
        existing = cursor.fetchone()
        now_str = self._dt_to_str(datetime.now(timezone.utc))
        
        if existing is None:
            # Вставляем новую запись
            final_name = (name if name and name.strip() else 'unknown')
            cursor.execute("""
                INSERT INTO topics (chat_id, message_thread_id, name, created_at)
                VALUES (?, ?, ?, ?)
            """, (chat_id, message_thread_id, final_name, now_str))
            topic_id = cursor.lastrowid
        else:
            # Обновляем существующую запись
            topic_id = existing['id']
            
            # Обновляем name только если передан непустой name и он не 'unknown'
            if name and name.strip() and name.strip() != 'unknown':
                cursor.execute("""
                    UPDATE topics SET name = ? WHERE id = ?
                """, (name.strip(), topic_id))
        
        conn.commit()
        
        # Получаем обновленную запись
        cursor.execute("SELECT * FROM topics WHERE id = ?", (topic_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        return self._row_to_topic(row)
    
    def get_topic(self, chat_id: int, message_thread_id: int) -> Topic | None:
        """
        Получает топик по chat_id и message_thread_id.
        
        Args:
            chat_id: ID чата
            message_thread_id: ID топика
        
        Returns:
            Topic | None: Топик или None если не найден
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM topics
            WHERE chat_id = ? AND message_thread_id = ?
        """, (chat_id, message_thread_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        return self._row_to_topic(row)
    
    def list_topics(self, chat_id: int, enabled_only: bool = True) -> list[Topic]:
        """
        Получает список топиков для чата.
        
        Args:
            chat_id: ID чата
            enabled_only: Если True, возвращать только включенные топики
        
        Returns:
            list[Topic]: Список топиков
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if enabled_only:
            cursor.execute("""
                SELECT * FROM topics
                WHERE chat_id = ? AND enabled = 1
                ORDER BY id
            """, (chat_id,))
        else:
            cursor.execute("""
                SELECT * FROM topics
                WHERE chat_id = ?
                ORDER BY id
            """, (chat_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_topic(row) for row in rows]
    
    def touch_last_post(self, topic_id: int, dt: datetime) -> None:
        """
        Обновляет время последнего поста в топике.
        
        Args:
            topic_id: ID топика
            dt: Время последнего поста
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        dt_str = self._dt_to_str(dt)
        cursor.execute("""
            UPDATE topics SET last_post_at = ? WHERE id = ?
        """, (dt_str, topic_id))
        
        conn.commit()
        conn.close()
    
    def set_region_key(self, topic_id: int, region_key: str) -> None:
        """
        Устанавливает region_key для топика.
        
        Args:
            topic_id: ID топика
            region_key: Ключ региона
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE topics SET region_key = ? WHERE id = ?
        """, (region_key, topic_id))
        
        conn.commit()
        conn.close()
    
    def set_enabled(self, topic_id: int, enabled: bool) -> None:
        """
        Устанавливает статус enabled для топика.
        
        Args:
            topic_id: ID топика
            enabled: Включен ли топик
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE topics SET enabled = ? WHERE id = ?
        """, (1 if enabled else 0, topic_id))
        
        conn.commit()
        conn.close()
    
    def _dt_to_str(self, dt: datetime) -> str:
        """
        Преобразует datetime в ISO строку с timezone (UTC).
        
        Args:
            dt: datetime объект (может быть naive или aware)
        
        Returns:
            str: ISO строка с timezone
        """
        # Приводим к UTC aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    
    def _str_to_dt(self, s: str | None) -> datetime | None:
        """
        Преобразует ISO строку в datetime (UTC aware).
        
        Args:
            s: ISO строка или None
        
        Returns:
            datetime | None: datetime объект (UTC aware) или None
        """
        if s is None:
            return None
        try:
            dt = datetime.fromisoformat(s)
            # Если naive, трактуем как UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    
    def _row_to_topic(self, row: sqlite3.Row) -> Topic:
        """
        Преобразует строку из БД в объект Topic.
        
        Args:
            row: Строка из БД (sqlite3.Row)
        
        Returns:
            Topic: Объект Topic
        """
        return Topic(
            id=row['id'],
            chat_id=row['chat_id'],
            message_thread_id=row['message_thread_id'],
            name=row['name'],
            region_key=row['region_key'],
            mode=row['mode'],
            enabled=bool(row['enabled']),
            created_at=self._str_to_dt(row['created_at']) or datetime.now(timezone.utc),
            last_post_at=self._str_to_dt(row['last_post_at'])
        )
