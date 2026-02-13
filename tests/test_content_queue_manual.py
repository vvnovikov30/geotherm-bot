"""
Ручной тест для SQLiteContentQueue (без pytest).
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.ports.queue import QueueItem


def test_all():
    """Запускает все тесты."""
    # Создаем временную БД
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # Инициализируем оба реестра
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()
        
        content_queue = SQLiteContentQueue(db_path=db_path)
        content_queue.init()
        
        # Создаем тестовый топик
        topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Тестовый топик")
        
        # Тест 1: enqueue добавляет элемент и в seen
        print("Test 1: enqueue_inserts_new_item_and_seen")
        item = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="sha1_hash_123",
            title="Тестовая публикация",
            snippet="query string",
            url="https://example.com",
            score=5,
            reasons=["test"],
            status="new",
            created_at=datetime.now(timezone.utc)
        )
        result = content_queue.enqueue(item)
        assert result is True
        assert content_queue.count_new(topic.id) == 1
        assert content_queue.seen_exists("sha1_hash_123") is True
        print("  [OK] PASS")
        
        # Тест 2: дедуп по глобальному seen
        print("Test 2: enqueue_dedup_by_seen_global")
        topic2 = topic_registry.upsert_topic(chat_id=1, message_thread_id=20, name="Топик 2")
        item2 = QueueItem(
            id=None,
            topic_id=topic2.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="sha1_hash_123",  # Тот же external_id
            title="Публикация 2",
            snippet=None,
            url="https://example.com/2",
            score=6,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc)
        )
        result2 = content_queue.enqueue(item2)
        assert result2 is False
        assert content_queue.count_new(topic2.id) == 0
        print("  [OK] PASS")
        
        # Тест 3: дедуп по unique(topic_id, external_id)
        print("Test 3: enqueue_dedup_by_unique_topic_external")
        item3 = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="unique_id_123",
            title="Публикация",
            snippet=None,
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc)
        )
        result3a = content_queue.enqueue(item3)
        assert result3a is True
        result3b = content_queue.enqueue(item3)
        assert result3b is False
        print("  [OK] PASS")
        
        # Тест 4: сортировка по score и created_at
        print("Test 4: pop_best_new_orders_by_score_then_age")
        now = datetime.now()
        item4a = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id4a",
            title="Низкий score",
            snippet=None,
            url="https://example.com/4a",
            score=3,
            reasons=[],
            status="new",
            created_at=now - timedelta(hours=2)
        )
        item4b = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id4b",
            title="Высокий score, новый",
            snippet=None,
            url="https://example.com/4b",
            score=8,
            reasons=[],
            status="new",
            created_at=now - timedelta(hours=1)
        )
        item4c = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id4c",
            title="Высокий score, старый",
            snippet=None,
            url="https://example.com/4c",
            score=8,
            reasons=[],
            status="new",
            created_at=now - timedelta(hours=3)
        )
        content_queue.enqueue(item4a)
        content_queue.enqueue(item4b)
        content_queue.enqueue(item4c)
        best = content_queue.pop_best_new(topic.id)
        assert best is not None
        assert best.external_id == "id4c"  # score=8, самый старый
        print("  [OK] PASS")
        
        # Тест 5: mark_posted
        print("Test 5: mark_posted_changes_status_and_posted_at")
        item5 = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id5",
            title="Публикация",
            snippet=None,
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc)
        )
        content_queue.enqueue(item5)
        popped = content_queue.pop_best_new(topic.id)
        assert popped is not None
        content_queue.mark_posted(popped.id, datetime.now())
        popped_again = content_queue.pop_best_new(topic.id)
        assert popped_again is None or popped_again.id != popped.id
        print("  [OK] PASS")
        
        # Тест 6: mark_rejected
        print("Test 6: mark_rejected_excludes_from_new")
        # Сначала очистим очередь от предыдущих элементов
        # Получаем все элементы и помечаем их как posted
        while True:
            popped = content_queue.pop_best_new(topic.id)
            if popped is None:
                break
            content_queue.mark_posted(popped.id, datetime.now(timezone.utc))
        
        item6 = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id6",
            title="Публикация",
            snippet=None,
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc)
        )
        content_queue.enqueue(item6)
        count_before = content_queue.count_new(topic.id)
        assert count_before == 1
        
        popped6 = content_queue.pop_best_new(topic.id)
        assert popped6 is not None
        content_queue.mark_rejected(popped6.id)
        
        count_after = content_queue.count_new(topic.id)
        assert count_after == 0
        print("  [OK] PASS")
        
        # Тест 7: каскадное удаление
        print("Test 7: foreign_key_topic_delete_cascades_queue")
        topic3 = topic_registry.upsert_topic(chat_id=2, message_thread_id=10, name="Топик 3")
        item7 = QueueItem(
            id=None,
            topic_id=topic3.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id7",
            title="Публикация",
            snippet=None,
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc)
        )
        content_queue.enqueue(item7)
        assert content_queue.count_new(topic3.id) == 1
        
        # Удаляем топик
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM topics WHERE id = ?", (topic3.id,))
        conn.commit()
        conn.close()
        
        assert content_queue.count_new(topic3.id) == 0
        print("  [OK] PASS")
        
        print("\n[SUCCESS] Все тесты пройдены!")
        
    finally:
        # Очистка
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_all()
