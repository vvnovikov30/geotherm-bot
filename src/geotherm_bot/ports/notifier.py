"""
Интерфейс для отправки уведомлений.
"""
from abc import ABC, abstractmethod


class Notifier(ABC):
    """Абстрактный интерфейс для отправки уведомлений."""
    
    @abstractmethod
    def send(self, chat_id: str, message_thread_id: int, text: str, topic_key: str = None) -> bool:
        """
        Отправляет уведомление (legacy метод).
        
        Args:
            chat_id: ID чата/группы/канала
            message_thread_id: ID темы (topic) в группе
            text: Текст сообщения
            topic_key: Ключ темы для логирования (опционально)
        
        Returns:
            bool: True если сообщение отправлено успешно, False иначе
        """
        pass
    
    @abstractmethod
    def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> None:
        """
        Отправляет сообщение.
        
        Args:
            chat_id: ID чата/группы/канала (int)
            text: Текст сообщения
            message_thread_id: ID темы (topic) в группе (опционально)
        
        Raises:
            Exception: При ошибке отправки
        """
        pass