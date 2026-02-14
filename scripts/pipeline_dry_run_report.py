#!/usr/bin/env python3
"""
Offline pipeline dry-run report для проверки связки filtering + scoring + enqueue.

Проверяет полный пайплайн без подключения scheduler/telegram.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Добавляем корень проекта в sys.path для импортов
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from src.geotherm_bot.domain.filtering import is_fresh, is_relevant  # noqa: E402
from src.geotherm_bot.domain.models import Publication  # noqa: E402
from src.geotherm_bot.domain.scoring import score_publication  # noqa: E402

THRESHOLD = 5
# Используем большой max_age_days для dry-run, чтобы не фильтровать по свежести
MAX_AGE_DAYS = 2000

# Детерминированные термины для filtering
INCLUDE_TERMS = [
    "geothermal",
    "thermal",
    "spring",
    "mineral",
    "balneotherapy",
    "spa",
    "wellness",
    "resort",
    "geochemical",
    "chemistry",
]
EXCLUDE_TERMS = ["сточные", "wastewater"]


def load_fixture_file(filepath: Path) -> Tuple[str, dict, str]:
    """
    Загружает фикстуру из файла и определяет её класс.

    Args:
        filepath: Путь к JSON-файлу фикстуры

    Returns:
        Tuple[filename, data, label]: имя файла, данные, метка
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    filename = filepath.name
    if filename.startswith("accept_"):
        label = "accept"
    elif filename.startswith("reject_"):
        label = "reject"
    elif filename.startswith("borderline_"):
        label = "borderline"
    else:
        label = "unknown"

    return filename, data, label


def publication_from_dict(data: dict) -> Publication:
    """Создает Publication из словаря, добавляя published_at если есть year."""
    # Создаем published_at из year если его нет
    published_at = data.get("published_at")
    if not published_at and data.get("year"):
        year = data["year"]
        published_at = f"{year}-01-01"

    return Publication(
        id=data["id"],
        source=data["source"],
        title=data["title"],
        abstract=data.get("abstract"),
        pub_types=data.get("pub_types", []),
        year=data.get("year"),
        published_at=published_at,
    )


def apply_filtering(publication: Publication) -> Tuple[bool, str]:
    """
    Применяет filtering к публикации.

    Returns:
        Tuple[passed, reason]: прошла ли фильтрацию и причина
    """
    # Проверка релевантности
    if not is_relevant(publication, INCLUDE_TERMS, EXCLUDE_TERMS):
        return False, "not_relevant"

    # Проверка свежести
    if not is_fresh(publication, MAX_AGE_DAYS):
        return False, "not_fresh"

    return True, "passed"


def process_pipeline(results: List[Dict]) -> Dict:
    """
    Обрабатывает публикации через пайплайн: filtering -> scoring -> threshold.

    Returns:
        Dict с результатами обработки
    """
    stats = {
        "loaded": len(results),
        "filtered_out": 0,
        "passed_filter": 0,
        "passed_threshold": 0,
        "filter_reasons": {"not_relevant": 0, "not_fresh": 0},
        "per_label": {
            "accept": {"loaded": 0, "filtered": 0, "passed_filter": 0, "passed_threshold": 0},
            "reject": {"loaded": 0, "filtered": 0, "passed_filter": 0, "passed_threshold": 0},
            "borderline": {
                "loaded": 0,
                "filtered": 0,
                "passed_filter": 0,
                "passed_threshold": 0,
            },
        },
        "candidates": [],
    }

    for item in results:
        filename = item["filename"]
        label = item["label"]
        publication = item["publication"]

        stats["per_label"][label]["loaded"] += 1

        # Filtering
        passed_filter, filter_reason = apply_filtering(publication)
        if not passed_filter:
            stats["filtered_out"] += 1
            stats["filter_reasons"][filter_reason] += 1
            stats["per_label"][label]["filtered"] += 1
            continue

        stats["passed_filter"] += 1
        stats["per_label"][label]["passed_filter"] += 1

        # Scoring
        score_result = score_publication(publication)

        # Threshold check
        if score_result.score >= THRESHOLD:
            stats["passed_threshold"] += 1
            stats["per_label"][label]["passed_threshold"] += 1
            stats["candidates"].append(
                {
                    "filename": filename,
                    "label": label,
                    "score": score_result.score,
                    "reasons": score_result.reasons,
                    "title": publication.title,
                }
            )

    # Сортируем кандидатов по score desc
    stats["candidates"].sort(key=lambda x: x["score"], reverse=True)

    return stats


def print_report(stats: Dict):
    """Выводит отчет."""
    print("\n" + "=" * 100)
    print("PIPELINE DRY-RUN REPORT")
    print("=" * 100)

    # Totals
    print("\nTOTALS:")
    print(f"  Loaded          : {stats['loaded']:3}")
    print(f"  Filtered out    : {stats['filtered_out']:3}")
    print(f"  Passed filter   : {stats['passed_filter']:3}")
    print(f"  Passed threshold: {stats['passed_threshold']:3}")

    # Filter reasons
    print("\nFILTER REASONS:")
    for reason, count in stats["filter_reasons"].items():
        print(f"  {reason:15}: {count:3}")

    # Per-label breakdown
    print("\nPER-LABEL BREAKDOWN:")
    for label in ["accept", "reject", "borderline"]:
        label_stats = stats["per_label"][label]
        print(f"  {label:10}:")
        print(f"    Loaded          : {label_stats['loaded']:3}")
        print(f"    Filtered        : {label_stats['filtered']:3}")
        print(f"    Passed filter   : {label_stats['passed_filter']:3}")
        print(f"    Passed threshold: {label_stats['passed_threshold']:3}")

    # Top candidates
    print("\n" + "=" * 100)
    print("TOP-10 QUEUE CANDIDATES (sorted by score desc)")
    print("=" * 100)
    print(f"{'Rank':<5} | {'Filename':<40} | {'Label':<10} | {'Score':>5}")
    print("-" * 100)

    top_candidates = stats["candidates"][:10]
    if not top_candidates:
        print("  (no candidates)")
    else:
        for rank, candidate in enumerate(top_candidates, 1):
            filename_short = (
                candidate["filename"][:40]
                if len(candidate["filename"]) > 40
                else candidate["filename"]
            )
            print(
                f"{rank:<5} | {filename_short:<40} | "
                f"{candidate['label']:<10} | {candidate['score']:>5}"
            )

    print("=" * 100)


def main():
    """Главная функция скрипта."""
    # Определяем путь к fixtures
    fixtures_dir = project_root / "tests" / "fixtures" / "scoring"

    if not fixtures_dir.exists():
        print(f"Error: Fixtures directory not found: {fixtures_dir}")
        return 1

    # Загружаем все фикстуры
    results = []
    for json_file in sorted(fixtures_dir.glob("*.json")):
        filename, data, label = load_fixture_file(json_file)
        publication = publication_from_dict(data)
        results.append({"filename": filename, "label": label, "publication": publication})

    # Обрабатываем через пайплайн
    stats = process_pipeline(results)

    # Выводим отчет
    print_report(stats)

    return 0


if __name__ == "__main__":
    exit(main())
