"""Loading states and progress indicators for plain REPL."""

import sys
import threading
import time


class LoadingIndicator:
    """Thread-safe loading indicator for terminal."""

    STATES = ["◌", "◐", "◑", "◒", "◓", "◔", "◕", "◖", "◗"]

    def __init__(self, message: str = "Working"):
        self.message = message
        self._running = False
        self._thread: threading.Thread | None = None
        self._done = threading.Event()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, final: str = "Done"):
        self._running = False
        self._done.set()
        if self._thread:
            self._thread.join(timeout=1)
        sys.stdout.write(f"\r{' ' * (len(self.message) + 10)}\r")
        sys.stdout.write(f"✓ {final}\n")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        while self._running:
            state = self.STATES[i % len(self.STATES)]
            sys.stdout.write(f"\r{state} {self.message}...")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

def with_loading(func):
    """Decorator to wrap a function with loading indicator."""
    def wrapper(*args, **kwargs):
        indicator = LoadingIndicator(f"Running {func.__name__}")
        indicator.start()
        try:
            result = func(*args, **kwargs)
            indicator.stop()
            return result
        except Exception as e:
            indicator.stop(f"Error: {e}")
            raise
    return wrapper

class ProgressTracker:
    """Track multi-step progress."""

    def __init__(self, total: int, description: str = ""):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()

    def step(self, label: str = "") -> None:
        self.current += 1
        pct = self.current / self.total if self.total > 0 else 0
        bar = "▓" * int(pct * 10) + "░" * (10 - int(pct * 10))
        elapsed = time.time() - self.start_time
        label_str = f" — {label}" if label else ""
        sys.stdout.write(
            f"\r[{bar}] {pct:.0%}{label_str} ({elapsed:.1f}s)"
        )
        sys.stdout.flush()

    def finish(self) -> None:
        elapsed = time.time() - self.start_time
        sys.stdout.write(f"\r{' ' * 60}\rDone in {elapsed:.1f}s\n")
        sys.stdout.flush()
