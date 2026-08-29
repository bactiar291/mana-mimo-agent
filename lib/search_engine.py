"""
search_engine.py — Keyless web search for MiMo Agent.

Design rule: every default backend must work WITHOUT an API key.
Priority (all free, no key):
  1. ddgs      — aggregator lib, tries bing/brave/duckduckgo/... (lazy import, optional)
  2. duckduckgo — direct HTML scrape of html.duckduckgo.com (stdlib only)
  3. searxng   — public instances with ?format=json (often rate-limited, kept as fallback)
  4. wikipedia — MediaWiki list=search API (always reachable, snippets included)

Brave stays available but is OFF the default path because it requires a key.
"""
import json
import re
import urllib.parse
import urllib.request
import ssl
from html import unescape
from typing import List, Dict, Any, Optional

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ─── Search Engines ─────────────────────────────────────────────────────────


def search_ddgs(query: str, limit: int = 5, backends: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Search via the `ddgs` package (free, no API key). Lazy import: optional dep."""
    try:
        from ddgs import DDGS
    except ImportError:
        return [{"error": "ddgs: not installed (optional). Run: pip install ddgs"}]

    # "auto" aggregates several keyless engines; explicit ones are per-engine fallbacks.
    order = backends or ["auto", "bing", "brave", "duckduckgo", "yahoo", "mojeek"]
    failures: List[str] = []

    for backend in order:
        try:
            raw = DDGS().text(query, max_results=limit, backend=backend)
        except Exception as error:
            failures.append(f"{backend}: {type(error).__name__}")
            continue

        results = []
        for item in (raw or [])[:limit]:
            url = (item.get("href") or item.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            results.append({
                "url": url,
                "title": (item.get("title") or "").strip(),
                "description": (item.get("body") or item.get("description") or "").strip(),
                "backend": backend,
            })
        if results:
            return results

    return [{"error": f"ddgs: no results from any backend ({', '.join(failures) or 'empty'})"}]


def search_duckduckgo(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Search using DuckDuckGo HTML (no API key needed)."""
    results = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        req = urllib.request.Request(url, headers={'User-Agent': _UA})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        if "anomaly.js" in html or "challenge-form" in html:
            return [{"error": "DuckDuckGo: blocked_by_challenge"}]

        # DDG HTML format: <a class="result__a" href="URL">TITLE</a>
        #                  <a class="result__snippet" ...>DESCRIPTION</a>
        result_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'

        links = re.findall(result_pattern, html, re.DOTALL)
        snippets = re.findall(snippet_pattern, html, re.DOTALL)

        for i, (link, title) in enumerate(links[:limit]):
            if 'uddg=' in link:
                match = re.search(r'uddg=([^&]+)', link)
                if match:
                    link = urllib.parse.unquote(match.group(1))

            clean_title = unescape(re.sub(r'<[^>]+>', '', title)).strip()

            snippet = ""
            if i < len(snippets):
                snippet = unescape(re.sub(r'<[^>]+>', '', snippets[i])).strip()

            if link.startswith('http') and 'duckduckgo.com/y.js' not in link:
                results.append({
                    "url": link,
                    "title": clean_title,
                    "description": snippet,
                })

        if not results:
            return [{"error": "DuckDuckGo: no_results_parsed"}]

    except Exception as e:
        results.append({"error": f"DuckDuckGo: {str(e)}"})

    return results


def search_searxng(query: str, limit: int = 5, instance: str = None) -> List[Dict[str, str]]:
    """Search using public SearXNG instances (free, no API key). Often rate-limited."""
    results = []

    instances = [
        instance,  # user-provided first
        "https://searx.be",
        "https://priv.au",
        "https://searx.tiekoetter.com",
        "https://search.inetol.net",
        "https://opnxng.com",
        "https://paulgo.io",
        "https://search.rhscz.eu",
        "https://searx.namejeff.xyz",
    ]
    instances = [i for i in instances if i]
    failures: List[str] = []

    for inst in instances:
        try:
            params = urllib.parse.urlencode({
                'q': query,
                'format': 'json',
                'categories': 'general',
            })
            url = f"{inst}/search?{params}"

            req = urllib.request.Request(url, headers={
                'User-Agent': _UA,
                'Accept': 'application/json',
            })
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            for item in data.get('results', [])[:limit]:
                results.append({
                    "url": item.get('url', ''),
                    "title": item.get('title', ''),
                    "description": item.get('content', ''),
                })

            if results:
                return results

        except Exception as error:
            failures.append(f"{inst.split('//')[-1]}: {type(error).__name__}")
            continue

    if not results:
        results.append({"error": f"SearXNG: all instances failed ({len(failures)} tried)"})

    return results


def search_brave(query: str, limit: int = 5, api_key: str = None) -> List[Dict[str, str]]:
    """Search using Brave Search API (needs API key — NOT on the default path)."""
    if not api_key:
        return [{"error": "Brave: API key required (opt-in only, not used by default)"}]

    try:
        params = urllib.parse.urlencode({"q": query, "count": limit})
        url = f"https://api.search.brave.com/res/v1/web/search?{params}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": _UA,
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("web", {}).get("results", [])[:limit]:
            results.append({
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
            })
        return results or [{"error": "Brave: no_results"}]
    except Exception as e:
        return [{"error": f"Brave: {str(e)}"}]


def search_wikipedia(query: str, limit: int = 5, lang: str = None) -> List[Dict[str, str]]:
    """Search Wikipedia via MediaWiki list=search (free, no key, returns snippets)."""
    # Indonesian query heuristic: try id.wikipedia first, then en.
    langs = [lang] if lang else (["id", "en"] if _looks_indonesian(query) else ["en", "id"])
    failures: List[str] = []

    for code in langs:
        try:
            params = urllib.parse.urlencode({
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
            })
            url = f"https://{code}.wikipedia.org/w/api.php?{params}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "MiMoAgent/1.0 (keyless search fallback)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))

            results = []
            for item in payload.get("query", {}).get("search", [])[:limit]:
                title = item.get("title", "")
                snippet = unescape(re.sub(r"<[^>]+>", "", item.get("snippet", ""))).strip()
                results.append({
                    "url": f"https://{code}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                    "title": title,
                    "description": snippet,
                })
            if results:
                return results
            failures.append(f"{code}: no_results")
        except Exception as e:
            failures.append(f"{code}: {type(e).__name__}")

    return [{"error": f"Wikipedia: {', '.join(failures)}"}]


