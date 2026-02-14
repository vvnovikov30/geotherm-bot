"""
Минимальные unit-тесты для парсинга переменных окружения в run_scheduler.
"""

from scripts.run_scheduler import parse_run_once


def test_parse_run_once_none():
    """Проверяет, что None возвращает False."""
    assert parse_run_once(None) is False


def test_parse_run_once_empty():
    """Проверяет, что пустая строка возвращает False."""
    assert parse_run_once("") is False


def test_parse_run_once_one():
    """Проверяет, что "1" возвращает True."""
    assert parse_run_once("1") is True


def test_parse_run_once_true():
    """Проверяет, что "true" возвращает True."""
    assert parse_run_once("true") is True


def test_parse_run_once_yes_uppercase():
    """Проверяет, что "YES" (uppercase) возвращает True."""
    assert parse_run_once("YES") is True


def test_parse_run_once_zero():
    """Проверяет, что "0" возвращает False."""
    assert parse_run_once("0") is False


def test_parse_run_once_off():
    """Проверяет, что "off" возвращает False."""
    assert parse_run_once("off") is False
