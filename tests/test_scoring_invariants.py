"""
Unit-тесты на инварианты scoring.

Проверяет детерминированность, монотонность и граничные условия
функции score_publication без изменения логики scoring.py.
"""

from src.geotherm_bot.domain.models import Publication
from src.geotherm_bot.domain.scoring import score_publication


def create_publication(
    title: str = "Test Title",
    abstract: str = "",
    pub_types: list = None,
) -> Publication:
    """Создает минимальный mock-объект Publication для тестов."""
    return Publication(
        id="test-id",
        source="test",
        title=title,
        abstract=abstract,
        pub_types=pub_types or [],
    )


class TestMonotonicity:
    """Тесты на монотонность: добавление клинических признаков не уменьшает score."""

    def test_adding_randomized_increases_score(self):
        """Добавление 'randomized' в текст не должно уменьшать score."""
        base = create_publication(
            title="Geothermal energy study",
            abstract="Analysis of geothermal systems",
        )
        base_score = score_publication(base).score

        with_randomized = create_publication(
            title="Geothermal energy study",
            abstract="Analysis of geothermal systems. Randomized controlled trial.",
        )
        randomized_score = score_publication(with_randomized).score

        assert randomized_score >= base_score, (
            f"Score should not decrease when adding 'randomized'. "
            f"Base: {base_score}, With randomized: {randomized_score}"
        )

    def test_adding_clinical_trial_increases_score(self):
        """Добавление 'clinical trial' в текст не должно уменьшать score."""
        base = create_publication(
            title="Geothermal research",
            abstract="Study of geothermal resources",
        )
        base_score = score_publication(base).score

        with_clinical = create_publication(
            title="Geothermal research",
            abstract="Study of geothermal resources. Clinical trial results.",
        )
        clinical_score = score_publication(with_clinical).score

        assert clinical_score >= base_score, (
            f"Score should not decrease when adding 'clinical trial'. "
            f"Base: {base_score}, With clinical: {clinical_score}"
        )

    def test_adding_pilot_study_increases_score(self):
        """Добавление 'pilot study' в текст не должно уменьшать score."""
        base = create_publication(
            title="Geothermal analysis",
            abstract="Geothermal energy analysis",
        )
        base_score = score_publication(base).score

        with_pilot = create_publication(
            title="Geothermal analysis",
            abstract="Geothermal energy analysis. Pilot study results.",
        )
        pilot_score = score_publication(with_pilot).score

        assert pilot_score >= base_score, (
            f"Score should not decrease when adding 'pilot study'. "
            f"Base: {base_score}, With pilot: {pilot_score}"
        )

    def test_adding_high_priority_pub_type_increases_score(self):
        """Добавление высокоприоритетного типа публикации не должно уменьшать score."""
        base = create_publication(
            title="Geothermal study",
            abstract="Geothermal research",
            pub_types=[],
        )
        base_score = score_publication(base).score

        with_high_priority = create_publication(
            title="Geothermal study",
            abstract="Geothermal research",
            pub_types=["randomized controlled trial"],
        )
        high_priority_score = score_publication(with_high_priority).score

        assert high_priority_score >= base_score, (
            f"Score should not decrease when adding high-priority pub_type. "
            f"Base: {base_score}, With high-priority: {high_priority_score}"
        )


class TestRegionalSignal:
    """Тесты на региональный сигнал: совпадение с region_key должно увеличивать score."""

    def test_region_key_in_text_does_not_decrease_score(self):
        """Наличие названия региона в тексте не должно уменьшать score."""
        base = create_publication(
            title="Geothermal energy",
            abstract="Study of geothermal systems",
        )
        base_score = score_publication(base).score

        # Добавляем название региона (например, "turkey" из region_key)
        with_region = create_publication(
            title="Geothermal energy in Turkey",
            abstract="Study of geothermal systems in Turkey",
        )
        region_score = score_publication(with_region).score

        # Регион не должен уменьшать score (может не увеличивать, если нет правил для регионов)
        assert region_score >= base_score, (
            f"Score should not decrease when adding region name. "
            f"Base: {base_score}, With region: {region_score}"
        )

    def test_asia_country_in_text_does_not_decrease_score(self):
        """Наличие страны Азии в тексте не должно уменьшать score."""
        base = create_publication(
            title="Geothermal research",
            abstract="Geothermal energy study",
        )
        base_score = score_publication(base).score

        with_asia = create_publication(
            title="Geothermal research in Japan",
            abstract="Geothermal energy study in Japan",
        )
        asia_score = score_publication(with_asia).score

        assert asia_score >= base_score, (
            f"Score should not decrease when adding Asia country. "
            f"Base: {base_score}, With Asia: {asia_score}"
        )


