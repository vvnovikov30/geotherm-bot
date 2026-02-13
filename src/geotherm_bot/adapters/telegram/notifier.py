"""
Адаптер для отправки уведомлений через Telegram Bot API.
"""

import requests

from ...ports.notifier import Notifier


class TelegramNotifier(Notifier):
    """Реализация Notifier для Telegram."""

    def __init__(self, bot_token: str, dry_run: bool = False):
        """
        Инициализирует Telegram notifier.

        Args:
            bot_token: Токен бота из BotFather
            dry_run: Если True, печатает сообщения вместо отправки
        """
        self.bot_token = bot_token
        self.dry_run = dry_run

    def send(self, chat_id: str, message_thread_id: int, text: str, topic_key: str = None) -> bool:
        """
        Отправляет сообщение в Telegram.

        Args:
            chat_id: ID чата/группы/канала
            message_thread_id: ID темы (topic) в группе
            text: Текст сообщения
            topic_key: Ключ темы для логирования (опционально)

        Returns:
            bool: True если сообщение отправлено успешно, False иначе
        """
        if self.dry_run:
            print("\n" + "=" * 60)
            print("DRY_RUN: Сообщение не отправлено")
            if topic_key:
                print(f"Topic key: {topic_key}")
            print(f"message_thread_id: {message_thread_id}")
            print("Текст сообщения:")
            print("-" * 60)
            print(text)
            print("=" * 60 + "\n")
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }

        if message_thread_id and message_thread_id != 0:
            payload["message_thread_id"] = message_thread_id

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при отправке сообщения в Telegram: {e}")
            if hasattr(e, "response") and hasattr(e.response, "text"):
                print(f"Ответ API: {e.response.text}")
            return False

    def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> None:
        """
        Отправляет сообщение в Telegram.

        Args:
            chat_id: ID чата/группы/канала (int)
            text: Текст сообщения
            message_thread_id: ID темы (topic) в группе (опционально)

        Raises:
            Exception: При ошибке отправки
        """
        if self.dry_run:
            print("\n" + "=" * 60)
            print("DRY_RUN: Сообщение не отправлено")
            print(f"chat_id: {chat_id}")
            if message_thread_id:
                print(f"message_thread_id: {message_thread_id}")
            print("Текст сообщения:")
            print("-" * 60)
            print(text)
            print("=" * 60 + "\n")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }

        if message_thread_id and message_thread_id != 0:
            payload["message_thread_id"] = message_thread_id

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
