"""
Проверка схемы БД: таблицы, foreign keys, индексы.
"""
import os
import sqlite3
import tempfile

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry


def test_db_schema():
    """Проверяет схему БД после init."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # Инициализируем оба адаптера
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()
        
        content_queue = SQLiteContentQueue(db_path=db_path)
        content_queue.init()
        
        # Проверяем схему
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем таблицы
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('topics', 'content_queue', 'seen')
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        assert 'topics' in tables, "Таблица topics должна существовать"
        assert 'content_queue' in tables, "Таблица content_queue должна существовать"
        assert 'seen' in tables, "Таблица seen должна существовать"
        print(f"[OK] Все таблицы созданы: {tables}")
        
        # Проверяем структуру topics
        cursor.execute("PRAGMA table_info(topics)")
        topics_columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert 'id' in topics_columns
        assert 'chat_id' in topics_columns
        assert 'message_thread_id' in topics_columns
        assert 'name' in topics_columns
        assert 'region_key' in topics_columns
        assert 'mode' in topics_columns
        assert 'enabled' in topics_columns
        assert 'created_at' in topics_columns
        assert 'last_post_at' in topics_columns
        print("[OK] Таблица topics имеет все необходимые колонки")
        
        # Проверяем структуру content_queue
        cursor.execute("PRAGMA table_info(content_queue)")
        queue_columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert 'id' in queue_columns
        assert 'topic_id' in queue_columns
        assert 'item_type' in queue_columns
        assert 'source' in queue_columns
        assert 'external_id' in queue_columns
        assert 'title' in queue_columns
        assert 'snippet' in queue_columns
        assert 'url' in queue_columns
        assert 'score' in queue_columns
        assert 'reasons_json' in queue_columns
        assert 'status' in queue_columns
        assert 'created_at' in queue_columns
        assert 'posted_at' in queue_columns
        print("[OK] Таблица content_queue имеет все необходимые колонки")
        
        # Проверяем структуру seen
        cursor.execute("PRAGMA table_info(seen)")
        seen_columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert 'external_id' in seen_columns
        assert 'first_seen_at' in seen_columns
        assert 'source_kind' in seen_columns
        assert 'expires_at' in seen_columns
        print("[OK] Таблица seen имеет все необходимые колонки (включая source_kind и expires_at)")
        
        # Проверяем foreign keys
        cursor.execute("PRAGMA foreign_key_check")
        fk_errors = cursor.fetchall()
        assert len(fk_errors) == 0, f"Foreign key errors: {fk_errors}"
        
        # Проверяем, что foreign_keys включены (включаем для этого соединения)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1, "Foreign keys должны быть включены"
        print("[OK] Foreign keys могут быть включены")
        
        # Проверяем UNIQUE constraints
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='topics'
        """)
        topics_sql = cursor.fetchone()[0]
        assert 'UNIQUE(chat_id, message_thread_id)' in topics_sql, "UNIQUE constraint на topics должен быть"
        
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='content_queue'
        """)
        queue_sql = cursor.fetchone()[0]
        assert 'UNIQUE(topic_id, external_id)' in queue_sql, "UNIQUE constraint на content_queue должен быть"
        print("[OK] UNIQUE constraints присутствуют")
        
        # Проверяем FOREIGN KEY constraint
        assert 'FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE' in queue_sql, "FOREIGN KEY constraint должен быть"
        print("[OK] FOREIGN KEY constraint присутствует с CASCADE")
        
        conn.close()
        print("\n[SUCCESS] DB schema verification passed!")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_db_schema()
