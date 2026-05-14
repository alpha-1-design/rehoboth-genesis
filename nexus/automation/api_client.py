"""API automation client for HTTP-based web interactions with anti-detection."""

import random
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


REALISTIC_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


@dataclass
class ApiRequest:
    """Represents an API request."""

    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    json_data: dict[str, Any] | None = None
    auth: tuple[str, str] | None = None
    timeout: int = 30
    referrer: str | None = None


@dataclass
class ApiAutomation:
    """API automation client with session, cookie management, and anti-detection."""

    base_url: str = ""
    headers: dict[str, str] = field(
        default_factory=lambda: {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
    )
    cookies: dict[str, str] = field(default_factory=dict)
    auth: tuple[str, str] | None = None
    timeout: int = 30
    user_agent_rotation: bool = True
    min_delay: float = 1.0
    max_delay: float = 3.0
    proxy: str | None = None

    _client: "httpx.AsyncClient | None" = None
    _response_history: list[dict] = field(default_factory=list)
    _last_request_time: float = 0.0
    _request_count: int = 0
    _current_user_agent: str = field(default_factory=lambda: random.choice(REALISTIC_USER_AGENTS))

    def __post_init__(self):
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx not installed. Run: pip install httpx")

    async def _get_client(self) -> "httpx.AsyncClient":
        """Get or create the HTTP client."""
        if self._client is None:
            cookies = {**self.cookies} if self.cookies else {}

            transport = httpx.AsyncHTTPTransport(retries=1)

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                cookies=cookies,
                auth=self.auth,
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=True,
                transport=transport,
            )
        return self._client

    def _rotate_headers(self, request: ApiRequest) -> dict[str, str]:
        """Apply anti-detection header rotation."""
        headers = {**self.headers, **request.headers}

        if self.user_agent_rotation:
            headers["User-Agent"] = self._current_user_agent

        if request.referrer:
            headers["Referer"] = request.referrer
        elif self._request_count > 0:
            prev = self._response_history[-1] if self._response_history else None
            if prev:
                headers["Referer"] = prev.get("url", "")

        if self._request_count == 0:
            headers["Sec-Fetch-Site"] = "none"
            headers["Sec-Fetch-Dest"] = "document"
        else:
            headers["Sec-Fetch-Site"] = "same-origin"
            headers["Sec-Fetch-Dest"] = "empty"

        return headers

    def _apply_delay(self) -> None:
        """Apply realistic delay between requests."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    async def request(self, request: ApiRequest) -> dict[str, Any]:
        """Execute an API request with anti-detection."""
        self._apply_delay()

        client = await self._get_client()

        request_headers = self._rotate_headers(request)
        request_params = {**request.params}
        request_data = request.data.copy()

        self._request_count += 1

        try:
            response = await client.request(
                method=request.method,
                url=request.url,
                headers=request_headers,
                params=request_params,
                content=request_data,
                json=request.json_data,
                auth=request.auth or self.auth,
            )

            result = {
                "status": response.status_code,
                "headers": dict(response.headers),
                "cookies": dict(response.cookies),
                "url": str(response.url),
                "request_count": self._request_count,
            }

            content_type = response.headers.get("content-type", "")

            if "json" in content_type:
                try:
                    result["json"] = response.json()
                except Exception:
                    result["text"] = response.text
            elif "html" in content_type:
                result["html"] = response.text
            else:
                result["text"] = response.text

            if response.cookies:
                self.cookies.update(response.cookies)

            self._response_history.append(result)
            return result

        except httpx.HTTPStatusError as e:
            result = {
                "status": e.response.status_code,
                "error": str(e),
                "url": str(e.request.url),
                "blocked": e.response.status_code in (403, 406, 429),
                "request_count": self._request_count,
            }
            self._response_history.append(result)
            return result

    async def get(self, url: str, **kwargs) -> dict[str, Any]:
        """Make a GET request."""
        return await self.request(ApiRequest(method="GET", url=url, **kwargs))

    async def post(self, url: str, **kwargs) -> dict[str, Any]:
        """Make a POST request."""
        return await self.request(ApiRequest(method="POST", url=url, **kwargs))

    async def put(self, url: str, **kwargs) -> dict[str, Any]:
        """Make a PUT request."""
        return await self.request(ApiRequest(method="PUT", url=url, **kwargs))

    async def patch(self, url: str, **kwargs) -> dict[str, Any]:
        """Make a PATCH request."""
        return await self.request(ApiRequest(method="PATCH", url=url, **kwargs))

    async def delete(self, url: str, **kwargs) -> dict[str, Any]:
        """Make a DELETE request."""
        return await self.request(ApiRequest(method="DELETE", url=url, **kwargs))

    async def fill_form(self, url: str, form_data: dict[str, Any], method: str = "POST") -> dict[str, Any]:
        """Submit form data to a URL."""
        return await self.request(
            ApiRequest(
                method=method,
                url=url,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        )

    async def upload(self, url: str, files: dict[str, Any], data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Upload files to a URL."""
        client = await self._get_client()

        files_data = {}
        for name, file_info in files.items():
            if isinstance(file_info, tuple):
                files_data[name] = file_info
            else:
                files_data[name] = (file_info, "")

        response = await client.request(
            method="POST",
            url=url,
            files=files_data,
            data=data or {},
        )

        return {
            "status": response.status_code,
            "text": response.text,
            "json": response.json() if "json" in response.headers.get("content-type", "") else None,
        }

    async def login(
        self, url: str, username: str, password: str, username_field: str = "username", password_field: str = "password", submit_field: str = "submit"
    ) -> dict[str, Any]:
        """Perform login to a website."""
        client = await self._get_client()

        response = await client.get(url)
        html = response.text

        form_action = None
        form_method = "POST"

        form_match = re.search(r'<form[^>]*action=["\']([^"\']*)["\'][^>]*method=["\']?([^["\'>\s]*)', html, re.IGNORECASE)
        if form_match:
            form_action = form_match.group(1)
            form_method = form_match.group(2).upper() or "POST"

        if not form_action:
            form_action = url

        form_data = {username_field: username, password_field: password}

        return await self.request(
            ApiRequest(
                method=form_method,
                url=urljoin(url, form_action),
                data=form_data,
            )
        )

    async def extract_from_html(self, html: str, pattern: str) -> list[str]:
        """Extract text from HTML using regex pattern."""
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        return [m.strip() for m in matches if m.strip()]

    async def extract_links(self, html: str, base_url: str = "") -> list[dict[str, str]]:
        """Extract all links from HTML."""
        links = []
        pattern = r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>([^<]*)</a>'
        for href, text in re.findall(pattern, html, re.IGNORECASE):
            full_url = urljoin(base_url, href) if base_url else href
            links.append({"url": full_url, "text": text.strip()})
        return links

    async def extract_forms(self, html: str) -> list[dict[str, Any]]:
        """Extract all forms from HTML."""
        forms = []

        form_pattern = r"<form([^>]*)>(.*?)</form>"
        for form_tag, form_content in re.findall(form_pattern, html, re.DOTALL | re.IGNORECASE):
            form_info = {"action": "", "method": "GET", "fields": {}}

            action_match = re.search(r'action=["\']([^"\']*)["\']', form_tag, re.IGNORECASE)
            if action_match:
                form_info["action"] = action_match.group(1)

            method_match = re.search(r'method=["\']([^"\']*)["\']', form_tag, re.IGNORECASE)
            if method_match:
                form_info["method"] = method_match.group(1).upper()

            input_pattern = r'<input[^>]*name=["\']([^"\']*)["\'][^>]*>'
            for name in re.findall(input_pattern, form_content, re.IGNORECASE):
                form_info["fields"][name] = ""

            forms.append(form_info)

        return forms

    def get_history(self) -> list[dict[str, Any]]:
        """Get the response history."""
        return self._response_history

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "ApiAutomation":
        await self._get_client()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()


class ApiFlow:
    """Predefined automation flows."""

    @staticmethod
    async def github_login(api: ApiAutomation, token: str) -> dict[str, Any]:
        """GitHub API authentication."""
        return await api.get("https://api.github.com/user", headers={"Authorization": f"token {token}"})

    @staticmethod
    async def twitter_post(api: ApiAutomation, text: str, bearer_token: str) -> dict[str, Any]:
        """Post a tweet via Twitter API v2."""
        return await api.post(
            "https://api.twitter.com/2/tweets",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            },
            json_data={"text": text},
        )

    @staticmethod
    async def discord_message(api: ApiAutomation, webhook_url: str, content: str) -> dict[str, Any]:
        """Send a Discord webhook message."""
        return await api.post(
            webhook_url,
            json_data={"content": content},
            headers={"Content-Type": "application/json"},
        )

    @staticmethod
    async def slack_webhook(api: ApiAutomation, webhook_url: str, text: str, blocks: list | None = None) -> dict[str, Any]:
        """Send a Slack webhook message."""
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        return await api.post(webhook_url, json_data=payload)

    @staticmethod
    async def webhook_notify(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Generic webhook notification."""
        async with ApiAutomation() as api:
            return await api.post(url, json_data=payload)
