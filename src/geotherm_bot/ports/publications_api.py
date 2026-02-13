"""
Интерфейс для получения публикаций из различных источников.
"""
from abc import ABC, abstractmethod
from typing import List

from ..domain.models import Publication, QuerySpec


class PublicationsAPI(ABC):
    """Абстрактный интерфейс для получения публикаций."""
    
    @abstractmethod
    def fetch(self, query_spec: QuerySpec) -> List[Publication]:
        """
        Получает список публикаций по QuerySpec.
        
        Args:
            query_spec: Спецификация запроса
        
        Returns:
            List[Publication]: Список публикаций
        """
        pass
    
    @abstractmethod
    def fetch_publications(self) -> List[Publication]:
        """
        Получает список публикаций из источника (legacy метод).
        
        Returns:
            List[Publication]: Список публикаций
        """
        pass
