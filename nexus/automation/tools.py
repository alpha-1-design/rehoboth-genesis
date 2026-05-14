"""Browser and API automation tools for Nexus with shared session management."""

from typing import Any

from ..tools.base import BaseTool, ToolDefinition, ToolResult


def _get_browser():
    from ..automation.browser import BrowserManager
    return BrowserManager.get()


class BrowserNavigateTool(BaseTool):
    name = "browser_navigate"
    description = "Navigate to a URL in the browser. Use this to open any webpage before filling forms or clicking."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"},
                    "wait": {"type": "string", "description": "Wait condition: load, domcontentloaded, networkidle"},
                },
                "required": ["url"],
            },
            category="automation",
        )

    async def execute(self, url: str, wait: str = "networkidle", **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserAutomation

            browser = _get_browser()
            if browser is None:
                browser = BrowserAutomation()
                await browser.start()

            result = await browser.navigate(url, wait_until=wait)

            blocked, msg = await browser.is_blocked()
            if blocked:
                return ToolResult(success=False, content=f"BLOCKED: {msg}", error=msg)

            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Navigation failed: {e}", error=str(e))


class BrowserFillFormTool(BaseTool):
    name = "browser_fill_form"
    description = "Fill form fields on the current page. Each field has a CSS selector and value. Use after browser_navigate."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "array",
                        "description": "Form fields to fill",
                        "items": {
                            "type": "object",
                            "properties": {
                                "selector": {"type": "string", "description": "CSS selector for the field"},
                                "value": {"type": "string", "description": "Value to fill"},
                                "type": {"type": "string", "description": "Field type: input, select, checkbox, radio"},
                            },
                            "required": ["selector", "value"],
                        },
                    },
                },
                "required": ["fields"],
            },
            category="automation",
        )

    async def execute(self, fields: list[dict[str, Any]], **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager, FormField

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session. Use browser_navigate first.")

            form_fields = [
                FormField(
                    selector=f.get("selector", ""),
                    value=f.get("value", ""),
                    field_type=f.get("type", "input"),
                )
                for f in fields
            ]

            result = await browser.fill_form(form_fields)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Fill form failed: {e}", error=str(e))


class BrowserClickTool(BaseTool):
    name = "browser_click"
    description = "Click an element on the page. Use CSS selector or 'text:' prefix for text matching."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector (e.g., '#submit', 'button.primary') or 'text:Click me'"},
                },
                "required": ["selector"],
            },
            category="automation",
        )

    async def execute(self, selector: str, **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            result = await browser.click(selector)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Click failed: {e}", error=str(e))


class BrowserScreenshotTool(BaseTool):
    name = "browser_screenshot"
    description = "Take a screenshot of the current page. Saves to a file or returns base64."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to save. If omitted, returns base64."},
                    "full_page": {"type": "boolean", "description": "Capture full page vs viewport"},
                },
            },
            category="automation",
        )

    async def execute(self, path: str | None = None, full_page: bool = False, **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            result = await browser.screenshot(path=path, full_page=full_page)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Screenshot failed: {e}", error=str(e))


class BrowserGetContentTool(BaseTool):
    name = "browser_get_content"
    description = "Get text content from the page or a specific element."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector. If omitted, returns full page content."},
                },
            },
            category="automation",
        )

    async def execute(self, selector: str | None = None, **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            content = await browser.get_content(selector)
            return ToolResult(success=True, content=content)
        except Exception as e:
            return ToolResult(success=False, content=f"Get content failed: {e}", error=str(e))


class BrowserSubmitFormTool(BaseTool):
    name = "browser_submit_form"
    description = "Submit a form. Automatically detects and stops if CAPTCHA is present."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Form CSS selector"},
                },
            },
            category="automation",
        )

    async def execute(self, selector: str = "form", **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            result = await browser.submit(selector)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Submit failed: {e}", error=str(e))


class BrowserTypeTool(BaseTool):
    name = "browser_type"
    description = "Type text into an input field with human-like keystroke timing."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input field"},
                    "text": {"type": "string", "description": "Text to type"},
                    "delay": {"type": "integer", "description": "Ms delay between keystrokes"},
                },
                "required": ["selector", "text"],
            },
            category="automation",
        )

    async def execute(self, selector: str, text: str, delay: int = 50, **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            result = await browser.type_text(selector, text, delay)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Type failed: {e}", error=str(e))


class BrowserScrollTool(BaseTool):
    name = "browser_scroll"
    description = "Scroll the page down or up."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "down or up"},
                    "amount": {"type": "integer", "description": "Pixels to scroll"},
                },
            },
            category="automation",
        )

    async def execute(self, direction: str = "down", amount: int = 500, **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            y = amount if direction == "down" else -amount
            result = await browser.scroll(y=y)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"Scroll failed: {e}", error=str(e))


class BrowserCloseTool(BaseTool):
    name = "browser_close"
    description = "Close the browser session and clean up resources."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={"type": "object", "properties": {}},
            category="automation",
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            await BrowserManager.close()
            return ToolResult(success=True, content="Browser session closed.")
        except Exception as e:
            return ToolResult(success=False, content=f"Close failed: {e}", error=str(e))


class BrowserSolveCaptchaTool(BaseTool):
    name = "browser_solve_captcha"
    description = "Attempt to handle a CAPTCHA challenge. Returns guidance for manual solving if needed."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "captcha_type": {"type": "string", "description": "Type of CAPTCHA if known"},
                },
            },
            category="automation",
        )

    async def execute(self, captcha_type: str = "image", **kwargs) -> ToolResult:
        try:
            from ..automation.browser import BrowserManager

            browser = BrowserManager.get()
            if not browser:
                return ToolResult(success=False, content="No browser session.")

            result = await browser.solve_captcha(captcha_type)
            return ToolResult(success=True, content=result)
        except Exception as e:
            return ToolResult(success=False, content=f"CAPTCHA solve failed: {e}", error=str(e))


