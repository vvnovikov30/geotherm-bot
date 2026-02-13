"""
Smoke test для интеграции refresh->publish (полностью офлайн).
"""
import os
import tempfile
from datetime import datetime, timezone

from src.geotherm_bot.adapters.storage.sqlite_queue import SQLiteContentQueue
from src.geotherm_bot.adapters.storage.sqlite_topics import SQLiteTopicRegistry
from src.geotherm_bot.app.publish_service import PublishService
from src.geotherm_bot.app.query_builder import QueryBuilder
from src.geotherm_bot.app.refresh_service import RefreshService
from src.geotherm_bot.app.region import RegionResolver
from src.geotherm_bot.domain.models import FilterDecision, Publication, QuerySpec, ScoreResult
from src.geotherm_bot.ports.notifier import Notifier
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


class FakeNotifier(Notifier):
    """Фейковый notifier для тестов."""
    
    def __init__(self):
        self.calls = []
    
    def send(self, chat_id: str, message_thread_id: int, text: str, topic_key: str = None) -> bool:
        return True
    
    def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> None:
        self.calls.append({
            "chat_id": chat_id,
            "text": text,
            "message_thread_id": message_thread_id,
        })


def test_smoke_integration():
    """Smoke test: refresh -> publish интеграция."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        # a) Создаем TopicRegistry и ContentQueue
        topic_registry = SQLiteTopicRegistry(db_path=db_path)
        topic_registry.init()
        
        content_queue = SQLiteContentQueue(db_path=db_path)
        content_queue.init()
        
        # b) Создаем 1 topic
        topic = topic_registry.upsert_topic(chat_id=1, message_thread_id=100, name="КМВ")
        topic_registry.set_region_key(topic.id, "kmv")
        
        # c) Создаем FakeProvider, FakeFiltering, FakeScoring
        # Настраиваем провайдер для возврата публикаций
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
        
        query_builder = QueryBuilder()
        queries = query_builder.build_backfill_queries("kmv", "КМВ")
        publications_by_query = {}
        for q in queries[:2]:  # Только первые 2 запроса
            publications_by_query[q.query] = [pub1, pub2]
        
        provider = FakeProvider(publications_by_query)
        
        # d) Создаем RefreshService
        refresh_service = RefreshService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            region_resolver=RegionResolver(),
            query_builder=query_builder,
            provider=provider,
            filtering=fake_filtering,
            scoring=fake_scoring,
        )
        
        # e) Вызываем refresh_queue_for_chat
        now = datetime.now(timezone.utc)
        refresh_service.refresh_queue_for_chat(chat_id=1, now=now)
        
        # f) Убеждаемся, что queue.count_new(topic.id) > 0
        count_after_refresh = content_queue.count_new(topic.id)
        assert count_after_refresh > 0, f"Expected count > 0, got {count_after_refresh}"
        print(f"[OK] Refresh добавил {count_after_refresh} элементов в очередь")
        
        # g) Создаем FakeNotifier
        notifier = FakeNotifier()
        
        # h) Вызываем PublishService(dry_run=True).publish_next_for_chat
        publish_service_dry = PublishService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            notifier=notifier,
            dry_run=True,
        )
        
        result_dry = publish_service_dry.publish_next_for_chat(chat_id=1, now=now)
        
        # i) Убеждаемся, что в dry_run:
        assert result_dry["posted"] is True
        assert result_dry["reason"] == "dry_run"
        assert len(notifier.calls) == 0, "FakeNotifier не должен быть вызван в dry_run"
        
        count_after_dry = content_queue.count_new(topic.id)
        assert count_after_dry == count_after_refresh, f"В dry_run очередь не должна уменьшиться: {count_after_dry} == {count_after_refresh}"
        print(f"[OK] Dry-run не изменил состояние: {count_after_dry} элементов осталось")
        
        # Проверяем, что last_post_at не обновился
        topic_after_dry = topic_registry.get_topic(chat_id=1, message_thread_id=100)
        assert topic_after_dry.last_post_at is None, "last_post_at не должен обновиться в dry_run"
        
        # j) Вызываем PublishService(dry_run=False)
        notifier.calls = []  # Очищаем вызовы
        publish_service = PublishService(
            topic_registry=topic_registry,
            content_queue=content_queue,
            notifier=notifier,
            dry_run=False,
        )
        
        result = publish_service.publish_next_for_chat(chat_id=1, now=now)
        
        # Убеждаемся:
        assert result["posted"] is True
        assert result["reason"] == "posted"
        assert len(notifier.calls) == 1, f"FakeNotifier должен быть вызван 1 раз, получили {len(notifier.calls)}"
        
        count_after_publish = content_queue.count_new(topic.id)
        assert count_after_publish == count_after_refresh - 1, f"Очередь должна уменьшиться на 1: {count_after_publish} == {count_after_refresh - 1}"
        print(f"[OK] Publish уменьшил очередь: {count_after_publish} элементов осталось")
        
        # Проверяем, что topic.last_post_at обновился
        topic_after_publish = topic_registry.get_topic(chat_id=1, message_thread_id=100)
        assert topic_after_publish.last_post_at is not None, "last_post_at должен обновиться после publish"
        assert topic_after_publish.last_post_at == now, "last_post_at должен быть равен now"
        print(f"[OK] last_post_at обновился: {topic_after_publish.last_post_at}")
        
        # Проверяем содержимое сообщения
        assert "КМВ" in notifier.calls[0]["text"]
        assert "Score:" in notifier.calls[0]["text"]
        assert "Query:" in notifier.calls[0]["text"]
        assert notifier.calls[0]["message_thread_id"] == 100
        print("[OK] Сообщение корректно сформировано")
        
        print("\n[SUCCESS] Smoke integration test passed!")
        
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    test_smoke_integration()