def _looks_indonesian(query: str) -> bool:
    words = set(re.findall(r"[a-z]+", query.lower()))
    hints = {
        "apa", "siapa", "berapa", "kapan", "dimana", "mengapa", "bagaimana",
        "yang", "dan", "atau", "tidak", "adalah", "dengan", "untuk", "dari",
        "terbaru", "harga", "cara", "berita", "indonesia",
    }
    return bool(words & hints)


# ─── Unified Search Interface ───────────────────────────────────────────────

# Keyless engines only. Brave is opt-in via set_search_engine("brave", api_key=...).
KEYLESS_ENGINES = ["ddgs", "duckduckgo", "searxng", "wikipedia"]
ALL_ENGINES = KEYLESS_ENGINES + ["brave"]

_engine_priority = list(KEYLESS_ENGINES)
_active_engine = "ddgs"
_brave_api_key = None
_searxng_instance = None


def set_search_engine(engine: str, api_key: str = None, instance: str = None):
    """Set the active search engine (must be one of ALL_ENGINES)."""
    global _active_engine, _brave_api_key, _searxng_instance
    if engine in ALL_ENGINES:
        _active_engine = engine
    if api_key:
        _brave_api_key = api_key
    if instance:
        _searxng_instance = instance
    return _active_engine


def _run_engine(engine: str, query: str, limit: int) -> List[Dict[str, str]]:
    if engine == "ddgs":
        return search_ddgs(query, limit)
    if engine == "duckduckgo":
        return search_duckduckgo(query, limit)
    if engine == "searxng":
        return search_searxng(query, limit, _searxng_instance)
    if engine == "brave":
        return search_brave(query, limit, _brave_api_key)
    if engine == "wikipedia":
        return search_wikipedia(query, limit)
    return []


def web_search(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Search the web using keyless engines with auto-fallback.
    Brave is only tried when an API key was explicitly provided.
    """
    order = [_active_engine] + [e for e in _engine_priority if e != _active_engine]
    if _brave_api_key and "brave" not in order:
        order.append("brave")

    failures: List[str] = []

    for engine in order:
        try:
            results = _run_engine(engine, query, limit)
        except Exception as error:
            failures.append(f"{engine}: {error}")
            continue

        real_results = [r for r in results if "error" not in r]
        failures.extend(
            r["error"] for r in results if isinstance(r, dict) and r.get("error")
        )
        if real_results:
            return {
                "engine": engine,
                "query": query,
                "results": real_results,
                "count": len(real_results),
                "fallbacks_tried": failures or None,
            }

    return {
        "engine": "none",
        "query": query,
        "results": [],
        "error": "All keyless search engines failed",
        "failures": failures,
    }


def get_search_status() -> Dict[str, Any]:
    """Get current search engine status."""
    try:
        import ddgs  # noqa: F401
        ddgs_state = "installed"
    except ImportError:
        ddgs_state = "not installed (optional)"

    return {
        "active_engine": _active_engine,
        "keyless_priority": _engine_priority,
        "ddgs": ddgs_state,
        "brave_api_key": "set" if _brave_api_key else "not set (not required)",
        "searxng_instance": _searxng_instance or "auto (public instances)",
        "available_engines": ALL_ENGINES,
    }


# ─── Test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing keyless search engines...\n")
    for name in KEYLESS_ENGINES:
        print(f"=== {name} ===")
        for r in _run_engine(name, "presiden indonesia", 3):
            if "error" in r:
                print(f"  ERROR: {r['error']}")
            else:
                print(f"  {r['title'][:60]}\n    {r['url'][:70]}")
        print()

    print("=== Unified ===")
    out = web_search("berita teknologi terbaru", 3)
    print(f"  engine={out['engine']} count={out.get('count', 0)}")
    for r in out.get("results", [])[:3]:
        print(f"  - {r.get('title', 'N/A')[:55]}")
