"""
Ручной тест для SQLiteTopicRegistry (без pytest).
"""
import os
import tempfile
from datetime import datetime

from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry


def test_all():
    """Запускает все тесты."""
    # Создаем временную БД
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        registry = SQLiteTopicRegistry(db_path=db_path)
        registry.init()
        
        # Тест 1: создание топика
        print("Test 1: insert_topic_creates_row")
        topic = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
        assert topic is not None
        assert topic.name == "Турция"
        assert topic.enabled is True
        assert topic.mode == "backfill_ru"
        retrieved = registry.get_topic(chat_id=1, message_thread_id=10)
        assert retrieved.name == "Турция"
        print("  [OK] PASS")
        
        # Тест 2: дедупликация
        print("Test 2: upsert_dedup_unique")
        topic2 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
        assert topic.id == topic2.id
        topics = registry.list_topics(chat_id=1)
        assert len(topics) == 1
        print("  [OK] PASS")
        
        # Тест 3: обновление name
        print("Test 3: upsert_updates_name_when_provided")
        topic3 = registry.upsert_topic(chat_id=1, message_thread_id=10, name=None)
        assert topic3.name == "unknown" or topic3.name == "Турция"  # Может быть старое имя
        topic4 = registry.upsert_topic(chat_id=1, message_thread_id=20, name=None)
        assert topic4.name == "unknown"
        topic5 = registry.upsert_topic(chat_id=1, message_thread_id=20, name="Закавказье")
        assert topic5.name == "Закавказье"
        print("  [OK] PASS")
        
        # Тест 4: не перезаписывать name
        print("Test 4: upsert_does_not_overwrite_name_with_none_or_empty")
        topic6 = registry.upsert_topic(chat_id=1, message_thread_id=30, name="Алтай")
        assert topic6.name == "Алтай"
        topic7 = registry.upsert_topic(chat_id=1, message_thread_id=30, name=None)
        assert topic7.name == "Алтай"
        topic8 = registry.upsert_topic(chat_id=1, message_thread_id=30, name="")
        assert topic8.name == "Алтай"
        print("  [OK] PASS")
        
        # Тест 5: touch_last_post
        print("Test 5: touch_last_post_sets_timestamp")
        fixed_dt = datetime(2024, 1, 15, 12, 30, 45)
        registry.touch_last_post(topic6.id, fixed_dt)
        retrieved = registry.get_topic(chat_id=1, message_thread_id=30)
        assert retrieved.last_post_at is not None
        assert retrieved.last_post_at.year == fixed_dt.year
        print("  [OK] PASS")
        
        # Тест 6: set_enabled фильтрация
        print("Test 6: set_enabled_filters_list")
        topic9 = registry.upsert_topic(chat_id=2, message_thread_id=10, name="Турция")
        topic10 = registry.upsert_topic(chat_id=2, message_thread_id=20, name="Алтай")
        enabled = registry.list_topics(chat_id=2, enabled_only=True)
        assert len(enabled) == 2
        registry.set_enabled(topic10.id, False)
        enabled = registry.list_topics(chat_id=2, enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].id == topic9.id
        all_topics = registry.list_topics(chat_id=2, enabled_only=False)
        assert len(all_topics) == 2
        print("  [OK] PASS")
        
        print("\n[SUCCESS] Все тесты пройдены!")
        
    finally:
        # Очистка
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_all()
