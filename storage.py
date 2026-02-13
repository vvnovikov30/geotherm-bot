"""
Работа с SQLite базой данных для дедупликации новостей.
"""
import hashlib
import os
import sqlite3

# Путь к базе данных
DB_DIR = "db"
DB_PATH = os.path.join(DB_DIR, "seen.db")


def init_db():
    """
    Инициализирует базу данных и создает таблицу, если её нет.
    """
    # Создаем директорию для базы данных, если её нет
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    
    # Подключаемся к базе данных
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Создаем таблицу для хранения просмотренных новостей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_items (
            fingerprint TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            published_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"База данных инициализирована: {DB_PATH}")


def make_fingerprint(title, url):
    """
    Создает уникальный fingerprint для новости на основе заголовка и URL.
    
    Args:
        title: Заголовок новости
        url: URL новости
    
    Returns:
        str: SHA256 хеш от заголовка и URL
    """
    # Комбинируем заголовок и URL для создания уникального идентификатора
    combined = f"{title}|{url}".encode('utf-8')
    fingerprint = hashlib.sha256(combined).hexdigest()
    return fingerprint


def already_seen(fingerprint):
    """
    Проверяет, была ли новость уже обработана.
    
    Args:
        fingerprint: Уникальный идентификатор новости
    
    Returns:
        bool: True если новость уже была обработана, False иначе
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM seen_items WHERE fingerprint = ?", (fingerprint,))
    result = cursor.fetchone()
    
    conn.close()
    return result is not None


def mark_seen(fingerprint, url, published_at):
    """
    Помечает новость как обработанную.
    
    Args:
        fingerprint: Уникальный идентификатор новости
        url: URL новости
        published_at: Дата публикации новости
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR IGNORE INTO seen_items (fingerprint, url, published_at)
        VALUES (?, ?, ?)
    """, (fingerprint, url, published_at))
    
    conn.commit()
    conn.close()
