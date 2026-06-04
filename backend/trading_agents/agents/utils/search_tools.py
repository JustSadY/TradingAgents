import logging
import os
import requests
from abc import ABC, abstractmethod
from typing import List, Dict
from langchain_core.tools import tool
_logger = logging.getLogger(__name__)
class BaseSearchEngine(ABC):
    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        pass
from backend.trading_agents.dataflows.config import get_config
class SearxNGSearchEngine(BaseSearchEngine):
    def __init__(self, base_url: str = None):
        cfg_url = get_config().get("searxng_url")
        self.base_url = base_url or cfg_url or os.getenv("SEARXNG_URL", "http://localhost:8080")
    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        try:
            url = f"{self.base_url}/search"
            params = {
                "q": query,
                "format": "json",
                "language": "en"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("results", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("url", ""),
                    "snippet": item.get("content", "")
                })
            return results
        except Exception as e:
            _logger.warning("SearxNG search failed for query %r: %s", query, e, exc_info=True)
            return [{"title": "Error", "link": "", "snippet": f"SearxNG Search Failed: {str(e)}"}]
def get_search_engine() -> BaseSearchEngine:
    engine_type = os.getenv("SEARCH_ENGINE_TYPE", "searxng").lower()
    if engine_type == "searxng":
        return SearxNGSearchEngine()
    else:
        return SearxNGSearchEngine()
@tool
def search_web(query: str, num_results: int = 5) -> str:
    engine = get_search_engine()
    results = engine.search(query, num_results)
    if not results:
        return f"No results found for query: {query}"
    formatted_results = []
    for i, res in enumerate(results, 1):
        formatted_results.append(f"{i}. {res['title']}\n   URL: {res['link']}\n   Snippet: {res['snippet']}")
    return "\n\n".join(formatted_results)
@tool
def get_crypto_fear_and_greed_index() -> str:
    try:
        response = requests.get("https://api.alternative.me/fng/", timeout=10)
        response.raise_for_status()
        data = response.json()
        fng_data = data.get("data", [{}])[0]
        value = fng_data.get("value", "N/A")
        classification = fng_data.get("value_classification", "Unknown")
        report = (
            "### Crypto Fear & Greed Index\n"
            f"- **Current Value**: `{value}` / 100\n"
            f"- **Classification**: **{classification}**\n"
            f"- **Analysis Note**: Extreme Fear can be a sign that investors are too worried (buying opportunity), whereas Extreme Greed implies the market is due for a correction."
        )
        return report
    except Exception as e:
        return f"Failed to retrieve Crypto Fear and Greed Index: {str(e)}"
