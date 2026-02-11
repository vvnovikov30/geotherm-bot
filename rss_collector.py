"""
Сбор RSS-новостей из различных источников.
"""
import feedparser
import requests
from datetime import datetime
from config import ALL_FEEDS


def fetch_items():
    """
    Читает все RSS-ленты из конфигурации и возвращает список новостей.
    
    Returns:
        list: Список словарей с новостями:
            {
                "title": str,
                "url": str,
                "published_at": str,
                "source": str,
                "summary": str
            }
    """
    all_items = []
    
    for feed_url in ALL_FEEDS:
        try:
            # Обработка Europe PMC REST API (JSON)
            if feed_url.startswith("https://www.ebi.ac.uk/europepmc/webservices/rest/search"):
                response = requests.get(feed_url, timeout=20)
                response.raise_for_status()
                data = response.json()
                
                # Извлекаем список результатов
                results = data.get("resultList", {}).get("result", [])
                result_count = len(results)
                
                print(f"[Europe PMC] {feed_url}")
                print(f"  Результатов: {result_count}")
                
                if result_count == 0:
                    print(f"  Query: {feed_url}")
                
                # Обрабатываем каждый результат
                for result in results:
                    title = result.get("title", "Без заголовка")
                    
                    # Формируем URL: приоритет DOI, иначе journalUrl/pmid/pmcid
                    url = ""
                    if result.get("doi"):
                        url = f"https://doi.org/{result['doi']}"
                    elif result.get("journalUrl"):
                        url = result["journalUrl"]
                    elif result.get("pmid"):
                        url = f"https://europepmc.org/article/MED/{result['pmid']}"
                    elif result.get("pmcid"):
                        url = f"https://europepmc.org/article/PMC/{result['pmcid']}"
                    
                    # Извлекаем дату публикации
                    published_at = result.get("firstPublicationDate", "")
                    if not published_at:
                        pub_year = result.get("pubYear", "")
                        if pub_year:
                            published_at = pub_year
                    
                    # Извлекаем аннотацию
                    abstract = result.get("abstractText") or ""
                    journal = result.get("journalTitle") or ""
                    authors = result.get("authorString") or ""
                    
                    # Извлекаем pubTypeList.pubType (list)
                    pub_type_list = result.get("pubTypeList", {})
                    pub_types = pub_type_list.get("pubType", []) if isinstance(pub_type_list, dict) else []
                    if not isinstance(pub_types, list):
                        pub_types = [pub_types] if pub_types else []
                    
                    # Сохраняем как список строк
                    pub_types = [str(pt) for pt in pub_types] if pub_types else []
                    
                    # Формируем текстовое представление типов публикаций
                    pub_types_text = " ".join(pub_types).lower() if pub_types else ""

                    summary = f"{abstract}\n{journal}\n{authors}"
                    if pub_types_text:
                        summary = summary + " " + pub_types_text

                    
                    item = {
                        "title": title,
                        "url": url,
                        "published_at": published_at,
                        "source": "Europe PMC",
                        "summary": summary,
                        "pub_types": pub_types
                    }
                    
                    all_items.append(item)
            
            else:
                # Обычный RSS через feedparser
                feed = feedparser.parse(feed_url)
                print(f"[RSS] {feed_url}")
                print(f"  bozo={getattr(feed, 'bozo', None)} entries={len(getattr(feed, 'entries', []))}")
                if getattr(feed, "bozo", 0):
                    print(f"  bozo_exception={getattr(feed, 'bozo_exception', None)}")

                # Обрабатываем каждую новость из ленты
                for entry in feed.entries:
                    # Извлекаем заголовок
                    title = entry.get("title", "Без заголовка")
                    
                    # Извлекаем URL (может быть в разных полях)
                    url = entry.get("link", "")
                    if not url and hasattr(entry, "links") and entry.links:
                        url = entry.links[0].get("href", "")
                    
                    # Извлекаем дату публикации
                    published_at = ""
                    if hasattr(entry, "published"):
                        published_at = entry.published
                    elif hasattr(entry, "updated"):
                        published_at = entry.updated
                    elif hasattr(entry, "published_parsed"):
                        # Парсим структурированную дату
                        pub_date = entry.published_parsed
                        published_at = datetime(*pub_date[:6]).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Определяем источник (из URL или заголовка ленты)
                    source = feed.feed.get("title", feed_url)
                    
                    # Извлекаем summary (если есть)
                    summary = entry.get("summary", "")
                    
                    item = {
                        "title": title,
                        "url": url,
                        "published_at": published_at,
                        "source": source,
                        "summary": summary
                    }
                    
                    all_items.append(item)
                
        except Exception as e:
            print(f"Ошибка при обработке {feed_url}: {e}")
            continue
    
    return all_items
