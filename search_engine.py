"""
search_engine.py — Multi-engine web search for MiMo Agent
Supports: DuckDuckGo (free, no API), SearXNG (self-hosted, free), Brave (API key)
"""
import json
import re
import urllib.parse
import urllib.request
import ssl
from typing import List, Dict, Any, Optional

# ─── Search Engines ─────────────────────────────────────────────────────────

def search_duckduckgo(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Search using DuckDuckGo HTML (no API key needed)."""
    results = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        })
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # Parse results from HTML
        # DDG HTML format: <a rel="nofollow" class="result__a" href="URL">TITLE</a>
        # <a class="result__snippet" href="...">DESCRIPTION</a>

        # Extract result blocks
        result_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'

        links = re.findall(result_pattern, html, re.DOTALL)
        snippets = re.findall(snippet_pattern, html, re.DOTALL)

        for i, (link, title) in enumerate(links[:limit]):
            # Clean up link (DDG sometimes wraps URLs)
            if 'uddg=' in link:
                match = re.search(r'uddg=([^&]+)', link)
                if match:
                    link = urllib.parse.unquote(match.group(1))

            # Clean HTML from title
            clean_title = re.sub(r'<[^>]+>', '', title).strip()

            # Get snippet if available
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            if link.startswith('http') and 'duckduckgo.com/y.js' not in link:
                results.append({
                    "url": link,
                    "title": clean_title,
                    "description": snippet
                })

    except Exception as e:
        results.append({"error": f"DuckDuckGo: {str(e)}"})

    return results


def search_searxng(query: str, limit: int = 5, instance: str = None) -> List[Dict[str, str]]:
    """Search using SearXNG public instance (free, no API key)."""
    results = []

    # Public SearXNG instances (no API key needed)
    instances = [
        instance,  # User-provided instance first
        "https://searx.be",
        "https://search.sapti.me",
        "https://searxng.site",
        "https://search.bus-hit.me",
        "https://searx.tuxcloud.net",
    ]
    instances = [i for i in instances if i]  # Remove None

    for inst in instances:
        try:
            params = urllib.parse.urlencode({
                'q': query,
                'format': 'json',
                'categories': 'general',
                'language': 'en',
            })
            url = f"{inst}/search?{params}"

            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            })
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            for item in data.get('results', [])[:limit]:
                results.append({
                    "url": item.get('url', ''),
                    "title": item.get('title', ''),
                    "description": item.get('content', '')
                })

            if results:
                return results  # Success, return

        except Exception:
            continue  # Try next instance

    if not results:
        results.append({"error": "SearXNG: All instances failed"})

    return results


def search_brave(query: str, limit: int = 5, api_key: str = None) -> List[Dict[str, str]]:
    """Search using Brave Search API (needs API key)."""
    if not api_key:
        return [{"error": "Brave: API key required. Get free key at https://brave.com/search/api/"}]

    results = []
    try:
        params = urllib.parse.urlencode({
            'q': query,
            'count': limit,
        })
        url = f"https://api.search.brave.com/res/v1/web/search?{params}"

        req = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'X-Subscription-Token': api_key,
        })

        import gzip
        ctx = ssl.create_default_context()

        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data_bytes = resp.read()
            # Try to decompress if gzip
            try:
                data_bytes = gzip.decompress(data_bytes)
            except:
                pass
            data = json.loads(data_bytes.decode('utf-8'))

        for item in data.get('web', {}).get('results', [])[:limit]:
            results.append({
                "url": item.get('url', ''),
                "title": item.get('title', ''),
                "description": item.get('description', '')
            })

    except Exception as e:
        results.append({"error": f"Brave: {str(e)}"})

    return results


# ─── Unified Search Interface ───────────────────────────────────────────────

# Default engine priority
_engine_priority = ["duckduckgo", "searxng", "brave"]
_active_engine = "duckduckgo"
_brave_api_key = None
_searxng_instance = None


def set_search_engine(engine: str, api_key: str = None, instance: str = None):
    """Set the active search engine."""
    global _active_engine, _brave_api_key, _searxng_instance
    if engine in ("duckduckgo", "searxng", "brave"):
        _active_engine = engine
    if api_key:
        _brave_api_key = api_key
    if instance:
        _searxng_instance = instance
    return _active_engine


def web_search(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Search the web using the active engine with auto-fallback.
    Tries engines in priority order if one fails.
    """
    engines_to_try = [_active_engine] + [e for e in _engine_priority if e != _active_engine]

    for engine in engines_to_try:
        try:
            if engine == "duckduckgo":
                results = search_duckduckgo(query, limit)
            elif engine == "searxng":
                results = search_searxng(query, limit, _searxng_instance)
            elif engine == "brave":
                results = search_brave(query, limit, _brave_api_key)
            else:
                continue

            # Check if we got real results (not just errors)
            real_results = [r for r in results if "error" not in r]
            if real_results:
                return {
                    "engine": engine,
                    "query": query,
                    "results": real_results,
                    "count": len(real_results)
                }

        except Exception:
            continue

    # All engines failed
    return {
        "engine": "none",
        "query": query,
        "results": [],
        "error": "All search engines failed"
    }


def get_search_status() -> Dict[str, Any]:
    """Get current search engine status."""
    return {
        "active_engine": _active_engine,
        "brave_api_key": "set" if _brave_api_key else "not set",
        "searxng_instance": _searxng_instance or "auto (public instances)",
        "available_engines": ["duckduckgo", "searxng", "brave"]
    }


# ─── Test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing search engines...")

    # Test DuckDuckGo
    print("\n=== DuckDuckGo ===")
    results = search_duckduckgo("python programming", 3)
    for r in results:
        if "error" not in r:
            print(f"  {r['title'][:60]}")
            print(f"  {r['url']}")
        else:
            print(f"  ERROR: {r['error']}")

    # Test SearXNG
    print("\n=== SearXNG ===")
    results = search_searxng("python programming", 3)
    for r in results:
        if "error" not in r:
            print(f"  {r['title'][:60]}")
            print(f"  {r['url']}")
        else:
            print(f"  ERROR: {r['error']}")

    # Test unified interface
    print("\n=== Unified Search ===")
    result = web_search("what is python", 3)
    print(f"  Engine: {result['engine']}")
    print(f"  Results: {result.get('count', 0)}")
    for r in result.get('results', [])[:2]:
        print(f"  - {r.get('title', 'N/A')[:50]}")
