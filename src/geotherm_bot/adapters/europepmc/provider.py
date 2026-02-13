"""
Адаптер для Europe PMC REST API.
"""

import logging
import os
from typing import List

import requests

from ...domain.models import Publication, QuerySpec
from ...ports.publications_api import PublicationsAPI

logger = logging.getLogger(__name__)


class EuropePMCProvider(PublicationsAPI):
    """Провайдер публикаций из Europe PMC."""

    def __init__(self, feed_urls: List[str]):
        """
        Инициализирует провайдер.

        Args:
            feed_urls: Список URL для запросов к Europe PMC API
        """
        self.feed_urls = feed_urls

    def fetch(self, query_spec: QuerySpec) -> List[Publication]:
        """
        Получает публикации по QuerySpec.

        Europe PMC использует feed_urls, а не QuerySpec.
        Этот метод не реализован для QuerySpec.

        Args:
            query_spec: Спецификация запроса

        Returns:
            List[Publication]: Пустой список (Europe PMC не поддерживает QuerySpec)

        Raises:
            NotImplementedError: Если EUROPEPMC_ENABLED=true
        """
        # Проверяем флаг окружения
        europepmc_enabled = os.getenv("EUROPEPMC_ENABLED", "").lower() in ("true", "1", "yes")

        if europepmc_enabled:
            # Если флаг включен, бросаем исключение вместо молчаливого пустого списка
            raise NotImplementedError(
                f"EuropePMCProvider.fetch(QuerySpec) is not implemented. "
                f"Europe PMC uses feed_urls, not QuerySpec. "
                f"Query: {query_spec.query}"
            )

        # Иначе логируем warning и возвращаем пустой список
        logger.warning(
            "EuropePMCProvider.fetch is not implemented for QuerySpec; returning empty list. "
            f"Query: {query_spec.query}, Source: {query_spec.source}, QueryName: {query_spec.name}"
        )
        return []

    def fetch_publications(self) -> List[Publication]:
        """
        Получает публикации из Europe PMC API.

        Returns:
            List[Publication]: Список публикаций
        """
        all_publications = []

        for feed_url in self.feed_urls:
            try:
                expected_prefix = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                if not feed_url.startswith(expected_prefix):
                    continue

                response = requests.get(feed_url, timeout=20)
                response.raise_for_status()
                data = response.json()

                results = data.get("resultList", {}).get("result", [])
                result_count = len(results)

                print(f"[Europe PMC] {feed_url}")
                print(f"  Результатов: {result_count}")

                for result in results:
                    publication = self._parse_result(result)
                    if publication:
                        all_publications.append(publication)

            except Exception as e:
                print(f"Ошибка при обработке {feed_url}: {e}")
                continue

        return all_publications

    def _parse_result(self, result: dict) -> Publication:
        """
        Парсит результат из Europe PMC API в Publication.

        Args:
            result: Результат из API

        Returns:
            Publication: Публикация
        """
        # Генерируем ID из pmid или pmcid
        pub_id = result.get("pmid") or result.get("pmcid") or result.get("doi", "")
        if not pub_id:
            # Если нет ID, создаем из заголовка
            import hashlib

            title = result.get("title", "Без заголовка")
            pub_id = hashlib.md5(title.encode("utf-8")).hexdigest()

        title = result.get("title", "Без заголовка")

        # Формируем URL
        url = None
        if result.get("doi"):
            url = f"https://doi.org/{result['doi']}"
        elif result.get("journalUrl"):
            url = result["journalUrl"]
        elif result.get("pmid"):
            url = f"https://europepmc.org/article/MED/{result['pmid']}"
        elif result.get("pmcid"):
            url = f"https://europepmc.org/article/PMC/{result['pmcid']}"

        # Извлекаем дату публикации и год
        published_at = result.get("firstPublicationDate", "")
        year = None
        if published_at:
            try:
                year = int(published_at[:4])
            except (ValueError, IndexError):
                pass

        if not year:
            pub_year = result.get("pubYear")
            if pub_year:
                try:
                    year = int(pub_year)
                except (ValueError, TypeError):
                    pass

        if not published_at and year:
            published_at = str(year)

        # Извлекаем аннотацию
        abstract = result.get("abstractText") or None
        journal = result.get("journalTitle") or None

        # Извлекаем авторов
        authors_str = result.get("authorString") or ""
        authors = []
        if authors_str:
            # Разбиваем строку авторов на список
            authors = [a.strip() for a in authors_str.split(";") if a.strip()]

        # Извлекаем ключевые слова
        keywords = []
        keyword_list = result.get("keywordList", {})
        if keyword_list and isinstance(keyword_list, dict):
            keyword_values = keyword_list.get("keyword", [])
            if keyword_values:
                if isinstance(keyword_values, list):
                    keywords = [str(kw) for kw in keyword_values]
                else:
                    keywords = [str(keyword_values)]

        # Извлекаем pub_types
        pub_types = []
        pub_type_list = result.get("pubTypeList")
        if pub_type_list and isinstance(pub_type_list, dict):
            pub_type_value = pub_type_list.get("pubType")
            if pub_type_value:
                if isinstance(pub_type_value, list):
                    pub_types = pub_type_value
                else:
                    pub_types = [pub_type_value]

        if not pub_types:
            pub_type = result.get("pubType")
            if pub_type:
                if isinstance(pub_type, list):
                    pub_types = pub_type
                else:
                    pub_types = [pub_type]

        pub_types = [str(pt) for pt in pub_types] if pub_types else []

        return Publication(
            id=str(pub_id),
            source="Europe PMC",
            title=title,
            abstract=abstract,
            url=url,
            year=year,
            authors=authors,
            journal=journal,
            keywords=keywords,
            raw=result,
            published_at=published_at,
            pub_types=pub_types,
        )
