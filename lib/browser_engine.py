"""
browser_engine.py — Hybrid browser engine for MiMo Agent
- Primary: DrissionPage (fast, lightweight)
- Fallback: Playwright (stable, handles SPA better)
- Auto-recovery on crash
- Connection pooling
"""
import json
import time
import re
import os
import threading
import glob
import shutil
from typing import Optional, Dict, Any

# ─── Browser State ──────────────────────────────────────────────────────────

_browser = None
_browser_tab = None
_browser_engine = "drission"  # "drission" or "playwright"
_browser_lock = threading.RLock()
_last_url = None
_browser_start_time = None
try:
    _MAX_BROWSER_AGE = int(os.environ.get("MIMO_BROWSER_MAX_AGE", "1800"))
except (TypeError, ValueError):
    _MAX_BROWSER_AGE = 1800
_DEFAULT_IDLE_TIMEOUT = 90
_last_activity_time = None
_active_tasks = 0
_idle_thread = None


def _idle_timeout_seconds() -> int:
    """Clamp idle cleanup into the 60-120s lifecycle window."""
    try:
        value = int(os.environ.get("MIMO_BROWSER_IDLE_TIMEOUT", str(_DEFAULT_IDLE_TIMEOUT)))
    except (TypeError, ValueError):
        value = _DEFAULT_IDLE_TIMEOUT
    return max(60, min(120, value))


def _has_browser_locked() -> bool:
    return any((_browser, _browser_tab, _playwright, _playwright_browser, _playwright_page))


def _cleanup_drission_tmp() -> int:
    """Remove DrissionPage temp profiles after the browser is closed."""
    removed = 0
    for path in glob.glob("/tmp/DrissionPage*"):
        if not os.path.basename(path).startswith("DrissionPage"):
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
            removed += 1
        except Exception:
            pass
    return removed


def _ensure_idle_reaper_locked():
    global _idle_thread
    if _idle_thread and _idle_thread.is_alive():
        return
    _idle_thread = threading.Thread(target=_idle_reaper, name="mimo-browser-idle", daemon=True)
    _idle_thread.start()


def _touch_activity_locked():
    global _last_activity_time
    _last_activity_time = time.time()
    _ensure_idle_reaper_locked()


def _mark_activity():
    with _browser_lock:
        _touch_activity_locked()


def _idle_reaper():
    while True:
        time.sleep(5)
        with _browser_lock:
            if _active_tasks > 0:
                continue
            if not _has_browser_locked():
                return
            last_activity = _last_activity_time or _browser_start_time or time.time()
            should_close = (time.time() - last_activity) >= _idle_timeout_seconds()
        if should_close:
            close_browser(reason="idle")


def begin_task(label: str = "task") -> Dict[str, Any]:
    """Mark a task as active so idle cleanup does not break an in-flight flow."""
    global _active_tasks
    with _browser_lock:
        _active_tasks += 1
        _touch_activity_locked()
        return get_browser_status()


def end_task(label: str = "task", close_now: bool = False) -> Dict[str, Any]:
    """Release a task marker and either close now or let the idle reaper handle it."""
    global _active_tasks
    should_close = False
    close_result = None
    with _browser_lock:
        _active_tasks = max(0, _active_tasks - 1)
        _touch_activity_locked()
        should_close = close_now and _active_tasks == 0 and _has_browser_locked()
    if should_close:
        close_result = close_browser(reason="task_complete")
    status = get_browser_status()
    if close_result:
        status.update(close_result)
    return status


# ─── Engine Selection ────────────────────────────────────────────────────────

def get_engine() -> str:
    return _browser_engine

def set_engine(engine: str, close_existing: bool = True):
    global _browser_engine
    if engine in ("drission", "playwright"):
        if close_existing and engine != _browser_engine:
            close_browser(reason="engine_switch")
        _browser_engine = engine
    return _browser_engine


# ─── Browser Lifecycle ──────────────────────────────────────────────────────

def close_browser(reason: str = "manual"):
    global _browser, _browser_tab, _browser_start_time, _last_activity_time
    with _browser_lock:
        if _browser:
            try:
                _browser.quit()
            except:
                pass
        _browser = None
        _browser_tab = None
        _browser_start_time = None
        _last_activity_time = None
    close_playwright()
    cleaned = _cleanup_drission_tmp()
    return {"status": "closed", "reason": reason, "tmp_removed": cleaned}

def _is_browser_alive() -> bool:
    global _browser, _browser_start_time
    if _browser is None:
        return False
    # Check age
    if _browser_start_time and (time.time() - _browser_start_time) > _MAX_BROWSER_AGE:
        return False
    # Try a simple operation
    try:
        _ = _browser.title
        return True
    except:
        return False


# ─── DrissionPage Engine ────────────────────────────────────────────────────

