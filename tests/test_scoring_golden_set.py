"""
Golden set тесты для scoring.

Проверяет, что scoring корректно обрабатывает набор репрезентативных публикаций
из fixtures, разделенных на accept, reject и borderline категории.
"""

import json
from pathlib import Path

from src.geotherm_bot.domain.models import Publication
from src.geotherm_bot.domain.scoring import score_publication


def load_fixtures() -> dict[str, list[dict]]:
    """
    Загружает все JSON-фикстуры из tests/fixtures/scoring/.

    Returns:
        dict: {
            "accept": [publication_dict, ...],
            "reject": [publication_dict, ...],
            "borderline": [publication_dict, ...]
        }
    """
    fixtures_dir = Path(__file__).parent / "fixtures" / "scoring"
    fixtures = {"accept": [], "reject": [], "borderline": []}

    for json_file in sorted(fixtures_dir.glob("*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Определяем категорию по имени файла
        if json_file.name.startswith("accept_"):
            fixtures["accept"].append(data)
        elif json_file.name.startswith("reject_"):
            fixtures["reject"].append(data)
        elif json_file.name.startswith("borderline_"):
            fixtures["borderline"].append(data)

    return fixtures


def publication_from_dict(data: dict) -> Publication:
    """Создает Publication из словаря."""
    return Publication(
        id=data["id"],
        source=data["source"],
        title=data["title"],
        abstract=data.get("abstract"),
        pub_types=data.get("pub_types", []),
        year=data.get("year"),
    )


class TestGoldenSetAccept:
    """Тесты для accept-фикстур: должны иметь score >= 5."""

    def test_all_accept_fixtures_above_threshold(self):
        """Все accept-фикстуры должны иметь score >= 5."""
        fixtures = load_fixtures()
        failures = []

        for pub_data in fixtures["accept"]:
            publication = publication_from_dict(pub_data)
            result = score_publication(publication)

            if result.score < 5:
                failures.append(
                    f"{pub_data['id']} ({pub_data['title'][:50]}...): "
                    f"score={result.score} < 5, reasons={result.reasons}"
                )

        assert len(failures) == 0, (
            f"Found {len(failures)} accept fixtures below threshold:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )


class TestGoldenSetReject:
    """Тесты для reject-фикстур: должны иметь score < 5."""

    def test_all_reject_fixtures_below_threshold(self):
        """Все reject-фикстуры должны иметь score < 5."""
        fixtures = load_fixtures()
        failures = []

        for pub_data in fixtures["reject"]:
            publication = publication_from_dict(pub_data)
            result = score_publication(publication)

            if result.score >= 5:
                failures.append(
                    f"{pub_data['id']} ({pub_data['title'][:50]}...): "
                    f"score={result.score} >= 5, reasons={result.reasons}"
                )

        assert len(failures) == 0, (
            f"Found {len(failures)} reject fixtures above threshold:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )


class TestGoldenSetBorderline:
    """Тесты для borderline-фикстур: score в разумном диапазоне, детерминированно."""

    def test_borderline_fixtures_reasonable_range(self):
        """Borderline-фикстуры должны иметь score в диапазоне -5..20."""
        fixtures = load_fixtures()
        failures = []

        for pub_data in fixtures["borderline"]:
            publication = publication_from_dict(pub_data)
            result = score_publication(publication)

            if not (-5 <= result.score <= 20):
                failures.append(
                    f"{pub_data['id']} ({pub_data['title'][:50]}...): "
                    f"score={result.score} not in range [-5, 20]"
                )

        assert len(failures) == 0, (
            f"Found {len(failures)} borderline fixtures outside reasonable range:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    def test_borderline_fixtures_deterministic(self):
        """Borderline-фикстуры должны давать детерминированный результат."""
        fixtures = load_fixtures()
        failures = []

        for pub_data in fixtures["borderline"]:
            publication1 = publication_from_dict(pub_data)
            publication2 = publication_from_dict(pub_data)

            result1 = score_publication(publication1)
            result2 = score_publication(publication2)

            if result1.score != result2.score or result1.reasons != result2.reasons:
                failures.append(
                    f"{pub_data['id']}: non-deterministic results - "
                    f"first: score={result1.score}, second: score={result2.score}"
                )

        assert len(failures) == 0, (
            f"Found {len(failures)} borderline fixtures with non-deterministic results:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    def test_borderline_fixtures_no_exception(self):
        """Borderline-фикстуры не должны вызывать исключений."""
        fixtures = load_fixtures()

        for pub_data in fixtures["borderline"]:
            publication = publication_from_dict(pub_data)
            # Не должно быть исключения
            result = score_publication(publication)

            assert isinstance(result.score, int)
            assert isinstance(result.reasons, list)
            assert isinstance(result.is_high_priority, bool)


class TestGoldenSetRelativeOrder:
    """Тесты на относительный порядок: клинический + химия >= только гео."""

    def test_clinical_chemistry_vs_geo_only(self):
        """
        Публикация с клиническим аспектом + химией должна иметь
        score >= публикации только с гео (без клиники/химии).
        """
        fixtures = load_fixtures()

        # Находим accept-фикстуру с клиническим аспектом + химией
        clinical_chemistry = None
        for pub_data in fixtures["accept"]:
            title_lower = pub_data["title"].lower()
            abstract_lower = (pub_data.get("abstract") or "").lower()
            text = f"{title_lower} {abstract_lower}"

            has_clinical = (
                "clinical" in text
                or "trial" in text
                or "randomized" in text
                or "balneotherapy" in text
            )
            has_chemistry = (
                "chemical" in text
                or "composition" in text
                or "mineral" in text
                or "geochemical" in text
            )

            if has_clinical and has_chemistry:
                clinical_chemistry = publication_from_dict(pub_data)
                break

        # Находим accept-фикстуру только с гео (без явной клиники/химии)
        geo_only = None
        for pub_data in fixtures["accept"]:
            title_lower = pub_data["title"].lower()
            abstract_lower = (pub_data.get("abstract") or "").lower()
            text = f"{title_lower} {abstract_lower}"

            has_geo = (
                "geothermal" in text or "thermal" in text or "spring" in text or "region" in text
            )
            has_clinical = (
                "clinical" in text
                or "trial" in text
                or "randomized" in text
                or "balneotherapy" in text
            )
            has_chemistry = (
                "chemical" in text
                or "composition" in text
                or "mineral" in text
                or "geochemical" in text
            )

            if has_geo and not has_clinical and not has_chemistry:
                geo_only = publication_from_dict(pub_data)
                break

        # Если нашли обе, проверяем относительный порядок
        if clinical_chemistry is not None and geo_only is not None:
            clinical_score = score_publication(clinical_chemistry).score
            geo_score = score_publication(geo_only).score

            assert clinical_score >= geo_score, (
                f"Clinical+chemistry score ({clinical_score}) should be >= "
                f"geo-only score ({geo_score})"
            )
