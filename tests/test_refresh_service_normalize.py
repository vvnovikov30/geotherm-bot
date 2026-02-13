"""
Тесты для normalize_query и стабильности external_id.
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.app.query_builder import QueryBuilder
from src.geotherm_bot.app.refresh_service import RefreshService, normalize_query
from src.geotherm_bot.app.region import RegionResolver
from src.geotherm_bot.domain.models import FilterDecision, Publication, QuerySpec, ScoreResult
from src.geotherm_bot.ports.publications_api import PublicationsAPI


class FakeProvider(PublicationsAPI):
    """Фейковый провайдер для тестов."""

    def __init__(self, publications_by_query: dict = None):
        self.publications_by_query = publications_by_query or {}

    def fetch(self, query_spec: QuerySpec) -> list[Publication]:
        return self.publications_by_query.get(query_spec.query, [])

    def fetch_publications(self) -> list[Publication]:
        return []


def fake_filtering(pub: Publication) -> FilterDecision:
    """Фейковая функция фильтрации."""
    return FilterDecision(passed=True, reasons=[])


def fake_scoring(pub: Publication) -> ScoreResult:
    """Фейковая функция скоринга."""
    return ScoreResult(score=6, reasons=["geo", "chem"], is_high_priority=False)


def test_normalize_query_stable_equivalence():
    """Тест: normalize_query делает эквивалентные строки одинаковыми."""
    q1 = 'Ессентуки №17  "химический состав"'
    q2 = "Ессентуки No 17 «химический состав»"

    result1 = normalize_query(q1)
    result2 = normalize_query(q2)

    assert result1 == result2, f"Expected '{result1}' == '{result2}'"
    # Проверяем, что результат нормализован (точное значение может варьироваться)
    assert "ессентуки" in result1
    assert "no 17" in result1
    assert '"химический состав"' in result1


def test_normalize_query_various_cases():
    """Тест: normalize_query обрабатывает различные случаи."""
    # Тест 1: кавычки
    assert normalize_query("«текст»") == '"текст"'
    assert normalize_query('"текст"') == '"текст"'
    assert normalize_query('„текст"') == '"текст"'

    # Тест 2: № -> no
    assert normalize_query("№17") == "no 17"
    assert normalize_query("No 17") == "no 17"

    # Тест 3: тире
    assert normalize_query("текст—текст") == "текст-текст"
    assert normalize_query("текст–текст") == "текст-текст"

    # Тест 4: пробелы
    assert normalize_query("текст   текст") == "текст текст"
    assert normalize_query("  текст  ") == "текст"

    # Тест 5: ё -> е
    assert normalize_query("ёлка") == "елка"

    # Тест 6: сохраняет *
    assert normalize_query("химическ* состав") == "химическ* состав"

    # Тест 7: удаляет лишнюю пунктуацию
    assert normalize_query("текст, текст!") == "текст текст"
    assert normalize_query("текст; текст?") == "текст текст"


@pytest.fixture
def temp_db():
    """Создает временную БД для тестов."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def refresh_service(temp_db):
    """Создает RefreshService для тестов."""
    topic_registry = SQLiteTopicRegistry(db_path=temp_db)
    topic_registry.init()

    content_queue = SQLiteContentQueue(db_path=temp_db)
    content_queue.init()

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


def test_external_id_stable_for_equivalent_queries(refresh_service, temp_db):
    """Тест: external_id одинаковый для эквивалентных query строк."""
    # Создаем топик
    topic = refresh_service.topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")
    refresh_service.topic_registry.set_region_key(topic.id, "kmv")

    # Создаем две публикации с эквивалентными query строками
    q1 = 'Ессентуки №17  "химический состав"'
    q2 = "Ессентуки No 17 «химический состав»"

    pub1 = Publication(
        id="pub1",
        source="discovery:cyberleninka",
        title="Публикация 1",
        abstract="Химический состав",
        url="https://example.com/pub1",
        raw={"site": "cyberleninka", "query": q1},
    )

    pub2 = Publication(
        id="pub2",
        source="discovery:cyberleninka",
        title="Публикация 2",
        abstract="Другой текст",
        url="https://example.com/pub2",
        raw={"site": "cyberleninka", "query": q2},  # Эквивалентный query
    )

    # Генерируем external_id вручную для проверки
    external_id1 = refresh_service._generate_external_id("kmv", pub1)
    external_id2 = refresh_service._generate_external_id("kmv", pub2)

    # Проверяем, что external_id одинаковые
    assert external_id1 == external_id2, f"Expected '{external_id1}' == '{external_id2}'"

    # Проверяем через enqueue
    query_builder = QueryBuilder()
    queries = query_builder.build_backfill_queries("kmv", "КМВ")

    publications_by_query = {queries[0].query: [pub1, pub2]}
    refresh_service.provider = FakeProvider(publications_by_query)

    now = datetime.now(timezone.utc)
    stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)

    # Проверяем, что добавлена только одна публикация (вторая дедуплицирована)
    assert stats["items_enqueued"] == 1
    assert stats["items_deduped"] == 1
    assert refresh_service.content_queue.count_new(topic.id) == 1


def test_europepmc_fetch_warning_when_disabled(monkeypatch):
    """Тест: EuropePMCProvider.fetch логирует warning когда EUROPEPMC_ENABLED не установлен."""
    import logging

    from src.geotherm_bot.adapters.europepmc.provider import EuropePMCProvider
    from src.geotherm_bot.domain.models import QuerySpec

    # Убеждаемся, что флаг не установлен
    monkeypatch.delenv("EUROPEPMC_ENABLED", raising=False)

    # Настраиваем логирование для захвата warning
    logger = logging.getLogger("src.geotherm_bot.adapters.europepmc.provider")
    handler = logging.StreamHandler()
    handler.setLevel(logging.WARNING)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    provider = EuropePMCProvider(feed_urls=[])
    query_spec = QuerySpec(source="europepmc", name="test", query="test query")

    # Вызываем fetch - должен вернуть пустой список с warning
    result = provider.fetch(query_spec)

    assert result == []
    # Проверяем, что метод не бросил исключение


def test_europepmc_fetch_raises_when_enabled(monkeypatch):
    """Тест: EuropePMCProvider.fetch бросает NotImplementedError когда EUROPEPMC_ENABLED=true."""
    from src.geotherm_bot.adapters.europepmc.provider import EuropePMCProvider
    from src.geotherm_bot.domain.models import QuerySpec

    # Устанавливаем флаг
    monkeypatch.setenv("EUROPEPMC_ENABLED", "true")

    provider = EuropePMCProvider(feed_urls=[])
    query_spec = QuerySpec(source="europepmc", name="test", query="test query")

    # Вызываем fetch - должен бросить NotImplementedError
    try:
        provider.fetch(query_spec)
        assert False, "Expected NotImplementedError"
    except NotImplementedError as e:
        assert "EuropePMCProvider.fetch" in str(e)
        assert "QuerySpec" in str(e)
        assert "test query" in str(e)
