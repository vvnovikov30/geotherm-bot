"""
Ручной тест для normalize_query и стабильности external_id (без pytest).
"""
import os
import tempfile
from datetime import datetime, timezone

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


def test_all():
    """Запускает все тесты."""
    # Тест 1: normalize_query делает эквивалентные строки одинаковыми
    print("Test 1: normalize_query_stable_equivalence")
    q1 = 'Ессентуки №17  "химический состав"'
    q2 = 'Ессентуки No 17 «химический состав»'
    
    result1 = normalize_query(q1)
    result2 = normalize_query(q2)
    
    assert result1 == result2, f"Expected '{result1}' == '{result2}'"
    # Проверяем, что результаты одинаковые (точное значение может варьироваться)
    assert result1 == result2
    print("  [OK] PASS")
    
    # Тест 2: различные случаи нормализации
    print("Test 2: normalize_query_various_cases")
    assert normalize_query('«текст»') == '"текст"'
    assert normalize_query('№17') == 'no 17'
    assert normalize_query('текст—текст') == 'текст-текст'
    assert normalize_query('текст   текст') == 'текст текст'
    assert normalize_query('ёлка') == 'елка'
    assert normalize_query('химическ* состав') == 'химическ* состав'
    assert normalize_query('текст, текст!') == 'текст текст'
    print("  [OK] PASS")
    
    # Тест 3: external_id стабилен для эквивалентных queries
    print("Test 3: external_id_stable_for_equivalent_queries")
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()
        
        content_queue = SQLiteContentQueue(db_path=db_path)
        content_queue.init()
        
        region_resolver = RegionResolver()
        query_builder = QueryBuilder()
        provider = FakeProvider()
        
        refresh_service = RefreshService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            region_resolver=region_resolver,
            query_builder=query_builder,
            provider=provider,
            filtering=fake_filtering,
            scoring=fake_scoring,
        )
        
        topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")
        topic_registry.set_region_key(topic.id, "kmv")
        
        q1 = 'Ессентуки №17  "химический состав"'
        q2 = 'Ессентуки No 17 «химический состав»'
        
        pub1 = Publication(
            id="pub1",
            source="discovery:cyberleninka",
            title="Публикация 1",
            abstract="Химический состав",
            url="https://example.com/pub1",
            raw={"site": "cyberleninka", "query": q1}
        )
        
        pub2 = Publication(
            id="pub2",
            source="discovery:cyberleninka",
            title="Публикация 2",
            abstract="Другой текст",
            url="https://example.com/pub2",
            raw={"site": "cyberleninka", "query": q2}
        )
        
        external_id1 = refresh_service._generate_external_id("kmv", pub1)
        external_id2 = refresh_service._generate_external_id("kmv", pub2)
        
        assert external_id1 == external_id2, f"Expected '{external_id1}' == '{external_id2}'"
        
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {queries[0].query: [pub1, pub2]}
        refresh_service.provider = FakeProvider(publications_by_query)
        
        now = datetime.now(timezone.utc)
        stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        assert stats["items_enqueued"] == 1
        assert stats["items_deduped"] == 1
        assert content_queue.count_new(topic.id) == 1
        print("  [OK] PASS")
        
        # Тест 4: EuropePMCProvider.fetch warning
        print("Test 4: europepmc_fetch_warning_when_disabled")
        from src.geotherm_bot.adapters.europepmc.provider import EuropePMCProvider
        
        # Убеждаемся, что флаг не установлен
        if "EUROPEPMC_ENABLED" in os.environ:
            del os.environ["EUROPEPMC_ENABLED"]
        
        provider = EuropePMCProvider(feed_urls=[])
        query_spec = QuerySpec(
            source="europepmc",
            name="test",
            query="test query"
        )
        
        result = provider.fetch(query_spec)
        assert result == []
        print("  [OK] PASS")
        
        # Тест 5: EuropePMCProvider.fetch raises when enabled
        print("Test 5: europepmc_fetch_raises_when_enabled")
        os.environ["EUROPEPMC_ENABLED"] = "true"
        
        try:
            provider.fetch(query_spec)
            assert False, "Expected NotImplementedError"
        except NotImplementedError as e:
            assert "EuropePMCProvider.fetch" in str(e)
            assert "QuerySpec" in str(e)
            assert "test query" in str(e)
        finally:
            # Очищаем флаг
            if "EUROPEPMC_ENABLED" in os.environ:
                del os.environ["EUROPEPMC_ENABLED"]
        print("  [OK] PASS")
        
        print("\n[SUCCESS] Все тесты пройдены!")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_all()
