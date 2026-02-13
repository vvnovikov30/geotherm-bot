"""
Сервис для обновления очереди контента из discovery источников.
"""
import hashlib
import re
from datetime import datetime
from typing import Callable, Dict

from ..domain.models import FilterDecision, Publication, ScoreResult
from ..ports.publications_api import PublicationsAPI
from ..ports.queue import ContentQueue, QueueItem
from ..ports.topic_registry import TopicRegistry
from .query_builder import QueryBuilder
from .region import RegionResolver


def normalize_query(query: str) -> str:
    """
    Нормализует query строку для стабильного external_id.
    
    Правила нормализации:
    1. strip + lower
    2. замена 'ё' -> 'е'
    3. унификация кавычек
    4. замена '№' -> 'no'
    5. замена длинных тире/дефисов на '-'
    6. удаление пунктуации кроме: латиница/цифры/кириллица/пробелы/*/кавычки/дефис
    7. collapse spaces
    
    Args:
        query: Исходная query строка
    
    Returns:
        str: Нормализованная query строка
    """
    if not query:
        return ""
    
    # 1) strip + lower
    s = query.strip().lower()
    
    # 2) замена 'ё' -> 'е'
    s = s.replace('ё', 'е')
    
    # 3) унификация кавычек
    # «» -> "
    s = s.replace('«', '"').replace('»', '"')
    # "" -> "
    s = s.replace('"', '"').replace('"', '"')
    # „" -> "
    s = s.replace('„', '"').replace('"', '"')
    # ' ' -> '
    s = s.replace(''', "'").replace(''', "'")
    
    # 4) замена '№' -> 'no ' (с пробелом для консистентности)
    s = s.replace('№', 'no ')
    
    # 5) замена длинных тире/дефисов на '-'
    # — (em dash), – (en dash), ‐ (hyphen) -> -
    s = s.replace('—', '-').replace('–', '-').replace('‐', '-')
    
    # 6) убрать пунктуацию кроме: латиница/цифры/кириллица/пробелы/*/кавычки/дефис
    # Оставляем: a-z, 0-9, а-я, пробелы, *, ", ', -
    result = []
    for char in s:
        if char.isalnum():  # латиница, цифры, кириллица
            result.append(char)
        elif char in (' ', '*', '"', "'", '-'):
            result.append(char)
        else:
            # Всё остальное заменяем пробелом
            result.append(' ')
    
    s = ''.join(result)
    
    # 7) collapse spaces до одного пробела
    s = re.sub(r'\s+', ' ', s)
    s = s.strip()
    
    return s


