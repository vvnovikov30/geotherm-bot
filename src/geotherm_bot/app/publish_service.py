"""
Сервис для публикации элементов из очереди.
"""

from datetime import datetime, timezone
from typing import Dict

from ..ports.notifier import Notifier
from ..ports.queue import ContentQueue, QueueItem
from ..ports.topic_registry import Topic, TopicRegistry


def render_queue_item(topic: Topic, item: QueueItem) -> str:
    """
    Рендерит текст сообщения для QueueItem.

    Формат:
    - Первая строка: "[BACKFILL][DISCOVERY] {topic.name}"
    - "Score: {item.score}"
    - "Reasons: " + ", ".join(item.reasons[:5])
    - "Query: {item.snippet}"  (snippet хранит query строку)
    - "Source: {item.source}"
    - "Link: {item.url}" (если url None -> пропусти строку)
    - "Tags: #backfill #discovery #{topic.region_key}"

    Args:
        topic: Топик
        item: Элемент очереди

    Returns:
        str: Текст сообщения
    """
    lines = []

    # Первая строка
    lines.append(f"[BACKFILL][DISCOVERY] {topic.name}")

    # Score
    lines.append(f"Score: {item.score}")

    # Reasons
    if item.reasons:
        reasons_str = ", ".join(item.reasons[:5])
        lines.append(f"Reasons: {reasons_str}")

    # Query
    if item.snippet:
        lines.append(f"Query: {item.snippet}")

    # Source
    lines.append(f"Source: {item.source}")

    # Link (если есть)
    if item.url:
        lines.append(f"Link: {item.url}")

    # Tags
    tags = ["#backfill", "#discovery"]
    if topic.region_key:
        tags.append(f"#{topic.region_key}")
    lines.append(f"Tags: {' '.join(tags)}")

    return "\n".join(lines)


class PublishService:
    """Сервис для публикации элементов из очереди."""

    def __init__(
        self,
        topic_registry: TopicRegistry,
        content_queue: ContentQueue,
        notifier: Notifier,
        dry_run: bool = False,
    ):
        """
        Инициализирует PublishService.

        Args:
            topic_registry: Реестр топиков
            content_queue: Очередь контента
            notifier: Уведомитель
            dry_run: Если True, не отправляет сообщения и не меняет состояние
        """
        self.topic_registry = topic_registry
        self.content_queue = content_queue
        self.notifier = notifier
        self.dry_run = dry_run

    def publish_next_for_chat(self, chat_id: int, now: datetime) -> Dict[str, any]:
        """
        Публикует следующий элемент из очереди для чата.

        Алгоритм:
        1. Выбирает топик по fairness: NULL last_post_at первыми,
           затем по last_post_at ASC, затем по created_at ASC
        2. Берет лучший элемент из очереди (по score DESC, created_at ASC)
        3. Рендерит сообщение
        4. Отправляет через notifier (если не dry_run)
        5. Помечает как posted и обновляет last_post_at (если не dry_run)

        Args:
            chat_id: ID чата
            now: Текущее время (UTC aware)

        Returns:
            dict: Статистика публикации
        """
        # 1) Выбираем топик (fair pick: самый старый last_post_at, NULL первыми)
        topics = self.topic_registry.list_topics(chat_id, enabled_only=True)

        # Фильтруем топики с новыми элементами
        candidates = []
        for t in topics:
            count = self.content_queue.count_new(t.id)
            if count > 0:
                candidates.append(t)

        if not candidates:
            return {
                "posted": False,
                "reason": "no_topics_or_empty_queues",
                "topic_id": None,
                "thread_id": None,
                "queue_item_id": None,
                "score": None,
            }

        # Сортируем по fairness: NULL last_post_at первыми,
        # затем по last_post_at ASC, затем по created_at ASC
        # Используем кортеж для сортировки: (has_last_post, last_post_at, created_at)
        # NULL last_post_at -> (False, epoch_utc, created_at)
        epoch_utc = datetime(1970, 1, 1, tzinfo=timezone.utc)

        candidates.sort(
            key=lambda t: (
                t.last_post_at is not None,  # False (NULL) первыми
                t.last_post_at if t.last_post_at is not None else epoch_utc,
                t.created_at,
            )
        )

        topic = candidates[0]
        topic_id = topic.id

        # 2) Берем лучший элемент из выбранного топика
        item = self.content_queue.pop_best_new(topic_id)
        if item is None:
            return {
                "posted": False,
                "reason": "empty_queue_for_picked_topic",
                "topic_id": topic_id,
                "thread_id": topic.message_thread_id,
                "queue_item_id": None,
                "score": None,
            }

        # Проверяем, что item.id не None
        if item.id is None:
            raise ValueError("QueueItem.id must not be None after pop_best_new")

        # 3) Рендерим сообщение
        text = render_queue_item(topic, item)

        # 4) Если dry_run - не отправляем и не меняем состояние
        if self.dry_run:
            return {
                "posted": True,
                "reason": "dry_run",
                "topic_id": topic_id,
                "thread_id": topic.message_thread_id,
                "queue_item_id": item.id,
                "score": item.score,
            }

        # 5) Отправляем сообщение
        try:
            self.notifier.send_message(
                chat_id=chat_id, text=text, message_thread_id=topic.message_thread_id
            )
        except Exception:
            # При ошибке не помечаем как posted, пробрасываем исключение
            raise

        # 6) Помечаем как posted и обновляем last_post_at
        self.content_queue.mark_posted(item.id, now)
        self.topic_registry.touch_last_post(topic_id, now)

        return {
            "posted": True,
            "reason": "posted",
            "topic_id": topic_id,
            "thread_id": topic.message_thread_id,
            "queue_item_id": item.id,
            "score": item.score,
        }
