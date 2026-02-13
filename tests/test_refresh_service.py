"""
Тесты для RefreshService.
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.app.query_builder import QueryBuilder
from src.geotherm_bot.app.refresh_service import RefreshService
from src.geotherm_bot.app.region import RegionResolver
from src.geotherm_bot.domain.models import FilterDecision, Publication, QuerySpec, ScoreResult
from src.geotherm_bot.ports.publications_api import PublicationsAPI


class FakeProvider(PublicationsAPI):
    """Фейковый провайдер для тестов."""

    def __init__(self, publications_by_query: dict = None):
        """
        Инициализирует фейковый провайдер.

        Args:
            publications_by_query: Словарь {query_spec.query: [Publication, ...]}
        """
        self.publications_by_query = publications_by_query or {}

    def fetch(self, query_spec: QuerySpec) -> list[Publication]:
        """Возвращает публикации для query_spec."""
        return self.publications_by_query.get(query_spec.query, [])

    def fetch_publications(self) -> list[Publication]:
        """Legacy метод."""
        return []


def fake_filtering(pub: Publication) -> FilterDecision:
    """Фейковая функция фильтрации."""
    # Простая проверка: если в abstract есть "сточные" -> reject
    abstract = (pub.abstract or "").lower()
    if "сточные" in abstract:
        return FilterDecision(passed=False, reasons=["contains сточные"])
    return FilterDecision(passed=True, reasons=[])


def fake_scoring(pub: Publication) -> ScoreResult:
    """Фейковая функция скоринга."""
    # По умолчанию score=6, но если в title есть "low_score", то score=2
    title = (pub.title or "").lower()
    if "low_score" in title:
        return ScoreResult(score=2, reasons=["low_score test"], is_high_priority=False)
    return ScoreResult(score=6, reasons=["geo", "chem"], is_high_priority=False)


@pytest.fixture
def temp_db():
    """Создает временную БД для тестов."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
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
def refresh_service(topic_registry, content_queue):
    """Создает RefreshService с фейковыми зависимостями."""
    region_resolver = RegionResolver()
    query_builder = QueryBuilder()
    provider = FakeProvider()

    return RefreshService(
        topic_registry=topic_registry,
        content_queue=content_queue,
        region_resolver=region_resolver,
        query_builder=query_builder,
        provider=provider,
        filtering=fake_filtering,
        scoring=fake_scoring,
    )


def test_refresh_enqueues_items_for_topics(refresh_service, topic_registry, content_queue):
    """Тест: refresh добавляет элементы в очередь для топиков."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")
    assert topic.region_key == ""  # Пустой изначально

    # Настраиваем провайдер для возврата публикаций
    pub1 = Publication(
        id="pub1",
        source="discovery:cyberleninka",
        title="Тестовая публикация 1",
        abstract="Химический состав минеральных вод",
        url="https://example.com/pub1",
        raw={"site": "cyberleninka", "query": "Ессентуки chemistry"},
    )

    pub2 = Publication(
        id="pub2",
        source="discovery:cyberleninka",
        title="Тестовая публикация 2",
        abstract="Источники минеральных вод",
        url="https://example.com/pub2",
        raw={"site": "cyberleninka", "query": "Ессентуки wells"},
    )

    # Получаем queries для KMV
    query_builder = QueryBuilder()
    queries = query_builder.build_backfill_queries("kmv", "КМВ")

    # Настраиваем провайдер
    publications_by_query = {}
    for q in queries[:2]:  # Только первые 2 запроса
        publications_by_query[q.query] = [pub1, pub2]

    refresh_service.provider = FakeProvider(publications_by_query)

    # Выполняем refresh
    now = datetime.now(timezone.utc)
    stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)

    # Проверяем результаты
    assert stats["topics_seen"] == 1
    assert stats["queries_built"] > 0
    assert stats["pubs_fetched"] > 0
    assert stats["items_enqueued"] > 0

    # Проверяем, что region_key был установлен
    updated_topic = topic_registry.get_topic(chat_id=1, message_thread_id=10)
    assert updated_topic.region_key == "kmv"

    # Проверяем, что элементы добавлены в очередь
    count = content_queue.count_new(topic.id)
    assert count > 0


def test_refresh_respects_topic_queue_cap(refresh_service, topic_registry, content_queue):
    """Тест: refresh не добавляет элементы если очередь полна (80)."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")

    # Набиваем очередь до 80 элементов
    from src.geotherm_bot.ports.queue import QueueItem

    now = datetime.now(timezone.utc)

    for i in range(80):
        item = QueueItem(
            id=None,
            topic_id=topic.id,
            item_type="discovery_link",
            source="discovery:test",
            external_id=f"test_id_{i}",
            title=f"Test {i}",
            snippet="",
            url="https://example.com",
            score=5,
            reasons=[],
            status="new",
            created_at=now,
        )
        content_queue.enqueue(item)

    # Проверяем, что очередь полна
    assert content_queue.count_new(topic.id) == 80

    # Настраиваем провайдер
    pub = Publication(
        id="pub1",
        source="discovery:cyberleninka",
        title="Тестовая публикация",
        abstract="Химический состав",
        url="https://example.com/pub1",
        raw={"site": "cyberleninka", "query": "test"},
    )

    query_builder = QueryBuilder()
    queries = query_builder.build_backfill_queries("kmv", "КМВ")
    publications_by_query = {queries[0].query: [pub]}
    refresh_service.provider = FakeProvider(publications_by_query)

    # Выполняем refresh
    stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)

    # Проверяем, что ничего не добавлено
    assert stats["topics_skipped_full"] == 1
    assert stats["items_enqueued"] == 0
    assert content_queue.count_new(topic.id) == 80


