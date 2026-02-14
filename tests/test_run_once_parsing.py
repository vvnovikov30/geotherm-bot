"""
Тесты для парсинга переменной окружения RUN_ONCE.
"""

import sys
from pathlib import Path

# Добавляем scripts в путь для импорта
script_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(script_dir))

# Импортируем функцию парсинга из run_scheduler
from run_scheduler import parse_run_once  # noqa: E402


def test_parse_run_once_true_values():
    """Проверяет, что значения для True правильно парсятся."""
    true_values = ["1", "true", "yes", "y", "on"]
    # Также проверяем case-insensitive
    true_values.extend(["TRUE", "True", "YES", "Yes", "Y", "ON", "On"])

    for value in true_values:
        assert parse_run_once(value) is True, f"Expected True for '{value}'"


def test_parse_run_once_false_values():
    """Проверяет, что значения для False правильно парсятся."""
    false_values = ["0", "false", "no", "off", ""]
    # Также проверяем case-insensitive
    false_values.extend(["FALSE", "False", "NO", "No", "OFF", "Off"])

    for value in false_values:
        assert parse_run_once(value) is False, f"Expected False for '{value}'"


def test_parse_run_once_none():
    """Проверяет, что None возвращает False."""
    assert parse_run_once(None) is False


def test_parse_run_once_whitespace():
    """Проверяет, что пробелы обрезаются."""
    assert parse_run_once("  true  ") is True
    assert parse_run_once("  1  ") is True
    assert parse_run_once("  false  ") is False
    assert parse_run_once("  0  ") is False
