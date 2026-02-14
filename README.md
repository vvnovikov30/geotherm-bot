# GeoTherm Bot

Минимальный Telegram-бот для агрегации RSS-лент по теме geothermal / hot springs / geysers с дедупликацией и отправкой в темы (Topics).

## Возможности

- 📰 Агрегация новостей из нескольких RSS-лент
- 🔍 Дедупликация через SQLite базу данных
- 🎯 Автоматическая маршрутизация по темам на основе ключевых слов
- 💬 Отправка сообщений в конкретные Telegram Topics
- ⏰ Работа в режиме polling с настраиваемым интервалом

## Структура проекта

```
geo_therm_bot/
├── bot.py              # Основной файл с polling логикой
├── config.py           # Конфигурация и загрузка переменных окружения
├── rss_collector.py    # Сбор RSS-новостей
├── storage.py          # Работа с SQLite для дедупликации
├── router.py           # Маршрутизация по темам
├── formatter.py        # Форматирование сообщений
├── requirements.txt    # Зависимости проекта
├── .env.example        # Пример файла с переменными окружения
├── README.md           # Документация
└── db/                 # Папка для SQLite базы данных
    └── seen.db         # База данных (создается автоматически)
```

## Установка и запуск на Windows

### 1. Создание виртуального окружения

```powershell
py -m venv .venv
```

### 2. Активация виртуального окружения

```powershell
.\.venv\Scripts\activate
```

### 3. Установка зависимостей

```powershell
pip install -r requirements.txt
```

### 3.1. Installation (development mode)

Install in editable mode:

```powershell
pip install -e .
```

This enables direct import:

```python
import geotherm_bot
```

No PYTHONPATH needed.

### 4. Настройка конфигурации

Создайте файл `.env` на основе `.env.example`:

```powershell
copy .env.example .env
```

Откройте `.env` и заполните необходимые значения:

```env
BOT_TOKEN=ваш_токен_от_BotFather
CHAT_ID=ваш_chat_id
POLL_SECONDS=300
TOPIC_ICELAND=1111
TOPIC_JAPAN=2222
TOPIC_GENERAL=3333
DRY_RUN=false
```

**Опциональные параметры:**
- `DRY_RUN=true` - включить режим тестирования (сообщения не отправляются)

### 5. Запуск бота

```powershell
python bot.py
```

## Режимы запуска

### Режим --once

Выполняет один цикл обработки (сбор → фильтр → форматирование) и завершается:

```powershell
python bot.py --once
```

Полезно для:
- Тестирования конфигурации
- Ручного запуска через cron/task scheduler
- Отладки без бесконечного цикла

### Режим DRY_RUN

Вместо отправки сообщений в Telegram выводит информацию в консоль. Активируется через переменную окружения в `.env`:

```env
DRY_RUN=true
```

В этом режиме для каждого сообщения выводится:
- **Topic key** (ключ темы: iceland, japan, general)
- **message_thread_id** (ID темы в Telegram)
- **Итоговый текст сообщения**

Пример вывода:
```
============================================================
DRY_RUN: Сообщение не отправлено
Topic key: general
message_thread_id: 3333
Текст сообщения:
------------------------------------------------------------
📰 Заголовок новости

🔗 Источник: Medical Xpress
📅 Дата: 2024-01-15 10:30:00

🔗 https://example.com/news
============================================================
```

**Примечание:** В режиме DRY_RUN не требуется указывать `BOT_TOKEN` и `CHAT_ID` в `.env`.

### Подробные логи фильтрации

Бот выводит подробную информацию о том, почему элементы были отфильтрованы:

- `⊘ Отфильтровано (уже обработано): ...` - элемент уже был обработан ранее (дедупликация)

Логи помогают понять, какие новости пропускаются и почему.

## Как получить необходимые параметры

### BOT_TOKEN

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен в `.env`

### CHAT_ID

