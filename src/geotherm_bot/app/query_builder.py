"""
Построитель запросов для backfill.
"""

from typing import List

from ..domain.models import QuerySpec
from .region_profiles import get_region_profile

# Базовые маркеры для запросов
# Базовые маркеры для запросов (длинные строки по смыслу)
CHEM = (  # noqa: E501
    '("химическ* состав" OR минерализац* OR "ионный состав" OR pH OR дебит OR '
    'температура OR радон OR "сероводород" OR CO2 OR углекисл*)'
)
CLIN = (  # noqa: E501
    '("питьевое лечение" OR "внутреннее применение" OR бальнеотерап* OR '
    'курортолог* OR "санаторно-курортн*" OR показани* OR противопоказани*)'
)
SOURCEOBJ = (  # noqa: E501
    '(источник* OR скважин* OR каптаж OR галерея OR "паспорт источника" OR '
    '"режим эксплуатации" OR "санитарная охрана")'
)
DOC = (  # noqa: E501
    '("методические указания" OR "клинические наблюдения" OR диссертац* OR '
    'автореферат OR "гидрогеологическ* отчет" OR "паспорт скважины")'
)


class QueryBuilder:
    """Построитель запросов для backfill."""

    def build_backfill_queries(self, region_key: str, topic_name: str) -> List[QuerySpec]:
        """
        Строит список QuerySpec для backfill региона.

        Args:
            region_key: Ключ региона
            topic_name: Название топика (для человекочитаемых имен)

        Returns:
            List[QuerySpec]: Список запросов (10-14 максимум)
        """
        profile = get_region_profile(region_key)

        geo_anchors = profile.get("geo_anchors_ru", [])[:2]  # Ограничиваем до первых 2
        resort_anchors = profile.get("resort_anchors_ru", [])

        queries = []
        seen_queries = set()  # Для дедупликации

        # 1) Для каждого resort_anchor: CHEM запросы
        for resort in resort_anchors:
            if len(geo_anchors) > 0:
                query_str = f'("{resort}" OR "{geo_anchors[0]}") AND {CHEM}'
            else:
                query_str = f'"{resort}" AND {CHEM}'

            if query_str not in seen_queries:
                seen_queries.add(query_str)
                queries.append(
                    QuerySpec(
                        source="eurasia_discovery",
                        name=f"{self._format_name(region_key)} {resort} chemistry",
                        query=query_str,
                        language_hint="ru",
                        tags=["backfill_ru", region_key],
                        max_results=20,
                    )
                )

        # 2) Для каждого resort_anchor: SOURCEOBJ запросы
        for resort in resort_anchors:
            if len(geo_anchors) > 0:
                query_str = f'("{resort}" OR "{geo_anchors[0]}") AND {SOURCEOBJ}'
            else:
                query_str = f'"{resort}" AND {SOURCEOBJ}'

            if query_str not in seen_queries:
                seen_queries.add(query_str)
                queries.append(
                    QuerySpec(
                        source="eurasia_discovery",
                        name=f"{self._format_name(region_key)} {resort} wells",
                        query=query_str,
                        language_hint="ru",
                        tags=["backfill_ru", region_key],
                        max_results=20,
                    )
                )

        # 3) Общие запросы: CHEM + CLIN
        if len(geo_anchors) >= 2:
            query_str = f'("{geo_anchors[0]}" OR "{geo_anchors[1]}") AND {CHEM} AND {CLIN}'
        elif len(geo_anchors) == 1:
            query_str = f'"{geo_anchors[0]}" AND {CHEM} AND {CLIN}'
        else:
            query_str = f'"{topic_name}" AND {CHEM} AND {CLIN}'

        if query_str not in seen_queries:
            seen_queries.add(query_str)
            queries.append(
                QuerySpec(
                    source="eurasia_discovery",
                    name=f"{self._format_name(region_key)} chemistry + clinical",
                    query=query_str,
                    language_hint="ru",
                    tags=["backfill_ru", region_key],
                    max_results=20,
                )
            )

        # Еще один общий запрос
        if len(geo_anchors) >= 1:
            query_str = f'"{geo_anchors[0]}" AND {CHEM}'
            if query_str not in seen_queries:
                seen_queries.add(query_str)
                queries.append(
                    QuerySpec(
                        source="eurasia_discovery",
                        name=f"{self._format_name(region_key)} chemistry",
                        query=query_str,
                        language_hint="ru",
                        tags=["backfill_ru", region_key],
                        max_results=20,
                    )
                )

        # 4) DOC запросы (2 штуки)
        if len(geo_anchors) >= 1:
            query_str = f'"{geo_anchors[0]}" AND {DOC} AND {SOURCEOBJ}'
            if query_str not in seen_queries:
                seen_queries.add(query_str)
                queries.append(
                    QuerySpec(
                        source="eurasia_discovery",
                        name=f"{self._format_name(region_key)} documents",
                        query=query_str,
                        language_hint="ru",
                        tags=["backfill_ru", region_key],
                        max_results=20,
                    )
                )

        if len(geo_anchors) >= 1:
            query_str = f'"{geo_anchors[0]}" AND {DOC}'
            if query_str not in seen_queries:
                seen_queries.add(query_str)
                queries.append(
                    QuerySpec(
                        source="eurasia_discovery",
                        name=f"{self._format_name(region_key)} documents only",
                        query=query_str,
                        language_hint="ru",
                        tags=["backfill_ru", region_key],
                        max_results=20,
                    )
                )

        # Ограничиваем до 14 запросов максимум
        return queries[:14]

    @staticmethod
    def _format_name(region_key: str) -> str:
        """
        Форматирует region_key в человекочитаемое имя для QuerySpec.name.

        Args:
            region_key: Ключ региона

        Returns:
            str: Форматированное имя
        """
        name_map = {
            "kmv": "KMW",
            "transcaucasia": "Transcaucasia",
            "altai": "Altai",
            "tyumen": "Tyumen",
            "turkey": "Turkey",
            "se_asia": "SE Asia",
        }
        return name_map.get(region_key, region_key.upper())
