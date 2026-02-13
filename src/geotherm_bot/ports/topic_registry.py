"""
Интерфейс для хранения информации о Telegram forum topics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Topic:
    """Модель топика Telegram forum."""

    id: int
    chat_id: int
    message_thread_id: int
    name: str
    region_key: str
    mode: str  # default 'backfill_ru'
    enabled: bool  # default True
    created_at: datetime
    last_post_at: datetime | None


class TopicRegistry(ABC):
    """Абстрактный интерфейс для хранения информации о топиках."""

    @abstractmethod
    def upsert_topic(self, chat_id: int, message_thread_id: int, name: str | None) -> Topic:
        """
        Создает или обновляет топик.

        Args:
            chat_id: ID чата
            message_thread_id: ID топика (message_thread_id)
            name: Название топика (может быть None)

        Returns:
            Topic: Созданный или обновленный топик
        """
        pass

    @abstractmethod
    def get_topic(self, chat_id: int, message_thread_id: int) -> Topic | None:
        """
        Получает топик по chat_id и message_thread_id.

        Args:
            chat_id: ID чата
            message_thread_id: ID топика

        Returns:
            Topic | None: Топик или None если не найден
        """
        pass

    @abstractmethod
    def list_topics(self, chat_id: int, enabled_only: bool = True) -> list[Topic]:
        """
        Получает список топиков для чата.

        Args:
            chat_id: ID чата
            enabled_only: Если True, возвращать только включенные топики

        Returns:
            list[Topic]: Список топиков
        """
        pass

    @abstractmethod
    def touch_last_post(self, topic_id: int, dt: datetime) -> None:
        """
        Обновляет время последнего поста в топике.

        Args:
            topic_id: ID топика
            dt: Время последнего поста
        """
        pass

    @abstractmethod
    def set_region_key(self, topic_id: int, region_key: str) -> None:
        """
        Устанавливает region_key для топика.

        Args:
            topic_id: ID топика
            region_key: Ключ региона
        """
        pass

    @abstractmethod
    def set_enabled(self, topic_id: int, enabled: bool) -> None:
        """
        Устанавливает статус enabled для топика.

        Args:
            topic_id: ID топика
            enabled: Включен ли топик
        """
        pass

    @abstractmethod
    def init(self) -> None:
        """Инициализирует хранилище (создает таблицы и т.д.)."""
        pass
