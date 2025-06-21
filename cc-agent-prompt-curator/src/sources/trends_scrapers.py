import asyncio
import aiohttp
import json
import logging
import re
from typing import List, Dict
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class TrendsScraper:
    def __init__(self, timeout: int = 10):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_trends24(self) -> List[str]:
        try:
            url = "https://trends24.in/api/trending.json"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    trends = []
                    for location_data in data.values():
                        if isinstance(location_data, list):
                            trends.extend([item.get('name', '') for item in location_data[:10]])
                    return [trend for trend in trends if trend and len(trend) > 2][:20]
        except Exception as e:
            logger.error(f"Failed to fetch trends24: {e}")
        return []

    async def fetch_tiktok_trends(self) -> List[str]:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            url = "https://www.tiktok.com/api/trending/feed/"
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    trends = []
                    if 'itemList' in data:
                        for item in data['itemList'][:20]:
                            desc = item.get('desc', '')
                            hashtags = re.findall(r'#(\w+)', desc)
                            trends.extend(hashtags)
                    return trends[:20]
        except Exception as e:
            logger.error(f"Failed to fetch TikTok trends: {e}")
        return []

    async def fetch_google_trends(self) -> List[str]:
        try:
            url = "https://trends.google.com/trends/trendingsearches/daily/rss"
            async with self.session.get(url) as response:
                if response.status == 200:
                    xml_content = await response.text()
                    root = ET.fromstring(xml_content)
                    trends = []
                    for item in root.findall('.//item')[:20]:
                        title = item.find('title')
                        if title is not None and title.text:
                            clean_title = re.sub(r'\s*-\s*Google\s+Trends.*$', '', title.text)
                            trends.append(clean_title.strip())
                    return trends
        except Exception as e:
            logger.error(f"Failed to fetch Google trends: {e}")
        return []

    async def collect_all_trends(self) -> List[Dict[str, str]]:
        tasks = [
            self._safe_fetch("trends24", self.fetch_trends24),
            self._safe_fetch("tiktok", self.fetch_tiktok_trends),
            self._safe_fetch("google", self.fetch_google_trends)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_phrases = []
        for source, phrases in results:
            if isinstance(phrases, Exception):
                logger.error(f"Source {source} failed: {phrases}")
                continue
            for phrase in phrases:
                all_phrases.append({"source": source, "phrase": phrase})
        
        return all_phrases

    async def _safe_fetch(self, source_name: str, fetch_func) -> tuple:
        try:
            phrases = await fetch_func()
            logger.info(f"Fetched {len(phrases)} phrases from {source_name}")
            return source_name, phrases
        except Exception as e:
            logger.error(f"Error fetching from {source_name}: {e}")
            return source_name, []
