"""Browser automation using Playwright with stealth/anti-detection."""

from __future__ import annotations

import asyncio
import base64
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_browser_manager: BrowserManager | None = None


class BrowserManager:
    """Singleton browser session manager for shared tool access."""

    _instance: BrowserManager | None = None

    def __init__(self):
        self.browser: BrowserAutomation | None = None
        self.session_id: str = ""
        self.session_start: float = 0.0

    @classmethod
    def get_instance(cls) -> BrowserManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get(cls) -> BrowserAutomation | None:
        """Get the current browser instance."""
        return cls.get_instance().browser

    @classmethod
    def set(cls, browser: BrowserAutomation) -> None:
        """Set the current browser instance."""
        inst = cls.get_instance()
        inst.browser = browser
        inst.session_start = time.time()
        inst.session_id = f"session_{int(inst.session_start)}"

    @classmethod
    async def close(cls) -> None:
        """Close the current browser session."""
        inst = cls.get_instance()
        if inst.browser:
            await inst.browser.close()
            inst.browser = None
            inst.session_id = ""


def get_browser_manager() -> BrowserManager:
    return BrowserManager.get_instance()

try:
    from playwright.async_api import Browser, Page, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class BrowserConfig:
    """Configuration for browser automation."""
    headless: bool = True
    stealth: bool = True
    slow_mo: int = 0
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: str | None = None
    downloads_path: Path | None = None
    human_like: bool = True
    disable_webdriver: bool = True
    randomize_viewport: bool = True


STEEP_CHROME_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


STEALTH_SCRIPTS = [
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});",
    "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5], configurable: true});",
    "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'en-GB'], configurable: true});",
    """
    Object.defineProperty(navigator, 'permissions', {
        get: () => ({
            query: (p) => Promise.resolve({ state: 'prompt', onchange: null })
        })
    });
    """,
    """
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
        get: function() {
            return function(type, attributes) {
                const orig = HTMLCanvasElement.prototype._getContext || HTMLCanvasElement.prototype.getContext;
                const context = orig.call(this, type, attributes);
                if (type === '2d') {
                    const origGet = context.getImageData;
                    context.getImageData = function(sx, sy, sw, sh) {
                        const data = origGet.call(this, sx, sy, sw, sh);
                        for (let i = 0; i < data.data.length; i += Math.floor(Math.random() * 10) + 1) {
                            const delta = Math.floor(Math.random() * 2);
                            data.data[i] = Math.min(255, data.data[i] + delta);
                        }
                        return data;
                    };
                }
                return context;
            };
        }
    });
    """,
    """
    if (typeof navigator.maxTouchPoints === 'undefined') {
        Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0, configurable: true });
    }
    """,
    """
    if (!window.chrome) window.chrome = {};
    window.chrome.runtime = { sendMessage: () => {}, onMessage: { addListener: () => {} } };
    """,
]


def is_browser_available() -> bool:
    """Check if Playwright and a browser are available."""
    if not PLAYWRIGHT_AVAILABLE:
        return False
    try:
        import os
        cache = os.path.expanduser("~/.cache/ms-playwright")
        if os.path.exists(cache):
            for item in os.listdir(cache):
                path = os.path.join(cache, item)
                if os.path.isdir(path):
                    for sub in os.listdir(path):
                        if sub.endswith(".zip") or sub == "chrome-linux" or sub == "chromium" or "chromium" in sub:
                            return True
        return False
    except Exception:
        return False


@dataclass
class FormField:
    """Represents a form field to fill."""
    selector: str
    value: str
    field_type: str = "input"
    delay: int = 0


