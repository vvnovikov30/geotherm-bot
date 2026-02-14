#!/usr/bin/env python3
"""
Offline report для scoring по golden set fixtures.

Генерирует текстовый отчет с таблицей результатов и статистикой.
"""

import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Добавляем корень проекта в sys.path для импортов
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from src.geotherm_bot.domain.models import Publication  # noqa: E402
from src.geotherm_bot.domain.scoring import score_publication  # noqa: E402

THRESHOLD = 5


def load_fixture_file(filepath: Path) -> Tuple[str, dict, str]:
    """
    Загружает фикстуру из файла и определяет её класс.

    Args:
        filepath: Путь к JSON-файлу фикстуры

    Returns:
        Tuple[filename, data, label]: имя файла, данные, метка (accept/reject/borderline)
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
    """Создает Publication из словаря."""
    return Publication(
        id=data["id"],
        source=data["source"],
        title=data["title"],
        abstract=data.get("abstract"),
        pub_types=data.get("pub_types", []),
        year=data.get("year"),
    )


def format_table_row(filename: str, label: str, score: int, width: int = 60) -> str:
    """Форматирует строку таблицы."""
    filename_short = filename[:width] if len(filename) > width else filename
    return f"{filename_short:<{width}} | {label:<10} | {score:>5}"


def print_table(results: List[Tuple[str, str, int]]):
    """Выводит таблицу результатов."""
    print("\n" + "=" * 100)
    print("SCORING REPORT - GOLDEN SET FIXTURES")
    print("=" * 100)
    print(f"{'Filename':<60} | {'Label':<10} | {'Score':>5}")
    print("-" * 100)

    for filename, label, score in results:
        print(format_table_row(filename, label, score))

    print("=" * 100)


def calculate_statistics(results: List[Tuple[str, str, int]]) -> Dict:
    """Вычисляет статистику по результатам."""
    all_scores = [score for _, _, score in results]
    accept_scores = [score for _, label, score in results if label == "accept"]
    reject_scores = [score for _, label, score in results if label == "reject"]
    borderline_scores = [score for _, label, score in results if label == "borderline"]

    stats = {
        "total_count": len(results),
        "count_per_label": {
            "accept": len(accept_scores),
            "reject": len(reject_scores),
            "borderline": len(borderline_scores),
        },
        "overall": {
            "min": min(all_scores) if all_scores else 0,
            "median": int(statistics.median(all_scores)) if all_scores else 0,
            "max": max(all_scores) if all_scores else 0,
        },
        "per_label": {},
        "threshold_violations": {
            "accept_below": sum(
                1 for _, label, score in results if label == "accept" and score < THRESHOLD
            ),
            "reject_above": sum(
                1 for _, label, score in results if label == "reject" and score >= THRESHOLD
            ),
        },
        "borderline_threshold": {
            "above": sum(
                1 for _, label, score in results if label == "borderline" and score >= THRESHOLD
            ),
            "below": sum(
                1 for _, label, score in results if label == "borderline" and score < THRESHOLD
            ),
        },
    }

    # Статистика по меткам
    for label, scores in [
        ("accept", accept_scores),
        ("reject", reject_scores),
        ("borderline", borderline_scores),
    ]:
        if scores:
            stats["per_label"][label] = {
                "min": min(scores),
                "median": int(statistics.median(scores)),
                "max": max(scores),
            }
        else:
            stats["per_label"][label] = {"min": 0, "median": 0, "max": 0}

    return stats


def print_statistics(stats: Dict):
    """Выводит статистику."""
    print("\n" + "=" * 100)
    print("STATISTICS")
    print("=" * 100)

    print(f"\nTotal fixtures: {stats['total_count']}")
    print("\nCount per label:")
    for label, count in stats["count_per_label"].items():
        print(f"  {label:10}: {count:3}")

    print("\nOverall score statistics:")
    overall = stats["overall"]
    print(f"  Min   : {overall['min']:5}")
    print(f"  Median: {overall['median']:5}")
    print(f"  Max   : {overall['max']:5}")

    print("\nScore statistics per label:")
    for label in ["accept", "reject", "borderline"]:
        if label in stats["per_label"]:
            per_label = stats["per_label"][label]
            print(f"  {label:10}:")
            print(f"    Min   : {per_label['min']:5}")
            print(f"    Median: {per_label['median']:5}")
            print(f"    Max   : {per_label['max']:5}")

    print("\nThreshold violations:")
    violations = stats["threshold_violations"]
    print(f"  Accept below threshold ({THRESHOLD}): {violations['accept_below']} (expected: 0)")
    print(f"  Reject >= threshold ({THRESHOLD}):    {violations['reject_above']} (expected: 0)")

    print("\nBorderline threshold distribution:")
    borderline = stats["borderline_threshold"]
    print(f"  Above threshold ({THRESHOLD}): {borderline['above']}")
    print(f"  Below threshold ({THRESHOLD}): {borderline['below']}")

    print("=" * 100)


def print_top_items(results: List[Tuple[str, str, int]], top_n: int = 5):
    """Выводит TOP-N элементов с наивысшим score."""
    sorted_results = sorted(results, key=lambda x: x[2], reverse=True)
    top_items = sorted_results[:top_n]

    print("\n" + "=" * 100)
    print(f"TOP-{top_n} HIGHEST SCORING ITEMS")
    print("=" * 100)
    print(f"{'Rank':<5} | {'Filename':<50} | {'Label':<10} | {'Score':>5}")
    print("-" * 100)

    for rank, (filename, label, score) in enumerate(top_items, 1):
        filename_short = filename[:50] if len(filename) > 50 else filename
        print(f"{rank:<5} | {filename_short:<50} | {label:<10} | {score:>5}")

    print("=" * 100)


def main():
    """Главная функция скрипта."""
    # Определяем путь к fixtures
    fixtures_dir = project_root / "tests" / "fixtures" / "scoring"

    if not fixtures_dir.exists():
        print(f"Error: Fixtures directory not found: {fixtures_dir}")
        return 1

    # Загружаем все фикстуры и вычисляем score
    results = []
    for json_file in sorted(fixtures_dir.glob("*.json")):
        filename, data, label = load_fixture_file(json_file)
        publication = publication_from_dict(data)
        result = score_publication(publication)
        results.append((filename, label, result.score))

    # Выводим отчет
    print_table(results)

    # Вычисляем и выводим статистику
    stats = calculate_statistics(results)
    print_statistics(stats)

    # Выводим TOP-5
    print_top_items(results, top_n=5)

    return 0


if __name__ == "__main__":
    exit(main())
