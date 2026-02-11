"""
Маршрутизация новостей по темам на основе ключевых слов.
"""
from config import TOPIC_MAP


def get_topic(title):
    """
    Определяет тему новости на основе заголовка.
    
    Args:
        title: Заголовок новости
    
    Returns:
        int: message_thread_id для соответствующей темы, или "general" если не найдено
    """
    title_lower = title.lower()
    
    # Проверяем ключевые слова для каждой темы
    if "iceland" in title_lower:
        return TOPIC_MAP.get("iceland", TOPIC_MAP.get("general", 0))
    
    if "japan" in title_lower:
        return TOPIC_MAP.get("japan", TOPIC_MAP.get("general", 0))
    
    # По умолчанию отправляем в общую тему
    return TOPIC_MAP.get("general", 0)


def get_topic_key(title):
    """
    Определяет ключ темы новости на основе заголовка.
    
    Args:
        title: Заголовок новости
    
    Returns:
        str: Ключ темы ("iceland", "japan", "general")
    """
    title_lower = title.lower()
    
    if "iceland" in title_lower:
        return "iceland"
    
    if "japan" in title_lower:
        return "japan"
    
    return "general"