"""
Основной пайплайн обработки публикаций.
"""
from typing import List

from ..domain.filtering import is_fresh, is_relevant
from ..domain.models import Publication
from ..domain.scoring import classify_bucket, detect_region, score_publication
from ..ports.notifier import Notifier
from ..ports.publications_api import PublicationsAPI
from ..ports.repository import Repository


class ProcessingPipeline:
    """Пайплайн обработки публикаций."""
    
    def __init__(
        self,
        publications_api: PublicationsAPI,
        repository: Repository,
        notifier: Notifier,
        chat_id: str,
        topic_map: dict,
        include_terms: List[str],
        exclude_terms: List[str],
        max_age_days: int,
        score_threshold: int,
        editorial_mode: bool = True,
        debug_mode: bool = False
    ):
        """
        Инициализирует пайплайн.
        
        Args:
            publications_api: API для получения публикаций
            repository: Репозиторий для хранения данных
            notifier: Уведомитель для отправки сообщений
            chat_id: ID чата для отправки сообщений
            topic_map: Маппинг bucket/region на message_thread_id
            include_terms: Термины для включения
            exclude_terms: Термины для исключения
            max_age_days: Максимальный возраст публикации в днях
            score_threshold: Минимальный score для публикации
            editorial_mode: Включить редакционный режим фильтрации
            debug_mode: Включить debug-режим
        """
        self.publications_api = publications_api
        self.repository = repository
        self.notifier = notifier
        self.chat_id = chat_id
        self.topic_map = topic_map
        self.include_terms = include_terms
        self.exclude_terms = exclude_terms
        self.max_age_days = max_age_days
        self.score_threshold = score_threshold
        self.editorial_mode = editorial_mode
        self.debug_mode = debug_mode
    
    def process_cycle(self) -> int:
        """
        Выполняет один цикл обработки: сбор → фильтр → форматирование → отправка.
        
        Returns:
            int: Количество обработанных новых публикаций
        """
        import time
        
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Проверка новых публикаций...")
        
        # Получаем публикации
        publications = self.publications_api.fetch_publications()
        print(f"Найдено публикаций: {len(publications)}")
        
        new_count = 0
        filtered_count = 0
        
        for publication in publications:
            try:
                # Создаем fingerprint для дедупликации
                fingerprint = self.repository.make_fingerprint(publication.title, publication.url)
                
                # Проверяем, не обрабатывали ли мы уже эту публикацию
                if self.repository.already_seen(fingerprint):
                    print(f"⊘ Отфильтровано (уже обработано): {publication.title[:60]}...")
                    filtered_count += 1
                    continue
                
                # Редакционный режим: фильтрация
                if self.editorial_mode:
                    # Проверка релевантности
                    if not is_relevant(publication, self.include_terms, self.exclude_terms):
                        if self.debug_mode:
                            scoring_result = score_publication(publication)
                            print(f"\n[DEBUG] Score breakdown для: {publication.title[:60]}...")
                            print(f"  Score: {scoring_result.score}")
                            print(f"  Reasons: {', '.join(scoring_result.reasons) if scoring_result.reasons else 'none'}")
                            print("  Status: ⊘ EXCLUDED (не релевантно)")
                        filtered_count += 1
                        continue
                    
                    # Проверка свежести
                    if not is_fresh(publication, self.max_age_days):
                        if self.debug_mode:
                            scoring_result = score_publication(publication)
                            print(f"\n[DEBUG] Score breakdown для: {publication.title[:60]}...")
                            print(f"  Score: {scoring_result.score}")
                            print(f"  Reasons: {', '.join(scoring_result.reasons) if scoring_result.reasons else 'none'}")
                            print("  Status: ⊘ NOT_FRESH (не свежая)")
                        filtered_count += 1
                        continue
                    
                    # Проверка score
                    scoring_result = score_publication(publication)
                    
                    if self.debug_mode:
                        print(f"\n[DEBUG] Score breakdown для: {publication.title[:60]}...")
                        print(f"  Score: {scoring_result.score}")
                        print(f"  Reasons: {', '.join(scoring_result.reasons) if scoring_result.reasons else 'none'}")
                        print(f"  Threshold: {self.score_threshold}")
                        print(f"  Status: {'PASS' if scoring_result.score >= self.score_threshold else 'FAIL (LOW_SCORE)'}")
                    
                    if scoring_result.score < self.score_threshold:
                        print(f"⊘ LOW_SCORE ({scoring_result.score}): {publication.title[:60]}...")
                        print(f"   Reasons: {', '.join(scoring_result.reasons) if scoring_result.reasons else 'none'}")
                        filtered_count += 1
                        continue
                    
                    # Классификация и определение темы
                    bucket = classify_bucket(publication)
                    region = detect_region(publication)
                    
                    # Определяем topic_key
                    if region == "asia":
                        topic_key = "asia"
                    else:
                        topic_key = bucket
                    
                    # Получаем message_thread_id
                    message_thread_id = self.topic_map.get(topic_key, self.topic_map.get("general", 0))
                    
                    # Добавляем метаданные в публикацию
                    publication.bucket = bucket
                    publication.score = scoring_result.score
                    publication.region = region
                
                # Форматируем сообщение
                message_text = self._format_message(publication)
                
                # Отправляем сообщение
                if self.notifier.send(self.chat_id, message_thread_id, message_text, topic_key):
                    print(f"✓ Отправлено: {publication.title[:50]}...")
                    if self.debug_mode and self.editorial_mode:
                        print(f"  [DEBUG] Score: {scoring_result.score}, Reasons: {', '.join(scoring_result.reasons) if scoring_result.reasons else 'none'}")
                    new_count += 1
                else:
                    print(f"✗ Ошибка отправки: {publication.title[:50]}...")
                
                # Помечаем публикацию как обработанную
                url = publication.url or ""
                published_at = publication.published_at or (str(publication.year) if publication.year else "")
                self.repository.mark_seen(fingerprint, url, published_at)
            
            except Exception as e:
                print(f"Ошибка при обработке публикации: {e}")
                continue
        
        print(f"Обработано новых публикаций: {new_count}")
        if filtered_count > 0:
            print(f"Отфильтровано публикаций: {filtered_count}")
        
        return new_count
    
    def _format_message(self, publication: Publication) -> str:
        """
        Форматирует публикацию в текст сообщения.
        
        Args:
            publication: Публикация для форматирования
        
        Returns:
            str: Отформатированный текст сообщения
        """
        message = f"📰 {publication.title}\n\n"
        
        if publication.bucket:
            bucket_display = publication.bucket.capitalize()
            message += f"Тип: {bucket_display}\n"
        
        message += f"🔗 Источник: {publication.source}\n"
        
        if publication.published_at:
            message += f"📅 Дата: {publication.published_at}\n"
        
        summary = publication.abstract or publication.summary
        if summary:
            summary_clean = " ".join(summary.split())
            if len(summary_clean) > 400:
                summary_clean = summary_clean[:400].rsplit(" ", 1)[0] + "..."
            message += f"\n{summary_clean}\n"
        
        if publication.url:
            message += f"\n🔗 {publication.url}"
        
        return message
