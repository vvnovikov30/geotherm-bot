"""
Форматирование сообщений для отправки в Telegram.
"""
from datetime import datetime


def format_message(item):
    """
    Форматирует новость в текст сообщения для Telegram.
    
    Args:
        item: Словарь с новостью:
            {
                "title": str,
                "url": str,
                "published_at": str,
                "source": str,
                "summary": str (опционально),
                "bucket": str (опционально, "review"/"trial"/"study")
            }
    
    Returns:
        str: Отформатированный текст сообщения
    """
    title = item.get("title", "Без заголовка")
    url = item.get("url", "")
    source = item.get("source", "Неизвестный источник")
    published_at = item.get("published_at", "")
    summary = item.get("summary", "")
    bucket = item.get("bucket", "")
    
    # Формируем сообщение
    message = f"📰 {title}\n\n"
    
    # Добавляем тип статьи (Review/Trial/Study)
    if bucket:
        bucket_display = bucket.capitalize()
        message += f"Тип: {bucket_display}\n"
    
    message += f"🔗 Источник: {source}\n"
    
    if published_at:
        message += f"📅 Дата: {published_at}\n"
    
    # Добавляем аннотацию (1-2 строки, обрезать до 300-500 символов)
    if summary:
        # Очищаем от лишних пробелов и переносов
        summary_clean = " ".join(summary.split())
        # Обрезаем до 400 символов (компромисс между 300-500)
        if len(summary_clean) > 400:
            summary_clean = summary_clean[:400].rsplit(" ", 1)[0] + "..."
        message += f"\n{summary_clean}\n"
    
    if url:
        message += f"\n🔗 {url}"
    
    return message
