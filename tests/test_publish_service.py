"""
Тесты для PublishService.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.app.publish_service import PublishService
from src.geotherm_bot.ports.notifier import Notifier
from src.geotherm_bot.ports.queue import QueueItem


class FakeNotifier(Notifier):
    """Фейковый notifier для тестов."""

    def __init__(self):
        self.calls = []  # Список вызовов send_message

    def send(self, chat_id: str, message_thread_id: int, text: str, topic_key: str = None) -> bool:
        """Legacy метод."""
        return True

    def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> None:
        """Записывает вызов в список."""
        self.calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "message_thread_id": message_thread_id,
            }
        )


@pytest.fixture
def temp_db():
    """Создает временную БД для тестов."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def topic_registry(temp_db):
    """Создает и инициализирует TopicRegistry."""
    registry = SQLiteTopicRegistry(db_path=temp_db)
    registry.init()
    return registry


@pytest.fixture
def content_queue(temp_db):
    """Создает и инициализирует ContentQueue."""
    queue = SQLiteContentQueue(db_path=temp_db)
    queue.init()
    return queue


@pytest.fixture
def notifier():
    """Создает FakeNotifier."""
    return FakeNotifier()


@pytest.fixture
def now():
    """Фиксированное время для тестов."""
    return datetime(2026, 2, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def publish_service(topic_registry, content_queue, notifier):
    """Создает PublishService."""
    return PublishService(
        topic_registry=topic_registry,
        content_queue=content_queue,
        notifier=notifier,
        dry_run=False,
    )


def test_publish_picks_oldest_last_post_topic(
    topic_registry, content_queue, notifier, now, publish_service
):
    """Тест: publish выбирает топик с самым старым last_post_at (fairness)."""
    # Создаем 2 топика
    topic_a = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик A")
    topic_b = topic_registry.upsert_topic(chat_id=1, message_thread_id=20, name="Топик B")

    # Устанавливаем last_post_at для A (недавно)
    topic_registry.touch_last_post(topic_a.id, now - timedelta(hours=1))
    # B оставляем с NULL last_post_at

    # Добавляем по 1 элементу в очередь для обоих
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

    # Публикуем
    result = publish_service.publish_next_for_chat(chat_id=1, now=now)

    # Должен выбрать B (NULL oldest - fairness)
    assert result["posted"] is True
    assert result["topic_id"] == topic_b.id
    assert result["thread_id"] == topic_b.message_thread_id

    # Проверяем, что FakeNotifier вызван с thread_id B
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["message_thread_id"] == topic_b.message_thread_id


def test_publish_fairness_prioritizes_null_over_count(
    topic_registry, content_queue, notifier, now, publish_service
):
    """Тест: fairness выбирает NULL last_post_at даже если у другого топика больше элементов."""
    # Создаем 2 топика
    topic_a = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик A")
    topic_b = topic_registry.upsert_topic(chat_id=1, message_thread_id=20, name="Топик B")

    # Устанавливаем last_post_at для A (недавно)
    topic_registry.touch_last_post(topic_a.id, now - timedelta(hours=1))
    # B оставляем с NULL last_post_at

    # Добавляем больше элементов в A (чтобы проверить, что fairness важнее количества)
    for i in range(5):
        item = QueueItem(
            id=None,
            topic_id=topic_a.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id=f"id_a_{i}",
            title=f"Item A {i}",
            snippet="query a",
            url="https://example.com/a",
            score=5,
            reasons=[],
            status="new",
            created_at=now,
        )
        content_queue.enqueue(item)

    # Добавляем только 1 элемент в B
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
    content_queue.enqueue(item_b)

    # Публикуем
    result = publish_service.publish_next_for_chat(chat_id=1, now=now)

    # Должен выбрать B (NULL oldest), несмотря на то что у A больше элементов
    assert result["posted"] is True
    assert result["topic_id"] == topic_b.id
    assert result["thread_id"] == topic_b.message_thread_id


def test_publish_posts_best_item_by_score(
    topic_registry, content_queue, notifier, now, publish_service
):
    """Тест: publish отправляет лучший элемент по score."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик")

    # Добавляем 2 элемента с разными score
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

    # Публикуем
    result = publish_service.publish_next_for_chat(chat_id=1, now=now)

    # Должен быть отправлен элемент с score 10
    assert result["posted"] is True
    assert result["score"] == 10

    # Проверяем текст сообщения
    assert len(notifier.calls) == 1
    assert "Score: 10" in notifier.calls[0]["text"]


def test_publish_marks_posted_and_touches_last_post(
    topic_registry, content_queue, notifier, now, publish_service
):
    """Тест: publish помечает элемент как posted и обновляет last_post_at."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик")

    # Добавляем элемент
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

    # Проверяем начальное состояние
    assert content_queue.count_new(topic.id) == 1
    initial_topic = topic_registry.get_topic(chat_id=1, message_thread_id=10)
    assert initial_topic.last_post_at is None

    # Публикуем
    result = publish_service.publish_next_for_chat(chat_id=1, now=now)

    # Проверяем результаты
    assert result["posted"] is True

    # Элемент должен быть помечен как posted
    assert content_queue.count_new(topic.id) == 0

    # last_post_at должен быть обновлен
    updated_topic = topic_registry.get_topic(chat_id=1, message_thread_id=10)
    assert updated_topic.last_post_at is not None
    assert updated_topic.last_post_at == now


