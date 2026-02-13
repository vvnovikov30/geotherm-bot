"""
Генерация запросов для поиска публикаций на сайтах Евразии.
"""
from typing import List

from ...domain.models import QuerySpec


def generate_queries() -> List[QuerySpec]:
    """
    Генерирует список QuerySpec для поиска публикаций.
    
    Returns:
        List[QuerySpec]: Список спецификаций запросов
    """
    queries = [
        QuerySpec(
            source="eurasia",
            name="Минеральная вода и бальнеотерапия",
            query="минеральная вода бальнеотерапия",
            language_hint="ru",
            tags=["mineral_water", "balneotherapy"],
            max_results=50
        ),
        QuerySpec(
            source="eurasia",
            name="Термальная вода и курортное лечение",
            query="термальная вода курортное лечение",
            language_hint="ru",
            tags=["thermal_water", "spa"],
            max_results=50
        ),
        QuerySpec(
            source="eurasia",
            name="Гидротерапия и спа терапия",
            query="гидротерапия спа терапия",
            language_hint="ru",
            tags=["hydrotherapy", "spa_therapy"],
            max_results=50
        ),
        QuerySpec(
            source="eurasia",
            name="Бикарбонатная и сульфатная вода",
            query="бикарбонатная вода сульфатная вода",
            language_hint="ru",
            tags=["bicarbonate", "sulfate"],
            max_results=50
        ),
    ]
    
    return queries
