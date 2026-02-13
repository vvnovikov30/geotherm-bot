"""
Тест идемпотентности refresh: двойной refresh на одной БД не должен создавать дубликаты.
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
        return self.publications_by_query.get(query_spec.query, [])
    
    def fetch_publications(self) -> list[Publication]:
        return []


def fake_filtering(pub: Publication) -> FilterDecision:
    """Фейковая функция фильтрации (всегда пропускает)."""
    return FilterDecision(passed=True, reasons=[])


def fake_scoring(pub: Publication) -> ScoreResult:
    """Фейковая функция скоринга (score=6)."""
    return ScoreResult(score=6, reasons=["geo", "chem"], is_high_priority=False)


def test_idempotent_refresh_double_refresh_no_duplicates():
    """
    Тест: двойной refresh на одной БД не создает дубликаты.
    
    Проверяет:
    - Первый refresh добавляет элементы в очередь
    - Второй refresh не добавляет дубликаты (дедуп работает)
    - seen содержит записи для всех external_id
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # 1) Создаем компоненты
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()
        
        content_queue = SQLiteContentQueue(db_path=db_path)
        content_queue.init()
        
        region_resolver = RegionResolver()
        query_builder = QueryBuilder()
        
        # 2) Создаем FakeProvider с публикациями
        pub1 = Publication(
            id="pub1",
            source="discovery:cyberleninka",
            title="Тестовая публикация 1",
            abstract="Химический состав минеральных вод КМВ",
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
        
        # Настраиваем провайдер для возврата публикаций
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {}
        for q in queries[:2]:  # Только первые 2 запроса
            publications_by_query[q.query] = [pub1, pub2]
        
        provider = FakeProvider(publications_by_query)
        
        # 3) Создаем RefreshService
        refresh_service = RefreshService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            region_resolver=region_resolver,
            query_builder=query_builder,
            provider=provider,
            filtering=fake_filtering,
            scoring=fake_scoring,
        )
        
        # 4) Создаем topic
        topic = topic_registry.upsert_topic(
            chat_id=1,
            message_thread_id=100,
            name="КМВ"
        )
        topic_registry.set_region_key(topic.id, "kmv")
        
        # 5) Первый refresh
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        stats1 = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        assert stats1["items_enqueued"] > 0, (
            f"Первый refresh должен добавить элементы, "
            f"получили {stats1['items_enqueued']}"
        )
        
        new_count_after_first = content_queue.count_new(topic.id)
        assert new_count_after_first > 0, (
            f"После первого refresh должно быть элементов в очереди, "
            f"получили {new_count_after_first}"
        )
        
        # Сохраняем external_id для проверки seen
        # Получаем первый элемент из очереди (не удаляя его через pop_best_new)
        # Используем прямой SQL запрос
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT external_id FROM content_queue "
            "WHERE topic_id = ? AND status = 'new' LIMIT 1",
            (topic.id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None, "Должен быть хотя бы один элемент в очереди"
        external_id_to_check = row['external_id']
        
        # 6) Второй refresh (без очистки БД)
        stats2 = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        new_count_after_second = content_queue.count_new(topic.id)
        
        # Проверяем, что количество не увеличилось
        assert new_count_after_second == new_count_after_first, (
            f"Второй refresh не должен добавлять дубликаты. "
            f"Было: {new_count_after_first}, стало: {new_count_after_second}"
        )
        
        # Проверяем, что второй refresh не добавил элементов
        assert stats2["items_enqueued"] == 0, (
            f"Второй refresh не должен добавлять элементы, "
            f"получили {stats2['items_enqueued']}"
        )
        
        # Проверяем, что items_deduped увеличился
        assert stats2["items_deduped"] > 0, (
            f"Второй refresh должен показывать дедупликацию, "
            f"получили {stats2['items_deduped']}"
        )
        
        # 7) Проверяем, что seen содержит записи
        assert content_queue.seen_exists(external_id_to_check), (
            f"external_id {external_id_to_check} должен быть в seen"
        )
        
        # Проверяем стабильность: делаем третий refresh
        stats3 = refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        new_count_after_third = content_queue.count_new(topic.id)
        
        assert new_count_after_third == new_count_after_first, (
            f"Третий refresh также не должен добавлять дубликаты. "
            f"Было: {new_count_after_first}, стало: {new_count_after_third}"
        )
        assert stats3["items_enqueued"] == 0, (
            f"Третий refresh не должен добавлять элементы, "
            f"получили {stats3['items_enqueued']}"
        )
        
        print("[OK] Идемпотентность проверена:")
        print(f"  Первый refresh: {stats1['items_enqueued']} элементов")
        print(f"  Второй refresh: {stats2['items_enqueued']} элементов, "
              f"{stats2['items_deduped']} дедуплицировано")
        print(f"  Третий refresh: {stats3['items_enqueued']} элементов, "
              f"{stats3['items_deduped']} дедуплицировано")
        print(f"  Количество в очереди стабильно: {new_count_after_first}")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
