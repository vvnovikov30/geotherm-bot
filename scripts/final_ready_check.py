#!/usr/bin/env python3
"""
Final ready check - release gate перед включением scheduler/publish/telegram.

Выполняет последовательность проверок:
- Ruff check
- Pytest
- Scoring report
- Pipeline dry-run report
- Gate conditions validation
"""

import re
import subprocess
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path для импортов
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))


def run_command(cmd: list[str], description: str) -> tuple[int, str]:
    """
    Запускает команду и возвращает exit code и stdout.

    Args:
        cmd: Команда для запуска (список аргументов)
        description: Описание команды для вывода

    Returns:
        Tuple[exit_code, stdout]: код выхода и вывод команды
    """
    print(f"\n{'=' * 100}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 100)

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode, result.stdout
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return 1, ""


def parse_pipeline_metrics(stdout: str) -> dict:
    """
    Парсит метрики из вывода pipeline_dry_run_report.py.

    Returns:
        Dict с метриками или пустой dict если не удалось распарсить
    """
    metrics = {}
    lines = stdout.split("\n")

    # Парсим TOTALS
    i = 0
    while i < len(lines):
        if "TOTALS:" in lines[i]:
            i += 1
            # Следующие строки должны быть метриками
            while i < len(lines) and (
                "Loaded" in lines[i] or "Filtered" in lines[i] or "Passed" in lines[i]
            ):
                line = lines[i]
                if "Loaded" in line:
                    match = re.search(r"Loaded\s+:\s*(\d+)", line)
                    if match:
                        metrics["total_loaded"] = int(match.group(1))
                elif "Filtered out" in line:
                    match = re.search(r"Filtered out\s+:\s*(\d+)", line)
                    if match:
                        metrics["filtered_out"] = int(match.group(1))
                elif "Passed filter" in line:
                    match = re.search(r"Passed filter\s+:\s*(\d+)", line)
                    if match:
                        metrics["passed_filter"] = int(match.group(1))
                elif "Passed threshold" in line:
                    match = re.search(r"Passed threshold:\s*(\d+)", line)
                    if match:
                        metrics["passed_threshold"] = int(match.group(1))
                i += 1
            break
        i += 1

    # Парсим PER-LABEL BREAKDOWN
    # Ищем секцию PER-LABEL BREAKDOWN
    per_label_start = stdout.find("PER-LABEL BREAKDOWN:")
    if per_label_start != -1:
        # Находим конец секции (следующая секция с ===)
        per_label_end = stdout.find("\n" + "=" * 100, per_label_start)
        if per_label_end == -1:
            per_label_end = len(stdout)
        per_label_section = stdout[per_label_start:per_label_end]
        per_label_lines = per_label_section.split("\n")

        # Для каждого label ищем его блок
        for label in ["accept", "reject", "borderline"]:
            # Ищем строку с label в секции PER-LABEL
            label_line_idx = None
            for i, line in enumerate(per_label_lines):
                # Ищем строку вида "  accept    :" или "  borderline:" и т.д.
                # Используем более гибкий паттерн
                if re.search(rf"^\s+{label}\s*:\s*$", line):
                    label_line_idx = i
                    break

            if label_line_idx is not None:
                # Парсим следующие строки с отступом (метрики)
                # Берём строки до следующего label или до конца секции
                for i in range(label_line_idx + 1, min(label_line_idx + 10, len(per_label_lines))):
                    line = per_label_lines[i]
                    # Если встретили следующий label - останавливаемся
                    if line.strip():
                        # Проверяем, не начало ли это следующего label
                        if any(
                            re.search(rf"^\s+{other_label}\s*:\s*$", line)
                            for other_label in ["accept", "reject", "borderline"]
                            if other_label != label
                        ):
                            break
                    # Парсим метрики (только строки с отступом)
                    if line.startswith(" ") and line.strip():
                        if "Loaded" in line and ":" in line:
                            match = re.search(r"Loaded\s+:\s*(\d+)", line)
                            if match:
                                metrics[f"{label}_loaded"] = int(match.group(1))
                        elif "Filtered" in line and ":" in line:
                            match = re.search(r"Filtered\s+:\s*(\d+)", line)
                            if match:
                                metrics[f"{label}_filtered"] = int(match.group(1))
                        elif "Passed filter" in line:
                            match = re.search(r"Passed filter\s+:\s*(\d+)", line)
                            if match:
                                metrics[f"{label}_passed_filter"] = int(match.group(1))
                        elif "Passed threshold" in line:
                            match = re.search(r"Passed threshold:\s*(\d+)", line)
                            if match:
                                metrics[f"{label}_passed_threshold"] = int(match.group(1))

    return metrics


def check_gate_conditions(metrics: dict) -> tuple[list[str], list[str]]:
    """
    Проверяет gate conditions на основе метрик.

    Returns:
        Tuple[hard_failures, warnings]: список жёстких ошибок и предупреждений
    """
    hard_failures = []
    warnings = []

    # Жёсткие условия
    if metrics.get("passed_threshold", 0) == 0:
        hard_failures.append("Passed threshold = 0 (должен быть > 0)")

    accept_loaded = metrics.get("accept_loaded", 0)
    accept_filtered = metrics.get("accept_filtered", 0)
    accept_passed_threshold = metrics.get("accept_passed_threshold", 0)

    if accept_filtered != 0:
        hard_failures.append(f"Accept: Filtered = {accept_filtered} (ожидается 0)")

    if accept_loaded > 0 and accept_passed_threshold != accept_loaded:
        hard_failures.append(
            f"Accept: Passed threshold = {accept_passed_threshold}, "
            f"но Loaded = {accept_loaded} (все accept должны проходить)"
        )

    reject_passed_threshold = metrics.get("reject_passed_threshold", 0)
    if reject_passed_threshold != 0:
        hard_failures.append(f"Reject: Passed threshold = {reject_passed_threshold} (ожидается 0)")

    # Мягкие условия (warnings)
    borderline_loaded = metrics.get("borderline_loaded", 0)
    if borderline_loaded > 0:
        # Проверяем, есть ли хотя бы один borderline с score != 0
        # Это сложно проверить из метрик, но можем проверить что
        # passed_threshold > 0 или passed_filter > 0
        borderline_passed_filter = metrics.get("borderline_passed_filter", 0)
        if borderline_passed_filter == 0:
            warnings.append(
                "Borderline: все borderline имеют score = 0 "
                "(желательно иметь хотя бы один с score != 0)"
            )

    if metrics.get("filtered_out", 0) == 0:
        warnings.append("Filtered out = 0 (фильтр ничего не режет, возможно слишком мягкий)")

    return hard_failures, warnings


def print_readiness_report(metrics: dict, hard_failures: list[str], warnings: list[str]):
    """Выводит отчёт о готовности."""
    print("\n" + "=" * 100)
    print("READINESS METRICS")
    print("=" * 100)

    print("\nPipeline Metrics:")
    print(f"  Total Loaded      : {metrics.get('total_loaded', 'N/A')}")
    print(f"  Filtered out      : {metrics.get('filtered_out', 'N/A')}")
    print(f"  Passed filter     : {metrics.get('passed_filter', 'N/A')}")
    print(f"  Passed threshold  : {metrics.get('passed_threshold', 'N/A')}")

    print("\nPer-Label Metrics:")
    for label in ["accept", "reject", "borderline"]:
        loaded = metrics.get(f"{label}_loaded", 0)
        filtered = metrics.get(f"{label}_filtered", 0)
        passed_filter = metrics.get(f"{label}_passed_filter", 0)
        passed_threshold = metrics.get(f"{label}_passed_threshold", 0)
        print(f"  {label:10}:")
        print(f"    Loaded          : {loaded}")
        print(f"    Filtered        : {filtered}")
        print(f"    Passed filter   : {passed_filter}")
        print(f"    Passed threshold: {passed_threshold}")

    print("\n" + "=" * 100)
    print("GATE CONDITIONS")
    print("=" * 100)

    if hard_failures:
        print("\n[FAIL] HARD FAILURES (must fix):")
        for failure in hard_failures:
            print(f"  - {failure}")
    else:
        print("\n[PASS] All hard conditions passed")

    if warnings:
        print("\n[WARN] WARNINGS (soft conditions):")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("\n[PASS] No warnings")

    print("\n" + "=" * 100)
    print("FINAL STATUS")
    print("=" * 100)

    if hard_failures:
        print("\n[FAIL] READY TO ENABLE SCHEDULER/PUBLISH: NO")
        print("\nReasons:")
        for failure in hard_failures:
            print(f"  - {failure}")
    else:
        print("\n[PASS] READY TO ENABLE SCHEDULER/PUBLISH: YES")
        if warnings:
            print("\nNote: There are warnings, but they don't block release.")


def main():
    """Главная функция скрипта."""
    print("=" * 100)
    print("FINAL READY CHECK - RELEASE GATE")
    print("=" * 100)

    # A) Ruff check
    exit_code, _ = run_command(["ruff", "check", "."], "Ruff check")
    if exit_code != 0:
        print("\n[FAIL] Ruff check failed. Aborting.")
        return 1

    # B) Pytest
    exit_code, _ = run_command(["pytest", "-q"], "Pytest")
    if exit_code != 0:
        print("\n[FAIL] Pytest failed. Aborting.")
        return 1

    # C) Scoring report
    exit_code, scoring_stdout = run_command(
        [sys.executable, "scripts/scoring_report.py"], "Scoring report"
    )
    if exit_code != 0:
        print("\n[FAIL] Scoring report failed. Aborting.")
        return 1

    # D) Pipeline dry-run report
    exit_code, pipeline_stdout = run_command(
        [sys.executable, "scripts/pipeline_dry_run_report.py"],
        "Pipeline dry-run report",
    )
    if exit_code != 0:
        print("\n[FAIL] Pipeline dry-run report failed. Aborting.")
        return 1

    # Парсим метрики из pipeline report
    metrics = parse_pipeline_metrics(pipeline_stdout)
    if not metrics:
        print("\n[FAIL] Error: Could not parse pipeline metrics.")
        return 1

    # Строгая проверка: все label должны быть найдены
    required_labels = ["accept", "reject", "borderline"]
    missing_labels = []
    for label in required_labels:
        if f"{label}_loaded" not in metrics:
            missing_labels.append(label)

    if missing_labels:
        print("\n[FAIL] Error: Could not parse metrics for labels:")
        for label in missing_labels:
            print(f"  - {label}")
        print("\nThis indicates a parsing bug or changed output format.")
        return 1

    # Проверяем gate conditions
    hard_failures, warnings = check_gate_conditions(metrics)

    # Выводим отчёт о готовности
    print_readiness_report(metrics, hard_failures, warnings)

    # Возвращаем exit code
    if hard_failures:
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