**Для группы:**
1. Добавьте бота в группу
2. Отправьте сообщение в группу
3. Откройте в браузере: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
4. Найдите `"chat":{"id":-123456789}` - это ваш CHAT_ID (отрицательное число для групп)

**Для канала:**
1. Создайте канал
2. Добавьте бота как администратора
3. Отправьте сообщение в канал
4. Используйте тот же метод через getUpdates

### message_thread_id (TOPIC_ICELAND, TOPIC_JAPAN, TOPIC_GENERAL)

1. Создайте группу с включенными темами (Topics)
2. Создайте нужные темы в группе
3. Отправьте сообщение в конкретную тему
4. Используйте бота [@userinfobot](https://t.me/userinfobot) или API:
   - Откройте: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   - Найдите `"message_thread_id":123` в ответе
   - Это и есть ID темы

**Альтернативный способ:**
- Используйте библиотеку `python-telegram-bot` для получения thread_id программно
- Или отправьте тестовое сообщение через бота и проверьте getUpdates

## Настройка RSS-лент

По умолчанию используются медицинские RSS-ленты из `config.py`:
- Medical Xpress - медицинские новости и исследования
- Medscape - медицинские новости
- MedlinePlus - медицинская информация от NIH
- Europe PMC - европейские медицинские публикации

Для настройки собственных лент:

1. Отредактируйте `config.py` и измените список `RSS_FEEDS`
2. Или добавьте в `.env`:
   ```
   RSS_FEEDS=https://example.com/feed1.xml,https://example.com/feed2.xml
   ```

## Как использовать RSS-каналы по медицине

Бот по умолчанию настроен на сбор новостей из медицинских RSS-каналов. Вы можете настроить собственные RSS-ленты для отслеживания конкретных медицинских тем.

### Создание RSS-лент из PubMed

PubMed предоставляет возможность создавать RSS-ленты на основе поисковых запросов. Это позволяет получать уведомления о новых публикациях по интересующим темам.

#### Примеры запросов PubMed для RSS:

**1. Поиск по ключевым словам:**
```
https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=geothermal+therapy&limit=10&utm_campaign=pubmed-2&fc=20240101123456
```

**2. Поиск по конкретной теме (например, hot springs):**
```
https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=hot+springs+therapy&limit=10&utm_campaign=pubmed-2&fc=20240101123456
```

**3. Поиск по медицинской специальности:**
```
https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=thermal+medicine&limit=10&utm_campaign=pubmed-2&fc=20240101123456
```

**4. Комбинированный поиск (например, геотермальная энергия + медицина):**
```
https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=(geothermal+OR+thermal)+AND+(medicine+OR+therapy)&limit=10&utm_campaign=pubmed-2&fc=20240101123456
```

**5. Поиск по авторам:**
```
https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=Smith+J[Author]&limit=10&utm_campaign=pubmed-2&fc=20240101123456
```

**6. Поиск по дате публикации (последние публикации):**
```
https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=thermal+therapy&filter=datesearch.y_1&limit=10&utm_campaign=pubmed-2&fc=20240101123456
```

#### Как создать собственную RSS-ленту из PubMed:

1. Перейдите на [PubMed](https://pubmed.ncbi.nlm.nih.gov/)
2. Введите поисковый запрос (например: "geothermal medicine" или "hot springs therapy")
3. Нажмите "Search"
4. На странице результатов найдите иконку RSS (обычно в правом верхнем углу)
5. Скопируйте URL RSS-ленты
6. Добавьте его в `config.py` в список `RSS_FEEDS` или в `.env` файл

#### Примеры других медицинских RSS-источников:

- **Nature Medicine**: `https://www.nature.com/nm.rss`
- **The Lancet**: `https://www.thelancet.com/rssfeed/lancet_current.xml`
- **New England Journal of Medicine**: `https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm`
- **Science Daily - Health**: `https://www.sciencedaily.com/rss/health_medicine.xml`

#### Настройка в проекте:

Добавьте созданные RSS-ссылки в `config.py`:

```python
RSS_FEEDS = [
    "https://medicalxpress.com/rss-feed",
    "https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=your+search+query&limit=10",
    # ... другие ленты
]
```

Или через переменную окружения в `.env`:

```env
RSS_FEEDS=https://pubmed.ncbi.nlm.nih.gov/rss/search/1?term=geothermal+therapy&limit=10,https://example.com/other-feed.xml
```

## Маршрутизация по темам

Бот автоматически определяет тему на основе ключевых слов в заголовке:

- `"iceland"` в заголовке → тема `TOPIC_ICELAND`
- `"japan"` в заголовке → тема `TOPIC_JAPAN`
- Иначе → тема `TOPIC_GENERAL`

Для изменения логики маршрутизации отредактируйте функцию `get_topic()` в `router.py`.

## Остановка бота

Нажмите `Ctrl+C` в терминале для корректной остановки.

## Как перенести на VPS (Ubuntu)

### 1. Подключение к серверу

```bash
ssh user@your-server-ip
```

### 2. Установка Python и зависимостей

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

### 3. Клонирование/загрузка проекта

```bash
# Если используете git
git clone <your-repo-url> geotherm-bot
cd geotherm-bot

# Или загрузите файлы через scp/sftp
```

### 4. Создание виртуального окружения

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 6. Настройка .env

```bash
cp .env.example .env
nano .env  # или используйте другой редактор
```

Заполните все необходимые переменные.

### 7. Тестовый запуск

```bash
python3 bot.py
```

Убедитесь, что бот работает корректно.

### 8. Создание systemd сервиса

Создайте файл `/etc/systemd/system/geotherm-bot.service`:

```ini
[Unit]
Description=GeoTherm Telegram Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/geotherm-bot
Environment="PATH=/home/your-username/geotherm-bot/.venv/bin"
ExecStart=/home/your-username/geotherm-bot/.venv/bin/python3 /home/your-username/geotherm-bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Важно:** Замените `your-username` и пути на ваши реальные значения.

### 9. Запуск и управление сервисом

```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable geotherm-bot

# Запуск сервиса
sudo systemctl start geotherm-bot

# Проверка статуса
sudo systemctl status geotherm-bot

# Просмотр логов
sudo journalctl -u geotherm-bot -f
```

### 10. Полезные команды

```bash
# Остановка
sudo systemctl stop geotherm-bot

# Перезапуск
sudo systemctl restart geotherm-bot

# Отключение автозапуска
sudo systemctl disable geotherm-bot
```

## Устранение неполадок

### Бот не отправляет сообщения

- Проверьте правильность `BOT_TOKEN` и `CHAT_ID`
- Убедитесь, что бот добавлен в группу и имеет права на отправку сообщений
- Проверьте, что `message_thread_id` указан правильно для тем

### Ошибки при работе с базой данных

- Убедитесь, что папка `db/` существует и доступна для записи
- Проверьте права доступа к файлу базы данных

### RSS-ленты не загружаются

- Проверьте доступность RSS-лент в браузере
- Убедитесь, что на сервере есть доступ к интернету
- Проверьте формат RSS-лент (должен быть валидный XML)

## Development

### Install dev dependencies

```bash
pip install -r dev-requirements.txt
```

### Run tests

```bash
pytest -q
```

### Run linter

```bash
ruff check .
```

### Format imports automatically

```bash
ruff check . --fix
```

## Publish Tick — Phase 1 Manual Verification (Dry Run)

Phase 1 of the Publish Tick infrastructure is a read-only dry-run implementation with zero side effects. It selects candidate items from the content queue and logs them without modifying the database or sending any messages.

### Environment Variables

Set the following environment variables to enable and configure publish tick:

```env
ENABLE_PUBLISH=1
PUBLISH_DRY_RUN=1
PUBLISH_MAX_ITEMS=1
```

### Manual Verification Methods

#### Method 1: Direct Function Invocation

The fastest way to test publish tick without waiting for scheduler intervals:

**PowerShell (Windows):**
```powershell
$env:ENABLE_PUBLISH="1"
$env:PUBLISH_DRY_RUN="1"
$env:PUBLISH_MAX_ITEMS="1"
python -c "from scripts.run_scheduler import run_publish_tick; run_publish_tick()"
```

**Linux/macOS (bash):**
```bash
export ENABLE_PUBLISH=1
export PUBLISH_DRY_RUN=1
export PUBLISH_MAX_ITEMS=1
python -c "from scripts.run_scheduler import run_publish_tick; run_publish_tick()"
```

#### Method 2: Scheduler with Short Interval

Run the scheduler with a short publish interval for testing:

**PowerShell (Windows):**
```powershell
$env:ENABLE_PUBLISH="1"
$env:PUBLISH_DRY_RUN="1"
$env:PUBLISH_EVERY_HOURS="0.01"
$env:PUBLISH_MAX_ITEMS="1"
python scripts/run_scheduler.py
```

**Linux/macOS (bash):**
```bash
export ENABLE_PUBLISH=1
export PUBLISH_DRY_RUN=1
export PUBLISH_EVERY_HOURS=0.01
export PUBLISH_MAX_ITEMS=1
python scripts/run_scheduler.py
```

Note: `PUBLISH_EVERY_HOURS=0.01` equals 36 seconds, allowing quick verification.

### Expected Log Output

Successful execution should produce logs matching these patterns:

```
2024-01-15 10:30:00 [INFO] Starting publish tick (dry_run=True, max_items=1) at 2024-01-15T10:30:00.123456+00:00
2024-01-15 10:30:00 [INFO] Dry-run verified: no DB mutation (topic_id=1, count=5)
2024-01-15 10:30:00 [INFO] DRY RUN: would publish item
2024-01-15 10:30:00 [INFO]   chat_id: 1
2024-01-15 10:30:00 [INFO]   thread_id: 123
2024-01-15 10:30:00 [INFO]   external_id: abc123def456
2024-01-15 10:30:00 [INFO]   score: 8
2024-01-15 10:30:00 [INFO]   title: Geothermal Energy Research
2024-01-15 10:30:00 [INFO] SMOKE CHECK PASSED: all topic counts unchanged
2024-01-15 10:30:00 [INFO] Publish tick completed in 0.15s
```

If no eligible items are found:
```
2024-01-15 10:30:00 [INFO] Starting publish tick (dry_run=True, max_items=1) at 2024-01-15T10:30:00.123456+00:00
2024-01-15 10:30:00 [INFO] No eligible items: no topics with new items
2024-01-15 10:30:00 [INFO] Publish tick completed in 0.08s
```

### Success Criteria

Verify the following conditions are met:

- [ ] No exceptions or stack traces in logs
- [ ] No database mutations (all `count_new` values unchanged)
- [ ] Smoke check passes: "SMOKE CHECK PASSED: all topic counts unchanged"
- [ ] Scheduler does not crash or exit unexpectedly
- [ ] Log output includes "Starting publish tick" and "Publish tick completed"
- [ ] If items are found, "DRY RUN: would publish item" appears with required fields

### Troubleshooting

**No eligible items:**
- Ensure the database contains topics with `status='new'` items
- Verify `CHAT_ID` matches the chat ID in your database
- Check that topics are enabled (`enabled=1` in topics table)

**Smoke check fails:**
- This indicates a bug: `peek_best_new()` should not modify the database
- Report the issue with full logs and database state

**Scheduler crashes:**
- Check for Python import errors
- Verify database file exists and is accessible
- Review exception logs for stack traces

## Лицензия

Проект создан для личного использования.
