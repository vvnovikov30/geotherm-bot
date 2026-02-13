# GeoTherm Bot - Архитектура

## Структура проекта

Проект организован в слоистую архитектуру (Clean Architecture / Hexagonal Architecture):

```
src/geotherm_bot/
├── domain/              # Доменная логика (бизнес-правила)
│   ├── models.py       # Модели данных (Publication, ScoringResult)
│   ├── filtering.py    # Фильтрация (релевантность, свежесть)
│   ├── scoring.py      # Скоринг публикаций
│   └── rules.py        # Правила скоринга
│
├── ports/              # Порты (интерфейсы)
│   ├── publications_api.py  # Интерфейс для получения публикаций
│   ├── repository.py        # Интерфейс для хранения данных
│   └── notifier.py          # Интерфейс для отправки уведомлений
│
├── adapters/           # Адаптеры (реализации портов)
│   ├── europepmc/      # Адаптер для Europe PMC API
│   ├── telegram/       # Адаптер для Telegram Bot API
│   ├── storage/        # Адаптеры для хранения
│   │   └── sqlite_seen.py
│   └── eurasia_discovery/  # Модуль для поиска на сайтах Евразии
│       ├── queries.py      # Генерация запросов
│       └── provider.py     # Провайдер публикаций
│
└── app/                # Приложение
    └── pipeline.py     # Основной пайплайн обработки
```

## Компоненты

### Domain (Доменная логика)

- **models.py**: Модели данных (`Publication`, `QuerySpec`, `ScoreResult`, `FilterDecision`)
- **filtering.py**: Логика фильтрации (релевантность, свежесть)
- **scoring.py**: Логика скоринга и классификации
- **rules.py**: Правила скоринга (вынесены отдельно для переиспользования)

### Ports (Интерфейсы)

- **publications_api.py**: Интерфейс для получения публикаций из различных источников
- **repository.py**: Интерфейс для хранения данных (дедупликация)
- **notifier.py**: Интерфейс для отправки уведомлений

### Adapters (Реализации)

- **europepmc/provider.py**: Реализация `PublicationsAPI` для Europe PMC
- **telegram/notifier.py**: Реализация `Notifier` для Telegram
- **storage/sqlite_seen.py**: Реализация `Repository` для SQLite
- **eurasia_discovery/**: Модуль для поиска на сайтах Евразии
  - Генерирует `QuerySpec` и ссылки для проверки
  - Сохраняет результаты как `Publication` для скоринга

### App (Приложение)

- **pipeline.py**: Основной пайплайн обработки публикаций
  - Получение публикаций из источников
  - Фильтрация (релевантность, свежесть, score)
  - Классификация и определение темы
  - Отправка уведомлений

## Использование

```python
from geotherm_bot.domain.models import Publication
from geotherm_bot.adapters.europepmc.provider import EuropePMCProvider
from geotherm_bot.adapters.telegram.notifier import TelegramNotifier
from geotherm_bot.adapters.storage.sqlite_seen import SQLiteSeenRepository
from geotherm_bot.app.pipeline import ProcessingPipeline

# Инициализация компонентов
provider = EuropePMCProvider(feed_urls=["..."])
repository = SQLiteSeenRepository(db_path="db/seen.db")
notifier = TelegramNotifier(bot_token="...", dry_run=False)

# Создание пайплайна
pipeline = ProcessingPipeline(
    publications_api=provider,
    repository=repository,
    notifier=notifier,
    chat_id="...",
    topic_map={...},
    include_terms=[...],
    exclude_terms=[...],
    max_age_days=120,
    score_threshold=3
)

# Запуск обработки
pipeline.process_cycle()
```

## Eurasia Discovery

Модуль `eurasia_discovery` предназначен для поиска публикаций на сайтах:
- EastView
- CyberLeninka
- eLIBRARY
- VINITI

В текущей реализации модуль:
1. Генерирует `QuerySpec` с ключевыми словами
2. Создает ссылки для ручной проверки на сайтах
3. Предоставляет метод `create_publication_from_result()` для создания `Publication` из результатов

В будущем может быть добавлен автоматический парсинг результатов.
