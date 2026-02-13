"""
Адаптер для очереди контента и глобального seen в SQLite.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from ...ports.queue import ContentQueue, QueueItem


class SQLiteContentQueue(ContentQueue):
    """Реализация ContentQueue для SQLite."""
    
    def __init__(self, db_path: str, seen_ttl_days_discovery: int | None = None):
        """
        Инициализирует очередь контента.
        
        Args:
            db_path: Путь к файлу базы данных SQLite (та же БД, что и для topics)
            seen_ttl_days_discovery: TTL в днях для discovery элементов
                (если None, читается из SEEN_TTL_DAYS_DISCOVERY env, по умолчанию 30)
        """
        self.db_path = db_path
        self.db_dir = os.path.dirname(db_path)
        
        if seen_ttl_days_discovery is None:
            # Читаем из переменной окружения
            ttl_str = os.getenv("SEEN_TTL_DAYS_DISCOVERY", "30")
            try:
                self.seen_ttl_days_discovery = int(ttl_str)
            except (ValueError, TypeError):
                self.seen_ttl_days_discovery = 30
        else:
            self.seen_ttl_days_discovery = seen_ttl_days_discovery
    
    def init(self) -> None:
        """Инициализирует базу данных и создает таблицы, если их нет."""
        if self.db_dir and not os.path.exists(self.db_dir):
            os.makedirs(self.db_dir)
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Включаем foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        
        # Создаем таблицу content_queue
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT NULL,
                url TEXT NULL,
                score INTEGER NOT NULL,
                reasons_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL,
                posted_at TEXT NULL,
                UNIQUE(topic_id, external_id),
                FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
            )
        """)
        
        # Создаем таблицу seen
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                external_id TEXT PRIMARY KEY,
                first_seen_at TEXT NOT NULL,
                source_kind TEXT NOT NULL DEFAULT '',
                expires_at TEXT NULL
            )
        """)
        
        # Миграция: добавляем колонки если таблица уже существует
        try:
            cursor.execute("SELECT source_kind FROM seen LIMIT 1")
        except sqlite3.OperationalError:
            # Колонка source_kind не существует, добавляем
            cursor.execute("ALTER TABLE seen ADD COLUMN source_kind TEXT NOT NULL DEFAULT ''")
        
        try:
            cursor.execute("SELECT expires_at FROM seen LIMIT 1")
        except sqlite3.OperationalError:
            # Колонка expires_at не существует, добавляем
            cursor.execute("ALTER TABLE seen ADD COLUMN expires_at TEXT NULL")
        
        conn.commit()
        conn.close()
    
    def enqueue(self, item: QueueItem) -> bool:
        """
        Добавляет элемент в очередь с дедупликацией.
        
        Args:
            item: Элемент для добавления
        
        Returns:
            bool: True если элемент добавлен, False если был дедуплицирован
        """
        # Определяем source_kind
        source_kind = ''
        if item.item_type == 'discovery_link' or item.source.startswith('discovery:'):
            source_kind = 'discovery'
        
        # Проверяем глобальный seen
        if self.seen_exists(item.external_id, source_kind):
            return False
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        
        try:
            # Пробуем вставить в content_queue
            reasons_json = json.dumps(item.reasons)
            created_at_str = self._dt_to_str(item.created_at)
            
            cursor.execute("""
                INSERT INTO content_queue (
                    topic_id, item_type, source, external_id, title, snippet, url,
                    score, reasons_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.topic_id,
                item.item_type,
                item.source,
                item.external_id,
                item.title,
                item.snippet,
                item.url,
                item.score,
                reasons_json,
                item.status,
                created_at_str
            ))
            
            # Добавляем в seen с TTL
            now = datetime.now(timezone.utc)
            now_str = self._dt_to_str(now)
            
            # Вычисляем expires_at для discovery элементов
            expires_at_str = None
            if source_kind == 'discovery':
                expires_at = now + timedelta(days=self.seen_ttl_days_discovery)
                expires_at_str = self._dt_to_str(expires_at)
            
            cursor.execute("""
                INSERT INTO seen (external_id, first_seen_at, source_kind, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    first_seen_at = excluded.first_seen_at,
                    source_kind = excluded.source_kind,
                    expires_at = excluded.expires_at
            """, (item.external_id, now_str, source_kind, expires_at_str))
            
            conn.commit()
            return True
        
        except sqlite3.IntegrityError:
            # Конфликт UNIQUE(topic_id, external_id)
            conn.rollback()
            return False
        
        finally:
            conn.close()
    
    def count_new(self, topic_id: int) -> int:
        """
        Подсчитывает количество новых элементов для топика.
        
        Args:
            topic_id: ID топика
        
        Returns:
            int: Количество элементов со статусом 'new'
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM content_queue
            WHERE topic_id = ? AND status = 'new'
        """, (topic_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row['count'] if row else 0
    
    def pop_best_new(self, topic_id: int) -> QueueItem | None:
        """
        Извлекает лучший новый элемент из очереди (не меняет статус).
        
        Args:
            topic_id: ID топика
        
        Returns:
            QueueItem | None: Лучший элемент или None если нет новых
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM content_queue
            WHERE topic_id = ? AND status = 'new'
            ORDER BY score DESC, created_at ASC
            LIMIT 1
        """, (topic_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        return self._row_to_item(row)
    
    def mark_posted(self, item_id: int, posted_at: datetime) -> None:
        """
        Помечает элемент как опубликованный.
        
        Args:
            item_id: ID элемента
            posted_at: Время публикации
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        posted_at_str = self._dt_to_str(posted_at)
        cursor.execute("""
            UPDATE content_queue
            SET status = 'posted', posted_at = ?
            WHERE id = ?
        """, (posted_at_str, item_id))
        
        conn.commit()
        conn.close()
    
    def mark_rejected(self, item_id: int) -> None:
        """
        Помечает элемент как отклоненный.
        
        Args:
            item_id: ID элемента
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE content_queue
            SET status = 'rejected'
            WHERE id = ?
        """, (item_id,))
        
        conn.commit()
        conn.close()
    
    def seen_exists(self, external_id: str, source_kind: str = '') -> bool:
        """
        Проверяет, существует ли external_id в глобальном seen.
        
        Args:
            external_id: Внешний идентификатор
            source_kind: Тип источника ('discovery' или '') для проверки TTL
        
        Returns:
            bool: True если external_id уже был виден и не истек TTL
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT first_seen_at, expires_at, source_kind FROM seen WHERE external_id = ?
        """, (external_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return False
        
        # Если это discovery элемент, проверяем TTL
        if source_kind == 'discovery' or row['source_kind'] == 'discovery':
            expires_at_str = row['expires_at']
            if expires_at_str is None:
                return True  # TTL не установлен (старая запись)
            
            expires_at = self._str_to_dt(expires_at_str)
            if expires_at is None:
                return True  # Не удалось распарсить, считаем что не истек
            
            now = datetime.now(timezone.utc)
            if now < expires_at:
                return True  # TTL не истек
            else:
                return False  # TTL истек, разрешаем повторную вставку
        
        # Для non-discovery элементов всегда блокируем
        return True
    
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
    
    def _row_to_item(self, row: sqlite3.Row) -> QueueItem:
        """
        Преобразует строку из БД в объект QueueItem.
        
        Args:
            row: Строка из БД (sqlite3.Row)
        
        Returns:
            QueueItem: Объект QueueItem
        """
        reasons = []
        if row['reasons_json']:
            try:
                reasons = json.loads(row['reasons_json'])
            except (json.JSONDecodeError, TypeError):
                reasons = []
        
        return QueueItem(
            id=row['id'],
            topic_id=row['topic_id'],
            item_type=row['item_type'],
            source=row['source'],
            external_id=row['external_id'],
            title=row['title'],
            snippet=row['snippet'],
            url=row['url'],
            score=row['score'],
            reasons=reasons,
            status=row['status'],
            created_at=self._str_to_dt(row['created_at']) or datetime.now(timezone.utc),
            posted_at=self._str_to_dt(row['posted_at'])
        )