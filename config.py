"""
Конфигурация бота.
Загружает переменные окружения из .env файла.
"""

import os

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Токен бота из Telegram BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ID чата (группы/канала) куда отправлять сообщения
CHAT_ID = os.getenv("CHAT_ID", "")

# Интервал опроса RSS в секундах (по умолчанию 5 минут)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "300"))

# Режим DRY_RUN: вместо отправки в Telegram печатать информацию
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")

# Редакционный режим: фильтрация статей по релевантности, свежести и score
EDITORIAL_MODE = os.getenv("EDITORIAL_MODE", "True").lower() in ("true", "1", "yes")

# Режим отладки: печать score breakdown для каждого item
DEBUG = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

# Максимальный возраст публикации в днях
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "120"))

# Термины для включения (должны быть в title или summary)
INCLUDE_TERMS = [
    "mineral water",
    "thermal mineral water",
    "balneotherapy",
    "spa therapy",
    "hot spring",
    "onsen",
    "bicarbonate",
    "sulfate",
]

# Термины для исключения (не должны быть в title или summary)
EXCLUDE_TERMS = [
    "wastewater",
    "water pollution",
    "water treatment",
    "sewage",
    "microplastics",
    "chlorination",
    "aquatic",
    "fish",
    "river",
    "desalination",
    "yoga",
    "naturopathy",
    "acupuncture",
    "murine",
    "mice",
    "rat",
    "piglet",
    "in vitro",
    "tensile",
    "fiber",
    "luffa",
    "protocol",
    "study protocol",
    "corrigendum",
    "comment",
]

# Минимальный score для публикации
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "3"))

# Маппинг тем на message_thread_id (по bucket)
TOPIC_MAP = {
    "review": int(os.getenv("TOPIC_REVIEW", "0")),
    "trial": int(os.getenv("TOPIC_TRIAL", "0")),
    "study": int(os.getenv("TOPIC_STUDY", "0")),
    "asia": int(os.getenv("TOPIC_ASIA", "0")),
    "general": int(os.getenv("TOPIC_GENERAL", "0")),
}

# Список RSS-лент для мониторинга
# Медицинские RSS-каналы для сбора новостей и исследований

SCIENCE_FEEDS = [
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=%22mineral%20water%22&format=json&pageSize=25&sort_date=y",
    # Закомментировано: feedparser ломает europepmc.org/search?...mode=rss
    # "https://europepmc.org/search?query=(%22mineral%20water%22%20OR%20balneotherapy%20OR%20hydrotherapy%20OR%20%22spa%20therapy%22%20OR%20%22hot%20spring%22%20OR%20onsen)%20NOT%20(wastewater%20OR%20%22water%20pollution%22%20OR%20%22water%20treatment%22%20OR%20sewage%20OR%20microplastics%20OR%20chlorination%20OR%20aquatic%20OR%20fish)&page=1&mode=rss",
    # --- Глобальные клинические ---
    #  "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(%22mineral%20water%22%20OR%20balneotherapy%20OR%20%22spa%20therapy%22)%20AND%20(trial%20OR%20randomized%20OR%20%22systematic%20review%22%20OR%20meta-analysis)%20AND%20humans&format=json&pageSize=25&sort_date=y",
    # --- ЖКТ ---
    # "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(%22mineral%20water%22%20OR%20bicarbonate%20water%20OR%20sulfate%20water)%20AND%20(constipation%20OR%20dyspepsia)%20AND%20(trial%20OR%20randomized%20OR%20%22systematic%20review%22)&format=json&pageSize=25&sort_date=y",
    # --- Метаболизм ---
    # "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(%22mineral%20water%22%20OR%20bicarbonate%20water)%20AND%20(metabolic%20OR%20glucose%20OR%20lipid%20OR%20cardiometabolic)%20AND%20(trial%20OR%20randomized%20OR%20%22systematic%20review%22)&format=json&pageSize=25&sort_date=y",
    # --- Урология ---
    # "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(%22mineral%20water%22%20OR%20alkaline%20water)%20AND%20(nephrolithiasis%20OR%20urolithiasis)%20AND%20(trial%20OR%20randomized%20OR%20%22systematic%20review%22)&format=json&pageSize=25&sort_date=y",
    # --- Гидратация ---
    # "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(hydration%20OR%20%22water%20intake%22)%20AND%20(outcomes%20OR%20blood%20pressure%20OR%20migraine)%20AND%20(trial%20OR%20randomized%20OR%20%22systematic%20review%22)&format=json&pageSize=25&sort_date=y",
    # --- Азия ---
    # Japan
    # "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(balneotherapy%20OR%20%22hot%20spring%22)%20AND%20AFF:%22Japan%22%20AND%20(trial%20OR%20clinical%20OR%20randomized)&format=json&pageSize=25&sort_date=y",
    # Korea
    # "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(%22mineral%20water%22%20OR%20balneotherapy)%20AND%20AFF:%22Korea%22%20AND%20(trial%20OR%20clinical)&format=json&pageSize=25&sort_date=y",
    # China
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(%22mineral%20water%22%20OR%20balneotherapy)%20AND%20AFF:%22China%22%20AND%20(trial%20OR%20clinical)&format=json&pageSize=25&sort_date=y",
    # India
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=(balneotherapy%20OR%20hydrotherapy)%20AND%20AFF:%22India%22%20AND%20(trial%20OR%20clinical)&format=json&pageSize=25&sort_date=y",
]

TRIALS_FEEDS = []
NEWS_FEEDS = []

ALL_FEEDS = SCIENCE_FEEDS + TRIALS_FEEDS + NEWS_FEEDS
