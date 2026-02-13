"""
Ручной тест для PublishService (без pytest).
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.app.publish_service import PublishService
from src.geotherm_bot.ports.notifier import Notifier
from src.geotherm_bot.ports.queue import QueueItem


class FakeNotifier(Notifier):
    """Фейковый notifier для тестов."""

    def __init__(self):
        self.calls = []

    def send(self, chat_id: str, message_thread_id: int, text: str, topic_key: str = None) -> bool:
        return True

    def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> None:
        self.calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "message_thread_id": message_thread_id,
            }
        )


def test_all():
    """Запускает все тесты."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()

        content_queue = SQLiteContentQueue(db_path=db_path)
        content_queue.init()

        notifier = FakeNotifier()
        now = datetime(2026, 2, 12, 12, 0, tzinfo=timezone.utc)

        # Тест 1: выбирает топик с самым старым last_post_at
        print("Test 1: publish_picks_oldest_last_post_topic")
        topic_a = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик A")
        topic_b = topic_registry.upsert_topic(chat_id=1, message_thread_id=20, name="Топик B")

        topic_registry.touch_last_post(topic_a.id, now - timedelta(hours=1))

        item_a = QueueItem(
            id=None,
            topic_id=topic_a.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id="id_a",
            title="Item A",
            snippet="query a",
            url="https://example.com/a",
            score=5,
            reasons=[],
            status="new",
            created_at=now,
        )

        item_b = QueueItem(
            id=None,
            topic_id=topic_b.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id="id_b",
            title="Item B",
            snippet="query b",
            url="https://example.com/b",
            score=5,
            reasons=[],
            status="new",
            created_at=now,
        )

        content_queue.enqueue(item_a)
        content_queue.enqueue(item_b)

        publish_service = PublishService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            notifier=notifier,
            dry_run=False,
        )

        result = publish_service.publish_next_for_chat(chat_id=1, now=now)

        assert result["posted"] is True
        assert result["topic_id"] == topic_b.id
        assert len(notifier.calls) == 1
        assert notifier.calls[0]["message_thread_id"] == topic_b.message_thread_id
        print("  [OK] PASS")

        # Тест 2: отправляет лучший элемент по score
        print("Test 2: publish_posts_best_item_by_score")
        notifier.calls = []
        topic = topic_registry.upsert_topic(chat_id=2, message_thread_id=10, name="Топик")

        item_low = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id="id_low",
            title="Item Low",
            snippet="query low",
            url="https://example.com/low",
            score=6,
            reasons=[],
            status="new",
            created_at=now,
        )

        item_high = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id="id_high",
            title="Item High",
            snippet="query high",
            url="https://example.com/high",
            score=10,
            reasons=[],
            status="new",
            created_at=now,
        )

        content_queue.enqueue(item_low)
        content_queue.enqueue(item_high)

        result = publish_service.publish_next_for_chat(chat_id=2, now=now)

        assert result["posted"] is True
        assert result["score"] == 10
        assert "Score: 10" in notifier.calls[0]["text"]
        print("  [OK] PASS")

        # Тест 3: помечает как posted и обновляет last_post_at
        print("Test 3: publish_marks_posted_and_touches_last_post")
        notifier.calls = []
        topic = topic_registry.upsert_topic(chat_id=3, message_thread_id=10, name="Топик")

        item = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id="id1",
            title="Item",
            snippet="query",
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=now,
        )

        content_queue.enqueue(item)
        assert content_queue.count_new(topic.id) == 1

        result = publish_service.publish_next_for_chat(chat_id=3, now=now)

        assert result["posted"] is True
        assert content_queue.count_new(topic.id) == 0

        updated_topic = topic_registry.get_topic(chat_id=3, message_thread_id=10)
        assert updated_topic.last_post_at is not None
        print("  [OK] PASS")

        # Тест 4: dry_run не меняет состояние
        print("Test 4: publish_dry_run_does_not_mutate_state")
        notifier.calls = []
        publish_service_dry = PublishService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            notifier=notifier,
            dry_run=True,
        )

        topic = topic_registry.upsert_topic(chat_id=4, message_thread_id=10, name="Топик")

        item = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id="id_dry",
            title="Item",
            snippet="query",
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=now,
        )

        content_queue.enqueue(item)

        result = publish_service_dry.publish_next_for_chat(chat_id=4, now=now)

        assert result["posted"] is True
        assert result["reason"] == "dry_run"
        assert content_queue.count_new(topic.id) == 1
        assert len(notifier.calls) == 0

        updated_topic = topic_registry.get_topic(chat_id=4, message_thread_id=10)
        assert updated_topic.last_post_at is None
        print("  [OK] PASS")

        # Тест 5: нет топиков или пустая очередь
        print("Test 5: publish_no_topics_or_empty_queue")
        result1 = publish_service.publish_next_for_chat(chat_id=999, now=now)
        assert result1["posted"] is False
        assert result1["reason"] == "no_topics_or_empty_queues"
        print("  [OK] PASS")

        # Тест 6: render включает query и tags
        print("Test 6: render_includes_query_and_tags")
        notifier.calls = []
        topic = topic_registry.upsert_topic(chat_id=5, message_thread_id=10, name="КМВ")
        topic_registry.set_region_key(topic.id, "kmv")

        item = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:cyberleninka",
            external_id="id_render",
            title="Публикация",
            snippet="Ессентуки №17 химический состав",
            url="https://example.com",
            score=5,
            reasons=["geo", "chem"],
            status="new",
            created_at=now,
        )

        content_queue.enqueue(item)

        result = publish_service.publish_next_for_chat(chat_id=5, now=now)

        assert result["posted"] is True
        assert len(notifier.calls) == 1
        text = notifier.calls[0]["text"]

        assert "Query:" in text
        assert "Ессентуки" in text
        assert "#backfill" in text
        assert "#discovery" in text
        assert "#kmv" in text
        assert "Score: 5" in text
        assert "Reasons:" in text
        print("  [OK] PASS")

        print("\n[SUCCESS] Все тесты пройдены!")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_all()