def _get_drission_browser():
    global _browser, _browser_tab, _browser_start_time
    if _browser is not None and _is_browser_alive():
        return _browser_tab

    # Need to create new browser
    close_browser()

    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()

    # Use Playwright's Chromium
    pw_chromium = os.path.expanduser('~/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome')
    if os.path.exists(pw_chromium):
        co.set_browser_path(pw_chromium)

    # Headless by default
    co.headless()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--disable-infobars')
    co.set_argument('--disable-extensions')
    co.set_argument('--disable-background-timer-throttling')
    co.set_argument('--disable-renderer-backgrounding')
    co.set_argument('--window-size=1280,800')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    co.set_pref('credentials_enable_service', False)
    co.set_pref('profile.password_manager_enabled', False)

    _browser = ChromiumPage(co)
    _browser_tab = _browser
    _browser_start_time = time.time()
    _mark_activity()
    return _browser_tab


# ─── Playwright Engine ──────────────────────────────────────────────────────

_playwright = None
_playwright_browser = None
_playwright_page = None

def _get_playwright_browser():
    global _playwright, _playwright_browser, _playwright_page, _browser_start_time

    if _playwright_page and _is_playwright_alive():
        return _playwright_page

    # Need to create new
    close_playwright()

    from playwright.sync_api import sync_playwright
    _playwright = sync_playwright().start()
    _playwright_browser = _playwright.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
        ]
    )
    _playwright_page = _playwright_browser.new_page(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 800}
    )
    _browser_start_time = time.time()
    _mark_activity()
    return _playwright_page

def _is_playwright_alive() -> bool:
    global _playwright_page, _browser_start_time
    if _playwright_page is None:
        return False
    if _browser_start_time and (time.time() - _browser_start_time) > _MAX_BROWSER_AGE:
        return False
    try:
        _playwright_page.evaluate("1+1")
        return True
    except:
        return False

def close_playwright():
    global _playwright, _playwright_browser, _playwright_page
    try:
        if _playwright_page:
            _playwright_page.close()
    except:
        pass
    try:
        if _playwright_browser:
            _playwright_browser.close()
    except:
        pass
    try:
        if _playwright:
            _playwright.stop()
    except:
        pass
    _playwright = None
    _playwright_browser = None
    _playwright_page = None


# ─── Unified Browser Interface ──────────────────────────────────────────────


# ─── Auto-Cleanup ──────────────────────────────────────────────────────────

import threading

_cleanup_timer = None
_CLEANUP_TIMEOUT = _idle_timeout_seconds

def _schedule_cleanup():
    """Schedule browser cleanup after timeout."""
    global _cleanup_timer
    
    # Cancel existing timer
    if _cleanup_timer:
        _cleanup_timer.cancel()
    
    # Schedule new cleanup using the same active-task-aware idle window.
    _cleanup_timer = threading.Timer(_idle_timeout_seconds(), _auto_cleanup)
    _cleanup_timer.daemon = True
    _cleanup_timer.start()

def _auto_cleanup():
    """Auto-close browser after timeout."""
    global _cleanup_timer
    try:
        with _browser_lock:
            active = _active_tasks > 0
            last_activity = _last_activity_time or _browser_start_time or time.time()
            idle_for = time.time() - last_activity
            should_close = (not active) and idle_for >= _idle_timeout_seconds()
        if should_close:
            close_browser("auto-cleanup")
        elif _has_browser_locked():
            _schedule_cleanup()
    except Exception:
        pass
    if not _has_browser_locked():
        _cleanup_timer = None

def browser_open(url: str, wait: int = 3, engine: str = None) -> str:
    """Open URL with automatic engine selection and retry."""
    global _last_url

    _last_url = url
    _mark_activity()

    if wait > 15:
        wait = 15
    if wait < 1:
        wait = 1

    use_engine = engine or _browser_engine
    errors = []

    # Try primary engine
    for attempt in range(2):
        try:
            if use_engine == "playwright":
                result = _playwright_open(url, wait)
            else:
                result = _drission_open(url, wait)
            _mark_activity()
            # Auto-cleanup after 30 seconds of inactivity
            _schedule_cleanup()
            return result
        except Exception as e:
            errors.append(f"{use_engine}: {str(e)}")
            close_browser()
            time.sleep(1)

    # Primary failed, try fallback
    fallback = "playwright" if use_engine == "drission" else "drission"
    try:
        if fallback == "playwright":
            result = _playwright_open(url, wait)
        else:
            result = _drission_open(url, wait)
        # Switch to fallback for future calls
        set_engine(fallback, close_existing=False)
        _mark_activity()
        # Auto-cleanup after 30 seconds of inactivity
        _schedule_cleanup()
        return result
    except Exception as e:
        errors.append(f"{fallback}: {str(e)}")

    return json.dumps({
        "error": "All browser engines failed",
        "details": errors,
        "url": url
    })

def _drission_open(url: str, wait: int) -> str:
    """Open with DrissionPage."""
    tab = _get_drission_browser()
    tab.get(url)
    time.sleep(wait)

    try:
        title = tab.title
        html = tab.html
    except Exception as e:
        close_browser()
        raise e

    if not html or len(html) < 100:
        raise Exception("Empty page content")

    return _extract_content(html, title, url)