class RefreshService:
    """Сервис для обновления очереди контента."""
    
    def __init__(
        self,
        topic_registry: TopicRegistry,
        content_queue: ContentQueue,
        region_resolver: RegionResolver,
        query_builder: QueryBuilder,
        provider: PublicationsAPI,
        filtering: Callable[[Publication], FilterDecision],
        scoring: Callable[[Publication], ScoreResult],
    ):
        """
        Инициализирует RefreshService.
        
        Args:
            topic_registry: Реестр топиков
            content_queue: Очередь контента
            region_resolver: Резолвер регионов
            query_builder: Построитель запросов
            provider: Провайдер публикаций
            filtering: Функция фильтрации (pub -> FilterDecision)
            scoring: Функция скоринга (pub -> ScoreResult)
        """
        self.topic_registry = topic_registry
        self.content_queue = content_queue
        self.region_resolver = region_resolver
        self.query_builder = query_builder
        self.provider = provider
        self.filtering = filtering
        self.scoring = scoring
    
    def refresh_queue_for_chat(self, chat_id: int, now: datetime) -> Dict[str, int]:
        """
        Обновляет очередь контента для чата.
        
        Алгоритм:
        1. Получает активные топики для чата
        2. Для каждого топика в mode='backfill_ru':
           - Вычисляет region_key если пустой
           - Проверяет лимит очереди (80)
           - Генерирует запросы через QueryBuilder
           - Для каждого запроса получает публикации
           - Фильтрует и скорит публикации
           - Добавляет в очередь (лимит 30 на топик за refresh)
        
        Args:
            chat_id: ID чата
            now: Текущее время (UTC aware)
        
        Returns:
            dict: Статистика обновления
        """
        stats = {
            "topics_seen": 0,
            "queries_built": 0,
            "pubs_fetched": 0,
            "pubs_passed": 0,
            "items_enqueued": 0,
            "items_deduped": 0,
            "topics_skipped_full": 0,
        }
        
        # Получаем активные топики
        topics = self.topic_registry.list_topics(chat_id, enabled_only=True)
        stats["topics_seen"] = len(topics)
        
        for topic in topics:
            # Пропускаем топики не в mode='backfill_ru'
            if topic.mode != 'backfill_ru':
                continue
            
            # Вычисляем region_key если пустой
            if not topic.region_key:
                region_key = self.region_resolver.infer_region_key(topic.name)
                self.topic_registry.set_region_key(topic.id, region_key)
                topic.region_key = region_key
            
            # Проверяем лимит очереди (80)
            queue_count = self.content_queue.count_new(topic.id)
            if queue_count >= 80:
                stats["topics_skipped_full"] += 1
                continue
            
            # Генерируем запросы
            queries = self.query_builder.build_backfill_queries(topic.region_key, topic.name)
            # Ограничиваем до 12 запросов на топик
            queries = queries[:12]
            stats["queries_built"] += len(queries)
            
            items_enqueued_for_topic = 0
            pubs_processed_for_topic = 0
            
            # Обрабатываем каждый запрос
            for query_spec in queries:
                # Получаем публикации
                pubs = self.provider.fetch(query_spec)
                stats["pubs_fetched"] += len(pubs)
                
                # Ограничиваем обработку до 200 pubs per topic per refresh
                remaining_pubs = 200 - pubs_processed_for_topic
                if remaining_pubs <= 0:
                    break
                
                pubs_to_process = pubs[:remaining_pubs]
                pubs_processed_for_topic += len(pubs_to_process)
                
                # Обрабатываем каждую публикацию
                for pub in pubs_to_process:
                    # Фильтрация
                    decision = self.filtering(pub)
                    if not decision.passed:
                        continue
                    
                    # Скоринг
                    score_result = self.scoring(pub)
                    if score_result.score < 5:
                        continue
                    
                    stats["pubs_passed"] += 1
                    
                    # Генерируем external_id
                    external_id = self._generate_external_id(topic.region_key, pub)
                    
                    # Создаем QueueItem
                    item = QueueItem(
                        id=None,
                        topic_id=topic.id,
                        item_type="discovery_link",
                        source=pub.source,
                        external_id=external_id,
                        title=pub.title,
                        snippet=pub.abstract or "",
                        url=pub.url,
                        score=score_result.score,
                        reasons=score_result.reasons,
                        status="new",
                        created_at=now,
                        posted_at=None
                    )
                    
                    # Добавляем в очередь
                    ok = self.content_queue.enqueue(item)
                    if ok:
                        items_enqueued_for_topic += 1
                        stats["items_enqueued"] += 1
                    else:
                        stats["items_deduped"] += 1
                    
                    # Лимит 30 на топик за refresh
                    if items_enqueued_for_topic >= 30:
                        break
                
                # Если достигнут лимит на топик, прекращаем обработку запросов
                if items_enqueued_for_topic >= 30:
                    break
        
        return stats
    
    def _generate_external_id(self, region_key: str, pub: Publication) -> str:
        """
        Генерирует стабильный external_id для публикации.
        
        Приоритет:
        1. Если pub.raw содержит {"site":..., "query":...}:
           external_id = sha1(region_key + "|" + pub.raw["site"] + "|" + normalize(pub.raw["query"]))
        2. Иначе:
           external_id = sha1(region_key + "|" + pub.source + "|" + (pub.url or "") + "|" + (pub.abstract or ""))
        
        Args:
            region_key: Ключ региона
            pub: Публикация
        
        Returns:
            str: SHA1 хеш external_id
        """
        raw = pub.raw or {}
        
        if "site" in raw and "query" in raw:
            # Используем site и query из raw
            site = str(raw["site"])
            query = normalize_query(str(raw["query"]))
            key_string = f"{region_key}|{site}|{query}"
        else:
            # Fallback: используем source, url, abstract
            source = pub.source or ""
            url = pub.url or ""
            abstract = pub.abstract or ""
            key_string = f"{region_key}|{source}|{url}|{abstract}"
        
        # Генерируем SHA1 хеш
        return hashlib.sha1(key_string.encode('utf-8')).hexdigest()
