from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay: float = 1.0,
    factor: float = 3.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Exponential backoff retry. Delays: base, base*factor, base*factor^2, ..."""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            last = e
            if i == attempts - 1:
                raise
            await asyncio.sleep(base_delay * (factor**i))
    assert last is not None
    raise last
