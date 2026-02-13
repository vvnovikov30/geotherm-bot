"""
Логика скоринга публикаций.
"""

from typing import List

from .models import Publication, ScoreResult
from .rules import apply_pub_type_rules, apply_text_rules, apply_title_rules


def score_publication(publication: Publication) -> ScoreResult:
    """
    Вычисляет score публикации на основе её характеристик.

    Args:
        publication: Публикация для скоринга

    Returns:
        ScoreResult: Результат скоринга (score, reasons, is_high_priority)
    """
    title = publication.title
    # Используем abstract или summary
    summary = publication.abstract or publication.summary or ""
    text = (title + " " + summary).lower()

    title_lower = title.lower()
    pub_types = publication.pub_types
    pub_types_lower = [str(pt).lower() for pt in pub_types]

    score = 0
    reasons: List[str] = []

    # Helper функция для добавления причины
    def add(points: int, reason: str):
        nonlocal score
        score += points
        reasons.append(reason)

    # Применяем правила скоринга
    apply_title_rules(title_lower, add)
    apply_pub_type_rules(pub_types_lower, add)
    apply_text_rules(text, add)

    # Определяем, является ли публикация высокоприоритетной
    is_high_priority = any("high-priority" in reason for reason in reasons) or score >= 8

    return ScoreResult(score=score, reasons=reasons, is_high_priority=is_high_priority)


def classify_bucket(publication: Publication) -> str:
    """
    Классифицирует публикацию по типу: review, trial, study.

    Args:
        publication: Публикация для классификации

    Returns:
        str: "review", "trial" или "study"
    """
    title = publication.title.lower()
    summary = (publication.abstract or publication.summary or "").lower()
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


def detect_region(publication: Publication) -> str:
    """
    Определяет регион публикации на основе affiliation/country.

    Args:
        publication: Публикация для определения региона

    Returns:
        str|None: "asia" если найдена страна из Азии, иначе None
    """
    title = publication.title.lower()
    summary = (publication.abstract or publication.summary or "").lower()
    text = f"{title} {summary}"

    asia_countries = ["japan", "korea", "china", "india"]
    for country in asia_countries:
        if country in text:
            return "asia"

    return None
