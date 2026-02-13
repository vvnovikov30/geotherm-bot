"""
Редакционная фильтрация статей: релевантность, свежесть, score.
"""

import re
from datetime import datetime

from config import EXCLUDE_TERMS, INCLUDE_TERMS, MAX_AGE_DAYS


def is_relevant(item):
    """
    Проверяет релевантность статьи по include/exclude терминам.

    Args:
        item: Словарь с новостью (должен содержать "title" и "summary")

    Returns:
        bool: True если статья релевантна, False иначе
    """
    title = item.get("title", "").lower()
    summary = item.get("summary", "").lower()
    text = f"{title} {summary}"

    # Проверяем exclude термины (если есть хотя бы один - не релевантно)
    for term in EXCLUDE_TERMS:
        if term.lower() in text:
            return False

    # Проверяем include термины (должен быть хотя бы один)
    for term in INCLUDE_TERMS:
        if term.lower() in text:
            return True

    # Если нет ни одного include термина - не релевантно
    return False


def parse_date(date_str):
    """
    Парсит дату из строки в datetime объект.

    Поддерживает форматы:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM:SS
    - YYYY (только год)
    - Другие форматы через dateutil

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


def is_fresh(item):
    """
    Проверяет, свежая ли статья (в пределах MAX_AGE_DAYS).

    Args:
        item: Словарь с новостью (должен содержать "published_at")

    Returns:
        bool: True если статья свежая, False иначе
            (включая случай, когда дату не удалось распарсить)
    """
    published_at = item.get("published_at", "")
    if not published_at:
        return False

    pub_date = parse_date(published_at)
    if not pub_date:
        return False

    age = datetime.now() - pub_date
    return age.days <= MAX_AGE_DAYS


def score_item(item) -> tuple[int, list[str]]:
    """
    Вычисляет score статьи на основе её характеристик.

    Args:
        item: Словарь с новостью (должен содержать "title" и "summary")

    Returns:
        tuple[int, list[str]]: (score: int, reasons: list[str])
    """
    title = item.get("title", "")
    summary = item.get("summary", "")
    text = (title + " " + summary).lower()

    title_lower = title.lower()
    pub_types = item.get("pub_types", [])
    pub_types_lower = [str(pt).lower() for pt in pub_types]

    score = 0
    reasons = []

    # Helper функция для добавления причины
    def add(points, reason):
        nonlocal score
        score += points
        reasons.append(reason)

    # Правила для title
    if "letter to the editor" in title_lower:
        add(-6, "letter")

    if "corrigendum" in title_lower:
        add(-6, "erratum")

    if "published erratum" in title_lower:
        add(-6, "erratum")

    # Правила для pub_types (проверяем в порядке приоритета)

    # Высокоприоритетные типы публикаций: большие бонусы
    high_priority_types = [
        "randomized controlled trial",
        "clinical trial",
        "systematic review",
        "meta-analysis",
    ]
    for pub_type in pub_types_lower:
        if any(priority in pub_type for priority in high_priority_types):
            add(+8, f"high-priority: {pub_type}")
            break  # Берем только первый найденный

    # Review (но не Systematic Review, который уже обработан выше)
    if not any("systematic review" in pt or "meta-analysis" in pt for pt in pub_types_lower):
        if any("review" in pt for pt in pub_types_lower):
            add(+5, "review")

    # Негативные типы: сильный штраф
    negative_types = ["letter", "comment", "editorial", "erratum", "corrigendum"]
    for pub_type in pub_types_lower:
        if any(negative in pub_type for negative in negative_types):
            add(-8, f"negative-type: {pub_type}")
            break  # Берем только первый найденный

    # Preprint: небольшой штраф
    if "preprint" in pub_types_lower:
        add(-3, "preprint")

    # Правила для text
    if "mouse" in text or "mice" in text:
        add(-4, "animal study")

    if "in vitro" in text:
        add(-4, "in vitro")

    if "randomized" in text or "randomised" in text:
        add(+5, "randomized trial")

    if "clinical trial" in text:
        add(+5, "clinical trial")

    if "pilot study" in text:
        add(+3, "pilot study")

    return score, reasons


def classify_bucket(item):
    """
    Классифицирует статью по типу: review, trial, study.

    Args:
        item: Словарь с новостью (должен содержать "title" и "summary")

    Returns:
        str: "review", "trial" или "study"
    """
    title = item.get("title", "").lower()
    summary = item.get("summary", "").lower()
    text = f"{title} {summary}"

    review_terms = (
        "systematic review" in text
        or "meta-analysis" in text
        or "meta analysis" in text
        or "review" in text
    )
    if review_terms:
        return "review"

    if "trial" in text or "randomized" in text or "randomised" in text:
        return "trial"

    return "study"


def detect_region(item):
    """
    Определяет регион статьи на основе affiliation/country.

    Args:
        item: Словарь с новостью (может содержать дополнительные поля из Europe PMC)

    Returns:
        str|None: "asia" если найдена страна из Азии, иначе None
    """
    # Проверяем title и summary на упоминание стран
    title = item.get("title", "").lower()
    summary = item.get("summary", "").lower()
    text = f"{title} {summary}"

    asia_countries = ["japan", "korea", "china", "india"]
    for country in asia_countries:
        if country in text:
            return "asia"

    # Если в item есть дополнительные поля из Europe PMC (affiliation, country и т.д.)
    # можно добавить проверку здесь

    return None
