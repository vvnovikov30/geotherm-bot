"""
Основной файл Telegram-бота.
Осуществляет polling RSS-лент и отправку новых новостей в Telegram.
"""
import time
import argparse
import requests
from config import (
    BOT_TOKEN, CHAT_ID, POLL_SECONDS, DRY_RUN, EDITORIAL_MODE,
    SCORE_THRESHOLD, TOPIC_MAP
)
from storage import init_db, make_fingerprint, already_seen, mark_seen
from rss_collector import fetch_items
from router import get_topic, get_topic_key
from formatter import format_message
from editorial import (
    is_relevant, is_fresh, score_item, classify_bucket, detect_region
)


def send_telegram_message(chat_id, message_thread_id, text, topic_key=None):
    """
    Отправляет сообщение в Telegram через Bot API или печатает в DRY_RUN режиме.
    
    Args:
        chat_id: ID чата/группы/канала
        message_thread_id: ID темы (topic) в группе
        text: Текст сообщения
        topic_key: Ключ темы для логирования (опционально)
    
    Returns:
        bool: True если сообщение отправлено успешно, False иначе
    """
    # В режиме DRY_RUN печатаем информацию вместо отправки
    if DRY_RUN:
        print("\n" + "="*60)
        print("DRY_RUN: Сообщение не отправлено")
        if topic_key:
            print(f"Topic key: {topic_key}")
        print(f"message_thread_id: {message_thread_id}")
        print(f"Текст сообщения:")
        print("-"*60)
        print(text)
        print("="*60 + "\n")
        return True
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }
    
    # Добавляем message_thread_id только если он не равен 0
    if message_thread_id and message_thread_id != 0:
        payload["message_thread_id"] = message_thread_id
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")
        if hasattr(e.response, 'text'):
            print(f"Ответ API: {e.response.text}")
        return False


def process_cycle():
    """
    Выполняет один цикл обработки: сбор → фильтр → форматирование → отправка.
    
    Returns:
        int: Количество обработанных новых новостей
    """
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Проверка новых новостей...")
    
    # Получаем новости из RSS-лент
    items = fetch_items()
    print(f"Найдено новостей: {len(items)}")
    
    new_count = 0
    filtered_count = 0
    
    for item in items:
        if DRY_RUN:
            print("\n--- RAW ITEM --------------------------------")
            print("TITLE:", item.get("title"))
            print("DATE:", item.get("published_at"))
            print("URL:", item.get("url"))
            print("SUMMARY:", (item.get("summary") or "")[:500])
            print("--------------------------------------------")

        reasons = []  # Инициализируем для доступа в DRY_RUN
        try:
            # Создаем fingerprint для дедупликации
            fingerprint = make_fingerprint(item["title"], item["url"])
            
            # Проверяем, не обрабатывали ли мы уже эту новость
            if already_seen(fingerprint):
                print(f"⊘ Отфильтровано (уже обработано): {item['title'][:60]}...")
                filtered_count += 1
                continue
            
            # Редакционный режим: фильтрация
            if EDITORIAL_MODE:
                # Проверка релевантности
                if not is_relevant(item):
                    if DRY_RUN:
                        print(f"⊘ EXCLUDED: {item['title'][:60]}...")
                    filtered_count += 1
                    continue
                
                # Проверка свежести
                if not is_fresh(item):
                    if DRY_RUN:
                        print(f"⊘ NOT_FRESH: {item['title'][:60]}...")
                    filtered_count += 1
                    continue
                
                # Проверка score (на уровне цикла for item in items)
                score, reasons = score_item(item)
                if score < SCORE_THRESHOLD:
                    if DRY_RUN:
                        print(f"⊘ LOW_SCORE ({score}): {item['title']}")
                        print(f"   Reasons: {', '.join(reasons) if reasons else 'none'}")
                    filtered_count += 1
                    continue
                
                # Классификация и определение темы
                bucket = classify_bucket(item)
                region = detect_region(item)
                
                # Определяем topic_key: "asia" если region=="asia", иначе bucket
                if region == "asia":
                    topic_key = "asia"
                else:
                    topic_key = bucket
                
                # Получаем message_thread_id из TOPIC_MAP
                message_thread_id = TOPIC_MAP.get(topic_key, TOPIC_MAP.get("general", 0))
                
                # Добавляем bucket и score в item для форматтера
                item["bucket"] = bucket
                item["score"] = score
            else:
                # Старый режим: используем router
                message_thread_id = get_topic(item["title"])
                topic_key = get_topic_key(item["title"])
            
            # Форматируем сообщение
            message_text = format_message(item)
            
            # Отправляем сообщение в Telegram (или печатаем в DRY_RUN)
            if send_telegram_message(CHAT_ID, message_thread_id, message_text, topic_key):
                if DRY_RUN:
                    print(f"✓ [DRY_RUN] Обработано: {item['title'][:50]}...")
                    if EDITORIAL_MODE and reasons:
                        print(f"   Reasons: {', '.join(reasons)}")
                else:
                    print(f"✓ Отправлено: {item['title'][:50]}...")
                new_count += 1
            else:
                print(f"✗ Ошибка отправки: {item['title'][:50]}...")
            
            # Помечаем новость как обработанную
            mark_seen(fingerprint, item["url"], item["published_at"])
            
            # Небольшая задержка между сообщениями, чтобы не спамить
            if not DRY_RUN:
                time.sleep(1)
            
        except Exception as e:
            print(f"Ошибка при обработке новости: {e}")
            continue
    
    print(f"Обработано новых новостей: {new_count}")
    if filtered_count > 0:
        print(f"Отфильтровано новостей: {filtered_count}")
    
    return new_count


def main():
    """
    Основной цикл работы бота.
    """
    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description="GeoTherm Telegram Bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Выполнить один цикл (сбор → фильтр → форматирование) и завершиться"
    )
    args = parser.parse_args()
    
    # Проверяем наличие обязательных параметров (только если не DRY_RUN)
    if not DRY_RUN:
        if not BOT_TOKEN:
            print("ОШИБКА: BOT_TOKEN не установлен в .env файле")
            return
        
        if not CHAT_ID:
            print("ОШИБКА: CHAT_ID не установлен в .env файле")
            return
    
    # Инициализируем базу данных
    print("Инициализация базы данных...")
    init_db()
    
    if DRY_RUN:
        print("⚠️  Режим DRY_RUN: сообщения не будут отправляться в Telegram")
    
    if args.once:
        print("Режим --once: выполнение одного цикла...")
        process_cycle()
        print("\nЦикл завершен. Выход.")
        return
    
    print(f"Бот запущен. Интервал опроса: {POLL_SECONDS} секунд")
    print("Нажмите Ctrl+C для остановки")
    
    # Бесконечный цикл опроса
    while True:
        try:
            process_cycle()
        except KeyboardInterrupt:
            print("\n\nОстановка бота...")
            break
        except Exception as e:
            print(f"Критическая ошибка в основном цикле: {e}")
            print("Продолжаем работу через 60 секунд...")
            time.sleep(60)
        
        # Ждем перед следующим опросом
        print(f"Ожидание {POLL_SECONDS} секунд до следующей проверки...")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