def test_refresh_respects_per_topic_limit_30(refresh_service, topic_registry, content_queue):
    """Тест: refresh добавляет не больше 30 элементов на топик."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")

    # Настраиваем провайдер для возврата 100 публикаций
    pubs = []
    for i in range(100):
        pub = Publication(
            id=f"pub{i}",
            source="discovery:cyberleninka",
            title=f"Тестовая публикация {i}",
            abstract="Химический состав",
            url=f"https://example.com/pub{i}",
            raw={"site": "cyberleninka", "query": f"test query {i}"},
        )
        pubs.append(pub)

    query_builder = QueryBuilder()
    queries = query_builder.build_backfill_queries("kmv", "КМВ")
    publications_by_query = {queries[0].query: pubs}
    refresh_service.provider = FakeProvider(publications_by_query)

    # Выполняем refresh
    now = datetime.now(timezone.utc)
    stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)

    # Проверяем, что добавлено не больше 30
    assert stats["items_enqueued"] <= 30
    assert content_queue.count_new(topic.id) <= 30


def test_refresh_threshold_filters_low_score(refresh_service, topic_registry, content_queue):
    """Тест: refresh фильтрует публикации с низким score (< 5)."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")

    # Создаем публикации: одна с низким score, одна с нормальным
    pub_low = Publication(
        id="pub_low",
        source="discovery:cyberleninka",
        title="low_score публикация",
        abstract="Химический состав",
        url="https://example.com/pub_low",
        raw={"site": "cyberleninka", "query": "test"},
    )

    pub_normal = Publication(
        id="pub_normal",
        source="discovery:cyberleninka",
        title="Нормальная публикация",
        abstract="Химический состав",
        url="https://example.com/pub_normal",
        raw={"site": "cyberleninka", "query": "test2"},
    )

    query_builder = QueryBuilder()
    queries = query_builder.build_backfill_queries("kmv", "КМВ")
    publications_by_query = {queries[0].query: [pub_low, pub_normal]}
    refresh_service.provider = FakeProvider(publications_by_query)

    # Выполняем refresh
    now = datetime.now(timezone.utc)
    stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)

    # Проверяем, что добавлена только одна публикация (с нормальным score)
    assert stats["items_enqueued"] == 1
    assert content_queue.count_new(topic.id) == 1


def test_refresh_dedup_works(refresh_service, topic_registry, content_queue):
    """Тест: refresh дедуплицирует одинаковые публикации."""
    # Создаем топик
    topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")

    # Создаем две одинаковые публикации (одинаковый site и query)
    pub1 = Publication(
        id="pub1",
        source="discovery:cyberleninka",
        title="Публикация 1",
        abstract="Химический состав",
        url="https://example.com/pub1",
        raw={"site": "cyberleninka", "query": "Ессентуки chemistry"},
    )

    pub2 = Publication(
        id="pub2",
        source="discovery:cyberleninka",
        title="Публикация 2",
        abstract="Другой текст",
        url="https://example.com/pub2",
        raw={"site": "cyberleninka", "query": "Ессентуки chemistry"},  # Тот же query
    )

    query_builder = QueryBuilder()
    queries = query_builder.build_backfill_queries("kmv", "КМВ")
    publications_by_query = {queries[0].query: [pub1, pub2]}
    refresh_service.provider = FakeProvider(publications_by_query)

    # Выполняем refresh
    now = datetime.now(timezone.utc)
    stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)

    # Проверяем, что добавлена только одна публикация (вторая дедуплицирована)
    assert stats["items_enqueued"] == 1
    assert stats["items_deduped"] == 1
    assert content_queue.count_new(topic.id) == 1