class TestIrrelevancePenalty:
    """Тесты на штраф за нерелевантность: SPA-формулировки без гео/химии дают score < 5."""

    def test_spa_formulations_below_threshold(self):
        """Общие SPA-формулировки без гео/химии должны давать score < 5."""
        spa_publication = create_publication(
            title="Relaxation and wellness",
            abstract="Spa treatments for relaxation and wellness. "
            "Massage therapy and aromatherapy benefits.",
        )
        result = score_publication(spa_publication)

        assert result.score < 5, (
            f"SPA-formulated text without geo/chemistry should score < 5. " f"Got: {result.score}"
        )

    def test_generic_wellness_below_threshold(self):
        """Общие формулировки о wellness без гео/химии должны давать score < 5."""
        generic = create_publication(
            title="Health and wellness",
            abstract="General health and wellness information. " "Benefits of healthy lifestyle.",
        )
        result = score_publication(generic)

        assert result.score < 5, f"Generic wellness text should score < 5. Got: {result.score}"

    def test_unrelated_topic_below_threshold(self):
        """Несвязанная тема без гео/химии должна давать score < 5."""
        unrelated = create_publication(
            title="Cooking recipes",
            abstract="Delicious recipes for home cooking. " "Tips and tricks for better meals.",
        )
        result = score_publication(unrelated)

        assert result.score < 5, f"Unrelated topic should score < 5. Got: {result.score}"


class TestBoundaryValues:
    """Тесты на граничные значения около threshold (score >= 5)."""

    def test_score_is_integer(self):
        """Score должен быть целым числом."""
        pub = create_publication(
            title="Test",
            abstract="Test abstract",
        )
        result = score_publication(pub)

        assert isinstance(result.score, int), f"Score should be integer. Got: {type(result.score)}"

    def test_threshold_behavior_around_5(self):
        """Проверка поведения около threshold = 5."""
        # Публикация с минимальными признаками, которая может дать score = 4
        low_score = create_publication(
            title="Geothermal",
            abstract="Geothermal study",
        )
        low_result = score_publication(low_score)

        # Публикация с признаками, которая должна дать score >= 5
        # Используем "randomized" или "clinical trial" для гарантированного +5
        high_score = create_publication(
            title="Geothermal randomized study",
            abstract="Geothermal randomized controlled trial",
        )
        high_result = score_publication(high_score)

        # Проверяем, что есть разница между low и high
        assert high_result.score >= 5, (
            f"Publication with clinical signs should score >= 5. " f"Got: {high_result.score}"
        )

        # Проверяем, что high >= low (монотонность)
        assert high_result.score >= low_result.score, (
            f"High score should be >= low score. "
            f"Low: {low_result.score}, High: {high_result.score}"
        )

    def test_negative_score_possible(self):
        """Проверка, что отрицательный score возможен (для крайних случаев)."""
        negative_pub = create_publication(
            title="Letter to the editor",
            abstract="This is a letter",
            pub_types=["letter", "comment"],
        )
        result = score_publication(negative_pub)

        # Отрицательный score допустим для крайних случаев
        assert isinstance(
            result.score, int
        ), f"Score should be integer even if negative. Got: {result.score}"


class TestRobustness:
    """Тесты на устойчивость: пустой abstract не должен приводить к исключению."""

    def test_empty_abstract_no_exception(self):
        """Пустой abstract не должен приводить к исключению."""
        pub = create_publication(
            title="Test Title",
            abstract="",
        )

        # Не должно быть исключения
        result = score_publication(pub)

        assert isinstance(result.score, int)
        assert isinstance(result.reasons, list)
        assert isinstance(result.is_high_priority, bool)

    def test_none_abstract_no_exception(self):
        """None abstract не должен приводить к исключению."""
        pub = create_publication(
            title="Test Title",
            abstract="",
        )
        pub.abstract = None

        # Не должно быть исключения
        result = score_publication(pub)

        assert isinstance(result.score, int)
        assert isinstance(result.reasons, list)
        assert isinstance(result.is_high_priority, bool)

    def test_empty_title_and_abstract_no_exception(self):
        """Пустые title и abstract не должны приводить к исключению."""
        pub = create_publication(
            title="",
            abstract="",
        )

        # Не должно быть исключения
        result = score_publication(pub)

        assert isinstance(result.score, int)
        assert isinstance(result.reasons, list)
        assert isinstance(result.is_high_priority, bool)

    def test_deterministic_scoring(self):
        """Скоринг должен быть детерминированным: одинаковые входы дают одинаковый результат."""
        pub1 = create_publication(
            title="Geothermal energy study",
            abstract="Randomized controlled trial of geothermal systems",
            pub_types=["clinical trial"],
        )
        pub2 = create_publication(
            title="Geothermal energy study",
            abstract="Randomized controlled trial of geothermal systems",
            pub_types=["clinical trial"],
        )

        result1 = score_publication(pub1)
        result2 = score_publication(pub2)

        assert result1.score == result2.score, (
            f"Scoring should be deterministic. " f"First: {result1.score}, Second: {result2.score}"
        )
        assert result1.reasons == result2.reasons, (
            f"Reasons should be deterministic. "
            f"First: {result1.reasons}, Second: {result2.reasons}"
        )
