"""
Nexus Task Wrapper - Unified Error and Status Management.
Ensures that all orchestrator tasks report status to the TUI.
"""

import asyncio
import logging
from typing import Callable, Any, Awaitable

class OrchestrationTask:
    def __init__(self, tui_app: Any, task_func: Awaitable[Any]):
        self.tui = tui_app
        self.task = task_func

    async def run(self):
        """Execute task with global error handling and UI feedback."""
        try:
            self.tui.query_one("StatusBar").update(message="Brain: Thinking...")
            await self.task
            self.tui.query_one("StatusBar").update(message="Brain: Ready.")
        except Exception as e:
            logging.error(f"Orchestration Error: {e}")
            self.tui.query_one("StatusBar").update(message=f"Brain Error: {str(e)[:30]}...")
            # Potentially trigger a visual alert in chat
            self.tui.query_one("#chat-panel").add_message(f"SYSTEM ERROR: {e}")
        finally:
            pass
