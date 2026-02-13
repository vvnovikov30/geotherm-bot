"""
Ручной тест для RegionResolver и QueryBuilder (без pytest).
"""

from src.geotherm_bot.app.query_builder import CHEM, SOURCEOBJ, QueryBuilder
from src.geotherm_bot.app.region import RegionResolver


def test_all():
    """Запускает все тесты."""
    resolver = RegionResolver()
    builder = QueryBuilder()

    # Тест 1: известные регионы
    print("Test 1: region_resolver_known")
    assert resolver.infer_region_key("Турция") == "turkey"
    assert resolver.infer_region_key("Регион кавказских минеральных вод") == "kmv"
    assert resolver.infer_region_key("КМВ") == "kmv"
    assert resolver.infer_region_key("Юго-восточная Азия") == "se_asia"
    print("  [OK] PASS")

    # Тест 2: fallback slugify
    print("Test 2: region_resolver_fallback_slugify")
    assert resolver.infer_region_key("Северный Кавказ") == "severny_kavkaz"
    assert resolver.infer_region_key("Курорты СССР") == "kurorty_sssr"
    assert resolver.infer_region_key("  Северный   Кавказ  ") == "severny_kavkaz"
    assert resolver.infer_region_key("Ёлка") == "elka"
    print("  [OK] PASS")

    # Тест 3: QueryBuilder для KMV
    print("Test 3: query_builder_kmv_contains_key_anchors")
    queries = builder.build_backfill_queries("kmv", "КМВ")
    assert len(queries) > 0

    # Проверяем наличие "Ессентуки"
    essentuki_queries = [q for q in queries if "Ессентуки" in q.query]
    assert len(essentuki_queries) > 0

    # Проверяем CHEM маркеры
    chem_queries = [q for q in queries if CHEM in q.query]
    assert len(chem_queries) > 0

    # Проверяем SOURCEOBJ маркеры
    sourceobj_queries = [q for q in queries if SOURCEOBJ in q.query]
    assert len(sourceobj_queries) > 0
    print("  [OK] PASS")

    # Тест 4: ограничения и уникальность
    print("Test 4: query_builder_limits_and_uniqueness")
    queries = builder.build_backfill_queries("kmv", "КМВ")
    assert len(queries) <= 14

    query_strings = [q.query for q in queries]
    assert len(query_strings) == len(set(query_strings))
    print("  [OK] PASS")

    # Тест 5: поля QuerySpec
    print("Test 5: queryspec_fields")
    queries = builder.build_backfill_queries("kmv", "КМВ")
    for q in queries:
        assert q.source == "eurasia_discovery"
        assert q.language_hint == "ru"
        assert "backfill_ru" in q.tags
        assert "kmv" in q.tags
        assert q.max_results == 20
    print("  [OK] PASS")

    # Тест 6: разные регионы
    print("Test 6: query_builder_different_regions")
    regions = ["kmv", "transcaucasia", "altai", "tyumen", "turkey", "se_asia"]
    for region_key in regions:
        queries = builder.build_backfill_queries(region_key, region_key)
        assert len(queries) > 0
        assert len(queries) <= 14
    print("  [OK] PASS")

    # Тест 7: неизвестный регион
    print("Test 7: query_builder_unknown_region")
    queries = builder.build_backfill_queries("unknown_region", "Неизвестный регион")
    assert len(queries) > 0
    assert len(queries) <= 14
    print("  [OK] PASS")

    print("\n[SUCCESS] Все тесты пройдены!")


if __name__ == "__main__":
    test_all()
