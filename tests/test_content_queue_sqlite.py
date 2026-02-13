"""
Тесты для SQLiteContentQueue.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.ports.queue import QueueItem


@pytest.fixture
def temp_db():
    """Создает временную БД для тестов."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    # Очистка после теста
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
def topic(topic_registry):
    """Создает тестовый топик."""
    return topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="Тестовый топик")


def test_enqueue_inserts_new_item_and_seen(topic, content_queue):
    """Тест: enqueue добавляет новый элемент и в seen."""
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
    
    # Проверяем count_new
    count = content_queue.count_new(topic.id)
    assert count == 1
    
    # Проверяем seen_exists
    assert content_queue.seen_exists("sha1_hash_123") is True


def test_enqueue_dedup_by_seen_global(topic, content_queue, topic_registry):
    """Тест: enqueue дедуплицирует по глобальному seen."""
    # Создаем второй топик
    topic2 = topic_registry.upsert_topic(chat_id=1, message_thread_id=20, name="Топик 2")
    
    item1 = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="same_external_id",
        title="Публикация 1",
        snippet=None,
        url="https://example.com/1",
        score=5,
        reasons=[],
        status="new",
        created_at=datetime.now(timezone.utc)
    )
    
    item2 = QueueItem(
        id=None,
        topic_id=topic2.id,  # Другой топик
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="same_external_id",  # Тот же external_id
        title="Публикация 2",
        snippet=None,
        url="https://example.com/2",
        score=6,
        reasons=[],
        status="new",
        created_at=datetime.now(timezone.utc)
    )
    
    # Первый должен добавиться
    result1 = content_queue.enqueue(item1)
    assert result1 is True
    
    # Второй должен быть заблокирован глобальным seen
    result2 = content_queue.enqueue(item2)
    assert result2 is False
    
    # Проверяем, что только один элемент в очереди
    count1 = content_queue.count_new(topic.id)
    count2 = content_queue.count_new(topic2.id)
    assert count1 == 1
    assert count2 == 0


def test_enqueue_dedup_by_unique_topic_external(topic, content_queue):
    """Тест: enqueue дедуплицирует по unique(topic_id, external_id)."""
    item = QueueItem(
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
    
    # Первый раз должен добавиться
    result1 = content_queue.enqueue(item)
    assert result1 is True
    
    # Второй раз с тем же external_id должен быть заблокирован
    result2 = content_queue.enqueue(item)
    assert result2 is False
    
    # Должен быть только один элемент
    count = content_queue.count_new(topic.id)
    assert count == 1


def test_pop_best_new_orders_by_score_then_age(topic, content_queue):
    """Тест: pop_best_new сортирует по score DESC, затем по created_at ASC."""
    now = datetime.now(timezone.utc)
    
    # Создаем элементы с разными score и временем
    item1 = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id1",
        title="Низкий score, старый",
        snippet=None,
        url="https://example.com/1",
        score=3,
        reasons=[],
        status="new",
        created_at=now - timedelta(hours=2)
    )
    
    item2 = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id2",
        title="Высокий score, новый",
        snippet=None,
        url="https://example.com/2",
        score=8,
        reasons=[],
        status="new",
        created_at=now - timedelta(hours=1)
    )
    
    item3 = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id3",
        title="Высокий score, старый",
        snippet=None,
        url="https://example.com/3",
        score=8,  # Тот же score что у item2
        reasons=[],
        status="new",
        created_at=now - timedelta(hours=3)  # Старше item2
    )
    
    # Добавляем в порядке, отличном от приоритета
    content_queue.enqueue(item1)
    content_queue.enqueue(item2)
    content_queue.enqueue(item3)
    
    # pop_best_new должен вернуть item3 (score=8, самый старый среди score=8)
    best = content_queue.pop_best_new(topic.id)
    assert best is not None
    assert best.external_id == "id3"
    assert best.score == 8
    
    # Помечаем как posted и проверяем следующий
    content_queue.mark_posted(best.id, datetime.now(timezone.utc))
    
    best2 = content_queue.pop_best_new(topic.id)
    assert best2 is not None
    assert best2.external_id == "id2"
    assert best2.score == 8


def test_mark_posted_changes_status_and_posted_at(topic, content_queue):
    """Тест: mark_posted меняет статус и устанавливает posted_at."""
    item = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id_posted",
        title="Публикация",
        snippet=None,
        url="https://example.com",
        score=5,
        reasons=[],
        status="new",
        created_at=datetime.now(timezone.utc)
    )
    
    content_queue.enqueue(item)
    
    # Получаем элемент
    popped = content_queue.pop_best_new(topic.id)
    assert popped is not None
    assert popped.status == "new"
    assert popped.posted_at is None
    
    # Помечаем как posted
    posted_at = datetime.now(timezone.utc)
    content_queue.mark_posted(popped.id, posted_at)
    
    # Повторный pop_best_new не должен вернуть posted элемент
    popped_again = content_queue.pop_best_new(topic.id)
    assert popped_again is None
    
    # Проверяем через прямой запрос (можно добавить метод get_item если нужно)
    # Но для теста проверим count_new
    count = content_queue.count_new(topic.id)
    assert count == 0


