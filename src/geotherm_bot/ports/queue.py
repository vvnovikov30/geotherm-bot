"""
Интерфейс для очереди контента и глобального seen.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class QueueItem:
    """Элемент очереди контента."""
    id: int | None
    topic_id: int
    item_type: str  # MVP: "discovery_link"
    source: str  # например "discovery:cyberleninka"
    external_id: str  # дедуп ключ (sha1)
    title: str
    snippet: str | None  # для discovery: query string
    url: str | None
    score: int
    status: str  # "new" / "posted" / "rejected"
    created_at: datetime
    reasons: list[str] = field(default_factory=list)
    posted_at: datetime | None = None


class ContentQueue(ABC):
    """Абстрактный интерфейс для очереди контента."""
    
    @abstractmethod
    def init(self) -> None:
        """Инициализирует хранилище (создает таблицы и т.д.)."""
        pass
    
    @abstractmethod
    def enqueue(self, item: QueueItem) -> bool:
        """
        Добавляет элемент в очередь с дедупликацией.
        
        Дедупликация:
        - если external_id уже есть в seen -> False
        - если (topic_id, external_id) уже в content_queue -> False
        - иначе insert в content_queue и insert/ignore в seen -> True
        
        Args:
            item: Элемент для добавления
        
        Returns:
            bool: True если элемент добавлен, False если был дедуплицирован
        """
        pass
    
    @abstractmethod
    def count_new(self, topic_id: int) -> int:
        """
        Подсчитывает количество новых элементов для топика.
        
        Args:
            topic_id: ID топика
        
        Returns:
            int: Количество элементов со статусом 'new'
        """
        pass
    
    @abstractmethod
    def pop_best_new(self, topic_id: int) -> QueueItem | None:
        """
        Извлекает лучший новый элемент из очереди (не меняет статус).
        
        Сортировка: score DESC, created_at ASC
        
        Args:
            topic_id: ID топика
        
        Returns:
            QueueItem | None: Лучший элемент или None если нет новых
        """
        pass
    
    @abstractmethod
    def mark_posted(self, item_id: int, posted_at: datetime) -> None:
        """
        Помечает элемент как опубликованный.
        
        Args:
            item_id: ID элемента
            posted_at: Время публикации
        """
        pass
    
    @abstractmethod
    def mark_rejected(self, item_id: int) -> None:
        """
        Помечает элемент как отклоненный.
        
        Args:
            item_id: ID элемента
        """
        pass
    
    @abstractmethod
    def seen_exists(self, external_id: str, source_kind: str = '') -> bool:
        """
        Проверяет, существует ли external_id в глобальном seen.
        
        Args:
            external_id: Внешний идентификатор
            source_kind: Тип источника ('discovery' или '') для проверки TTL
        
        Returns:
            bool: True если external_id уже был виден и не истек TTL
        """
        pass
