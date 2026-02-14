#!/usr/bin/env python3
"""
Production-safe scheduler для запуска RefreshService.

Запускает refresh job каждые N часов с логированием и graceful shutdown.
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Добавляем корень проекта в sys.path для импортов
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from apscheduler.events import (  # noqa: E402
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
)
from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402
from apscheduler.triggers.interval import IntervalTrigger  # noqa: E402

from src.geotherm_bot.adapters.eurasia_discovery.provider import (  # noqa: E402
    EurasiaDiscoveryProvider,
)
from src.geotherm_bot.adapters.storage.sqlite_queue import (  # noqa: E402
    SQLiteContentQueue,
)
from src.geotherm_bot.adapters.storage.sqlite_topics import (  # noqa: E402
    SQLiteTopicRegistry,
)
from src.geotherm_bot.app.query_builder import QueryBuilder  # noqa: E402
from src.geotherm_bot.app.refresh_service import RefreshService  # noqa: E402
from src.geotherm_bot.app.region import RegionResolver  # noqa: E402
from src.geotherm_bot.domain.filtering import is_fresh, is_relevant  # noqa: E402
from src.geotherm_bot.domain.models import (  # noqa: E402
    FilterDecision,
    Publication,
    ScoreResult,
)
from src.geotherm_bot.domain.scoring import score_publication  # noqa: E402

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Конфигурация из env
REFRESH_EVERY_HOURS = int(os.getenv("REFRESH_EVERY_HOURS", "6"))


def parse_bool(value: str | None) -> bool:
    """
    Парсит значение в булевый флаг.

    True для (case-insensitive): "1", "true", "yes", "y", "on"
    False для: пусто/не задано, "0", "false", "no", "off"
    """
    if not value:
        return False
    normalized = value.strip().lower()
    return normalized in ("1", "true", "yes", "y", "on")


# Для обратной совместимости
def parse_run_once(value: str | None) -> bool:
    """Парсит значение RUN_ONCE в булевый флаг (алиас для parse_bool)."""
    return parse_bool(value)


RUN_ONCE_RAW = os.getenv("RUN_ONCE")
RUN_ONCE = parse_bool(RUN_ONCE_RAW)
DB_PATH = os.getenv("DB_PATH", "db/geotherm.db")
CHAT_ID = int(os.getenv("CHAT_ID", "1"))
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "120"))

# Publish configuration
PUBLISH_EVERY_HOURS = int(os.getenv("PUBLISH_EVERY_HOURS", "3"))
ENABLE_PUBLISH = parse_bool(os.getenv("ENABLE_PUBLISH"))
PUBLISH_DRY_RUN = parse_bool(os.getenv("PUBLISH_DRY_RUN", "1"))  # default True
PUBLISH_MAX_ITEMS = int(os.getenv("PUBLISH_MAX_ITEMS", "1"))
ENABLE_PUBLISH_APPLY = parse_bool(os.getenv("ENABLE_PUBLISH_APPLY", "0"))

# Термины для фильтрации (из config.py или env)
INCLUDE_TERMS = [
    "geothermal",
    "thermal",
    "spring",
    "mineral",
    "balneotherapy",
    "spa",
    "wellness",
    "resort",
    "geochemical",
    "chemistry",
]
EXCLUDE_TERMS = ["сточные", "wastewater"]

# Глобальные переменные для graceful shutdown
scheduler = None
shutdown_requested = False
current_job_running = False


def create_filtering_function() -> Callable[[Publication], FilterDecision]:
    """Создает функцию фильтрации на основе domain логики."""

    def filtering(pub: Publication) -> FilterDecision:
        """Функция фильтрации для RefreshService."""
        if not is_relevant(pub, INCLUDE_TERMS, EXCLUDE_TERMS):
            return FilterDecision(passed=False, reasons=["not_relevant"])

        if not is_fresh(pub, MAX_AGE_DAYS):
            return FilterDecision(passed=False, reasons=["not_fresh"])

        return FilterDecision(passed=True, reasons=[])

    return filtering


def create_scoring_function() -> Callable[[Publication], ScoreResult]:
    """Создает функцию скоринга на основе domain логики."""

    def scoring(pub: Publication) -> ScoreResult:
        """Функция скоринга для RefreshService."""
        return score_publication(pub)

    return scoring


def create_refresh_service() -> RefreshService:
    """Создает и инициализирует RefreshService с зависимостями."""
    # Инициализация БД
    topic_registry = SQLiteTopicRegistry(db_path=DB_PATH)
    topic_registry.init()

    content_queue = SQLiteContentQueue(db_path=DB_PATH)
    content_queue.init()

    # Инициализация компонентов
    region_resolver = RegionResolver()
    query_builder = QueryBuilder()

    # Провайдер: используем EurasiaDiscoveryProvider
    # EuropePMC может быть NotImplemented, но это не должно валить процесс
    provider = EurasiaDiscoveryProvider()
    logger.info("Using EurasiaDiscoveryProvider")

    # Функции фильтрации и скоринга
    filtering = create_filtering_function()
    scoring = create_scoring_function()

    return RefreshService(
        topic_registry=topic_registry,
        content_queue=content_queue,
        region_resolver=region_resolver,
        query_builder=query_builder,
        provider=provider,
        filtering=filtering,
        scoring=scoring,
    )


def run_refresh_job():
    """Запускает refresh job с логированием."""
    global current_job_running, shutdown_requested

    if shutdown_requested:
        logger.info("Shutdown requested, skipping refresh job")
        return

    current_job_running = True
    start_time = time.time()

    try:
        logger.info(
            f"Starting refresh job (interval={REFRESH_EVERY_HOURS}h, "
            f"run_once={RUN_ONCE}, max_age_days={MAX_AGE_DAYS})"
        )

        refresh_service = create_refresh_service()
        now = datetime.now(timezone.utc)

        # Запускаем refresh
        # Оборачиваем в try-except для обработки возможных ошибок провайдера
        try:
            stats = refresh_service.refresh_queue_for_chat(chat_id=CHAT_ID, now=now)
        except NotImplementedError as e:
            # EuropePMC может бросать NotImplementedError
            logger.warning(
                f"Provider raised NotImplementedError (expected for some providers): {e}"
            )
            # Возвращаем пустую статистику
            stats = {
                "topics_seen": 0,
                "queries_built": 0,
                "pubs_fetched": 0,
                "pubs_passed": 0,
                "items_enqueued": 0,
                "items_deduped": 0,
                "topics_skipped_full": 0,
            }

        duration = time.time() - start_time

        # Логируем результаты
        logger.info(f"Refresh job completed in {duration:.2f}s")
        logger.info("Refresh metrics:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Refresh job failed after {duration:.2f}s: {e}", exc_info=True)
    finally:
        current_job_running = False


def run_publish_tick():
    """Запускает publish tick: dry-run (Phase 1) или apply (Phase 2)."""
    global shutdown_requested

    if shutdown_requested:
        logger.info("Shutdown requested, skipping publish tick")
        return

    start_time = time.time()
    timestamp = datetime.now(timezone.utc).isoformat()
    now_utc = datetime.now(timezone.utc)

    try:
        logger.info(
            f"Starting publish tick (dry_run={PUBLISH_DRY_RUN}, "
            f"max_items={PUBLISH_MAX_ITEMS}) at {timestamp}"
        )

        # Инициализация БД
        topic_registry = SQLiteTopicRegistry(db_path=DB_PATH)
        topic_registry.init()

        content_queue = SQLiteContentQueue(db_path=DB_PATH)
        content_queue.init()

        # Получаем список enabled топиков
        topics = topic_registry.list_topics(chat_id=CHAT_ID, enabled_only=True)

        # Фильтруем топики с новыми элементами и сохраняем count_new ДО
        candidates = []
        counts_before = {}
        for topic in topics:
            count = content_queue.count_new(topic.id)
            if count > 0:
                candidates.append(topic)
                counts_before[topic.id] = count

        if not candidates:
            logger.info("No eligible items: no topics with new items")
            duration = time.time() - start_time
            logger.info(f"Publish tick completed in {duration:.2f}s")
            return

        # Сортируем по fairness: NULL last_post_at первыми,
        # затем по last_post_at ASC, затем по created_at ASC
        epoch_utc = datetime(1970, 1, 1, tzinfo=timezone.utc)
        candidates.sort(
            key=lambda t: (
                t.last_post_at is not None,  # False (None) первыми
                t.last_post_at or epoch_utc,  # Затем по времени
                t.created_at,  # Затем по created_at
            )
        )

        if PUBLISH_DRY_RUN:
            # Phase 1: Dry-run mode (read-only, invariants, smoke check)
            items_logged = 0
            for topic in candidates:
                if items_logged >= PUBLISH_MAX_ITEMS:
                    break

                # Проверяем count_new ДО peek_best_new
                before_count = content_queue.count_new(topic.id)
                # Получаем лучший элемент (read-only, не меняет БД)
                item = content_queue.peek_best_new(topic.id)
                # Проверяем count_new ПОСЛЕ peek_best_new
                after_count = content_queue.count_new(topic.id)

                if item is None:
                    continue

                # Верификация: count_new не должен измениться
                if before_count != after_count:
                    logger.error(
                        f"Dry-run invariant violated: count_new changed! "
                        f"topic_id={topic.id} before={before_count} "
                        f"after={after_count}"
                    )
                else:
                    logger.info(
                        f"Dry-run verified: no DB mutation (topic_id={topic.id}, "
                        f"count={before_count})"
                    )

                items_logged += 1
                logger.info("DRY RUN: would publish item")
                logger.info(f"  chat_id: {topic.chat_id}")
                logger.info(f"  thread_id: {topic.message_thread_id}")
                logger.info(f"  external_id: {item.external_id}")
                logger.info(f"  score: {item.score}")
                if item.title:
                    logger.info(f"  title: {item.title}")

            if items_logged == 0:
                logger.info("No eligible items: no items found in candidates")

            # Smoke-проверка: count_new не должен измениться
            smoke_passed = True
            for topic_id, count_before in counts_before.items():
                count_after = content_queue.count_new(topic_id)
                if count_before != count_after:
                    smoke_passed = False
                    logger.warning(
                        f"SMOKE CHECK FAILED: topic_id={topic_id} "
                        f"count changed from {count_before} to {count_after}"
                    )
            if smoke_passed:
                logger.info("SMOKE CHECK PASSED: all topic counts unchanged")
        else:
            # Phase 2: Apply mode (DB mutations)
            items_posted = 0
            for topic in candidates:
                if items_posted >= PUBLISH_MAX_ITEMS:
                    break

                # Получаем count_new ДО claim
                before_count = content_queue.count_new(topic.id)
                # Атомарно захватываем лучший элемент
                item = content_queue.claim_best_new(topic.id)

                if item is None:
                    if before_count > 0:
                        logger.info("No claimable items (already claimed by another " "worker)")
                    continue

                if item.id is None:
                    logger.error(
                        f"QueueItem.id is None for topic_id={topic.id}, "
                        f"external_id={item.external_id}"
                    )
                    continue

                logger.info("CLAIMED item for publish (status=new->posting)")

                # Логируем публикацию (без Telegram)
                logger.info("PUBLISHED (no-telegram):")
                logger.info(f"  chat_id: {topic.chat_id}")
                logger.info(f"  thread_id: {topic.message_thread_id}")
                logger.info(f"  external_id: {item.external_id}")
                logger.info(f"  score: {item.score}")
                if item.title:
                    logger.info(f"  title: {item.title}")

                # Применяем DB мутации
                try:
                    content_queue.mark_posted(item.id, posted_at=now_utc)
                    topic_registry.touch_last_post(topic.id, now_utc)
                except Exception as e:
                    logger.exception(f"Failed to mark_posted or touch_last_post: {e}")
                    # Автоматически освобождаем захват
                    released = content_queue.release_posting(item.id)
                    if released:
                        logger.info(f"Released claim (posting->new) for item " f"id={item.id}")
                    else:
                        logger.warning(
                            f"Failed to release claim for item id={item.id} "
                            "(maybe already posted or missing)"
                        )
                    continue

                # Верификация после применения
                after_count = content_queue.count_new(topic.id)
                if before_count - 1 != after_count:
                    logger.warning(
                        f"Verification: count_new decreased unexpectedly "
                        f"topic_id={topic.id} before={before_count} "
                        f"after={after_count} (expected {before_count - 1})"
                    )
                else:
                    logger.info(
                        f"Verified: count_new decreased correctly "
                        f"(topic_id={topic.id} {before_count} -> {after_count})"
                    )

                # Проверяем обновление last_post_at
                updated_topic = topic_registry.get_topic(
                    chat_id=topic.chat_id,
                    message_thread_id=topic.message_thread_id,
                )
                if updated_topic is None:
                    logger.error(
                        f"Failed to retrieve topic after touch_last_post "
                        f"(chat_id={topic.chat_id}, "
                        f"thread_id={topic.message_thread_id})"
                    )
                elif updated_topic.last_post_at is None:
                    logger.error(f"last_post_at not updated for topic_id={topic.id}")
                else:
                    # Проверяем, что время обновлено (с точностью до секунды)
                    time_diff = abs((updated_topic.last_post_at - now_utc).total_seconds())
                    if time_diff > 1:
                        logger.warning(
                            f"last_post_at time mismatch: expected ~{now_utc}, "
                            f"got {updated_topic.last_post_at} "
                            f"(diff={time_diff}s)"
                        )
                    else:
                        logger.info(f"Verified: last_post_at updated " f"(topic_id={topic.id})")

                items_posted += 1

            if items_posted == 0:
                logger.info("No eligible items: no items found in candidates")

            # Логируем итоговую статистику
            logger.info(f"Apply summary: items_posted={items_posted}")

        duration = time.time() - start_time
        logger.info(f"Publish tick completed in {duration:.2f}s")

    except Exception as e:
        duration = time.time() - start_time
        logger.exception(f"Publish tick failed after {duration:.2f}s: {e}")


def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown."""
    global shutdown_requested, scheduler

    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True

    if scheduler:
        # Останавливаем scheduler (не запускает новые job)
        scheduler.shutdown(wait=False)

        # Ждём завершения текущей job (grace period: 60 секунд)
        if current_job_running:
            logger.info("Waiting for current job to finish (max 60s)...")
            for _ in range(60):
                if not current_job_running:
                    break
                time.sleep(1)
            else:
                logger.warning("Grace period expired, job may still be running")

    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    """Главная функция scheduler."""
    global scheduler

    logger.info("=" * 80)
    logger.info("Geotherm Bot Scheduler")
    logger.info("=" * 80)
    logger.info("Configuration:")
    logger.info(f"  Refresh interval: {REFRESH_EVERY_HOURS} hours")
    logger.info(f"  Run once (raw='{RUN_ONCE_RAW}'): {RUN_ONCE}")
    logger.info(f"  DB path: {DB_PATH}")
    logger.info(f"  Chat ID: {CHAT_ID}")
    logger.info(f"  Max age days: {MAX_AGE_DAYS}")
    logger.info("Publish configuration:")
    logger.info(f"  ENABLE_PUBLISH: {ENABLE_PUBLISH}")
    logger.info(f"  PUBLISH_DRY_RUN: {PUBLISH_DRY_RUN}")
    logger.info(f"  ENABLE_PUBLISH_APPLY: {ENABLE_PUBLISH_APPLY}")
    logger.info(f"  PUBLISH_EVERY_HOURS: {PUBLISH_EVERY_HOURS}")
    logger.info(f"  PUBLISH_MAX_ITEMS: {PUBLISH_MAX_ITEMS}")
    logger.info("=" * 80)

    # Валидация: если PUBLISH_DRY_RUN=False, требуется ENABLE_PUBLISH_APPLY=True
    if not PUBLISH_DRY_RUN and not ENABLE_PUBLISH_APPLY:
        logger.error("Refusing to run with PUBLISH_DRY_RUN=0 without " "ENABLE_PUBLISH_APPLY=1")
        sys.exit(2)

    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Создаём scheduler
    scheduler = BlockingScheduler()

    # Запускаем первый job сразу
    logger.info("Running initial refresh job...")
    run_refresh_job()

    if RUN_ONCE:
        logger.info("Run once mode: exiting after initial refresh")
        return 0

    # Настраиваем периодический запуск с безопасной конфигурацией
    trigger = IntervalTrigger(hours=REFRESH_EVERY_HOURS)
    misfire_grace_seconds = 3600  # 1 час - разумно для интервала в часы
    scheduler.add_job(
        run_refresh_job,
        trigger=trigger,
        id="refresh_job",
        name="Refresh queue for chat",
        max_instances=1,  # Не запускать параллельно
        coalesce=True,  # Склеивать пропущенные запуски
        misfire_grace_time=misfire_grace_seconds,  # Пропускать запуски > 1 час
        replace_existing=True,  # Заменять job при рестарте
    )

    # Общий event listener для логирования событий job
    def job_event_listener(event):
        """Логирует события job: пропущенные запуски и overlap."""
        if event.code == EVENT_JOB_MISSED:
            logger.warning(
                f"Job {event.job_id} missed scheduled execution time. "
                f"Next run: {event.scheduled_run_time}"
            )
        elif event.code == EVENT_JOB_MAX_INSTANCES:
            logger.warning(
                f"Job {event.job_id} skipped due to max_instances=1 "
                f"(previous run still executing). Scheduled: {event.scheduled_run_time}"
            )

    scheduler.add_listener(job_event_listener, EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)

    # Регистрируем publish job если включен
    if ENABLE_PUBLISH:
        publish_trigger = IntervalTrigger(hours=PUBLISH_EVERY_HOURS)
        publish_misfire_grace_seconds = 3600  # 1 час
        scheduler.add_job(
            run_publish_tick,
            trigger=publish_trigger,
            id="publish_job",
            name="Publish tick",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=publish_misfire_grace_seconds,
            replace_existing=True,
        )
        logger.info(f"Publish job registered. Will run every {PUBLISH_EVERY_HOURS} hours.")
    else:
        logger.info("Publish disabled")

    logger.info(f"Scheduler started. Refresh will run every {REFRESH_EVERY_HOURS} hours.")
    logger.info(
        "Job safety settings: max_instances=1, coalesce=True, "
        f"misfire_grace_time={misfire_grace_seconds}s, replace_existing=True"
    )
    logger.info("Press Ctrl+C to stop")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user")
        return 0

    return 0


if __name__ == "__main__":
    exit(main())
