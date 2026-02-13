"""
Логика фильтрации публикаций: релевантность и свежесть.
"""

import re
from datetime import datetime
from typing import List, Optional

from .models import Publication


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Парсит дату из строки в datetime объект.

    Поддерживает форматы:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM:SS
    - YYYY (только год)

    Args:
        date_str: Строка с датой

    Returns:
        datetime|None: Объект datetime или None если не удалось распарсить
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # Пробуем стандартные форматы
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Если только год, создаем дату 1 января
    if re.match(r"^\d{4}$", date_str):
        try:
            year = int(date_str)
            return datetime(year, 1, 1)
        except ValueError:
            pass

    return None


def is_relevant(
    publication: Publication, include_terms: List[str], exclude_terms: List[str]
) -> bool:
    """
    Проверяет релевантность публикации по include/exclude терминам.

    Args:
        publication: Публикация для проверки
        include_terms: Список терминов, которые должны присутствовать
        exclude_terms: Список терминов, которые не должны присутствовать

    Returns:
        bool: True если публикация релевантна, False иначе
    """
    title = publication.title.lower()
    summary = (publication.abstract or publication.summary or "").lower()
    text = f"{title} {summary}"

    # Проверяем exclude термины (если есть хотя бы один - не релевантно)
    for term in exclude_terms:
        if term.lower() in text:
            return False

    # Проверяем include термины (должен быть хотя бы один)
    for term in include_terms:
        if term.lower() in text:
            return True

    # Если нет ни одного include термина - не релевантно
    return False


def is_fresh(publication: Publication, max_age_days: int) -> bool:
    """
    Проверяет, свежая ли публикация (в пределах max_age_days).

    Args:
        publication: Публикация для проверки
        max_age_days: Максимальный возраст публикации в днях

    Returns:
        bool: True если публикация свежая, False иначе
    """
    if not publication.published_at:
        return False

    pub_date = parse_date(publication.published_at)
    if not pub_date:
        return False

    age = datetime.now() - pub_date
    return age.days <= max_age_days