def test_mark_rejected_excludes_from_new(topic, content_queue):
    """Тест: mark_rejected исключает элемент из новых."""
    item = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id_rejected",
        title="Публикация",
        snippet=None,
        url="https://example.com",
        score=5,
        reasons=[],
        status="new",
        created_at=datetime.now(timezone.utc)
    )
    
    content_queue.enqueue(item)
    
    # Проверяем, что элемент есть
    count_before = content_queue.count_new(topic.id)
    assert count_before == 1
    
    # Получаем элемент
    popped = content_queue.pop_best_new(topic.id)
    assert popped is not None
    
    # Помечаем как rejected
    content_queue.mark_rejected(popped.id)
    
    # Проверяем, что элемент больше не в новых
    count_after = content_queue.count_new(topic.id)
    assert count_after == 0
    
    # pop_best_new не должен вернуть rejected элемент
    popped_again = content_queue.pop_best_new(topic.id)
    assert popped_again is None


def test_foreign_key_topic_delete_cascades_queue(topic, content_queue, topic_registry):
    """Тест: удаление топика каскадно удаляет элементы очереди."""
    # Добавляем элемент в очередь
    item = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="discovery_link",
        source="discovery:cyberleninka",
        external_id="id_cascade",
        title="Публикация",
        snippet=None,
        url="https://example.com",
        score=5,
        reasons=[],
        status="new",
        created_at=datetime.now(timezone.utc)
    )
    
    content_queue.enqueue(item)
    
    # Проверяем, что элемент есть
    count_before = content_queue.count_new(topic.id)
    assert count_before == 1
    
    # Удаляем топик напрямую через SQL (так как нет метода delete в TopicRegistry)
    import sqlite3
    conn = sqlite3.connect(content_queue.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM topics WHERE id = ?", (topic.id,))
    conn.commit()
    conn.close()
    
    # Проверяем, что элемент удален каскадно
    count_after = content_queue.count_new(topic.id)
    assert count_after == 0
    
    # pop_best_new не должен вернуть элемент
    popped = content_queue.pop_best_new(topic.id)
    assert popped is None


def test_seen_ttl_allows_rediscovery_after_expiry(topic_registry, temp_db):
    """Тест: TTL для discovery элементов позволяет повторную вставку после истечения."""
    # Создаем очередь с TTL = 1 день
    content_queue = SQLiteContentQueue(db_path=temp_db, seen_ttl_days_discovery=1)
    content_queue.init()
    
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="TTL Test Topic")
    
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
        created_at=datetime.now(timezone.utc)
    )
    
    # Первая вставка должна быть успешной
    result1 = content_queue.enqueue(item)
    assert result1 is True
    
    # Вторая вставка сразу должна быть заблокирована
    result2 = content_queue.enqueue(item)
    assert result2 is False
    
    # Вручную обновляем expires_at на прошлое и удаляем из content_queue
    import sqlite3
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    # Удаляем элемент из content_queue (симулируем, что он был обработан)
    cursor.execute("DELETE FROM content_queue WHERE external_id = ?", ("ttl_test_id",))
    
    # Обновляем expires_at на прошлое
    past_time = datetime.now(timezone.utc) - timedelta(days=2)
    past_time_str = content_queue._dt_to_str(past_time)
    cursor.execute("""
        UPDATE seen SET expires_at = ? WHERE external_id = ?
    """, (past_time_str, "ttl_test_id"))
    conn.commit()
    conn.close()
    
    # Теперь seen_exists должен вернуть False (TTL истек)
    assert content_queue.seen_exists("ttl_test_id", "discovery") is False
    
    # Теперь вставка должна быть разрешена (TTL истек и элемент удален из content_queue)
    result3 = content_queue.enqueue(item)
    assert result3 is True


def test_seen_non_discovery_blocks_forever(topic, content_queue):
    """Тест: non-discovery элементы блокируются навсегда."""
    item = QueueItem(
        id=None,
        topic_id=topic.id,
        item_type="other",  # Не discovery
        source="europepmc",  # Не discovery
        external_id="non_discovery_id",
        title="Non-discovery item",
        snippet=None,
        url="https://example.com",
        score=5,
        reasons=[],
        status="new",
        created_at=datetime.now(timezone.utc)
    )
    
    # Первая вставка должна быть успешной
    result1 = content_queue.enqueue(item)
    assert result1 is True
    
    # Вторая вставка должна быть заблокирована навсегда
    result2 = content_queue.enqueue(item)
    assert result2 is False
    
    # Даже если expires_at NULL, non-discovery должен блокироваться
    assert content_queue.seen_exists("non_discovery_id", "") is True
