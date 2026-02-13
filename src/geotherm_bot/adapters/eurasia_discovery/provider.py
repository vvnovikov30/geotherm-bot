"""
Провайдер для поиска публикаций на сайтах Евразии.
Генерирует QuerySpec, создает ссылки для проверки, сохраняет результаты как Publication.
"""

from typing import List

from ...domain.models import Publication, QuerySpec
from ...ports.publications_api import PublicationsAPI
from .queries import generate_queries


class EurasiaDiscoveryProvider(PublicationsAPI):
    """
    Провайдер для поиска публикаций на сайтах Евразии.

    Это не полноценный API провайдер, а модуль, который:
    1. Генерирует QuerySpec и ссылки для проверки на сайтах
    2. Сохраняет results как Publication-like записи
    3. Позволяет скорить и отправлять в Telegram
    """

    def __init__(self):
        """Инициализирует провайдер."""
        self.queries = generate_queries()

    def fetch(self, query_spec: QuerySpec) -> List[Publication]:
        """
        Получает публикации по QuerySpec.

        Args:
            query_spec: Спецификация запроса

        Returns:
            List[Publication]: Список публикаций
        """
        # В текущей реализации генерирует ссылки для ручной проверки
        # В будущем здесь может быть автоматический парсинг результатов
        self._generate_check_links(query_spec)

        # TODO: Здесь может быть автоматический парсинг результатов
        # Пока возвращаем пустой список, так как требуется ручная проверка
        return []

    def fetch_publications(self) -> List[Publication]:
        """
        Получает публикации из сайтов Евразии (legacy метод).

        Returns:
            List[Publication]: Список публикаций (пока пустой, требует ручной проверки)
        """
        publications = []

        for query_spec in self.queries:
            # Генерируем ссылки для проверки на различных сайтах
            links = self._generate_check_links(query_spec)

            print(f"[Eurasia Discovery] {query_spec.name}")
            print(f"  Query: {query_spec.query}")
            print(f"  EastView: {links['eastview']}")
            print(f"  CyberLeninka: {links['cyberleninka']}")
            print(f"  eLIBRARY: {links['elibrary']}")
            print(f"  VINITI: {links['viniti']}")

            # TODO: Здесь может быть автоматический парсинг результатов
            # Пока возвращаем пустой список, так как требуется ручная проверка

        return publications

    def _generate_check_links(self, query_spec: QuerySpec) -> dict:
        """
        Генерирует ссылки для проверки на различных сайтах.

        Args:
            query_spec: Спецификация запроса

        Returns:
            dict: Словарь с ссылками для каждого сайта
        """
        import urllib.parse

        encoded_query = urllib.parse.quote(query_spec.query)

        links = {
            "eastview": f"https://eastview.com/search?q={encoded_query}",
            "cyberleninka": f"https://cyberleninka.ru/search?q={encoded_query}",
            "elibrary": (
                f"https://elibrary.ru/querybox.asp?" f"scope=newquery&querytext={encoded_query}"
            ),
            "viniti": f"https://www.viniti.ru/search?q={encoded_query}",
        }

        return links

    def create_publication_from_result(
        self,
        id: str,
        source: str,
        title: str,
        abstract: str = None,
        url: str = None,
        year: int = None,
        authors: List[str] = None,
        journal: str = None,
        keywords: List[str] = None,
        raw: dict = None,
    ) -> Publication:
        """
        Создает Publication из результата поиска.

        Args:
            id: Уникальный идентификатор публикации
            source: Источник (EastView, CyberLeninka, etc.)
            title: Заголовок публикации
            abstract: Аннотация
            url: URL публикации
            year: Год публикации
            authors: Список авторов
            journal: Название журнала
            keywords: Ключевые слова
            raw: Сырые данные из источника

        Returns:
            Publication: Публикация
        """
        return Publication(
            id=id,
            source=source,
            title=title,
            abstract=abstract,
            url=url,
            year=year,
            authors=authors or [],
            journal=journal,
            keywords=keywords or [],
            raw=raw or {},
        )
