"""
Тесты для SQLiteTopicRegistry.
"""
import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry


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
def registry(temp_db):
    """Создает и инициализирует TopicRegistry."""
    registry = SQLiteTopicRegistry(db_path=temp_db)
    registry.init()
    return registry


def test_insert_topic_creates_row(registry):
    """Тест: создание нового топика."""
    topic = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
    
    assert topic is not None
    assert topic.id > 0
    assert topic.chat_id == 1
    assert topic.message_thread_id == 10
    assert topic.name == "Турция"
    assert topic.enabled is True
    assert topic.mode == "backfill_ru"
    assert topic.region_key == ""
    assert topic.created_at is not None
    assert topic.last_post_at is None
    
    # Проверяем через get_topic
    retrieved = registry.get_topic(chat_id=1, message_thread_id=10)
    assert retrieved is not None
    assert retrieved.name == "Турция"
    assert retrieved.enabled is True
    assert retrieved.mode == "backfill_ru"


def test_upsert_dedup_unique(registry):
    """Тест: upsert не создает дубликаты."""
    topic1 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
    topic2 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
    
    # Должны быть одинаковые ID
    assert topic1.id == topic2.id
    
    # Должен быть только один топик в списке
    topics = registry.list_topics(chat_id=1)
    assert len(topics) == 1
    assert topics[0].id == topic1.id


def test_upsert_updates_name_when_provided(registry):
    """Тест: upsert обновляет name когда передан непустой name."""
    # Создаем с None -> должно быть "unknown"
    topic1 = registry.upsert_topic(chat_id=1, message_thread_id=10, name=None)
    assert topic1.name == "unknown"
    
    # Обновляем с реальным именем
    topic2 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Закавказье")
    assert topic2.id == topic1.id  # Тот же топик
    assert topic2.name == "Закавказье"
    
    # Проверяем через get_topic
    retrieved = registry.get_topic(chat_id=1, message_thread_id=10)
    assert retrieved.name == "Закавказье"


def test_upsert_does_not_overwrite_name_with_none_or_empty(registry):
    """Тест: upsert не перезаписывает name на None или пустую строку."""
    # Создаем с именем
    topic1 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Алтай")
    assert topic1.name == "Алтай"
    
    # Пытаемся обновить с None
    topic2 = registry.upsert_topic(chat_id=1, message_thread_id=10, name=None)
    assert topic2.id == topic1.id
    assert topic2.name == "Алтай"  # Имя не изменилось
    
    # Пытаемся обновить с пустой строкой
    topic3 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="")
    assert topic3.id == topic1.id
    assert topic3.name == "Алтай"  # Имя не изменилось
    
    # Проверяем через get_topic
    retrieved = registry.get_topic(chat_id=1, message_thread_id=10)
    assert retrieved.name == "Алтай"


def test_touch_last_post_sets_timestamp(registry):
    """Тест: touch_last_post устанавливает timestamp."""
    topic = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
    assert topic.last_post_at is None
    
    # Устанавливаем фиксированное время (UTC aware)
    fixed_dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
    registry.touch_last_post(topic.id, fixed_dt)
    
    # Проверяем через get_topic
    retrieved = registry.get_topic(chat_id=1, message_thread_id=10)
    assert retrieved.last_post_at is not None
    
    # Проверяем, что время совпадает (с учетом сериализации)
    # ISO формат может немного отличаться, поэтому сравниваем до секунд
    assert retrieved.last_post_at.year == fixed_dt.year
    assert retrieved.last_post_at.month == fixed_dt.month
    assert retrieved.last_post_at.day == fixed_dt.day
    assert retrieved.last_post_at.hour == fixed_dt.hour
    assert retrieved.last_post_at.minute == fixed_dt.minute
    assert retrieved.last_post_at.second == fixed_dt.second


def test_set_enabled_filters_list(registry):
    """Тест: set_enabled фильтрует список топиков."""
    # Создаем два топика
    topic1 = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
    topic2 = registry.upsert_topic(chat_id=1, message_thread_id=20, name="Алтай")
    
    # Оба должны быть в списке
    all_topics = registry.list_topics(chat_id=1, enabled_only=False)
    assert len(all_topics) == 2
    
    enabled_topics = registry.list_topics(chat_id=1, enabled_only=True)
    assert len(enabled_topics) == 2
    
    # Отключаем topic2
    registry.set_enabled(topic2.id, False)
    
    # Теперь только topic1 должен быть в enabled_only
    enabled_topics = registry.list_topics(chat_id=1, enabled_only=True)
    assert len(enabled_topics) == 1
    assert enabled_topics[0].id == topic1.id
    assert enabled_topics[0].name == "Турция"
    
    # Но оба должны быть в полном списке
    all_topics = registry.list_topics(chat_id=1, enabled_only=False)
    assert len(all_topics) == 2
    
    # Проверяем, что topic2 действительно disabled
    retrieved = registry.get_topic(chat_id=1, message_thread_id=20)
    assert retrieved.enabled is False


def test_set_region_key(registry):
    """Тест: set_region_key обновляет region_key."""
    topic = registry.upsert_topic(chat_id=1, message_thread_id=10, name="Турция")
    assert topic.region_key == ""
    
    registry.set_region_key(topic.id, "turkey")
    
    retrieved = registry.get_topic(chat_id=1, message_thread_id=10)
    assert retrieved.region_key == "turkey"


def test_get_topic_returns_none_when_not_found(registry):
    """Тест: get_topic возвращает None для несуществующего топика."""
    result = registry.get_topic(chat_id=999, message_thread_id=999)
    assert result is None


def test_list_topics_empty_when_no_topics(registry):
    """Тест: list_topics возвращает пустой список когда нет топиков."""
    topics = registry.list_topics(chat_id=1)
    assert topics == []
