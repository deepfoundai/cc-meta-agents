import pytest
import json
from unittest.mock import AsyncMock, patch
import aiohttp
from aioresponses import aioresponses

from src.sources.trends_scrapers import TrendsScraper

@pytest.fixture
def trends_scraper():
    return TrendsScraper(timeout=5)

@pytest.fixture
def mock_trends24_response():
    return {
        "united_states": [
            {"name": "AI Revolution", "url": "test"},
            {"name": "Climate Change", "url": "test"},
            {"name": "Space Exploration", "url": "test"}
        ],
        "global": [
            {"name": "Tech Innovation", "url": "test"},
            {"name": "Green Energy", "url": "test"}
        ]
    }

@pytest.fixture
def mock_tiktok_response():
    return {
        "itemList": [
            {"desc": "Check out this #AIRevolution video #tech"},
            {"desc": "Amazing #ClimateAction content #green"},
            {"desc": "New #SpaceExploration discovery #science"}
        ]
    }

@pytest.fixture
def mock_google_trends_rss():
    return '''<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>AI Revolution - Google Trends</title>
            </item>
            <item>
                <title>Climate Change Solutions - Google Trends</title>
            </item>
            <item>
                <title>Space Technology - Google Trends</title>
            </item>
        </channel>
    </rss>'''

class TestTrendsScraper:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with TrendsScraper() as scraper:
            assert scraper.session is not None
        assert scraper.session.closed

    @pytest.mark.asyncio
    async def test_fetch_trends24_success(self, trends_scraper, mock_trends24_response):
        with aioresponses() as m:
            m.get('https://trends24.in/api/trending.json', payload=mock_trends24_response)
            
            async with trends_scraper:
                result = await trends_scraper.fetch_trends24()
            
            assert len(result) == 5
            assert "AI Revolution" in result
            assert "Climate Change" in result
            assert "Tech Innovation" in result

    @pytest.mark.asyncio
    async def test_fetch_trends24_failure(self, trends_scraper):
        with aioresponses() as m:
            m.get('https://trends24.in/api/trending.json', status=500)
            
            async with trends_scraper:
                result = await trends_scraper.fetch_trends24()
            
            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_tiktok_trends_success(self, trends_scraper, mock_tiktok_response):
        with aioresponses() as m:
            m.get('https://www.tiktok.com/api/trending/feed/', payload=mock_tiktok_response)
            
            async with trends_scraper:
                result = await trends_scraper.fetch_tiktok_trends()
            
            assert len(result) >= 3
            assert "AIRevolution" in result
            assert "ClimateAction" in result
            assert "SpaceExploration" in result

    @pytest.mark.asyncio
    async def test_fetch_tiktok_trends_failure(self, trends_scraper):
        with aioresponses() as m:
            m.get('https://www.tiktok.com/api/trending/feed/', status=403)
            
            async with trends_scraper:
                result = await trends_scraper.fetch_tiktok_trends()
            
            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_google_trends_success(self, trends_scraper, mock_google_trends_rss):
        with aioresponses() as m:
            m.get('https://trends.google.com/trends/trendingsearches/daily/rss', 
                  body=mock_google_trends_rss, content_type='application/rss+xml')
            
            async with trends_scraper:
                result = await trends_scraper.fetch_google_trends()
            
            assert len(result) == 3
            assert "AI Revolution" in result
            assert "Climate Change Solutions" in result
            assert "Space Technology" in result

    @pytest.mark.asyncio
    async def test_fetch_google_trends_failure(self, trends_scraper):
        with aioresponses() as m:
            m.get('https://trends.google.com/trends/trendingsearches/daily/rss', status=404)
            
            async with trends_scraper:
                result = await trends_scraper.fetch_google_trends()
            
            assert result == []

    @pytest.mark.asyncio
    async def test_collect_all_trends_success(self, trends_scraper, mock_trends24_response, 
                                            mock_tiktok_response, mock_google_trends_rss):
        with aioresponses() as m:
            m.get('https://trends24.in/api/trending.json', payload=mock_trends24_response)
            m.get('https://www.tiktok.com/api/trending/feed/', payload=mock_tiktok_response)
            m.get('https://trends.google.com/trends/trendingsearches/daily/rss', 
                  body=mock_google_trends_rss, content_type='application/rss+xml')
            
            async with trends_scraper:
                result = await trends_scraper.collect_all_trends()
            
            assert len(result) > 0
            
            sources = {item["source"] for item in result}
            assert "trends24" in sources
            assert "tiktok" in sources
            assert "google" in sources
            
            phrases = [item["phrase"] for item in result]
            assert any("AI Revolution" in phrase for phrase in phrases)

    @pytest.mark.asyncio
    async def test_collect_all_trends_partial_failure(self, trends_scraper, mock_trends24_response):
        with aioresponses() as m:
            m.get('https://trends24.in/api/trending.json', payload=mock_trends24_response)
            m.get('https://www.tiktok.com/api/trending/feed/', status=500)
            m.get('https://trends.google.com/trends/trendingsearches/daily/rss', status=404)
            
            async with trends_scraper:
                result = await trends_scraper.collect_all_trends()
            
            assert len(result) > 0
            sources = {item["source"] for item in result}
            assert "trends24" in sources
            assert "tiktok" not in sources or len([item for item in result if item["source"] == "tiktok"]) == 0

    @pytest.mark.asyncio
    async def test_collect_all_trends_complete_failure(self, trends_scraper):
        with aioresponses() as m:
            m.get('https://trends24.in/api/trending.json', status=500)
            m.get('https://www.tiktok.com/api/trending/feed/', status=500)
            m.get('https://trends.google.com/trends/trendingsearches/daily/rss', status=500)
            
            async with trends_scraper:
                result = await trends_scraper.collect_all_trends()
            
            assert result == []

    @pytest.mark.asyncio
    async def test_safe_fetch_success(self, trends_scraper):
        async def mock_fetch():
            return ["test1", "test2"]
        
        async with trends_scraper:
            source, phrases = await trends_scraper._safe_fetch("test_source", mock_fetch)
        
        assert source == "test_source"
        assert phrases == ["test1", "test2"]

    @pytest.mark.asyncio
    async def test_safe_fetch_failure(self, trends_scraper):
        async def mock_fetch():
            raise Exception("Test error")
        
        async with trends_scraper:
            source, phrases = await trends_scraper._safe_fetch("test_source", mock_fetch)
        
        assert source == "test_source"
        assert phrases == []
