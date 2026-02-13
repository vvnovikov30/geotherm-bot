"""
Ручной тест для TTL функциональности (без pytest).
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.ports.queue import QueueItem


def test_ttl():
    """Тест TTL функциональности."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Инициализируем
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()

        # Создаем очередь с TTL = 1 день
        content_queue = SQLiteContentQueue(db_path=db_path, seen_ttl_days_discovery=1)
        content_queue.init()

        # Создаем топик
        topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="TTL Test")

        # Discovery элемент
        item = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="ttl_test_id",
            title="TTL Test",
            snippet=None,
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc),
        )

        # Тест 1: Первая вставка
        print("Test 1: Первая вставка discovery элемента")
        result1 = content_queue.enqueue(item)
        assert result1 is True
        assert content_queue.seen_exists("ttl_test_id", "discovery") is True
        print("  [OK] PASS")

        # Тест 2: Повторная вставка сразу блокируется
        print("Test 2: Повторная вставка блокируется")
        result2 = content_queue.enqueue(item)
        assert result2 is False
        print("  [OK] PASS")

        # Тест 3: Обновляем expires_at на прошлое и удаляем из content_queue
        print("Test 3: TTL истек - разрешаем повторную вставку")
        # Сначала удаляем элемент из content_queue (симулируем, что он был обработан)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM content_queue WHERE external_id = ?", ("ttl_test_id",))

        # Обновляем expires_at на прошлое
        past_time = datetime.now(timezone.utc) - timedelta(days=2)
        past_time_str = content_queue._dt_to_str(past_time)
        cursor.execute(
            "UPDATE seen SET expires_at = ? WHERE external_id = ?", (past_time_str, "ttl_test_id")
        )
        conn.commit()
        conn.close()

        # Теперь seen_exists должен вернуть False (TTL истек)
        assert content_queue.seen_exists("ttl_test_id", "discovery") is False

        # Вставка должна быть разрешена (элемент удален из content_queue)
        result3 = content_queue.enqueue(item)
        assert result3 is True
        print("  [OK] PASS")

        # Тест 4: Non-discovery блокируется навсегда
        print("Test 4: Non-discovery блокируется навсегда")
        item2 = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="other",
            source="europepmc",
            external_id="non_discovery_id",
            title="Non-discovery",
            snippet=None,
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=datetime.now(timezone.utc),
        )

        result4a = content_queue.enqueue(item2)
        assert result4a is True

        result4b = content_queue.enqueue(item2)
        assert result4b is False

        # Проверяем, что блокируется даже с пустым source_kind
        assert content_queue.seen_exists("non_discovery_id", "") is True
        print("  [OK] PASS")

        print("\n[SUCCESS] Все TTL тесты пройдены!")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_ttl()