def _get_api_client():
    from ..automation.api_client import ApiAutomation
    return ApiAutomation()


class ApiFetchTool(BaseTool):
    name = "api_fetch"
    description = "Make a GET request to any URL. Use for fetching page content, APIs, or JSON data."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                    "params": {"type": "object", "description": "Query string parameters"},
                    "headers": {"type": "object", "description": "Additional HTTP headers"},
                },
                "required": ["url"],
            },
            category="automation",
        )

    async def execute(self, url: str, params: dict | None = None,
                      headers: dict | None = None, **kwargs) -> ToolResult:
        try:
            import json
            client = _get_api_client()
            result = await client.get(url, params=params or {}, headers=headers or {})

            if result.get("blocked"):
                return ToolResult(
                    success=False,
                    content=f"Request blocked (status {result.get('status')}). "
                            "Consider using browser_navigate instead.",
                    error=f"HTTP {result.get('status')}",
                )

            if result.get("json"):
                return ToolResult(success=True, content=json.dumps(result["json"], indent=2))
            elif result.get("html"):
                return ToolResult(success=True, content=result["html"])
            elif result.get("text"):
                return ToolResult(success=True, content=result["text"])
            else:
                return ToolResult(success=True, content=f"Status {result.get('status')}")
        except ImportError:
            return ToolResult(success=False, content="httpx not installed. Run: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, content=f"API fetch failed: {e}", error=str(e))


class ApiPostTool(BaseTool):
    name = "api_post"
    description = "Make a POST request. Use for form submissions, API calls, JSON payloads."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to post to"},
                    "data": {"type": "object", "description": "Form data (application/x-www-form-urlencoded)"},
                    "json_data": {"type": "object", "description": "JSON body (application/json)"},
                    "params": {"type": "object", "description": "Query string parameters"},
                    "headers": {"type": "object", "description": "Additional HTTP headers"},
                },
                "required": ["url"],
            },
            category="automation",
        )

    async def execute(self, url: str, data: dict | None = None,
                      json_data: dict | None = None, params: dict | None = None,
                      headers: dict | None = None, **kwargs) -> ToolResult:
        try:
            import json
            client = _get_api_client()
            result = await client.post(
                url, data=data or {}, params=params or {},
                headers=headers or {}, json_data=json_data,
            )

            if result.get("blocked"):
                return ToolResult(
                    success=False,
                    content=f"Request blocked (status {result.get('status')}). "
                            "Consider using browser_fill_form instead.",
                    error=f"HTTP {result.get('status')}",
                )

            if result.get("json"):
                return ToolResult(success=True, content=json.dumps(result["json"], indent=2))
            elif result.get("text"):
                return ToolResult(success=True, content=result["text"])
            else:
                return ToolResult(success=True, content=f"Status {result.get('status')}")
        except ImportError:
            return ToolResult(success=False, content="httpx not installed. Run: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, content=f"API post failed: {e}", error=str(e))


class ExtractFormsTool(BaseTool):
    name = "extract_forms"
    description = "Extract all forms and their fields from HTML content. Use to discover form structure before filling."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "html": {"type": "string", "description": "HTML content to parse"},
                },
                "required": ["html"],
            },
            category="automation",
        )

    async def execute(self, html: str, **kwargs) -> ToolResult:
        try:
            import json

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            forms = soup.find_all("form")

            if not forms:
                return ToolResult(success=False, content="No forms found in HTML.", error="No forms")

            result = []
            for i, form in enumerate(forms):
                form_info = {
                    "index": i,
                    "action": form.get("action", ""),
                    "method": form.get("method", "get").upper(),
                    "fields": [],
                }

                for field in form.find_all(["input", "select", "textarea"]):
                    field_info = {
                        "tag": field.name,
                        "name": field.get("name", ""),
                        "type": field.get("type", "text"),
                        "id": field.get("id", ""),
                        "placeholder": field.get("placeholder", ""),
                        "required": field.has_attr("required"),
                        "value": field.get("value", ""),
                    }
                    form_info["fields"].append(field_info)

                result.append(form_info)

            return ToolResult(success=True, content=json.dumps(result, indent=2))
        except ImportError as e:
            return ToolResult(
                success=False,
                content=f"Missing dependency: {e}. Run: pip install beautifulsoup4",
            )
        except Exception as e:
            return ToolResult(success=False, content=f"Form extraction failed: {e}", error=str(e))


class ApiUploadTool(BaseTool):
    name = "api_upload"
    description = "Upload files to a URL via multipart/form-data POST."

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The upload endpoint URL"},
                    "file_path": {"type": "string", "description": "Local path to the file to upload"},
                    "field_name": {"type": "string", "description": "Form field name for the file"},
                    "data": {"type": "object", "description": "Additional form fields"},
                },
                "required": ["url", "file_path"],
            },
            category="automation",
        )

    async def execute(self, url: str, file_path: str, field_name: str = "file",
                      data: dict | None = None, **kwargs) -> ToolResult:
        try:
            import json
            from pathlib import Path

            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, content=f"File not found: {file_path}")

            client = _get_api_client()
            with open(path, "rb") as f:
                files = {field_name: (path.name, f, "application/octet-stream")}
                result = await client.upload(url, files, data=data or {})

            if result.get("json"):
                return ToolResult(success=True, content=json.dumps(result["json"], indent=2))
            return ToolResult(success=True, content=result.get("text", f"Status {result.get('status')}"))
        except ImportError:
            return ToolResult(success=False, content="httpx not installed. Run: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, content=f"Upload failed: {e}", error=str(e))
