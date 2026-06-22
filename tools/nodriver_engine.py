"""
nodriver_engine.py — Nodriver Browser Engine
Lightweight, undetectable Chrome automation with fingerprinting.
Replaces Camofox for browser tasks.
"""
import asyncio
import json
import os
import time
from typing import Any, Dict, Optional

# ─── Nodriver Browser Manager ──────────────────────────────────────────────

class NodriverEngine:
    """Nodriver browser engine for undetectable automation."""
    
    def __init__(self):
        self.browser = None
        self.tab = None
        self._loop = None
    
    async def _get_loop(self):
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop
    
    async def start(self):
        """Start the browser."""
        import nodriver as uc
        
        if self.browser:
            return
        
        self.browser = await uc.start(
            headless=True,
            browser_args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-size=1280,800',
            ]
        )
        self.tab = await self.browser.get('about:blank')
    
    async def stop(self):
        """Stop the browser."""
        if self.browser:
            try:
                self.browser.stop()
            except:
                pass
            self.browser = None
            self.tab = None
    
    async def open(self, url: str, wait: int = 3) -> Dict[str, Any]:
        """Open a URL and return page info."""
        try:
            if not self.browser:
                await self.start()
            
            self.tab = await self.browser.get(url)
            
            # Wait for page to load
            await asyncio.sleep(wait)
            
            # Get page info
            title = await self.tab.evaluate('document.title')
            content = await self.tab.evaluate('document.body.innerText')
            
            return {
                'success': True,
                'url': url,
                'title': title or '',
                'content': content[:5000] if content else '',
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url,
            }
    
    async def screenshot(self, path: str = '/tmp/nodriver_screenshot.png') -> Dict[str, Any]:
        """Take a screenshot."""
        try:
            if not self.tab:
                return {'success': False, 'error': 'No tab open'}
            
            await self.tab.save_screenshot(path)
            return {
                'success': True,
                'path': path,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }
    
    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element."""
        try:
            if not self.tab:
                return {'success': False, 'error': 'No tab open'}
            
            element = await self.tab.find(selector, best_match=True)
            await element.click()
            
            return {
                'success': True,
                'selector': selector,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'selector': selector,
            }
    
    async def type(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into an element."""
        try:
            if not self.tab:
                return {'success': False, 'error': 'No tab open'}
            
            element = await self.tab.find(selector, best_match=True)
            await element.clear_input()
            await element.send_keys(text)
            
            return {
                'success': True,
                'selector': selector,
                'text': text,
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'selector': selector,
            }
    
    async def get_text(self) -> str:
        """Get page text."""
        try:
            if not self.tab:
                return ''
            return await self.tab.evaluate('document.body.innerText')
        except:
            return ''
    
    async def get_url(self) -> str:
        """Get current URL."""
        try:
            if not self.tab:
                return ''
            return await self.tab.evaluate('window.location.href')
        except:
            return ''

# ─── Global Instance ──────────────────────────────────────────────────────

_engine = NodriverEngine()

def get_engine() -> NodriverEngine:
    """Get the global nodriver engine."""
    return _engine

# ─── Sync Wrappers ──────────────────────────────────────────────────────

def nodriver_open(url: str, wait: int = 3) -> str:
    """Open URL with nodriver (sync wrapper)."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_engine.open(url, wait))
        return json.dumps(result)
    finally:
        loop.close()

def nodriver_screenshot(path: str = '/tmp/nodriver_screenshot.png') -> str:
    """Take screenshot (sync wrapper)."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_engine.screenshot(path))
        return json.dumps(result)
    finally:
        loop.close()

def nodriver_click(selector: str) -> str:
    """Click element (sync wrapper)."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_engine.click(selector))
        return json.dumps(result)
    finally:
        loop.close()

def nodriver_type(selector: str, text: str) -> str:
    """Type text (sync wrapper)."""
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_engine.type(selector, text))
        return json.dumps(result)
    finally:
        loop.close()

def nodriver_close() -> str:
    """Close browser (sync wrapper)."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_engine.stop())
        return json.dumps({'success': True, 'message': 'Browser closed'})
    finally:
        loop.close()

# ─── Register Tools ──────────────────────────────────────────────────────

def register_nodriver_tools(register_tool):
    """Register nodriver browser tools."""
    register_tool(
        name='nodriver_open',
        description='Open URL with undetectable Chrome (nodriver)',
        parameters={
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'description': 'URL to open'},
                'wait': {'type': 'integer', 'description': 'Wait seconds', 'default': 3},
            },
            'required': ['url'],
        },
        handler=lambda args: nodriver_open(args.get('url', ''), args.get('wait', 3))
    )
    
    register_tool(
        name='nodriver_screenshot',
        description='Take screenshot with nodriver',
        parameters={
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Screenshot path', 'default': '/tmp/nodriver_screenshot.png'},
            },
        },
        handler=lambda args: nodriver_screenshot(args.get('path', '/tmp/nodriver_screenshot.png'))
    )
    
    register_tool(
        name='nodriver_click',
        description='Click element with nodriver',
        parameters={
            'type': 'object',
            'properties': {
                'selector': {'type': 'string', 'description': 'CSS selector'},
            },
            'required': ['selector'],
        },
        handler=lambda args: nodriver_click(args.get('selector', ''))
    )
    
    register_tool(
        name='nodriver_type',
        description='Type text with nodriver',
        parameters={
            'type': 'object',
            'properties': {
                'selector': {'type': 'string', 'description': 'CSS selector'},
                'text': {'type': 'string', 'description': 'Text to type'},
            },
            'required': ['selector', 'text'],
        },
        handler=lambda args: nodriver_type(args.get('selector', ''), args.get('text', ''))
    )
    
    register_tool(
        name='nodriver_close',
        description='Close nodriver browser',
        parameters={'type': 'object', 'properties': {}},
        handler=lambda args: nodriver_close()
    )
