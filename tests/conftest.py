"""Root test configuration for pytest-asyncio on Windows."""

import asyncio
import sys


def pytest_configure(config):
    """Configure pytest-asyncio to use SelectorEventLoop on Windows."""
    if sys.platform == "win32":
        # Set the event loop policy before any async code runs
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
