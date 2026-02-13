"""
Интерфейс для хранения данных о публикациях.
"""

from abc import ABC, abstractmethod


class Repository(ABC):
    """Абстрактный интерфейс для хранения данных."""

    @abstractmethod
    def make_fingerprint(self, title: str, url: str) -> str:
        """
        Создает уникальный fingerprint для публикации.

        Args:
            title: Заголовок публикации
            url: URL публикации

        Returns:
            str: Уникальный fingerprint
        """
        pass

    @abstractmethod
    def already_seen(self, fingerprint: str) -> bool:
        """
        Проверяет, была ли публикация уже обработана.

        Args:
            fingerprint: Уникальный идентификатор публикации

        Returns:
            bool: True если публикация уже была обработана, False иначе
        """
        pass

    @abstractmethod
    def mark_seen(self, fingerprint: str, url: str, published_at: str) -> None:
        """
        Помечает публикацию как обработанную.

        Args:
            fingerprint: Уникальный идентификатор публикации
            url: URL публикации
            published_at: Дата публикации
        """
        pass

    @abstractmethod
    def init(self) -> None:
        """Инициализирует хранилище (создает таблицы и т.д.)."""
        pass
