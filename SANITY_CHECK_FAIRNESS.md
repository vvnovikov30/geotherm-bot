# Sanity-Check: Перенос fairness из ContentQueue в PublishService

## Анализ текущего кода

### A) Зависимости `pick_next_topic_to_post`

**Ответ:** Да, метод имеет сильные зависимости от `topics`:

1. **Делает JOIN с `topics`:** Да (строка 410 в `sqlite_queue.py`):
   ```sql
   FROM topics t
   INNER JOIN content_queue cq ON t.id = cq.topic_id
   ```

2. **Использует поля `topics.last_post_at`:** Да (строки 407, 416-417):
   - Читает `t.last_post_at`
   - Сортирует по `CASE WHEN t.last_post_at IS NULL THEN 0 ELSE 1 END`

3. **Требует schema knowledge о `topics`:** Да:
   - Знает про таблицу `topics`
   - Знает про поля `chat_id`, `enabled`, `last_post_at`
   - Знает про структуру FOREIGN KEY

### B) Нарушение границ ответственности

**Ответ:** Да, явное нарушение:

- **ContentQueue** должен быть "storage for items" (CRUD для `content_queue` и `seen`)
- **TopicRegistry** должен быть "storage for topics" (CRUD для `topics`)
- **Текущая ситуация:** ContentQueue делает JOIN с `topics` и знает о её структуре

Это нарушает принцип разделения ответственности (Separation of Concerns).

### C) Практическая польза SQL

**Ответ:** Да, есть польза, но она не оправдывает нарушение архитектуры:

1. **Производительность:** Один запрос вместо N+1
   - SQL: 1 JOIN запрос
   - Python: `list_topics()` + N `count_new()` запросов

2. **Уменьшение количества запросов:** Да
   - SQL: 1 запрос
   - Python: 1 + N запросов (где N = количество топиков)

3. **Простота:** SQL делает всю работу в одном запросе

**НО:** Для типичного использования (5-10 топиков на чат) N+1 не является проблемой производительности.

### D) Риски переноса

**Ответ:** Есть риски, но они управляемы:

1. **N+1 запросов:** Да, будет `list_topics()` + `count_new()` для каждого топика
   - **Митигация:** Для небольшого количества топиков (<20) это приемлемо
   - **Альтернатива:** Можно добавить метод `count_new_batch(topic_ids: list[int]) -> dict[int, int]` если понадобится

2. **Справедливость при конкурентной публикации:** SQL гарантирует атомарность, в Python нужны транзакции/блокировки
   - **Митигация:** В текущей реализации нет конкурентной публикации (один процесс)
   - **Если понадобится:** Можно использовать транзакции или advisory locks

### E) Соответствие заявленному правилу fairness

**Ответ:** НЕТ, текущая реализация НЕ соответствует fairness:

**Текущая реализация:**
```sql
ORDER BY new_count DESC,  -- ПЕРВЫМ приоритет количества!
         CASE WHEN t.last_post_at IS NULL THEN 0 ELSE 1 END,
         t.last_post_at ASC
```

**Проблема:** Выбирает топик с **наибольшим количеством** элементов первым, а не по времени.

**Правильный fairness должен быть:**
```python
ORDER BY 
    last_post_at IS NULL DESC,  # NULL первыми
    last_post_at ASC,            # Затем по времени
    created_at ASC               # Затем по дате создания
```

**Докстринг говорит "fair pick", но логика не соответствует.**

## ВЫВОД

### ✅ **ПЕРЕНОСИТЬ**

**Причины:**

1. **Архитектурное нарушение:** ContentQueue не должен знать о структуре `topics`
2. **Неправильная логика fairness:** Приоритет количества над временем
3. **Единственное использование:** Метод используется только в `PublishService`
4. **Производительность:** N+1 приемлемо для небольшого количества топиков (<20)

### План изменений (реализовано)

1. ✅ Удален `pick_next_topic_to_post` из `ports/queue.py` и `sqlite_queue.py`
2. ✅ В `PublishService` реализован выбор топика:
   - `topics = topic_registry.list_topics(chat_id, enabled_only=True)`
   - `candidates = [t for t in topics if content_queue.count_new(t.id) > 0]`
   - Сортировка: `(t.last_post_at is not None, t.last_post_at or datetime.min, t.created_at)` — NULL первыми
   - Выбрать первый
3. ✅ Обновлены тесты в `tests/test_publish_service.py`
4. ✅ Добавлен тест `test_publish_fairness_prioritizes_null_over_count` для проверки правильной логики fairness

### Результат

- ✅ Все тесты проходят
- ✅ Правильная логика fairness (NULL первыми, затем по времени)
- ✅ Чистая архитектура (ContentQueue не знает о topics)
- ✅ Нет ошибок линтера

## Альтернативы (если понадобится оптимизация)

Если в будущем количество топиков вырастет и N+1 станет проблемой:

1. **Добавить batch метод:** `count_new_batch(topic_ids: list[int]) -> dict[int, int]`
2. **Использовать кэширование:** Кэшировать `count_new` на короткое время
3. **Вернуть SQL JOIN:** Но в отдельном сервисе/методе, не в ContentQueue

Но для текущего масштаба (5-10 топиков) это не нужно.
