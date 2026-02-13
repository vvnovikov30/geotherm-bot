"""
Профили регионов для генерации запросов.
"""

from typing import Dict, List

REGION_PROFILES: Dict[str, Dict[str, List[str]]] = {
    "kmv": {
        "geo_anchors_ru": ["Кавказские Минеральные Воды", "КМВ", "Ставропольский край"],
        "resort_anchors_ru": ["Ессентуки", "Кисловодск", "Пятигорск", "Железноводск", "Нарзан"],
        "extra_ru": [
            "Ессентуки №17",
            "Ессентуки №4",
            "нарзанная галерея",
            "радоновые воды",
            "сероводородные воды",
        ],
    },
    "transcaucasia": {
        "geo_anchors_ru": ["Закавказье", "Кавказ"],
        "resort_anchors_ru": ["Боржоми", "Цхалтубо", "Джермук", "Нафталан", "Саирме", "Ахтала"],
        "extra_ru": [
            "минеральные воды Грузии",
            "минеральные воды Армении",
            "санаторно-курортное лечение",
        ],
    },
    "altai": {
        "geo_anchors_ru": ["Алтай", "Алтайский край", "Горный Алтай"],
        "resort_anchors_ru": ["Белокуриха"],
        "extra_ru": ["радоновые воды", "термальные источники", "курорт Белокуриха"],
    },
    "tyumen": {
        "geo_anchors_ru": ["Тюмень", "Тюменская область", "Западная Сибирь"],
        "resort_anchors_ru": ["геотермальные воды", "термальные источники Тюмени"],
        "extra_ru": ["скважина", "температура пласта", "дебит", "геотермальное теплоснабжение"],
    },
    "turkey": {
        "geo_anchors_ru": ["Турция", "Türkiye"],
        "resort_anchors_ru": ["Памуккале", "Ялова", "Афьон", "Кангал", "Денизли"],
        "extra_ru": ["термальные источники", "thermal springs", "balneotherapy"],
    },
    "se_asia": {
        "geo_anchors_ru": ["Юго-Восточная Азия", "ЮВА"],
        "resort_anchors_ru": ["Вьетнам", "Индонезия", "Таиланд", "Филиппины", "Малайзия"],
        "extra_ru": ["hot springs", "thermal springs", "spa"],
    },
}


def get_region_profile(region_key: str) -> Dict[str, List[str]]:
    """
    Получает профиль региона.

    Args:
        region_key: Ключ региона

    Returns:
        Dict с geo_anchors_ru, resort_anchors_ru, extra_ru
        Если профиль не найден, возвращает пустой профиль с geo_anchors=[region_key]
    """
    if region_key in REGION_PROFILES:
        return REGION_PROFILES[region_key]

    # Fallback: пустой профиль
    return {"geo_anchors_ru": [region_key], "resort_anchors_ru": [], "extra_ru": []}
