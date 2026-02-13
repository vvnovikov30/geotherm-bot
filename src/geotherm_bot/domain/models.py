"""
Доменные модели данных.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Publication:
    """Модель публикации."""
    id: str
    source: str
    title: str
    abstract: Optional[str] = None
    url: Optional[str] = None
    year: Optional[int] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    
    # Дополнительные поля для совместимости и обработки
    published_at: Optional[str] = None  # Для обратной совместимости
    summary: Optional[str] = None  # Алиас для abstract
    pub_types: List[str] = field(default_factory=list)
    bucket: Optional[str] = None  # "review", "trial", "study"
    score: Optional[int] = None
    region: Optional[str] = None  # "asia", etc.
    
    def __post_init__(self):
        """Инициализация после создания объекта."""
        # Синхронизация summary и abstract
        if self.summary is None and self.abstract is not None:
            self.summary = self.abstract
        elif self.abstract is None and self.summary is not None:
            self.abstract = self.summary
        
        # Извлечение year из published_at если не указан
        if self.year is None and self.published_at:
            try:
                # Пробуем извлечь год из строки даты
                year_str = self.published_at[:4]
                if year_str.isdigit():
                    self.year = int(year_str)
            except (ValueError, IndexError):
                pass


@dataclass
class QuerySpec:
    """Спецификация запроса для поиска публикаций."""
    source: str
    name: str
    query: str
    language_hint: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    max_results: int = 100


@dataclass
class ScoreResult:
    """Результат скоринга публикации."""
    score: int
    reasons: List[str] = field(default_factory=list)
    is_high_priority: bool = False
    
    def __post_init__(self):
        """Инициализация после создания объекта."""
        if self.reasons is None:
            self.reasons = []


@dataclass
class FilterDecision:
    """Результат фильтрации публикации."""
    passed: bool
    reasons: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Инициализация после создания объекта."""
        if self.reasons is None:
            self.reasons = []