def _playwright_open(url: str, wait: int) -> str:
    """Open with Playwright."""
    page = _get_playwright_browser()
    page.goto(url, wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(wait * 1000)

    title = page.title()
    html = page.content()

    if not html or len(html) < 100:
        raise Exception("Empty page content")

    return _extract_content(html, title, url)

def _extract_content(html: str, title: str, url: str) -> str:
    """Extract clean text from HTML."""
    text = html[:20000] if len(html) > 20000 else html
    clean = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > 10000:
        clean = clean[:10000] + "\n... (truncated)"
    return json.dumps({"url": url, "title": title or "", "content": clean, "status": "ok"})


def browser_click(selector: str) -> str:
    """Click element."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            page.click(selector, timeout=10000)
            time.sleep(1)
        else:
            tab = _get_drission_browser()
            elem = tab.ele(selector)
            if elem:
                elem.click()
                time.sleep(1)
            else:
                return json.dumps({"error": f"Element not found: {selector}"})
        _mark_activity()
        return json.dumps({"clicked": selector, "status": "ok"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_type(selector: str, text: str, press_enter: bool = False) -> str:
    """Type into input field."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            page.fill(selector, text, timeout=10000)
            if press_enter:
                page.press(selector, 'Enter')
            time.sleep(0.5)
        else:
            tab = _get_drission_browser()
            elem = tab.ele(selector)
            if elem:
                elem.clear()
                elem.input(text)
                if press_enter:
                    from DrissionPage.common import Keys
                    elem.input(Keys.ENTER)
                time.sleep(0.5)
            else:
                return json.dumps({"error": f"Element not found: {selector}"})
        _mark_activity()
        return json.dumps({"typed": text, "selector": selector, "status": "ok"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_get_text(selector: str = "body") -> str:
    """Get text from page."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            if selector == "body":
                html = page.content()
                clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<[^>]+>', ' ', clean)
                clean = re.sub(r'\s+', ' ', clean).strip()
            else:
                clean = page.text_content(selector, timeout=10000) or ""
        else:
            tab = _get_drission_browser()
            if selector == "body":
                html = tab.html
                clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'<[^>]+>', ' ', clean)
                clean = re.sub(r'\s+', ' ', clean).strip()
            else:
                elem = tab.ele(selector)
                clean = elem.text if elem else "Element not found"

        if len(clean) > 10000:
            clean = clean[:10000] + "\n... (truncated)"
        _mark_activity()
        return json.dumps({"text": clean, "selector": selector})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_get_links() -> str:
    """Get all links."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            links_data = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    url: a.href,
                    text: (a.textContent || '').trim().substring(0, 100)
                })).filter(l => l.url.startsWith('http')).slice(0, 50)
            """)
        else:
            tab = _get_drission_browser()
            links_data = []
            for elem in tab.eles('tag:a'):
                href = elem.attr('href')
                text = elem.text.strip()
                if href and href.startswith('http'):
                    links_data.append({"url": href, "text": text[:100]})
            links_data = links_data[:50]

        _mark_activity()
        return json.dumps({"links": links_data, "total": len(links_data)})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_evaluate(js_code: str) -> str:
    """Execute JavaScript."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            result = page.evaluate(js_code)
        else:
            tab = _get_drission_browser()
            result = tab.run_js(js_code)
        _mark_activity()
        return json.dumps({"result": str(result)[:5000]})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_wait_for(selector: str, timeout: int = 10) -> str:
    """Wait for element."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            page.wait_for_selector(selector, timeout=timeout * 1000)
            text = page.text_content(selector, timeout=5000) or ""
        else:
            tab = _get_drission_browser()
            elem = tab.ele(selector, timeout=timeout)
            text = elem.text if elem else ""

        _mark_activity()
        return json.dumps({"found": selector, "text": text[:200]})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_screenshot(path: str = "/tmp/mimo_screenshot.png") -> str:
    """Take screenshot."""
    try:
        _mark_activity()
        if _browser_engine == "playwright":
            page = _get_playwright_browser()
            page.screenshot(path=path)
        else:
            tab = _get_drission_browser()
            tab.get_screenshot(path)
        _mark_activity()
        return json.dumps({"screenshot": path, "status": "ok"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Status ─────────────────────────────────────────────────────────────────

def get_browser_status() -> Dict[str, Any]:
    """Get current browser status."""
    last_activity_age = int(time.time() - _last_activity_time) if _last_activity_time else 0
    return {
        "engine": _browser_engine,
        "alive": _is_browser_alive() if _browser_engine == "drission" else _is_playwright_alive(),
        "last_url": _last_url,
        "age_seconds": int(time.time() - _browser_start_time) if _browser_start_time else 0,
        "idle_seconds": last_activity_age,
        "idle_timeout_seconds": _idle_timeout_seconds(),
        "active_tasks": _active_tasks,
    }
