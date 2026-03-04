from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    func: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay: float = 0.75,
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == attempts:
                break
            await asyncio.sleep(base_delay * attempt)
    if last_error is None:
        raise RuntimeError("retry_async failed without exception")
    raise last_error
