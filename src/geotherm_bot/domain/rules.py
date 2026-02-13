"""
Правила скоринга публикаций.
"""
from typing import List

# Высокоприоритетные типы публикаций: большие бонусы
HIGH_PRIORITY_TYPES = [
    "randomized controlled trial",
    "clinical trial",
    "systematic review",
    "meta-analysis"
]

# Негативные типы: сильный штраф
NEGATIVE_TYPES = [
    "letter",
    "comment",
    "editorial",
    "erratum",
    "corrigendum"
]


def apply_pub_type_rules(pub_types_lower: List[str], add_reason) -> None:
    """
    Применяет правила скоринга на основе типов публикаций.
    
    Args:
        pub_types_lower: Список типов публикаций в нижнем регистре
        add_reason: Функция для добавления очков и причины (points, reason)
    """
    # Высокоприоритетные типы: большие бонусы
    for pub_type in pub_types_lower:
        if any(priority in pub_type for priority in HIGH_PRIORITY_TYPES):
            add_reason(+8, f"high-priority: {pub_type}")
            break  # Берем только первый найденный
    
    # Review (но не Systematic Review, который уже обработан выше)
    if not any("systematic review" in pt or "meta-analysis" in pt for pt in pub_types_lower):
        if any("review" in pt for pt in pub_types_lower):
            add_reason(+5, "review")
    
    # Негативные типы: сильный штраф
    for pub_type in pub_types_lower:
        if any(negative in pub_type for negative in NEGATIVE_TYPES):
            add_reason(-8, f"negative-type: {pub_type}")
            break  # Берем только первый найденный
    
    # Preprint: небольшой штраф
    if "preprint" in pub_types_lower:
        add_reason(-3, "preprint")


def apply_title_rules(title_lower: str, add_reason) -> None:
    """
    Применяет правила скоринга на основе заголовка.
    
    Args:
        title_lower: Заголовок в нижнем регистре
        add_reason: Функция для добавления очков и причины (points, reason)
    """
    if "letter to the editor" in title_lower:
        add_reason(-6, "letter")
    
    if "corrigendum" in title_lower:
        add_reason(-6, "erratum")
    
    if "published erratum" in title_lower:
        add_reason(-6, "erratum")


def apply_text_rules(text_lower: str, add_reason) -> None:
    """
    Применяет правила скоринга на основе текста (title + summary).
    
    Args:
        text_lower: Текст в нижнем регистре
        add_reason: Функция для добавления очков и причины (points, reason)
    """
    if "mouse" in text_lower or "mice" in text_lower:
        add_reason(-4, "animal study")
    
    if "in vitro" in text_lower:
        add_reason(-4, "in vitro")
    
    if "randomized" in text_lower or "randomised" in text_lower:
        add_reason(+5, "randomized trial")
    
    if "clinical trial" in text_lower:
        add_reason(+5, "clinical trial")
    
    if "pilot study" in text_lower:
        add_reason(+3, "pilot study")
