"""
Тесты для RegionResolver и QueryBuilder.
"""

import pytest

from src.geotherm_bot.app.query_builder import CHEM, SOURCEOBJ, QueryBuilder
from src.geotherm_bot.app.region import RegionResolver


@pytest.fixture
def region_resolver():
    """Создает RegionResolver."""
    return RegionResolver()


@pytest.fixture
def query_builder():
    """Создает QueryBuilder."""
    return QueryBuilder()


def test_region_resolver_known(region_resolver):
    """Тест: RegionResolver распознает известные регионы."""
    assert region_resolver.infer_region_key("Турция") == "turkey"
    assert region_resolver.infer_region_key("Регион кавказских минеральных вод") == "kmv"
    assert region_resolver.infer_region_key("КМВ") == "kmv"
    assert region_resolver.infer_region_key("Юго-восточная Азия") == "se_asia"
    assert region_resolver.infer_region_key("Закавказье") == "transcaucasia"
    assert region_resolver.infer_region_key("Алтай") == "altai"
    assert region_resolver.infer_region_key("Тюмень") == "tyumen"


def test_region_resolver_fallback_slugify(region_resolver):
    """Тест: RegionResolver использует slugify для неизвестных регионов."""
    assert region_resolver.infer_region_key("Северный Кавказ") == "severny_kavkaz"
    assert region_resolver.infer_region_key("Курорты СССР") == "kurorty_sssr"

    # Проверяем нормализацию (пробелы по краям)
    assert region_resolver.infer_region_key("  Северный   Кавказ  ") == "severny_kavkaz"

    # Проверяем замену ё
    assert region_resolver.infer_region_key("Ёлка") == "elka"


def test_region_resolver_normalize(region_resolver):
    """Тест: нормализация названий."""
    assert region_resolver.normalize_topic_name("  ТУРЦИЯ  ") == "турция"
    assert region_resolver.normalize_topic_name("Ёлка") == "елка"
    assert region_resolver.normalize_topic_name("Кавказ") == "кавказ"


def test_region_resolver_slugify(region_resolver):
    """Тест: slugify преобразование."""
    assert region_resolver.slugify("Северный Кавказ") == "severny_kavkaz"
    assert region_resolver.slugify("Курорты СССР") == "kurorty_sssr"
    assert region_resolver.slugify("тест  --  строка") == "test_stroka"
    assert region_resolver.slugify("двойные___подчеркивания") == "dvoinye_podcherkivaniya"


def test_query_builder_kmv_contains_key_anchors(query_builder):
    """Тест: QueryBuilder для KMV содержит ключевые якоря."""
    queries = query_builder.build_backfill_queries("kmv", "КМВ")

    assert len(queries) > 0

    # Проверяем, что есть запросы с "Ессентуки"
    essentuki_queries = [q for q in queries if "Ессентуки" in q.query]
    assert len(essentuki_queries) > 0

    # Проверяем, что есть запросы с CHEM маркерами
    chem_queries = [q for q in queries if CHEM in q.query]
    assert len(chem_queries) > 0

    # Проверяем, что есть запросы с SOURCEOBJ маркерами
    sourceobj_queries = [q for q in queries if SOURCEOBJ in q.query]
    assert len(sourceobj_queries) > 0


def test_query_builder_limits_and_uniqueness(query_builder):
    """Тест: QueryBuilder ограничивает количество и обеспечивает уникальность."""
    queries = query_builder.build_backfill_queries("kmv", "КМВ")

    # Проверяем ограничение до 14
    assert len(queries) <= 14

    # Проверяем уникальность query строк
    query_strings = [q.query for q in queries]
    assert len(query_strings) == len(set(query_strings))


def test_queryspec_fields(query_builder):
    """Тест: QuerySpec содержит правильные поля."""
    queries = query_builder.build_backfill_queries("kmv", "КМВ")

    assert len(queries) > 0

    for q in queries:
        assert q.source == "eurasia_discovery"
        assert q.language_hint == "ru"
        assert "backfill_ru" in q.tags
        assert "kmv" in q.tags
        assert q.max_results == 20
        assert q.name is not None
        assert len(q.name) > 0
        assert len(q.query) > 0


def test_query_builder_different_regions(query_builder):
    """Тест: QueryBuilder работает для разных регионов."""
    regions = ["kmv", "transcaucasia", "altai", "tyumen", "turkey", "se_asia"]

    for region_key in regions:
        queries = query_builder.build_backfill_queries(region_key, region_key)
        assert len(queries) > 0
        assert len(queries) <= 14

        # Проверяем, что все запросы имеют правильный region_key в tags
        for q in queries:
            assert region_key in q.tags


def test_query_builder_unknown_region(query_builder):
    """Тест: QueryBuilder работает для неизвестного региона."""
    queries = query_builder.build_backfill_queries("unknown_region", "Неизвестный регион")

    # Должен вернуть хотя бы несколько запросов (fallback профиль)
    assert len(queries) > 0
    assert len(queries) <= 14

    # Проверяем поля
    for q in queries:
        assert q.source == "eurasia_discovery"
        assert "unknown_region" in q.tags


def test_query_builder_resort_queries(query_builder):
    """Тест: QueryBuilder создает запросы для курортов."""
    queries = query_builder.build_backfill_queries("transcaucasia", "Закавказье")

    # Проверяем, что есть запросы с курортами из профиля
    resort_names = ["Боржоми", "Цхалтубо", "Джермук"]
    found_resorts = []
    for q in queries:
        for resort in resort_names:
            if resort in q.query:
                found_resorts.append(resort)
                break

    # Должен быть хотя бы один запрос с курортом
    assert len(found_resorts) > 0


def test_query_builder_doc_queries(query_builder):
    """Тест: QueryBuilder создает DOC запросы."""
    queries = query_builder.build_backfill_queries("kmv", "КМВ")

    # Проверяем наличие DOC маркеров
    doc_queries = [
        q for q in queries if "методические указания" in q.query or "диссертац*" in q.query
    ]
    assert len(doc_queries) > 0