class BrowserAutomation:
    """Browser automation using Playwright with anti-detection."""

    def __init__(self, config: BrowserConfig | None = None):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._context = None
        self._page_metadata: dict = {}

    def _random_viewport(self) -> dict[str, int]:
        """Generate random viewport dimensions."""
        widths = [1280, 1366, 1440, 1536, 1920]
        heights = [720, 768, 800, 900, 1000]
        return {
            "width": random.choice(widths) if self.config.randomize_viewport else self.config.viewport_width,
            "height": random.choice(heights) if self.config.randomize_viewport else self.config.viewport_height,
        }

    def _random_user_agent(self) -> str:
        """Pick a random user agent."""
        if self.config.user_agent:
            return self.config.user_agent
        return random.choice(STEEP_CHROME_USER_AGENTS)

    async def _apply_stealth(self, page: Page) -> None:
        """Apply stealth/anti-detection patches."""
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
        """)

        for script in STEALTH_SCRIPTS:
            await page.add_init_script(script)

        await page.context.new_page()

    async def start(self) -> BrowserAutomation:
        """Start the browser with optional stealth mode."""
        self._playwright = await async_playwright().start()

        viewport = self._random_viewport()
        user_agent = self._random_user_agent()

        launch_options: dict[str, Any] = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
                "--window-size=1920,1080",
                "--start-maximized",
            ],
        }

        if self.config.downloads_path:
            self.config.downloads_path.mkdir(parents=True, exist_ok=True)

        try:
            self._browser = await self._playwright.chromium.launch(**launch_options)
        except Exception:
            launch_options["args"] = [a for a in launch_options["args"] if "--disable-gpu" not in a]
            self._browser = await self._playwright.chromium.launch(**launch_options)

        context_options: dict[str, Any] = {
            "viewport": viewport,
            "user_agent": user_agent,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "geolocation": {"latitude": 40.7128, "longitude": -74.0060},
            "permissions": ["geolocation"],
            "ignore_https_errors": True,
        }

        self._context = await self._browser.new_context(**context_options)

        if self.config.stealth:
            self._context.set_default_timeout(30000)

        self._page = await self._context.new_page()

        if self.config.stealth:
            await self._apply_stealth(self._page)

        self._page_metadata = {"url": "", "title": ""}
        self._page.on("load", lambda p: self._page_metadata.update({"url": p.url, "title": p.title()}))

        BrowserManager.set(self)

        return self

    async def navigate(self, url: str, wait_until: str = "networkidle",
                       timeout: int = 30000) -> str:
        """Navigate to a URL with anti-bot checks."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        if self.config.human_like:
            await asyncio.sleep(random.uniform(0.5, 1.5))

        response = await self._page.goto(url, wait_until=wait_until, timeout=timeout)
        status = response.status if response else 0

        self._page_metadata = {"url": url, "title": await self._page.title()}

        if status in (403, 406):
            return f"BLOCKED ({status}) — site may have bot detection"

        if self.config.human_like:
            await self._human_scroll()

        return f"Navigated to {url} (status: {status})"

    async def _human_scroll(self) -> None:
        """Human-like scrolling behavior."""
        if not self._page:
            return
        for _ in range(random.randint(2, 4)):
            await self._page.mouse.wheel(0, random.randint(200, 600))
            await asyncio.sleep(random.uniform(0.2, 0.5))

    async def _human_mouse_move(self, x: int, y: int) -> None:
        """Move mouse in a human-like curve."""
        if not self._page:
            return

        start_x = random.randint(0, 200)
        start_y = random.randint(0, 200)
        steps = random.randint(8, 15)

        for i in range(steps):
            progress = i / steps
            ease = progress - (1 - (1 - progress) ** 3)
            current_x = int(start_x + (x - start_x) * ease)
            current_y = int(start_y + (y - start_y) * ease)
            await self._page.mouse.move(current_x, current_y)
            await asyncio.sleep(random.uniform(0.01, 0.03))

        await self._page.mouse.move(x, y)

    async def _check_for_captcha(self) -> tuple[bool, str]:
        """Check if the page has a CAPTCHA or challenge."""
        if not self._page:
            return False, ""

        captcha_indicators = [
            "g-recaptcha", "g-resp", "captcha", "challenge", "Challenge",
            "cf-challenge", "h-captcha", "Turnstile", "arkose", "hcaptcha",
            "data-sitekey", "recaptcha/api", "challenges.cloudflare.com",
        ]

        content = await self._page.content()

        for indicator in captcha_indicators:
            if indicator.lower() in content.lower():
                url = self._page.url
                title = await self._page.title()
                return True, f"CAPTCHA detected on {url}: {title}"

        return False, ""

    async def screenshot(self, path: str | None = None, full_page: bool = False) -> str:
        """Take a screenshot."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        if path:
            await self._page.screenshot(path=path, full_page=full_page)
            return f"Screenshot saved to {path}"
        else:
            bytes_data = await self._page.screenshot(full_page=full_page)
            return base64.b64encode(bytes_data).decode()

    async def fill_form(self, fields: list[FormField]) -> str:
        """Fill form fields with human-like timing."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        filled, failed = [], []
        for field_data in fields:
            try:
                if self.config.human_like:
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    await self._page.hover(field_data.selector)
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                if field_data.field_type == "select":
                    await self._page.select_option(field_data.selector, field_data.value)
                elif field_data.field_type == "checkbox":
                    if field_data.value.lower() in ("true", "1", "yes", "check"):
                        await self._page.check(field_data.selector)
                    else:
                        await self._page.uncheck(field_data.selector)
                elif field_data.field_type == "radio":
                    await self._page.click(f'{field_data.selector}[value="{field_data.value}"]')
                else:
                    delay = field_data.delay or random.randint(30, 80)
                    await self._page.fill(field_data.selector, field_data.value, delay=delay)

                filled.append(field_data.selector)
            except Exception as e:
                failed.append(f"{field_data.selector}: {e}")

        return f"Filled {len(filled)}/{len(fields)} fields" + (f" | Failed: {', '.join(failed)}" if failed else "")

    async def click(self, selector: str, timeout: int = 5000) -> str:
        """Click an element with human-like behavior."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        element = await self._page.query_selector(selector)
        if not element:
            return f"Element not found: {selector}"

        box = await element.bounding_box()
        if box and self.config.human_like:
            cx, cy = int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)
            await self._human_mouse_move(cx, cy)
            await asyncio.sleep(random.uniform(0.1, 0.3))

        await self._page.click(selector, timeout=timeout)

        if self.config.human_like:
            await asyncio.sleep(random.uniform(0.1, 0.3))

        return f"Clicked: {selector}"

    async def submit(self, selector: str = "form") -> str:
        """Submit a form."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        captcha_detected, msg = await self._check_for_captcha()
        if captcha_detected:
            return f"STOPPED: {msg}"

        try:
            await self._page.click(f"{selector} button[type='submit']", timeout=3000)
        except Exception:
            await self._page.click(selector, timeout=3000)

        await asyncio.sleep(random.uniform(1.0, 2.0))
        return f"Submitted form: {selector}"

    async def get_content(self, selector: str | None = None) -> str:
        """Get page or element content."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        captcha_detected, msg = await self._check_for_captcha()
        if captcha_detected:
            return f"WARNING: {msg}"

        if selector:
            element = await self._page.query_selector(selector)
            if element:
                return await element.inner_text()
            return f"Element not found: {selector}"
        else:
            return await self._page.content()

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> str:
        """Wait for an element to appear."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return f"Element appeared: {selector}"
        except Exception:
            return f"Element did NOT appear in {timeout}ms: {selector}"

    async def type_text(self, selector: str, text: str, delay: int = 50) -> str:
        """Type text with human-like variation."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        await self._page.click(selector)
        await self._page.keyboard.type(text, delay=delay + random.randint(-20, 20))
        return f"Typed text into: {selector}"

    async def press_key(self, selector: str, key: str) -> str:
        """Press a key."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        await self._page.press(selector, key)
        return f"Pressed {key} on: {selector}"

    async def hover(self, selector: str) -> str:
        """Hover over an element."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        await self._page.hover(selector)
        return f"Hovered: {selector}"

    async def scroll(self, x: int = 0, y: int = 500) -> str:
        """Scroll the page."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        await self._page.mouse.wheel(x, y)
        return f"Scrolled ({x}, {y})"

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        return await self._page.evaluate(script)

    async def get_cookies(self) -> list[dict]:
        """Get browser cookies."""
        if not self._context:
            raise RuntimeError("Browser context not started.")
        return await self._context.cookies()

    async def set_cookies(self, cookies: list[dict]) -> str:
        """Set browser cookies."""
        if not self._context:
            raise RuntimeError("Browser context not started.")
        await self._context.add_cookies(cookies)
        return f"Set {len(cookies)} cookies"

    async def is_blocked(self) -> tuple[bool, str]:
        """Check if the current page blocked us."""
        return await self._check_for_captcha()

    async def solve_captcha(self, captcha_type: str = "image") -> str:
        """Attempt to solve a CAPTCHA. Returns instructions if manual solving needed.
        
        Note: Most CAPTCHAs require human solving. This will attempt known
        strategies and fall back to manual instructions for the user.
        """
        if not self._page:
            return "No active page"

        title = await self._page.title()
        url = self._page.url

        if "cloudflare" in url.lower() or "cf-" in title.lower():
            await asyncio.sleep(2)
            return "Cloudflare challenge — waiting for verification"

        if "recaptcha" in title.lower() or "g-recaptcha" in await self._page.content().lower():
            return ("reCAPTCHA detected — manual solving required. "
                    "Instructions: 1) Take screenshot, 2) Solve at 2captcha.com or "
                    "anti-captcha.com, 3) Use the returned token with browser.evaluate()")

        if "hcaptcha" in await self._page.content().lower():
            return ("hCaptcha detected — manual solving required. "
                    "Use anti-captcha.com with site key")

        return "Unknown CAPTCHA type"

    async def close(self) -> None:
        """Close the browser."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> BrowserAutomation:
        return await self.start()

    async def __aexit__(self, *args) -> None:
        await self.close()


def parse_selector(selector_str: str) -> dict[str, str]:
    """Parse a selector string into type and value."""
    if selector_str.startswith("text:"):
        return {"type": "text", "value": selector_str[5:]}
    elif selector_str.startswith("xpath:"):
        return {"type": "xpath", "value": selector_str[6:]}
    elif selector_str.startswith("//"):
        return {"type": "xpath", "value": selector_str}
    else:
        return {"type": "css", "value": selector_str}
