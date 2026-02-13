"""
Ручной тест для RefreshService (без pytest).
"""
import os
import tempfile
from datetime import datetime, timezone

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
        self.publications_by_query = publications_by_query or {}
    
    def fetch(self, query_spec: QuerySpec) -> list[Publication]:
        """Возвращает публикации для query_spec."""
        return self.publications_by_query.get(query_spec.query, [])
    
    def fetch_publications(self) -> list[Publication]:
        """Legacy метод."""
        return []


def fake_filtering(pub: Publication) -> FilterDecision:
    """Фейковая функция фильтрации."""
    abstract = (pub.abstract or "").lower()
    if "сточные" in abstract:
        return FilterDecision(passed=False, reasons=["contains сточные"])
    return FilterDecision(passed=True, reasons=[])


def fake_scoring(pub: Publication) -> ScoreResult:
    """Фейковая функция скоринга."""
    title = (pub.title or "").lower()
    if "low_score" in title:
        return ScoreResult(score=2, reasons=["low_score test"], is_high_priority=False)
    return ScoreResult(score=6, reasons=["geo", "chem"], is_high_priority=False)


def test_all():
    """Запускает все тесты."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # Инициализация
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
        
        # Тест 1: refresh добавляет элементы в очередь
        print("Test 1: refresh_enqueues_items_for_topics")
        topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=10, name="КМВ")
        assert topic.region_key == ""
        
        pub1 = Publication(
            id="pub1",
            source="discovery:cyberleninka",
            title="Тестовая публикация 1",
            abstract="Химический состав минеральных вод",
            url="https://example.com/pub1",
            raw={"site": "cyberleninka", "query": "Ессентуки chemistry"}
        )
        
        pub2 = Publication(
            id="pub2",
            source="discovery:cyberleninka",
            title="Тестовая публикация 2",
            abstract="Источники минеральных вод",
            url="https://example.com/pub2",
            raw={"site": "cyberleninka", "query": "Ессентуки wells"}
        )
        
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {}
        for q in queries[:2]:
            publications_by_query[q.query] = [pub1, pub2]
        
        refresh_service.provider = FakeProvider(publications_by_query)
        
        now = datetime.now(timezone.utc)
        stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        assert stats["topics_seen"] == 1
        assert stats["queries_built"] > 0
        assert stats["pubs_fetched"] > 0
        assert stats["items_enqueued"] > 0
        
        updated_topic = topic_registry.get_topic(chat_id=1, message_thread_id=10)
        assert updated_topic.region_key == "kmv"
        
        count = content_queue.count_new(topic.id)
        assert count > 0
        print("  [OK] PASS")
        
        # Тест 2: лимит очереди (80)
        print("Test 2: refresh_respects_topic_queue_cap")
        from src.geotherm_bot.ports.queue import QueueItem
        
        # Создаем новый топик для этого теста
        topic2 = topic_registry.upsert_topic(chat_id=1, message_thread_id=20, name="Тест 2")
        
        enqueued = 0
        for i in range(100):  # Пробуем больше, чтобы набрать 80
            item = QueueItem(
                id=None,
                topic_id=topic2.id,
                item_type="discovery_link",
                source="discovery:test",
                external_id=f"test_id_{i}",
                title=f"Test {i}",
                snippet="",
                url="https://example.com",
                score=5,
                reasons=[],
                status="new",
                created_at=now
            )
            if content_queue.enqueue(item):
                enqueued += 1
            if content_queue.count_new(topic2.id) >= 80:
                break
        
        queue_count = content_queue.count_new(topic2.id)
        assert queue_count >= 80, f"Expected at least 80, got {queue_count}"
        
        pub = Publication(
            id="pub3",
            source="discovery:cyberleninka",
            title="Тестовая публикация",
            abstract="Химический состав",
            url="https://example.com/pub3",
            raw={"site": "cyberleninka", "query": "test"}
        )
        
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {queries[0].query: [pub]}
        refresh_service.provider = FakeProvider(publications_by_query)
        
        # Устанавливаем region_key для topic2
        topic_registry.set_region_key(topic2.id, "kmv")
        
        stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        # Проверяем, что topic2 был пропущен (полная очередь)
        # topic (КМВ) может быть обработан, поэтому items_enqueued может быть > 0
        # Но topics_skipped_full должен быть >= 1 (topic2)
        assert stats["topics_skipped_full"] >= 1
        assert content_queue.count_new(topic2.id) >= 80
        print("  [OK] PASS")
        
        # Тест 3: лимит 30 на топик
        print("Test 3: refresh_respects_per_topic_limit_30")
        # Очищаем очередь
        while True:
            popped = content_queue.pop_best_new(topic.id)
            if popped is None:
                break
            content_queue.mark_posted(popped.id, now)
        
        pubs = []
        for i in range(100):
            pub = Publication(
                id=f"pub{i}",
                source="discovery:cyberleninka",
                title=f"Тестовая публикация {i}",
                abstract="Химический состав",
                url=f"https://example.com/pub{i}",
                raw={"site": "cyberleninka", "query": f"test query {i}"}
            )
            pubs.append(pub)
        
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {queries[0].query: pubs}
        refresh_service.provider = FakeProvider(publications_by_query)
        
        stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        assert stats["items_enqueued"] <= 30
        assert content_queue.count_new(topic.id) <= 30
        print("  [OK] PASS")
        
        # Тест 4: фильтрация по score
        print("Test 4: refresh_threshold_filters_low_score")
        # Очищаем очередь
        while True:
            popped = content_queue.pop_best_new(topic.id)
            if popped is None:
                break
            content_queue.mark_posted(popped.id, now)
        
        pub_low = Publication(
            id="pub_low",
            source="discovery:cyberleninka",
            title="low_score публикация",
            abstract="Химический состав",
            url="https://example.com/pub_low",
            raw={"site": "cyberleninka", "query": "test"}
        )
        
        pub_normal = Publication(
            id="pub_normal",
            source="discovery:cyberleninka",
            title="Нормальная публикация",
            abstract="Химический состав",
            url="https://example.com/pub_normal",
            raw={"site": "cyberleninka", "query": "test2"}
        )
        
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {queries[0].query: [pub_low, pub_normal]}
        refresh_service.provider = FakeProvider(publications_by_query)
        
        stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        assert stats["items_enqueued"] == 1
        assert content_queue.count_new(topic.id) == 1
        print("  [OK] PASS")
        
        # Тест 5: дедупликация
        print("Test 5: refresh_dedup_works")
        # Очищаем очередь
        while True:
            popped = content_queue.pop_best_new(topic.id)
            if popped is None:
                break
            content_queue.mark_posted(popped.id, now)
        
        pub1 = Publication(
            id="pub1",
            source="discovery:cyberleninka",
            title="Публикация 1",
            abstract="Химический состав",
            url="https://example.com/pub1",
            raw={"site": "cyberleninka", "query": "Ессентуки chemistry"}
        )
        
        pub2 = Publication(
            id="pub2",
            source="discovery:cyberleninka",
            title="Публикация 2",
            abstract="Другой текст",
            url="https://example.com/pub2",
            raw={"site": "cyberleninka", "query": "Ессентуки chemistry"}
        )
        
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {queries[0].query: [pub1, pub2]}
        refresh_service.provider = FakeProvider(publications_by_query)
        
        stats = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        # Проверяем, что добавлена только одна публикация (вторая дедуплицирована)
        # Может быть items_enqueued == 0 если обе были дедуплицированы из предыдущих тестов
        assert stats["items_enqueued"] <= 1
        assert stats["items_deduped"] >= 1
        # Проверяем, что в очереди не больше 1 элемента для этого топика
        # (может быть 0 если оба дедуплицированы)
        count = content_queue.count_new(topic.id)
        assert count <= 1
        print("  [OK] PASS")
        
        print("\n[SUCCESS] Все тесты пройдены!")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_all()