def test_publish_dry_run_does_not_mutate_state(topic_registry, content_queue, notifier, now):
    """Тест: dry_run не меняет состояние."""
    # Создаем PublishService с dry_run=True
    publish_service = PublishService(
        topic_registry=topic_registry,
        content_queue=content_queue,
        notifier=notifier,
        dry_run=True,
    )

    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик")

    # Добавляем элемент
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

    # Публикуем
    result = publish_service.publish_next_for_chat(chat_id=1, now=now)

    # Проверяем результаты
    assert result["posted"] is True
    assert result["reason"] == "dry_run"

    # Элемент всё ещё должен быть в статусе 'new'
    assert content_queue.count_new(topic.id) == 1

    # FakeNotifier не должен быть вызван
    assert len(notifier.calls) == 0

    # last_post_at не должен быть обновлен
    updated_topic = topic_registry.get_topic(chat_id=1, message_thread_id=10)
    assert updated_topic.last_post_at is None


def test_publish_no_topics_or_empty_queue(
    topic_registry, content_queue, notifier, now, publish_service
):
    """Тест: publish возвращает posted=False если нет топиков или элементов."""
    # Тест 1: нет топиков
    result1 = publish_service.publish_next_for_chat(chat_id=1, now=now)
    assert result1["posted"] is False
    assert result1["reason"] == "no_topics_or_empty_queues"

    # Тест 2: есть топик, но нет элементов
    topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Топик")
    result2 = publish_service.publish_next_for_chat(chat_id=1, now=now)
    assert result2["posted"] is False
    assert result2["reason"] == "no_topics_or_empty_queues"


def test_render_includes_query_and_tags(
    topic_registry, content_queue, notifier, now, publish_service
):
    """Тест: render включает query и tags."""
    # Создаем топик с region_key
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")
    topic_registry.set_region_key(topic.id, "kmv")

    # Добавляем элемент с snippet
    item = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id1",
        title="Публикация",
        snippet="Ессентуки №17 химический состав",
        url="https://example.com",
        score=5,
        reasons=["geo", "chem"],
        status="new",
        created_at=now,
    )

    content_queue.enqueue(item)

    # Публикуем
    result = publish_service.publish_next_for_chat(chat_id=1, now=now)

    # Проверяем результаты
    assert result["posted"] is True

    # Проверяем текст сообщения
    assert len(notifier.calls) == 1
    text = notifier.calls[0]["text"]

    assert "Query:" in text
    assert "Ессентуки" in text
    assert "#backfill" in text
    assert "#discovery" in text
    assert "#kmv" in text
    assert "Score: 5" in text
    assert "Reasons:" in text
