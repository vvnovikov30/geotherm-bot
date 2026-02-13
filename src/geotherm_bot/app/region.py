"""
Разрешение региона по названию топика.
"""
import re
import unicodedata
from typing import Dict


class RegionResolver:
    """Разрешает region_key из названия топика."""
    
    # Статический словарь маппинга названий на region_key
    REGION_MAP: Dict[str, str] = {
        "турция": "turkey",
        "закавказье": "transcaucasia",
        "алтай": "altai",
        "тюмень": "tyumen",
        "юго-восточная азия": "se_asia",
        "юва": "se_asia",
        "регион кавказских минеральных вод": "kmv",
        "кавказские минеральные воды": "kmv",
        "кмв": "kmv",
    }
    
    def infer_region_key(self, topic_name: str) -> str:
        """
        Определяет region_key из названия топика.
        
        Args:
            topic_name: Название топика
        
        Returns:
            str: region_key
        """
        normalized = self.normalize_topic_name(topic_name)
        
        # Проверяем точное совпадение
        if normalized in self.REGION_MAP:
            return self.REGION_MAP[normalized]
        
        # Проверяем частичное совпадение (если normalized содержит ключ)
        for key, value in self.REGION_MAP.items():
            if key in normalized:
                return value
        
        # Fallback: slugify
        return self.slugify(normalized)
    
    @staticmethod
    def normalize_topic_name(s: str) -> str:
        """
        Нормализует название топика.
        
        Args:
            s: Исходная строка
        
        Returns:
            str: Нормализованная строка
        """
        # Убираем пробелы по краям
        s = s.strip()
        # Приводим к нижнему регистру
        s = s.lower()
        # Заменяем 'ё' на 'е'
        s = s.replace('ё', 'е')
        return s
    
    @staticmethod
    def slugify(s: str) -> str:
        """
        Преобразует строку в slug (только латиница/цифры/underscore).
        
        Детерминированная транслитерация кириллицы в латиницу.
        
        Args:
            s: Исходная строка
        
        Returns:
            str: Slug строка
        """
        # b) Приводим к lower и заменяем 'ё' на 'е'
        s = s.lower()
        s = s.replace('ё', 'е')
        
        # c) Транслитерация кириллицы в латиницу (ДО нормализации)
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
            'е': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'i',
            'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
            'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh',
            'щ': 'shch', 'ы': 'y', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'ь': '', 'ъ': '',
        }
        
        # Сначала транслитерируем кириллицу
        # Специальная обработка: "й" после "ы" не транслитерируется (чтобы избежать "yi" -> "y")
        result = []
        prev_char = None
        for i, char in enumerate(s):
            if char == 'й' and prev_char == 'ы':
                # Пропускаем "й" после "ы" (чтобы "Северный" -> "severny", а не "severnyi")
                continue
            if char in translit_map:
                result.append(translit_map[char])
            else:
                result.append(char)
            prev_char = char
        
        # Теперь работаем с уже транслитерированной строкой
        s_translit = ''.join(result)
        
        # a) Нормализуем Unicode (NFKD разбивает составные символы)
        # Теперь это безопасно, так как кириллица уже транслитерирована
        s_translit = unicodedata.normalize("NFKD", s_translit)
        
        # Обрабатываем нормализованную строку
        result = []
        for char in s_translit:
            # Латиница и цифры (ASCII alnum или underscore)
            if char.isascii() and (char.isalnum() or char == '_'):
                result.append(char)
            # Всё прочее (включая пробелы, тире, не-ASCII, диакритики после NFKD) -> '_'
            else:
                # NFKD может оставить диакритики - пропускаем их
                if not unicodedata.combining(char):
                    result.append('_')
        
        # e) Убираем повторные '_' и обрезаем '_' по краям
        slug = ''.join(result)
        slug = re.sub(r'_+', '_', slug)
        slug = slug.strip('_')
        
        # f) Если пусто -> "topic"
        if not slug:
            slug = "topic"
        
        return slug
