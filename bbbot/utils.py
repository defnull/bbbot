from bs4 import BeautifulSoup
import asyncio
import contextlib
import logging
import typing
logger = logging.getLogger(__name__)

def soupify(html):
    return BeautifulSoup(html, features="html.parser")


class Events:
    def __init__(self, *names):
        self.events = {name: asyncio.Event() for name in names}

    def set(self, name):
        self.events[name].set()

    async def wait(self, name, timeout=None):
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.events[name].wait(), timeout)
        return self.events[name].is_set()


class AsyncCloseable:
    def __init__(self):
        self._on_close = []
        self._closed = asyncio.Event()

    def on_close(self, func):
        self._on_close.append(func)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        for closer in self._on_close:
            try:
                await closer()
            except:
                logger.exception(f"Failed to close: {closer} in {self}.close()")
        self._closed.set()

    async def wait_closed(self):
        await self._closed.wait()


class Waiter:
    def __init__(self):
        self.waiting : list[tuple[typing.Callable[..., typing.Any], asyncio.Event]] = []

    def expect(self, condition: typing.Callable[..., typing.Any]):
        event = asyncio.Event()
        self.waiting.append((condition, event))
        return event
    
    def on_event(self, *a, **ka):
        def triggered(condition, event):
            if condition(*a, **ka):
                event.set()
            return event.is_set
        
        self.waiting[:] = [waiter for waiter in self.waiting if not triggered(*waiter)]
